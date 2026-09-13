"""XL330 test-bench RL environment.

Single-DOF fixed-base joint tracking task for sim2real validation.  Starts at 0
and must reach a target angle uniformly sampled in [-80°, 80°].  Uses the same
observation noise and action-smoothness regularization as the microduck velocity
env, with NO domain randomization so the learned policy can be transferred
directly to the real XL330 testbench.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

import torch

from mjlab.entity import Entity
from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs.manager_based_rl_env import ManagerBasedRlEnv
from mjlab.envs.mdp.actions import JointPositionActionCfg
from mjlab.envs import mdp as base_mdp
from mjlab.managers.command_manager import CommandTerm
from mjlab.managers import (
    CommandTermCfg,
    EventTermCfg,
    ObservationGroupCfg,
    ObservationTermCfg,
    RewardTermCfg,
    TerminationTermCfg,
)
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.rl import (
    RslRlOnPolicyRunnerCfg,
    RslRlPpoActorCriticCfg,
    RslRlPpoAlgorithmCfg,
)
from mjlab.scene import SceneCfg
from mjlab.sim import MujocoCfg, SimulationCfg
from mjlab.terrains import TerrainImporterCfg
from mjlab.utils.noise import UniformNoiseCfg as Unoise
from mjlab.viewer import ViewerConfig

from mjlab_microduck.robot.testbench_constants import XL330_TESTBENCH_ROBOT_CFG


# ----------------------------------------------------------------------------
# Target angle command (single joint)
# ----------------------------------------------------------------------------

TESTBENCH_MAX_ANGLE_RAD = math.radians(80.0)


class TargetAngleCommand(CommandTerm):
    """Uniform single-scalar target angle command."""

    cfg: "TargetAngleCommandCfg"

    def __init__(self, cfg: "TargetAngleCommandCfg", env: ManagerBasedRlEnv):
        super().__init__(cfg, env)
        self.robot: Entity = env.scene[cfg.asset_name]
        self._target = torch.zeros(self.num_envs, 1, device=self.device)
        self.metrics["error"] = torch.zeros(self.num_envs, device=self.device)
        joint_ids, _ = self.robot.find_joints([cfg.joint_name])
        self._joint_id = int(joint_ids[0])

    @property
    def command(self) -> torch.Tensor:
        return self._target

    def _resample_command(self, env_ids: torch.Tensor) -> None:
        lo, hi = self.cfg.range
        self._target[env_ids, 0] = (
            torch.rand(len(env_ids), device=self.device) * (hi - lo) + lo
        )

    def _update_command(self) -> None:
        pass

    def _update_metrics(self) -> None:
        q = self.robot.data.joint_pos[:, self._joint_id]
        self.metrics["error"] = torch.abs(q - self._target[:, 0])


@dataclass(kw_only=True)
class TargetAngleCommandCfg(CommandTermCfg):
    class_type: type[CommandTerm] = TargetAngleCommand
    asset_name: str = "robot"
    joint_name: str = "1"
    range: tuple[float, float] = (-TESTBENCH_MAX_ANGLE_RAD, TESTBENCH_MAX_ANGLE_RAD)
    resampling_time_range: tuple[float, float] = (4.0, 4.0)


# ----------------------------------------------------------------------------
# Rewards
# ----------------------------------------------------------------------------


def target_angle_tracking(
    env: ManagerBasedRlEnv,
    command_name: str,
    std: float,
    asset_cfg: SceneEntityCfg,
) -> torch.Tensor:
    """exp(-error^2 / std^2) reward for single-joint position tracking."""
    target = env.command_manager.get_command(command_name)[:, 0]
    asset: Entity = env.scene[asset_cfg.name]
    joint_ids = asset_cfg.joint_ids
    q = asset.data.joint_pos[:, joint_ids[0] if isinstance(joint_ids, list) else joint_ids]
    if q.dim() > 1:
        q = q[:, 0]
    err = q - target
    return torch.exp(-(err ** 2) / (std ** 2))


# ----------------------------------------------------------------------------
# Env factory
# ----------------------------------------------------------------------------


