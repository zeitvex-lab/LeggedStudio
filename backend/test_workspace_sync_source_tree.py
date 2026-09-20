"""序 13：源树 → workspace 副本的**内容级**同步回归锁。

背景（2026-09-20 go2 去包化实况）：`_package_signature()` 原先只取 `training/profiles`
**目录**的 mtime + 计数，于是
① 目录内文件的**内容编辑**（不改变目录 mtime）不被感知；
② `training/source` 下的**任何**变化（含删除）完全不进签名。
后果链：改/删 `assets/robots/<id>` 的包内训练源码 → 索引不判过期 ⇒ 不触发
`_scan_package_records()` ⇒ 不触发 `_sync_shipped_packages_into_workspace` ⇒
**运行时与所有"改完就跑"的冒烟验的都是旧副本**（当时删了 23 个文件，副本的 182 个 .py
一个都没动，"回归通过"是假的）。

锁死语义：
- 源树**删除** `training/source` 下文件 ⇒ 新进程语义下的下一次读即判过期，并让副本同步删除；
- 源树**内容编辑** ⇒ 副本同步为新内容；
- 源树**新增** ⇒ 副本补齐；
- `__pycache__` 不影响签名稳定性（同步本就不搬它；纳进来会让两侧永远"不一致"、每次读都重扫）。
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from backend import robot_packages


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


CONTRACT = {"robot_id": "acme_bot", "family": "Acme", "joints": {"actuated_joints": []}, "urdf": {"path": "model/robot.xml"}}
MANIFEST = {"schema_version": "robot-package-1.0", "package_id": "acme_bot", "model": {"format": "mjcf", "path": "model/robot.xml"}}


class WorkspaceSyncSourceTreeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="legged-studio-src-sync-")
        root = Path(self._tmp.name)
        self.assets_root = root / "assets" / "robots"
        self.workspace_root = root / "workspace"
        shipped = self.assets_root / "acme_bot"
        (shipped / "model").mkdir(parents=True)
        (shipped / "training" / "profiles").mkdir(parents=True)
        (shipped / "training" / "source" / "pkg").mkdir(parents=True)
        (shipped / "model" / "robot.xml").write_text('<mujoco model="acme"/>', encoding="utf-8")
        (shipped / "training" / "profiles" / "flat.json").write_text("{}", encoding="utf-8")
        self._write(shipped / "training" / "source" / "pkg" / "keep.py", "VALUE = 1\n")
        self._write(shipped / "training" / "source" / "pkg" / "drop.py", "VALUE = 2\n")
        _write_json(shipped / "contract_legacy_v2.json", CONTRACT)
        _write_json(shipped / "robot_package.json", MANIFEST)

        # workspace 副本：起初与源树一致，外加一个源树没有的 ghost.py（历史残留）
        target = self.workspace_root / "packages" / "acme_bot"
        (target / "model").mkdir(parents=True)
        (target / "model" / "robot.xml").write_text('<mujoco model="acme"/>', encoding="utf-8")
        (target / "training" / "profiles").mkdir(parents=True)
        (target / "training" / "profiles" / "flat.json").write_text("{}", encoding="utf-8")
        (target / "training" / "source" / "pkg").mkdir(parents=True)
        self._write(target / "training" / "source" / "pkg" / "keep.py", "VALUE = 1\n")
        self._write(target / "training" / "source" / "pkg" / "drop.py", "VALUE = 2\n")
        self._write(target / "training" / "source" / "pkg" / "ghost.py", "VALUE = 99\n")
        _write_json(target / "contract_legacy_v2.json", CONTRACT)
        _write_json(target / "robot_package.json", MANIFEST)

        self._shipped = shipped
        self._target = target
        self._previous_root = robot_packages.ROOT
        self._previous_env = os.environ.get("LEGGED_STUDIO_WORKSPACE")
        robot_packages.ROOT = root
        os.environ["LEGGED_STUDIO_WORKSPACE"] = str(self.workspace_root)
        robot_packages.invalidate_package_cache()
        self.addCleanup(self._cleanup)

    def _cleanup(self) -> None:
        robot_packages.ROOT = self._previous_root
        if self._previous_env is None:
            os.environ.pop("LEGGED_STUDIO_WORKSPACE", None)
        else:
            os.environ["LEGGED_STUDIO_WORKSPACE"] = self._previous_env
        robot_packages.invalidate_package_cache()
        self._tmp.cleanup()

    @staticmethod
    def _write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _shipped_source(self) -> Path:
        return self._shipped / "training" / "source" / "pkg"

    def _copy_source(self) -> Path:
        return self._target / "training" / "source" / "pkg"

    def test_stale_copy_file_absent_from_source_is_pruned(self):
        """源树没有、副本有的文件（历史残留）必须被清除——副本与源树内容集合一致。"""
        robot_packages.list_robot_packages()
        self.assertFalse((self._copy_source() / "ghost.py").exists(), "首轮同步未清除源树没有的副本文件")

    def test_shipped_source_deletion_reaches_copy(self):
        """**核心回归**：源树删 `training/source` 文件 → 新进程语义下一次读就同步删除。

        修前：签名不覆盖 source ⇒ 不判过期 ⇒ 副本留着旧文件 ⇒ 冒烟验的是旧副本（假绿）。
        """
        robot_packages.list_robot_packages()
        (self._shipped_source() / "drop.py").unlink()
        robot_packages.invalidate_package_cache()  # 等价"重启后端 / 新进程"

        self.assertTrue(
            robot_packages._index_is_stale(),
            "源树删了 training/source 下的文件，签名却没判过期（序 13 盲区复发）",
        )
        robot_packages.list_robot_packages()
        self.assertFalse(
            (self._copy_source() / "drop.py").exists(),
            "源树已删的文件仍留在 workspace 副本 —— 运行时/冒烟验的会是旧副本",
        )

    def test_shipped_source_content_edit_is_mirrored(self):
        """源树内容编辑（目录 mtime 不变）也必须被感知并镜像。"""
        robot_packages.list_robot_packages()
        self._write(self._shipped_source() / "keep.py", "VALUE = 42\n")
        robot_packages.invalidate_package_cache()
        self.assertTrue(robot_packages._index_is_stale(), "源树内容编辑未触发重扫")
        robot_packages.list_robot_packages()
        self.assertEqual(
            (self._copy_source() / "keep.py").read_text(encoding="utf-8"),
            "VALUE = 42\n",
            "源树内容编辑未镜像到副本",
        )

    def test_shipped_source_addition_is_copied(self):
        robot_packages.list_robot_packages()
        self._write(self._shipped_source() / "fresh.py", "VALUE = 7\n")
        robot_packages.invalidate_package_cache()
        robot_packages.list_robot_packages()
        self.assertTrue((self._copy_source() / "fresh.py").is_file(), "源树新增文件未同步到副本")

    def test_pycache_does_not_destabilize_signature(self):
        """`__pycache__` 不参与签名：否则两侧永远"不一致"，每次读都重扫。"""
        robot_packages.list_robot_packages()
        for base in (self._shipped_source(), self._copy_source()):
            cache = base / "__pycache__"
            cache.mkdir(parents=True, exist_ok=True)
            (cache / "keep.cpython-312.pyc").write_bytes(b"\x00\x01")
        robot_packages.invalidate_package_cache()
        self.assertFalse(
            robot_packages._index_is_stale(),
            "__pycache__ 让签名永不稳定 → 每次读都重扫",
        )


if __name__ == "__main__":
    unittest.main()
