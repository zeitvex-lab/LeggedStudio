"""Shared DeepRobotics M20 task helpers.

Robot-specific joint naming, contact patterns, and asset selection live here
so the active M20 task builders stay easy to read without mutating other
robots' code.
"""

from __future__ import annotations

from collections.abc import Sequence

from .m20_constants import (
  M20_LEG_JOINT_NAMES,
  M20_WHEEL_JOINT_NAMES,
  get_m20_robot_cfg,
)
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.sensor import ContactMatch, ContactSensorCfg


def get_m20_scene_robot_cfg():
  """Return the vendored M20 robot asset config."""
  return get_m20_robot_cfg()


def m20_leg_joint_cfg() -> SceneEntityCfg:
  """Leg joints in the canonical M20 order."""
  return SceneEntityCfg(
    "robot",
    joint_names=M20_LEG_JOINT_NAMES,
    preserve_order=True,
  )


def m20_wheel_joint_cfg() -> SceneEntityCfg:
  """Wheel joints in the canonical M20 order."""
  return SceneEntityCfg(
    "robot",
    joint_names=M20_WHEEL_JOINT_NAMES,
    preserve_order=True,
  )


def m20_wheel_ground_contact_cfg(
  *,
  name: str = "wheel_ground_contact",
  pattern: str = r".*(fr|fl|hr|hl)_wheel.*",
  fields: Sequence[str] = ("found", "force"),
  reduce: str = "none",
  num_slots: int = 1,
  track_air_time: bool = False,
) -> ContactSensorCfg:
  """Wheel terrain contact sensor used by M20 locomotion tasks."""
  return ContactSensorCfg(
    name=name,
    primary=ContactMatch(
      mode="body",
      pattern=pattern,
      entity="robot",
    ),
    secondary=ContactMatch(mode="body", pattern="terrain"),
    fields=tuple(fields),
    reduce=reduce,
    num_slots=num_slots,
    track_air_time=track_air_time,
  )
