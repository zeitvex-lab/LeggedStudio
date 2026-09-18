"""Configuration schema for the HIM algorithm plugin.

Every default mirrors the extracted UniLab ``him_ppo`` core
(``HIMActorCritic`` / ``HIMPPO`` / ``HIMEstimator`` constructor defaults) so a
bare plugin build is upstream-equivalent.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field


@dataclass(frozen=True)
class HimAlgorithmConfig:
    """Hyper-parameter schema for the HIM plugin."""

    # HIMActorCritic defaults (UniLab him_ppo/actor_critic.py).
    one_step_obs_dim: int = 45
    actor_hidden_dims: tuple[int, ...] = (512, 256, 128)
    critic_hidden_dims: tuple[int, ...] = (512, 256, 128)
    activation: str = "elu"
    init_noise_std: float = 1.0
    action_dim: int = 12

    # HIMPPO defaults (UniLab him_ppo/algorithm.py).
    learning_rate: float = 1.0e-3
    clip_param: float = 0.2
    gamma: float = 0.998
    lam: float = 0.95
    entropy_coef: float = 0.0

    # HIMEstimator defaults (UniLab him_ppo/estimator.py).
    estimator_learning_rate: float = 1.0e-3
    estimator_num_prototype: int = 32

    #: Observation groups this family can consume (superset; profiles pick).
    supported_obs_types: tuple[str, ...] = field(
        default_factory=lambda: ("actor", "critic", "history", "privileged")
    )

    @classmethod
    def from_mapping(cls, values: dict | None) -> "HimAlgorithmConfig":
        """Build a config from arbitrary cfg keys, ignoring unknown ones."""
        if not values:
            return cls()
        names = {f.name for f in dataclasses.fields(cls)}
        return cls(**{key: value for key, value in values.items() if key in names})


DEFAULT_HIM_CONFIG = HimAlgorithmConfig()

__all__ = ["HimAlgorithmConfig", "DEFAULT_HIM_CONFIG"]
