"""CTS (Concurrent Teacher-Student) algorithm classes.

Moved from ``local_tasks/learning/algorithms.py``; the legacy module re-imports
these so its entrypoints keep resolving.
"""

from __future__ import annotations

import torch

from adapters.mjlab.algorithms.common.auxiliary_ppo import (
  Go2AuxiliaryPPO,
  OptimizerMixin,
)
from adapters.mjlab.algorithms.common.storage import Go2RolloutStorage

from .models import CtsActorCritic


class CtsAlgorithm(OptimizerMixin):
  """PPO-compatible CTS update with an explicit latent distillation term."""

  def __init__(
    self, model: CtsActorCritic, storage: Go2RolloutStorage, lr: float = 1e-3
  ):
    self.model = model
    self.storage = storage
    self.parameters = list(model.parameters())
    self.optimizer = torch.optim.Adam(self.parameters, lr=lr)

  def update(
    self,
    obs: torch.Tensor | None = None,
    privileged: torch.Tensor | None = None,
    critic_obs: torch.Tensor | None = None,
    history: torch.Tensor | None = None,
    actions: torch.Tensor | None = None,
    old_log_prob: torch.Tensor | None = None,
    returns: torch.Tensor | None = None,
    advantages: torch.Tensor | None = None,
    clip_param: float = 0.2,
  ) -> dict[str, float]:
    if any(
      item is None
      for item in (
        obs,
        privileged,
        critic_obs,
        history,
        actions,
        old_log_prob,
        returns,
        advantages,
      )
    ):
      if self.storage.advantages is None:
        raise RuntimeError("CTS storage has no returns")
      loss = self.storage.advantages.square().mean()
      return {"ppo": self._step_loss(loss), "distillation": 0.0}
    assert obs is not None and privileged is not None and critic_obs is not None
    assert history is not None and actions is not None and old_log_prob is not None
    assert returns is not None and advantages is not None
    output = self.model.act(obs, privileged, history, teacher=True)
    log_prob = (
      self.model.policy.distribution(
        torch.cat((self.model.encode_teacher(privileged), obs), dim=-1)
      )
      .log_prob(actions)
      .sum(dim=-1)
    )
    ratio = torch.exp(log_prob - old_log_prob)
    surrogate = -torch.minimum(
      ratio * advantages, ratio.clamp(1.0 - clip_param, 1.0 + clip_param) * advantages
    ).mean()
    value_loss = (
      (
        self.model.evaluate(critic_obs, privileged, history, teacher=True).squeeze(-1)
        - returns
      )
      .square()
      .mean()
    )
    distill = self.model.distillation_loss(privileged, history)
    loss = surrogate + value_loss + 0.1 * distill - 0.01 * output.log_prob.mean()
    return {"ppo": self._step_loss(loss), "distillation": float(distill.detach())}


class CtsPPO(Go2AuxiliaryPPO):
  auxiliary_kind = "cts"

  def update(self) -> dict[str, float]:
    # Source CTS computes teacher and student surrogate means independently
    # and adds them, giving the 1/4 student partition equal group weight to
    # the 3/4 teacher partition.  Pre-weighting advantages reproduces that
    # objective inside the native shuffled PPO mini-batch implementation.
    if "teacher_mask" in self.storage.observations.keys():
      teacher_mask = self.storage.observations["teacher_mask"]
      if not isinstance(teacher_mask, torch.Tensor):
        raise TypeError("teacher_mask observation must be a tensor")
      teacher = (teacher_mask > 0.5).to(torch.bool)
      advantages = self.storage.advantages
      assert advantages is not None
      group_weight = teacher.to(advantages.dtype) * (1.0 / 0.75) + (~teacher).to(
        advantages.dtype
      ) * (1.0 / 0.25)
      # Rollout returns are computed under inference mode by RSL-RL.  Clone
      # before weighting so the PPO update owns a regular mutable tensor.
      self.storage.advantages = advantages.clone() * group_weight
    return super().update()


class AmpCtsPPO(CtsPPO):
  uses_amp = True
  amp_replay_buffer_size = 1_000_000

  def _auxiliary_update(self) -> dict[str, float]:
    metrics = super()._auxiliary_update()
    metrics.update(self._amp_update())
    return metrics


__all__ = ["AmpCtsPPO", "CtsAlgorithm", "CtsPPO"]
