"""Data container for articulation joint actions.

This module provides the ArticulationActions class, which is used to pass
joint commands (positions, velocities, efforts) to actuator models.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import torch


@dataclass
class ArticulationActions:
    """Data container to store articulation joint actions.

    This mirrors IsaacLab's ``ArticulationActions`` but is defined in the
    GenesisLab namespace so that actuator code does not depend on IsaacLab.

    Attributes:
        joint_positions: Desired joint positions. Shape: (num_envs, num_joints).
        joint_velocities: Desired joint velocities. Shape: (num_envs, num_joints).
        joint_efforts: Desired joint efforts (torques/forces). Shape: (num_envs, num_joints).
        joint_indices: Optional joint indices for partial control. Can be a tensor,
            sequence of integers, or slice.
    """

    joint_positions: torch.Tensor = None
    """Desired joint positions. Shape: (num_envs, num_joints)."""

    joint_velocities: torch.Tensor = None
    """Desired joint velocities. Shape: (num_envs, num_joints)."""

    joint_efforts: torch.Tensor = None
    """Desired joint efforts (torques/forces). Shape: (num_envs, num_joints)."""

    joint_indices: torch.Tensor | Sequence[int] | slice = None
    """Optional joint indices for partial control."""


__all__ = ["ArticulationActions"]
