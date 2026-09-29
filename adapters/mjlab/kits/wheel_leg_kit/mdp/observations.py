# ------------------------------------------------------------------------------
# B8 训练去包化（第二批）：本文件由 b2w_velocity/mdp/{name}.py **逐字上移**
# （== go2w_velocity 同名文件 sha256 一致；m20_velocity 同名文件亦逐字一致）。
# 包侧 mdp/__init__ 改为从本 kit 模块星导入，组合顺序与原 mdp/__init__ 相同。
# ------------------------------------------------------------------------------
from __future__ import annotations

from typing import TYPE_CHECKING

import torch

from mjlab.envs import mdp as envs_mdp
from mjlab.entity import Entity
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.sensor import ContactSensor

if TYPE_CHECKING:
  from mjlab.envs import ManagerBasedRlEnv

_DEFAULT_ASSET_CFG = SceneEntityCfg("robot")



def finite_obs(value: torch.Tensor, nan: float = 0.0, posinf: float = 0.0,
               neginf: float = 0.0) -> torch.Tensor:
  """Keep obs/metric reads finite when a terminating env has invalid physics state.

  上游 rc_mjlab mdp/rewards.py::_finite 同款：nan_to_num 出口清洗——物理在某个
  终止瞬间出现 inf/NaN（轮速 × 障碍深穿透等）时，清洗成有限值，本 episode 随即
  被 termination 摘除，不会污染策略输入（rsl_rl check_nan 不再误伤整批训练）。
  """

  import torch as _torch

  return _torch.nan_to_num(value, nan=nan, posinf=posinf, neginf=neginf)



def foot_height(
  env: ManagerBasedRlEnv, asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG
) -> torch.Tensor:
  asset: Entity = env.scene[asset_cfg.name]
  return asset.data.site_pos_w[:, asset_cfg.site_ids, 2]  # (num_envs, num_sites)


def foot_air_time(env: ManagerBasedRlEnv, sensor_name: str) -> torch.Tensor:
  sensor: ContactSensor = env.scene[sensor_name]
  sensor_data = sensor.data
  current_air_time = sensor_data.current_air_time
  assert current_air_time is not None
  return current_air_time


def foot_contact(env: ManagerBasedRlEnv, sensor_name: str) -> torch.Tensor:
  sensor: ContactSensor = env.scene[sensor_name]
  sensor_data = sensor.data
  assert sensor_data.found is not None
  return (sensor_data.found > 0).float()


def foot_contact_forces(env: ManagerBasedRlEnv, sensor_name: str) -> torch.Tensor:
  sensor: ContactSensor = env.scene[sensor_name]
  sensor_data = sensor.data
  assert sensor_data.force is not None
  forces_flat = sensor_data.force.flatten(start_dim=1)  # [B, N*3]
  return torch.sign(forces_flat) * torch.log1p(torch.abs(forces_flat))


def wheel_joint_pos_rel(
  env: ManagerBasedRlEnv,
  asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
  return envs_mdp.joint_pos_rel(env, asset_cfg=asset_cfg)


def wheel_joint_vel_rel(
  env: ManagerBasedRlEnv,
  asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
  return envs_mdp.joint_vel_rel(env, asset_cfg=asset_cfg)
