"""workspace 副本的**引用文件补齐**：config 指向的文件必须真的在。

背景（真实事故）：`workspace/packages/<robot>` 由 `robot_packages._sync_shipped_packages_into_workspace`
从源树同步，但 C6 的补缺规则只覆盖 `simulation/` 子树 —— 而 policy 的 `path` 可以指向
`deploy/…`（`wuji_hand` 就是 `deploy/reorient-v2026.5.29/policy.onnx`）。于是副本留下
"config 指向一个不存在的 onnx"：**运行时就 404**，`scripts/release-check.js` 的 workspace 段直接红。

所以这里守三件事：**按引用补**、**路径不可信（相对 + 无 ..）**、**源包也没有就不伪造**。
"""

import json
import pathlib
import tempfile
import unittest

from backend import robot_packages as rp


class SyncReferencedBlobsTest(unittest.TestCase):
    def _layout(self, root: pathlib.Path, *, policies, shipped_files) -> tuple[pathlib.Path, pathlib.Path]:
        shipped = root / "assets" / "robots" / "wuji_hand"
        target = root / "workspace" / "packages" / "wuji_hand"
        (shipped / "simulation").mkdir(parents=True)
        (target / "simulation").mkdir(parents=True)
        (target / "simulation" / "config.json").write_text(
            json.dumps({"policies": policies}, ensure_ascii=False), encoding="utf-8",
        )
        for relative, payload in shipped_files.items():
            path = shipped / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        return shipped, target

    def test_referenced_blob_outside_simulation_is_restored(self):
        """`deploy/` 下的策略（不在 simulation/ 子树）也要补上 —— 这正是 wuji_hand 的情形。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            relative = "deploy/reorient-v2026.5.29/policy.onnx"
            shipped, target = self._layout(
                root,
                policies=[{"id": "reorient", "path": relative}],
                shipped_files={relative: b"onnx-blob"},
            )
            self.assertFalse((target / relative).exists(), "前置：副本里确实缺")

            restored = rp.sync_referenced_blobs(shipped, target)

            self.assertEqual([relative], restored)
            self.assertEqual(b"onnx-blob", (target / relative).read_bytes())

    def test_existing_copy_is_left_alone(self):
        """副本已有该文件 → 不动（workspace 是运行时权威，训练导出的策略不能被覆盖）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            relative = "deploy/p/policy.onnx"
            shipped, target = self._layout(
                root,
                policies=[{"path": relative}],
                shipped_files={relative: b"from-source"},
            )
            (target / relative).parent.mkdir(parents=True, exist_ok=True)
            (target / relative).write_bytes(b"from-workspace")

            self.assertEqual([], rp.sync_referenced_blobs(shipped, target))
            self.assertEqual(b"from-workspace", (target / relative).read_bytes())

    def test_absolute_and_parent_traversal_paths_are_refused(self):
        """路径不可信：绝对路径与 `..` 一律不碰（副本可能来自历史/外部）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            outside = root / "outside.onnx"
            outside.write_bytes(b"secret")
            shipped, target = self._layout(
                root,
                policies=[{"path": str(outside)}, {"path": "../../outside.onnx"},
                          {"path": "deploy/../outside.onnx"}],
                shipped_files={},
            )
            self.assertEqual([], rp.sync_referenced_blobs(shipped, target))
            self.assertTrue(outside.exists(), "不得被搬动")

    def test_missing_in_source_is_not_fabricated(self):
        """源包也没有 → **不伪造**，照样缺着（让门禁与运行时如实报出来）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            shipped, target = self._layout(
                root, policies=[{"path": "deploy/ghost/policy.onnx"}], shipped_files={},
            )
            self.assertEqual([], rp.sync_referenced_blobs(shipped, target))
            self.assertFalse((target / "deploy" / "ghost" / "policy.onnx").exists())

    def test_demo_policies_are_covered_too(self):
        """`demo_policies` 与 `policies` 同权（首页演示策略也从这里来）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            shipped = root / "assets" / "robots" / "r"
            target = root / "workspace" / "packages" / "r"
            (shipped / "simulation").mkdir(parents=True)
            (target / "simulation").mkdir(parents=True)
            (target / "simulation" / "config.json").write_text(
                json.dumps({"demo_policies": [{"path": "deploy/demo/policy.onnx"}]}), encoding="utf-8",
            )
            src = shipped / "deploy" / "demo" / "policy.onnx"
            src.parent.mkdir(parents=True, exist_ok=True)
            src.write_bytes(b"demo")
            self.assertEqual(["deploy/demo/policy.onnx"], rp.sync_referenced_blobs(shipped, target))


if __name__ == "__main__":
    unittest.main()
