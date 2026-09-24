"""导入侧判族与族观测骨架的回归锁（"一键导入"⇒"同族复用"的前置）。

现状（2026-09-24 实测，`onboard` 预演 fsdog1.xml）：导入器**能**从命名猜出
`morphology.id = quadruped_12dof`，但观测骨架是它自己造的那套——`base_lin_vel` 放进 actor、
没有 `commands`；而族骨架（`registry/families/*.json#observation_skeleton`）是
`base_ang_vel · projected_gravity · commands · joint_pos · joint_vel · last_action`
（`base_lin_vel` 只进 critic）。两者宽度都是 45，**项序却不同** ⇒ 导入的同族新机型从第一天起
就与族内其它机型观测不同构，"同族复用同一套技能"落不了地。

本文件锁三件事：
1. 判族**以族注册表为准**（腿数 / 角色经 `role_aliases` 归一 / 各腿顺序一致 / 形态 id 已登记）；
   判不出就如实说判不出，**不许猜**；
2. 判出族 ⇒ 导入契约的观测段用**族骨架**（宽度随关节数派生）；
3. 判不出族 ⇒ 保留通用骨架，导入照常成功（非族成员不假装是族成员）。
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

from backend.family_readiness import family_observation_components, judge_family  # noqa: E402
from backend.package_import import draft_model_contract  # noqa: E402

QUADRUPED_JOINTS = [
    f"{leg}_{role}_joint"
    for leg in ("fl", "fr", "rl", "rr")
    for role in ("hip", "thigh", "calf")
]
WHEEL_LEG_JOINTS = [
    f"{leg}_{role}_joint"
    for leg in ("fl", "fr", "hl", "hr")
    for role in ("hipx", "hipy", "knee", "wheel")
]


def _draft(joints: list[str]) -> dict:
    inspection = {
        "joints": [{"name": name, "type": "hinge"} for name in joints],
        "actuators": {"targets": list(joints)},
        "root_name": "imported_fixture",
        "inertial": {"total_mass_kg": 12.0},
    }
    return draft_model_contract(Path("robot.xml"), "mjcf", inspection, "0" * 64)


class JudgeFamilyTest(unittest.TestCase):
    def test_quadruped_naming_is_judged_as_quadruped(self):
        verdict = judge_family(QUADRUPED_JOINTS)
        self.assertEqual("quadruped", verdict["family"])
        self.assertEqual("quadruped_12dof", verdict["morphology_id"])
        self.assertEqual(["fl", "fr", "rl", "rr"], verdict["legs"])

    def test_wheel_leg_naming_is_judged_as_wheel_leg(self):
        verdict = judge_family(WHEEL_LEG_JOINTS)
        self.assertEqual("wheel_leg", verdict["family"])
        self.assertEqual("wheel_leg_16dof", verdict["morphology_id"])

    def test_unknown_morphology_is_not_claimed(self):
        """6 条腿 / 关节名认不出角色 ⇒ 不判族（不许硬塞一个族）。"""
        six_legs = [f"{leg}_{role}_joint" for leg in ("l1", "l2", "l3", "r1", "r2", "r3")
                    for role in ("hip", "thigh", "calf")]
        verdict = judge_family(six_legs)
        self.assertIsNone(verdict["family"])
        self.assertTrue(verdict["reason"])

    def test_inconsistent_role_order_across_legs_is_rejected(self):
        joints = [n for n in QUADRUPED_JOINTS if not n.startswith("rr_")]
        joints += ["rr_calf_joint", "rr_hip_joint", "rr_thigh_joint"]
        verdict = judge_family(joints)
        self.assertIsNone(verdict["family"])

    def test_judgement_follows_the_registry_not_hardcoded_names(self):
        """把族注册表换成一族**别处没有**的声明，判定必须随注册表走。"""
        with tempfile.TemporaryDirectory() as tmp:
            families_dir = Path(tmp)
            (families_dir / "index.json").write_text(json.dumps({
                "schema": "family-index-1.0",
                "families": [{"family_id": "biped_demo", "path": "biped_demo.json"}],
            }, ensure_ascii=False), encoding="utf-8")
            (families_dir / "biped_demo.json").write_text(json.dumps({
                "schema_version": "family-1.0",
                "family_id": "biped_demo",
                "legs": 2,
                "joint_roles": ["hip", "knee"],
                "role_aliases": {"hip": ["hip"], "knee": ["knee"]},
                "morphology_ids": ["biped_demo_4dof"],
                "observation_skeleton": {"actor": ["base_ang_vel", "joint_pos"], "critic_only": []},
            }, ensure_ascii=False), encoding="utf-8")
            verdict = judge_family(
                ["l_hip_joint", "l_knee_joint", "r_hip_joint", "r_knee_joint"],
                families_dir=families_dir,
            )
            self.assertEqual("biped_demo", verdict["family"])
            self.assertEqual("biped_demo_4dof", verdict["morphology_id"])
            self.assertEqual(
                ["base_ang_vel", "joint_pos"],
                family_observation_components("biped_demo", families_dir=families_dir),
            )
            # 换成临时注册表后，真实的四足命名不再被判族（证明不是写死的）
            self.assertIsNone(judge_family(QUADRUPED_JOINTS, families_dir=families_dir)["family"])


class DraftObservationSkeletonTest(unittest.TestCase):
    def test_family_member_draft_uses_family_skeleton(self):
        draft = _draft(QUADRUPED_JOINTS)
        self.assertEqual(
            ["base_ang_vel", "projected_gravity", "commands", "joint_pos", "joint_vel", "last_action"],
            draft["observation"]["components"],
        )
        self.assertEqual(45, draft["observation"]["dimension"])

    def test_wheel_leg_member_draft_uses_family_skeleton(self):
        draft = _draft(WHEEL_LEG_JOINTS)
        self.assertEqual(["commands"], [c for c in draft["observation"]["components"] if c == "commands"])
        self.assertEqual(57, draft["observation"]["dimension"])

    def test_non_member_keeps_generic_skeleton_and_still_imports(self):
        draft = _draft([f"joint_{index}" for index in range(12)])
        self.assertEqual(
            ["base_lin_vel", "base_ang_vel", "projected_gravity", "joint_pos", "joint_vel", "last_action"],
            draft["observation"]["components"],
        )
        self.assertEqual(45, draft["observation"]["dimension"])

    def test_family_judgement_is_reported(self):
        self.assertEqual("quadruped", _draft(QUADRUPED_JOINTS)["family_judgement"]["family"])
        self.assertIsNone(_draft([f"joint_{index}" for index in range(12)])["family_judgement"]["family"])


_QUADRUPED_MJCF = """<mujoco model="family_import_fixture">
  <worldbody>
    <body name="base" pos="0 0 0.3">
      <freejoint name="root"/>
      <geom name="base" type="box" size="0.15 0.08 0.05"/>
      {legs}
    </body>
  </worldbody>
  <actuator>
    {actuators}
  </actuator>
</mujoco>
"""


def _quadruped_mjcf() -> str:
    legs, actuators = [], []
    for leg in ("fl", "fr", "rl", "rr"):
        for role in ("hip", "thigh", "calf"):
            legs.append(
                f'<body name="{leg}_{role}"><joint name="{leg}_{role}_joint" axis="0 1 0" '
                f'range="-1 1"/><geom name="{leg}_{role}_geom" type="capsule" '
                f'size="0.02 0.08" pos="0 0 -0.08"/></body>'
            )
            actuators.append(f'<position name="{leg}_{role}_motor" joint="{leg}_{role}_joint" kp="20" kv="1"/>')
    return _QUADRUPED_MJCF.replace("{legs}", "".join(legs)).replace("{actuators}", "".join(actuators))


class ImportedContractArtifactTest(unittest.TestCase):
    """导入**落盘**的契约文件里不许混进非 schema 键；判族结论只进报告。"""

    def test_report_has_judgement_but_artifact_does_not(self):
        import tempfile

        from backend.package_import import onboard_package

        with tempfile.TemporaryDirectory(prefix="family-import-", dir=ROOT / "workspace") as tmp:
            base = Path(tmp)
            source = base / "robot"
            source.mkdir()
            (source / "robot.xml").write_text(_quadruped_mjcf(), encoding="utf-8")
            report = onboard_package(source, write=True, packages_root=base / "packages")
            self.assertTrue(report.get("valid"), report.get("errors"))
            self.assertEqual("quadruped", (report.get("family_judgement") or {}).get("family"))
            package_root = Path(report["package_root"].replace("\\", "/"))
            if not package_root.is_absolute():
                package_root = ROOT / package_root
            v2 = json.loads((package_root / "contract_legacy_v2.json").read_text(encoding="utf-8-sig"))
            self.assertNotIn("family_judgement", v2)
            self.assertEqual(
                ["base_ang_vel", "projected_gravity", "commands", "joint_pos", "joint_vel", "last_action"],
                v2["observation"]["components"],
            )
            self.assertEqual(45, v2["observation"]["dimension"])
            self.assertGreater(v2["urdf"]["total_mass_kg"], 0)
            self.assertEqual("mjcf_compiled", v2["urdf"]["mass_source"])
            v3 = json.loads((package_root / "contract.json").read_text(encoding="utf-8-sig"))
            self.assertEqual("quadruped_12dof", v3["morphology"]["id"])


if __name__ == "__main__":
    unittest.main()
