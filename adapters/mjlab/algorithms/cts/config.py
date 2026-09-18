"""Configuration schema for the CTS algorithm plugin.

Every default mirrors the source task's constants so a profile that only sets
``algorithm_plugin: "cts"`` gets source-equivalent hyper-parameters.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CtsAlgorithmConfig:
  """Hyper-parameter schema for the CTS plugin."""

  # CtsActorCritic defaults (source ActorCriticCTS).
  latent_dim: int = 32
  encoder_hidden_dims: tuple[int, ...] = (512, 256)
  policy_hidden_dims: tuple[int, ...] = (512, 256, 128)
  action_dim: int = 12

  # Standalone updater (CtsAlgorithm).
  learning_rate: float = 1.0e-3
  clip_param: float = 0.2
  distillation_weight: float = 0.1
  entropy_coef: float = 0.01

  # Auxiliary distillation module built by the shared PPO runtime.
  auxiliary_hidden_dims: tuple[int, ...] = (128, 64)
  auxiliary_learning_rate: float = 1.0e-3

  # AMP composition (AmpCtsPPO).
  amp_reward_coef: float = 0.5
  amp_replay_buffer_size: int = 1_000_000
  amp_discriminator_hidden_dims: tuple[int, ...] = (1024, 512)

  #: Observation groups this family can consume (superset; profiles pick).
  supported_obs_types: tuple[str, ...] = field(
    default_factory=lambda: ("actor", "critic", "history", "privileged")
  )

  @classmethod
  def from_mapping(cls, values: dict | None) -> "CtsAlgorithmConfig":
    """Build a config from arbitrary cfg keys, ignoring unknown ones.

    Runner configs carry extra family dimensions (``privileged_dim`` etc.)
    next to hyper-parameters; only schema fields are consumed.
    """
    if not values:
      return cls()
    names = {field.name for field in dataclasses.fields(cls)}
    return cls(**{key: value for key, value in values.items() if key in names})


DEFAULT_CTS_CONFIG = CtsAlgorithmConfig()

__all__ = ["CtsAlgorithmConfig", "DEFAULT_CTS_CONFIG"]
