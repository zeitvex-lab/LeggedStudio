"""DreamWaQ M20 perturbation events."""

import torch

from mjlab.entity import Entity
from mjlab.envs.mdp.events import resolve_env_ids


def overwrite_base_velocity(
  env,
  env_ids,
  max_push_vel_xy: float,
) -> None:
  """Source ``_push_robots``: overwrite the base xy velocity (no z/angular)."""
  ids = resolve_env_ids(env, env_ids)
  robot: Entity = env.scene["robot"]
  velocity = robot.data.root_link_vel_w[ids].clone()
  velocity[:, :2].uniform_(-max_push_vel_xy, max_push_vel_xy)
  robot.write_root_link_velocity_to_sim(velocity, env_ids=ids)


def scale_leg_pd_gains(
  env,
  env_ids=None,
  kp_range: tuple[float, float] = (0.85, 1.15),
  kd_range: tuple[float, float] = (0.85, 1.15),
) -> None:
  """Scale kp/kd on position-mode actuators only (velocity wheels excluded)."""
  import torch
  from mjlab.actuator.builtin_actuator import BuiltinPositionActuator

  if env_ids is None:
    env_ids = torch.arange(env.num_envs, device=env.device, dtype=torch.int)
  else:
    env_ids = env_ids.to(env.device, dtype=torch.int)

  robot: Entity = env.scene["robot"]
  default_gainprm = env.sim.get_default_field("actuator_gainprm")
  default_biasprm = env.sim.get_default_field("actuator_biasprm")
  for actuator in robot.actuators:
    if not isinstance(actuator, BuiltinPositionActuator):
      continue  # velocity-mode wheel actuators carry no kp/kd
    ctrl = actuator.global_ctrl_ids
    n = len(ctrl)
    kp = torch.rand(len(env_ids), n, device=env.device) * (kp_range[1] - kp_range[0]) + kp_range[0]
    kd = torch.rand(len(env_ids), n, device=env.device) * (kd_range[1] - kd_range[0]) + kd_range[0]
    env.sim.model.actuator_gainprm[env_ids[:, None], ctrl, 0] = default_gainprm[ctrl, 0] * kp
    env.sim.model.actuator_biasprm[env_ids[:, None], ctrl, 1] = default_biasprm[ctrl, 1] * kp
    env.sim.model.actuator_biasprm[env_ids[:, None], ctrl, 2] = default_biasprm[ctrl, 2] * kd


def scale_leg_effort_limits(
  env,
  env_ids=None,
  effort_limit_range: tuple[float, float] = (0.85, 1.15),
) -> None:
  """Scale effort limits on position-mode actuators only (wheels excluded)."""
  import torch
  from mjlab.actuator.builtin_actuator import BuiltinPositionActuator

  if env_ids is None:
    env_ids = torch.arange(env.num_envs, device=env.device, dtype=torch.int)
  else:
    env_ids = env_ids.to(env.device, dtype=torch.int)

  robot: Entity = env.scene["robot"]
  default_forcerange = env.sim.get_default_field("actuator_forcerange")
  for actuator in robot.actuators:
    if not isinstance(actuator, BuiltinPositionActuator):
      continue
    ctrl = actuator.global_ctrl_ids
    n = len(ctrl)
    effort = (
      torch.rand(len(env_ids), n, device=env.device)
      * (effort_limit_range[1] - effort_limit_range[0])
      + effort_limit_range[0]
    )
    env.sim.model.actuator_forcerange[env_ids[:, None], ctrl, 0] = (
      default_forcerange[ctrl, 0] * effort
    )
    env.sim.model.actuator_forcerange[env_ids[:, None], ctrl, 1] = (
      default_forcerange[ctrl, 1] * effort
    )
