"""Unitree B2 的 handstand（前腿站立/倒立）入口（薄委托：族级站姿类技能 + b2 绑定）。

族级实现在 `adapters/mjlab/kits/quadruped_kit/skills/stance/`（一份机制 + 两个奖励档）。
本模块只给两样 b2 事实：

1. **机型绑定** `B2_VELOCITY`（复用 `b2_velocity.binding`）—— 与其余 b2 档案同一份绑定；
2. **本档数值** `HANDSTAND`（`profile.py`：机型身份 + 几何目标高 / 命令口径 / 事件微调 / runner）。

**Kit 未改一行**：b2 与 go2 的差异全部由绑定派生吸收 —— 腿序、MJCF 包装执行器、
腿杆惩罚的 body 集（结构派生）、镜像腿对（右腿在 0/2 位）。
"""

from __future__ import annotations

import sys
from pathlib import Path

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.rl import RslRlOnPolicyRunnerCfg

# 仓库根自举（与 b2_velocity/binding.py 同一约定）。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.kits.quadruped_kit.skills import stance as kit_stance  # noqa: E402

from b2_velocity.binding import B2_VELOCITY  # noqa: E402

from .profile import HANDSTAND  # noqa: E402


def make_b2_handstand_env_cfg(*, play: bool = False) -> ManagerBasedRlEnvCfg:
    """族级 handstand 档 + b2 绑定（入口签名与族级工厂一致）。"""
    return kit_stance.make_env_cfg(B2_VELOCITY, HANDSTAND, play=play)


def b2_handstand_env_cfg(*, play: bool = False) -> ManagerBasedRlEnvCfg:
    return make_b2_handstand_env_cfg(play=play)


def b2_handstand_runner_cfg() -> RslRlOnPolicyRunnerCfg:
    return kit_stance.make_runner_cfg(HANDSTAND)
