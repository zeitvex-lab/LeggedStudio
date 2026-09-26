"""Unitree Lite3 的 小跑步态（trot） 入口（薄委托：族级 Trot 技能 + lite3 绑定）。

族级实现在 `adapters/mjlab/kits/quadruped_kit/skills/trot/`。本模块只给两样 lite3 事实：

1. **机型绑定** `LITE3_VELOCITY`（复用 `lite3_velocity.binding`：契约 + 包内 MJCF 真值 + 本机型训练实体）；
2. **任务数值** `TROT`（`profile.py`：机型身份；其余（周期、目标足高、帧数、PPO 超参）
   与源实现逐值相同）。

**Kit 未改一行**：执行器走 **MJCF 包装**（`XmlActuator`）；腿杆惩罚的匹配面按资产事实选（几何名或结构派生）；
初始姿沿用契约（见 `profile.py` 的口径说明）。lite3 无足端 site（族级足端帧回退到 `*_FOOT` body）
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

from lite3_velocity.binding import LITE3_VELOCITY  # noqa: E402

from .profile import TROT  # noqa: E402


def make_lite3_trot_env_cfg(*, play: bool = False) -> ManagerBasedRlEnvCfg:
    """族级 Trot 技能 + lite3 绑定（入口签名与族级工厂一致）。"""
    return kit_trot.make_env_cfg(LITE3_VELOCITY, TROT, play=play)


def lite3_trot_env_cfg(*, play: bool = False) -> ManagerBasedRlEnvCfg:
    return make_lite3_trot_env_cfg(play=play)


def lite3_trot_runner_cfg() -> RslRlOnPolicyRunnerCfg:
    return kit_trot.make_runner_cfg(TROT)
