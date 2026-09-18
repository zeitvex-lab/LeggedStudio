"""CTS (Concurrent Teacher-Student) model classes.

Moved from ``local_tasks/learning/models.py``; ``local_tasks.learning.models``
re-imports these so its legacy entrypoints keep resolving.
"""

from __future__ import annotations

import torch
from rsl_rl.models import MLPModel
from rsl_rl.modules.mlp import MLP
from torch import nn
from torch.nn import functional as F

from adapters.mjlab.algorithms.common.modules import (
  _ConditionalActor,
  _GaussianPolicy,
  _mlp,
)


class CtsActorCritic(nn.Module):
  """Concurrent teacher-student policy from the source CTS task."""

  def __init__(
    self,
    obs_dim: int,
    privileged_dim: int,
    critic_dim: int,
    history_dim: int,
    action_dim: int = 12,
    latent_dim: int = 32,
    hidden_dims: tuple[int, ...] = (512, 256, 128),
  ) -> None:
    super().__init__()
    self.teacher_encoder = _mlp(privileged_dim, latent_dim, (512, 256))
    self.student_encoder = _mlp(history_dim, latent_dim, (512, 256))
    self.policy = _GaussianPolicy(latent_dim + obs_dim, action_dim, hidden_dims)
    self.value = _mlp(latent_dim + critic_dim, 1, hidden_dims)

  def encode_teacher(self, privileged: torch.Tensor) -> torch.Tensor:
    return F.normalize(self.teacher_encoder(privileged), p=2.0, dim=-1)

  def encode_student(self, history: torch.Tensor) -> torch.Tensor:
    return F.normalize(self.student_encoder(history), p=2.0, dim=-1)

  def act(
    self,
    obs: torch.Tensor,
    privileged: torch.Tensor,
    history: torch.Tensor,
    teacher: bool = True,
    deterministic: bool = False,
  ):
    latent = (
      self.encode_teacher(privileged) if teacher else self.encode_student(history)
    )
    return self.policy.sample(torch.cat((latent, obs), dim=-1), deterministic)

  def evaluate(
    self,
    critic_obs: torch.Tensor,
    privileged: torch.Tensor,
    history: torch.Tensor,
    teacher: bool = True,
  ) -> torch.Tensor:
    latent = (
      self.encode_teacher(privileged) if teacher else self.encode_student(history)
    )
    return self.value(torch.cat((latent.detach(), critic_obs), dim=-1))

  def distillation_loss(
    self, privileged: torch.Tensor, history: torch.Tensor
  ) -> torch.Tensor:
    return F.mse_loss(
      self.encode_student(history), self.encode_teacher(privileged).detach()
    )


class CtsCriticModel(MLPModel):
  """CTS value model with the source latent||critic observation contract."""

  def __init__(self, obs, obs_groups, obs_set, output_dim, **kwargs) -> None:
    super().__init__(obs, obs_groups, obs_set, output_dim, **kwargs)
    privileged_dim = int(obs["privileged"].shape[-1])
    history_dim = int(obs["history"].shape[-1])
    self._go2_actor_dim = int(obs["actor"].shape[-1])
    hidden_dims = tuple(kwargs.get("hidden_dims", (512, 256, 128)))
    activation = kwargs.get("activation", "elu")
    self.teacher_encoder = _mlp(privileged_dim, 32, (512, 256))
    self.student_encoder = _mlp(history_dim - self._go2_actor_dim, 32, (512, 256))
    self.mlp = MLP(self.obs_dim + 32, output_dim, hidden_dims, activation)

  def get_latent(self, obs, masks=None, hidden_state=None):
    del masks, hidden_state
    critic_obs = self.obs_normalizer(
      torch.cat([obs[group] for group in self.obs_groups], dim=-1)
    )
    teacher = F.normalize(self.teacher_encoder(obs["privileged"]), p=2.0, dim=-1)
    student = F.normalize(
      self.student_encoder(obs["history"][..., : -self._go2_actor_dim]),
      p=2.0,
      dim=-1,
    )
    mask = obs.get("teacher_mask")
    if mask is None:
      latent = teacher
    else:
      latent = torch.where(mask > 0.5, teacher, student)
    # Source CTS explicitly detaches the selected encoder latent before the
    # value network so critic loss cannot update teacher/student encoders.
    return torch.cat((latent.detach(), critic_obs), dim=-1)


class CtsActorModel(_ConditionalActor):
  latent_kind = "cts"


class CtsStudentActorModel(_ConditionalActor):
  latent_kind = "cts"
  use_student = True


__all__ = [
  "CtsActorCritic",
  "CtsActorModel",
  "CtsCriticModel",
  "CtsStudentActorModel",
]
