"""站姿类技能的镜像对称（rear_stand 用；handstand 无此项）。

来源：`go2_skills/rear_stand/mdp/symmetry.py`。**置换表不再写死**：源里的
`_REAR_STAND_ACTION_INDEX` / `_REAR_STAND_ACTION_SIGN` 与 45 项观测置换，本质是
"腿对互换 + 髋外展取反"套到帧布局上 —— 由族级 `..mdp.symmetry.leg_pair_mirror` /
`frame_mirror` 派生，**派生结果与源表逐值相同**（12/12 与 45/45 已核对）。

留在本模块的是**帧布局常量**（技能配方）：前导 9 列的逐字段镜像符号
（`[0,0, vx,vy,yaw, ωx,ωy,ωz, ...]` 那一串）与"其后 3 个等长关节类段"的结构。
"""

from __future__ import annotations

import torch
from tensordict import TensorDict

from ..mdp.symmetry import (
    SourceMirrorSymmetry,
    SourceSymmetricPPO,
    frame_mirror,
    leg_pair_mirror,
    mirror_obs_and_actions,
)

#: 四足族关节布局：4 腿 × 3 角色（与动作接口序一致）。
LEGS, ROLES = 4, 3

#: 前导 9 列的逐字段镜像符号（源表）：源注释口径是"每个输出列选绝对源列并带符号"，
#: 两个零列、命令与角速度/姿态量的镜像符号逐字段保留。
LEADING_SIGN = (-1, 1, -1, 1, -1, 1, 1, -1, -1)

#: 观测帧里紧跟前导段的等长关节类段个数（q、dq、a 各一段）。
JOINT_BLOCKS = 3

_ACTION_INDEX, _ACTION_SIGN = leg_pair_mirror(LEGS, ROLES)
_OBS_INDEX, _OBS_SIGN = frame_mirror(
    _ACTION_INDEX,
    _ACTION_SIGN,
    leading_index=tuple(range(len(LEADING_SIGN))),
    leading_sign=LEADING_SIGN,
    blocks=JOINT_BLOCKS,
)

__all__ = [
    "SourceMirrorSymmetry",
    "SourceSymmetricPPO",
    "rear_stand_symmetry",
]


def rear_stand_symmetry(
    env,
    obs: TensorDict | None = None,
    actions: torch.Tensor | None = None,
):
    """源 `data_augmentation_func`：把观测与动作各自镜像后追加到 batch 维。"""
    del env
    return mirror_obs_and_actions(
        obs,
        actions,
        obs_index=_OBS_INDEX,
        obs_sign=_OBS_SIGN,
        action_index=_ACTION_INDEX,
        action_sign=_ACTION_SIGN,
        history=1,  # rear_stand 的观测是单帧（history 1），无需 reshape
    )
