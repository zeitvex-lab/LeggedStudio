import unittest
from pathlib import Path

from adapters.mjlab.generic_task_builder import build_generic_task


def _cartpole_contract(path: Path, joint: str = "slider") -> dict:
    return {
        "contract_id": "generic_fixture",
        "urdf": {"path": str(path)},
        "joints": {"actuated_joints": [joint], "default_pose": [0.0]},
        "action": {"joint_order": [joint], "action_scale": 0.5},
        "observation": {"components": ["joint_pos", "joint_vel", "last_action"]},
        "control": {"decimation": 5, "physics_hz": 100},
    }


class GenericTaskBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import mjlab

        cls.xml = Path(mjlab.__file__).resolve().parent / "tasks" / "cartpole" / "cartpole.xml"
        if not cls.xml.exists():
            raise unittest.SkipTest("MJLab cartpole fixture is unavailable")

    def test_builds_from_contract_and_binds_xml_actuator(self):
        bundle = build_generic_task(
            _cartpole_contract(self.xml),
            {"environment": {"terrain_type": "plane", "num_envs": 3}, "reward_scales": {"joint_torques_l2": -0.01}},
        )
        self.assertTrue(bundle.task_id.startswith("LeggedStudio-Generic-"))
        self.assertEqual(bundle.env_cfg.scene.num_envs, 3)
        self.assertEqual(bundle.env_cfg.actions["joint_pos"].actuator_names, ("slider",))
        self.assertEqual(bundle.diagnostics["xml_actuated_joints"], ["slider"])

    def test_preset_reward_names_map_to_mjlab_terms(self):
        bundle = build_generic_task(
            _cartpole_contract(self.xml),
            {"environment": {"terrain_type": "plane"}, "reward_scales": {"body_orientation_l2": -2.0}},
        )
        self.assertIn("upright", bundle.env_cfg.rewards)
        self.assertEqual(bundle.env_cfg.rewards["upright"].weight, -2.0)
        self.assertNotIn("body_orientation_l2", bundle.diagnostics["skipped_rewards"])

    def test_command_cfg_mirrors_mjlab_velocity_defaults(self):
        contract = _cartpole_contract(self.xml)
        contract["observation"]["components"].append("command")
        bundle = build_generic_task(
            contract,
            {"environment": {"terrain_type": "plane", "command_ranges": {"vx": (-0.4, 0.4)}}},
        )
        twist = bundle.env_cfg.commands["twist"]
        self.assertTrue(twist.heading_command)
        self.assertEqual(twist.ranges.lin_vel_x, (-0.4, 0.4))
        self.assertFalse(twist.debug_vis)

    def test_rejects_robot_specific_unknown_observation(self):
        contract = _cartpole_contract(self.xml)
        contract["observation"]["components"].append("foot_contact")
        with self.assertRaisesRegex(ValueError, "unsupported generic observation"):
            build_generic_task(contract, {"environment": {"terrain_type": "plane"}})


if __name__ == "__main__":
    unittest.main()
