"""AMP (Adversarial Motion Prior) algorithm plugin.

The AMP family is a *composition* plugin: it contributes the discriminator,
replay buffer and shaping-reward machinery that other families (cts /
dreamwaq / distill) mix in via their ``Amp*PPO`` variants.
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
from adapters.mjlab.algorithms.common.storage import (
  Go2AmpReplayBuffer,
  Go2RolloutStorage,
)

from .algorithms import AmpAlgorithm, AmpPPO
from .config import AmpAlgorithmConfig, DEFAULT_AMP_CONFIG
from .models import AmpDiscriminator


class AmpPlugin(AlgorithmPlugin):
  """Registry entry for the adversarial-motion-prior family."""

  name = "amp"
  upstream = (
    "LeggedGym-Ex go2 AMP variants (00_resources/LeggedGym-Ex) with mjlab AMP "
    "reference (00_resources/AMP_mjlab); migrated via local_tasks/learning"
  )
  license = (
    "BSD-3-Clause (00_resources/LeggedGym-Ex/LICENSE; AMP_mjlab vendored copy "
    "carries no top-level license)"
  )
  supported_obs_types = ("actor", "critic", "amp")

  def build_actor_critic(
    self,
    obs_dim: int,
    action_dim: int,
    cfg: Mapping[str, Any] | None = None,
  ) -> nn.Module:
    """Build the AMP discriminator; ``obs_dim`` is the AMP state width.

    The discriminator scores transitions (state, next_state) so its input is
    ``2 * obs_dim``; ``action_dim`` is accepted for protocol uniformity and
    ignored by this family.
    """
    del action_dim
    config = AmpAlgorithmConfig.from_mapping(dict(cfg) if cfg else None)
    return AmpDiscriminator(
      input_dim=obs_dim,
      hidden_dims=tuple(config.discriminator_hidden_dims),
      amp_reward_coef=config.amp_reward_coef,
    )

  def build_storage(self, cfg: Mapping[str, Any] | None = None) -> Any:
    """Build the AMP transition replay buffer (family-native storage)."""
    values = dict(cfg) if cfg else {}
    state_dim = int(values.get("amp_state_dim", DEFAULT_AMP_CONFIG.amp_state_dim))
    capacity = int(
      values.get("replay_buffer_size", DEFAULT_AMP_CONFIG.replay_buffer_size)
    )
    device = values.get("device", "cpu")
    if values.get("as_rollout"):
      return Go2RolloutStorage(
        num_steps=int(values.get("num_steps", 24)),
        num_envs=int(values.get("num_envs", 1)),
        device=device,
      )
    return Go2AmpReplayBuffer(state_dim, capacity=capacity, device=device)

  def build_optimizer(
    self,
    params: Iterable[nn.Parameter],
    cfg: Mapping[str, Any] | None = None,
  ) -> torch.optim.Optimizer:
    """Build the source two-group Adam (hidden layers 1e-4 / head 1e-2 decay).

    ``params`` may be either a plain iterable (single group) or the source
    parameter-group list consumed verbatim.
    """
    config = AmpAlgorithmConfig.from_mapping(dict(cfg) if cfg else None)
    materialized = list(params)
    if materialized and all(isinstance(item, dict) for item in materialized):
      return torch.optim.Adam(materialized, lr=config.discriminator_learning_rate)
    return torch.optim.Adam(materialized, lr=config.discriminator_learning_rate)

  def export_onnx(self, path: str, model: nn.Module | None = None) -> str:
    """Export the discriminator scoring graph ``(amp, next_amp) -> logit``."""
    discriminator = (
      model
      if isinstance(model, AmpDiscriminator)
      else self.build_actor_critic(DEFAULT_AMP_CONFIG.amp_state_dim, 0)
    )
    state_dim = discriminator.state_dim
    inputs = zeros_like_on(discriminator, ((1, state_dim), (1, state_dim)))
    return export_onnx_module(
      discriminator,
      path,
      inputs,
      ("amp", "next_amp"),
      ("logit",),
      batch_axes(("amp", "next_amp"), ("logit",)),
    )


#: Module-level singleton used by the registry loader.
PLUGIN = AmpPlugin()

__all__ = [
  "AmpAlgorithm",
  "AmpAlgorithmConfig",
  "AmpDiscriminator",
  "AmpPlugin",
  "AmpPPO",
  "PLUGIN",
]
