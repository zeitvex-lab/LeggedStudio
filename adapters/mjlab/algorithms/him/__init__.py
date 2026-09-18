"""HIM (Hybrid Internal Model) PPO —— 从 UniLab him_ppo 提取的纯 torch 版本。

来源: 00_resources/unilab_new/UniLab/src/unilab/algos/him_ppo/（HIMLoco 的 UniLab 清洁版）

提取: actor_critic.py / estimator.py / storage.py / algorithm.py（全部核心）
未提取: runner.py（绑定 UniLab env/hydra 训练循环，属训练链，下轮接）

插件面: ``HIMPlugin`` 实现 ``adapters.mjlab.algorithms.base.AlgorithmPlugin``
（4 个 build 方法 + 4 个元数据字段），经 ``registry.json`` 按名 ``"him"`` 解析。
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

from .actor_critic import HIMActorCritic
from .algorithm import HIMPPO
from .config import DEFAULT_HIM_CONFIG, HimAlgorithmConfig
from .estimator import HIMEstimator, get_activation, sinkhorn
from .storage import HIMRolloutStorage


class _HimDeterministicOnnx(nn.Module):
    """ONNX-safe deterministic HIM policy: ``obs_history -> actions``.

    Deployment uses the ``act_inference`` path (estimator velocity/latent
    estimate + actor mean head), never the training-time sampling path.
    """

    def __init__(self, model: HIMActorCritic) -> None:
        super().__init__()
        self.model = model

    def forward(self, obs_history: torch.Tensor) -> torch.Tensor:
        return self.model.act_inference(obs_history)


class HIMPlugin(AlgorithmPlugin):
    """Registry entry for the HIM (hybrid internal model) family."""

    name = "him"
    upstream = (
        "UniLab him_ppo (00_resources/unilab_new/UniLab/src/unilab/algos/"
        "him_ppo); HIMLoco-lineage clean torch extraction"
    )
    license = "Apache-2.0 (00_resources/unilab_new/UniLab/LICENSE)"
    supported_obs_types = ("actor", "critic", "history", "privileged")

    def build_actor_critic(
        self,
        obs_dim: int,
        action_dim: int,
        cfg: Mapping[str, Any] | None = None,
    ) -> nn.Module:
        values = dict(cfg) if cfg else {}
        config = HimAlgorithmConfig.from_mapping(values)
        return HIMActorCritic(
            num_actor_obs=obs_dim,
            num_critic_obs=int(values.get("critic_dim", obs_dim)),
            num_one_step_obs=int(
                values.get("one_step_obs_dim", config.one_step_obs_dim)
            ),
            num_actions=action_dim,
            actor_hidden_dims=tuple(config.actor_hidden_dims),
            critic_hidden_dims=tuple(config.critic_hidden_dims),
            activation=config.activation,
            init_noise_std=config.init_noise_std,
            estimator={
                "learning_rate": config.estimator_learning_rate,
                "num_prototype": config.estimator_num_prototype,
            },
        )

    def build_storage(self, cfg: Mapping[str, Any] | None = None) -> Any:
        values = dict(cfg) if cfg else {}
        obs_dim = int(
            values.get("obs_dim", DEFAULT_HIM_CONFIG.one_step_obs_dim * 5)
        )
        return HIMRolloutStorage(
            num_envs=int(values.get("num_envs", 1)),
            num_transitions_per_env=int(values.get("num_steps", 24)),
            obs_shape=(obs_dim,),
            privileged_obs_shape=(int(values.get("critic_dim", 70)),),
            actions_shape=(
                int(values.get("action_dim", DEFAULT_HIM_CONFIG.action_dim)),
            ),
            device=values.get("device", "cpu"),
        )

    def build_optimizer(
        self,
        params: Iterable[nn.Parameter],
        cfg: Mapping[str, Any] | None = None,
    ) -> torch.optim.Optimizer:
        config = HimAlgorithmConfig.from_mapping(cfg)
        return torch.optim.Adam(list(params), lr=config.learning_rate)

    def export_onnx(self, path: str, model: nn.Module | None = None) -> str:
        policy = (
            model
            if isinstance(model, HIMActorCritic)
            else self.build_actor_critic(
                DEFAULT_HIM_CONFIG.one_step_obs_dim * 5,
                DEFAULT_HIM_CONFIG.action_dim,
            )
        )
        wrapper = _HimDeterministicOnnx(policy)
        inputs = zeros_like_on(wrapper, ((1, int(policy.num_actor_obs)),))
        return export_onnx_module(
            wrapper,
            path,
            inputs,
            ("obs_history",),
            ("actions",),
            batch_axes(("obs_history",), ("actions",)),
        )


#: Module-level singleton used by the registry loader.
PLUGIN = HIMPlugin()

__all__ = [
    "DEFAULT_HIM_CONFIG",
    "HIMActorCritic",
    "HIMEstimator",
    "HIMPPO",
    "HIMPlugin",
    "HIMRolloutStorage",
    "HimAlgorithmConfig",
    "PLUGIN",
    "get_activation",
    "sinkhorn",
]
