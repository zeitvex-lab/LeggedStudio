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
