"""HORA (Hybrid Omniscient Retirement Adaptation) —— 从 UniLab hora 提取的纯 torch 核心。

来源: 00_resources/unilab_new/UniLab/src/unilab/algos/hora/ (3845 行)
提取核心 (~950 行):
  - models.py    共享主干 HoraSharedActorCritic / ProprioAdaptTConv / actor-critic 包装
  - ppo.py       HoraPPO（自足 PPO update + dict 观测 HoraRolloutStorage + build_hora_ppo 工厂）
  - modules.py   EmpiricalNormalization + 最小 GaussianDistribution（替代 rsl_rl/unilab.common）
  - distill.py   HoraLatentDistiller（stage-2 latent 对齐核心）+ HoraDistillConfig
未提取（见各文件头注释与 TODO）:
  - AMP 演示数据判别器、多阶段蒸馏训练器（HoraDistillationTrainer 仅留接口）
  - RND 内在奖励 / symmetry 数据增强 / multi-GPU / torch.compile 快路径
  - SAC 分支 (sac*.py)、APPO runner/worker (appo*.py)、rsl_rl 兼容层、runtime

插件面: ``HoraPlugin`` 实现 ``adapters.mjlab.algorithms.base.AlgorithmPlugin``
（4 个 build 方法 + 4 个元数据字段），经 ``registry.json`` 按名 ``"hora"`` 解析。
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

from .config import DEFAULT_HORA_CONFIG, HoraAlgorithmConfig
from .distill import HoraDistillConfig, HoraLatentDistiller, HoraDistillationTrainer
from .models import (
    HoraActorModel,
    HoraCoreOutput,
    HoraCriticModel,
    HoraSharedActorCritic,
    ProprioAdaptTConv,
    build_hora_shared_actor_critic,
)
from .modules import EmpiricalNormalization, GaussianDistribution
from .ppo import HoraPPO, HoraRolloutStorage, build_hora_ppo


class _HoraDeterministicOnnx(nn.Module):
    """ONNX-safe deterministic HORA teacher policy: ``(actor, priv_info) -> actions``.

    Deployment uses the privileged teacher latent path (mean head only); the
    student ``proprio_hist`` adaptation encoder is a training-time option.
    """

    def __init__(self, model: HoraSharedActorCritic) -> None:
        super().__init__()
        self.model = model

    def forward(self, actor: torch.Tensor, priv_info: torch.Tensor) -> torch.Tensor:
        return self.model.policy_mean_from_tensors(
            actor, priv_info, prefer_student=False
        )


class HoraPlugin(AlgorithmPlugin):
    """Registry entry for the HORA shared-backbone family."""

    name = "hora"
    upstream = (
        "UniLab hora (00_resources/unilab_new/UniLab/src/unilab/algos/hora); "
        "HORA clean torch extraction"
    )
    license = "Apache-2.0 (00_resources/unilab_new/UniLab/LICENSE)"
    supported_obs_types = ("actor", "privileged", "history")

    def build_actor_critic(
        self,
        obs_dim: int,
        action_dim: int,
        cfg: Mapping[str, Any] | None = None,
    ) -> nn.Module:
        values = dict(cfg) if cfg else {}
        config = HoraAlgorithmConfig.from_mapping(values)
        return build_hora_shared_actor_critic(
            obs_dim=obs_dim,
            action_dim=action_dim,
            priv_info_dim=int(values.get("priv_info_dim", config.priv_info_dim)),
            actor_cfg={
                "hidden_dims": tuple(config.actor_hidden_dims),
                "activation": config.activation,
                "obs_normalization": config.obs_normalization,
                "priv_info_embed_dim": config.priv_info_embed_dim,
                "priv_mlp_hidden_dims": tuple(config.priv_mlp_hidden_dims),
                "use_student_encoder": config.use_student_encoder,
                "proprio_hist_len": config.proprio_hist_len,
            },
        )

    def build_storage(self, cfg: Mapping[str, Any] | None = None) -> Any:
        values = dict(cfg) if cfg else {}
        config = HoraAlgorithmConfig.from_mapping(values)
        obs_dim = int(values.get("obs_dim", 45))
        priv_info_dim = int(values.get("priv_info_dim", config.priv_info_dim))
        return HoraRolloutStorage(
            num_envs=int(values.get("num_envs", 1)),
            num_transitions_per_env=int(values.get("num_steps", 24)),
            obs_spec={
                "actor": (obs_dim,),
                "priv_info": (priv_info_dim,),
            },
            action_dim=int(values.get("action_dim", config.action_dim)),
            device=values.get("device", "cpu"),
        )

    def build_optimizer(
        self,
        params: Iterable[nn.Parameter],
        cfg: Mapping[str, Any] | None = None,
    ) -> torch.optim.Optimizer:
        config = HoraAlgorithmConfig.from_mapping(cfg)
        return torch.optim.Adam(list(params), lr=config.learning_rate)

    def export_onnx(self, path: str, model: nn.Module | None = None) -> str:
        policy = (
            model
            if isinstance(model, HoraSharedActorCritic)
            else self.build_actor_critic(
                45, DEFAULT_HORA_CONFIG.action_dim
            )
        )
        wrapper = _HoraDeterministicOnnx(policy)
        actor_dim = int(policy.obs_dim)
        priv_dim = int(policy.priv_info_dim)
        inputs = zeros_like_on(wrapper, ((1, actor_dim), (1, priv_dim)))
        return export_onnx_module(
            wrapper,
            path,
            inputs,
            ("actor", "priv_info"),
            ("actions",),
            batch_axes(("actor", "priv_info"), ("actions",)),
        )


#: Module-level singleton used by the registry loader.
PLUGIN = HoraPlugin()

__all__ = [
    "DEFAULT_HORA_CONFIG",
    "EmpiricalNormalization",
    "GaussianDistribution",
    "HoraActorModel",
    "HoraCoreOutput",
    "HoraCriticModel",
    "HoraDistillConfig",
    "HoraDistillationTrainer",
    "HoraLatentDistiller",
    "HoraPlugin",
    "HoraPPO",
    "HoraRolloutStorage",
    "HoraSharedActorCritic",
    "HoraAlgorithmConfig",
    "ProprioAdaptTConv",
    "PLUGIN",
    "build_hora_ppo",
    "build_hora_shared_actor_critic",
]
