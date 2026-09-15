"""C6：workspace 副本基础文件回落（demo_cards 静默跳过机型）回归锁。

背景：`_sync_shipped_packages_into_workspace` 原本只同步 training/ 子树，
workspace 副本缺源树后来新增的基础文件（simulation/scene.xml、策略 onnx）
或缺 simulation/config.json 里新增的声明段（policies/demo_policies）时，
demo_cards 因 config 缺声明而静默跳过该机型——lite3 演示策略从首页消失。

锁死语义（用户裁决：行为变更必须锁死变更集合）：
- simulation/ 下缺失文件按缺补齐，workspace 独有文件（训练导出策略）不清理；
- simulation/config.json 增量合并：副本已有键一律不动（用户编辑权威），
  源树新增键并入——变更集合恰为 set(source) - set(copy)；
- sync_rev 版本号让既有安装（磁盘未变）强制重跑一次同步。
"""

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

from backend import robot_packages
from backend.health_api import demo_cards


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


SOURCE_CONFIG = {
    "schema_version": "simulation-config-1.0",
    "backend": "mujoco",
    "scene_path": "simulation/scene.xml",
    "initial_base_height": 0.3,
    "actuator_interface": "position_target",
    "physics_hz": 200,
    "control_hz": 50,
    "decimation": 4,
    "stiffness": {"hip": 30.0, "knee": 30.0},
    "damping": {"hip": 1.0, "knee": 1.0},
    "torque_limits": {"hip": 24.0, "knee": 36.0},
    "policies": [
        {"id": "walk", "label": "Walk", "path": "simulation/policies/walk.onnx",
         "obs_dim": 42, "action_dim": 12, "contract": {"observation_kind": "proprio", "obs_dim": 42, "action_dim": 12}},
    ],
    "demo_policies": [
        {"id": "demo-walk", "label": "Demo Walk", "path": "simulation/policies/walk.onnx"},
    ],
}

# workspace 陈旧副本：只有老布局的物理键（且用户改过 knee 增益），无任何声明段
AGED_CONFIG_KEYS = ("control_hz", "physics_hz", "decimation", "stiffness", "damping")


class WorkspaceSyncC6Tests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="legged-studio-c6-")
        root = Path(self._tmp.name)
        self.assets_root = root / "assets" / "robots"
        self.workspace_root = root / "workspace"
        shipped = self.assets_root / "acme_bot"
        (shipped / "model").mkdir(parents=True)
        (shipped / "simulation" / "policies").mkdir(parents=True)
        (shipped / "training" / "profiles").mkdir(parents=True)
        (shipped / "model" / "robot.xml").write_text('<mujoco model="acme"/>', encoding="utf-8")
        (shipped / "simulation" / "scene.xml").write_text("<mujoco/>", encoding="utf-8")
        (shipped / "simulation" / "policies" / "walk.onnx").write_bytes(b"\x08\x01onnx-walk")
        (shipped / "training" / "profiles" / "flat.json").write_text("{}", encoding="utf-8")
        _write_json(shipped / "contract.json", {"robot_id": "acme_bot", "family": "Acme", "joints": {"actuated_joints": []}, "urdf": {"path": "model/robot.xml"}})
        _write_json(shipped / "robot_package.json", {"schema_version": "robot-package-1.0", "package_id": "acme_bot", "model": {"format": "mjcf", "path": "model/robot.xml"}})
        _write_json(shipped / "simulation" / "config.json", SOURCE_CONFIG)

        # 陈旧 workspace 副本：缺 config 声明段、缺 scene.xml、缺策略 onnx
        target = self.workspace_root / "packages" / "acme_bot"
        (target / "model").mkdir(parents=True)
        (target / "simulation" / "policies").mkdir(parents=True)
        (target / "model" / "robot.xml").write_text('<mujoco model="acme"/>', encoding="utf-8")
        (target / "simulation" / "policies" / "user_export.onnx").write_bytes(b"\x08\x01user")  # workspace 独有
        aged = {key: json.loads(json.dumps(SOURCE_CONFIG[key])) for key in AGED_CONFIG_KEYS}
        aged["physics_hz"] = 1000  # 陈旧值：与源树不同，必须保留（用户编辑权威）
        aged["stiffness"]["knee"] = 37.5  # 用户工作台编辑
        self._aged_config = aged
        _write_json(target / "simulation" / "config.json", aged)
        _write_json(target / "contract.json", _read_json(shipped / "contract.json"))
        _write_json(target / "robot_package.json", _read_json(shipped / "robot_package.json"))

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

    def _config_path(self) -> Path:
        return self.workspace_root / "packages" / "acme_bot" / "simulation" / "config.json"

    def test_missing_keys_merged_without_clobbering_user_edits(self):
        records = robot_packages.list_robot_packages()
        record = next(item for item in records if item["robot_id"] == "acme_bot")
        merged = _read_json(self._config_path())
        expected_added = {key: SOURCE_CONFIG[key] for key in SOURCE_CONFIG if key not in self._aged_config}
        # 变更集合恰为 set(source) - set(copy)，其余键与用户编辑后的副本逐值相等
        self.assertEqual(
            merged,
            {**self._aged_config, **expected_added},
            "config.json 合并结果偏离锁死集合：已有键被改动或新增键超出预期",
        )
        self.assertEqual(merged["stiffness"]["knee"], 37.5, "用户增益编辑被同步覆盖")
        self.assertEqual(merged["physics_hz"], 1000, "副本已有物理键被源树覆盖")
        # 记录里的 simulation_config 面向 demo_cards / 浏览器仿真，策略可达
        self.assertEqual(record["simulation_config"]["policies"], SOURCE_CONFIG["policies"])
        self.assertEqual(record["source"], "workspace")

    def test_missing_base_files_backfilled_and_workspace_only_files_kept(self):
        robot_packages.rebuild_package_index()
        target = self.workspace_root / "packages" / "acme_bot"
        self.assertTrue((target / "simulation" / "scene.xml").exists(), "缺失 scene.xml 未补齐")
        self.assertEqual(
            (target / "simulation" / "scene.xml").read_bytes(),
            (self.assets_root / "acme_bot" / "simulation" / "scene.xml").read_bytes(),
        )
        self.assertTrue((target / "simulation" / "policies" / "walk.onnx").exists(), "缺失策略 onnx 未补齐")
        self.assertEqual(
            (target / "simulation" / "policies" / "walk.onnx").read_bytes(), b"\x08\x01onnx-walk"
        )
        self.assertTrue(
            (target / "simulation" / "policies" / "user_export.onnx").exists(),
            "workspace 独有文件被同步误删",
        )

    def test_demo_cards_reach_merged_policies(self):
        cards = asyncio.run(demo_cards())["cards"]
        acme_cards = [item for item in cards if item["robot_id"] == "acme_bot"]
        self.assertEqual(
            {item["id"] for item in acme_cards}, {"walk", "demo-walk"},
            "demo_cards 未覆盖 workspace 副本合并后的策略声明",
        )
        for item in acme_cards:
            self.assertEqual(item["play_url"], f"/web/sim2sim/index.html?robot=acme_bot&policy={item['id']}")

    def test_whole_missing_config_file_is_copied_from_source(self):
        self._config_path().unlink()
        robot_packages.rebuild_package_index()
        self.assertEqual(_read_json(self._config_path()), SOURCE_CONFIG, "整文件缺失未按源树补齐")

    def test_sync_revision_bump_forces_rebuild_on_existing_installs(self):
        # list_robot_packages 在首次构建时写入 index + meta（含 sync_rev 标记）
        robot_packages.list_robot_packages()
        robot_packages.invalidate_package_cache()
        self.assertFalse(robot_packages._index_is_stale(), "刚重建的索引不应判为过期")
        # 模拟旧版本安装的 meta（无 sync_rev 标记）：必须判过期并触发重同步
        meta_path = robot_packages._index_meta_path()
        old_meta = _read_json(meta_path)
        old_meta["signature"] = old_meta["signature"].replace(
            f"sync_rev:{robot_packages.SYNC_REVISION}", "sync_rev:0", 1,
        )
        _write_json(meta_path, old_meta)
        self.assertTrue(robot_packages._index_is_stale(), "sync_rev 变更未触发既有安装重建")


if __name__ == "__main__":
    unittest.main()
