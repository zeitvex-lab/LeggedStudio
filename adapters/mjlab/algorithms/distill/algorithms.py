"""Teacher-student distillation algorithm classes.

Moved from ``local_tasks/learning/algorithms.py``; the legacy module re-imports
these so its entrypoints keep resolving.
"""

from __future__ import annotations

import torch

from adapters.mjlab.algorithms.common.auxiliary_ppo import (
  Go2AuxiliaryPPO,
  OptimizerMixin,
)

from .models import TeacherStudentActorCritic


class TeacherStudentAlgorithm(OptimizerMixin):
  """Teacher/student latent distillation update used by TS variants."""

  def __init__(self, model: TeacherStudentActorCritic, lr: float = 1e-3):
    self.model = model
    self.parameters = list(model.parameters())
    self.optimizer = torch.optim.Adam(self.parameters, lr=lr)

  def update(
    self,
    terrain: torch.Tensor,
    privileged: torch.Tensor,
    history: torch.Tensor,
  ) -> dict[str, float]:
    loss = self.model.distillation_loss(terrain, privileged, history)
    return {"distillation": self._step_loss(loss)}


class TeacherStudentPPO(Go2AuxiliaryPPO):
  auxiliary_kind = "ts"


class AmpTeacherStudentPPO(TeacherStudentPPO):
  uses_amp = True
  amp_replay_buffer_size = 1_000_000

  def _auxiliary_update(self) -> dict[str, float]:
    metrics = super()._auxiliary_update()
    metrics.update(self._amp_update())
    return metrics


__all__ = ["AmpTeacherStudentPPO", "TeacherStudentAlgorithm", "TeacherStudentPPO"]
