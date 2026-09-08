"""Unitree G1 motion-tracking environment configurations."""

import os

from mjlab.envs import ManagerBasedRlEnvCfg

from src.tasks.tracking.tracking_env_cfg import make_tracking_env_cfg

# Reference motion pkls (LeggedGym-Ex retarget, BSD-3-Clause), copied into
# the package at assets/motions/g1/tracking/.
_MOTION_DIR = os.path.abspath(
  os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..", "..", "..",
    "assets", "motions", "g1", "tracking",
  )
)


def g1_tracking_flat_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
  """Create the Unitree G1 flat-terrain motion-tracking configuration."""
  cfg = make_tracking_env_cfg(_MOTION_DIR)
  if play:
    cfg.episode_length_s = int(1e9)
    cfg.observations["actor"].enable_corruption = False
    cfg.events.pop("push_robot", None)
  return cfg
