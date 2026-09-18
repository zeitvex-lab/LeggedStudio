"""Configuration schema for the HORA algorithm plugin.

Every default mirrors the extracted UniLab ``hora`` core
(``HoraSharedActorCritic`` / ``build_hora_shared_actor_critic`` / ``HoraPPO``
constructor defaults) so a bare plugin build is upstream-equivalent.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field


@dataclass(frozen=True)
class HoraAlgorithmConfig:
    """Hyper-parameter schema for the HORA plugin."""

    # Shared-backbone core (UniLab hora/models.py).
    priv_info_dim: int = 32
    priv_info_embed_dim: int = 8
    actor_hidden_dims: tuple[int, ...] = (512, 256, 128)
    priv_mlp_hidden_dims: tuple[int, ...] = (256, 128, 8)
    activation: str = "elu"
    obs_normalization: bool = False
    use_student_encoder: bool = False
    proprio_hist_len: int = 30
    action_dim: int = 12

    # HoraPPO defaults (UniLab hora/ppo.py).
    learning_rate: float = 1.0e-3
    clip_param: float = 0.2
    gamma: float = 0.99
    lam: float = 0.95
    entropy_coef: float = 0.01

    #: Observation groups this family can consume (superset; profiles pick).
    supported_obs_types: tuple[str, ...] = field(
        default_factory=lambda: ("actor", "privileged", "history")
    )

    @classmethod
    def from_mapping(cls, values: dict | None) -> "HoraAlgorithmConfig":
        """Build a config from arbitrary cfg keys, ignoring unknown ones."""
        if not values:
            return cls()
        names = {f.name for f in dataclasses.fields(cls)}
        return cls(**{key: value for key, value in values.items() if key in names})


DEFAULT_HORA_CONFIG = HoraAlgorithmConfig()

__all__ = ["HoraAlgorithmConfig", "DEFAULT_HORA_CONFIG"]
