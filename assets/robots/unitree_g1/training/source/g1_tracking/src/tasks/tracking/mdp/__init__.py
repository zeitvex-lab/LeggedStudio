"""MDP terms for the motion-tracking task."""

from src.tasks.tracking.mdp.events import (
  init_tracking_motion,
  reset_from_reference_motion,
)
from src.tasks.tracking.mdp.observations import (
  ref_base_ang_vel_b,
  ref_base_lin_vel_b,
  ref_base_quat,
  ref_dof_pos,
  ref_dof_vel,
)
from src.tasks.tracking.mdp.rewards import (
  tracking_ref_base_pose,
  tracking_ref_base_vel,
  tracking_ref_dof_pos,
  tracking_ref_dof_vel,
  tracking_ref_key_pos,
)

__all__ = [
  "init_tracking_motion",
  "reset_from_reference_motion",
  "ref_base_ang_vel_b",
  "ref_base_lin_vel_b",
  "ref_base_quat",
  "ref_dof_pos",
  "ref_dof_vel",
  "tracking_ref_base_pose",
  "tracking_ref_base_vel",
  "tracking_ref_dof_pos",
  "tracking_ref_dof_vel",
  "tracking_ref_key_pos",
]
