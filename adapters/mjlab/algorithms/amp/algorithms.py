"""AMP (Adversarial Motion Prior) algorithm classes.

Moved from ``local_tasks/learning/algorithms.py``; the legacy module re-imports
these so its entrypoints keep resolving.
"""

from __future__ import annotations

import torch

from adapters.mjlab.algorithms.common.auxiliary_ppo import (
  Go2AuxiliaryPPO,
  OptimizerMixin,
)

from .models import AmpDiscriminator


class AmpAlgorithm(OptimizerMixin):
  """AMP discriminator update; PPO policy update remains handled by mjlab."""

  def __init__(self, discriminator: AmpDiscriminator, lr: float = 1e-4):
    self.discriminator = discriminator
    self.parameters = list(discriminator.parameters())
    self.optimizer = torch.optim.Adam(self.parameters, lr=lr)

  def update(self, expert: torch.Tensor, policy: torch.Tensor) -> dict[str, float]:
    loss = self.discriminator.loss(expert, policy)
    return {"amp": self._step_loss(loss)}


class AmpPPO(Go2AuxiliaryPPO):
  auxiliary_kind = "amp"
  uses_amp = True

  # The source AMP configurations reserve a million policy transitions.  The
  # buffer is allocated lazily after the first valid rollout pair, so keeping
  # this capacity does not inflate ordinary PPO or pre-step memory usage.
  amp_replay_buffer_size = 1_000_000

  def _auxiliary_update(self) -> dict[str, float]:
    return self._amp_update()


__all__ = ["AmpAlgorithm", "AmpPPO"]
