"""B13：training/config.json 指针文件镜像同步的回归锁。

背景：B13 收口后各内置包 `training/config.json` 只剩指针字段
（robot_id/contract_path/profile_id/schema_version/backend，尺子 =
tools/audit_training_config_layers.py）。它是随包分发的派生物而非用户
编辑面，workspace 副本必须**镜像**源树——否则旧安装副本会永远保留已
删除的 terrain/reward_scales 等陈旧任务字段，演化出第二套真值
（D7 contract_v3.json 镜像的同一先例）。

锁死语义：
- 副本含残留键（陈旧任务字段）→ 全量覆盖为源树指针文件，不是增量合并；
- 副本整文件缺失 → 按缺补齐；
- SYNC_REVISION bump 让既有安装（磁盘未变）强制重跑一次同步。
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


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


POINTER_CONFIG = {
    "robot_id": "acme_bot",
    "contract_path": "assets/robots/acme_bot/contract.json",
    "profile_id": "acme-flat",
}

# 陈旧 workspace 副本：B13 前的旧布局，带已删除的任务字段
STALE_CONFIG = {
    **POINTER_CONFIG,
    "terrain": {"terrain_type": "plane", "measure_heights": True},
    "reward_scales": {"track_linear_velocity": 1.0, "action_rate_l2": -0.05},
}


class WorkspaceSyncB13PointerConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="legged-studio-b13-sync-")
        root = Path(self._tmp.name)
        self.assets_root = root / "assets" / "robots"
        self.workspace_root = root / "workspace"
        shipped = self.assets_root / "acme_bot"
        (shipped / "model").mkdir(parents=True)
        (shipped / "training" / "profiles").mkdir(parents=True)
        (shipped / "model" / "robot.xml").write_text('<mujoco model="acme"/>', encoding="utf-8")
        (shipped / "training" / "profiles" / "flat.json").write_text("{}", encoding="utf-8")
        _write_json(shipped / "training" / "config.json", POINTER_CONFIG)
        _write_json(shipped / "contract.json", {"robot_id": "acme_bot", "family": "Acme", "joints": {"actuated_joints": []}, "urdf": {"path": "model/robot.xml"}})
        _write_json(shipped / "robot_package.json", {"schema_version": "robot-package-1.0", "package_id": "acme_bot", "model": {"format": "mjcf", "path": "model/robot.xml"}})

        # 陈旧 workspace 副本：training/config.json 还是 B13 前的旧布局
        target = self.workspace_root / "packages" / "acme_bot"
        (target / "model").mkdir(parents=True)
        (target / "model" / "robot.xml").write_text('<mujoco model="acme"/>', encoding="utf-8")
        _write_json(target / "training" / "config.json", STALE_CONFIG)
        _write_json(target / "contract.json", _read_json(shipped / "contract.json"))
        _write_json(target / "robot_package.json", _read_json(shipped / "robot_package.json"))

        self._root = root
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

    def _workspace_config(self) -> Path:
        return self._target / "training" / "config.json"

    def test_stale_residue_copy_is_mirrored_to_pointer_file(self):
        robot_packages.rebuild_package_index()
        self.assertEqual(
            _read_json(self._workspace_config()),
            POINTER_CONFIG,
            "副本残留的 terrain/reward_scales 未被源树指针文件覆盖（镜像语义失效）",
        )

    def test_whole_missing_config_file_is_copied_from_source(self):
        self._workspace_config().unlink()
        robot_packages.rebuild_package_index()
        self.assertEqual(_read_json(self._workspace_config()), POINTER_CONFIG, "整文件缺失未按源树补齐")

    def test_identical_copy_is_left_untouched(self):
        robot_packages.rebuild_package_index()  # 第一轮同步已镜像
        mtime_first = self._workspace_config().stat().st_mtime_ns
        robot_packages.rebuild_package_index()  # 第二轮：内容一致不应重写
        self.assertEqual(
            self._workspace_config().stat().st_mtime_ns,
            mtime_first,
            "内容一致的副本被无谓重写（应为内容级比较跳过）",
        )

    def test_record_training_config_comes_from_pointer_file(self):
        records = robot_packages.list_robot_packages()
        record = next(item for item in records if item["robot_id"] == "acme_bot")
        self.assertEqual(record["training_config"], POINTER_CONFIG, "索引记录仍携带陈旧任务字段")

    def test_sync_revision_bump_forces_resync_on_existing_installs(self):
        robot_packages.list_robot_packages()
        robot_packages.invalidate_package_cache()
        self.assertFalse(robot_packages._index_is_stale(), "刚重建的索引不应判为过期")
        meta_path = robot_packages._index_meta_path()
        old_meta = _read_json(meta_path)
        old_meta["signature"] = old_meta["signature"].replace(
            f"sync_rev:{robot_packages.SYNC_REVISION}", "sync_rev:3", 1,
        )
        _write_json(meta_path, old_meta)
        self.assertTrue(robot_packages._index_is_stale(), "sync_rev 变更未触发既有安装重建")


if __name__ == "__main__":
    unittest.main()
