"""Unitree Go1 的后空翻入口（薄委托：族级特技技能）。

族级实现在 `adapters/mjlab/kits/quadruped_kit/skills/backflip/`。本模块只给两样 go1 事实：

1. **机型绑定** `GO1_VELOCITY`（复用 `go1_velocity.binding`：契约 + 包内 MJCF 真值 +
   本机型训练实体）—— 与 `go1-jump` / `go1-velocity` / `go1-amp` 同一份绑定
   （同一个机器人不建第二份 MJCF/碰撞真值）；出生高 0.42 就来自 `INIT_STATE.pos[2]`，
   与特技源配方的 0.42 同值；
2. **任务数值** `BACKFLIP`（`backflip/profile.py`：机型身份；配方数值沿用族级默认值）。

**Kit 未改一行**：go1 与 go2 的差异全部由绑定派生吸收 —— 执行器走**契约重建**
（go1 的包内 `spec_fn` 先删掉 MJCF 内置 `<position>` 再注入契约 PD，`actuator_source`
判定为 `contract`）、腿杆惩罚按几何名匹配（go1 的碰撞几何 34/34 具名）、
镜像腿对同为 `(1,3)`。go1 **没有足端 site**，但后空翻不依赖足端 site（只依赖足端几何名
`<腿>_foot_collision`）—— 与 velocity 档"按能力撤项"的处置不同，这里不需要撤任何项。
"""

from __future__ import annotations

import sys
from pathlib import Path

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.rl import RslRlOnPolicyRunnerCfg

# 仓库根自举（与 go1_jump / go1_velocity 同一约定）：worker / schema-dump / 冒烟三种
# 运行环境都只把包根与 training/source 放进 sys.path，不保证仓库根在场。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.kits.quadruped_kit.skills import backflip as kit_backflip  # noqa: E402

from go1_velocity.binding import GO1_VELOCITY  # noqa: E402

from .profile import BACKFLIP  # noqa: E402


def make_go1_backflip_env_cfg(*, play: bool = False) -> ManagerBasedRlEnvCfg:
    """族级后空翻技能 + go1 绑定（入口签名与族级工厂一致）。"""
    return kit_backflip.make_env_cfg(GO1_VELOCITY, BACKFLIP, play=play)


def go1_backflip_env_cfg(*, play: bool = False) -> ManagerBasedRlEnvCfg:
    return make_go1_backflip_env_cfg(play=play)


def go1_backflip_runner_cfg() -> RslRlOnPolicyRunnerCfg:
    return kit_backflip.make_runner_cfg(BACKFLIP)
