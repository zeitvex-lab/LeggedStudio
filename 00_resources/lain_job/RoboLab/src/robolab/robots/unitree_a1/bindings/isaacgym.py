"""Isaac Gym binding metadata for the Unitree A1 velocity task."""

from __future__ import annotations

from pathlib import Path

from robolab.robots.unitree_a1.spec import ACTION, CONTROL_DT, UNITREE_A1_JOINT_ORDER


def canonical_urdf(repository_root: Path) -> Path:
    """Return the one RoboLab-tracked A1 URDF used by the Isaac Gym bundle."""

    return repository_root / "resources/robots/unitree_a1/urdf/unitree_a1.urdf"


__all__ = ["ACTION", "CONTROL_DT", "UNITREE_A1_JOINT_ORDER", "canonical_urdf"]
