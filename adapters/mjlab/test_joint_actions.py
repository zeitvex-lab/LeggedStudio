"""Action-mode boundary tests: real XML, configs and small reset/step runs."""
from __future__ import annotations

import importlib
import importlib.util
import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from adapters.mjlab.generic_task_builder import build_generic_task

ROOT = Path(__file__).resolve().parents[2]
RECIPE = {"environment": {"terrain_type": "plane", "num_envs": 1},
          "reward_scales": {"joint_torques_l2": -0.01}}
XML = """<mujoco><worldbody>
<body name="base"><freejoint/><geom type="sphere" size="0.1"/>
<body><joint name="alpha"/><geom type="sphere" size="0.02"/></body>
<body><joint name="beta"/><geom type="sphere" size="0.02"/></body>
<body><joint name="gamma"/><geom type="sphere" size="0.02"/></body>
<body><joint name="delta"/><geom type="sphere" size="0.02"/></body>
<body><joint name="epsilon"/><geom type="sphere" size="0.02"/></body>
</body></worldbody><actuator>
<position joint="alpha" name="a" kp="10"/>
<velocity joint="beta" name="b" kv="2"/>
<position joint="gamma" name="c" kp="10"/>
<velocity joint="delta" name="d" kv="2"/>
<motor joint="epsilon" name="e"/>
</actuator></mujoco>"""


def fixture_contract(path):
    return {"contract_id": "mixed", "urdf": {"path": str(path)},
            "action": {"joint_order": ["gamma", "alpha", "delta", "beta", "epsilon"],
                       "action_scale": 0.5},
            "joints": {"default_pose": [0.2] * 5},
            "observation": {"components": ["joint_pos", "joint_vel", "last_action"]},
            "control": {"decimation": 1, "physics_hz": 1000}}


def robot_contract(robot):
    from contracts.contract_legacy_v2 import ContractLegacyV2
    return ContractLegacyV2.from_json_file(
        str(ROOT / "assets" / "robots" / robot / "contract_legacy_v2.json"))


class JointActionTests(unittest.TestCase):
    def factory(self):
        name = "adapters.mjlab.kits.joint_actions"
        self.assertIsNotNone(importlib.util.find_spec(name), "shared action factory is missing")
        return importlib.import_module(name).build_joint_actions

    def test_factory_keeps_interleaved_modes_and_per_joint_scales(self):
        # Grouping/sorting by mode would silently permute this policy interface.
        from mjlab.envs.mdp.actions import JointPositionActionCfg, JointVelocityActionCfg
        actions = self.factory()(
            joint_order=("beta", "gamma", "alpha", "delta", "epsilon"),
            control_modes={"beta": "velocity", "gamma": "position", "alpha": "position",
                           "delta": "velocity", "epsilon": "position"},
            scale={"beta": 7.0, "gamma": 0.2, "alpha": 0.3, "delta": 9.0, "epsilon": 0.4})
        terms = list(actions.values())
        self.assertEqual([("beta",), ("gamma", "alpha"), ("delta",), ("epsilon",)],
                         [tuple(t.actuator_names) for t in terms])
        for term, cls in zip(terms, (JointVelocityActionCfg, JointPositionActionCfg,
                                    JointVelocityActionCfg, JointPositionActionCfg)):
            self.assertIsInstance(term, cls)
            self.assertTrue(term.preserve_order)
        self.assertEqual([7.0, {"gamma": 0.2, "alpha": 0.3}, 9.0, 0.4], [t.scale for t in terms])
        for term in (terms[0], terms[2]):
            self.assertFalse(term.use_default_offset)
            self.assertEqual(0.0, term.offset)
        self.assertTrue(terms[1].use_default_offset)

    def test_factory_scalar_scale_and_explicit_term_names(self):
        actions = self.factory()(joint_order=("a", "b"),
                                 control_modes={"a": "position", "b": "velocity"},
                                 scale=0.75, term_names=("joint_pos", "wheel_vel"))
        self.assertEqual(["joint_pos", "wheel_vel"], list(actions))
        self.assertEqual([0.75, 0.75], [t.scale for t in actions.values()])

    def test_factory_rejects_unknown_or_missing_mode(self):
        factory = self.factory()
        for modes in ({"alpha": "torque"}, {"alpha": "effort"}, {}):
            with self.subTest(modes=modes), self.assertRaisesRegex(ValueError, "alpha"):
                factory(joint_order=("alpha",), control_modes=modes, scale=1.0)

    def test_generic_uses_xml_velocity_without_name_heuristics(self):
        from mjlab.envs.mdp.actions import JointPositionActionCfg, JointVelocityActionCfg
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "robot.xml"
            path.write_text(XML, encoding="utf-8")
            bundle = build_generic_task(fixture_contract(path), RECIPE)
        terms = list(bundle.env_cfg.actions.values())
        self.assertEqual(3, len(terms))
        self.assertIsInstance(terms[0], JointPositionActionCfg)
        self.assertIsInstance(terms[1], JointVelocityActionCfg)
        # Keep the existing position-input interface for motor/effort, not torque.
        self.assertIsInstance(terms[2], JointPositionActionCfg)
        self.assertEqual(["gamma", "alpha", "delta", "beta", "epsilon"],
                         [j for t in terms for j in t.actuator_names])
        self.assertEqual({"gamma": "position", "alpha": "position", "delta": "velocity",
                          "beta": "velocity", "epsilon": "position"},
                         bundle.diagnostics["action_control_modes"])
        self.assertEqual("effort", bundle.diagnostics["xml_command_fields"]["epsilon"])
        self.assertEqual(["epsilon"], bundle.diagnostics["legacy_effort_position_joints"])
        self.assertEqual([list(t.actuator_names) for t in terms],
                         [s["joint_order"] for s in bundle.diagnostics["action_segments"]])

    def test_generic_observation_selectors_keep_interface_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "robot.xml"
            path.write_text(XML, encoding="utf-8")
            bundle = build_generic_task(fixture_contract(path), RECIPE)
        for group in bundle.env_cfg.observations.values():
            for name in ("joint_pos", "joint_vel"):
                selector = group.terms[name].params["asset_cfg"]
                self.assertTrue(selector.preserve_order)
                self.assertEqual(("gamma", "alpha", "delta", "beta", "epsilon"), selector.joint_names)

    def test_four_real_wheel_leg_configs_bind_position_then_velocity(self):
        from mjlab.envs.mdp.actions import JointPositionActionCfg, JointVelocityActionCfg
        for robot in ("unitree_b2w", "unitree_go2w", "deeprobotics_m20", "zex-w"):
            with self.subTest(robot=robot):
                contract = robot_contract(robot)
                bundle = build_generic_task(contract, RECIPE)
                terms = list(bundle.env_cfg.actions.values())
                self.assertEqual(2, len(terms))
                self.assertIsInstance(terms[0], JointPositionActionCfg)
                self.assertIsInstance(terms[1], JointVelocityActionCfg)
                self.assertEqual([12, 4], [len(t.actuator_names) for t in terms])
                self.assertEqual(list(contract.action.joint_order),
                                 [j for t in terms for j in t.actuator_names])
                self.assertTrue(all(t.preserve_order for t in terms))

    def test_m20_profile_actions_are_equivalent_to_original_interface(self):
        # Hand-checked original profile: FL, FR, HL, HR; hipx .125, others .25; wheels 5.
        from mjlab.envs.mdp.actions import JointPositionActionCfg, JointVelocityActionCfg
        source = str(ROOT / "assets/robots/deeprobotics_m20/training/source")
        sys.path.insert(0, source)
        try:
            from m20_velocity.env_cfgs import m20_flat_env_cfg, m20_rough_env_cfg
            legs = tuple(f"{leg}_{joint}_joint" for leg in ("fl", "fr", "hl", "hr")
                         for joint in ("hipx", "hipy", "knee"))
            wheels = ("fl_wheel_joint", "fr_wheel_joint", "hl_wheel_joint", "hr_wheel_joint")
            expected = {
                "joint_pos": JointPositionActionCfg(entity_name="robot", actuator_names=legs,
                    preserve_order=True, scale=dict(zip(legs, [0.125, 0.25, 0.25] * 4)),
                    use_default_offset=True),
                "wheel_vel": JointVelocityActionCfg(entity_name="robot", actuator_names=wheels,
                    preserve_order=True, scale=5.0, offset=0.0, use_default_offset=False),
            }
            for builder in (m20_flat_env_cfg, m20_rough_env_cfg):
                cfg = builder()
                self.assertEqual(list(expected), list(cfg.actions))
                self.assertEqual({k: asdict(v) for k, v in expected.items()},
                                 {k: asdict(v) for k, v in cfg.actions.items()})
        finally:
            sys.path.remove(source)


class JointActionRuntimeTests(unittest.TestCase):
    def check_runtime(self, bundle, expected_order):
        import torch
        from mjlab.envs import ManagerBasedRlEnv
        # Small-env routing checks still need enough contact workspace for the
        # real assets' default pose; change capacity only, not physics parameters.
        bundle.env_cfg.sim.nconmax = 256
        bundle.env_cfg.sim.njmax = 1024
        env = ManagerBasedRlEnv(cfg=bundle.env_cfg, device="cpu")
        try:
            obs, _ = env.reset()
            manager = env.action_manager
            terms = [manager.get_term(n) for n in manager.active_terms]
            self.assertEqual(expected_order, [j for t in terms for j in t.target_names])
            action = torch.arange(1, len(expected_order) + 1, dtype=torch.float32)[None] * 0.01
            obs, reward, _, _, _ = env.step(action)
            self.assertTrue(torch.isfinite(obs["actor"]).all())
            self.assertTrue(torch.isfinite(reward).all())
            self.assertTrue(torch.isfinite(env.scene["robot"].data.joint_pos).all())
            cursor = 0
            for term, cfg in zip(terms, bundle.env_cfg.actions.values()):
                from mjlab.envs.mdp.actions import JointVelocityActionCfg
                if isinstance(cfg, JointVelocityActionCfg):
                    scales = [cfg.scale[j] if isinstance(cfg.scale, dict) else cfg.scale
                              for j in term.target_names]
                    expected = action[:, cursor:cursor + term.action_dim] * torch.tensor(scales)
                    actual = env.scene["robot"].data.joint_vel_target[:, term.target_ids]
                    torch.testing.assert_close(actual, expected)
                cursor += term.action_dim
        finally:
            env.close()

    def test_reverse_within_segments_survives_real_action_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "robot.xml"
            path.write_text(XML, encoding="utf-8")
            contract = fixture_contract(path)
            bundle = build_generic_task(contract, RECIPE)
            self.check_runtime(bundle, contract["action"]["joint_order"])

    def test_b2w_and_m20_generic_reset_step(self):
        for robot in ("unitree_b2w", "deeprobotics_m20"):
            with self.subTest(robot=robot):
                contract = robot_contract(robot)
                self.check_runtime(build_generic_task(contract, RECIPE), list(contract.action.joint_order))


if __name__ == "__main__":
    unittest.main()
