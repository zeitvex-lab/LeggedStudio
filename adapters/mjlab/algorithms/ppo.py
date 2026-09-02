"""
PPO Algorithm Implementation
基于 microduck_all 和标准 PPO 实现
"""

import torch
import torch.nn as nn
import torch.optim as optim
from torch.distributions import Normal
import numpy as np
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass


@dataclass
class PPOConfig:
    """PPO 配置"""
    learning_rate: float = 3e-4
    num_steps: int = 24
    num_minibatches: int = 4
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_param: float = 0.2
    entropy_coef: float = 0.01
    value_loss_coef: float = 1.0
    max_grad_norm: float = 1.0
    use_clipped_value_loss: bool = True


class ActorCritic(nn.Module):
    """Actor-Critic 网络"""

    def __init__(
        self,
        num_obs: int,
        num_actions: int,
        hidden_dims: list = None
    ):
        super().__init__()

        if hidden_dims is None:
            hidden_dims = [256, 256, 256]

        self.num_obs = num_obs
        self.num_actions = num_actions

        # Actor 网络
        actor_layers = []
        prev_dim = num_obs
        for dim in hidden_dims:
            actor_layers.extend([
                nn.Linear(prev_dim, dim),
                nn.ELU()
            ])
            prev_dim = dim
        actor_layers.append(nn.Linear(prev_dim, num_actions))
        self.actor = nn.Sequential(*actor_layers)

        # Critic 网络
        critic_layers = []
        prev_dim = num_obs
        for dim in hidden_dims:
            critic_layers.extend([
                nn.Linear(prev_dim, dim),
                nn.ELU()
            ])
            prev_dim = dim
        critic_layers.append(nn.Linear(prev_dim, 1))
        self.critic = nn.Sequential(*critic_layers)

        # 动作标准差（可学习）
        self.std = nn.Parameter(torch.ones(num_actions) * 0.5)

        # 初始化权重
        self.apply(self._init_weights)

    def _init_weights(self, module):
        """权重初始化"""
        if isinstance(module, nn.Linear):
            nn.init.orthogonal_(module.weight, gain=1.0)
            if module.bias is not None:
                nn.init.constant_(module.bias, 0.0)

    def forward(self, obs: torch.Tensor):
        """前向传播（用于推理）"""
        action_mean = self.actor(obs)
        value = self.critic(obs)
        return action_mean, value

    def act(self, obs: torch.Tensor, deterministic: bool = False):
        """采样动作"""
        action_mean, value = self.forward(obs)

        if deterministic:
            action = action_mean
        else:
            dist = Normal(action_mean, self.std.exp())
            action = dist.sample()

        return action, value

    def evaluate_actions(self, obs: torch.Tensor, actions: torch.Tensor):
        """评估动作（用于训练）"""
        action_mean, value = self.forward(obs)

        # 计算 log prob
        dist = Normal(action_mean, self.std.exp())
        log_prob = dist.log_prob(actions).sum(dim=-1)

        # 计算熵
        entropy = dist.entropy().sum(dim=-1)

        return value, log_prob, entropy


class PPOAlgorithm:
    """
    PPO 算法实现
    基于 microduck_all 和标准 PPO
    """

    def __init__(
        self,
        num_obs: int,
        num_actions: int,
        config: PPOConfig,
        device: str = "cuda" if torch.cuda.is_available() else "cpu"
    ):
        self.config = config
        self.device = device

        # 创建网络
        self.actor_critic = ActorCritic(num_obs, num_actions).to(device)

        # 优化器
        self.optimizer = optim.Adam(
            self.actor_critic.parameters(),
            lr=config.learning_rate
        )

        # 存储
        self.storage = None

    def act(self, obs: np.ndarray, deterministic: bool = False):
        """采样动作"""
        obs_tensor = torch.from_numpy(obs).float().to(self.device)

        with torch.no_grad():
            actions, values = self.actor_critic.act(obs_tensor, deterministic)

        return actions.cpu().numpy(), values.cpu().numpy()

    def act_with_log_prob(self, obs: np.ndarray):
        """Sample actions and retain log probabilities for PPO rollouts."""
        obs_tensor = torch.from_numpy(obs).float().to(self.device)
        with torch.no_grad():
            action_mean, values = self.actor_critic.forward(obs_tensor)
            dist = Normal(action_mean, self.actor_critic.std.exp())
            actions = dist.sample()
            log_probs = dist.log_prob(actions).sum(dim=-1)
        return actions.cpu().numpy(), values.squeeze(-1).cpu().numpy(), log_probs.cpu().numpy()

    def compute_returns(
        self,
        rewards: np.ndarray,
        dones: np.ndarray,
        values: np.ndarray,
        next_values: np.ndarray
    ):
        """计算 GAE returns"""
        num_steps = len(rewards)
        num_envs = rewards.shape[1]

        advantages = np.zeros((num_steps, num_envs), dtype=np.float32)
        returns = np.zeros((num_steps, num_envs), dtype=np.float32)

        gae = np.zeros(num_envs, dtype=np.float32)
        for step in reversed(range(num_steps)):
            if step == num_steps - 1:
                next_value = next_values
            else:
                next_value = values[step + 1]

            delta = rewards[step] + self.config.gamma * next_value * (1 - dones[step]) - values[step]
            gae = delta + self.config.gamma * self.config.gae_lambda * (1 - dones[step]) * gae

            advantages[step] = gae
            returns[step] = advantages[step] + values[step]

        return returns, advantages

    def update(
        self,
        obs: np.ndarray,
        actions: np.ndarray,
        returns: np.ndarray,
        advantages: np.ndarray,
        old_log_probs: np.ndarray
    ) -> Dict[str, float]:
        """PPO 更新"""

        # 转为 tensor
        obs_t = torch.from_numpy(obs).float().to(self.device)
        actions_t = torch.from_numpy(actions).float().to(self.device)
        returns_t = torch.from_numpy(returns).float().to(self.device)
        advantages_t = torch.from_numpy(advantages).float().to(self.device)
        old_log_probs_t = torch.from_numpy(old_log_probs).float().to(self.device)

        # 归一化 advantages
        advantages_t = (advantages_t - advantages_t.mean()) / (advantages_t.std() + 1e-8)

        # Mini-batch 更新
        num_samples = obs.shape[0]
        minibatch_size = num_samples // self.config.num_minibatches

        metrics = {
            "policy_loss": 0.0,
            "value_loss": 0.0,
            "entropy": 0.0,
            "approx_kl": 0.0,
            "clip_fraction": 0.0
        }

        for _ in range(self.config.num_minibatches):
            # 随机采样 mini-batch
            indices = np.random.choice(num_samples, minibatch_size, replace=False)

            mb_obs = obs_t[indices]
            mb_actions = actions_t[indices]
            mb_returns = returns_t[indices]
            mb_advantages = advantages_t[indices]
            mb_old_log_probs = old_log_probs_t[indices]

            # 评估
            values, log_probs, entropy = self.actor_critic.evaluate_actions(mb_obs, mb_actions)

            # Policy loss (PPO clip)
            ratio = torch.exp(log_probs - mb_old_log_probs)
            surr1 = ratio * mb_advantages
            surr2 = torch.clamp(ratio, 1.0 - self.config.clip_param, 1.0 + self.config.clip_param) * mb_advantages
            policy_loss = -torch.min(surr1, surr2).mean()

            # Value loss
            if self.config.use_clipped_value_loss:
                values_clipped = values + torch.clamp(
                    values - mb_returns,
                    -self.config.clip_param,
                    self.config.clip_param
                )
                value_loss1 = (values - mb_returns).pow(2)
                value_loss2 = (values_clipped - mb_returns).pow(2)
                value_loss = torch.max(value_loss1, value_loss2).mean()
            else:
                value_loss = (values - mb_returns).pow(2).mean()

            # Entropy loss
            entropy_loss = -entropy.mean()

            # Total loss
            loss = (
                policy_loss +
                self.config.value_loss_coef * value_loss +
                self.config.entropy_coef * entropy_loss
            )

            # 优化
            self.optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(self.actor_critic.parameters(), self.config.max_grad_norm)
            self.optimizer.step()

            # 记录指标
            with torch.no_grad():
                approx_kl = (mb_old_log_probs - log_probs).mean()
                clip_fraction = ((ratio - 1.0).abs() > self.config.clip_param).float().mean()

            metrics["policy_loss"] += policy_loss.item()
            metrics["value_loss"] += value_loss.item()
            metrics["entropy"] += entropy.mean().item()
            metrics["approx_kl"] += approx_kl.item()
            metrics["clip_fraction"] += clip_fraction.item()

        # 平均
        for key in metrics:
            metrics[key] /= self.config.num_minibatches

        return metrics

    def save(self, path: str):
        """保存模型"""
        torch.save({
            'actor_critic': self.actor_critic.state_dict(),
            'optimizer': self.optimizer.state_dict(),
            'config': self.config
        }, path)

    def load(self, path: str):
        """加载模型"""
        # Checkpoints are produced by this local adapter and intentionally
        # include the PPO config alongside weights for reproducible resumes.
        checkpoint = torch.load(path, map_location=self.device, weights_only=False)
        self.actor_critic.load_state_dict(checkpoint['actor_critic'])
        self.optimizer.load_state_dict(checkpoint['optimizer'])


if __name__ == "__main__":
    # 测试
    config = PPOConfig()
    ppo = PPOAlgorithm(num_obs=48, num_actions=12, config=config)

    # 测试 forward
    obs = np.random.randn(4096, 48).astype(np.float32)
    actions, values = ppo.act(obs)

    print(f"Actions shape: {actions.shape}")
    print(f"Values shape: {values.shape}")
    print(f"Action range: [{actions.min():.2f}, {actions.max():.2f}]")

    # 测试更新
    returns = np.random.randn(4096).astype(np.float32)
    advantages = np.random.randn(4096).astype(np.float32)
    old_log_probs = np.random.randn(4096).astype(np.float32)

    obs_flat = obs
    actions_flat = actions

    metrics = ppo.update(obs_flat, actions_flat, returns, advantages, old_log_probs)

    print("\nUpdate metrics:")
    for key, value in metrics.items():
        print(f"  {key}: {value:.4f}")
