"""Small, dependency-light continuous-control agents for the local adapter.

The public interface mirrors the runner boundary used by mjlab/RoboLab.  This
keeps the Web and CLI independent from an algorithm implementation while the
native mjlab/rsl-rl runner can be selected by a future adapter.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Normal


@dataclass
class OffPolicyConfig:
    learning_rate: float = 3e-4
    gamma: float = 0.99
    tau: float = 0.005
    batch_size: int = 256
    replay_size: int = 100_000
    alpha: float = 0.2
    policy_delay: int = 2
    exploration_noise: float = 0.1
    target_noise: float = 0.2
    target_noise_clip: float = 0.5


class _MLP(nn.Module):
    def __init__(self, input_dim: int, output_dim: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 256), nn.ReLU(),
            nn.Linear(256, 256), nn.ReLU(),
            nn.Linear(256, output_dim),
        )

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return self.net(value)


class _TwinQ(nn.Module):
    def __init__(self, obs_dim: int, action_dim: int):
        super().__init__()
        self.q1 = _MLP(obs_dim + action_dim, 1)
        self.q2 = _MLP(obs_dim + action_dim, 1)

    def forward(self, obs: torch.Tensor, action: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        values = torch.cat([obs, action], dim=-1)
        return self.q1(values), self.q2(values)


class _ReplayBuffer:
    def __init__(self, capacity: int, obs_dim: int, action_dim: int):
        self.capacity = max(1, int(capacity))
        self.obs = np.zeros((self.capacity, obs_dim), dtype=np.float32)
        self.actions = np.zeros((self.capacity, action_dim), dtype=np.float32)
        self.rewards = np.zeros(self.capacity, dtype=np.float32)
        self.next_obs = np.zeros((self.capacity, obs_dim), dtype=np.float32)
        self.dones = np.zeros(self.capacity, dtype=np.float32)
        self.position = 0
        self.size = 0

    def add(self, obs, action, reward, next_obs, done) -> None:
        count = len(obs)
        for index in range(count):
            slot = self.position
            self.obs[slot] = obs[index]
            self.actions[slot] = action[index]
            self.rewards[slot] = reward[index]
            self.next_obs[slot] = next_obs[index]
            self.dones[slot] = done[index]
            self.position = (self.position + 1) % self.capacity
            self.size = min(self.size + 1, self.capacity)

    def sample(self, batch_size: int, device: str) -> tuple[torch.Tensor, ...]:
        indices = np.random.randint(0, self.size, size=min(batch_size, self.size))
        return tuple(torch.from_numpy(value[indices]).to(device) for value in (
            self.obs, self.actions, self.rewards[:, None], self.next_obs, self.dones[:, None]
        ))


class OffPolicyAlgorithm:
    """Common SAC/TD3 runner boundary with real replay and critic updates."""

    name = "off_policy"

    def __init__(self, num_obs: int, num_actions: int, config: OffPolicyConfig, device: str = "cpu"):
        self.num_obs = num_obs
        self.num_actions = num_actions
        self.config = config
        self.device = device
        self.actor = _MLP(num_obs, num_actions).to(device)
        self.actor_target = _MLP(num_obs, num_actions).to(device)
        self.actor_target.load_state_dict(self.actor.state_dict())
        self.critic = _TwinQ(num_obs, num_actions).to(device)
        self.critic_target = _TwinQ(num_obs, num_actions).to(device)
        self.critic_target.load_state_dict(self.critic.state_dict())
        self.actor_optimizer = torch.optim.Adam(self.actor.parameters(), lr=config.learning_rate)
        self.critic_optimizer = torch.optim.Adam(self.critic.parameters(), lr=config.learning_rate)
        self.replay = _ReplayBuffer(config.replay_size, num_obs, num_actions)
        self.update_count = 0
        self.log_alpha = torch.tensor(np.log(max(config.alpha, 1e-5)), device=device, requires_grad=self.name == "SAC")
        self.alpha_optimizer = torch.optim.Adam([self.log_alpha], lr=config.learning_rate) if self.name == "SAC" else None
        self.target_entropy = -float(num_actions)

    def _soft_update(self, source: nn.Module, target: nn.Module) -> None:
        tau = self.config.tau
        for target_param, source_param in zip(target.parameters(), source.parameters()):
            target_param.data.mul_(1.0 - tau).add_(tau * source_param.data)

    def _policy_action(self, obs: torch.Tensor, deterministic: bool) -> tuple[torch.Tensor, torch.Tensor]:
        raise NotImplementedError

    def act(self, obs: np.ndarray, deterministic: bool = False) -> tuple[np.ndarray, np.ndarray]:
        obs_tensor = torch.from_numpy(np.asarray(obs, dtype=np.float32)).to(self.device)
        with torch.no_grad():
            action, value = self._policy_action(obs_tensor, deterministic)
        return action.cpu().numpy(), value.cpu().numpy()

    def add_transition(self, obs, actions, rewards, next_obs, dones) -> None:
        self.replay.add(obs, actions, rewards, next_obs, dones)

    def update(self) -> dict[str, float]:
        if self.replay.size == 0:
            return {"critic_loss": 0.0, "actor_loss": 0.0, "buffer_size": 0.0}
        obs, actions, rewards, next_obs, dones = self.replay.sample(self.config.batch_size, self.device)
        with torch.no_grad():
            next_action, next_log_prob = self._policy_action(next_obs, deterministic=False)
            target_q1, target_q2 = self.critic_target(next_obs, next_action)
            target_q = torch.minimum(target_q1, target_q2)
            if self.name == "SAC":
                target_q = target_q - self.log_alpha.exp().detach() * next_log_prob
            target = rewards + self.config.gamma * (1.0 - dones) * target_q
        q1, q2 = self.critic(obs, actions)
        critic_loss = F.mse_loss(q1, target) + F.mse_loss(q2, target)
        self.critic_optimizer.zero_grad()
        critic_loss.backward()
        self.critic_optimizer.step()
        self.update_count += 1
        actor_loss_value = 0.0
        if self.update_count % max(1, self.config.policy_delay) == 0:
            policy_action, log_prob = self._policy_action(obs, deterministic=False)
            q1_pi, q2_pi = self.critic(obs, policy_action)
            if self.name == "SAC":
                actor_loss = (self.log_alpha.exp().detach() * log_prob - torch.minimum(q1_pi, q2_pi)).mean()
                alpha_loss = -(self.log_alpha * (log_prob.detach() + self.target_entropy)).mean()
                self.alpha_optimizer.zero_grad()
                alpha_loss.backward()
                self.alpha_optimizer.step()
            else:
                actor_loss = -torch.minimum(q1_pi, q2_pi).mean()
            self.actor_optimizer.zero_grad()
            actor_loss.backward()
            self.actor_optimizer.step()
            actor_loss_value = float(actor_loss.detach().cpu())
            self._soft_update(self.actor, self.actor_target)
            self._soft_update(self.critic, self.critic_target)
        return {
            "critic_loss": float(critic_loss.detach().cpu()),
            "actor_loss": actor_loss_value,
            "buffer_size": float(self.replay.size),
        }

    def save(self, path: str) -> None:
        checkpoint = {
            "algorithm": self.name,
            "actor": self.actor.state_dict(),
            "actor_target": self.actor_target.state_dict(),
            "critic": self.critic.state_dict(),
            "critic_target": self.critic_target.state_dict(),
            "actor_optimizer": self.actor_optimizer.state_dict(),
            "critic_optimizer": self.critic_optimizer.state_dict(),
            "log_alpha": self.log_alpha.detach().cpu(),
            "alpha_optimizer": self.alpha_optimizer.state_dict() if self.alpha_optimizer else None,
            "update_count": self.update_count,
            "config": asdict(self.config),
        }
        if hasattr(self, "actor_log_std"):
            checkpoint["actor_log_std"] = self.actor_log_std.state_dict()
        torch.save(checkpoint, path)

    def load(self, path: str) -> None:
        checkpoint = torch.load(path, map_location=self.device, weights_only=False)
        if checkpoint.get("algorithm") != self.name:
            raise ValueError(f"checkpoint algorithm {checkpoint.get('algorithm')} does not match {self.name}")
        self.actor.load_state_dict(checkpoint["actor"])
        self.actor_target.load_state_dict(checkpoint.get("actor_target", checkpoint["actor"]))
        self.critic.load_state_dict(checkpoint["critic"])
        self.critic_target.load_state_dict(checkpoint.get("critic_target", checkpoint["critic"]))
        if hasattr(self, "actor_log_std"):
            if "actor_log_std" not in checkpoint:
                raise ValueError("SAC checkpoint is missing actor_log_std")
            self.actor_log_std.load_state_dict(checkpoint["actor_log_std"])
        if checkpoint.get("actor_optimizer"):
            self.actor_optimizer.load_state_dict(checkpoint["actor_optimizer"])
        if checkpoint.get("critic_optimizer"):
            self.critic_optimizer.load_state_dict(checkpoint["critic_optimizer"])
        if checkpoint.get("log_alpha") is not None:
            self.log_alpha.data.copy_(checkpoint["log_alpha"].to(self.device))
        if self.alpha_optimizer and checkpoint.get("alpha_optimizer"):
            self.alpha_optimizer.load_state_dict(checkpoint["alpha_optimizer"])
        self.update_count = int(checkpoint.get("update_count", 0))


class SACAlgorithm(OffPolicyAlgorithm):
    name = "SAC"

    def __init__(self, num_obs: int, num_actions: int, config: OffPolicyConfig, device: str = "cpu"):
        super().__init__(num_obs, num_actions, config, device)
        self.actor_log_std = _MLP(num_obs, num_actions).to(device)
        self.actor_optimizer = torch.optim.Adam(
            list(self.actor.parameters()) + list(self.actor_log_std.parameters()),
            lr=config.learning_rate,
        )

    def _policy_action(self, obs: torch.Tensor, deterministic: bool) -> tuple[torch.Tensor, torch.Tensor]:
        mean = self.actor(obs)
        log_std = torch.clamp(self.actor_log_std(obs), -5.0, 2.0)
        std = log_std.exp()
        distribution = Normal(mean, std)
        raw = mean if deterministic else distribution.rsample()
        action = torch.tanh(raw)
        log_prob = distribution.log_prob(raw).sum(-1, keepdim=True)
        log_prob -= torch.log(1.0 - action.pow(2) + 1e-6).sum(-1, keepdim=True)
        return action, log_prob


class TD3Algorithm(OffPolicyAlgorithm):
    name = "TD3"

    def _policy_action(self, obs: torch.Tensor, deterministic: bool) -> tuple[torch.Tensor, torch.Tensor]:
        action = torch.tanh(self.actor(obs))
        if not deterministic:
            action = action + torch.randn_like(action) * self.config.exploration_noise
        return action.clamp(-1.0, 1.0), torch.zeros((obs.shape[0], 1), device=obs.device)
