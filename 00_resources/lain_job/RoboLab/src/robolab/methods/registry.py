"""Registry for algorithm/method plugins.

The registry contains metadata and extension-point names only.  It does not
import Isaac Gym, MJLab, or any backend-owned runner implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MethodSpec:
    """Backend-neutral description of one trainable method."""

    method_id: str
    display_name: str
    algorithm: str
    policy: str
    runner: str
    storage: str
    frameworks: tuple[str, ...] = ()
    paper: str | None = None
    input_contract: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("method_id", "display_name", "algorithm", "policy", "runner", "storage"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not self.frameworks:
            raise ValueError("frameworks must contain at least one backend")
        if any(not isinstance(item, str) or not item.strip() for item in self.frameworks):
            raise ValueError("frameworks must contain non-empty strings")
        object.__setattr__(self, "frameworks", tuple(self.frameworks))
        object.__setattr__(self, "input_contract", dict(self.input_contract))

    def to_dict(self) -> dict[str, Any]:
        return {
            "method_id": self.method_id,
            "display_name": self.display_name,
            "algorithm": self.algorithm,
            "policy": self.policy,
            "runner": self.runner,
            "storage": self.storage,
            "frameworks": list(self.frameworks),
            "paper": self.paper,
            "input_contract": dict(self.input_contract),
        }


_METHODS: dict[str, MethodSpec] = {}


def register_method(spec: MethodSpec) -> MethodSpec:
    """Register a method once and return the registered specification."""

    if spec.method_id in _METHODS:
        raise ValueError(f"method already registered: {spec.method_id}")
    _METHODS[spec.method_id] = spec
    return spec


def get_method(method_id: str) -> MethodSpec:
    try:
        return _METHODS[method_id]
    except KeyError as exc:
        available = ", ".join(list_methods()) or "<none>"
        raise KeyError(f"unknown method {method_id!r}; available: {available}") from exc


def list_methods() -> tuple[str, ...]:
    return tuple(sorted(_METHODS))


def _register_builtin_methods() -> None:
    register_method(
        MethodSpec(
            method_id="ppo",
            display_name="Proximal Policy Optimization",
            algorithm="PPO",
            policy="ActorCritic",
            runner="OnPolicyRunner",
            storage="RolloutStorage",
            frameworks=("isaacgym", "mjlab"),
            input_contract={"actor_observation": "task-defined", "action": "task-defined"},
        )
    )
    register_method(
        MethodSpec(
            method_id="teacher_student",
            display_name="Teacher-Student Privileged-Information Distillation",
            algorithm="PPO_TS",
            policy="ActorCriticTS",
            runner="TeacherStudentRunner",
            storage="RolloutStorageTS",
            frameworks=("isaacgym",),
            paper="https://agility.csail.mit.edu/",
            input_contract={
                "actor_observation": "45-dim proprioception + 99-dim distilled latent (144 total)",
                "teacher_observation": "99-dim domain/terrain/contact/foot-geometry privileged input",
                "critic_observation": "5 x 96-dim clean privileged critic history (480 total)",
                "observation_history": "20 x 45-dim history (900 total)",
                "action": "12-dim A1 joint action",
            },
        )
    )
    register_method(
        MethodSpec(
            method_id="dreamwaq",
            display_name="DreamWaQ: VAE-based Hybrid Implicit-Explicit Policy",
            algorithm="PPO_DreamWaQ",
            policy="ActorCriticDreamWaQ",
            runner="DreamWaQRunner",
            storage="RolloutStorageDreamWaQ",
            frameworks=("isaacgym",),
            paper="2210.17002",
            input_contract={
                "actor_observation": "45-dim proprioception + 16-dim latent + 24-dim explicit estimate (85 total)",
                "observation_history": "5 x 45-dim A1 proprioceptive history (225 total)",
                "privileged_observation": "480-dim A1 critic history (5 x 96)",
                "explicit_target": "24-dim base velocity/contact/foot-height labels",
                "reconstruction_target": "next 45-dim proprioceptive observation",
                "action": "12-dim A1 joint action",
            },
        )
    )
    register_method(
        MethodSpec(
            method_id="ppo_ee",
            display_name="PPO with Explicit State Estimator",
            algorithm="PPO_EE",
            policy="ActorCriticEE",
            runner="EERunner",
            storage="RolloutStorageEE",
            frameworks=("isaacgym",),
            paper="2202.05481",
            input_contract={
                "actor_observation": "45-dim A1 velocity observation",
                "estimator_features": "observation history",
                "estimator_target": "base velocity/contact/foot height",
                "action": "12-dim A1 joint action",
            },
        )
    )
    register_method(
        MethodSpec(
            method_id="cts",
            display_name="Concurrent Teacher-Student Reinforcement Learning",
            algorithm="PPO_CTS",
            policy="ActorCriticCTS",
            runner="CTSRunner",
            storage="RolloutStorageCTS",
            frameworks=("isaacgym",),
            paper="https://clearlab-sustech.github.io/concurrentTS/",
            input_contract={
                "teacher_partition": "first 3/4 of parallel A1 environments",
                "student_partition": "remaining 1/4 of parallel A1 environments",
                "actor_observation": "45-dim A1 proprioception",
                "teacher_observation": "99-dim privileged domain/terrain/contact input",
                "observation_history": "20 x 45-dim history (900 total)",
                "critic_observation": "5 x 96-dim privileged critic history (480 total)",
                "action": "12-dim A1 joint action",
            },
        )
    )


_register_builtin_methods()
