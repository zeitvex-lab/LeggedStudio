"""弹簧跳（spring jump）的镜像对称：帧布局常量 + 由族机制派生的置换。

来源：`go2_skills/spring_jump/mdp/symmetry.py`。**置换表不再写死**：源里的
`_INDEX`（47 项）与 `_ACTION_INDEX`（12 项）本质是"腿对互换 + 髋外展取反"，由族级
`..mdp.symmetry.leg_pair_mirror` / `frame_mirror` 按 4 腿 3 角色派生 ——
派生结果与源表**逐值相同**（见 `test_family_backflip_and_spring...` 或对拍记录）。

留在本模块的是**帧布局常量**（技能配方，不是机型数据）：前导 11 列的逐字段镜像符号
（`v_y / ω_x / ω_z / roll / pitch / yaw` 取反），以及"其后 3 个等长关节类段"的结构。
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

#: 前导 11 列的逐字段镜像符号（源表）：`[0,0, vx,vy,yaw, ωx,ωy,ωz, roll,pitch,yaw ]`。
#: 两个零列与 `v_x` 不变；`v_y` / `yaw_rate` / `ω_x` / `ω_z` / `roll` / `pitch` 取反。
LEADING_SIGN = (-1, -1, 1, -1, 1, -1, 1, -1, -1, 1, -1)

_ACTION_INDEX, _ACTION_SIGN = leg_pair_mirror(LEGS, ROLES)
_OBS_INDEX, _OBS_SIGN = frame_mirror(
    _ACTION_INDEX,
    _ACTION_SIGN,
    leading_index=tuple(range(len(LEADING_SIGN))),
    leading_sign=LEADING_SIGN,
    blocks=3,  # 观测帧里紧跟着 3 个等长关节段：q、dq、a（各 12 维）
)

__all__ = [
    "SourceMirrorSymmetry",
    "SourceSymmetricPPO",
    "spring_jump_symmetry",
]


def spring_jump_symmetry(
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
        history=10,
    )
