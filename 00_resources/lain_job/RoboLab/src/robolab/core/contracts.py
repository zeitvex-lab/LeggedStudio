"""Small, serializable contracts shared by training framework adapters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any


def _require_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True)
class TensorContract:
    """Shape and semantic identity of one policy input/output tensor."""

    name: str
    shape: tuple[int, ...]
    dtype: str = "float32"
    semantics: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _require_identifier(self.name, "name"))
        if any(not isinstance(dim, int) or dim < 0 for dim in self.shape):
            raise ValueError("shape dimensions must be non-negative integers")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Recipe:
    """A reproducible Robot + Task + Method + Framework selection."""

    robot: str
    task: str
    method: str
    framework: str
    seed: int = 0
    overrides: Mapping[str, Any] = field(default_factory=dict)
    robot_profile: str | None = None
    joint_mapping: Mapping[str, Any] = field(default_factory=dict)
    control: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("robot", "task", "method", "framework"):
            object.__setattr__(
                self, name, _require_identifier(getattr(self, name), name)
            )
        if not isinstance(self.seed, int):
            raise TypeError("seed must be an integer")
        object.__setattr__(self, "overrides", dict(self.overrides))
        if self.robot_profile is not None:
            object.__setattr__(self, "robot_profile", str(self.robot_profile))
        object.__setattr__(self, "joint_mapping", dict(self.joint_mapping))
        object.__setattr__(self, "control", dict(self.control))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PolicyArtifact:
    """Manifest for a policy that can be validated outside its training backend."""

    policy_path: str
    robot: str
    task: str
    method: str
    framework: str
    observation: TensorContract
    action: TensorContract
    control_dt: float
    joint_order: tuple[str, ...]
    schema_version: int = 1
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.policy_path:
            raise ValueError("policy_path must be non-empty")
        for name in ("robot", "task", "method", "framework"):
            object.__setattr__(
                self, name, _require_identifier(getattr(self, name), name)
            )
        if self.control_dt <= 0:
            raise ValueError("control_dt must be positive")
        if not self.joint_order or any(
            not isinstance(joint, str) or not joint for joint in self.joint_order
        ):
            raise ValueError(
                "joint_order must contain at least one non-empty joint name"
            )
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RunRecord:
    """Resolved provenance for one train/play/evaluate invocation."""

    run_id: str
    recipe: Recipe
    status: str
    resolved_config_path: str | None = None
    artifact_path: str | None = None
    metrics_path: str | None = None
    environment: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_identifier(self.run_id, "run_id"))
        object.__setattr__(self, "status", _require_identifier(self.status, "status"))
        object.__setattr__(self, "environment", dict(self.environment))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
