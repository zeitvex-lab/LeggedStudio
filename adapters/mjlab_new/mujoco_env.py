"""Contract-driven MuJoCo vector environment for Go2 and Go2W training."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from contracts.asset_paths import resolve_asset_path
from contracts.robot_contract_v2 import RobotContractV2


class ContractMujocoEnv:
    """Small vectorized MuJoCo environment with stable Contract semantics.

    The environment intentionally keeps the observation layout deterministic:
    free-base velocity, actuated joint position/velocity, and previous action,
    padded to the Contract observation dimension. This makes Go2 and Go2W use
    the same PPO/training pipeline while preserving their 12/16 actuator sets.
    """

    def __init__(self, contract: RobotContractV2, num_envs: int, episode_length_s: float = 20.0, seed: int = 0, reward_scales: dict[str, float] | None = None):
        self.contract = contract
        self.num_envs = max(1, int(num_envs))
        self.model_path = resolve_asset_path(contract.urdf.path)
        self.model = mujoco.MjModel.from_xml_path(str(self.model_path))
        self.data = [mujoco.MjData(self.model) for _ in range(self.num_envs)]
        self.rng = np.random.default_rng(seed)
        self.step_count = np.zeros(self.num_envs, dtype=np.int32)
        self.max_steps = max(1, int(round(episode_length_s * contract.control.control_hz)))
        self.action_dim = contract.action.dimension
        self.obs_dim = contract.observation.dimension
        self.joint_ids = [self.model.joint(name).id for name in contract.joints.actuated_joints]
        self.qpos_adrs = np.asarray([self.model.jnt_qposadr[index] for index in self.joint_ids], dtype=np.int32)
        self.dof_adrs = np.asarray([self.model.jnt_dofadr[index] for index in self.joint_ids], dtype=np.int32)
        self.actuator_ids = np.asarray([self.model.actuator(name).id for name in self._actuator_names()], dtype=np.int32)
        self.actuator_types = [self.model.actuator_trntype[index] for index in self.actuator_ids]
        self.previous_action = np.zeros((self.num_envs, self.action_dim), dtype=np.float32)
        self.default_pose = np.asarray(contract.joints.default_pose, dtype=np.float64)
        self.reward_scales = {"tracking_lin_vel": 1.0, "upright": 0.1, "base_height": 0.0, "torques": -0.001, "action_rate": -0.01}
        self.reward_scales.update(reward_scales or {})
        self.reset()

    def _actuator_names(self) -> list[str]:
        names = []
        for joint_name in self.contract.joints.actuated_joints:
            joint_id = self.model.joint(joint_name).id
            actuator_ids = np.flatnonzero(self.model.actuator_trnid[:, 0] == joint_id)
            if len(actuator_ids) == 0:
                raise ValueError(f"No actuator is bound to Contract joint: {joint_name}")
            names.append(self.model.actuator(actuator_ids[0]).name)
        return names

    def reset(self) -> np.ndarray:
        for index, item in enumerate(self.data):
            mujoco.mj_resetData(self.model, item)
            item.qpos[self.qpos_adrs] = self.default_pose
            item.qvel[:] = 0.0
            if item.qpos.shape[0] > 2:
                item.qpos[2] = max(float(item.qpos[2]), 0.28)
            mujoco.mj_forward(self.model, item)
            self.step_count[index] = 0
        self.previous_action.fill(0.0)
        return self._observations()

    def _observations(self) -> np.ndarray:
        observations = np.zeros((self.num_envs, self.obs_dim), dtype=np.float32)
        for index, item in enumerate(self.data):
            values = np.concatenate((item.qvel[:6], item.qpos[self.qpos_adrs], item.qvel[self.dof_adrs], self.previous_action[index]))
            observations[index, :min(self.obs_dim, len(values))] = values[:self.obs_dim]
        return observations

    def step(self, actions: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
        actions = np.asarray(actions, dtype=np.float32).reshape(self.num_envs, self.action_dim)
        actions = np.clip(actions, -1.0, 1.0)
        for index, item in enumerate(self.data):
            for action_index, actuator_id in enumerate(self.actuator_ids):
                actuator_type = self.actuator_types[action_index]
                if actuator_type == mujoco.mjtTrn.mjTRN_JOINT and self.model.actuator_gainprm[actuator_id, 0] > 0:
                    item.ctrl[actuator_id] = self.default_pose[action_index] + actions[index, action_index] * self.contract.action.action_scale
                else:
                    low, high = self.model.actuator_ctrlrange[actuator_id]
                    item.ctrl[actuator_id] = actions[index, action_index] * max(abs(float(low)), abs(float(high)))
            for _ in range(max(1, self.contract.control.decimation)):
                mujoco.mj_step(self.model, item)
            self.step_count[index] += 1
        observations = self._observations()
        base_velocity = np.asarray([item.qvel[0] for item in self.data], dtype=np.float32)
        yaw_velocity = np.asarray([item.qvel[5] if item.qvel.shape[0] > 5 else 0.0 for item in self.data], dtype=np.float32)
        height = np.asarray([item.qpos[2] if item.qpos.shape[0] > 2 else 1.0 for item in self.data], dtype=np.float32)
        upright = np.clip(height / 0.28, 0.0, 1.0)
        height_error = np.abs(height - 0.28)
        torque_cost = np.asarray([np.mean(item.ctrl[self.actuator_ids] ** 2) for item in self.data], dtype=np.float32)
        action_rate_cost = np.mean((actions - self.previous_action) ** 2, axis=1)
        components = {
            "tracking_lin_vel": base_velocity,
            "tracking_ang_vel": -np.abs(yaw_velocity),
            "orientation": 1.0 - upright,
            "upright": upright,
            "base_height": height_error,
            "torques": torque_cost,
            "action_rate": action_rate_cost,
        }
        rewards = np.zeros(self.num_envs, dtype=np.float32)
        for name, values in components.items():
            rewards += float(self.reward_scales.get(name, 0.0)) * values
        dones = (self.step_count >= self.max_steps) | (height < 0.12) | ~np.isfinite(rewards)
        self.previous_action[:] = actions
        info = {"base_velocity": base_velocity, "upright": upright, "reward_components": components, "reward_scales": self.reward_scales}
        return observations, rewards.astype(np.float32), dones.astype(np.bool_), info

    def close(self) -> None:
        self.data.clear()
