"""Go2 机型专属的观测帧（薄 shim + 未上移的那几帧）。

被**速度跟踪算法变体**（CTS / AMP-CTS / TS / AMP-TS / TS-学生 / HIM / DreamWaQ /
AMP-DreamWaQ）消费的帧、历史类与域随机化标签助手已上移到族级
`adapters/mjlab/kits/quadruped_kit/skills/mdp/observations.py`：本模块把族级实现
**按原函数名再导出**（入口字符串与既有调用方一律不动），只保留机型专属的帧
（trot / jump / stand / backflip / spring_jump 的特权帧与动作观测帧）。

与族级实现共用的还有 `_go2_delayed_policy_state`（延时动作项的观测旁路）与
`_go2_terrain_heights`（地形高度扫描）—— 同一份实现，不再各写一份。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torch
from mjlab.entity import Entity
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.sensor import ContactSensor
from mjlab.sensor.raycast_sensor import RayCastSensor
from mjlab.utils.lab_api.math import euler_xyz_from_quat

from adapters.mjlab.kits.quadruped_kit.skills.mdp.observations import (
    HimHistory as Go2HimHistory,
)
from adapters.mjlab.kits.quadruped_kit.skills.mdp.observations import (
    SourceActorFrame as Go2SourceStandActor,
)
from adapters.mjlab.kits.quadruped_kit.skills.mdp.observations import (
    SourceActorHistory as Go2SourceStandHistory,
)
from adapters.mjlab.kits.quadruped_kit.skills.mdp.observations import (
    _delayed_policy_state as _go2_delayed_policy_state,
)
from adapters.mjlab.kits.quadruped_kit.skills.mdp.observations import (
    amp_state_frame as go2_amp_observation,
)
from adapters.mjlab.kits.quadruped_kit.skills.mdp.observations import (
    cts_critic_frame as go2_source_cts_critic_observation,
)
from adapters.mjlab.kits.quadruped_kit.skills.mdp.observations import (
    cts_privileged_frame as go2_source_cts_privileged_observation,
)
from adapters.mjlab.kits.quadruped_kit.skills.mdp.observations import (
    cts_teacher_mask as go2_cts_teacher_mask,
)
from adapters.mjlab.kits.quadruped_kit.skills.mdp.observations import (
    dreamwaq_privileged_frame as go2_source_dreamwaq_privileged_observation,
)
from adapters.mjlab.kits.quadruped_kit.skills.mdp.observations import (
    dreamwaq_velocity_target as go2_dreamwaq_velocity_target,
)
from adapters.mjlab.kits.quadruped_kit.skills.mdp.observations import (
    him_privileged_frame as go2_him_privileged_observation,
)
from adapters.mjlab.kits.quadruped_kit.skills.mdp.observations import (
    source_foot_contact_bits,
)
from adapters.mjlab.kits.quadruped_kit.skills.mdp.observations import (
    source_stand_frame as go2_source_stand_observation,
)
from adapters.mjlab.kits.quadruped_kit.skills.mdp.observations import (
    source_terrain_heights as go2_source_terrain_heights,
)
from adapters.mjlab.kits.quadruped_kit.skills.mdp.observations import (
    terrain_heights as _go2_terrain_heights,
)
from adapters.mjlab.kits.quadruped_kit.skills.mdp.observations import (
    ts_critic_frame as go2_source_ts_critic_observation,
)
from adapters.mjlab.kits.quadruped_kit.skills.mdp.observations import (
    ts_privileged_frame as go2_source_ts_privileged_observation,
)

from .actions import Go2DelayedJointPositionAction  # noqa: F401  (延时动作项的类型契约)

if TYPE_CHECKING:
  from mjlab.envs import ManagerBasedRlEnv


_DEFAULT_ASSET_CFG = SceneEntityCfg("robot")

#: 源观测契约的足序（源实现按 `(1, 0, 3, 2)` 重排共享传感器槽位 —— 等价于本机型
#: 观测缓冲的足序是 FR, FL, RR, RL）。族级实现按"契约足序"取位，故这里是数据。
_CONTRACT_CONTACT_ORDER = ("FR", "FL", "RR", "RL")


def _go2_source_contact_mask(sensor: ContactSensor, threshold: float) -> torch.Tensor:
  """源口径的足端接触位（按本机型观测契约的足序）—— 由族级实现代跑。"""
  return source_foot_contact_bits(sensor, threshold, _CONTRACT_CONTACT_ORDER)
















def _go2_stand_randomization_fields(env: ManagerBasedRlEnv) -> torch.Tensor:
  """Build the 34-D stand-task randomization block from MuJoCo model data."""
  asset: Entity = env.scene["robot"]
  zeros = torch.zeros((env.num_envs, 34), device=env.device)
  try:
    model = env.sim.model
    default = env.sim.get_default_field
    body_id = asset.indexing.body_ids[0]
    default_mass = default("body_mass")[body_id]
    mass = model.body_mass[:, body_id : body_id + 1] - default_mass
    com = model.body_ipos[:, body_id] - default("body_ipos")[body_id]
    default_gain = default("actuator_gainprm")
    default_bias = default("actuator_biasprm")
    ctrl_ids = asset.indexing.ctrl_ids
    kp = model.actuator_gainprm[:, ctrl_ids, 0] / default_gain[ctrl_ids, 0].clamp_min(
      1e-6
    )
    kd = (-model.actuator_biasprm[:, ctrl_ids, 2]) / (
      -default_bias[ctrl_ids, 2]
    ).clamp_min(1e-6)
    dof_ids = asset.indexing.joint_v_adr
    armature = model.dof_armature[:, dof_ids].mean(dim=-1, keepdim=True)
    friction_loss = model.dof_frictionloss[:, dof_ids].mean(dim=-1, keepdim=True)
    damping = model.dof_damping[:, dof_ids].mean(dim=-1, keepdim=True)
    geom = model.geom_friction[:, asset.indexing.geom_ids, 0].mean(dim=-1, keepdim=True)
    restitution = torch.zeros_like(geom)
    if kp.shape[-1] != 12 or kd.shape[-1] != 12:
      return zeros
    return torch.cat(
      (
        geom,
        mass,
        com,
        kp,
        kd,
        armature,
        friction_loss,
        damping,
        restitution,
        restitution,
      ),
      dim=-1,
    )
  except (AttributeError, IndexError, RuntimeError, TypeError):
    return zeros


def go2_source_trot_observation(
  env: ManagerBasedRlEnv,
  command_name: str = "twist",
  asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
  cycle_time: float = 0.5,
) -> torch.Tensor:
  """Build the 47-D single-frame observation used by the source Go2 trot task.

  The source Isaac Gym task concatenates phase (sin/cos), scaled commands, IMU
  angular velocity and Euler angles, relative joint position/velocity, and the
  previous policy action.  History is intentionally configured on the
  ``ObservationTermCfg`` so mjlab stores the frames in chronological order.
  """
  asset: Entity = env.scene[asset_cfg.name]
  command = env.command_manager.get_command(command_name)
  assert command is not None, f"Command '{command_name}' not found."

  phase = (
    (env.episode_length_buf.to(dtype=torch.float32) * env.step_dt)
    % cycle_time
    / cycle_time
  )
  phase_features = torch.stack(
    (torch.sin(2.0 * torch.pi * phase), torch.cos(2.0 * torch.pi * phase)), dim=1
  )

  command_scale = torch.tensor((2.0, 2.0, 0.25), device=env.device)
  command_features = command[:, :3] * command_scale
  roll, pitch, yaw = euler_xyz_from_quat(asset.data.root_link_quat_w)
  euler_xyz = torch.stack((roll, pitch, yaw), dim=-1)
  delayed = _go2_delayed_policy_state(env)
  if delayed is None:
    imu = torch.cat((asset.data.root_link_ang_vel_b * 0.25, euler_xyz), dim=-1)
    joint_pos = asset.data.joint_pos - asset.data.default_joint_pos
    joint_vel = asset.data.joint_vel * 0.05
  else:
    joint_pos, joint_vel, imu = delayed
  actions = env.action_manager.action
  return torch.cat(
    (phase_features, command_features, imu, joint_pos, joint_vel, actions),
    dim=-1,
  )


def go2_source_trot_privileged_observation(
  env: ManagerBasedRlEnv,
  command_name: str = "twist",
  sensor_name: str = "feet_ground_contact",
  asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
  cycle_time: float = 0.5,
  stance_threshold: float = 0.5,
) -> torch.Tensor:
  """Build the 68-D privileged frame used by the source Go2 trot critic."""
  asset: Entity = env.scene[asset_cfg.name]
  command = env.command_manager.get_command(command_name)
  assert command is not None, f"Command '{command_name}' not found."
  phase = (
    (env.episode_length_buf.to(dtype=torch.float32) * env.step_dt)
    % cycle_time
    / cycle_time
  )
  phase_features = torch.stack(
    (torch.sin(2.0 * torch.pi * phase), torch.cos(2.0 * torch.pi * phase)),
    dim=1,
  )
  command_input = torch.cat(
    (
      phase_features,
      command[:, :3] * torch.tensor((2.0, 2.0, 0.25), device=env.device),
    ),
    dim=1,
  )
  q_rel = asset.data.joint_pos - asset.data.default_joint_pos
  q = asset.data.joint_pos
  dq = asset.data.joint_vel * 0.05
  roll, pitch, yaw = euler_xyz_from_quat(asset.data.root_link_quat_w)
  euler_xyz = torch.stack((roll, pitch, yaw), dim=-1)
  stance_mask = torch.stack(
    (phase < stance_threshold, phase > stance_threshold), dim=1
  ).to(torch.float32)
  sensor: ContactSensor = env.scene[sensor_name]
  contact = _go2_source_contact_mask(sensor, threshold=5.0)
  return torch.cat(
    (
      command_input,
      q_rel,
      q,
      dq,
      env.action_manager.action,
      # Source ``obs_scales.lin_vel`` is 2.0 for the privileged critic frame;
      # actor IMU velocity remains represented only through the 0.25 angular
      # scale above.
      asset.data.root_link_lin_vel_b * 2.0,
      asset.data.root_link_ang_vel_b * 0.25,
      euler_xyz,
      stance_mask,
      contact,
    ),
    dim=-1,
  )


def go2_source_jump_privileged_observation(
  env: ManagerBasedRlEnv,
  command_name: str = "twist",
  sensor_name: str = "feet_ground_contact",
  asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
  """Build the source jump critic frame (68-D state plus two randomization fields)."""
  base = go2_source_trot_privileged_observation(
    env,
    command_name=command_name,
    sensor_name=sensor_name,
    asset_cfg=asset_cfg,
    cycle_time=1.5,
    # The source ``_get_gait_phase`` splits the cycle at one half for Jump;
    # the 1.5 s cycle length does not change that threshold.
    stance_threshold=0.5,
  )
  # The Isaac Gym jump critic appends the sampled friction coefficient and the
  # base mass normalized by 10.  Read the corresponding MuJoCo batch fields;
  # retain a finite zero fallback for minimal test doubles without model data.
  friction = torch.zeros((base.shape[0], 1), device=base.device, dtype=base.dtype)
  mass = torch.zeros_like(friction)
  try:
    asset: Entity = env.scene[asset_cfg.name]
    model = env.sim.model
    friction = model.geom_friction[:, asset.indexing.geom_ids, 0].mean(
      dim=-1, keepdim=True
    )
    body_id = asset.indexing.body_ids[0]
    mass = model.body_mass[:, body_id : body_id + 1] / 10.0
    friction = friction.to(dtype=base.dtype)
    mass = mass.to(dtype=base.dtype)
  except (AttributeError, IndexError, RuntimeError, TypeError):
    pass
  extras = torch.cat((friction, mass), dim=-1)
  return torch.cat((base, extras), dim=-1)


def go2_source_backflip_observation(
  env: ManagerBasedRlEnv,
  command_name: str = "twist",
  asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
  """Build the 47-D backflip frame (zero phase channels, as in the source)."""
  asset: Entity = env.scene[asset_cfg.name]
  command = env.command_manager.get_command(command_name)
  assert command is not None, f"Command '{command_name}' not found."
  zeros = torch.zeros((command.shape[0], 2), device=command.device, dtype=command.dtype)
  # The source BackFlip observer uses projected gravity (not Euler angles) in
  # its six-dimensional IMU block.  Keep this distinct from Spring-Jump/Trot,
  # whose source observers use Euler XYZ.
  projected_gravity = asset.data.projected_gravity_b
  delayed = _go2_delayed_policy_state(env)
  if delayed is None:
    imu = torch.cat((asset.data.root_link_ang_vel_b * 0.25, projected_gravity), dim=-1)
    q_rel = asset.data.joint_pos - asset.data.default_joint_pos
    joint_vel = asset.data.joint_vel * 0.05
  else:
    q_rel, joint_vel, imu = delayed
  return torch.cat(
    (zeros, command[:, :3], imu, q_rel, joint_vel, env.action_manager.action), dim=-1
  )


def go2_source_backflip_privileged_observation(
  env: ManagerBasedRlEnv,
  command_name: str = "twist",
  asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
  """Build the 50-D backflip privileged frame."""
  asset: Entity = env.scene[asset_cfg.name]
  command = env.command_manager.get_command(command_name)
  assert command is not None, f"Command '{command_name}' not found."
  zeros = torch.zeros((command.shape[0], 2), device=command.device, dtype=command.dtype)
  command_input = torch.cat((zeros, command[:, :3]), dim=-1)
  q_rel = asset.data.joint_pos - asset.data.default_joint_pos
  projected_gravity = asset.data.projected_gravity_b
  return torch.cat(
    (
      command_input,
      q_rel,
      asset.data.joint_vel * 0.05,
      env.action_manager.action,
      asset.data.root_link_lin_vel_b * 2.0,
      asset.data.root_link_ang_vel_b * 0.25,
      projected_gravity,
    ),
    dim=-1,
  )


def go2_source_stand_observation(
  env: ManagerBasedRlEnv,
  command_name: str = "twist",
  asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
  command_first: bool = False,
) -> torch.Tensor:
  """Build a 45-D blind observation.

  The handstand/leggedstand source puts IMU and gravity before the command,
  while CTS/DreamWaQ/TS put the command first.  The switch keeps both legacy
  contracts explicit without duplicating the state assembly.
  """
  asset: Entity = env.scene[asset_cfg.name]
  command = env.command_manager.get_command(command_name)
  assert command is not None, f"Command '{command_name}' not found."
  projected_gravity = asset.data.projected_gravity_b
  command_obs = command[:, :3] * torch.tensor((2.0, 2.0, 0.25), device=env.device)
  delayed = _go2_delayed_policy_state(env)
  if delayed is None:
    imu_obs = asset.data.root_link_ang_vel_b * 0.25
    joint_pos = asset.data.joint_pos - asset.data.default_joint_pos
    joint_vel = asset.data.joint_vel * 0.05
  else:
    joint_pos, joint_vel, delayed_imu = delayed
    imu_obs = delayed_imu[:, :3]
  state = (
    (command_obs, imu_obs, projected_gravity)
    if command_first
    else (imu_obs, projected_gravity, command_obs)
  )
  return torch.cat((*state, joint_pos, joint_vel, env.action_manager.action), dim=-1)


def go2_source_stand_privileged_observation(
  env: ManagerBasedRlEnv,
  command_name: str = "twist",
  sensor_name: str = "feet_ground_contact",
  asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
  """Build the 86-D stand critic frame, reserving randomization fields."""
  asset: Entity = env.scene[asset_cfg.name]
  actor = go2_source_stand_observation(env, command_name, asset_cfg)
  sensor: ContactSensor = env.scene[sensor_name]
  # Source stores 34 domain-randomization scalars followed by four contacts.
  reserved = _go2_stand_randomization_fields(env).to(actor.dtype)
  contact = _go2_source_contact_mask(sensor, threshold=1.0).to(actor.dtype)
  return torch.cat((asset.data.root_link_lin_vel_b, actor, reserved, contact), dim=-1)






def go2_source_spring_jump_observation(
  env: ManagerBasedRlEnv,
  command_name: str = "twist",
  asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
  """Build the 47-D spring-jump frame (zero phase channels)."""
  asset: Entity = env.scene[asset_cfg.name]
  command = env.command_manager.get_command(command_name)
  assert command is not None, f"Command '{command_name}' not found."
  zeros = torch.zeros((command.shape[0], 2), device=command.device, dtype=command.dtype)
  roll, pitch, yaw = euler_xyz_from_quat(asset.data.root_link_quat_w)
  euler_xyz = torch.stack((roll, pitch, yaw), dim=-1)
  delayed = _go2_delayed_policy_state(env)
  if delayed is None:
    imu = torch.cat((asset.data.root_link_ang_vel_b * 0.25, euler_xyz), dim=-1)
    q_rel = asset.data.joint_pos - asset.data.default_joint_pos
    joint_vel = asset.data.joint_vel * 0.05
  else:
    q_rel, joint_vel, imu = delayed
  return torch.cat(
    (
      zeros,
      command[:, :3],
      imu,
      q_rel,
      joint_vel,
      env.action_manager.action,
    ),
    dim=-1,
  )


def go2_source_spring_jump_privileged_observation(
  env: ManagerBasedRlEnv,
  command_name: str = "twist",
  sensor_name: str = "feet_ground_contact",
  asset_cfg: SceneEntityCfg = _DEFAULT_ASSET_CFG,
) -> torch.Tensor:
  """Build the 65-D spring-jump privileged frame."""
  asset: Entity = env.scene[asset_cfg.name]
  command = env.command_manager.get_command(command_name)
  assert command is not None, f"Command '{command_name}' not found."
  sensor: ContactSensor = env.scene[sensor_name]
  contact = _go2_source_contact_mask(sensor, threshold=5.0).to(
    asset.data.joint_pos.dtype
  )
  try:
    command_term = env.command_manager.get_term(command_name)
  except (KeyError, AttributeError):
    command_term = None
  has_jumped = getattr(command_term, "has_jumped", None)
  if has_jumped is None:
    jumped = torch.zeros(
      (command.shape[0], 1), device=command.device, dtype=command.dtype
    )
  else:
    jumped = has_jumped.to(device=command.device, dtype=command.dtype).unsqueeze(-1)
  return torch.cat(
    (
      command[:, :3],
      asset.data.joint_pos - asset.data.default_joint_pos,
      asset.data.joint_pos,
      asset.data.joint_vel * 0.05,
      env.action_manager.action,
      asset.data.root_link_lin_vel_b,
      asset.data.root_link_ang_vel_b * 0.25,
      asset.data.projected_gravity_b,
      contact,
      jumped,
    ),
    dim=-1,
  )


















