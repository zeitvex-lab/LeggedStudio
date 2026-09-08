"""DreamWaQ M20 reward terms (legged_gym ``M20_Robot`` reward table).

Weights follow the source ``rewards.scales`` with mjlab's
``scale_rewards_by_dt`` semantics (each term is scaled by the control-step
dt, matching legged_gym's scale*dt).  The source clips the summed reward at
zero (``only_positive_rewards``); mjlab 1.6's RewardManager has no per-step
sum hook, so the clip is not reproduced (same deviation as the Go2 port).
"""

import torch

from mjlab.entity import Entity
from mjlab.managers.scene_entity_config import SceneEntityCfg

from ..constants import M20_HIPX_JOINT_NAMES


def _joint_ids(robot: Entity, asset_cfg: SceneEntityCfg) -> list[int]:
  return asset_cfg.joint_ids


def tracking_lin_vel(env, command_name: str, sigma: float) -> torch.Tensor:
  command = env.command_manager.get_command(command_name)
  assert command is not None
  error = torch.square(
    command[:, :2] - env.scene["robot"].data.root_link_lin_vel_b[:, :2]
  ).sum(1)
  return torch.exp(-error / sigma)


def tracking_ang_vel(env, command_name: str, sigma: float) -> torch.Tensor:
  command = env.command_manager.get_command(command_name)
  assert command is not None
  error = torch.square(
    command[:, 2] - env.scene["robot"].data.root_link_ang_vel_b[:, 2]
  )
  return torch.exp(-error / sigma)


def lin_vel_z(env) -> torch.Tensor:
  return torch.square(env.scene["robot"].data.root_link_lin_vel_b[:, 2])


def ang_vel_xy(env) -> torch.Tensor:
  return torch.square(env.scene["robot"].data.root_link_ang_vel_b[:, :2]).sum(1)


def orientation(env) -> torch.Tensor:
  return torch.square(env.scene["robot"].data.projected_gravity_b[:, :2]).sum(1)


def base_height(env, target_height: float, sensor_name: str) -> torch.Tensor:
  # Source: square(mean(root_z - measured_heights) - base_height_target) over
  # the 17x11 terrain probe grid.
  robot: Entity = env.scene["robot"]
  scan = env.scene[sensor_name].data
  terrain_z = scan.hit_pos_w[..., 2].mean(1)
  return torch.square(robot.data.root_link_pos_w[:, 2] - terrain_z - target_height)


def torques(env) -> torch.Tensor:
  robot: Entity = env.scene["robot"]
  return torch.square(robot.data.qfrc_actuator).sum(1)


def dof_vel_wheel_masked(env, asset_cfg: SceneEntityCfg) -> torch.Tensor:
  """Source ``_reward_dof_vel``: wheel slots are excluded."""
  robot: Entity = env.scene["robot"]
  ids = _joint_ids(robot, asset_cfg)
  return torch.square(robot.data.joint_vel[:, ids]).sum(1)


def dof_acc(env) -> torch.Tensor:
  """Source ``_reward_dof_acc``: finite difference over all 16 joints."""
  robot: Entity = env.scene["robot"]
  last = getattr(env, "_m20_dreamwaq_last_dof_vel", None)
  if last is None:
    last = torch.zeros_like(robot.data.joint_vel)
    setattr(env, "_m20_dreamwaq_last_dof_vel", last)
  value = torch.square((last - robot.data.joint_vel) / env.step_dt).sum(1)
  last.copy_(robot.data.joint_vel)
  return value


def collision(env, sensor_name: str) -> torch.Tensor:
  """Count non-wheel bodies (base + hipx/hipy/knee) in contact."""
  force = env.scene[sensor_name].data.force
  assert force is not None
  return (torch.linalg.vector_norm(force, dim=-1) > 0.1).float().sum(1)


def action_rate(env) -> torch.Tensor:
  return torch.square(env.action_manager.action - env.action_manager.prev_action).sum(1)


def stand_still(env, command_name: str, asset_cfg: SceneEntityCfg) -> torch.Tensor:
  """Leg joint deviation from default while the xy command is ~zero."""
  robot: Entity = env.scene["robot"]
  ids = _joint_ids(robot, asset_cfg)
  command = env.command_manager.get_command(command_name)
  assert command is not None
  error = (
    robot.data.joint_pos[:, ids] - robot.data.default_joint_pos[:, ids]
  ).abs().sum(1)
  return error * (torch.linalg.vector_norm(command[:, :2], dim=1) < 0.1)


def run_still(env, command_name: str, asset_cfg: SceneEntityCfg) -> torch.Tensor:
  """Leg joint deviation from default while the xy command is active."""
  robot: Entity = env.scene["robot"]
  ids = _joint_ids(robot, asset_cfg)
  command = env.command_manager.get_command(command_name)
  assert command is not None
  error = (
    robot.data.joint_pos[:, ids] - robot.data.default_joint_pos[:, ids]
  ).abs().sum(1)
  return error * (torch.linalg.vector_norm(command[:, :2], dim=1) > 0.1)


def dof_pos_limits(env, asset_cfg: SceneEntityCfg) -> torch.Tensor:
  """Soft-limit penalty on leg joints (wheels carry no position limits)."""
  robot: Entity = env.scene["robot"]
  ids = _joint_ids(robot, asset_cfg)
  position = robot.data.joint_pos[:, ids]
  limits = robot.data.soft_joint_pos_limits[:, ids]
  return (
    -(position - limits[..., 0]).clamp(max=0.0)
    + (position - limits[..., 1]).clamp(min=0.0)
  ).sum(1)


def hip_default(env, asset_cfg: SceneEntityCfg) -> torch.Tensor:
  """Source ``_reward_hip_default``: hipx deviation from default."""
  robot: Entity = env.scene["robot"]
  ids, names = robot.find_joints(M20_HIPX_JOINT_NAMES, preserve_order=True)
  del names
  del asset_cfg
  error = robot.data.joint_pos[:, ids] - robot.data.default_joint_pos[:, ids]
  return torch.square(error).sum(1)
