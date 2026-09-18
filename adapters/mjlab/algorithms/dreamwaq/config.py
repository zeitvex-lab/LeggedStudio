"""Configuration schema for the DreamWaQ algorithm plugin."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field


@dataclass(frozen=True)
class DreamWaQAlgorithmConfig:
  """Hyper-parameter schema for the DreamWaQ plugin."""

  # DreamWaQActorCritic / CENet defaults (source ActorCriticDreamWaQ).
  latent_dim: int = 16
  explicit_dim: int = 3
  policy_hidden_dims: tuple[int, ...] = (256, 256, 256)
  action_dim: int = 12

  # Standalone VAE updater (DreamWaQAlgorithm).
  vae_learning_rate: float = 1.0e-3
  ppo_learning_rate: float = 1.0e-3

  # AMP composition (AmpDreamWaQPPO).
  amp_reward_coef: float = 0.5
  amp_replay_buffer_size: int = 1_000_000
  amp_discriminator_hidden_dims: tuple[int, ...] = (1024, 512)

  #: Observation groups this family can consume (superset; profiles pick).
  supported_obs_types: tuple[str, ...] = field(
    default_factory=lambda: ("actor", "critic", "history", "explicit")
  )

  @classmethod
  def from_mapping(cls, values: dict | None) -> "DreamWaQAlgorithmConfig":
    """Build a config from arbitrary cfg keys, ignoring unknown ones."""
    if not values:
      return cls()
    names = {field.name for field in dataclasses.fields(cls)}
    return cls(**{key: value for key, value in values.items() if key in names})


DEFAULT_DREAMWAQ_CONFIG = DreamWaQAlgorithmConfig()

__all__ = ["DEFAULT_DREAMWAQ_CONFIG", "DreamWaQAlgorithmConfig"]
