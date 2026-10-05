"""控制插件注册表回归锁（MPC 轴，2026-10-05）——校验是 fail-loud 的，锁也要 fail-loud。

守住四件事：①真实表加载全绿（id 唯一 / 词汇闭合 / 快照在盘 / 溯源锚点齐）；
②坏声明逐项判红（重复 id / 越界词汇 / 悬空路径 / 无 license 未登记零许可）；
③面板投影三面同源（CLI provider 可解析、panels 声明存在、summary 可 JSON 序列化）；
④只做声明不做执行体（本表不 import 任何上游参考代码——参考是数据不是依赖）。
"""

from __future__ import annotations

import importlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

cp = importlib.import_module("backend.controller_plugins")


def _mk_registry(root: Path, controllers: list[dict], vocabulary: dict | None = None) -> Path:
    reg_dir = root / "registry" / "controllers"
    reg_dir.mkdir(parents=True)
    # 声明的快照路径如实建在盘上（快照在盘是加载校验的一部分）——
    # 但**只建 snapshot 命名的**：悬空声明的用例靠"夹具不替它兜底"成立。
    (root / "refs").mkdir(exist_ok=True)
    for i, entry in enumerate(controllers):
        rel = str((entry.get("source") or {}).get("path") or f"refs/snapshot{i}")
        if "/snapshot" in rel:
            (root / rel).mkdir(parents=True, exist_ok=True)
    data = {
        "schema": "controller-registry-1.0",
        "vocabulary": vocabulary if vocabulary is not None else {
            "mechanism_class": ["centroidal_mpc"],
            "status": ["audit"],
        },
        "controllers": controllers,
    }
    (reg_dir / "index.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return root


def _valid_entry(**overrides) -> dict:
    entry = {
        "controller_id": "test-mpc",
        "label": "测试",
        "mechanism_class": "centroidal_mpc",
        "source": {"path": "refs/snapshot-a", "snapshot_head": "1234567",
                   "license": "MIT"},
        "porting": {"status": "audit", "mechanism_files": []},
    }
    entry.update(overrides)
    return entry


class RealRegistryTest(unittest.TestCase):
    def test_real_registry_loads_and_is_coherent(self):
        data = cp.load_registry()
        ids = [e["controller_id"] for e in data["controllers"]]
        self.assertEqual(len(ids), len(set(ids)), "id 唯一")
        self.assertGreaterEqual(len(ids), 5, "MPC 参考 5 份应全部登记")
        # 快照在盘 + 词汇闭合（load_registry 已校验，这里锁读数形状）
        s = cp.summary()
        self.assertEqual(s["count"], len(ids))
        self.assertEqual(s["count"], sum(s["by_mechanism_class"].values()))
        self.assertEqual(s["count"], sum(s["by_porting_status"].values()))

    def test_snapshot_head_hashes_recorded(self):
        """溯源锚点：每条都带上游 HEAD（无 .git 快照靠它对上游，B19 教训）。"""
        for entry in cp.list_controllers():
            with self.subTest(controller=entry["controller_id"]):
                head = str((entry.get("source") or {}).get("snapshot_head") or "")
                self.assertRegex(head, r"^[0-9a-f]{7,40}$")

    def test_registry_does_not_import_upstream_code(self):
        """参考是数据不是依赖：本模块 import 链不许碰上游参考包。"""
        source = (ROOT / "backend" / "controller_plugins.py").read_text(encoding="utf-8")
        import ast
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                modules = [a.name for a in node.names] if isinstance(node, ast.Import) \
                    else [node.module or ""]
                for m in modules:
                    self.assertFalse(m.startswith(("dial_mpc", "legged_", "00_resources")),
                                     f"注册表模块不许 import 上游参考：{m}")


class BadDeclarationTest(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._old_root = cp._ROOT
        self._old_path = cp._REGISTRY_PATH
        cp.reset_cache()

    def tearDown(self) -> None:
        cp._ROOT = self._old_root
        cp._REGISTRY_PATH = self._old_path
        cp.reset_cache()
        self._tmp.cleanup()

    def _use(self, controllers: list[dict], vocabulary: dict | None = None) -> None:
        root = _mk_registry(self.root, controllers, vocabulary)
        cp._ROOT = root
        cp._REGISTRY_PATH = root / "registry" / "controllers" / "index.json"

    def test_duplicate_id_fails_loud(self):
        self._use([_valid_entry(), _valid_entry()])
        with self.assertRaises(ValueError) as ctx:
            cp.load_registry()
        self.assertIn("重复", str(ctx.exception))

    def test_unknown_mechanism_class_fails_loud(self):
        self._use([_valid_entry(mechanism_class="magic_mpc")])
        with self.assertRaises(ValueError) as ctx:
            cp.load_registry()
        self.assertIn("mechanism_class", str(ctx.exception))

    def test_dangling_snapshot_path_fails_loud(self):
        self._use([_valid_entry(
            source={"path": "refs/ghost", "snapshot_head": "1234567", "license": "MIT"})])
        with self.assertRaises(ValueError) as ctx:
            cp.load_registry()
        self.assertIn("快照不存在", str(ctx.exception))

    def test_unknown_status_fails_loud(self):
        self._use([_valid_entry(**{"porting": {"status": "done", "mechanism_files": []}})])
        with self.assertRaises(ValueError) as ctx:
            cp.load_registry()
        self.assertIn("porting.status", str(ctx.exception))

    def test_bad_head_fails_loud(self):
        self._use([_valid_entry(
            source={"path": "refs/snapshot-a", "snapshot_head": "not-a-hash",
                    "license": "MIT"})])
        with self.assertRaises(ValueError):
            cp.load_registry()

    def test_unlicensed_unregistered_fails_loud(self):
        self._use([_valid_entry(
            source={"path": "refs/snapshot-a", "snapshot_head": "1234567",
                    "license": None})])
        with self.assertRaises(ValueError) as ctx:
            cp.load_registry()
        self.assertIn("零许可", str(ctx.exception))

    def test_missing_vocabulary_fails_loud(self):
        self._use([_valid_entry()], vocabulary={})
        with self.assertRaises(ValueError) as ctx:
            cp.load_registry()
        self.assertIn("vocabulary", str(ctx.exception))


class PanelProjectionTest(unittest.TestCase):
    def test_cli_provider_resolves_and_serializes(self):
        from backend.cli_panels import resolve_provider

        fn = resolve_provider("backend.cli_panels:controllers_list")
        payload = fn()
        json.dumps(payload, ensure_ascii=False)  # 不可序列化 = provider 违约
        self.assertEqual(payload["count"], len(cp.list_controllers()))

    def test_panel_declared_in_registry(self):
        panels = json.loads(
            (ROOT / "registry" / "panels" / "index.json").read_text(encoding="utf-8-sig"))
        entry = next((p for p in panels["panels"] if p["id"] == "controllers"), None)
        self.assertIsNotNone(entry, "controllers 面板必须一行声明（加面板 = 一行）")
        self.assertEqual(entry["cli"]["provider"], "backend.cli_panels:controllers_list")
        self.assertEqual(entry["home_card"]["provider"], "backend.cli_panels:controllers_list")

    def test_require_controller_fail_loud_with_known_list(self):
        with self.assertRaises(KeyError) as ctx:
            cp.require_controller("no-such-mpc")
        self.assertIn("dial-mpc", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
