"""AMP (Adversarial Motion Prior) model classes.

Moved from ``local_tasks/learning/models.py``; ``local_tasks.learning.models``
re-imports these so its legacy entrypoints keep resolving.
"""

from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F


class AmpDiscriminator(nn.Module):
  """Binary discriminator for motion-reference AMP observations."""

  def __init__(
    self,
    input_dim: int,
    hidden_dims: tuple[int, ...] = (1024, 512),
    amp_reward_coef: float = 0.5,
  ):
    super().__init__()
    self.state_dim = input_dim
    self.amp_reward_coef = float(amp_reward_coef)
    # The legacy AMP discriminator classifies a transition, not an isolated
    # frame: current state and next state are concatenated at its input.
    # It uses LeakyReLU and least-squares targets (+1 expert / -1 policy).
    layers: list[nn.Module] = []
    current_dim = input_dim * 2
    for hidden_dim in hidden_dims:
      layers.extend((nn.Linear(current_dim, hidden_dim), nn.LeakyReLU()))
      current_dim = hidden_dim
    layers.append(nn.Linear(current_dim, 1))
    self.net = nn.Sequential(*layers)

  def forward(
    self, amp_obs: torch.Tensor, next_amp_obs: torch.Tensor | None = None
  ) -> torch.Tensor:
    if next_amp_obs is None:
      next_amp_obs = amp_obs
    return self.net(torch.cat((amp_obs, next_amp_obs), dim=-1))

  def loss(
    self,
    expert: torch.Tensor,
    policy: torch.Tensor,
    expert_next: torch.Tensor | None = None,
    policy_next: torch.Tensor | None = None,
    gradient_penalty_weight: float = 10.0,
  ) -> torch.Tensor:
    expert_logits = self(expert, expert_next)
    policy_logits = self(policy, policy_next)
    expert_loss = F.mse_loss(expert_logits, torch.ones_like(expert_logits))
    policy_loss = F.mse_loss(policy_logits, -torch.ones_like(policy_logits))
    if gradient_penalty_weight <= 0.0:
      return 0.5 * (expert_loss + policy_loss)
    if expert_next is None:
      expert_next = expert
    expert_pair = torch.cat((expert, expert_next), dim=-1).detach().requires_grad_(True)
    expert_prediction = self.net(expert_pair)
    gradient = torch.autograd.grad(
      outputs=expert_prediction,
      inputs=expert_pair,
      grad_outputs=torch.ones_like(expert_prediction),
      create_graph=True,
      retain_graph=True,
      only_inputs=True,
    )[0]
    gradient_penalty = gradient.norm(2, dim=-1).square().mean()
    return (
      0.5 * (expert_loss + policy_loss) + gradient_penalty_weight * gradient_penalty
    )

  def reward(
    self,
    policy: torch.Tensor,
    next_policy: torch.Tensor | None = None,
    normalizer=None,
  ) -> torch.Tensor:
    """Return the source AMP shaping reward for a policy transition."""
    if normalizer is not None:
      policy = normalizer.normalize(policy)
      if next_policy is None:
        next_policy = policy
      else:
        next_policy = normalizer.normalize(next_policy)
    with torch.no_grad():
      logits = self(policy, next_policy)
      amp_reward = (
        0.02
        * self.amp_reward_coef
        * torch.clamp(1.0 - 0.25 * (logits - 1.0).square(), min=0.0)
      )
    return amp_reward.squeeze(-1)


__all__ = ["AmpDiscriminator"]
