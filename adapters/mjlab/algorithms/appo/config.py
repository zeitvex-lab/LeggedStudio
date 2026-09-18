"""Configuration schema for the APPO algorithm plugin.

Every default mirrors the extracted UniLab ``appo`` core (``APPOActor`` /
``APPOCritic`` / ``APPOLearner`` constructor defaults) so a bare plugin build
is upstream-equivalent.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AppoAlgorithmConfig:
    """Hyper-parameter schema for the APPO plugin."""

    # APPOActor / APPOCritic defaults (UniLab appo/models.py).
    actor_hidden_dims: tuple[int, ...] = (256, 128, 64)
    critic_hidden_dims: tuple[int, ...] = (256, 128, 64)
    activation: str = "elu"
    init_noise_std: float = 1.0
    action_dim: int = 12

    # APPOLearner defaults (UniLab appo/learner.py).
    learning_rate: float = 1.0e-3
    clip_param: float = 0.2
    gamma: float = 0.99
    lam: float = 0.95
    entropy_coef: float = 0.01
    tau: float = 1.0
    vtrace_clip_rho: float = 1.0
    vtrace_clip_c: float = 1.0

    #: Observation groups this family can consume (superset; profiles pick).
    supported_obs_types: tuple[str, ...] = field(
        default_factory=lambda: ("actor", "critic")
    )

    @classmethod
    def from_mapping(cls, values: dict | None) -> "AppoAlgorithmConfig":
        """Build a config from arbitrary cfg keys, ignoring unknown ones."""
        if not values:
            return cls()
        names = {f.name for f in dataclasses.fields(cls)}
        return cls(**{key: value for key, value in values.items() if key in names})


DEFAULT_APPO_CONFIG = AppoAlgorithmConfig()

__all__ = ["AppoAlgorithmConfig", "DEFAULT_APPO_CONFIG"]
