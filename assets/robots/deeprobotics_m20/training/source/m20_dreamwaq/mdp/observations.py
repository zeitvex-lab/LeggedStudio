"""Field-for-field DreamWaQ M20 observations and source-style histories.

Actor frame (57, source ``compute_observations``):

    [cmd(3) * (2, 2, 0.25), ang_vel_b * 0.25, projected_gravity,
     joint_pos - default (wheel slots zeroed), joint_vel * 0.05, raw action]

Joint slots follow the package contract order: 12 legs
(fl/fr/hl/hr x hipx/hipy/knee) then 4 wheels (fl/fr/hl/hr).  The IsaacGym
source interleaved one wheel slot per leg; the mjlab task is self-consistent
in the contract order (the source order only matters for weight transfer,
which this retraining task does not perform).
"""

import torch

from mjlab.entity import Entity
from mjlab.managers import ObservationTermCfg

from ..constants import (
  ANG_VEL_SCALE,
  DOF_VEL_SCALE,
  LIN_VEL_SCALE,
  M20_ALL_JOINT_NAMES,
  M20_LEG_JOINT_NAMES,
  OBS_NOISE_ANG_VEL,
  OBS_NOISE_DOF_POS,
  OBS_NOISE_DOF_VEL,
  OBS_NOISE_GRAVITY,
)

_FRAME_DIM = 57


def _joint_ids(robot: Entity) -> list[int]:
  ids, names = robot.find_joints(M20_ALL_JOINT_NAMES, preserve_order=True)
  if tuple(names) != M20_ALL_JOINT_NAMES:
    raise RuntimeError(f"M20 joint order mismatch: {names}")
  return ids


def _wheel_slot_count(robot: Entity) -> int:
  """Number of trailing wheel slots in the contract joint order."""
  leg_ids, _ = robot.find_joints(M20_LEG_JOINT_NAMES, preserve_order=True)
  all_ids = _joint_ids(robot)
  return len(all_ids) - len(leg_ids)


def _command(env, command_name: str) -> torch.Tensor:
  command = env.command_manager.get_command(command_name)
  assert command is not None
  return command[:, :3]


def _actor_frame(env, command_name: str) -> torch.Tensor:
  """Clean (noise-free) 57-field actor frame."""
  robot: Entity = env.scene["robot"]
  ids = _joint_ids(robot)
  command_scale = torch.tensor(
    (LIN_VEL_SCALE, LIN_VEL_SCALE, ANG_VEL_SCALE), device=env.device
  )
  joint_pos_err = robot.data.joint_pos[:, ids] - robot.data.default_joint_pos[:, ids]
  joint_pos_err[:, -_wheel_slot_count(robot):] = 0.0
  return torch.cat(
    (
      _command(env, command_name) * command_scale,
      robot.data.root_link_ang_vel_b * ANG_VEL_SCALE,
      robot.data.projected_gravity_b,
      joint_pos_err,
      robot.data.joint_vel[:, ids] * DOF_VEL_SCALE,
      env.action_manager.action,
    ),
    dim=1,
  )


def _noise(frame: torch.Tensor, num_leg_joints: int = 12) -> torch.Tensor:
  amplitude = torch.tensor(
    [0.0] * 3
    + [OBS_NOISE_ANG_VEL] * 3
    + [OBS_NOISE_GRAVITY] * 3
    + [OBS_NOISE_DOF_POS] * 16
    + [OBS_NOISE_DOF_VEL] * 16
    + [0.0] * 16,
    device=frame.device,
    dtype=frame.dtype,
  )
  return frame + (2.0 * torch.rand_like(frame) - 1.0) * amplitude


class DreamActor:
  """Current 57-field actor input, retained for the delayed VAE history."""

  def __init__(self, cfg: ObservationTermCfg, env) -> None:
    del cfg
    self._current = torch.zeros((env.num_envs, _FRAME_DIM), device=env.device)
    # Observation terms are constructed before ObservationManager is attached.
    # Share the previous actor frame through the environment instead.
    env._m20_dreamwaq_actor_term = self

  def __call__(
    self,
    env,
    command_name: str,
    add_noise: bool,
  ) -> torch.Tensor:
    frame = _actor_frame(env, command_name)
    self._current.copy_(_noise(frame) if add_noise else frame)
    return self._current

  def reset(self, env_ids=None) -> None:
    self._current[env_ids] = 0.0


class DreamActorHistory:
  """Five source frames immediately preceding the actor frame, oldest first."""

  def __init__(self, cfg: ObservationTermCfg, env) -> None:
    del cfg
    self._history = torch.zeros((env.num_envs, 5, _FRAME_DIM), device=env.device)

  def __call__(self, env) -> torch.Tensor:
    # The Gym code shifts ``obs_hist_buf`` before constructing this step's
    # ``obs_buf``; use the actor term from the prior manager evaluation.
    output = self._history.reshape(env.num_envs, -1).clone()
    actor = env._m20_dreamwaq_actor_term
    assert isinstance(actor, DreamActor)
    self._history = torch.roll(self._history, shifts=-1, dims=1)
    self._history[:, -1] = actor._current
    return output

  def reset(self, env_ids=None) -> None:
    self._history[env_ids] = 0.0


class DreamCritic:
  """Single 247-field privileged frame matching the source layout.

  [base_lin_vel * 2.0 (3), height scan (187), clean actor frame (57)];
  the source adds noise to the actor buffer only after building the
  privileged observation, so the critic frame stays noise-free.
  """

  def __call__(self, env, command_name: str, sensor_name: str) -> torch.Tensor:
    robot: Entity = env.scene["robot"]
    scan = env.scene[sensor_name].data
    # Source height encoding: clip(base_z - 0.5 - terrain_height, -1, 1) * 5.
    heights = torch.clamp(
      scan.frame_pos_w[:, 0, 2:3] - 0.5 - scan.hit_pos_w[..., 2], -1.0, 1.0
    ) * 5.0
    frame = torch.cat(
      (
        robot.data.root_link_lin_vel_b * LIN_VEL_SCALE,
        heights,
        _actor_frame(env, command_name),
      ),
      dim=1,
    )
    assert frame.shape[1] == 247, frame.shape
    return frame


def base_linear_velocity(env) -> torch.Tensor:
  """VAE explicit-velocity label (source ``vel_buf`` = base_lin_vel)."""
  return env.scene["robot"].data.root_link_lin_vel_b
