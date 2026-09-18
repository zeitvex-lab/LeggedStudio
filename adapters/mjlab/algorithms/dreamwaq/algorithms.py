"""DreamWaQ algorithm classes.

Moved from ``local_tasks/learning/algorithms.py``; the legacy module re-imports
these so its entrypoints keep resolving.
"""

from __future__ import annotations

import torch

from adapters.mjlab.algorithms.common.auxiliary_ppo import (
  Go2AuxiliaryPPO,
  OptimizerMixin,
)

from .models import DreamWaQActorCritic


class DreamWaQAlgorithm(OptimizerMixin):
  """DreamWaQ VAE auxiliary update with reconstruction and KL losses."""

  def __init__(self, model: DreamWaQActorCritic, lr: float = 1e-3):
    self.model = model
    self.parameters = list(model.parameters())
    self.optimizer = torch.optim.Adam(self.parameters, lr=lr)

  def update(self, history: torch.Tensor, target_obs: torch.Tensor) -> dict[str, float]:
    loss = self.model.auxiliary_loss(history, target_obs)
    return {"dreamwaq": self._step_loss(loss)}


class DreamWaQPPO(Go2AuxiliaryPPO):
  auxiliary_kind = "dreamwaq"


class AmpDreamWaQPPO(DreamWaQPPO):
  uses_amp = True
  amp_replay_buffer_size = 1_000_000

  def _auxiliary_update(self) -> dict[str, float]:
    metrics = super()._auxiliary_update()
    metrics.update(self._amp_update())
    return metrics


__all__ = ["AmpDreamWaQPPO", "DreamWaQAlgorithm", "DreamWaQPPO"]
