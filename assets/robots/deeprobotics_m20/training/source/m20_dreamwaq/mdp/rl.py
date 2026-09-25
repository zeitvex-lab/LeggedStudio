"""DreamWaQ VAE actor and PPO extension on the installed rsl_rl 5.4.2 API.

Dimensions follow the M20 source: 5 x 57 = 285 history fields into the VAE
(the source derives this as ``num_obs_hist * num_observations``),
16 stochastic latent dims + 3 explicit velocity dims, a 57-field decoder, and
a 57 + 19 = 76-field actor input.
"""

from itertools import chain

import torch
from rsl_rl.algorithms import PPO
from rsl_rl.models import MLPModel
from rsl_rl.storage import RolloutStorage
from tensordict import TensorDict

from ..constants import HISTORY_OBS_DIM, OBS_FRAME_DIM


class _VAE(torch.nn.Module):
  """The source's 285->(3+16) VAE with a 57-field decoder.

  Widths come from :mod:`m20_dreamwaq.constants` (帧宽 × 历史长), never from a
  literal: the encoder and the history observation group must agree by
  construction.  A hard-coded 225 (the upstream VAE's *default* for a 45-field
  frame) silently mismatched this robot's 57-field frame and crashed the first
  PPO update.
  """

  def __init__(
    self,
    in_dim: int = HISTORY_OBS_DIM,
    latent_dim: int = 16,
    explicit_dim: int = 3,
    decode_dim: int = OBS_FRAME_DIM,
  ) -> None:
    super().__init__()
    self.encoder = torch.nn.Sequential(
      torch.nn.Linear(in_dim, 128), torch.nn.ELU(), torch.nn.Linear(128, 64), torch.nn.ELU()
    )
    self.mean_latent = torch.nn.Linear(64, latent_dim)
    self.logvar_latent = torch.nn.Sequential(torch.nn.Linear(64, latent_dim), torch.nn.Hardtanh(-5.0, 5.0))
    self.mean_vel = torch.nn.Linear(64, explicit_dim)
    self.logvar_vel = torch.nn.Sequential(torch.nn.Linear(64, explicit_dim), torch.nn.Hardtanh(-5.0, 5.0))
    self.decoder = torch.nn.Sequential(
      torch.nn.Linear(latent_dim + explicit_dim, 128),
      torch.nn.ELU(),
      torch.nn.Linear(128, 128),
      torch.nn.ELU(),
      torch.nn.Linear(128, decode_dim),
    )

  def forward(
    self, history: torch.Tensor, sample: bool
  ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    encoded = self.encoder(history)
    mean_latent, logvar_latent = self.mean_latent(encoded), self.logvar_latent(encoded)
    mean_vel, logvar_vel = self.mean_vel(encoded), self.logvar_vel(encoded)
    if sample:
      latent = mean_latent + torch.randn_like(mean_latent) * torch.exp(0.5 * logvar_latent)
      velocity = mean_vel + torch.randn_like(mean_vel) * torch.exp(0.5 * logvar_vel)
    else:
      latent, velocity = mean_latent, mean_vel
    code = torch.cat((velocity, latent), dim=-1)
    return code, velocity, self.decoder(code), mean_latent, logvar_latent


class DreamWaQActor(MLPModel):
  """57-field policy augmented with the source 3+16-dimensional VAE code."""

  def __init__(self, *args, **kwargs) -> None:
    super().__init__(*args, **kwargs)
    self.vae = _VAE()

  def _get_latent_dim(self) -> int:
    return 57 + 19

  def get_latent(self, obs: TensorDict, masks=None, hidden_state=None) -> torch.Tensor:
    del masks, hidden_state
    actor = torch.cat([obs[name] for name in self.obs_groups], dim=-1)
    actor = self.obs_normalizer(actor)
    # Source samples in PPO rollout/update and uses posterior means in play.
    code, _, _, _, _ = self.vae(obs["history"], sample=self.training)
    return torch.cat((code, actor), dim=-1)


class _LiveBatchRolloutStorage(RolloutStorage):
  """RolloutStorage whose feed-forward mini-batches also carry ``dones``.

  rsl_rl 5.4.2's ``Batch`` has a ``dones`` field but the stock generator
  leaves it unset; the source DreamWaQ needs it to mask VAE losses at
  episode boundaries.
  """

  def mini_batch_generator(self, num_mini_batches: int, num_epochs: int = 8):
    if self.training_type != "rl":
      raise ValueError("This function is only available for reinforcement learning training.")
    batch_size = self.num_envs * self.num_transitions_per_env
    mini_batch_size = batch_size // num_mini_batches
    indices = torch.randperm(num_mini_batches * mini_batch_size, requires_grad=False, device=self.device)

    observations = self.observations.flatten(0, 1)
    dones = self.dones.flatten(0, 1).float()
    actions = self.actions.flatten(0, 1)
    values = self.values.flatten(0, 1)
    returns = self.returns.flatten(0, 1)
    old_actions_log_prob = self.actions_log_prob.flatten(0, 1)
    advantages = self.advantages.flatten(0, 1)
    old_distribution_params = tuple(p.flatten(0, 1) for p in self.distribution_params)  # type: ignore

    for epoch in range(num_epochs):
      for i in range(num_mini_batches):
        batch_idx = indices[i * mini_batch_size : (i + 1) * mini_batch_size]
        yield RolloutStorage.Batch(
          observations=observations[batch_idx],  # type: ignore
          dones=dones[batch_idx],
          actions=actions[batch_idx],
          values=values[batch_idx],
          advantages=advantages[batch_idx],
          returns=returns[batch_idx],
          old_actions_log_prob=old_actions_log_prob[batch_idx],
          old_distribution_params=tuple(p[batch_idx] for p in old_distribution_params),
        )


class DreamWaQPPO(PPO):
  """PPO plus the source's separate VAE reconstruction/velocity/KL update."""

  def __init__(self, *args, vae_learning_rate: float = 1e-3, vae_kl_weight: float = 1.0, **kwargs) -> None:
    super().__init__(*args, **kwargs)
    self.vae_kl_weight = vae_kl_weight
    # Gym's PPO optimizer deliberately excludes VAE parameters.
    vae_ids = {id(p) for p in self.actor.vae.parameters()}  # type: ignore[attr-defined]
    policy_params = (p for p in chain(self.actor.parameters(), self.critic.parameters()) if id(p) not in vae_ids)
    self.optimizer = torch.optim.Adam(policy_params, lr=self.learning_rate)
    self.vae_optimizer = torch.optim.Adam(self.actor.vae.parameters(), lr=vae_learning_rate)  # type: ignore[attr-defined]

  @staticmethod
  def construct_algorithm(obs, env, cfg: dict, device) -> "DreamWaQPPO":
    alg = PPO.construct_algorithm(obs, env, cfg, device)
    # Upgrade the storage created by the stock factory so mini-batches carry
    # per-sample dones for the live-batch VAE mask below.
    alg.storage.__class__ = _LiveBatchRolloutStorage
    return alg

  def update(self) -> dict[str, float]:
    # The VAE does not share parameters with PPO, so running this before the
    # base PPO pass is mathematically equivalent to the source's second
    # optimizer step inside the same loop.
    vae_loss = vel_loss = recon_loss = kl_loss = 0.0
    updates = 0
    for batch in self.storage.mini_batch_generator(self.num_mini_batches, self.num_learning_epochs):
      history = batch.observations["history"]
      target_velocity = batch.observations["velocity"]
      target_frame = batch.observations["critic"][:, -57:]
      _, estimated_velocity, decoded, mean_latent, logvar_latent = self.actor.vae(history, sample=True)  # type: ignore[attr-defined]
      # Source DreamWaQ masks VAE losses with live_batch = 1 - dones: history
      # frames that span a reset boundary carry stale pre-reset context and
      # would poison the latent estimator.
      live_batch = getattr(batch, "dones", None)
      if live_batch is not None:
        live_batch = 1.0 - live_batch.float()
        if live_batch.sum() == 0:
          continue
        velocity_cost = (
          torch.nn.functional.mse_loss(estimated_velocity, target_velocity, reduction="none").mean(dim=-1)
          * live_batch.squeeze(-1)
        ).sum() / live_batch.sum()
        reconstruction_cost = (
          torch.nn.functional.mse_loss(decoded, target_frame, reduction="none").mean(dim=-1)
          * live_batch.squeeze(-1)
        ).sum() / live_batch.sum()
        kl_cost = -0.5 * torch.mean(
          torch.sum(1 + logvar_latent - mean_latent.square() - logvar_latent.exp(), dim=-1) * live_batch.squeeze(-1)
        )
      else:
        velocity_cost = torch.nn.functional.mse_loss(estimated_velocity, target_velocity)
        reconstruction_cost = torch.nn.functional.mse_loss(decoded, target_frame)
        kl_cost = -0.5 * torch.mean(torch.sum(1 + logvar_latent - mean_latent.square() - logvar_latent.exp(), dim=-1))
      loss = velocity_cost + reconstruction_cost + self.vae_kl_weight * kl_cost
      self.vae_optimizer.zero_grad()
      loss.backward()
      torch.nn.utils.clip_grad_norm_(self.actor.vae.parameters(), self.max_grad_norm)  # type: ignore[attr-defined]
      self.vae_optimizer.step()
      vae_loss += loss.item()
      vel_loss += velocity_cost.item()
      recon_loss += reconstruction_cost.item()
      kl_loss += kl_cost.item()
      updates += 1
    result = super().update()
    if updates == 0:
      return result
    result.update(
      {
        "vae": vae_loss / updates,
        "velocity_estimation": vel_loss / updates,
        "reconstruction": recon_loss / updates,
        "vae_kl": kl_loss / updates,
      }
    )
    return result

  def save(self) -> dict:
    result = super().save()
    result["vae_optimizer_state_dict"] = self.vae_optimizer.state_dict()
    return result

  def load(self, loaded_dict: dict, load_cfg: dict | None, strict: bool) -> bool:
    loaded_iteration = super().load(loaded_dict, load_cfg, strict)
    if load_cfg is None and "vae_optimizer_state_dict" in loaded_dict:
      self.vae_optimizer.load_state_dict(loaded_dict["vae_optimizer_state_dict"])
    return loaded_iteration
