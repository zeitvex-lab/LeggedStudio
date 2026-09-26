"""Unitree B2 的弹簧跳（spring_jump）入口（薄委托：族级技能 + b2 绑定）。

族级实现在 `adapters.mjlab.kits.quadruped_kit/skills/spring_jump/`。本模块只给两样 b2 事实：

1. **机型绑定** `B2_VELOCITY`（复用 `b2_velocity.binding`：契约 + `model/robot.xml`
   真值 + 本机型训练实体）—— 与 `b2-velocity` / `b2-wtw` / `b2-cts` / `b2-backflip`
   同一份绑定；
2. **任务数值** `SPRING_JUMP`（`profile.py`：机型身份；配方数值沿用族级默认值）。

**Kit 未改一行**：b2 与 go2 的差异全部由绑定派生吸收 —— 腿序 `FR,FL,RR,RL`、
MJCF 包装执行器（`actuator_source == "asset"` ⇒ 沿用自带执行器）、腿杆惩罚按
**结构**派生 body 集（`penalized_contact_match()`）、镜像腿对（右腿在 0/2 位）。
"""

from __future__ import annotations

import sys
from pathlib import Path

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.rl import RslRlOnPolicyRunnerCfg

# 仓库根自举（与 b2_velocity/binding.py 同一约定）：worker / schema-dump / 冒烟三种运行
# 环境都只把 training/source 或包根放进 sys.path，不保证仓库根在场。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.kits.quadruped_kit.skills.spring_jump import config as kit_skill  # noqa: E402

from b2_velocity.binding import B2_VELOCITY  # noqa: E402

from .profile import SPRING_JUMP  # noqa: E402


def make_b2_spring_jump_env_cfg(*, play: bool = False) -> ManagerBasedRlEnvCfg:
    """族级弹簧跳（spring_jump）技能 + b2 绑定（入口签名与族级工厂一致）。"""
    return kit_skill.make_env_cfg(B2_VELOCITY, SPRING_JUMP, play=play)


def b2_spring_jump_env_cfg(*, play: bool = False) -> ManagerBasedRlEnvCfg:
    return make_b2_spring_jump_env_cfg(play=play)


def b2_spring_jump_runner_cfg() -> RslRlOnPolicyRunnerCfg:
    return kit_skill.make_runner_cfg(SPRING_JUMP)
