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
  get_plugin_metadata,
  list_plugins,
  load_registry,
)
from adapters.mjlab.algorithms.registry import (  # noqa: E402
  list_algorithms,
  resolve,
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

  def test_capability_catalog_unchanged(self):
    self.assertEqual({"PPO", "SAC", "TD3"}, {item["id"] for item in list_algorithms()})


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
