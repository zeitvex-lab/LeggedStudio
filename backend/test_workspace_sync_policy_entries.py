"""workspace 副本 config.json 的**策略条目按 id 合并**回归锁。

背景（2026-09-20 实测）：LainLab 7 条策略在 `assets/robots/unitree_go2/simulation/
config.json` 入库全链走通，但运行时端点读 workspace 副本——副本里没有这 7 条，
页面选不到。根因：C6 的"增量合并"只认**顶层键**（`key not in dst`），而 policies
数组键在副本里老早存在 ⇒ 源树往数组里追加的新声明永远进不了副本。

锁死语义（不动 C6 既有口径，只补数组这一层）：
- 源树数组里副本**没有的 id** 追加进副本（只增）；
- 同 id 一律以副本为准（用户编辑权威不变）；
- produced 用户训练产物不在源树里，天然不动；
- 无 id 的条目无法去重（会每次同步重复追加），保守不并入；
- 重复同步幂等（第二次同步不产生重复条目）。
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from backend import robot_packages


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class WorkspaceSyncPolicyEntriesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="legged-studio-policy-merge-")
        root = Path(self._tmp.name)
        self.assets_root = root / "assets" / "robots"
        self.workspace_root = root / "workspace"
        self.shipped = self.assets_root / "acme_bot"
        self.target = self.workspace_root / "packages" / "acme_bot"
        for directory in (self.shipped / "simulation" / "policies", self.target / "simulation"):
            directory.mkdir(parents=True)
        # 包副本标记（同步的判据：target 是包副本）
        for directory in (self.shipped, self.target):
            _write_json(
                directory / "contract_legacy_v2.json",
                {"robot_id": "acme_bot", "family": "Acme", "joints": {"actuated_joints": []},
                 "urdf": {"path": "model/robot.xml"}},
            )
            _write_json(
                directory / "robot_package.json",
                {"schema_version": "robot-package-1.0", "package_id": "acme_bot",
                 "model": {"format": "mjcf", "path": "model/robot.xml"}},
            )

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

    def _rebuild(self) -> dict:
        robot_packages.rebuild_package_index()
        return json.loads(self.target.joinpath("simulation", "config.json").read_text(encoding="utf-8-sig"))

    def test_source_only_policy_ids_are_appended(self):
        """源树有、副本没有的 id 追加进副本——LainLab 7 条的场景。"""
        _write_json(self.shipped / "simulation" / "config.json", {
            "policies": [{"id": "walk"}, {"id": "lainlab-trot", "obs_dim": 47}],
        })
        _write_json(self.target / "simulation" / "config.json", {"policies": [{"id": "walk"}]})

        merged = self._rebuild()

        self.assertEqual([entry["id"] for entry in merged["policies"]], ["walk", "lainlab-trot"])
        self.assertEqual(merged["policies"][1], {"id": "lainlab-trot", "obs_dim": 47})

    def test_same_id_entry_is_not_overwritten(self):
        """同 id 以副本为准（用户编辑权威）——哪怕源树内容更新了。"""
        _write_json(self.shipped / "simulation" / "config.json", {
            "policies": [{"id": "walk", "label": "Source Label", "obs_dim": 42}],
        })
        _write_json(self.target / "simulation" / "config.json", {
            "policies": [{"id": "walk", "label": "Workspace Label", "obs_dim": 42}],
        })

        merged = self._rebuild()

        self.assertEqual(merged["policies"], [{"id": "walk", "label": "Workspace Label", "obs_dim": 42}])

    def test_produced_entries_survive_untouched(self):
        """produced 用户训练产物不在源树里——同步不得动它们（顺序与内容都不变）。"""
        produced = [{"id": f"acme-trained-{n:04d}", "path": f"training/onnx/{n}.onnx"} for n in range(3)]
        _write_json(self.shipped / "simulation" / "config.json", {"policies": [{"id": "walk"}]})
        _write_json(self.target / "simulation" / "config.json", {"policies": produced})

        merged = self._rebuild()

        # produced 三条原样留在原位置；源树的 walk 正常追加（合并语义不回退）
        self.assertEqual(merged["policies"], produced + [{"id": "walk"}])
        self.assertEqual(merged["policies"][:3], produced, "produced 条目被改动或重排")

    def test_demo_policies_are_merged_too(self):
        """demo_policies 与 policies 同权（首页演示策略也从这里来）。"""
        _write_json(self.shipped / "simulation" / "config.json", {
            "demo_policies": [{"id": "demo", "path": "simulation/policies/walk.onnx"}],
        })
        _write_json(self.target / "simulation" / "config.json", {"demo_policies": []})

        merged = self._rebuild()

        self.assertEqual([entry["id"] for entry in merged["demo_policies"]], ["demo"])

    def test_entries_without_id_are_not_merged(self):
        """无 id 的条目无法去重（每次同步都会重复追加）⇒ 保守不并入。"""
        _write_json(self.shipped / "simulation" / "config.json", {
            "policies": [{"path": "simulation/policies/walk.onnx"}],
        })
        _write_json(self.target / "simulation" / "config.json", {"policies": [{"id": "walk"}]})

        merged = self._rebuild()

        self.assertEqual([entry.get("id") for entry in merged["policies"]], ["walk"])

    def test_repeated_sync_is_idempotent(self):
        """重复同步幂等——第二次不得把已并入的条目再追加一遍。"""
        _write_json(self.shipped / "simulation" / "config.json", {
            "policies": [{"id": "walk"}, {"id": "lainlab-trot"}, {"id": "lainlab-jump"}],
        })
        _write_json(self.target / "simulation" / "config.json", {"policies": [{"id": "walk"}]})

        first = self._rebuild()
        second = self._rebuild()

        self.assertEqual(first["policies"], second["policies"])
        self.assertEqual([entry["id"] for entry in second["policies"]],
                         ["walk", "lainlab-trot", "lainlab-jump"])

    def test_non_list_policy_key_is_left_alone(self):
        """policies 键任一侧不是列表（畸形副本）⇒ 不猜，原样保留。"""
        _write_json(self.shipped / "simulation" / "config.json", {"policies": [{"id": "walk"}]})
        _write_json(self.target / "simulation" / "config.json", {"policies": {"walk": {}}})

        merged = self._rebuild()

        self.assertEqual(merged["policies"], {"walk": {}})

    def test_new_top_level_keys_still_merged(self):
        """C6 既有口径不回退：顶层新键照样合并，副本已有键不动。"""
        _write_json(self.shipped / "simulation" / "config.json", {
            "default_map": "warehouse", "policies": [{"id": "walk"}],
        })
        _write_json(self.target / "simulation" / "config.json", {
            "default_map": "keep-me", "policies": [{"id": "walk"}],
        })

        merged = self._rebuild()

        self.assertEqual(merged["default_map"], "keep-me", "副本已有的顶层键被覆盖")


if __name__ == "__main__":
    unittest.main()
