"""Configuration schema for the AMP algorithm plugin."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AmpAlgorithmConfig:
  """Hyper-parameter schema for the AMP plugin."""

  # AmpDiscriminator defaults (source Go2 AMP configs).
  discriminator_hidden_dims: tuple[int, ...] = (1024, 512)
  amp_reward_coef: float = 0.5
  gradient_penalty_weight: float = 10.0

  # Source AMP observation width (joint pos/vel + base lin/ang vel + height).
  amp_state_dim: int = 31

  # Standalone discriminator updater (AmpAlgorithm).
  discriminator_learning_rate: float = 1.0e-4

  # Shared PPO runtime wiring (AmpPPO).
  replay_buffer_size: int = 1_000_000
  motion_loader_env_var: str = "GO2_MOTION_DIR"

  #: Observation groups this family can consume (superset; profiles pick).
  supported_obs_types: tuple[str, ...] = field(
    default_factory=lambda: ("actor", "critic", "amp")
  )

  @classmethod
  def from_mapping(cls, values: dict | None) -> "AmpAlgorithmConfig":
    """Build a config from arbitrary cfg keys, ignoring unknown ones."""
    if not values:
      return cls()
    names = {field.name for field in dataclasses.fields(cls)}
    return cls(**{key: value for key, value in values.items() if key in names})


DEFAULT_AMP_CONFIG = AmpAlgorithmConfig()

__all__ = ["AmpAlgorithmConfig", "DEFAULT_AMP_CONFIG"]
