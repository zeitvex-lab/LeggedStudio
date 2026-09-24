"""族 Kit 委派门禁（`tools/audit_families.py` 的 Kit 委派两条不变量）的回归锁。

为什么单独一个文件：`test_family_contract.py` 覆盖族声明的其余判据；本文件只守"Kit 方向"——
① **成员 → 族 Kit**：每台成员必须引用本族 Kit（否则自带框架副本，"同族复用"只是名义）；
② **族 Kit → 机型包**：Kit 里 import 机型包（`assets.robots` / `local_tasks`）即方向搞反。
两条都是 2026-09-24 手工核对（8/8 引用、零反向依赖）后固化成门禁的，配反例注入。
"""

from __future__ import annotations

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


class KitDelegationGateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.families = root / "families"
        self.robots = root / "robots"
        self.kits = root / "kits"
        (self.families).mkdir(parents=True)
        (self.kits / "quadruped_kit").mkdir(parents=True)
        (self.kits / "quadruped_kit" / "__init__.py").write_text('"""族级框架。"""\n', encoding="utf-8")
        for robot_id in ("r1", "r2"):
            contract = {
                "robot_id": robot_id,
                "morphology": {"id": "quadruped_12dof", "legs": 4, "leg_pattern": ["hip", "thigh", "calf"]},
                "locomotion_type": "P",
                "control": {"control_hz": 50},
                "action": {"joint_order": ["hip", "thigh", "calf"] * 4},
                "observation": {
                    "components": [{"name": "base_ang_vel", "width": 3, "role": "actor"}],
                    "dimension": 3,
                },
            }
            path = self.robots / robot_id / "contract.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")
            stub = self.robots / robot_id / "training" / "source" / f"{robot_id}_velocity" / "env_cfg.py"
            stub.parent.mkdir(parents=True, exist_ok=True)
            stub.write_text("from adapters.mjlab.kits import quadruped_kit as kit  # 薄委托\n", encoding="utf-8")
            profiles = self.robots / robot_id / "training" / "profiles"
            profiles.mkdir(parents=True, exist_ok=True)
            (profiles / "p-velocity.json").write_text(
                json.dumps({"profile_id": "p-velocity", "task_name": "velocity"}, ensure_ascii=False), encoding="utf-8")
        (self.families / "quadruped.json").write_text(json.dumps({
            "schema_version": "family-1.0",
            "family_id": "quadruped",
            "morphology_ids": ["quadruped_12dof"],
            "locomotion_type": "P",
            "legs": 4,
            "joint_roles": ["hip_abduction", "hip_pitch", "knee"],
            "role_aliases": {"hip_abduction": ["hip"], "hip_pitch": ["thigh"], "knee": ["calf"]},
            "control_hz": 50,
            "observation_skeleton": {"actor": ["base_ang_vel"], "critic_only": [], "deviations": {}},
            "members": ["r1", "r2"],
            "skills": [
                {"skill_id": "velocity", "status": "generic", "task_names": ["velocity"]},
                {"skill_id": "traversal", "status": "missing", "task_names": [], "members_with_recipe": [], "gap": "夹具：无"},
                {"skill_id": "imitation", "status": "missing", "task_names": [], "members_with_recipe": [], "gap": "夹具：无"},
                {"skill_id": "stunt", "status": "missing", "task_names": [], "members_with_recipe": [], "gap": "夹具：无"},
            ],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        (self.families / "index.json").write_text(json.dumps(
            {"schema": "family-index-1.0", "families": [{"family_id": "quadruped", "path": "quadruped.json"}]},
            ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def audit(self) -> dict:
        return audit_families.audit(families_dir=self.families, robots_dir=self.robots, kits_dir=self.kits)

    def assertCaught(self, needle: str) -> None:  # noqa: N802
        report = self.audit()
        self.assertFalse(report["ok"], report["problems"])
        self.assertTrue(any(needle in item for item in report["problems"]), report["problems"])

    def test_fixture_passes(self):
        report = self.audit()
        self.assertTrue(report["ok"], report["problems"])

    def test_member_without_kit_reference_is_caught(self):
        stub = self.robots / "r2" / "training" / "source" / "r2_velocity" / "env_cfg.py"
        stub.write_text("# 自带一套框架副本，没接 Kit\n", encoding="utf-8")
        self.assertCaught("找不到对本族 Kit")

    def test_missing_kit_directory_is_caught(self):
        for path in sorted((self.kits / "quadruped_kit").rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        (self.kits / "quadruped_kit").rmdir()
        self.assertCaught("不存在")

    def test_kit_importing_robot_packages_is_caught(self):
        (self.kits / "quadruped_kit" / "sneaky.py").write_text(
            "from assets.robots.unitree_go2.training.source.local_tasks import robot\n", encoding="utf-8")
        self.assertCaught("反向 import")

    def test_kit_mention_in_docstring_is_allowed(self):
        (self.kits / "quadruped_kit" / "sneaky.py").write_text(
            '"""来源：`assets/robots/unitree_go2/training/source/local_tasks/...`（只是出处说明）。"""\n',
            encoding="utf-8")
        report = self.audit()
        self.assertTrue(report["ok"], report["problems"])


class RealRepoKitDelegationTest(unittest.TestCase):
    """真仓：8/8 引用本族 Kit，且 Kit 无反向依赖。"""

    def test_real_repo_passes(self):
        report = audit_families.audit()
        self.assertTrue(report["ok"], report["problems"])

    def test_every_member_uses_its_family_kit(self):
        for entry in json.loads((ROOT / "registry" / "families" / "index.json").read_text(encoding="utf-8"))["families"]:
            family = json.loads((ROOT / "registry" / "families" / entry["path"]).read_text(encoding="utf-8"))
            kit = f"{family['family_id']}_kit"
            for robot_id in family["members"]:
                source_root = ROOT / "assets" / "robots" / robot_id / "training" / "source"
                hits = [p for p in source_root.rglob("*.py")
                        if "__pycache__" not in p.parts and kit in p.read_text(encoding="utf-8", errors="ignore")]
                self.assertTrue(hits, f"{robot_id} 未引用本族 Kit {kit}")


if __name__ == "__main__":
    unittest.main()
