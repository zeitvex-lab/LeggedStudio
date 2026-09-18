"""DreamWaQ algorithm plugin.

Upstream: DreamWaQ blind locomotion reference (``00_resources/Dreamwaq``)
migrated into the go2 local task; see README.md for provenance.
"""

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

from .algorithms import AmpDreamWaQPPO, DreamWaQAlgorithm, DreamWaQPPO
from .config import DEFAULT_DREAMWAQ_CONFIG, DreamWaQAlgorithmConfig
from .models import DreamWaQActorCritic, DreamWaQActorModel, DreamWaQVAE


class _DreamWaQDeterministicOnnx(nn.Module):
  """ONNX-safe deterministic policy using the VAE posterior means.

  Deployment uses ``mean_explicit || mean_latent`` (no sampling), matching the
  runner-side conditional ONNX wrapper for this family.
  """

  def __init__(self, model: DreamWaQActorCritic) -> None:
    super().__init__()
    self.vae = model.vae
    self.policy_head = model.policy.policy  # mean head of the Gaussian policy

  def forward(self, actor: torch.Tensor, history: torch.Tensor) -> torch.Tensor:
    encoded = self.vae.encoder(history)
    explicit = self.vae.mean_explicit(encoded)
    latent = self.vae.mean_latent(encoded)
    return self.policy_head(torch.cat((explicit, latent, actor), dim=-1))


class DreamWaQPlugin(AlgorithmPlugin):
  """Registry entry for the DreamWaQ (CENet/VAE) family."""

  name = "dreamwaq"
  upstream = (
    "DreamWaQ reference project (00_resources/Dreamwaq); migrated via "
    "local_tasks/learning"
  )
  license = (
    "BSD-3-Clause (declared in 00_resources/Dreamwaq/setup.py; no LICENSE file "
    "in the vendored copy)"
  )
  supported_obs_types = ("actor", "critic", "history", "explicit")

  #: Source Go2 actor observation width used for default artifact builds.
  default_actor_dim = 45

  def build_actor_critic(
    self,
    obs_dim: int,
    action_dim: int,
    cfg: Mapping[str, Any] | None = None,
  ) -> nn.Module:
    values = dict(cfg) if cfg else {}
    config = DreamWaQAlgorithmConfig.from_mapping(values)
    return DreamWaQActorCritic(
      obs_dim=obs_dim,
      critic_dim=int(values.get("critic_dim", obs_dim)),
      history_dim=int(values.get("history_dim", 6 * obs_dim)),
      action_dim=action_dim,
      latent_dim=config.latent_dim,
      explicit_dim=config.explicit_dim,
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
    config = DreamWaQAlgorithmConfig.from_mapping(cfg)
    return torch.optim.Adam(list(params), lr=config.vae_learning_rate)

  def export_onnx(self, path: str, model: nn.Module | None = None) -> str:
    policy = (
      model
      if isinstance(model, DreamWaQActorCritic)
      else self.build_actor_critic(
        self.default_actor_dim, DEFAULT_DREAMWAQ_CONFIG.action_dim
      )
    )
    wrapper = _DreamWaQDeterministicOnnx(policy)
    history_dim = int(policy.vae.encoder[0].in_features)
    actor_dim = policy.obs_dim
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
PLUGIN = DreamWaQPlugin()

__all__ = [
  "AmpDreamWaQPPO",
  "DreamWaQActorCritic",
  "DreamWaQActorModel",
  "DreamWaQAlgorithm",
  "DreamWaQAlgorithmConfig",
  "DreamWaQPPO",
  "DreamWaQPlugin",
  "DreamWaQVAE",
  "PLUGIN",
]
