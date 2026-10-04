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
from adapters.mjlab.algorithms.amp.source_amp import AmpPpoMixin

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


class AmpDreamWaQPPO(AmpPpoMixin, DreamWaQPPO):
  """DreamWaQ PPO + 源口径 AMP（与 go2 薄委托同一组合，2026-10-04 上移后插件化）。

  机型量（amp_joint_order / amp_motion_root）由 runner cfg 的算法字段在构造期
  传入（rsl_rl construct_algorithm 把 cfg 字段作为 kwargs）；类属性缺省为空、
  缺失即在构造期 fail-loud（AmpPpoMixin 的双通道设计）。
  """

  amp_joint_order: tuple[str, ...] = ()
  amp_motion_root: str | None = None


__all__ = ["AmpDreamWaQPPO", "DreamWaQAlgorithm", "DreamWaQPPO"]
