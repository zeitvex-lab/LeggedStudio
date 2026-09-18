"""Teacher-student distillation algorithm plugin."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import torch
from torch import nn

from adapters.mjlab.algorithms.base import AlgorithmPlugin
from adapters.mjlab.algorithms.common.export import (
  batch_axes,
  export_onnx_module,
  zeros_like_on,
)
from adapters.mjlab.algorithms.common.storage import Go2RolloutStorage

from .algorithms import (
  AmpTeacherStudentPPO,
  TeacherStudentAlgorithm,
  TeacherStudentPPO,
)
from .config import DEFAULT_DISTILL_CONFIG, DistillAlgorithmConfig
from .models import (
  StudentActorModel,
  TeacherActorModel,
  TeacherStudentActorCritic,
)


class _TsStudentDeterministicOnnx(nn.Module):
  """ONNX-safe deterministic student policy (frame-window contract)."""

  def __init__(self, model: TeacherStudentActorCritic) -> None:
    super().__init__()
    self.student_lstm = model.student_lstm
    self.student_head = model.student_head
    self.policy_head = model.policy.policy

  def forward(self, actor: torch.Tensor, history: torch.Tensor) -> torch.Tensor:
    obs_dim = actor.shape[-1]
    sequence = history.view(history.shape[0], -1, obs_dim)
    encoded, _ = self.student_lstm(sequence)
    features = self.student_head(encoded[:, -1])
    return self.policy_head(torch.cat((features, actor), dim=-1))


class DistillPlugin(AlgorithmPlugin):
  """Registry entry for the teacher-student distillation family."""

  name = "distill"
  upstream = (
    "LeggedGym-Ex go2 CTS/TS teacher-student framework (00_resources/"
    "LeggedGym-Ex); migrated via local_tasks/learning"
  )
  license = "BSD-3-Clause (00_resources/LeggedGym-Ex/LICENSE)"
  supported_obs_types = ("actor", "critic", "history", "terrain", "privileged")

  #: Source Go2 actor observation width used for default artifact builds.
  default_actor_dim = 45

  def build_actor_critic(
    self,
    obs_dim: int,
    action_dim: int,
    cfg: Mapping[str, Any] | None = None,
  ) -> nn.Module:
    values = dict(cfg) if cfg else {}
    config = DistillAlgorithmConfig.from_mapping(values)
    return TeacherStudentActorCritic(
      obs_dim=obs_dim,
      critic_dim=int(values.get("critic_dim", obs_dim)),
      terrain_dim=int(values.get("terrain_dim", config.terrain_dim)),
      privileged_dim=int(values.get("privileged_dim", config.privileged_dim)),
      action_dim=action_dim,
      encoder_dim=config.encoder_dim,
      hidden_dims=tuple(config.policy_hidden_dims),
    )

  def build_storage(self, cfg: Mapping[str, Any] | None = None) -> Any:
    values = dict(cfg) if cfg else {}
    return Go2RolloutStorage(
      num_steps=int(values.get("num_steps", 50)),
      num_envs=int(values.get("num_envs", 1)),
      device=values.get("device", "cpu"),
    )

  def build_optimizer(
    self,
    params: Iterable[nn.Parameter],
    cfg: Mapping[str, Any] | None = None,
  ) -> torch.optim.Optimizer:
    config = DistillAlgorithmConfig.from_mapping(cfg)
    return torch.optim.Adam(list(params), lr=config.distillation_learning_rate)

  def export_onnx(self, path: str, model: nn.Module | None = None) -> str:
    policy = (
      model
      if isinstance(model, TeacherStudentActorCritic)
      else self.build_actor_critic(
        self.default_actor_dim, DEFAULT_DISTILL_CONFIG.action_dim
      )
    )
    wrapper = _TsStudentDeterministicOnnx(policy)
    actor_dim = policy.obs_dim
    history_dim = actor_dim * 5
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
PLUGIN = DistillPlugin()

__all__ = [
  "AmpTeacherStudentPPO",
  "DistillAlgorithmConfig",
  "DistillPlugin",
  "PLUGIN",
  "StudentActorModel",
  "TeacherActorModel",
  "TeacherStudentActorCritic",
  "TeacherStudentAlgorithm",
  "TeacherStudentPPO",
]
