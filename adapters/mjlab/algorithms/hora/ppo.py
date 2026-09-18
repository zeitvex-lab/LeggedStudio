# 来源:
#   - HoraPPO 骨架: 00_resources/unilab_new/UniLab/src/unilab/algos/hora/ppo.py (235 行)
#   - PPO update 逻辑: 00_resources/unilab_new/UniLab/src/unilab/algos/rsl_rl_ppo.py
#     (FinalObservationAwarePPO 的非 compile 路径)
# 适配:
#   - 原版 HoraPPO 继承 rsl_rl.algorithms.ppo.PPO（外部包），这里改为**自足实现**:
#     自带 act/process_env_step/compute_returns/update 与 dict 观测的 rollout storage。
#   - 剥掉 tensordict: obs 从 TensorDict 改为普通 dict[str, torch.Tensor]。
#   - 剥掉 rsl_rl.utils.resolve_optimizer → torch.optim.Adam。
#   - hydra 配置改为显式构造参数（新增 build_hora_ppo 工厂替代 construct_algorithm）。
# 删除(未提取, 留 TODO 接口):
#   - RND 内在奖励 (rsl_rl.extensions.RandomNetworkDistillation) —— rnd_cfg 传入即报未实现
#   - symmetry 数据增强 / mirror loss —— symmetry_cfg 传入即报未实现
#   - multi-GPU (multi_gpu_cfg) 分支
#   - torch.compile 快路径 (rsl_rl_ppo.py 的 _minibatch_loss_tensors compile 版)
#   - distill.py / distill_config.py 多阶段蒸馏训练器（见 distill.py 的最小接口）

from __future__ import annotations

import logging
from itertools import chain
from typing import Any, Iterator

import torch
import torch.nn as nn
import torch.optim as optim

from .models import (
    HoraActorModel,
    HoraCriticModel,
    HoraSharedActorCritic,
    build_hora_shared_actor_critic,
)

logger = logging.getLogger(__name__)


class HoraRolloutStorage:
    """dict 观测的 HORA rollout 缓冲（替代 rsl_rl RolloutStorage 的 TensorDict 版）。

    obs_spec: {key: shape_tuple}，例如 {"actor": (45,), "priv_info": (12,)}。
    每个键分配 [T, N, *shape] 张量；minibatch 生成器展平后按索引取样，
    返回 (obs_batch_dict, actions, values, advantages, returns, old_log_prob, old_mu, old_sigma)。
    """

    class Transition:
        def __init__(self) -> None:
            self.observations: dict[str, torch.Tensor] | None = None
            self.actions: torch.Tensor | None = None
            self.values: torch.Tensor | None = None
            self.actions_log_prob: torch.Tensor | None = None
            self.action_mean: torch.Tensor | None = None
            self.action_sigma: torch.Tensor | None = None
            self.rewards: torch.Tensor | None = None
            self.dones: torch.Tensor | None = None

        def clear(self) -> None:
            self.observations = None
            self.actions = None
            self.values = None
            self.actions_log_prob = None
            self.action_mean = None
            self.action_sigma = None
            self.rewards = None
            self.dones = None

    def __init__(
        self,
        num_envs: int,
        num_transitions_per_env: int,
        obs_spec: dict[str, tuple[int, ...]],
        action_dim: int,
        device: str = "cpu",
    ) -> None:
        if "actor" not in obs_spec:
            raise ValueError("obs_spec must contain the 'actor' key")
        self.device = device
        self.num_envs = int(num_envs)
        self.num_transitions_per_env = int(num_transitions_per_env)
        self.action_dim = int(action_dim)
        self.step = 0

        T, N = self.num_transitions_per_env, self.num_envs
        self.obs_buffers = {
            key: torch.zeros(T, N, *shape, device=self.device)
            for key, shape in obs_spec.items()
        }
        self.actions = torch.zeros(T, N, self.action_dim, device=self.device)
        self.rewards = torch.zeros(T, N, 1, device=self.device)
        self.dones = torch.zeros(T, N, 1, device=self.device).bool()
        self.values = torch.zeros(T, N, 1, device=self.device)
        self.actions_log_prob = torch.zeros(T, N, 1, device=self.device)
        self.returns = torch.zeros(T, N, 1, device=self.device)
        self.advantages = torch.zeros(T, N, 1, device=self.device)
        self.mu = torch.zeros(T, N, self.action_dim, device=self.device)
        self.sigma = torch.zeros(T, N, self.action_dim, device=self.device)

    def add_transition(self, transition: Transition) -> None:
        if self.step >= self.num_transitions_per_env:
            raise AssertionError("Rollout buffer overflow")
        if transition.observations is None or transition.actions is None:
            raise ValueError("transition.observations and transition.actions are required")
        if (
            transition.values is None
            or transition.actions_log_prob is None
            or transition.action_mean is None
            or transition.action_sigma is None
            or transition.rewards is None
            or transition.dones is None
        ):
            raise ValueError("transition fields must be fully populated by HoraPPO.act")

        for key, buf in self.obs_buffers.items():
            buf[self.step].copy_(transition.observations[key])
        self.actions[self.step].copy_(transition.actions)
        self.rewards[self.step].copy_(transition.rewards.view(-1, 1))
        self.dones[self.step].copy_(transition.dones.view(-1, 1).bool())
        self.values[self.step].copy_(transition.values)
        self.actions_log_prob[self.step].copy_(transition.actions_log_prob.view(-1, 1))
        self.mu[self.step].copy_(transition.action_mean)
        self.sigma[self.step].copy_(transition.action_sigma)
        self.step += 1

    def clear(self) -> None:
        self.step = 0

    def compute_returns(self, last_values: torch.Tensor, gamma: float, lam: float) -> None:
        advantage = torch.zeros_like(last_values)
        for step in reversed(range(self.num_transitions_per_env)):
            if step == self.num_transitions_per_env - 1:
                next_values = last_values
            else:
                next_values = self.values[step + 1]
            next_is_not_terminal = 1.0 - self.dones[step].float()
            delta = (
                self.rewards[step] + next_is_not_terminal * gamma * next_values - self.values[step]
            )
            advantage = delta + next_is_not_terminal * gamma * lam * advantage
            self.returns[step] = advantage + self.values[step]

        self.advantages = self.returns - self.values
        self.advantages = (self.advantages - self.advantages.mean()) / (
            self.advantages.std() + 1e-8
        )

    def mini_batch_generator(
        self, num_mini_batches: int, num_epochs: int
    ) -> Iterator[tuple[Any, ...]]:
        batch_size = self.num_envs * self.num_transitions_per_env
        mini_batch_size = batch_size // int(num_mini_batches)
        if mini_batch_size <= 0:
            raise ValueError("num_mini_batches is too large for the rollout batch")
        indices = torch.randperm(
            int(num_mini_batches) * mini_batch_size, requires_grad=False, device=self.device
        )

        obs_flat = {key: buf.flatten(0, 1) for key, buf in self.obs_buffers.items()}
        actions = self.actions.flatten(0, 1)
        values = self.values.flatten(0, 1)
        returns = self.returns.flatten(0, 1)
        old_actions_log_prob = self.actions_log_prob.flatten(0, 1)
        advantages = self.advantages.flatten(0, 1)
        old_mu = self.mu.flatten(0, 1)
        old_sigma = self.sigma.flatten(0, 1)

        for _ in range(int(num_epochs)):
            for i in range(int(num_mini_batches)):
                start = i * mini_batch_size
                end = (i + 1) * mini_batch_size
                batch_idx = indices[start:end]
                yield (
                    {key: tensor[batch_idx] for key, tensor in obs_flat.items()},
                    actions[batch_idx],
                    values[batch_idx],
                    advantages[batch_idx],
                    returns[batch_idx],
                    old_actions_log_prob[batch_idx],
                    old_mu[batch_idx],
                    old_sigma[batch_idx],
                )


class HoraPPO:
    """PPO variant that constructs a shared HORA actor-critic backbone.

    自足版: 不再继承 rsl_rl PPO，update/process_env_step 逻辑取自
    FinalObservationAwarePPO 的非 compile 路径 + 原版 HoraPPO 的
    timeout bootstrap / 归一化更新行为。
    """

    def __init__(
        self,
        actor: HoraActorModel,
        critic: HoraCriticModel,
        storage: HoraRolloutStorage,
        num_learning_epochs: int = 5,
        num_mini_batches: int = 4,
        clip_param: float = 0.2,
        gamma: float = 0.99,
        lam: float = 0.95,
        value_loss_coef: float = 1.0,
        entropy_coef: float = 0.01,
        learning_rate: float = 0.001,
        max_grad_norm: float = 1.0,
        use_clipped_value_loss: bool = True,
        schedule: str = "adaptive",
        desired_kl: float = 0.01,
        normalize_advantage_per_mini_batch: bool = False,
        device: str = "cpu",
        rnd_cfg: dict | None = None,
        symmetry_cfg: dict | None = None,
        multi_gpu_cfg: dict | None = None,
        enable_compile: bool = False,
    ) -> None:
        self.device = device
        if multi_gpu_cfg is not None:
            raise NotImplementedError(
                "HORA multi-GPU 分支未提取（原版: hora/ppo.py multi_gpu_cfg / rsl_rl 分布式）"
            )
        if rnd_cfg:
            # TODO(未提取): 原版接 rsl_rl.extensions.RandomNetworkDistillation,
            # 在 process_env_step 中加 intrinsic reward。本轮只留接口。
            raise NotImplementedError("HORA RND 内在奖励未提取（rsl_rl.extensions.RND）")
        if symmetry_cfg is not None:
            # TODO(未提取): 原版支持 data_augmentation_func / mirror_loss 两种对称用法。
            raise NotImplementedError("HORA symmetry 数据增强 / mirror loss 未提取")
        if enable_compile:
            # TODO(未提取): torch.compile 快路径（原版 rsl_rl_ppo.py _compile_training_methods）。
            logger.warning("enable_compile=True 被忽略: torch.compile 路径未提取, 走常规 update")

        self.rnd = None
        self.rnd_optimizer = None
        self.symmetry = None
        self.is_multi_gpu = False

        self.actor = actor.to(self.device)
        self.critic = critic.to(self.device)
        self.optimizer = optim.Adam(
            self._unique_trainable_parameters(), lr=float(learning_rate)
        )
        self.storage = storage
        self.transition = HoraRolloutStorage.Transition()

        self.clip_param = float(clip_param)
        self.num_learning_epochs = int(num_learning_epochs)
        self.num_mini_batches = int(num_mini_batches)
        self.value_loss_coef = float(value_loss_coef)
        self.entropy_coef = float(entropy_coef)
        self.gamma = float(gamma)
        self.lam = float(lam)
        self.max_grad_norm = float(max_grad_norm)
        self.use_clipped_value_loss = bool(use_clipped_value_loss)
        self.desired_kl = desired_kl
        self.schedule = schedule
        self.learning_rate = float(learning_rate)
        self.normalize_advantage_per_mini_batch = bool(normalize_advantage_per_mini_batch)
        self.enable_compile = False

    def _unique_trainable_parameters(self) -> list[torch.nn.Parameter]:
        params: list[torch.nn.Parameter] = []
        seen: set[int] = set()
        for param in chain(self.actor.parameters(), self.critic.parameters()):
            ident = id(param)
            if ident in seen:
                continue
            seen.add(ident)
            params.append(param)
        return params

    def train_mode(self) -> None:
        self.actor.train()
        self.critic.train()

    def act(self, obs: dict[str, torch.Tensor]) -> torch.Tensor:
        actions = self.actor(obs, stochastic_output=True)
        self.transition.observations = obs
        self.transition.actions = actions.detach()
        self.transition.values = self.critic(obs).detach()
        self.transition.actions_log_prob = self.actor.get_output_log_prob(
            self.transition.actions
        ).detach()
        self.transition.action_mean = self.actor.output_mean.detach()
        self.transition.action_sigma = self.actor.output_std.detach()
        return self.transition.actions

    def evaluate(self, obs: dict[str, torch.Tensor]) -> torch.Tensor:
        return self.critic(obs)

    def process_env_step(
        self,
        obs: dict[str, torch.Tensor],
        rewards: torch.Tensor,
        dones: torch.Tensor,
        extras: dict[str, Any],
    ) -> None:
        self.actor.update_normalization(obs)
        # self.critic.update_normalization 为 no-op（特权侧不归一化），保持原版调用面

        self.transition.rewards = rewards.clone()
        self.transition.dones = dones

        timeouts = extras.get("time_outs")
        timeout_bootstrap_obs = extras.get("time_out_bootstrap_obs")
        if isinstance(timeouts, torch.Tensor):
            timeout_mask = timeouts.to(self.device).float()
            can_bootstrap = (
                timeout_bootstrap_obs is not None
                and isinstance(timeout_bootstrap_obs, dict)
                and "priv_info" in timeout_bootstrap_obs
                and torch.count_nonzero(timeout_mask) > 0
            )
            if can_bootstrap:
                bootstrap_obs = timeout_bootstrap_obs
                bootstrap_values = self.critic(bootstrap_obs).detach()
                correction = self.gamma * torch.squeeze(
                    bootstrap_values * timeout_mask.unsqueeze(1), 1
                )
                if self.transition.rewards.ndim == 2 and self.transition.rewards.shape[-1] == 1:
                    correction = correction.unsqueeze(1)
                self.transition.rewards += correction
            else:
                transition_values = self.transition.values
                assert transition_values is not None
                correction = self.gamma * torch.squeeze(
                    transition_values * timeout_mask.unsqueeze(1), 1
                )
                if self.transition.rewards.ndim == 2 and self.transition.rewards.shape[-1] == 1:
                    correction = correction.unsqueeze(1)
                self.transition.rewards += correction

        self.storage.add_transition(self.transition)
        self.transition.clear()
        self.actor.reset(dones)
        self.critic.reset(dones)

    def compute_returns(self, last_obs: dict[str, torch.Tensor]) -> None:
        last_values = self.critic(last_obs).detach()
        self.storage.compute_returns(last_values, self.gamma, self.lam)

    def update(self) -> dict[str, float]:
        mean_value_loss = 0.0
        mean_surrogate_loss = 0.0
        mean_entropy = 0.0

        generator = self.storage.mini_batch_generator(
            self.num_mini_batches, self.num_learning_epochs
        )

        for (
            obs_batch,
            actions_batch,
            values_batch,
            advantages_batch,
            returns_batch,
            old_actions_log_prob_batch,
            old_mu_batch,
            old_sigma_batch,
        ) in generator:
            if self.normalize_advantage_per_mini_batch:
                with torch.no_grad():
                    advantages_batch = (
                        advantages_batch - advantages_batch.mean()
                    ) / (advantages_batch.std() + 1e-8)

            self.actor(obs_batch)  # 更新 distribution 至当前策略
            actions_log_prob_batch = self.actor.get_output_log_prob(actions_batch)
            value_batch = self.critic(obs_batch)
            mu_batch = self.actor.output_mean
            sigma_batch = self.actor.output_std
            entropy_batch = self.actor.output_entropy

            ratio = torch.exp(
                actions_log_prob_batch - torch.squeeze(old_actions_log_prob_batch)
            )
            surrogate = -torch.squeeze(advantages_batch) * ratio
            surrogate_clipped = -torch.squeeze(advantages_batch) * torch.clamp(
                ratio, 1.0 - self.clip_param, 1.0 + self.clip_param
            )
            surrogate_loss = torch.max(surrogate, surrogate_clipped).mean()

            if self.use_clipped_value_loss:
                value_clipped = values_batch + (value_batch - values_batch).clamp(
                    -self.clip_param, self.clip_param
                )
                value_losses = (value_batch - returns_batch).pow(2)
                value_losses_clipped = (value_clipped - returns_batch).pow(2)
                value_loss = torch.max(value_losses, value_losses_clipped).mean()
            else:
                value_loss = (returns_batch - value_batch).pow(2).mean()

            if self.desired_kl is not None and self.schedule == "adaptive":
                with torch.inference_mode():
                    kl = torch.sum(
                        torch.log(sigma_batch / old_sigma_batch + 1e-5)
                        + (old_sigma_batch.pow(2) + (old_mu_batch - mu_batch).pow(2))
                        / (2.0 * sigma_batch.pow(2))
                        - 0.5,
                        dim=-1,
                    )
                    kl_mean = torch.mean(kl)

                    if kl_mean > self.desired_kl * 2.0:
                        self.learning_rate = max(1e-5, self.learning_rate / 1.5)
                    elif kl_mean < self.desired_kl / 2.0 and kl_mean > 0.0:
                        self.learning_rate = min(1e-2, self.learning_rate * 1.5)

                    for param_group in self.optimizer.param_groups:
                        param_group["lr"] = self.learning_rate

            loss = (
                surrogate_loss
                + self.value_loss_coef * value_loss
                - self.entropy_coef * entropy_batch.mean()
            )

            self.optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(self.actor.parameters(), self.max_grad_norm)
            nn.utils.clip_grad_norm_(self.critic.parameters(), self.max_grad_norm)
            self.optimizer.step()

            mean_value_loss += float(value_loss.item())
            mean_surrogate_loss += float(surrogate_loss.item())
            mean_entropy += float(entropy_batch.mean().item())

        num_updates = self.num_learning_epochs * self.num_mini_batches
        self.storage.clear()
        return {
            "value": mean_value_loss / num_updates,
            "surrogate": mean_surrogate_loss / num_updates,
            "entropy": mean_entropy / num_updates,
        }


def build_hora_ppo(
    *,
    obs_dim: int,
    action_dim: int,
    priv_info_dim: int,
    num_envs: int,
    num_steps_per_env: int,
    device: str = "cpu",
    actor_cfg: dict[str, Any] | None = None,
    algorithm_cfg: dict[str, Any] | None = None,
    use_student_encoder: bool = False,
    proprio_hist_len: int = 30,
    proprio_frame_dim: int | None = None,
) -> HoraPPO:
    """显式参数工厂，替代原版 HoraPPO.construct_algorithm（绑定 env/TensorDict/hydra）。

    返回装配好 storage 的 HoraPPO。obs_spec 含 "actor"/"priv_info"，
    启用学生编码器时再加 "proprio_hist"。
    """
    shared_model = build_hora_shared_actor_critic(
        obs_dim=obs_dim,
        action_dim=action_dim,
        priv_info_dim=priv_info_dim,
        actor_cfg=actor_cfg,
    )
    dummy_obs = {
        "actor": torch.zeros(1, obs_dim),
        "priv_info": torch.zeros(1, priv_info_dim),
    }
    actor = HoraActorModel(
        dummy_obs,
        output_dim=action_dim,
        shared_model=shared_model,
        use_student_encoder=use_student_encoder,
        proprio_hist_len=proprio_hist_len,
        proprio_frame_dim=proprio_frame_dim,
    )
    critic = HoraCriticModel(dummy_obs, shared_model=shared_model)

    obs_spec: dict[str, tuple[int, ...]] = {
        "actor": (int(obs_dim),),
        "priv_info": (int(priv_info_dim),),
    }
    if use_student_encoder:
        frame_dim = int(proprio_frame_dim) if proprio_frame_dim is not None else obs_dim // 3
        obs_spec["proprio_hist"] = (int(proprio_hist_len), frame_dim)
    storage = HoraRolloutStorage(
        num_envs=num_envs,
        num_transitions_per_env=num_steps_per_env,
        obs_spec=obs_spec,
        action_dim=int(action_dim),
        device=device,
    )
    algo_cfg = dict(algorithm_cfg or {})
    algo_cfg.pop("class_name", None)
    return HoraPPO(actor, critic, storage, device=device, **algo_cfg)
