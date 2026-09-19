"""B36：v2 contract_legacy_v2.json 契约镜像同步的回归锁。

背景（系统性缺陷，wuji_hand 现场实证）：`_sync_shipped_packages_into_workspace`
的镜像集原本只有 contract.json（D7）、training/profiles、training/source、
simulation/ 补缺、training/config.json（B13）——**从不同步 v2 contract_legacy_v2.json**。
运行时预设链（create 校验等）对已有 workspace 副本的包以**副本**为权威，
assets 侧对 v2 的修复（如 B29 wuji_hand observation.dimension 0→69）对存量
安装不生效，被旧副本静默遮蔽（wuji_hand：修复后首次 create 仍 400，手动用
源树覆盖副本 + 重启后才 200）。

契约副本不得独立演化出第二套真值——v2 与 v3 同为随包分发的派生/契约文件，
且 v2 是 create 校验链的执行输入，副本漂移会静默遮蔽上游修复。

锁死语义（照 D7 同一先例）：
- 副本为陈旧契约（如旧 hash / 旧 observation.dimension）→ 全量覆盖为源树，
  索引记录的 contract 不再携带陈旧字段；
- 副本整文件缺失（残缺副本，robot_package.json 仍在）→ 按缺补齐、顺势治愈，
  治愈后重新成为 workspace 权威副本；
- 内容一致 → 不重写（mtime 不变）；
- 非**包副本**的残留目录（无 robot_package.json）不制造假副本；
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


# 源树真值：B29 修复后的 v2 契约（wuji_hand 同型：observation.dimension 69）
SOURCE_CONTRACT = {
    "robot_id": "acme_bot",
    "family": "Acme",
    "contract_id": "acme-bot-v2",
    "observation": {"dimension": 69, "components": [{"kind": "proprio", "dim": 69}]},
    "joints": {"actuated_joints": ["hip", "knee"]},
    "urdf": {"path": "model/robot.xml", "hash": "b36fresh0"},
}

# 陈旧 workspace 副本：B29 前的旧契约（dimension 0、旧 urdf hash）
STALE_CONTRACT = {
    **SOURCE_CONTRACT,
    "observation": {"dimension": 0, "components": [{"kind": "proprio", "dim": 0}]},
    "urdf": {"path": "model/robot.xml", "hash": "stale-00000"},
}

SOURCE_CONTRACT_V3 = {
    "schema_version": "robot-contract-3.0",
    "robot_id": "acme_bot",
    "morphology": {"form": "biped", "actuator_type": "electric"},
}

POINTER_CONFIG = {
    "robot_id": "acme_bot",
    "contract_path": "assets/robots/acme_bot/contract_legacy_v2.json",
    "profile_id": "acme-flat",
}


class WorkspaceSyncB36ContractMirrorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="legged-studio-b36-sync-")
        root = Path(self._tmp.name)
        self.assets_root = root / "assets" / "robots"
        self.workspace_root = root / "workspace"
        shipped = self.assets_root / "acme_bot"
        (shipped / "model").mkdir(parents=True)
        (shipped / "training" / "profiles").mkdir(parents=True)
        (shipped / "model" / "robot.xml").write_text('<mujoco model="acme"/>', encoding="utf-8")
        (shipped / "training" / "profiles" / "flat.json").write_text("{}", encoding="utf-8")
        _write_json(shipped / "training" / "config.json", POINTER_CONFIG)
        _write_json(shipped / "contract_legacy_v2.json", SOURCE_CONTRACT)
        _write_json(shipped / "contract.json", SOURCE_CONTRACT_V3)
        _write_json(shipped / "robot_package.json", {"schema_version": "robot-package-1.0", "package_id": "acme_bot", "model": {"format": "mjcf", "path": "model/robot.xml"}})

        # workspace 副本：contract_legacy_v2.json 是 B29 前的陈旧契约（漂移副本）
        target = self.workspace_root / "packages" / "acme_bot"
        (target / "model").mkdir(parents=True)
        (target / "model" / "robot.xml").write_text('<mujoco model="acme"/>', encoding="utf-8")
        _write_json(target / "contract_legacy_v2.json", STALE_CONTRACT)
        _write_json(target / "contract.json", SOURCE_CONTRACT_V3)
        _write_json(target / "robot_package.json", _read_json(shipped / "robot_package.json"))
        _write_json(target / "training" / "config.json", POINTER_CONFIG)

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

    def _workspace_contract(self) -> Path:
        return self._target / "contract_legacy_v2.json"

    def _acme_record(self) -> dict:
        records = robot_packages.list_robot_packages()
        return next(item for item in records if item["robot_id"] == "acme_bot")

    def test_stale_contract_copy_is_mirrored_to_source(self):
        robot_packages.rebuild_package_index()
        self.assertEqual(
            _read_json(self._workspace_contract()),
            SOURCE_CONTRACT,
            "陈旧契约副本未被源树覆盖（B36 镜像语义失效，v2 修复仍被副本遮蔽）",
        )
        record = self._acme_record()
        self.assertEqual(
            record["contract"]["observation"]["dimension"],
            SOURCE_CONTRACT["observation"]["dimension"],
            "索引记录的 contract 仍携带陈旧 observation.dimension（预设链会沿用旧副本 400）",
        )
        self.assertNotEqual(record["contract"]["urdf"]["hash"], STALE_CONTRACT["urdf"]["hash"])

    def test_whole_missing_contract_file_is_backfilled_and_copy_healed(self):
        self._workspace_contract().unlink()
        robot_packages.rebuild_package_index()
        self.assertEqual(_read_json(self._workspace_contract()), SOURCE_CONTRACT, "整文件缺失未按源树补齐")
        record = self._acme_record()
        self.assertEqual(record["source"], "workspace", "治愈后的副本未重新成为 workspace 权威（残缺副本永难自愈）")
        self.assertEqual(record["contract"]["observation"]["dimension"], SOURCE_CONTRACT["observation"]["dimension"])

    def test_identical_copy_is_left_untouched(self):
        robot_packages.rebuild_package_index()  # 第一轮同步已镜像
        mtime_first = self._workspace_contract().stat().st_mtime_ns
        robot_packages.rebuild_package_index()  # 第二轮：内容一致不应重写
        self.assertEqual(
            self._workspace_contract().stat().st_mtime_ns,
            mtime_first,
            "内容一致的契约副本被无谓重写（应为内容级比较跳过，D7 同一先例）",
        )

    def test_non_copy_dir_without_descriptor_is_not_fabricated(self):
        # 守住 B36 放宽后的判据边界：纯残留目录（无 robot_package.json）不制造假副本
        self._workspace_contract().unlink()
        (self._target / "robot_package.json").unlink()
        robot_packages.rebuild_package_index()
        self.assertFalse(
            self._workspace_contract().exists(),
            "非包副本的残留目录被伪造了 contract_legacy_v2.json（不应制造假副本）",
        )
        record = self._acme_record()
        self.assertEqual(record["source"], "bundled", "无副本时应回落源树（bundled）而非残缺目录")
        self.assertEqual(
            record["contract"]["observation"]["dimension"],
            SOURCE_CONTRACT["observation"]["dimension"],
            "回落源树时记录的契约应来自源树真值",
        )

    def test_sync_revision_bump_forces_resync_on_existing_installs(self):
        robot_packages.list_robot_packages()
        robot_packages.invalidate_package_cache()
        self.assertFalse(robot_packages._index_is_stale(), "刚重建的索引不应判为过期")
        meta_path = robot_packages._index_meta_path()
        old_meta = _read_json(meta_path)
        old_meta["signature"] = old_meta["signature"].replace(
            f"sync_rev:{robot_packages.SYNC_REVISION}", "sync_rev:4", 1,
        )
        _write_json(meta_path, old_meta)
        self.assertTrue(robot_packages._index_is_stale(), "sync_rev 变更未触发既有安装重建")


if __name__ == "__main__":
    unittest.main()
