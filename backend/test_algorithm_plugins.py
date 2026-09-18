"""算法插件层（B: algorithm plugin layer）——协议、注册表、迁移兼容性测试。

## 这组测试守的是什么

算法像插件一样可插拔（UniLab 级兼容目标）：CTS / DreamWaQ / AMP / distill
四族算法从 ``local_tasks/learning`` 迁入
``adapters/mjlab/algorithms/<family>/``，经 ``registry.json`` 按名解析；
``local_tasks.learning.{algorithms,models,storage,motion}`` 只留薄 re-export，
entrypoint 字符串（``unitree_go2_custom_runner_cfg`` 的 class_name 字典、
training catalog、bootstrap 的 legacy mjlab.* 别名）全部继续指向**同一个类对象**。

两层口径（与仓库测试基建一致）：

1. **控制面层（无 torch，CI ``unittest discover`` 必跑）**：注册表加载 /
   校验 / fail-closed、插件协议的 AST 静态合规（4 个 build 方法 + 4 个
   元数据字段）、re-export shim 的静态形状、go2-cts profile 的
   ``algorithm_plugin`` 按名解析、registry legacy_entrypoints 与
   ``config.py`` 硬编码字典的一致性。
2. **运行面层（需要训练栈；在 mjlab venv 下跑：
   ``adapters/mjlab/.venv/Scripts/python -m unittest
   backend.test_algorithm_plugins -v``）**：4 个插件类可 import 且类属性
   与注册表一致、4 个 build 方法真实可调、ONNX 产物自证（B44）、新旧
   路径类对象同一性、entrypoint 工厂与注册表绑定产出同一组类。
"""

from __future__ import annotations

import ast
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from adapters.mjlab.algorithms.base import (  # noqa: E402
  BUILD_METHODS,
  METADATA_FIELDS,
  REGISTRY_SCHEMA_VERSION,
)
from adapters.mjlab.algorithms.plugin_registry import (  # noqa: E402
  PluginRegistryError,
  get_plugin_metadata,
  list_plugins,
  load_registry,
  plugin_variants,
  variant_entrypoints,
)

ALGORITHMS_DIR = ROOT / "adapters" / "mjlab" / "algorithms"
REGISTRY_JSON = ALGORITHMS_DIR / "registry.json"
LOCAL_TASKS = ROOT / "assets" / "robots" / "unitree_go2" / "training" / "source" / "local_tasks"
GO2_CONFIG_PY = (
  LOCAL_TASKS / "robots" / "unitree" / "go2" / "training" / "config.py"
)
GO2_CTS_PROFILE = ROOT / "assets" / "robots" / "unitree_go2" / "training" / "profiles" / "go2-cts.json"

#: 已注册的算法族（增删是有意动作，须连同本清单一起改）：
#: go2 迁移四族（amp/cts/distill/dreamwaq）+ UniLab 提取三族（appo/him/hora）。
EXPECTED_PLUGINS = ("amp", "appo", "cts", "distill", "dreamwaq", "him", "hora")

#: 迁移后必须变成薄 re-export 的四个模块（canonical 实现在插件层）。
SHIM_MODULES = {
  "algorithms.py": "adapters.mjlab.algorithms",
  "models.py": "adapters.mjlab.algorithms",
  "storage.py": "adapters.mjlab.algorithms.common.storage",
  "motion.py": "adapters.mjlab.algorithms.common.motion",
}


def _module_level_imports(tree: ast.Module) -> list[ast.ImportFrom]:
  return [stmt for stmt in tree.body if isinstance(stmt, ast.ImportFrom)]


def _class_defs(tree: ast.Module) -> dict[str, ast.ClassDef]:
  return {
    stmt.name: stmt for stmt in tree.body if isinstance(stmt, ast.ClassDef)
  }


def _method_names(class_def: ast.ClassDef) -> set[str]:
  names: set[str] = set()
  for stmt in class_def.body:
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
      names.add(stmt.name)
  return names


def _assigned_names(class_def: ast.ClassDef) -> dict[str, object]:
  values: dict[str, object] = {}
  for stmt in class_def.body:
    if isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Name):
      values[stmt.targets[0].id] = stmt.value
  return values


class RegistryLoadTest(unittest.TestCase):
  """注册表加载与校验（纯 JSON，控制面安全）。"""

  def test_registry_file_exists_and_validates(self):
    registry = load_registry()
    self.assertEqual(REGISTRY_SCHEMA_VERSION, registry["schema_version"])
    self.assertEqual(sorted(EXPECTED_PLUGINS), list_plugins())

  def test_every_plugin_entry_well_formed(self):
    registry = load_registry()
    for name, entry in registry["plugins"].items():
      with self.subTest(plugin=name):
        self.assertTrue(entry["module"].startswith("adapters.mjlab.algorithms."))
        self.assertTrue(entry["plugin_class"])
        metadata = get_plugin_metadata(name)
        for field in METADATA_FIELDS:
          self.assertTrue(metadata[field], f"{name}.{field} empty")
        self.assertEqual(name, metadata["name"])
        variants = plugin_variants(name)
        self.assertTrue(variants)
        for variant, binding in variants.items():
          self.assertIn("algorithm", binding)
          self.assertIn("actor", binding)

  def test_known_variants_resolve_to_declared_modules(self):
    """variant 的 class_name 都指向声明过的插件层模块（或 rsl_rl 默认）。"""
    for name in list_plugins():
      for variant, binding in plugin_variants(name).items():
        for key, target in binding.items():
          if key == "distribution" or ":" not in target:
            continue
          module = target.split(":", 1)[0]
          self.assertTrue(
            module.startswith(("adapters.mjlab.algorithms.", "rsl_rl.")),
            f"{name}/{variant}/{key} -> {module}",
          )


class RegistryFailClosedTest(unittest.TestCase):
  """未知算法 / 畸形注册表 fail-closed。"""

  def test_unknown_plugin_name_fails_closed(self):
    for caller in (get_plugin_metadata, plugin_variants):
      with self.subTest(caller=caller.__name__):
        with self.assertRaises(PluginRegistryError) as ctx:
          caller("no_such_algorithm")
        self.assertIn("available", str(ctx.exception))
        for name in EXPECTED_PLUGINS:
          self.assertIn(name, str(ctx.exception))

  def test_unknown_variant_fails_closed(self):
    with self.assertRaises(PluginRegistryError):
      variant_entrypoints("cts", "no_such_variant")

  def _write_registry(self, payload: object) -> Path:
    tmp = tempfile.NamedTemporaryFile(
      "w", suffix=".json", delete=False, encoding="utf-8"
    )
    json.dump(payload, tmp)
    tmp.close()
    self.addCleanup(Path(tmp.name).unlink)
    return Path(tmp.name)

  def test_malformed_registry_fails_closed(self):
    good = load_registry()
    cases = {
      "not-json": None,  # replaced below with invalid text
      "bad-schema": {**good, "schema_version": "0.0-mismatch"},
      "no-plugins": {"schema_version": REGISTRY_SCHEMA_VERSION, "plugins": {}},
    }
    with tempfile.NamedTemporaryFile(
      "w", suffix=".json", delete=False, encoding="utf-8"
    ) as handle:
      handle.write("{not json")
      cases["not-json"] = Path(handle.name)
    self.addCleanup(Path(cases["not-json"]).unlink)
    for label, payload in cases.items():
      with self.subTest(case=label):
        path = payload if isinstance(payload, Path) else self._write_registry(payload)
        with self.assertRaises(PluginRegistryError):
          load_registry(path)

  def test_entry_missing_required_keys_fails_closed(self):
    good = json.loads(REGISTRY_JSON.read_text(encoding="utf-8"))
    del good["plugins"]["cts"]["module"]
    with self.assertRaises(PluginRegistryError):
      load_registry(self._write_registry(good))

  def test_metadata_name_mismatch_fails_closed(self):
    good = json.loads(REGISTRY_JSON.read_text(encoding="utf-8"))
    good["plugins"]["cts"]["metadata"]["name"] = "typo"
    with self.assertRaises(PluginRegistryError):
      load_registry(self._write_registry(good))


class PluginProtocolStaticTest(unittest.TestCase):
  """每个注册插件的 AST 静态协议合规（4 build 方法 + 4 元数据字段）。"""

  def _plugin_module_path(self, name: str) -> Path:
    entry = load_registry()["plugins"][name]
    relative = entry["module"].replace("adapters.mjlab.algorithms.", "")
    path = ALGORITHMS_DIR / Path(relative)
    return path / "__init__.py" if path.is_dir() else path.with_suffix(".py")

  def test_plugin_class_declares_full_protocol(self):
    registry = load_registry()
    for name in EXPECTED_PLUGINS:
      module_path = self._plugin_module_path(name)
      self.assertTrue(module_path.is_file(), module_path)
      tree = ast.parse(module_path.read_text(encoding="utf-8"))
      classes = _class_defs(tree)
      plugin_class = registry["plugins"][name]["plugin_class"]
      self.assertIn(plugin_class, classes, f"{module_path} lacks {plugin_class}")
      class_def = classes[plugin_class]
      methods = _method_names(class_def)
      for method in BUILD_METHODS:
        self.assertIn(method, methods, f"{name}.{plugin_class}.{method}")
      assigned = _assigned_names(class_def)
      declared = load_registry()["plugins"][name]["metadata"]
      for field in METADATA_FIELDS:
        self.assertIn(field, assigned, f"{name}.{plugin_class}.{field}")
      # 静态一致性：注册表与类声明的观测类型清单逐字一致。
      static_obs = declared["supported_obs_types"]
      node = assigned["supported_obs_types"]
      if isinstance(node, (ast.Tuple, ast.List)):
        self.assertEqual(
          static_obs,
          [element.value for element in node.elts if isinstance(element, ast.Constant)],
        )

  def test_family_layout_complete(self):
    """每族一目录：algorithms.py + models.py + config.py + README.md。"""
    for name in EXPECTED_PLUGINS:
      family = ALGORITHMS_DIR / name
      for artifact in ("algorithms.py", "models.py", "config.py", "README.md"):
        self.assertTrue((family / artifact).is_file(), family / artifact)

  def test_registry_metadata_matches_readme_registry_key(self):
    for name in EXPECTED_PLUGINS:
      readme = (ALGORITHMS_DIR / name / "README.md").read_text(encoding="utf-8")
      self.assertIn(f"Registry key: `{name}`", readme)


class LocalTasksShimTest(unittest.TestCase):
  """local_tasks/learning 薄 re-export：静态形状与 legacy 符号面不变。"""

  def test_shims_import_from_plugin_layer_only(self):
    for filename, expected_source in SHIM_MODULES.items():
      path = LOCAL_TASKS / "learning" / filename
      tree = ast.parse(path.read_text(encoding="utf-8"))
      imports = _module_level_imports(tree)
      self.assertTrue(imports, f"{path} has no module-level imports")
      for stmt in imports:
        if stmt.module == "__future__":
          continue
        source = stmt.module or ""
        if stmt.level:  # 相对导入只允许同包 rollout/symmetry 这类未迁移模块
          self.assertNotIn(filename, ("algorithms.py", "models.py", "storage.py", "motion.py"))
        else:
          self.assertTrue(
            source.startswith("adapters.mjlab.algorithms"),
            f"{path} imports {source!r}, expected {expected_source}.*",
          )

  def test_legacy_symbol_surface_unchanged(self):
    """learning/__init__.py 导出的 legacy 符号面逐字不变（shim 再导出）。"""
    init = (LOCAL_TASKS / "learning" / "__init__.py").read_text(encoding="utf-8")
    # 迁移前 learning/__init__.py 的完整 __all__（Go2CustomRunner 留在本地
    # rollout.py；Go2ClampedGaussianDistribution 原本就只经 models 模块消费）。
    original_surface = (
      "AmpAlgorithm", "AmpCtsPPO", "AmpDiscriminator", "AmpDreamWaQPPO",
      "AmpPPO", "AmpTeacherStudentPPO", "CtsActorCritic", "CtsActorModel",
      "CtsAlgorithm", "CtsCriticModel", "CtsPPO", "CtsStudentActorModel",
      "DreamWaQActorCritic", "DreamWaQActorModel", "DreamWaQAlgorithm",
      "DreamWaQPPO", "GO2_JOINT_NAMES", "Go2AmpReplayBuffer",
      "Go2AuxiliaryPPO", "Go2CustomRunner", "Go2MotionLoader",
      "Go2MotionTrajectory", "Go2RolloutStorage", "Go2RunningNormalizer",
      "Go2Transition", "StudentActorModel", "TeacherActorModel",
      "TeacherStudentActorCritic", "TeacherStudentAlgorithm",
      "TeacherStudentPPO", "joint_permutation",
    )
    for symbol in original_surface:
      self.assertIn(symbol, init, f"learning/__init__.py lost {symbol}")
    # shim 文件层面：四模块的 legacy 类名仍从插件层再导出。
    expected = {
      "algorithms.py": (
        "AmpAlgorithm", "AmpCtsPPO", "AmpDreamWaQPPO", "AmpPPO",
        "AmpTeacherStudentPPO", "CtsAlgorithm", "CtsPPO", "DreamWaQAlgorithm",
        "DreamWaQPPO", "Go2AuxiliaryPPO", "TeacherStudentAlgorithm",
        "TeacherStudentPPO",
      ),
      "models.py": (
        "AmpDiscriminator", "CtsActorCritic", "CtsActorModel", "CtsCriticModel",
        "CtsStudentActorModel", "DreamWaQActorCritic", "DreamWaQActorModel",
        "Go2ClampedGaussianDistribution", "StudentActorModel", "TeacherActorModel",
        "TeacherStudentActorCritic",
      ),
      "storage.py": (
        "Go2AmpReplayBuffer", "Go2RolloutStorage", "Go2RunningNormalizer",
        "Go2Transition",
      ),
      "motion.py": (
        "GO2_JOINT_NAMES", "Go2MotionLoader", "Go2MotionTrajectory",
        "joint_permutation",
      ),
    }
    for filename, symbols in expected.items():
      shim = ast.parse((LOCAL_TASKS / "learning" / filename).read_text(encoding="utf-8"))
      exported = set()
      for stmt in _module_level_imports(shim):
        exported.update(alias.name for alias in stmt.names)
      self.assertTrue(set(symbols).issubset(exported), f"{filename}: {set(symbols) - exported}")

  def test_registry_legacy_entrypoints_cover_config_dicts(self):
    """config.py 的 class_name 硬编码字典被注册表 legacy_entrypoints 完整覆盖。"""
    config_text = GO2_CONFIG_PY.read_text(encoding="utf-8")
    literal_strings = set(re.findall(r'"(local_tasks\.learning\.[A-Za-z_.]+)"', config_text))
    registry = load_registry()
    declared = {
      value
      for entry in registry["plugins"].values()
      for value in entry.get("legacy_entrypoints", {}).values()
    }
    missing = literal_strings - declared
    self.assertFalse(
      missing,
      f"config.py class_name strings absent from registry legacy_entrypoints: {sorted(missing)}",
    )


class ProfilePluginSwitchTest(unittest.TestCase):
  """go2-cts profile：不改 entrypoint，算法层经注册表按名解析。"""

  def test_go2_cts_profile_declares_registry_plugin(self):
    profile = json.loads(GO2_CTS_PROFILE.read_text(encoding="utf-8"))
    self.assertEqual("cts", profile.get("algorithm_plugin"))
    # entrypoint 三键原样保留（audit_training_entrypoints 的硬门禁对象）。
    self.assertEqual(
      {
        "env": "local_tasks.robots.unitree.go2.tasks.locomotion.variants:unitree_go2_cts_env_cfg",
        "runner": "local_tasks.robots.unitree.go2.training.config:go2_cts_runner_cfg",
        "runner_class": "local_tasks.robots.unitree.go2.training.runner:VelocityOnPolicyRunner",
      },
      profile["entrypoints"],
    )

  def test_profile_plugin_name_resolves_in_registry(self):
    profile = json.loads(GO2_CTS_PROFILE.read_text(encoding="utf-8"))
    name = profile["algorithm_plugin"]
    metadata = get_plugin_metadata(name)  # fail-closed: 未知名直接抛错
    self.assertEqual("cts", metadata["name"])
    binding = variant_entrypoints(name, "base")
    for key in ("algorithm", "actor", "critic"):
      self.assertIn(key, binding)


# --------------------------------------------------------------------------- #
# 运行面层：需要 torch/rsl_rl/mjlab；控制面 CI 自动跳过。
# 在训练 venv 下显式运行：
#   adapters/mjlab/.venv/Scripts/python -m unittest backend.test_algorithm_plugins -v
# --------------------------------------------------------------------------- #

try:
  import torch  # noqa: F401

  _TRAINING_STACK = True
except ImportError:  # pragma: no cover - control plane environment
  _TRAINING_STACK = False


@unittest.skipUnless(_TRAINING_STACK, "training stack (torch) not available")
class PluginRuntimeTest(unittest.TestCase):
  """全部注册插件可 import、类属性正确、协议合规（运行时验证）。"""

  @classmethod
  def setUpClass(cls):
    from adapters.mjlab.algorithms.plugin_registry import resolve_plugin

    cls.plugins = {name: resolve_plugin(name) for name in list_plugins()}

  def test_four_plugins_resolved_with_correct_class_attributes(self):
    from adapters.mjlab.algorithms.amp import AmpPlugin
    from adapters.mjlab.algorithms.cts import CtsPlugin
    from adapters.mjlab.algorithms.distill import DistillPlugin
    from adapters.mjlab.algorithms.dreamwaq import DreamWaQPlugin

    classes = {
      "cts": CtsPlugin,
      "dreamwaq": DreamWaQPlugin,
      "amp": AmpPlugin,
      "distill": DistillPlugin,
    }
    for name, plugin_class in classes.items():
      plugin = self.plugins[name]
      self.assertIsInstance(plugin, plugin_class)
      metadata = get_plugin_metadata(name)
      self.assertEqual(metadata["name"], plugin.name)
      self.assertEqual(metadata["upstream"], plugin.upstream)
      self.assertEqual(metadata["license"], plugin.license)
      self.assertEqual(
        tuple(metadata["supported_obs_types"]), tuple(plugin.supported_obs_types)
      )

  def test_protocol_compliance_runtime(self):
    from adapters.mjlab.algorithms.base import verify_plugin

    for name, plugin in self.plugins.items():
      self.assertEqual([], verify_plugin(plugin), name)

  def test_verify_plugin_reports_violations(self):
    from adapters.mjlab.algorithms.base import verify_plugin

    class Incomplete:  # 缺全部协议成员
      pass

    violations = verify_plugin(Incomplete())
    for method in BUILD_METHODS:
      self.assertIn(f"missing build method: {method}", violations)
    for field in METADATA_FIELDS:
      self.assertIn(f"missing metadata field: {field}", violations)

  def test_build_methods_real_calls(self):
    from adapters.mjlab.algorithms.common.storage import (
      Go2AmpReplayBuffer,
      Go2RolloutStorage,
    )

    cts = self.plugins["cts"]
    model = cts.build_actor_critic(45, 12, {"privileged_dim": 70, "history_dim": 225})
    storage = cts.build_storage({"num_steps": 4, "num_envs": 2})
    optimizer = cts.build_optimizer(model.parameters(), {"learning_rate": 3e-4})
    self.assertIsInstance(model, torch.nn.Module)
    self.assertIsInstance(storage, Go2RolloutStorage)
    self.assertEqual(3e-4, optimizer.param_groups[0]["lr"])

    dreamwaq = self.plugins["dreamwaq"]
    self.assertIsInstance(
      dreamwaq.build_actor_critic(45, 12), torch.nn.Module
    )
    amp = self.plugins["amp"]
    discriminator = amp.build_actor_critic(31, 0)
    replay = amp.build_storage({"replay_buffer_size": 128})
    self.assertIsInstance(replay, Go2AmpReplayBuffer)
    self.assertEqual(62, discriminator.net[0].in_features)  # (state, next) 拼接
    distill = self.plugins["distill"]
    self.assertIsInstance(distill.build_actor_critic(45, 12), torch.nn.Module)

  def test_export_onnx_self_certification(self):
    """四族插件各自产出非空 ONNX（B44 产物自证兼容）。"""
    import os

    with tempfile.TemporaryDirectory() as tmp:
      for name, plugin in self.plugins.items():
        target = os.path.join(tmp, f"{name}.onnx")
        written = plugin.export_onnx(target)
        self.assertTrue(Path(written).is_file())
        self.assertGreater(Path(written).stat().st_size, 0, name)


@unittest.skipUnless(_TRAINING_STACK, "training stack (torch) not available")
class ReexportIdentityTest(unittest.TestCase):
  """新旧路径类对象同一性 + entrypoint 工厂与注册表绑定一致。"""

  @classmethod
  def setUpClass(cls):
    source_root = str(
      ROOT / "assets" / "robots" / "unitree_go2" / "training" / "source"
    )
    if source_root not in sys.path:
      sys.path.insert(0, source_root)

  def test_legacy_module_paths_same_class_objects(self):
    from adapters.mjlab.algorithms.amp.models import AmpDiscriminator
    from adapters.mjlab.algorithms.cts.algorithms import CtsPPO
    from adapters.mjlab.algorithms.cts.models import CtsActorModel
    from adapters.mjlab.algorithms.common.auxiliary_ppo import Go2AuxiliaryPPO
    from adapters.mjlab.algorithms.distill.models import StudentActorModel
    from adapters.mjlab.algorithms.dreamwaq.algorithms import DreamWaQPPO
    from local_tasks.learning.algorithms import (
      AmpPPO,
      CtsPPO as LegacyCtsPPO,
      DreamWaQPPO as LegacyDreamWaQ,
      Go2AuxiliaryPPO as LegacyAuxiliaryPPO,
    )
    from local_tasks.learning.models import (
      AmpDiscriminator as LegacyAmpDisc,
      CtsActorModel as LegacyCtsActor,
      StudentActorModel as LegacyStudent,
    )

    self.assertIs(LegacyCtsPPO, CtsPPO)
    self.assertIs(LegacyDreamWaQ, DreamWaQPPO)
    self.assertIs(LegacyCtsActor, CtsActorModel)
    self.assertIs(LegacyAmpDisc, AmpDiscriminator)
    self.assertIs(LegacyStudent, StudentActorModel)
    self.assertIs(LegacyAuxiliaryPPO, Go2AuxiliaryPPO)
    self.assertTrue(callable(AmpPPO))

  def test_runner_cfg_factory_and_registry_bind_same_classes(self):
    """go2-cts entrypoint 工厂（未改）与注册表按名绑定产出同一组类对象。"""
    import copy

    from adapters.mjlab.algorithms.plugin_registry import bind_algorithm_to_runner_cfg
    from local_tasks.robots.unitree.go2.training.config import go2_cts_runner_cfg
    from rsl_rl.utils import resolve_callable

    legacy = go2_cts_runner_cfg()
    binding = variant_entrypoints("cts", "base")
    for key, legacy_string in (
      ("algorithm", legacy.algorithm.class_name),
      ("actor", legacy.actor.class_name),
      ("critic", legacy.critic.class_name),
    ):
      self.assertIs(
        resolve_callable(legacy_string), resolve_callable(binding[key]), key
      )

    bound = copy.deepcopy(legacy)
    bound.algorithm.class_name = "rsl_rl.algorithms.ppo:PPO"
    bind_algorithm_to_runner_cfg(bound, "cts", "base")
    for key, attr in (
      ("algorithm", bound.algorithm),
      ("actor", bound.actor),
      ("critic", bound.critic),
    ):
      self.assertIs(resolve_callable(attr.class_name), resolve_callable(binding[key]))

  def test_all_legacy_kinds_equal_registry_variants(self):
    from local_tasks.robots.unitree.go2.training.config import (
      unitree_go2_custom_runner_cfg,
    )
    from rsl_rl.utils import resolve_callable

    for kind, name, variant in (
      ("cts", "cts", "base"),
      ("amp_cts", "cts", "amp"),
      ("dreamwaq", "dreamwaq", "base"),
      ("amp_dreamwaq", "dreamwaq", "amp"),
      ("amp_ts", "amp", "ts"),
      ("amp_ts_student", "distill", "amp_student"),
      ("ts", "distill", "teacher"),
      ("ts_student", "distill", "student"),
    ):
      with self.subTest(kind=kind):
        legacy = unitree_go2_custom_runner_cfg(kind)
        binding = variant_entrypoints(name, variant)
        self.assertIs(
          resolve_callable(legacy.algorithm.class_name),
          resolve_callable(binding["algorithm"]),
        )
        self.assertIs(
          resolve_callable(legacy.actor.class_name),
          resolve_callable(binding["actor"]),
        )


if __name__ == "__main__":
  unittest.main()
