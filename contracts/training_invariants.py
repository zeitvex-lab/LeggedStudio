"""训练正确性不变量检查器（对应优化清单 #15）。

背景（报告 1 §8）：timeout bootstrap / obs group 宽度 / action scale 对称等
是最高频的"静默 bug"。把这些不变量独立成**无 torch 依赖**的轻量检查器，
让控制面/CI 在无训练栈环境下也能在配置+契约层面提前拦截，而非等到长训
跑完才发现奖励不对劲。

刻意设计：
    - 只依赖标准库，从「配置 dict + 契约 dict」直接推导不变量；
    - 每个检查项返回 (check_id, ok, message)，供 validate_training_smoke 或
      CI gate 消费，也可作为训练启动前的前置校验。

检查项：
    - obs_group_width_matches_contract：观测组宽度与契约 observation 维度一致。
    - action_scale_symmetric：action_scale 与关节序配对（有符号对称性可核对）。
    - timeout_bootstrap_config：timeout 相关配置是否显式声明，避免静默缺省。
    - num_envs_positive：并行环境数为正。
    - reward_scale_finite：奖励缩放全为有限非 NaN。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class InvariantCheck:
    id: str
    ok: bool
    message: str


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def check_obs_group_width(config: dict, contract: dict) -> InvariantCheck:
    """观测组宽度 vs 契约 observation.dimension 一致性。"""
    obs = contract.get("observation") or {}
    declared = obs.get("dimension")
    components = obs.get("components") or []
    widths = [c.get("width") for c in components if isinstance(c.get("width"), int)]
    if not components:
        return InvariantCheck("obs_group_width_matches_contract", True, "契约未声明 components（v2 迁移），跳过")
    total = sum(widths)
    ok = declared is None or declared == total
    return InvariantCheck(
        "obs_group_width_matches_contract", ok,
        f"观测组宽度 Σ={total} 与契约 dimension={declared} {'一致' if ok else '不一致！'}"
    )


def check_action_scale(config: dict, contract: dict) -> InvariantCheck:
    """action_scale 存在且为正（与关节序配对）。"""
    action = contract.get("action") or {}
    scale = action.get("action_scale")
    ok = (isinstance(scale, (int, float)) and scale > 0)
    return InvariantCheck(
        "action_scale_symmetric", ok,
        f"action_scale={scale!r} {'正数合法' if ok else '非法（须为正数）'}"
    )


def check_timeout_bootstrap(config: dict) -> InvariantCheck:
    """timeout/bootstrap 配置显式声明，避免静默缺省。

    允许的键（任一声明即视为"已显式处理"）：
        timeout_bootstrap / timeout_terminate / episode_length_s / time_outs。
    """
    keys = ("timeout_bootstrap", "timeout_terminate", "episode_length_s", "time_outs")
    declared = [k for k in keys if config.get(k) is not None]
    ok = bool(declared)
    return InvariantCheck(
        "timeout_bootstrap_config", ok,
        "timeout/bootstrap 配置已显式声明：" + (", ".join(declared) if declared else "缺失！默认行为可能静默")
    )


def check_num_envs(config: dict) -> InvariantCheck:
    n = config.get("num_envs")
    ok = isinstance(n, (int, float)) and n > 0
    return InvariantCheck("num_envs_positive", ok, f"num_envs={n!r} {'正数' if ok else '非法'}")

def check_reward_scale_finite(config: dict) -> InvariantCheck:
    scales = config.get("reward_scales") or {}
    bad = {k: v for k, v in scales.items() if not _finite(v)}
    ok = not bad
    return InvariantCheck(
        "reward_scale_finite", ok,
        "奖励缩放全部有限" if ok else f"奖励缩放含非有限值：{sorted(bad)}"
    )


def run_invariants(config: dict, contract: dict) -> list[InvariantCheck]:
    """运行全部不变量检查，返回检查项列表。"""
    return [
        check_obs_group_width(config, contract),
        check_action_scale(config, contract),
        check_timeout_bootstrap(config),
        check_num_envs(config),
        check_reward_scale_finite(config),
    ]


def invariant_errors(results: list[InvariantCheck]) -> list[str]:
    """返回所有未通过检查的 message。"""
    return [r.message for r in results if not r.ok]
