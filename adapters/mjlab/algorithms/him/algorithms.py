"""Algorithm surface for the HIM plugin family.

Two layers live here:

- ``HIMPPO`` — the extracted UniLab core (``algorithm.py``, upstream file name),
  re-exported untouched.
- ``HimPPO`` — the mjlab/RSL-RL adapter: an ``rsl_rl`` ``PPO`` subclass that the
  standard ``OnPolicyRunner`` can dispatch via ``cfg.algorithm.class_name``. It
  reproduces the two upstream additions of HIM over plain PPO:

  1. The estimator (owned by :class:`HIMActorModel`) is trained every update
     from ``(obs_history, next_critic_obs)`` minibatches — velocity regression
     plus SwAV-style swap prediction. UniLab couples these steps to the PPO
     minibatches; here RSL-RL owns the PPO loop, so the adapter runs the same
     number of estimator minibatch steps (``epochs × mini_batches``) with its
     own permutation and the shared adaptive learning rate after PPO finishes
     (same PPO-then-auxiliary ordering as the CTS/DreamWaQ adapters).
  2. ``next_critic_obs`` per transition is captured in ``process_env_step`` into
     a preallocated buffer (allocated outside ``torch.inference_mode``; filled
     with ``copy_`` inside it, like the native rollout storage) so the swap
     target aligns row-for-row with the stored actor history.
"""

from __future__ import annotations

import torch

from adapters.mjlab.algorithms.common.auxiliary_ppo import Go2AuxiliaryPPO

from .algorithm import HIMPPO

__all__ = [
    "HIMPPO",
    "HimPPO",
]


class HimPPO(Go2AuxiliaryPPO):
  """RSL-RL-dispatchable HIM-PPO adapter (estimator joint-update phase)."""

  auxiliary_kind = "him"

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    # Allocated here (outside the runner's inference-mode rollout): the buffer
    # is a regular tensor that process_env_step fills via copy_ from the
    # inference-mode observation, mirroring how rsl_rl's own storage works.
    self._him_next_critic = torch.zeros(
      self.storage.num_transitions_per_env,
      self.storage.num_envs,
      int(self.critic.obs_dim),
      device=self.device,
    )
    self._him_next_critic_count = 0

  def process_env_step(self, obs, rewards, dones, extras):
    result = super().process_env_step(obs, rewards, dones, extras)
    next_critic = obs.get("critic") if hasattr(obs, "get") else None
    if isinstance(next_critic, torch.Tensor):
      index = self.storage.step - 1  # transition just stored by the native PPO
      if 0 <= index < self._him_next_critic.shape[0]:
        self._him_next_critic[index].copy_(next_critic.to(self.device))
        self._him_next_critic_count = index + 1
    return result

  def _him_estimator_update(self) -> dict[str, float]:
    count = self._him_next_critic_count
    if count == 0:
      return {}
    actor = self._flat_group(self.storage, "actor")
    estimator = getattr(self.actor, "estimator", None)
    if actor is None or estimator is None:
      return {}
    rows = min(count * self.storage.num_envs, actor.shape[0])
    next_critic = self._him_next_critic.reshape(-1, self._him_next_critic.shape[-1])[:rows]
    history = actor[:rows]
    batch_count = self.num_learning_epochs * self.num_mini_batches
    estimation_total = 0.0
    swap_total = 0.0
    steps = 0
    for indices in torch.randperm(history.shape[0], device=self.device).tensor_split(
      batch_count
    ):
      if indices.numel() == 0:
        continue
      estimation_loss, swap_loss = estimator.update(
        history[indices],
        next_critic[indices],
        lr=self.learning_rate,
      )
      estimation_total += estimation_loss
      swap_total += swap_loss
      steps += 1
    self._him_next_critic_count = 0
    if steps == 0:
      return {}
    return {
      "him_estimation": estimation_total / steps,
      "him_swap": swap_total / steps,
    }

  def _auxiliary_update(self) -> dict[str, float]:
    # HIM keeps the estimator inside the actor module (upstream structure), so
    # no separate auxiliary module is built; only the joint-update phase runs.
    return self._him_estimator_update()

  def save(self) -> dict:
    saved = super().save()
    estimator = getattr(self.actor, "estimator", None)
    if estimator is not None:
      saved["go2_him_estimator_optimizer_state_dict"] = estimator.optimizer.state_dict()
    return saved

  def load(self, loaded_dict: dict, load_cfg: dict | None, strict: bool) -> bool:
    result = super().load(loaded_dict, load_cfg, strict)
    estimator = getattr(self.actor, "estimator", None)
    if estimator is not None and "go2_him_estimator_optimizer_state_dict" in loaded_dict:
      estimator.optimizer.load_state_dict(
        loaded_dict["go2_him_estimator_optimizer_state_dict"]
      )
    return result
