"""Serializable state exchanged by backend adapters and Viser."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class SceneFrame:
    """One normalized robot state at a policy/control timestamp."""

    robot: str
    joint_order: tuple[str, ...]
    root_position: tuple[float, float, float]
    root_orientation: tuple[float, float, float, float]
    joint_position: tuple[float, ...]
    joint_velocity: tuple[float, ...]
    command: tuple[float, ...]
    reward: float
    timestamp: float = 0.0
    contacts: tuple[str, ...] = ()
    metrics: Mapping[str, float] = field(default_factory=dict)
    schema_version: int = 1

    def __post_init__(self) -> None:
        if len(self.joint_order) != len(self.joint_position):
            raise ValueError("joint_order and joint_position must have equal length")
        if len(self.joint_order) != len(self.joint_velocity):
            raise ValueError("joint_order and joint_velocity must have equal length")
        if len(self.root_position) != 3 or len(self.root_orientation) != 4:
            raise ValueError("root pose must be xyz position and wxyz orientation")
        if not self.robot:
            raise ValueError("robot must be non-empty")
        object.__setattr__(self, "metrics", dict(self.metrics))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TrainingFrame:
    """Normalized training metrics accompanying a scene frame."""

    backend: str
    task: str
    step: int
    metrics: Mapping[str, float] = field(default_factory=dict)
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not self.backend or not self.task:
            raise ValueError("backend and task must be non-empty")
        object.__setattr__(self, "metrics", dict(self.metrics))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
