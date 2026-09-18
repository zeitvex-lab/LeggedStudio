"""APPO（非对称异步 PPO, IMPACT 风格）—— 从 UniLab appo 提取的纯 torch 核心。

来源: 00_resources/unilab_new/UniLab/src/unilab/algos/appo/ (1701 行)

提取核心 (~700 行):
  - learner.py  APPOLearner（V-trace + target network 软更新 + 自适应 KL 学习率）
               + vtrace_advantages（V-trace 重要性采样修正）
  - models.py  APPOActor（本体观测）/ APPOCritic（特权观测）—— 非对称 actor-critic
               + EmpiricalNormalization / GaussianDistribution 最小纯 torch 实现

关键差异 vs 标准 PPO: actor 只见本体观测，critic 吃特权观测（观测维度可以不同）；
数据异步采集后用 V-trace（rho/c 裁剪 IS 比率）修正 off-policy。

未提取（属训练链/IPC，下轮接）:
  - runner.py / worker.py（子进程 rollout 采集、环境循环）
  - staging.py（RolloutStagingPool 有界缓冲）/ runtime.py

插件面: ``AppoPlugin`` 实现 ``adapters.mjlab.algorithms.base.AlgorithmPlugin``
（4 个 build 方法 + 4 个元数据字段），经 ``registry.json`` 按名 ``"appo"`` 解析。
``AppoActorCritic`` 是把提取核心的 APPOActor/APPOCritic 组合成单模块的适配
包装（提取原件不加改）。
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

from .config import DEFAULT_APPO_CONFIG, AppoAlgorithmConfig
from .learner import APPOLearner, vtrace_advantages
from .models import APPOActor, APPOCritic, EmpiricalNormalization, GaussianDistribution


class AppoActorCritic(nn.Module):
    """Asymmetric actor-critic composite: proprio actor + privileged critic.

    The UniLab runner wires ``APPOActor``/``APPOCritic`` separately; this
    composite gives the plugin protocol its single ``build_actor_critic``
    module without touching the extracted core files.
    """

    is_recurrent = False

    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        critic_dim: int | None = None,
        config: AppoAlgorithmConfig | None = None,
    ) -> None:
        super().__init__()
        config = config or AppoAlgorithmConfig()
        self.obs_dim = int(obs_dim)
        self.action_dim = int(action_dim)
        self.critic_dim = int(critic_dim if critic_dim is not None else obs_dim)
        self.actor = APPOActor(
            self.obs_dim,
            self.action_dim,
            hidden_dims=tuple(config.actor_hidden_dims),
            activation=config.activation,
            init_noise_std=config.init_noise_std,
        )
        self.critic = APPOCritic(
            self.critic_dim,
            hidden_dims=tuple(config.critic_hidden_dims),
            activation=config.activation,
        )

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        return self.actor(obs)


class _AppoDeterministicOnnx(nn.Module):
    """ONNX-safe deterministic APPO policy: ``actor_obs -> actions``."""

    def __init__(self, actor: APPOActor) -> None:
        super().__init__()
        self.actor = actor

    def forward(self, actor_obs: torch.Tensor) -> torch.Tensor:
        return self.actor(actor_obs)


class AppoPlugin(AlgorithmPlugin):
    """Registry entry for the asymmetric async-PPO (IMPACT) family."""

    name = "appo"
    upstream = (
        "UniLab appo (00_resources/unilab_new/UniLab/src/unilab/algos/appo); "
        "IMPACT async-PPO clean torch extraction"
    )
    license = "Apache-2.0 (00_resources/unilab_new/UniLab/LICENSE)"
    supported_obs_types = ("actor", "critic")

    def build_actor_critic(
        self,
        obs_dim: int,
        action_dim: int,
        cfg: Mapping[str, Any] | None = None,
    ) -> nn.Module:
        values = dict(cfg) if cfg else {}
        config = AppoAlgorithmConfig.from_mapping(values)
        return AppoActorCritic(
            obs_dim=obs_dim,
            action_dim=action_dim,
            critic_dim=int(values.get("critic_dim", obs_dim)),
            config=config,
        )

    def build_storage(self, cfg: Mapping[str, Any] | None = None) -> Any:
        # UniLab 侧异步 staging/worker 未提取；先给适配器侧标准 rollout 容器。
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
        config = AppoAlgorithmConfig.from_mapping(cfg)
        return torch.optim.Adam(list(params), lr=config.learning_rate)

    def export_onnx(self, path: str, model: nn.Module | None = None) -> str:
        policy = (
            model
            if isinstance(model, AppoActorCritic)
            else self.build_actor_critic(45, DEFAULT_APPO_CONFIG.action_dim)
        )
        wrapper = _AppoDeterministicOnnx(policy.actor)
        inputs = zeros_like_on(wrapper, ((1, int(policy.obs_dim)),))
        return export_onnx_module(
            wrapper,
            path,
            inputs,
            ("actor_obs",),
            ("actions",),
            batch_axes(("actor_obs",), ("actions",)),
        )


#: Module-level singleton used by the registry loader.
PLUGIN = AppoPlugin()

__all__ = [
    "APPOActor",
    "APPOLearner",
    "APPOCritic",
    "AppoActorCritic",
    "AppoAlgorithmConfig",
    "AppoPlugin",
    "DEFAULT_APPO_CONFIG",
    "EmpiricalNormalization",
    "GaussianDistribution",
    "PLUGIN",
    "vtrace_advantages",
]
