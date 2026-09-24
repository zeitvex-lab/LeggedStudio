"""v2 契约观测段投影（#21）的回归锁。

守三件事：
1. **真仓一致**：8 个包里的 ``contract_legacy_v2.json`` 观测段 == v3 投影
   （历史缺陷：go2 缺 ``commands`` 多 ``base_lin_vel``、go1 少 ``base_lin_vel``、
   go2w 旧项名、zex-w 缺 ``wheel_vel``——v2 是 create 校验链与预设记录的输入，
   陈旧值会盖着真值出现在训练配置页）；
2. **反例注入**：把某包的 v2 观测段改回去必须判红（门禁不能是摆设）；
3. **合并后不变**：v2 投影回去后，``merge_legacy_over_contract`` 的观测段与 v3 同名
   —— 即"v2 是投影"这条投影关系在合并视图里也无残留分歧。
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import sync_legacy_observation  # noqa: E402
from contracts.contract_loader import (  # noqa: E402
    load_contract,
    load_legacy_contract,
    merge_legacy_over_contract,
    project_observation_to_legacy,
)

ROBOTS_DIR = ROOT / "assets" / "robots"


def _v3(components: list[tuple[str, int]]) -> dict:
    return {"observation": {"components": [{"name": n, "width": w} for n, w in components], "dimension": sum(w for _, w in components)}}


class ProjectionFunctionTest(unittest.TestCase):
    def test_projects_names_and_dimension_in_v3_order(self):
        v3 = _v3([("base_ang_vel", 3), ("commands", 3), ("joint_pos", 12)])
        legacy = {"observation": {"components": ["base_lin_vel", "base_ang_vel"], "dimension": 6}, "robot_id": "x"}
        projected = project_observation_to_legacy(v3, legacy)
        self.assertEqual(["base_ang_vel", "commands", "joint_pos"], projected["observation"]["components"])
        self.assertEqual(18, projected["observation"]["dimension"])
        self.assertEqual("x", projected["robot_id"])

    def test_keeps_legacy_when_v3_has_no_components(self):
        legacy = {"observation": {"components": ["vision"], "dimension": 128}}
        self.assertIs(legacy, project_observation_to_legacy({"observation": {"dimension": 128}}, legacy))

    def test_is_idempotent(self):
        v3 = _v3([("base_ang_vel", 3), ("last_action", 12)])
        legacy = {"observation": {"components": ["old"], "dimension": 1}}
        once = project_observation_to_legacy(v3, legacy)
        twice = project_observation_to_legacy(v3, once)
        self.assertEqual(once, twice)


class RealRepoProjectionTest(unittest.TestCase):
    def test_all_pairs_are_projected(self):
        report = sync_legacy_observation.audit(ROBOTS_DIR)
        self.assertTrue(report["ok"], report["drifted"])
        self.assertEqual(8, report["paired"], report["skipped"])
        self.assertEqual([], report["skipped"])

    def test_merged_observation_agrees_with_v3(self):
        for robot_dir in sorted(p for p in ROBOTS_DIR.iterdir() if p.is_dir()):
            v3 = load_contract(robot_dir)
            v2 = load_legacy_contract(robot_dir)
            if v3 is None or v2 is None:
                continue
            v3_names = [item.get("name") for item in (v3.get("observation") or {}).get("components") or []]
            if not v3_names:
                continue
            merged = merge_legacy_over_contract(v3, v2)
            merged_names = [item.get("name") if isinstance(item, dict) else item
                            for item in (merged.get("observation") or {}).get("components") or []]
            self.assertEqual(v3_names, merged_names, robot_dir.name)


class DriftDetectionTest(unittest.TestCase):
    """反例注入：门禁必须真能红。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.robots = Path(self._tmp.name)
        src = ROBOTS_DIR / "unitree_go2"
        dst = self.robots / "unitree_go2"
        dst.mkdir()
        for name in ("contract.json", "contract_legacy_v2.json"):
            shutil.copy(src / name, dst / name)
        self.legacy_path = dst / "contract_legacy_v2.json"

    def tearDown(self):
        self._tmp.cleanup()

    def _write_legacy(self, components: list[str], dimension: int) -> None:
        data = json.loads(self.legacy_path.read_text(encoding="utf-8"))
        data["observation"] = {"components": components, "dimension": dimension}
        self.legacy_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def test_stale_observation_is_caught(self):
        self._write_legacy(["base_lin_vel", "base_ang_vel"], 6)
        report = sync_legacy_observation.audit(self.robots)
        self.assertFalse(report["ok"])
        self.assertEqual(1, len(report["drifted"]))
        self.assertIn("unitree_go2", report["drifted"][0])

    def test_write_converges_then_check_passes(self):
        self._write_legacy(["base_lin_vel", "base_ang_vel"], 6)
        changed = sync_legacy_observation.write(self.robots)
        self.assertEqual(1, changed)
        self.assertTrue(sync_legacy_observation.audit(self.robots)["ok"])


if __name__ == "__main__":
    unittest.main()
