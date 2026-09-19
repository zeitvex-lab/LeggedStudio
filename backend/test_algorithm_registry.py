"""算法插件注册表（registry.json / registry.py / 插件包）测试。

与 ``test_algorithm_plugins.py`` 分工：那边守插件协议 / 迁移兼容性 / profile
切换的完整面；这边只守**注册表本身**的最小契约：

1. ``registry.json`` 加载与按名解析（含未知名 fail-closed）；
2. ``registry.py::resolve`` 的 ValueError 语义 + 控制面能力目录不回退；
3. 7 个注册插件包（go2 四族 + UniLab 三族）可 import；
4. ``local_tasks.learning`` 薄 re-export 指向迁移后的同一类对象。

两层口径（与仓库测试基建一致）：控制面用例无 torch 必跑；运行面用例需要
训练栈（``adapters/mjlab/.venv``），控制面环境自动跳过。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from adapters.mjlab.algorithms.base import REGISTRY_SCHEMA_VERSION  # noqa: E402
from adapters.mjlab.algorithms.plugin_registry import (  # noqa: E402
  apply_algorithm_plugin,
  get_plugin_metadata,
  list_plugins,
  load_registry,
)
from adapters.mjlab.algorithms.registry import (  # noqa: E402
  list_algorithms,
  resolve,
  resolve_algorithm,
)

EXPECTED_PLUGINS = ("amp", "appo", "cts", "distill", "dreamwaq", "him", "hora")


class RegistryControlPlaneTest(unittest.TestCase):
  """注册表加载 / 解析 / fail-closed（纯 JSON，无 torch 必跑）。"""

  def test_registry_loads_seven_plugins(self):
    registry = load_registry()
    self.assertEqual(REGISTRY_SCHEMA_VERSION, registry["schema_version"])
    self.assertEqual(sorted(EXPECTED_PLUGINS), sorted(registry["plugins"]))

  def test_every_plugin_metadata_declared(self):
    for name in EXPECTED_PLUGINS:
      with self.subTest(plugin=name):
        self.assertEqual(name, get_plugin_metadata(name)["name"])

  def test_registry_resolve_unknown_fails_closed(self):
    with self.assertRaises(ValueError) as ctx:
      resolve("no_such_algorithm")
    self.assertIn("available", str(ctx.exception))
    self.assertIn("cts", str(ctx.exception))

  def test_capability_catalog_covers_native_and_plugins(self):
    """单一词汇表：一份清单同时含内置 runner 算法与插件（2026-09-19 收口）。

    此前这里钉的是 `{"PPO","SAC","TD3"}`——那是"只认内置、插件另立一份词表"的旧形态；
    profile 里的 `algorithm: "HIM"` 因此不属于任何一份词表，谁都不认。
    """

    entries = {item["id"]: item for item in list_algorithms()}
    self.assertEqual({"PPO", "SAC", "TD3"} | set(EXPECTED_PLUGINS), set(entries))
    for name, item in entries.items():
      with self.subTest(algo=name):
        self.assertIn(item["kind"], {"native", "plugin"})
        self.assertTrue(item["registered"])
        # `available` 是 `product_open` 的别名（前端按它决定能不能选）
        self.assertEqual(item["product_open"], item["available"])

  def test_only_ppo_is_product_open(self):
    """三个"能"必须分清：注册 ≠ 能接进来 ≠ 产品内可创建训练。"""

    self.assertEqual(["PPO"], sorted(item["id"] for item in list_algorithms() if item["product_open"]))

  def test_plugin_entry_declares_provenance_and_binding(self):
    him = next(item for item in list_algorithms() if item["id"] == "him")
    self.assertEqual("plugin", him["kind"])
    self.assertTrue(him["native_supported"], "有 variants 绑定 ⇒ 能接进 native runner")
    self.assertFalse(him["product_open"], "未经真训练验证 ⇒ 产品内不开放")
    self.assertTrue(him["upstream"] and him["license"] and him["variants"])
    self.assertIn("HIM", him["label"])

  def test_resolve_algorithm_by_native_label(self):
    entry = resolve_algorithm("ppo")           # 大小写不敏感
    self.assertEqual("PPO", entry["id"])
    self.assertEqual("native", entry["kind"])
    self.assertTrue(entry["product_open"])

  def test_resolve_algorithm_by_plugin_name(self):
    entry = resolve_algorithm("HIM")           # 大写同样命中插件名
    self.assertEqual("him", entry["id"])
    self.assertEqual("plugin", entry["kind"])
    self.assertFalse(entry["product_open"])

  def test_resolve_algorithm_prefers_explicit_plugin(self):
    entry = resolve_algorithm("HIM", plugin="him")
    self.assertEqual("him", entry["id"])
    self.assertEqual("algorithm_plugin", entry["resolved_by"])

  def test_resolve_algorithm_unknown_lists_both_vocabularies(self):
    with self.assertRaises(ValueError) as ctx:
      resolve_algorithm("magic")
    message = str(ctx.exception)
    self.assertIn("PPO", message)
    self.assertIn("cts", message)

  def test_resolve_algorithm_unknown_plugin_fails_closed(self):
    with self.assertRaises(ValueError):
      resolve_algorithm("him", plugin="no_such_plugin")


class ApplyAlgorithmPluginTest(unittest.TestCase):
  """插件绑定：**profile 显式声明才生效**，且只需注册表（纯 JSON）即可决策。

  这条是"算法像插件一样可插拔"的接线点：worker 在 profile 声明 ``algorithm_plugin``
  时调它把 class_name 写进 runner cfg；没声明的 profile（52 个里的 50 个）一行不碰。
  """

  class _Node:
    def __init__(self) -> None:
      self.class_name = ""

  class _Cfg:
    def __init__(self) -> None:
      self.algorithm = ApplyAlgorithmPluginTest._Node()
      self.actor = ApplyAlgorithmPluginTest._Node()
      self.actor.distribution_cfg = None
      self.critic = ApplyAlgorithmPluginTest._Node()

  def test_binding_writes_class_names(self):
    cfg = self._Cfg()
    report = apply_algorithm_plugin(cfg, algorithm_plugin="him")
    self.assertEqual("him", report["plugin"])
    self.assertEqual("base", report["variant"])
    self.assertTrue(cfg.algorithm.class_name.endswith("HimPPO"))
    self.assertTrue(cfg.actor.class_name.endswith("HIMActorModel"))
    self.assertTrue(cfg.critic.class_name)

  def test_variant_selection(self):
    cfg = self._Cfg()
    report = apply_algorithm_plugin(cfg, algorithm_plugin="cts", variant="amp")
    self.assertEqual("amp", report["variant"])
    self.assertTrue(cfg.algorithm.class_name.endswith("AmpCtsPPO"))

  def test_unknown_plugin_fails_closed(self):
    with self.assertRaises(Exception):
      apply_algorithm_plugin(self._Cfg(), algorithm_plugin="no_such_plugin")

  def test_unknown_variant_fails_closed(self):
    with self.assertRaises(Exception):
      apply_algorithm_plugin(self._Cfg(), algorithm_plugin="him", variant="nope")


try:
  import torch  # noqa: F401

  _TRAINING_STACK = True
except ImportError:  # pragma: no cover - control plane environment
  _TRAINING_STACK = False


@unittest.skipUnless(_TRAINING_STACK, "training stack (torch) not available")
class RegistryRuntimeTest(unittest.TestCase):
  """插件包可 import、按名解析出元数据一致的插件、re-export 路径不变。"""

  @classmethod
  def setUpClass(cls):
    source_root = str(
      ROOT / "assets" / "robots" / "unitree_go2" / "training" / "source"
    )
    if source_root not in sys.path:
      sys.path.insert(0, source_root)

  def test_go2_plugin_packages_import(self):
    from adapters.mjlab.algorithms.base import AlgorithmPlugin
    from adapters.mjlab.algorithms.amp import AmpPlugin
    from adapters.mjlab.algorithms.cts import CtsPlugin
    from adapters.mjlab.algorithms.distill import DistillPlugin
    from adapters.mjlab.algorithms.dreamwaq import DreamWaQPlugin

    for plugin_class in (CtsPlugin, DreamWaQPlugin, AmpPlugin, DistillPlugin):
      self.assertTrue(issubclass(plugin_class, AlgorithmPlugin))

  def test_unilab_plugin_packages_import(self):
    from adapters.mjlab.algorithms.appo import AppoPlugin
    from adapters.mjlab.algorithms.him import HIMPlugin
    from adapters.mjlab.algorithms.hora import HoraPlugin

    self.assertEqual({"him", "hora", "appo"},
                     {p.name for p in (HIMPlugin(), HoraPlugin(), AppoPlugin())})

  def test_registry_resolve_returns_named_plugin(self):
    for name in EXPECTED_PLUGINS:
      with self.subTest(plugin=name):
        self.assertEqual(name, resolve(name).name)

  def test_local_tasks_reexport_paths_unchanged(self):
    from adapters.mjlab.algorithms.amp.models import AmpDiscriminator
    from adapters.mjlab.algorithms.cts.algorithms import CtsPPO
    from adapters.mjlab.algorithms.dreamwaq.algorithms import DreamWaQPPO
    from local_tasks.learning.algorithms import (
      CtsPPO as LegacyCtsPPO,
      DreamWaQPPO as LegacyDreamWaQPPO,
    )
    from local_tasks.learning.models import (
      AmpDiscriminator as LegacyAmpDiscriminator,
    )

    self.assertIs(CtsPPO, LegacyCtsPPO)
    self.assertIs(DreamWaQPPO, LegacyDreamWaQPPO)
    self.assertIs(AmpDiscriminator, LegacyAmpDiscriminator)

  def test_top_level_lazy_exports_same_classes(self):
    import adapters.mjlab.algorithms as pkg
    from adapters.mjlab.algorithms.appo import APPOLearner
    from adapters.mjlab.algorithms.cts import CtsPPO
    from adapters.mjlab.algorithms.him import HIMPPO

    self.assertIs(pkg.CtsPPO, CtsPPO)
    self.assertIs(pkg.HIMPPO, HIMPPO)
    self.assertIs(pkg.APPOLearner, APPOLearner)


if __name__ == "__main__":
  unittest.main()
