"""族架构门禁（tools/audit_families.py）的契约测试。

守三件事：
1. 真仓通过，且形状与事实一致（2 个族 / 8 格技能矩阵 / 四类技能齐备）；
2. **反例注入**：成员漏登记、角色顺序漂移、通用技能少一台成员、非通用技能不写 gap、
   游离任务、未登记的族文件 —— 逐条必须判红；
3. 缺口如实留痕：今天的技能覆盖就是"速度跟踪两族全通、越障/模仿/特技只在 go2"，
   这条不会被误当成"全绿"。

夹具是**临时目录里的小族**（真实契约 + 档案的缩微版），不动真仓任何文件。
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import audit_families  # noqa: E402

ROLES = ["hip_abduction", "hip_pitch", "knee"]
ALIASES = {"hip_abduction": ["hip", "hipx"], "hip_pitch": ["thigh", "hipy"], "knee": ["calf"]}
JOINTS = ["hip", "thigh", "calf", "hip", "thigh", "calf", "hip", "thigh", "calf", "hip", "thigh", "calf"]
ACTOR_OBS = [("base_ang_vel", 3), ("projected_gravity", 3), ("commands", 3),
             ("joint_pos", 12), ("joint_vel", 12), ("last_action", 12)]


def _contract(robot_id: str) -> dict:
    return {
        "robot_id": robot_id,
        "morphology": {"id": "quadruped_12dof", "legs": 4, "leg_pattern": ["hip", "thigh", "calf"]},
        "locomotion_type": "P",
        "control": {"control_hz": 50, "physics_hz": 200, "decimation": 4},
        "action": {"joint_order": list(JOINTS)},
        "observation": {
            "components": [{"name": name, "width": width, "role": "actor"} for name, width in ACTOR_OBS],
            "dimension": sum(width for _, width in ACTOR_OBS),
        },
    }


def _skill(skill_id: str, status: str, task_names: list[str], members: list[str]) -> dict:
    skill = {"skill_id": skill_id, "status": status, "task_names": task_names}
    if status == "generic":
        skill["summary"] = "族级通用"
    else:
        skill["members_with_recipe"] = members
        skill["gap"] = "缺口留痕"
    return skill


def _family() -> dict:
    return {
        "schema_version": "family-1.0",
        "family_id": "quadruped",
        "morphology_ids": ["quadruped_12dof"],
        "locomotion_type": "P",
        "legs": 4,
        "joint_roles": list(ROLES),
        "role_aliases": copy.deepcopy(ALIASES),
        "control_hz": 50,
        "observation_skeleton": {
            "note": "夹具骨架",
            "actor": [name for name, _ in ACTOR_OBS],
            "critic_only": ["base_lin_vel"],
            "width_source": {"joint_pos": "12"},
            "deviations": {},
        },
        "members": ["r1", "r2"],
        "skills": [
            _skill("velocity", "generic", ["velocity"], []),
            _skill("traversal", "robot-specific", ["parkour"], ["r1"]),
            _skill("imitation", "robot-specific", ["amp"], ["r1"]),
            _skill("stunt", "robot-specific", ["jump"], ["r1"]),
        ],
    }


def _write_profile(robots_dir: Path, robot_id: str, profile_id: str, task_name: str) -> None:
    path = robots_dir / robot_id / "training" / "profiles" / f"{profile_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"profile_id": profile_id, "task_name": task_name}, ensure_ascii=False), encoding="utf-8")


class FamilyAuditTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.families = root / "families"
        self.robots = root / "robots"
        (self.families).mkdir(parents=True)
        for robot_id in ("r1", "r2"):
            path = self.robots / robot_id / "contract.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(_contract(robot_id), ensure_ascii=False), encoding="utf-8")
        _write_profile(self.robots, "r1", "p-velocity", "velocity")
        _write_profile(self.robots, "r1", "p-parkour", "parkour")
        _write_profile(self.robots, "r1", "p-amp", "amp")
        _write_profile(self.robots, "r1", "p-jump", "jump")
        _write_profile(self.robots, "r2", "p-velocity", "velocity")
        self.write_family(_family())
        self.write_index(["quadruped.json"])

    def tearDown(self):
        self._tmp.cleanup()

    def write_family(self, family: dict) -> None:
        (self.families / "quadruped.json").write_text(json.dumps(family, ensure_ascii=False, indent=2), encoding="utf-8")

    def write_index(self, paths: list[str]) -> None:
        (self.families / "index.json").write_text(
            json.dumps({"schema": "family-index-1.0", "families": [
                {"family_id": Path(p).stem, "path": p} for p in paths]}, ensure_ascii=False, indent=2), encoding="utf-8")

    def audit(self) -> dict:
        return audit_families.audit(families_dir=self.families, robots_dir=self.robots)

    def assertCaught(self, needle: str) -> None:  # noqa: N802
        report = self.audit()
        self.assertFalse(report["ok"], report["problems"])
        self.assertTrue(any(needle in item for item in report["problems"]), report["problems"])

    def test_fixture_passes(self):
        report = self.audit()
        self.assertTrue(report["ok"], report["problems"])
        self.assertEqual(2, sum(1 for _ in self.robots.iterdir()))

    def test_member_declared_without_contract_is_caught(self):
        family = _family()
        family["members"].append("ghost")
        self.write_family(family)
        self.assertCaught("ghost")

    def test_role_order_drift_is_caught(self):
        family = _family()
        family["joint_roles"] = ["hip_pitch", "hip_abduction", "knee"]
        self.write_family(family)
        self.assertCaught("与族角色顺序")

    def test_control_rate_drift_is_caught(self):
        family = _family()
        family["control_hz"] = 200
        self.write_family(family)
        self.assertCaught("control_hz")

    def test_generic_skill_losing_a_member_is_caught(self):
        (self.robots / "r2" / "training" / "profiles" / "p-velocity.json").unlink()
        self.assertCaught("没有对应档案")

    def test_orphan_task_is_caught(self):
        _write_profile(self.robots, "r2", "p-mystery", "brand_new")
        self.assertCaught("游离任务")

    def test_non_generic_skill_without_gap_is_caught(self):
        family = _family()
        next(s for s in family["skills"] if s["skill_id"] == "stunt").pop("gap")
        self.write_family(family)
        self.assertCaught("gap")

    def test_non_generic_skill_claiming_unused_task_is_caught(self):
        family = _family()
        next(s for s in family["skills"] if s["skill_id"] == "stunt")["task_names"].append("brand_new")
        self.write_family(family)
        self.assertCaught("没有任何档案在用")

    def test_unregistered_family_file_is_caught(self):
        (self.families / "humanoid.json").write_text(json.dumps(_family()), encoding="utf-8")
        self.assertCaught("未在 index.json 登记")

    def test_missing_observation_skeleton_is_caught(self):
        family = _family()
        family.pop("observation_skeleton")
        self.write_family(family)
        self.assertCaught("缺 observation_skeleton")

    def test_observation_deviation_must_be_declared(self):
        contract = _contract("r2")
        contract["observation"]["components"] = [
            {"name": "base_lin_vel", "width": 3, "role": "actor"},
            *contract["observation"]["components"],
        ]
        contract["observation"]["dimension"] += 3
        path = self.robots / "r2" / "contract.json"
        path.write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")
        self.assertCaught("未登记偏差")

    def test_stale_observation_deviation_is_caught(self):
        family = _family()
        family["observation_skeleton"]["deviations"] = {"r1": "其实已经一致了"}
        self.write_family(family)
        self.assertCaught("偏差登记还在")

    def test_self_contradicting_skeleton_is_caught(self):
        family = _family()
        family["observation_skeleton"]["critic_only"].append("commands")
        self.write_family(family)
        self.assertCaught("自相矛盾")

    def test_registered_but_missing_family_file_is_caught(self):
        self.write_index(["quadruped.json", "humanoid.json"])
        self.assertCaught("但文件不存在")


class RealRepoFamilyTest(unittest.TestCase):
    """真仓：族声明与事实一致，且缺口不被当成通过。"""

    def test_real_repo_passes(self):
        report = audit_families.audit()
        self.assertTrue(report["ok"], report["problems"])
        self.assertEqual(2, report["families"])
        self.assertEqual(8, len(report["matrix"]))

    def test_four_skill_classes_present_for_both_families(self):
        for entry in json.loads((ROOT / "registry" / "families" / "index.json").read_text(encoding="utf-8"))["families"]:
            family = json.loads((ROOT / "registry" / "families" / entry["path"]).read_text(encoding="utf-8"))
            ids = {skill["skill_id"] for skill in family["skills"]}
            self.assertEqual(set(audit_families.REQUIRED_SKILLS), ids, entry["path"])

    def test_velocity_is_the_only_generic_skill_today(self):
        """诚实边界：今天只有速度跟踪两族通用；越障/模仿/特技仍是单机型。"""
        generic = set()
        for entry in json.loads((ROOT / "registry" / "families" / "index.json").read_text(encoding="utf-8"))["families"]:
            family = json.loads((ROOT / "registry" / "families" / entry["path"]).read_text(encoding="utf-8"))
            generic |= {(family["family_id"], skill["skill_id"]) for skill in family["skills"] if skill["status"] == "generic"}
        self.assertEqual({("quadruped", "velocity"), ("wheel_leg", "velocity")}, generic)

    def test_observation_deviations_are_exactly_go1_and_zexw_today(self):
        """诚实边界：族内观测骨架今天有两处**已登记**偏差，且不再多也不再少。

        go1 多 base_lin_vel(48 维)、zex-w 轮速单列(53 维)；两者都属"改宽会动到存量策略"
        的迁移，须单独裁决 —— 这条断言保证它们不会被静默统一，也不会被静默扩大。
        """
        declared = {}
        for entry in json.loads((ROOT / "registry" / "families" / "index.json").read_text(encoding="utf-8"))["families"]:
            family = json.loads((ROOT / "registry" / "families" / entry["path"]).read_text(encoding="utf-8"))
            declared[family["family_id"]] = sorted((family.get("observation_skeleton") or {}).get("deviations") or {})
        self.assertEqual({"quadruped": ["unitree_go1"], "wheel_leg": ["zex-w"]}, declared)


if __name__ == "__main__":
    unittest.main()
