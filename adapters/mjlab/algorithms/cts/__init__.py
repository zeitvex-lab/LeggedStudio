"""CTS (Concurrent Teacher-Student) algorithm plugin.

Upstream: LeggedGym-Ex go2 CTS/TS (``00_resources/LeggedGym-Ex``), BSD-3-Clause.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import torch
from torch import nn
from torch.nn import functional as F

from adapters.mjlab.algorithms.base import AlgorithmPlugin
from adapters.mjlab.algorithms.common.export import (
  batch_axes,
  export_onnx_module,
  zeros_like_on,
)
from adapters.mjlab.algorithms.common.storage import Go2RolloutStorage

from .algorithms import AmpCtsPPO, CtsAlgorithm, CtsPPO
from .config import DEFAULT_CTS_CONFIG, CtsAlgorithmConfig
from .models import (
  CtsActorCritic,
  CtsActorModel,
  CtsCriticModel,
  CtsStudentActorModel,
)


class _CtsDeterministicOnnx(nn.Module):
  """ONNX-safe deterministic student policy built from :class:`CtsActorCritic`.

  Deployment always uses the distilled history (student) encoder; the
  privileged teacher path never leaves training (source ``act_inference``).
  """

  def __init__(self, model: CtsActorCritic) -> None:
    super().__init__()
    self.student_encoder = model.student_encoder
    self.policy_head = model.policy.policy  # mean head of the Gaussian policy

  def forward(self, actor: torch.Tensor, history: torch.Tensor) -> torch.Tensor:
    latent = F.normalize(self.student_encoder(history), p=2.0, dim=-1)
    return self.policy_head(torch.cat((latent, actor), dim=-1))


class CtsPlugin(AlgorithmPlugin):
  """Registry entry for the concurrent teacher-student family."""

  name = "cts"
  upstream = (
    "LeggedGym-Ex go2 CTS/TS (00_resources/LeggedGym-Ex); migrated via "
    "local_tasks/learning"
  )
  license = "BSD-3-Clause (00_resources/LeggedGym-Ex/LICENSE)"
  supported_obs_types = ("actor", "critic", "history", "privileged")

  #: Source Go2 actor observation width used for default artifact builds.
  default_actor_dim = 45

  def build_actor_critic(
    self,
    obs_dim: int,
    action_dim: int,
    cfg: Mapping[str, Any] | None = None,
  ) -> nn.Module:
    values = dict(cfg) if cfg else {}
    config = CtsAlgorithmConfig.from_mapping(values)
    return CtsActorCritic(
      obs_dim=obs_dim,
      privileged_dim=int(values.get("privileged_dim", 70)),
      critic_dim=int(values.get("critic_dim", obs_dim)),
      history_dim=int(values.get("history_dim", 5 * obs_dim)),
      action_dim=action_dim,
      latent_dim=config.latent_dim,
      hidden_dims=tuple(config.policy_hidden_dims),
    )

  def build_storage(self, cfg: Mapping[str, Any] | None = None) -> Any:
    values = dict(cfg) if cfg else {}
    return Go2RolloutStorage(
      num_steps=int(values.get("num_steps", 24)),
      num_envs=int(values.get("num_envs", 1)),
      device=values.get("device", "cpu"),
    )

  def build_optimizer(
    self,
    params: Iterable[nn.Parameter],
    cfg: Mapping[str, Any] | None = None,
  ) -> torch.optim.Optimizer:
    config = CtsAlgorithmConfig.from_mapping(cfg)
    return torch.optim.Adam(list(params), lr=config.learning_rate)

  def export_onnx(self, path: str, model: nn.Module | None = None) -> str:
    policy = (
      model
      if isinstance(model, CtsActorCritic)
      else self.build_actor_critic(self.default_actor_dim, DEFAULT_CTS_CONFIG.action_dim)
    )
    wrapper = _CtsDeterministicOnnx(policy)
    # Widths are recovered from the module graph: the policy consumes
    # ``latent || actor`` and the student encoder consumes the raw history.
    latent_dim = int(policy.student_encoder[-1].out_features)
    actor_dim = int(policy.policy.policy[0].in_features) - latent_dim
    history_dim = int(policy.student_encoder[0].in_features)
    inputs = zeros_like_on(wrapper, ((1, actor_dim), (1, history_dim)))
    return export_onnx_module(
      wrapper,
      path,
      inputs,
      ("actor", "history"),
      ("actions",),
      batch_axes(("actor", "history"), ("actions",)),
    )


#: Module-level singleton used by the registry loader.
PLUGIN = CtsPlugin()

__all__ = [
  "AmpCtsPPO",
  "CtsActorCritic",
  "CtsActorModel",
  "CtsAlgorithm",
  "CtsAlgorithmConfig",
  "CtsCriticModel",
  "CtsPlugin",
  "CtsPPO",
  "CtsStudentActorModel",
  "PLUGIN",
]
