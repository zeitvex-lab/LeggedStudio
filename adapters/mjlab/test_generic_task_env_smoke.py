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

    def test_env_builds_for_unnamed_sensors_and_geom_margins(self):
        """两类**真实机型资产**上的建环境阻断（2026-09-24 可训矩阵实测，非构造样例）。

        - lite3：MJCF 里有无名 `<gyro>`/`<accelerometer>` ⇒ mjlab scene 按名包装时
          `KeyError: Invalid name ''`；
        - go2：default class 上 `margin="0.001"` × 地形 BOX ⇒ mujoco_warp 在 MULTICCD 下
          `NotImplementedError`（plane 档不触发，必须用带 BOX 地形 geom 的档复现）。

        两者都只在**真建环境**时暴露，预览/单测看不出来——所以锁在这里，用真实包的 XML。
        """
        import torch
        from contracts.contract_legacy_v2 import ContractLegacyV2
        from mjlab.envs import ManagerBasedRlEnv

        for robot_id, terrain in (("deeprobotics_lite3", "plane"), ("unitree_go2", "rough")):
            with self.subTest(robot=robot_id, terrain=terrain):
                contract = ContractLegacyV2.from_json_file(
                    str(ROOT / "assets" / "robots" / robot_id / "contract_legacy_v2.json"))
                bundle = build_generic_task(
                    contract,
                    {"environment": {"terrain_type": terrain, "num_envs": 2},
                     "reward_scales": {"track_linear_velocity": 1.0, "track_angular_velocity": 0.5}},
                )
                env = ManagerBasedRlEnv(cfg=bundle.env_cfg, device="cpu")
                obs, _ = env.reset()
                action = torch.zeros((env.num_envs, env.action_manager.total_action_dim))
                env.step(action)
                self.assertEqual(tuple(obs["actor"].shape)[0], env.num_envs)


if __name__ == "__main__":
    unittest.main()
