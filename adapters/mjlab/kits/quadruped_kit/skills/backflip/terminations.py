"""后空翻的终止核（源 `backflip/mdp/terminations.py` 同一行实现）。

去机型化：无 —— 只看根 body 高度，阈值由技能 profile 给。
"""

from __future__ import annotations

import torch


def below_reset_height(env, reset_height: float = 0.1) -> torch.Tensor:
    """躯干低于阈值即终止（源配方 0.1 m）。"""
    return env.scene["robot"].data.root_link_pos_w[:, 2] <= reset_height
