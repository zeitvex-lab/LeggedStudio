"""Go2 侧薄委托：事件函数。

族级实现在 `.../quadruped_kit/skills/mdp/events.py`（逐字上移）。
本模块保留一个 go2 专用的标签事件（DreamWaQ 的 PD 增益标签，只有 go2 的这个技能用），
其余一律转出 —— 包内未上移的技能按老路径 `shared.events.*` 继续导入。
"""

from __future__ import annotations

import torch
from mjlab.envs.mdp.events import resolve_env_ids

from adapters.mjlab.kits.quadruped_kit.skills.mdp.events import (
    _scale_joint_field_and_store_label,
    add_root_velocity,
    overwrite_root_velocity,
    reset_joints_by_scale,
    sample_restitution_label,
    scale_joint_damping_and_store_label,
    scale_joint_friction_and_store_label,
    source_friction_buckets,
)

__all__ = [
    "_scale_joint_field_and_store_label",
    "add_root_velocity",
    "dreamwaq_pd_labels",
    "overwrite_root_velocity",
    "reset_joints_by_scale",
    "sample_restitution_label",
    "scale_joint_damping_and_store_label",
    "scale_joint_friction_and_store_label",
    "source_friction_buckets",
]


def dreamwaq_pd_labels(
    env,
    env_ids,
    low: float = 0.9,
    high: float = 1.1,
) -> None:
    """Store the independently sampled source gain multipliers for the critic.

    go2 专用：`_dreamwaq_p_gain/_d_gain` 标签的宽度 = go2 的 12 个关节
    （源实现如此），只有 DreamWaQ 技能读它，故不随家族技能上移。
    """
    ids = resolve_env_ids(env, env_ids)
    for attribute in ("_dreamwaq_p_gain", "_dreamwaq_d_gain"):
        values = getattr(env, attribute, None)
        if values is None:
            values = torch.ones((env.num_envs, 12), device=env.device)
            setattr(env, attribute, values)
        values[ids].uniform_(low, high)
