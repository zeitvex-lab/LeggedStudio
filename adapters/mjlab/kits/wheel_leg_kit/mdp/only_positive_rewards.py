"""HIMLoco 系 only_positive_rewards（上游 rc_mjlab 同款，kit 内一份实现）。

机制：patch `RewardManager.compute`，把总步奖励截到 ≥0。上游注释的机理——
早期罚项远超正奖励时，总步奖励深负 → 负优势 → 策略学会"立刻自摔止损"；
截 0 后罚项只能抵消正增益，不再误导优势信号。各项 Episode 统计照记（诊断不受影响）。

开关语义：`enable_*` 是 RewardManager **类级** patch（幂等）；由
`wheel_leg_kit.velocity_env_cfg.make_velocity_env_cfg(only_positive_rewards=True)`
按 profile 数据调用——不是散在各包的手工开关。
"""

from __future__ import annotations

import torch
from mjlab.managers.reward_manager import RewardManager

_original_compute = RewardManager.compute


def _compute_with_clamp(self: RewardManager, dt: float) -> torch.Tensor:
    """Compute step rewards and clamp the final total reward to >= 0."""
    reward = _original_compute(self, dt)
    # In-place clamp on the same buffer reference for consistency with original API
    return torch.clamp(reward, min=0.0)


def enable_only_positive_rewards() -> None:
    """Enable HIMLoco-style positive-only step reward clamping globally.

    Idempotent: calling this multiple times is completely safe.
    """
    if RewardManager.compute is not _compute_with_clamp:
        RewardManager.compute = _compute_with_clamp


def disable_only_positive_rewards() -> None:
    """Disable positive-only step reward clamping, restoring default behavior."""
    if RewardManager.compute is not _original_compute:
        RewardManager.compute = _original_compute
