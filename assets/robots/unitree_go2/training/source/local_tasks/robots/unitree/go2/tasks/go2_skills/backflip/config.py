"""Go2 的后空翻入口（薄委托：族级特技技能）。

族级实现在 `adapters/mjlab/kits/quadruped_kit/skills/backflip/`。本模块只剩三样 go2 事实：

1. **机型绑定** `GO2`（`go2_skills/binding.py`：契约 + `training.xml` 真值 + 本机型训练实体，
   `armature_override=0.0` / 出生高 0.42 是**特技源配方**参数，取证在那个文件的注释里）；
2. **任务数值** `BACKFLIP`（`profile.py`：机型身份 + 几何目标高/速度上限/镜像腿对）；
3. **入口函数**（公开名不动，profile 的 `entrypoints.env/runner` 照旧解析到这里）。

原先本文件里 29 行的装配（平地基座 → 实体 → 传感器 → 延时动作项 → 一次性翻腾命令 →
47/50 维观测历史 → 20 项奖励 → 事件/终止）已整段上移为族级机制，机型侧零字面量。
"""

from __future__ import annotations

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.rl import RslRlOnPolicyRunnerCfg

from adapters.mjlab.kits.quadruped_kit.skills import backflip as kit_backflip

from ..binding import GO2
from .profile import BACKFLIP


def make_backflip_env_cfg(*, play: bool = False) -> ManagerBasedRlEnvCfg:
    return kit_backflip.make_env_cfg(GO2, BACKFLIP, play=play)


def make_backflip_runner_cfg() -> RslRlOnPolicyRunnerCfg:
    return kit_backflip.make_runner_cfg(BACKFLIP)
