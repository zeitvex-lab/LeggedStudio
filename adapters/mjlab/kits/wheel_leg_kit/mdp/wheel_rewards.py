# ------------------------------------------------------------------------------
# B8 训练去包化（第二批）：本文件由 b2w_velocity/mdp/{name}.py **逐字上移**
# （== go2w_velocity 同名文件 sha256 一致；m20_velocity 同名文件亦逐字一致）。
# 包侧 mdp/__init__ 改为从本 kit 模块星导入，组合顺序与原 mdp/__init__ 相同。
# ------------------------------------------------------------------------------
from __future__ import annotations

import math
from typing import TYPE_CHECKING

import torch

from mjlab.entity import Entity
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.sensor import ContactSensor

if TYPE_CHECKING:
  from mjlab.envs import ManagerBasedRlEnv


_DEFAULT_ASSET_CFG = SceneEntityCfg("robot")


def _total_command_magnitude(env: ManagerBasedRlEnv, command_name: str) -> torch.Tensor:
  command = env.command_manager.get_command(command_name)
  assert command is not None, f"Command '{command_name}' not found."
  linear_norm = torch.norm(command[:, :2], dim=1)
  angular_norm = torch.abs(command[:, 2])
  return linear_norm + angular_norm


def wheel_roll_tracking(
  env: ManagerBasedRlEnv,
  command_name: str,
  wheel_radius: float,
  wheel_track: float,
  std: float,
  asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
  """Reward wheel angular velocity matching the commanded planar motion."""
  asset: Entity = env.scene[asset_cfg.name]
  command = env.command_manager.get_command(command_name)
  assert command is not None, f"Command '{command_name}' not found."

  wheel_vel = asset.data.joint_vel[:, asset_cfg.joint_ids]
  side_signs = torch.tensor(
    [1.0, -1.0, 1.0, -1.0],
    device=env.device,
    dtype=wheel_vel.dtype,
  ).unsqueeze(0)

  lin_vel_x = command[:, 0:1]
  ang_vel_z = command[:, 2:3]
  target_wheel_vel = (
    lin_vel_x + 0.5 * wheel_track * side_signs * ang_vel_z
  ) / wheel_radius

  err = torch.mean(torch.square(wheel_vel - target_wheel_vel), dim=1)
  reward = torch.exp(-err / (std**2))
  env.extras["log"]["Metrics/wheel_roll_error_mean"] = torch.mean(torch.sqrt(err))
  return reward


def wheel_speed_limit_penalty(
  env: ManagerBasedRlEnv,
  max_abs_speed: float,
  command_name: str | None = None,
  command_threshold: float = 0.05,
  asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
  """Penalize wheel speeds above the configured limit."""
  asset: Entity = env.scene[asset_cfg.name]
  wheel_vel = asset.data.joint_vel[:, asset_cfg.joint_ids]
  excess = torch.clamp(torch.abs(wheel_vel) - max_abs_speed, min=0.0)
  cost = torch.mean(torch.square(excess), dim=1)

  if command_name is not None:
    active = (_total_command_magnitude(env, command_name) > command_threshold).float()
    cost = cost * active

  env.extras["log"]["Metrics/wheel_speed_excess_mean"] = torch.mean(
    torch.mean(excess, dim=1)
  )
  return cost


def leg_motion_penalty(
  env: ManagerBasedRlEnv,
  command_name: str,
  command_threshold: float = 0.05,
  asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
  """Penalize leg motion while the robot is commanded to move."""
  asset: Entity = env.scene[asset_cfg.name]
  leg_vel = asset.data.joint_vel[:, asset_cfg.joint_ids]
  cost = torch.mean(torch.square(leg_vel), dim=1)
  active = (_total_command_magnitude(env, command_name) > command_threshold).float()
  return cost * active


def adaptive_leg_motion_penalty(
  env: ManagerBasedRlEnv,
  command_name: str,
  sensor_name: str,
  command_threshold: float = 0.05,
  tilt_relax_start: float = 0.08,
  tilt_relax_end: float = 0.30,
  contact_target: float = 0.85,
  min_penalty_scale: float = 0.2,
  asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
  """Penalize leg motion less when tilt or wheel contact suggests recovery."""
  asset: Entity = env.scene[asset_cfg.name]
  leg_vel = asset.data.joint_vel[:, asset_cfg.joint_ids]
  base_cost = torch.mean(torch.square(leg_vel), dim=1)
  active = (_total_command_magnitude(env, command_name) > command_threshold).float()

  tilt_xy = torch.norm(asset.data.projected_gravity_b[:, :2], dim=1)
  tilt_relax = torch.clamp(
    (tilt_xy - tilt_relax_start) / max(tilt_relax_end - tilt_relax_start, 1.0e-6),
    min=0.0,
    max=1.0,
  )

  sensor: ContactSensor = env.scene[sensor_name]
  assert sensor.data.found is not None
  in_contact = (sensor.data.found > 0).float()
  contact_fraction = torch.mean(in_contact, dim=1)
  if contact_fraction.ndim > 1:
    contact_fraction = torch.mean(contact_fraction, dim=1)
  contact_relax = torch.clamp(
    (contact_target - contact_fraction) / max(contact_target, 1.0e-6),
    min=0.0,
    max=1.0,
  )

  relax = torch.maximum(tilt_relax, contact_relax)
  penalty_scale = 1.0 - (1.0 - min_penalty_scale) * relax
  env.extras["log"]["Metrics/leg_penalty_scale_mean"] = torch.mean(penalty_scale)
  return base_cost * active * penalty_scale


def contact_fraction_reward(
  env: ManagerBasedRlEnv,
  sensor_name: str,
) -> torch.Tensor:
  """Reward persistent wheel-ground contact."""
  sensor: ContactSensor = env.scene[sensor_name]
  assert sensor.data.found is not None
  in_contact = (sensor.data.found > 0).float()
  return torch.mean(in_contact, dim=1)

# ------------------------------------------------------------------------------
# 轮足站立/轮轴姿态奖励（2026-10-17 从 legbot_lab WF-CTS-MOE 提取，Apache-2.0）
#
# 来源：00_resources/legbot_lab_WF-CTS-MOE/source/robot_lab/robot_lab/tasks/legbot/env/rewards.py
# 适配：Isaac Lab 的 `body_quat_w` → mjlab 的 `body_link_quat_w`；高度扫描改为可选
# （没有 `ray_hits_w` 的档位只用 upright 项）；其余公式与阈值保持源实现。
# 许可见 00_resources/legbot_lab_WF-CTS-MOE/_SOURCE.md。默认关闭，由 profile 的
# `wheel_stance` 显式启用；上游权重未按本仓机型标定，启用前须按效果口径实测。
# ------------------------------------------------------------------------------


def _standing_mask(
  command: torch.Tensor,
  linear_threshold: float,
  yaw_threshold: float,
) -> torch.Tensor:
  """线速度与角速度单位不同，分开判零命令（源实现同口径）。"""
  return (torch.linalg.vector_norm(command[:, :2], dim=1) < linear_threshold) & (
    torch.abs(command[:, 2]) < yaw_threshold
  )


def _flat_upright_weight(
  env: ManagerBasedRlEnv,
  sensor_name: str | None,
  flatness_std: float,
) -> torch.Tensor:
  asset: Entity = env.scene["robot"]
  upright = torch.clamp(-asset.data.projected_gravity_b[:, 2], 0.0, 0.7) / 0.7
  if not sensor_name:
    return upright
  try:
    sensor = env.scene[sensor_name]
    heights = sensor.data.ray_hits_w[..., 2]
  except (KeyError, AttributeError):
    # 没有高度扫描数据的档位：只保留 upright 偏好，不产生 NaN。
    return upright
  valid = torch.isfinite(heights).all(dim=1) & (torch.abs(heights) < 1e6).all(dim=1)
  safe = torch.nan_to_num(heights, nan=0.0, posinf=0.0, neginf=0.0).clamp(-1e6, 1e6)
  variance = torch.mean(
    torch.square(safe - safe.mean(dim=1, keepdim=True)), dim=1
  )
  flat = torch.exp(-variance / flatness_std**2)
  return upright * flat * valid.to(upright.dtype)


def joint_pose_l1_standing_scaled(
  env: ManagerBasedRlEnv,
  command_name: str,
  asset_cfg: SceneEntityCfg,
  stand_still_scale: float = 2.0,
  linear_threshold: float = 0.1,
  yaw_threshold: float = 0.1,
  sensor_name: str | None = None,
  flatness_std: float = 0.03,
) -> torch.Tensor:
  """静立且接近平地时，放大实测关节姿态的 L1 代价（源实现同口径）。"""
  asset: Entity = env.scene[asset_cfg.name]
  default_joint_pos = asset.data.default_joint_pos
  assert default_joint_pos is not None, "joint_pose_l1_standing_scaled 需要默认关节角"
  deviation = torch.sum(
    torch.abs(
      asset.data.joint_pos[:, asset_cfg.joint_ids]
      - default_joint_pos[:, asset_cfg.joint_ids]
    ),
    dim=1,
  )
  command = env.command_manager.get_command(command_name)
  assert command is not None, f"Command '{command_name}' not found."
  standing = _standing_mask(command, linear_threshold, yaw_threshold)
  extra = standing.to(deviation.dtype) * _flat_upright_weight(
    env, sensor_name, flatness_std
  )
  return deviation * (1.0 + (stand_still_scale - 1.0) * extra)


def wheel_axis_alignment_l2(
  env: ManagerBasedRlEnv,
  command_name: str,
  asset_cfg: SceneEntityCfg,
  sensor_name: str | None = None,
  std: float = 0.2,
  deadzone_degrees: float = 2.0,
  straight_scale: float = 0.25,
  linear_threshold: float = 0.1,
  yaw_threshold: float = 0.1,
  flatness_std: float = 0.03,
) -> torch.Tensor:
  """惩罚轮轴 toe/camber：静立全权重，直行弱，横移/转向关闭（源实现同口径）。

  轮轴按轮 link 的局部 ±Y 轴计算（W1W 几何约定）；符号与轮子转向无关。
  """
  asset: Entity = env.scene[asset_cfg.name]
  wheel_quat = asset.data.body_link_quat_w[:, asset_cfg.body_ids]
  w, x, y, z = wheel_quat.unbind(dim=-1)
  axle_w = torch.stack(
    (
      2.0 * (x * y - w * z),
      1.0 - 2.0 * (x * x + z * z),
      2.0 * (y * z + w * x),
    ),
    dim=-1,
  )
  bw, bx, by, bz = asset.data.root_link_quat_w.unbind(dim=-1)
  forward_w = torch.stack(
    (
      1.0 - 2.0 * (by * by + bz * bz),
      2.0 * (bx * by + bw * bz),
      2.0 * (bx * bz - bw * by),
    ),
    dim=-1,
  )
  toe = torch.sum(axle_w * forward_w[:, None, :], dim=-1)
  camber = axle_w[..., 2]
  deadzone = math.sin(math.radians(deadzone_degrees))
  error = torch.mean(
    torch.square(torch.relu(torch.abs(toe) - deadzone))
    + torch.square(torch.relu(torch.abs(camber) - deadzone)),
    dim=1,
  ) / std**2
  command = env.command_manager.get_command(command_name)
  assert command is not None, f"Command '{command_name}' not found."
  standing = _standing_mask(command, linear_threshold, yaw_threshold)
  straight = (torch.abs(command[:, 1]) < linear_threshold) & (
    torch.abs(command[:, 2]) < yaw_threshold
  )
  context = torch.where(
    standing, torch.ones_like(error), straight_scale * straight.to(error.dtype)
  )
  return error * context * _flat_upright_weight(env, sensor_name, flatness_std)


def standing_joint_vel_l2(
  env: ManagerBasedRlEnv,
  command_name: str,
  asset_cfg: SceneEntityCfg,
  wheel_asset_cfg: SceneEntityCfg,
  sensor_name: str | None = None,
  leg_std: float = 1.0,
  wheel_std: float = 5.0,
  linear_threshold: float = 0.1,
  yaw_threshold: float = 0.1,
  flatness_std: float = 0.03,
) -> torch.Tensor:
  """只在校零命令时惩罚不必要的腿/轮速度（源实现同口径）。"""
  asset: Entity = env.scene[asset_cfg.name]
  leg_cost = torch.mean(
    torch.square(asset.data.joint_vel[:, asset_cfg.joint_ids] / leg_std), dim=1
  )
  wheel_cost = torch.mean(
    torch.square(
      asset.data.joint_vel[:, wheel_asset_cfg.joint_ids] / wheel_std
    ),
    dim=1,
  )
  command = env.command_manager.get_command(command_name)
  assert command is not None, f"Command '{command_name}' not found."
  standing = _standing_mask(command, linear_threshold, yaw_threshold)
  return (leg_cost + wheel_cost) * standing.to(leg_cost.dtype) * _flat_upright_weight(
    env, sensor_name, flatness_std
  )
