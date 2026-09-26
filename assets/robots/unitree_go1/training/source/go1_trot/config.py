"""Unitree Go1 的 小跑步态（trot） 入口（薄委托：族级 Trot 技能 + go1 绑定）。

族级实现在 `adapters/mjlab/kits/quadruped_kit/skills/trot/`。本模块只给两样 go1 事实：

1. **机型绑定** `GO1_VELOCITY`（复用 `go1_velocity.binding`：契约 + 包内 MJCF 真值 + 本机型训练实体）；
2. **任务数值** `TROT`（`profile.py`：机型身份；其余（周期、目标足高、帧数、PPO 超参）
   与源实现逐值相同）。

**Kit 未改一行**：执行器走**契约重建**（`BuiltinPositionActuator`）；腿杆惩罚的匹配面按资产事实选（几何名或结构派生）；
初始姿沿用契约（见 `profile.py` 的口径说明）。go1 无足端 site，族级足端帧自动回退到足端几何位姿（trot 不依赖 site 的项照常装配）
"""

from __future__ import annotations

import sys
from pathlib import Path

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.rl import RslRlOnPolicyRunnerCfg

for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.kits.quadruped_kit.skills.trot import config as kit_trot  # noqa: E402

from go1_velocity.binding import GO1_VELOCITY  # noqa: E402

from .profile import TROT  # noqa: E402


def make_go1_trot_env_cfg(*, play: bool = False) -> ManagerBasedRlEnvCfg:
    """族级 Trot 技能 + go1 绑定（入口签名与族级工厂一致）。"""
    return kit_trot.make_env_cfg(GO1_VELOCITY, TROT, play=play)


def go1_trot_env_cfg(*, play: bool = False) -> ManagerBasedRlEnvCfg:
    return make_go1_trot_env_cfg(play=play)


def go1_trot_runner_cfg() -> RslRlOnPolicyRunnerCfg:
    return kit_trot.make_runner_cfg(TROT)
