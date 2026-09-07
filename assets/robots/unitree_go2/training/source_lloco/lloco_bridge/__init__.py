"""LLoco (lain_job/LLoco, mjlab==1.6.0) bridge for the Go2 package.

把 LLoco 的 src 根加入 sys.path 后暴露无参 entrypoint 工厂——worker 的
entrypoints 契约要求 ``module:factory`` 且工厂无必选参数；LLoco 的
``make_flat_env_cfg(profile)`` 需要 profile 参数，这里用模块级查表补齐。
LLoco 与本平台 worker 同为 mjlab==1.6.0，训练内核零复制。
"""

from __future__ import annotations

import sys
from pathlib import Path

LLOCO_SRC = Path(r"C:/Users/31560/Documents/00_open/lain_job/LLoco/src")
if str(LLOCO_SRC) not in sys.path:
    sys.path.insert(0, str(LLOCO_SRC))

_PROFILE_BY_KEY = {
    "go2-flat": ("Go2", False),
    "go2-rough": ("Go2", True),
}


def _build(profile_key: str, *, play: bool):
    from lloco.tasks.velocity import PROFILES, make_flat_env_cfg, make_rough_env_cfg

    robot_name, rough = _PROFILE_BY_KEY[profile_key]
    profile = next(p for p in PROFILES if p.task_name == robot_name)
    builder = make_rough_env_cfg if rough else make_flat_env_cfg
    return builder(profile, play=play)


def go2_flat_env_cfg(play: bool = False):
    return _build("go2-flat", play=play)


def go2_rough_env_cfg(play: bool = False):
    return _build("go2-rough", play=play)


def go2_flat_runner_cfg():
    from lloco.tasks.rl import make_ppo_runner_cfg

    return make_ppo_runner_cfg("go2_flat_velocity", max_iterations=10_000)
