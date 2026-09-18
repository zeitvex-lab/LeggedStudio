# 来源: 00_resources/unilab_new/UniLab/src/unilab/algos/hora/distill.py (609 行) + distill_config.py (258 行)
# 适配: 多阶段蒸馏训练器（SAC teacher / 分阶段课程 / 检查点管理）**未提取**，
#       本文件只保留最小可用的蒸馏核心接口:
#       - HoraDistillConfig: 显式 dataclass 配置（替代 omegaconf DictConfig 的 distill_config.py）
#       - HoraLatentDistiller: 学生(ProprioAdaptTConv) latent 对教师特权 latent 的
#         对齐损失 —— stage-2 蒸馏的数学核心，纯 torch 可前向可反传
# 删除(未提取, 标注清楚):
#       - HoraDistillationTrainer 多阶段循环 / 阶段调度 / 日志与检查点
#       - SAC teacher 变体 (HoraSACDistillShared, sac_models.py 依赖)
#       - APPO worker 上的在线蒸馏 (appo_worker.py 内嵌 distill 阶段)

from __future__ import annotations

from dataclasses import dataclass, field

import torch
import torch.nn as nn

from .models import HoraSharedActorCritic


@dataclass
class HoraDistillConfig:
    """显式蒸馏配置（替代原 distill_config.py 的 omegaconf 方案）。"""

    latent_loss_coef: float = 1.0
    policy_loss_coef: float = 1.0
    learning_rate: float = 1e-3
    max_grad_norm: float = 1.0
    # 未提取的阶段调度参数占位（原 distill_config.py 的 stages 课程）
    stages: list[dict] = field(default_factory=list)


class HoraLatentDistiller(nn.Module):
    """Stage-2 蒸馏核心: 学生 proprio-history latent 对齐教师特权 latent。"""

    def __init__(
        self,
        shared: HoraSharedActorCritic,
        config: HoraDistillConfig | None = None,
    ) -> None:
        super().__init__()
        if shared.adapt_tconv is None:
            raise ValueError(
                "HoraLatentDistiller requires use_student_encoder=True "
                "(ProprioAdaptTConv) on the shared model"
            )
        self.shared = shared
        self.config = config or HoraDistillConfig()
        self.optimizer = torch.optim.Adam(
            shared.adapt_tconv.parameters(), lr=self.config.learning_rate
        )

    def forward(
        self, priv_info: torch.Tensor, proprio_hist: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """返回 (teacher_latent, student_latent)，均为 tanh 后的 embed 空间。"""
        teacher_latent = self.shared.encode_privileged_info(priv_info)
        student_latent = self.shared.encode_proprio_history(proprio_hist)
        return teacher_latent, student_latent

    def update(
        self, priv_info: torch.Tensor, proprio_hist: torch.Tensor
    ) -> float:
        teacher_latent, student_latent = self(priv_info, proprio_hist)
        loss = self.config.latent_loss_coef * nn.functional.mse_loss(
            student_latent, teacher_latent.detach()
        )
        self.optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(
            self.shared.adapt_tconv.parameters(), self.config.max_grad_norm
        )
        self.optimizer.step()
        return float(loss.item())


class HoraDistillationTrainer:
    """多阶段蒸馏训练器 —— 未提取，仅保留接口占位。

    原版 (distill.py HoraDistillationTrainer) 负责: 阶段调度、teacher 检查点加载、
    AMP 演示数据混合、日志与导出。这些绑定 UniLab runner/hydra 训练链，下轮接。
    """

    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError(
            "HoraDistillationTrainer 多阶段蒸馏训练循环未提取 "
            "(原版: unilab/algos/hora/distill.py)；本轮仅提供 HoraLatentDistiller 核心"
        )
