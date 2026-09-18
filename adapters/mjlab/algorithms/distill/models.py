"""Teacher-student distillation model classes.

Moved from ``local_tasks/learning/models.py``; ``local_tasks.learning.models``
re-imports these so its legacy entrypoints keep resolving.
"""

from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F

from adapters.mjlab.algorithms.common.modules import (
  _ConditionalActor,
  _GaussianPolicy,
  _TsStudentRecurrentOnnxModel,
  _mlp,
)


class TeacherStudentActorCritic(nn.Module):
  """Teacher/student policy with terrain, privileged and LSTM encoders."""

  def __init__(
    self,
    obs_dim: int,
    critic_dim: int,
    terrain_dim: int = 187,
    # The migrated Go2 TS environments expose 70 domain-randomization fields
    # plus four foot-contact bits to the teacher encoder.
    privileged_dim: int = 74,
    action_dim: int = 12,
    encoder_dim: int = 16,
    hidden_dims: tuple[int, ...] = (512, 256, 128),
  ) -> None:
    super().__init__()
    self.obs_dim = obs_dim
    self.terrain_encoder = _mlp(terrain_dim, encoder_dim, (256, 128))
    self.privileged_encoder = _mlp(privileged_dim, encoder_dim, (128, 64))
    self.student_lstm = nn.LSTM(obs_dim, 256, batch_first=True)
    self.student_head = _mlp(256, encoder_dim * 2, (256, 128))
    self.policy = _GaussianPolicy(obs_dim + encoder_dim * 2, action_dim, hidden_dims)
    self.value = _mlp(critic_dim, 1, hidden_dims)

  def teacher_features(
    self, terrain: torch.Tensor, privileged: torch.Tensor
  ) -> torch.Tensor:
    return torch.cat(
      (self.terrain_encoder(terrain), self.privileged_encoder(privileged)), dim=-1
    )

  def student_features(self, history: torch.Tensor) -> torch.Tensor:
    if history.ndim == 2:
      if history.shape[-1] == self.obs_dim:
        history = history.unsqueeze(1)
      elif history.shape[-1] % self.obs_dim == 0:
        history = history.view(history.shape[0], -1, self.obs_dim)
      else:
        raise ValueError(
          f"History dimension {history.shape[-1]} is not divisible by obs_dim {self.obs_dim}"
        )
    sequence, _ = self.student_lstm(history)
    return self.student_head(sequence[:, -1])

  def act(
    self, obs: torch.Tensor, features: torch.Tensor, deterministic: bool = False
  ):
    return self.policy.sample(torch.cat((obs, features), dim=-1), deterministic)

  def evaluate(self, critic_obs: torch.Tensor) -> torch.Tensor:
    return self.value(critic_obs)

  def distillation_loss(
    self, terrain: torch.Tensor, privileged: torch.Tensor, history: torch.Tensor
  ) -> torch.Tensor:
    return F.mse_loss(
      self.student_features(history),
      self.teacher_features(terrain, privileged).detach(),
    )


class TeacherActorModel(_ConditionalActor):
  latent_kind = "ts"


class StudentActorModel(_ConditionalActor):
  latent_kind = "ts"
  use_student = True

  def as_recurrent_onnx(self, verbose: bool = False) -> nn.Module:
    """Return the source TS-Student ``obs,h,c -> actions,he,ce`` exporter.

    The regular mjlab exporter keeps the migrated five-frame conditional
    input.  The legacy student deployment instead carries an external
    three-layer LSTM state, so this wrapper exposes that contract while
    reusing the trained student encoder and actor head.
    """
    return _TsStudentRecurrentOnnxModel(self, verbose)


__all__ = ["StudentActorModel", "TeacherActorModel", "TeacherStudentActorCritic"]
