"""族级「站姿类」技能内核（handstand / rear_stand 共用）。

来源：`go2_skills/{hand_stand,rear_stand}/mdp/{name}` —— 两包这两份文件**逐字节相同**
（同一上游 `Go2_Trot.py` 系谱），所以它们是**技能内核**而不是机型代码，上移为一份。

去机型化（逐处对应源文件）：
* 源里写死的 `JOINT_NAMES`（12 个 go2 关节）与"关节序不符即抛"的检查 → 族级
  `..mdp.contacts.joint_ids(env)`（**动作项序** = 契约 `action.joint_order`；
  go2 两处同名同序，故解析结果一致）；
* 源里写死的 `SOURCE_FOOT_GEOMS`（4 个 go2 足端几何名）→ 族级足端传感器**本就按契约
  腿序建**，其槽位序与源表同集同序，故重排退化为恒等置换（见 `_foot_order`）。

**口径未动**：帧宽、相位、门控、奖励方程、状态机逐式保留（它们是技能配方）。
"""

from __future__ import annotations

import math

import torch
from mjlab.actuator import IdealPdActuator, XmlActuator
from mjlab.entity import Entity
from mjlab.managers import ObservationTermCfg
from mjlab.sensor import ContactSensor
from mjlab.utils.lab_api.math import euler_xyz_from_quat

from ..mdp.contacts import joint_ids




def _foot_order(sensor: ContactSensor) -> list[int]:
  """足端槽位顺序。

  **族级等价改写**：源实现写死 `("FL_foot_collision", "FR_foot_collision",
  "RL_foot_collision", "RR_foot_collision")` 再去 `primary_names.index(...)` 重排 ——
  而族级足端传感器的 primary 就是按**契约腿序**（`binding.foot_geoms`）建的，
  槽位序与那张表**同集同序**，因此重排是恒等置换。换机型时这里自动跟随契约腿序，
  不再需要一份写死的表。
  """
  names = list(sensor.primary_names)
  if len(names) != 4:
    raise ValueError(f"足端接触传感器应有 4 个槽位，实得 {len(names)}：{names}")
  return list(range(len(names)))

def phase(env, cycle_time: float) -> torch.Tensor:
  return torch.remainder(env.episode_length_buf * env.step_dt, cycle_time) / cycle_time


def phase_command(env, command_name: str, cycle_time: float) -> torch.Tensor:
  gait_phase = phase(env, cycle_time)
  command = env.command_manager.get_command(command_name)
  assert command is not None
  return torch.cat(
    (
      torch.sin(2.0 * math.pi * gait_phase).unsqueeze(1),
      torch.cos(2.0 * math.pi * gait_phase).unsqueeze(1),
      command[:, :2] * 2.0,
      command[:, 2:3] * 0.25,
    ),
    dim=1,
  )




def source_contact(sensor: ContactSensor, threshold: float) -> torch.Tensor:
  """Contacts in source FL, FR, RL, RR order.

  Isaac Gym uses world-frame force Z. The mjlab net-force sensor exposes a
  resultant vector; on this flat task its norm is the stable equivalent.
  """
  force = sensor.data.force
  assert force is not None
  order = _foot_order(sensor)
  return torch.linalg.vector_norm(force[:, order], dim=-1) > threshold


def source_vertical_contact(sensor: ContactSensor, threshold: float) -> torch.Tensor:
  """Isaac Gym-equivalent upward foot force from mjlab's opposite-signed wrench."""
  force = sensor.data.force
  assert force is not None
  order = _foot_order(sensor)
  # With the foot as primary and terrain as secondary, mjlab reports the
  # primary-to-secondary wrench: supporting ground contact therefore has
  # negative world Z. Isaac Gym's rigid-body force uses the opposite sign.
  return -force[:, order, 2] > threshold


def contact_observation(env, sensor_name: str, threshold: float = 5.0) -> torch.Tensor:
  sensor: ContactSensor = env.scene[sensor_name]
  return source_contact(sensor, threshold).float()


def stance_mask(env, cycle_time: float) -> torch.Tensor:
  gait_phase = phase(env, cycle_time)
  return torch.stack((gait_phase < 0.5, gait_phase > 0.5), dim=1).float()


def root_euler(robot: Entity) -> torch.Tensor:
  return torch.stack(euler_xyz_from_quat(robot.data.root_link_quat_w), dim=1)


def actor_frame(env, command_name: str, cycle_time: float) -> torch.Tensor:
  robot: Entity = env.scene["robot"]
  ids = joint_ids(env)
  return torch.cat(
    (
      phase_command(env, command_name, cycle_time),
      robot.data.root_link_ang_vel_b * 0.25,
      root_euler(robot),
      robot.data.joint_pos[:, ids] - robot.data.default_joint_pos[:, ids],
      robot.data.joint_vel[:, ids] * 0.05,
      env.action_manager.action,
    ),
    dim=1,
  )


def critic_frame(
  env, command_name: str, sensor_name: str, cycle_time: float
) -> torch.Tensor:
  robot: Entity = env.scene["robot"]
  ids = joint_ids(env)
  return torch.cat(
    (
      phase_command(env, command_name, cycle_time),
      robot.data.joint_pos[:, ids] - robot.data.default_joint_pos[:, ids],
      robot.data.joint_pos[:, ids],
      robot.data.joint_vel[:, ids] * 0.05,
      env.action_manager.action,
      robot.data.root_link_lin_vel_b * 2.0,
      robot.data.root_link_ang_vel_b * 0.25,
      root_euler(robot),
      stance_mask(env, cycle_time),
      contact_observation(env, sensor_name),
    ),
    dim=1,
  )


class _SourceHistory:
  """Frame-major, oldest-to-newest history with source-style zero reset."""

  frame_dim: int
  history_length: int

  def __init__(self, cfg: ObservationTermCfg, env) -> None:
    del cfg
    self._history = torch.zeros(
      env.num_envs, self.history_length, self.frame_dim, device=env.device
    )

  def _append(self, frame: torch.Tensor) -> torch.Tensor:
    self._history = torch.roll(self._history, shifts=-1, dims=1)
    self._history[:, -1] = frame
    return self._history.reshape(frame.shape[0], -1)

  def reset(self, env_ids=None) -> None:
    self._history[env_ids] = 0.0


class TrotActorHistory(_SourceHistory):
  frame_dim = 47
  history_length = 10

  def __call__(
    self, env, command_name: str, cycle_time: float, add_noise: bool
  ) -> torch.Tensor:
    frame = actor_frame(env, command_name, cycle_time)
    if add_noise:
      _, upper = single_frame_noise_bounds()
      amplitude = torch.tensor(upper, device=env.device)
      frame = frame + (2.0 * torch.rand_like(frame) - 1.0) * amplitude
    return self._append(frame)


class TrotCriticHistory(_SourceHistory):
  frame_dim = 68
  history_length = 3

  def __call__(
    self, env, command_name: str, sensor_name: str, cycle_time: float
  ) -> torch.Tensor:
    return self._append(critic_frame(env, command_name, sensor_name, cycle_time))


def jump_phase(env, cycle_time: float) -> torch.Tensor:
  """Unwrapped source Jump phase (the stance transition happens only once)."""
  return env.episode_length_buf * env.step_dt / cycle_time


def jump_stance_mask(env, cycle_time: float) -> torch.Tensor:
  gait_phase = jump_phase(env, cycle_time)
  return torch.stack((gait_phase < 0.6, gait_phase > 0.6), dim=1).float()


def jump_phase_command(env, command_name: str, cycle_time: float) -> torch.Tensor:
  gait_phase = jump_phase(env, cycle_time)
  command = env.command_manager.get_command(command_name)
  assert command is not None
  return torch.cat(
    (
      torch.sin(2.0 * math.pi * gait_phase).unsqueeze(1),
      torch.cos(2.0 * math.pi * gait_phase).unsqueeze(1),
      command[:, :2] * 2.0,
      command[:, 2:3] * 0.25,
    ),
    dim=1,
  )


def jump_actor_frame(env, command_name: str, cycle_time: float) -> torch.Tensor:
  robot: Entity = env.scene["robot"]
  ids = joint_ids(env)
  return torch.cat(
    (
      jump_phase_command(env, command_name, cycle_time),
      robot.data.root_link_ang_vel_b * 0.25,
      root_euler(robot),
      robot.data.joint_pos[:, ids] - robot.data.default_joint_pos[:, ids],
      robot.data.joint_vel[:, ids] * 0.05,
      env.action_manager.action,
    ),
    dim=1,
  )


def jump_critic_frame(
  env, command_name: str, sensor_name: str, cycle_time: float
) -> torch.Tensor:
  robot: Entity = env.scene["robot"]
  ids = joint_ids(env)
  sensor: ContactSensor = env.scene[sensor_name]
  # The source samples one friction bucket per environment and applies it to all
  # robot shapes. Reading the first robot geom therefore recovers the label.
  friction = robot.data.model.geom_friction[:, robot.indexing.geom_ids[0], 0].unsqueeze(
    1
  )
  # Go2_Jump allocates body_mass but never writes to it; its critic observes zero.
  source_body_mass = torch.zeros((env.num_envs, 1), device=env.device)
  return torch.cat(
    (
      jump_phase_command(env, command_name, cycle_time),
      robot.data.joint_pos[:, ids] - robot.data.default_joint_pos[:, ids],
      robot.data.joint_pos[:, ids],
      robot.data.joint_vel[:, ids] * 0.05,
      env.action_manager.action,
      robot.data.root_link_lin_vel_b * 2.0,
      robot.data.root_link_ang_vel_b * 0.25,
      root_euler(robot),
      friction,
      source_body_mass,
      jump_stance_mask(env, cycle_time),
      source_vertical_contact(sensor, 5.0).float(),
    ),
    dim=1,
  )


class JumpActorHistory(_SourceHistory):
  frame_dim = 47
  history_length = 10

  def __call__(
    self, env, command_name: str, cycle_time: float, add_noise: bool
  ) -> torch.Tensor:
    frame = jump_actor_frame(env, command_name, cycle_time)
    if add_noise:
      _, upper = single_frame_noise_bounds()
      amplitude = torch.tensor(upper, device=env.device)
      frame = frame + (2.0 * torch.rand_like(frame) - 1.0) * amplitude
    return self._append(frame)


class JumpCriticHistory(_SourceHistory):
  frame_dim = 70
  history_length = 3

  def __call__(
    self, env, command_name: str, sensor_name: str, cycle_time: float
  ) -> torch.Tensor:
    return self._append(jump_critic_frame(env, command_name, sensor_name, cycle_time))


def rear_stand_noise_bounds() -> tuple[tuple[float, ...], tuple[float, ...]]:
  amplitudes = (
    [0.2 * 0.25] * 3
    + [0.05] * 3
    + [0.0] * 3
    + [0.01] * 12
    + [1.5 * 0.05] * 12
    + [0.0] * 12
  )
  return tuple(-value for value in amplitudes), tuple(amplitudes)


def _stand_actor_frame(
  env,
  command_name: str,
  add_noise: bool,
  cache_attribute: str,
  constant_prefix_dim: int = 0,
) -> torch.Tensor:
  robot: Entity = env.scene["robot"]
  ids = joint_ids(env)
  command = env.command_manager.get_command(command_name)
  assert command is not None
  frame = torch.cat(
    (
      robot.data.root_link_ang_vel_b * 0.25,
      robot.data.projected_gravity_b,
      command[:, :2] * 2.0,
      command[:, 2:3] * 0.25,
      robot.data.joint_pos[:, ids] - robot.data.default_joint_pos[:, ids],
      robot.data.joint_vel[:, ids] * 0.05,
      env.action_manager.action,
    ),
    dim=1,
  )
  if constant_prefix_dim:
    frame = torch.cat(
      (torch.zeros((env.num_envs, constant_prefix_dim), device=env.device), frame),
      dim=1,
    )
  if add_noise:
    _, upper = rear_stand_noise_bounds()
    amplitude = torch.tensor((0.0,) * constant_prefix_dim + upper, device=env.device)
    frame = frame + (2.0 * torch.rand_like(frame) - 1.0) * amplitude
  # The Gym critic concatenates the exact already-corrupted actor frame.
  setattr(env, cache_attribute, frame)
  return frame


def rear_stand_actor_frame(env, command_name: str, add_noise: bool) -> torch.Tensor:
  return _stand_actor_frame(env, command_name, add_noise, "_rear_stand_actor_frame")


def handstand_actor_frame(env, command_name: str, add_noise: bool) -> torch.Tensor:
  # The successful bundled Gym policy was trained before these legacy fields
  # were deleted: zeros(2) + stand_command(1). stand_command was initialized to
  # zero and never written, so all three inputs are constant zeros.
  return _stand_actor_frame(
    env,
    command_name,
    add_noise,
    "_handstand_actor_frame",
    constant_prefix_dim=3,
  )


def handstand_noise_bounds() -> tuple[tuple[float, ...], tuple[float, ...]]:
  lower, upper = rear_stand_noise_bounds()
  return (0.0, 0.0, 0.0) + lower, (0.0, 0.0, 0.0) + upper


def rear_stand_domain_randomization_info(
  env,
  restitution_attribute: str = "_rear_stand_restitution",
  joint_friction_attribute: str | None = None,
  joint_damping_attribute: str | None = None,
  foot_geom: str | None = None,
  root_body: str | None = None,
) -> torch.Tensor:
  """The source's 34 privileged domain-randomization labels, in source order.

  `foot_geom` / `root_body` 由技能配置从**绑定**派生传入（源实现写死 go2 的名字）；
  帧宽与项序不变 —— 只把"读哪一个足端几何 / 根 body"变成数据。
  """
  robot: Entity = env.scene["robot"]
  ids = joint_ids(env)

  if not foot_geom or not root_body:
    raise ValueError(
      "域随机化观测需要足端几何名与根 body 名（由 stance/config 从绑定派生传入）"
    )

  foot_geom_ids, foot_names = robot.find_geoms((foot_geom,), preserve_order=True)
  if tuple(foot_names) != (foot_geom,):
    raise RuntimeError(f"foot geom lookup mismatch: {foot_names}")
  friction_id = robot.indexing.geom_ids[foot_geom_ids[0]]
  friction = robot.data.model.geom_friction[:, friction_id, 0:1]

  base_ids, base_names = robot.find_bodies((root_body,), preserve_order=True)
  if tuple(base_names) != (root_body,):
    raise RuntimeError(f"base lookup mismatch: {base_names}")
  base_id = robot.indexing.body_ids[base_ids[0]]
  default_mass = env.sim.get_default_field("body_mass")[base_id]
  added_mass = robot.data.model.body_mass[:, base_id : base_id + 1] - default_mass
  default_ipos = env.sim.get_default_field("body_ipos")[base_id]
  added_com = robot.data.model.body_ipos[:, base_id] - default_ipos

  kp_multiplier = torch.zeros((env.num_envs, len(ids)), device=env.device)
  kd_multiplier = torch.zeros_like(kp_multiplier)
  for actuator in robot.actuators:
    # 增益倍率的**真值位置**按执行器种类分：`IdealPdActuator` 的 PD 律由它自己算
    # （`pd_gains` 改的就是它自己的张量）；MJCF 包装的 position 执行器则由 `pd_gains`
    # 直接写进模型的 `gainprm/biasprm`。两种各读各自的那一处，不猜也不换算。
    if isinstance(actuator, IdealPdActuator):
      assert actuator.stiffness is not None
      assert actuator.damping is not None
      assert actuator.default_stiffness is not None
      assert actuator.default_damping is not None
      kp_multiplier[:, actuator.target_ids] = (
        actuator.stiffness / actuator.default_stiffness
      )
      kd_multiplier[:, actuator.target_ids] = (
        actuator.damping / actuator.default_damping
      )
      continue
    if isinstance(actuator, XmlActuator) and actuator.command_field == "position":
      ctrl = actuator.global_ctrl_ids
      kp_multiplier[:, actuator.target_ids] = (
        env.sim.model.actuator_gainprm[:, ctrl, 0]
        / env.sim.get_default_field("actuator_gainprm")[ctrl, 0]
      )
      kd_multiplier[:, actuator.target_ids] = (
        env.sim.model.actuator_biasprm[:, ctrl, 2]
        / env.sim.get_default_field("actuator_biasprm")[ctrl, 2]
      )
      continue
    raise TypeError(
      f"站姿类域随机化观测不支持执行器类型 {type(actuator).__name__}"
      "（需 IdealPdActuator 或 MJCF position 包装的 XmlActuator）"
    )

  dof_ids = robot.indexing.joint_v_adr[ids]
  armature = robot.data.model.dof_armature[:, dof_ids[0] : dof_ids[0] + 1]
  joint_friction = robot.data.model.dof_frictionloss[:, dof_ids[0] : dof_ids[0] + 1]
  joint_damping = robot.data.model.dof_damping[:, dof_ids[0] : dof_ids[0] + 1]
  if joint_friction_attribute is not None:
    joint_friction = getattr(env, joint_friction_attribute, joint_friction)
  if joint_damping_attribute is not None:
    joint_damping = getattr(env, joint_damping_attribute, joint_damping)
  restitution = getattr(env, restitution_attribute, None)
  if restitution is None:
    restitution = torch.zeros((env.num_envs, 1), device=env.device)

  return torch.cat(
    (
      friction,
      added_mass,
      added_com,
      kp_multiplier,
      kd_multiplier,
      armature,
      joint_friction,
      joint_damping,
      restitution,
      restitution,
    ),
    dim=1,
  )


class RearStandActorObservation:
  frame_dim = 45
  history_length = 1

  def __init__(self, cfg: ObservationTermCfg, env) -> None:
    del cfg, env

  def __call__(self, env, command_name: str, add_noise: bool) -> torch.Tensor:
    return rear_stand_actor_frame(env, command_name, add_noise)

  def reset(self, env_ids=None) -> None:
    del env_ids


class RearStandCriticObservation:
  frame_dim = 86
  history_length = 1

  def __init__(self, cfg: ObservationTermCfg, env) -> None:
    del cfg, env

  def __call__(
    self, env, sensor_name: str, foot_geom: str, root_body: str
  ) -> torch.Tensor:
    robot: Entity = env.scene["robot"]
    actor_frame = getattr(env, "_rear_stand_actor_frame", None)
    if actor_frame is None:
      raise RuntimeError("Rear Stand actor observation must be computed before critic")
    sensor: ContactSensor = env.scene[sensor_name]
    return torch.cat(
      (
        robot.data.root_link_lin_vel_b * 2.0,
        actor_frame,
        rear_stand_domain_randomization_info(
          env, foot_geom=foot_geom, root_body=root_body
        ),
        source_vertical_contact(sensor, 1.0).float(),
      ),
      dim=1,
    )

  def reset(self, env_ids=None) -> None:
    del env_ids


class HandstandActorObservation:
  frame_dim = 48
  history_length = 1

  def __init__(self, cfg: ObservationTermCfg, env) -> None:
    del cfg, env

  def __call__(self, env, command_name: str, add_noise: bool) -> torch.Tensor:
    return handstand_actor_frame(env, command_name, add_noise)

  def reset(self, env_ids=None) -> None:
    del env_ids


class HandstandCriticObservation:
  frame_dim = 89
  history_length = 1

  def __init__(self, cfg: ObservationTermCfg, env) -> None:
    del cfg, env

  def __call__(
    self, env, sensor_name: str, foot_geom: str, root_body: str
  ) -> torch.Tensor:
    robot: Entity = env.scene["robot"]
    actor_frame = getattr(env, "_handstand_actor_frame", None)
    if actor_frame is None:
      raise RuntimeError("Handstand actor observation must be computed before critic")
    sensor: ContactSensor = env.scene[sensor_name]
    return torch.cat(
      (
        robot.data.root_link_lin_vel_b * 2.0,
        actor_frame,
        rear_stand_domain_randomization_info(
          env,
          "_handstand_restitution",
          "_handstand_joint_friction",
          "_handstand_joint_damping",
          foot_geom=foot_geom,
          root_body=root_body,
        ),
        source_vertical_contact(sensor, 1.0).float(),
      ),
      dim=1,
    )

  def reset(self, env_ids=None) -> None:
    del env_ids


def single_frame_noise_bounds() -> tuple[tuple[float, ...], tuple[float, ...]]:
  amplitudes = (
    [0.0] * 5
    + [0.2 * 0.25] * 3
    + [0.1] * 3
    + [0.01] * 12
    + [1.5 * 0.05] * 12
    + [0.0] * 12
  )
  return tuple(-value for value in amplitudes), tuple(amplitudes)
