"""Configuration schema for the teacher-student distillation plugin."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field


@dataclass(frozen=True)
class DistillAlgorithmConfig:
  """Hyper-parameter schema for the teacher-student plugin."""

  # TeacherStudentActorCritic defaults (source ActorCriticTS).
  encoder_dim: int = 16
  terrain_dim: int = 187
  privileged_dim: int = 74
  policy_hidden_dims: tuple[int, ...] = (512, 256, 128)
  action_dim: int = 12

  # Teacher encoder layouts.
  terrain_encoder_hidden_dims: tuple[int, ...] = (256, 128)
  privileged_encoder_hidden_dims: tuple[int, ...] = (128, 64)

  # Student recurrent encoder (source three-layer LSTM deployed externally).
  student_lstm_hidden_size: int = 256
  student_lstm_num_layers: int = 3

  # Standalone distillation updater (TeacherStudentAlgorithm).
  distillation_learning_rate: float = 1.0e-3
  teacher_learning_rate: float = 1.0e-5

  #: Teacher checkpoint opt-in for standalone student tasks.
  teacher_checkpoint_env_var: str = "GO2_TS_TEACHER_CHECKPOINT"

  #: Observation groups this family can consume (superset; profiles pick).
  supported_obs_types: tuple[str, ...] = field(
    default_factory=lambda: ("actor", "critic", "history", "terrain", "privileged")
  )

  @classmethod
  def from_mapping(cls, values: dict | None) -> "DistillAlgorithmConfig":
    """Build a config from arbitrary cfg keys, ignoring unknown ones."""
    if not values:
      return cls()
    names = {field.name for field in dataclasses.fields(cls)}
    return cls(**{key: value for key, value in values.items() if key in names})


DEFAULT_DISTILL_CONFIG = DistillAlgorithmConfig()

__all__ = ["DEFAULT_DISTILL_CONFIG", "DistillAlgorithmConfig"]
