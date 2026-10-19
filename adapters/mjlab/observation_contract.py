"""Canonical actor observation layout for generic tasks and parity audits.

The family declaration (``registry/families/*.json``) is the source of truth.
This module only carries the default fallback used when a contract does not
declare ``observation.components``.  It deliberately has no mjlab/torch import
so control-plane audits can compare it with the family skeletons.
"""

from __future__ import annotations

DEFAULT_ACTOR_TERMS: tuple[str, ...] = (
    "base_ang_vel",
    "projected_gravity",
    "commands",
    "joint_pos",
    "joint_vel",
    "last_action",
)

CRITIC_ONLY_TERMS: tuple[str, ...] = ("base_lin_vel",)


def expected_actor_width(joint_count: int, command_dims: int = 3) -> int:
    """Width for ``ang_vel + gravity + command + q + dq + last_action``."""
    if joint_count <= 0:
        raise ValueError("joint_count must be positive")
    if command_dims <= 0:
        raise ValueError("command_dims must be positive")
    return 3 + 3 + command_dims + 3 * joint_count
