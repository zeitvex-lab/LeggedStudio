"""Deeprobotics Lite3 的 jump 环境/运行器入口（薄委托：族级技能 + lite3 绑定）。

族级实现在 `adapters/mjlab/kits/quadruped_kit/skills/jump/`（跳跃 = 族级 trot 步态 +
跳跃奖励/终止层，见该模块头注）。本模块只给两样 lite3 事实：

1. **机型绑定** `LITE3_VELOCITY`（复用 `lite3_velocity.binding`：契约 + 包内 MJCF 真值 +
   本机型训练实体）—— 与 `lite3-velocity` 同一份绑定；
2. **任务数值** `LITE3_JUMP`（`jump/profile.py`：机型身份；配方数值沿用族级默认值）。

**Kit 未改一行**：lite3 与 go2 的差异全部由绑定派生吸收 —— 腿标记是 `FL,FR,HL,HR`
（后腿若按"尾字母 R/L 判侧别"会判错；族约定是"含 R 不含 L" ⇒ 右腿仍是 1/3）、
执行器走**MJCF 包装**（`XmlActuatorCfg`，`actuator_source == "asset"`）、腿杆惩罚按
几何名匹配（lite3 的碰撞几何 34/34 具名）、**无足端 site**（族级足端帧 `foot_scan_frames()`
自动回退到 `*_FOOT` body，跳跃不依赖 site 的项照常装配）。
"""

from __future__ import annotations

import sys
from pathlib import Path

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.rl import RslRlOnPolicyRunnerCfg

# 仓库根自举（与 lite3_velocity 同一约定）：worker / schema-dump / 冒烟三种运行环境
# 都只把包根与 training/source 放进 sys.path，不保证仓库根在场。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.kits.quadruped_kit.skills.jump import config as kit_jump  # noqa: E402

from lite3_velocity.binding import LITE3_VELOCITY  # noqa: E402

from .profile import LITE3_JUMP  # noqa: E402


def make_lite3_jump_env_cfg(*, play: bool = False) -> ManagerBasedRlEnvCfg:
    """族级 Jump 技能 + lite3 绑定（入口签名与族级工厂一致）。"""
    return kit_jump.make_env_cfg(LITE3_VELOCITY, LITE3_JUMP, play=play)


def lite3_jump_env_cfg(*, play: bool = False) -> ManagerBasedRlEnvCfg:
    return make_lite3_jump_env_cfg(play=play)


def lite3_jump_runner_cfg() -> RslRlOnPolicyRunnerCfg:
    return kit_jump.make_runner_cfg(LITE3_JUMP)
