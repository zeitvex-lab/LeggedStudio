"""DreamWaQ model classes.

Moved from ``local_tasks/learning/models.py``; ``local_tasks.learning.models``
re-imports these so its legacy entrypoints keep resolving.
"""

from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F

from adapters.mjlab.algorithms.common.modules import (
  _ConditionalActor,
  _GaussianPolicy,
  _mlp,
)


class DreamWaQVAE(nn.Module):
  """CENet/VAE used for latent and explicit velocity estimation."""

  def __init__(self, history_dim: int, latent_dim: int, explicit_dim: int, decode_dim: int):
    super().__init__()
    # Source CENet applies ELU after both encoder linear layers, including the
    # 64-D bottleneck.  ``_mlp`` intentionally leaves output layers linear, so
    # spell this encoder out rather than silently dropping the final ELU.
    self.encoder = nn.Sequential(
      nn.Linear(history_dim, 128),
      nn.ELU(),
      nn.Linear(128, 64),
      nn.ELU(),
    )
    self.mean_latent = nn.Linear(64, latent_dim)
    self.logvar_latent = nn.Sequential(
      nn.Linear(64, latent_dim), nn.Hardtanh(-5.0, 5.0)
    )
    self.mean_explicit = nn.Linear(64, explicit_dim)
    self.logvar_explicit = nn.Sequential(
      nn.Linear(64, explicit_dim), nn.Hardtanh(-5.0, 5.0)
    )
    self.decoder = _mlp(latent_dim + explicit_dim, decode_dim, (128, 128))

  @staticmethod
  def reparameterize(mean: torch.Tensor, logvar: torch.Tensor) -> torch.Tensor:
    return mean + torch.exp(0.5 * logvar) * torch.randn_like(mean)

  def forward(self, history: torch.Tensor) -> dict[str, torch.Tensor]:
    encoded = self.encoder(history)
    mean_latent = self.mean_latent(encoded)
    logvar_latent = self.logvar_latent(encoded)
    mean_explicit = self.mean_explicit(encoded)
    logvar_explicit = self.logvar_explicit(encoded)
    latent = self.reparameterize(mean_latent, logvar_latent)
    explicit = self.reparameterize(mean_explicit, logvar_explicit)
    # Keep the source VAE code layout: sampled velocity estimate first,
    # followed by the stochastic latent code.  The decoder is trained against
    # this ordering, so changing only the actor input would still make the
    # auxiliary reconstruction objective semantically inconsistent.
    decoded = self.decoder(torch.cat((explicit, latent), dim=-1))
    return {
      "latent": latent,
      "explicit": explicit,
      "decoded": decoded,
      "mean_latent": mean_latent,
      "logvar_latent": logvar_latent,
      "mean_explicit": mean_explicit,
      "logvar_explicit": logvar_explicit,
    }


class DreamWaQActorCritic(nn.Module):
  """DreamWaQ actor-critic with a trainable history VAE."""

  def __init__(
    self,
    obs_dim: int,
    critic_dim: int,
    history_dim: int,
    action_dim: int = 12,
    latent_dim: int = 16,
    explicit_dim: int = 3,
    hidden_dims: tuple[int, ...] = (256, 256, 256),
  ) -> None:
    super().__init__()
    self.obs_dim = obs_dim
    self.vae = DreamWaQVAE(history_dim - obs_dim, latent_dim, explicit_dim, obs_dim)
    self.policy = _GaussianPolicy(
      obs_dim + latent_dim + explicit_dim, action_dim, hidden_dims
    )
    self.value = _mlp(critic_dim, 1, hidden_dims)

  def act(
    self, obs: torch.Tensor, history: torch.Tensor, deterministic: bool = False
  ):
    encoded = self.vae(history[..., : -self.obs_dim])
    # The source DreamWaQ actor receives ``code_vel || code_latent || obs``.
    # Keep the explicit velocity code first; swapping these two  fields would
    # preserve the tensor width while silently making source checkpoints
    # incompatible.
    features = torch.cat((encoded["explicit"], encoded["latent"], obs), dim=-1)
    return self.policy.sample(features, deterministic)

  def evaluate(self, critic_obs: torch.Tensor) -> torch.Tensor:
    return self.value(critic_obs)

  def auxiliary_loss(
    self,
    history: torch.Tensor,
    target_obs: torch.Tensor,
    target_velocity: torch.Tensor | None = None,
    live_mask: torch.Tensor | None = None,
  ) -> torch.Tensor:
    encoded = self.vae(history[..., : -self.obs_dim])
    if live_mask is None:
      live_mask = torch.ones(
        (history.shape[0], 1), device=history.device, dtype=history.dtype
      )
    elif live_mask.ndim == 1:
      live_mask = live_mask.unsqueeze(-1)
    reconstruction = F.mse_loss(encoded["decoded"] * live_mask, target_obs * live_mask)
    velocity = (
      F.mse_loss(encoded["explicit"] * live_mask, target_velocity * live_mask)
      if target_velocity is not None
      else encoded["explicit"].new_zeros(())
    )
    kl_per_sample = torch.sum(
      1
      + encoded["logvar_latent"]
      - encoded["mean_latent"].square()
      - encoded["logvar_latent"].exp(),
      dim=-1,
    )
    kl_latent = -0.5 * torch.mean(kl_per_sample * live_mask.squeeze(-1))
    # The source update regularizes only the stochastic latent branch; the
    # explicit velocity branch is supervised directly and has no KL penalty.
    return velocity + reconstruction + kl_latent


class DreamWaQActorModel(_ConditionalActor):
  latent_kind = "dreamwaq"


__all__ = ["DreamWaQActorCritic", "DreamWaQActorModel", "DreamWaQVAE"]
