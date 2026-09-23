"""Generic-task env smoke: the built cfg must survive a real reset + step.

Guards the class of bug where a hand-assembled reward param (asset_cfg scope,
command wiring) is only rejected once a real environment runs — the preview and
unit tests alone cannot catch it.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from adapters.mjlab.generic_task_builder import build_generic_task

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "assets" / "robots" / "unitree_b2"


class GenericTaskEnvSmokeTest(unittest.TestCase):
    def test_generic_b2_task_resets_and_steps_with_preset_rewards(self):
        import torch
        from contracts.contract_legacy_v2 import ContractLegacyV2
        from mjlab.envs import ManagerBasedRlEnv

        contract = ContractLegacyV2.from_json_file(str(PACKAGE / "contract_legacy_v2.json"))
        recipe = {
            "environment": {"terrain_type": "plane", "num_envs": 2},
            "reward_scales": {
                "track_linear_velocity": 1.5,
                "track_angular_velocity": 0.5,
                "body_orientation_l2": -2.0,
                "joint_torques_l2": -0.0002,
                "action_rate_l2": -0.01,
            },
        }
        bundle = build_generic_task(contract, recipe)
        env = ManagerBasedRlEnv(cfg=bundle.env_cfg, device="cpu")
        obs, _ = env.reset()
        action = torch.zeros((env.num_envs, env.action_manager.total_action_dim))
        env.step(action)
        rewards = env.reward_manager.compute(dt=env.step_dt)
        self.assertEqual(tuple(rewards.shape), (env.num_envs,))
        self.assertIn("actor", obs)


if __name__ == "__main__":
    unittest.main()
