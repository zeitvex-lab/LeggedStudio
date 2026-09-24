"""Go2 侧薄委托：族级 Jump（特技）技能（入口符号不动）。

族级实现在 `adapters/mjlab/kits/quadruped_kit/skills/jump/`。profile 的入口
（`go2-jump.json` 的 `entrypoints.env/runner`）指向的就是本模块的两个函数 ——
**迁移没有动入口路径**，包侧只剩"机型绑定 + profile"两样机型事实。
"""

from __future__ import annotations

from adapters.mjlab.kits.quadruped_kit.skills.jump import config as _kit_jump

from ..binding import GO2
from .profile import JUMP


def make_jump_env_cfg(*, play: bool = False):
    return _kit_jump.make_env_cfg(GO2, JUMP, play=play)


def make_jump_runner_cfg():
    return _kit_jump.make_runner_cfg(JUMP)
