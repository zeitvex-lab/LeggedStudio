"""Versioned scenario and training-recipe contracts.

These models are shared by native MJLab training and MuJoCo simulation
workflows.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class Waypoint(BaseModel):
    x: float
    y: float
    tolerance: float = Field(default=0.35, gt=0.0, le=5.0)


class ScenarioContract(BaseModel):
    schema_version: str = "scenario-contract-1.0"
    scenario_id: str = Field(pattern=r"^[a-z0-9_-]+$")
    map_id: str = "flat"
    mode: Literal["basic", "navigation"] = "basic"
    seed: int = 0
    episode_length_s: float = Field(default=60.0, gt=0.0, le=3600.0)
    waypoints: list[Waypoint] = Field(default_factory=list)
    command_limits: dict[str, float] = Field(default_factory=lambda: {"vx": 1.0, "vy": 1.0, "wz": 1.0})
    metrics: list[str] = Field(default_factory=lambda: ["reward", "distance", "route_completion"])

    @field_validator("command_limits")
    @classmethod
    def validate_command_limits(cls, value: dict[str, float]) -> dict[str, float]:
        required = {"vx", "vy", "wz"}
        if not required.issubset(value):
            raise ValueError("command_limits must contain vx, vy and wz")
        if any(float(item) <= 0 for item in value.values()):
            raise ValueError("command limits must be positive")
        return {key: float(item) for key, item in value.items()}

    def to_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class TrainingRecipe(BaseModel):
    """Resolved task recipe shared by Web, CLI and adapter workers."""

    schema_version: str = "training-recipe-1.0"
    task_name: str = "forward_walk"
    algorithm: str = "PPO"
    backend: Literal["native_mjlab"] = "native_mjlab"
    reward_scales: dict[str, float] = Field(default_factory=dict)
    environment: dict[str, Any] = Field(default_factory=dict)
    algorithm_config: dict[str, Any] = Field(default_factory=dict)
    seed: int = 0

    @field_validator("algorithm")
    @classmethod
    def normalize_algorithm(cls, value: str) -> str:
        return value.upper()
