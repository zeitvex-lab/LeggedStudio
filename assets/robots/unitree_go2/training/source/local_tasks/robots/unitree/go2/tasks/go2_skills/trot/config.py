"""Go2 侧薄委托：族级 Trot 技能（入口符号不动）。

族级实现在 `adapters/mjlab/kits/quadruped_kit/skills/trot/`。本模块只把 go2 的绑定
接上去 —— 任务配方（观测/奖励/命令/事件/课程/终止）、动作项顺序、传感器装配、
平地起点全部来自 Kit。

包内**未上移**的特技技能（backflip / spring_jump）仍按老签名 `_trot_events(cfg)`
调用本模块（它们不在本次迁移范围）。
"""

from __future__ import annotations

from adapters.mjlab.kits.quadruped_kit.skills.trot import config as _kit_trot

from ..binding import GO2, GO2_TROT
from .profile import TROT


def _trot_events(cfg) -> None:
    """trot / jump 共用的初始事件表（固定到 go2 的绑定）。"""
    _kit_trot.trot_events(cfg, GO2)


def make_trot_env_cfg(*, play: bool = False):
    return _kit_trot.make_env_cfg(GO2_TROT, TROT, play=play)


def make_trot_runner_cfg():
    return _kit_trot.make_runner_cfg(TROT)
