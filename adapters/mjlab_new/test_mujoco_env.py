import unittest

import numpy as np

from contracts.robot_contract_v2 import RobotContractV2
from adapters.mjlab_new.mujoco_env import ContractMujocoEnv


class ContractMujocoEnvTests(unittest.TestCase):
    def test_go2_rollout_shapes(self):
        contract = RobotContractV2.from_json_file("contracts/fixtures/unitree_go2.v2.json")
        env = ContractMujocoEnv(contract, num_envs=2, episode_length_s=0.1)
        try:
            obs = env.reset()
            next_obs, rewards, dones, info = env.step(np.zeros((2, contract.action.dimension), dtype=np.float32))
            self.assertEqual(obs.shape, (2, 48))
            self.assertEqual(next_obs.shape, (2, 48))
            self.assertEqual(rewards.shape, (2,))
            self.assertEqual(dones.shape, (2,))
            self.assertIn("base_velocity", info)
        finally:
            env.close()

    def test_go2w_has_sixteen_actuators(self):
        contract = RobotContractV2.from_json_file("contracts/fixtures/unitree_go2w.v2.json")
        env = ContractMujocoEnv(contract, num_envs=1, episode_length_s=0.1)
        try:
            self.assertEqual(env.model.nu, 16)
            self.assertEqual(env.reset().shape, (1, 56))
        finally:
            env.close()

    def test_reward_terms_can_be_disabled_or_reweighted(self):
        contract = RobotContractV2.from_json_file("contracts/fixtures/unitree_go2.v2.json")
        env = ContractMujocoEnv(contract, num_envs=1, episode_length_s=0.1, reward_scales={"upright": 0.0, "tracking_lin_vel": 0.0, "torques": 0.0, "action_rate": 0.0, "base_height": 0.0})
        try:
            _, rewards, _, info = env.step(np.zeros((1, contract.action.dimension), dtype=np.float32))
            self.assertEqual(float(rewards[0]), 0.0)
            self.assertEqual(info["reward_scales"]["upright"], 0.0)
        finally:
            env.close()


if __name__ == "__main__":
    unittest.main()
