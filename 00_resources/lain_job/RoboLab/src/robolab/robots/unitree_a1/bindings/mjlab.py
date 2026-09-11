"""MJLab binding metadata for the canonical Unitree A1 MJCF."""

from __future__ import annotations

from pathlib import Path

from robolab.robots.unitree_a1.spec import ACTION, CONTROL_DT, UNITREE_A1_JOINT_ORDER


def canonical_mjcf(repository_root: Path) -> Path:
    """Return the one RoboLab-tracked A1 MJCF used by MJLab."""

    return repository_root / "resources/robots/unitree_a1/xml/unitree_a1.xml"


def build_spec(repository_root: Path):
    """Load the canonical A1 MJCF lazily inside the MJLab environment."""

    import mujoco

    return mujoco.MjSpec.from_file(str(canonical_mjcf(repository_root)))


A1_BODY_NAME = "robot"
A1_FOOT_BODY_NAMES = ("FL_calf", "FR_calf", "RL_calf", "RR_calf")
A1_DEFAULT_JOINT_POSITIONS = {
    "FL_hip_joint": 0.1,
    "RL_hip_joint": 0.1,
    "FR_hip_joint": -0.1,
    "RR_hip_joint": -0.1,
    "FL_thigh_joint": 0.8,
    "RL_thigh_joint": 1.0,
    "FR_thigh_joint": 0.8,
    "RR_thigh_joint": 1.0,
    "FL_calf_joint": -1.5,
    "RL_calf_joint": -1.5,
    "FR_calf_joint": -1.5,
    "RR_calf_joint": -1.5,
}

__all__ = [
    "A1_BODY_NAME",
    "A1_DEFAULT_JOINT_POSITIONS",
    "A1_FOOT_BODY_NAMES",
    "ACTION",
    "CONTROL_DT",
    "UNITREE_A1_JOINT_ORDER",
    "build_spec",
    "canonical_mjcf",
]
