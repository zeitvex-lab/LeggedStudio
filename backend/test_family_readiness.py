"""族通用就绪（`backend/family_readiness.py`）的回归锁。

守：真仓 8 台全 `ready` 且给出本族可训档；反例注入逐条判红——缺 contract、形态不在族注册表、
缺关节序、默认姿长度不符、MJCF 缺执行器/用 general、缺 PD、质量为 0、观测骨架不一致且未登记。
夹具是临时目录里的迷你包（v3 契约 + robot_package.json + model/robot.xml），不动真仓。
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

from backend.family_readiness import readiness  # noqa: E402

JOINTS = ["FL_hip_joint", "FL_thigh_joint", "FL_calf_joint"]
XML = """<mujoco>
  <worldbody><body name="base_link">
    <joint name="FL_hip_joint"/><joint name="FL_thigh_joint"/><joint name="FL_calf_joint"/>
  </body></worldbody>
  <actuator>
    <position joint="FL_hip_joint" kp="20" kv="0.5"/>
    <position joint="FL_thigh_joint" kp="20" kv="0.5"/>
    <position joint="FL_calf_joint" kp="20" kv="0.5"/>
  </actuator>
</mujoco>
"""


def _contract() -> dict:
    return {
        "schema_version": "robot-contract-3.0",
        "robot_id": "fixture_bot",
        "morphology": {"id": "quadruped_12dof", "legs": 4, "leg_pattern": ["hip", "thigh", "calf"]},
        "joints": {
            "actuated": [{"name": n, "leg": "FL", "role": n.split("_")[1]} for n in JOINTS],
            "default_pose": [0.1, 0.2, 0.3],
        },
        "actuator_profile": {
            "by_role": {"hip": {"stiffness": 20.0, "damping": 0.5},
                        "thigh": {"stiffness": 20.0, "damping": 0.5},
                        "calf": {"stiffness": 20.0, "damping": 0.5}},
        },
        "action": {"joint_order": list(JOINTS)},
        # 观测项按**族骨架**给全（readiness 逐项比 actor 序列；缺项会被正确判红）
        "observation": {
            "components": [{"name": name, "width": 3, "role": "actor"} for name in
                           ("base_ang_vel", "projected_gravity", "commands",
                            "joint_pos", "joint_vel", "last_action")],
            "dimension": 18,
        },
        "control": {"control_hz": 50},
    }


class ReadinessTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "model").mkdir()
        (self.root / "model" / "robot.xml").write_text(XML, encoding="utf-8")
        (self.root / "robot_package.json").write_text(
            json.dumps({"package_id": "fixture_bot", "model": {"path": "model/robot.xml"}}), encoding="utf-8")
        self.contract = _contract()
        self.write_contract(self.contract)
        (self.root / "contract_legacy_v2.json").write_text(
            json.dumps({"robot_id": "fixture_bot", "urdf": {"total_mass_kg": 12.0}}), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def write_contract(self, contract: dict) -> None:
        (self.root / "contract.json").write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")

    def failures(self) -> list[str]:
        report = readiness(self.root)
        return [c["id"] for c in report["checks"] if c["status"] == "fail"]

    def test_fixture_is_ready(self):
        report = readiness(self.root)
        self.assertEqual("ready", report["verdict"], report["checks"])
        self.assertEqual("quadruped", report["family"])
        self.assertEqual(["plane", "rough", "stairs"], report["trainable_terrain_profiles"])

    def test_missing_contract_is_caught(self):
        (self.root / "contract.json").unlink()
        self.assertIn("contract", self.failures())

    def test_unknown_morphology_is_caught(self):
        contract = _contract()
        contract["morphology"]["id"] = "hexapod_18dof"
        self.write_contract(contract)
        report = readiness(self.root)
        self.assertEqual("not_ready", report["verdict"])
        self.assertTrue(any(c["id"] == "family" and c["status"] == "fail" for c in report["checks"]))
        self.assertEqual([], report["trainable_terrain_profiles"])

    def test_missing_joint_order_is_caught(self):
        contract = _contract()
        contract["action"]["joint_order"] = []
        self.write_contract(contract)
        self.assertIn("joint_order", self.failures())

    def test_pose_length_mismatch_is_caught(self):
        contract = _contract()
        contract["joints"]["default_pose"] = [0.1, 0.2]
        self.write_contract(contract)
        self.assertIn("default_pose", self.failures())

    def test_missing_actuator_is_caught(self):
        (self.root / "model" / "robot.xml").write_text(
            XML.replace('<position joint="FL_calf_joint" kp="20" kv="0.5"/>', ""), encoding="utf-8")
        self.assertIn("actuators", self.failures())

    def test_general_actuator_is_caught(self):
        (self.root / "model" / "robot.xml").write_text(
            XML.replace('<position joint="FL_calf_joint" kp="20" kv="0.5"/>',
                        '<general joint="FL_calf_joint"/>'), encoding="utf-8")
        self.assertIn("actuators", self.failures())

    def test_declared_training_asset_is_the_one_measured(self):
        """量的是**训练资产**（`model.training_path`），不是上游那份 `model.path`。

        go2 包内两份 MJCF：上游 `robot.xml`（几何名 `FL_thigh_geom`、无足端 site）与
        `training.xml`（合族约定）。就绪判定说的是"能不能用族架构训"，量错资产就会
        给出与实际训练资产无关的结论。
        """
        (self.root / "model" / "robot.xml").write_text(
            XML.replace('<position joint="FL_calf_joint" kp="20" kv="0.5"/>', ""), encoding="utf-8")
        (self.root / "model" / "training.xml").write_text(XML, encoding="utf-8")
        (self.root / "robot_package.json").write_text(
            json.dumps({
                "package_id": "fixture_bot",
                "model": {"path": "model/robot.xml", "training_path": "model/training.xml"},
            }),
            encoding="utf-8",
        )
        report = readiness(self.root)
        self.assertEqual("ready", report["verdict"], report["checks"])

    def test_mjcf_without_actuator_section_is_cfg_declared(self):
        """MJCF **完全不带执行器** = 执行器由契约声明（`cfg_declared`），不是缺口。

        go2 的训练资产 `model/training.xml` 就是这个形状（0 个执行器，PD 全在契约里），
        而它冒烟绿、族级装配真跑也通过。判红的应该是"声明了却对不上"
        （缺关节 / `<general>` 这种映射不出命令域的），不是"没声明"。
        """
        (self.root / "model" / "robot.xml").write_text(
            XML.replace("""  <actuator>
    <position joint="FL_hip_joint" kp="20" kv="0.5"/>
    <position joint="FL_thigh_joint" kp="20" kv="0.5"/>
    <position joint="FL_calf_joint" kp="20" kv="0.5"/>
  </actuator>
""", ""),
            encoding="utf-8",
        )
        self.assertNotIn("<actuator>", (self.root / "model" / "robot.xml").read_text(encoding="utf-8"))
        report = readiness(self.root)
        self.assertEqual("ready", report["verdict"], report["checks"])
        actuators = next(c for c in report["checks"] if c["id"] == "actuators")
        self.assertIn("契约", actuators["summary"])

    def test_missing_pd_is_caught(self):
        contract = _contract()
        contract["actuator_profile"] = {}
        self.write_contract(contract)
        self.assertIn("actuator_pd", self.failures())

    def test_zero_mass_is_caught(self):
        (self.root / "contract_legacy_v2.json").write_text(
            json.dumps({"robot_id": "fixture_bot", "urdf": {"total_mass_kg": 0}}), encoding="utf-8")
        self.assertIn("mass", self.failures())

    def test_observation_deviation_is_only_a_warning(self):
        contract = _contract()
        contract["observation"]["components"] = [
            {"name": "base_lin_vel", "width": 3, "role": "actor"},
            *contract["observation"]["components"],
        ]
        self.write_contract(contract)
        report = readiness(self.root)
        statuses = {c["id"]: c["status"] for c in report["checks"]}
        self.assertEqual("fail", statuses["observation_skeleton"])
        self.assertEqual("not_ready", report["verdict"])


class RealRepoReadinessTest(unittest.TestCase):
    def test_all_builtins_are_ready(self):
        results = {}
        for robot_dir in sorted(p for p in (ROOT / "assets" / "robots").iterdir() if p.is_dir()):
            report = readiness(robot_dir)
            results[robot_dir.name] = (report["verdict"], report["family"], len(report["trainable_terrain_profiles"]))
        self.assertEqual(8, len(results))
        for name, (verdict, family, terrains) in results.items():
            self.assertEqual("ready", verdict, f"{name} 未就绪")
            self.assertIn(family, {"quadruped", "wheel_leg"})
            self.assertGreaterEqual(terrains, 3, f"{name} 可训档过少")
        # 轮足比四足多两档（障碍释放 / 竞赛地形）
        self.assertEqual(3, results["unitree_go2"][2])
        self.assertEqual(5, results["unitree_b2w"][2])


if __name__ == "__main__":
    unittest.main()
