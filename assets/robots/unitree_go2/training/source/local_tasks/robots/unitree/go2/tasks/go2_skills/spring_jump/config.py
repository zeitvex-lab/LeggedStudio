"""Go2 的弹簧跳入口（薄委托：族级特技技能）。

族级实现在 `adapters/mjlab/kits/quadruped_kit/skills/spring_jump/`。本模块只剩三样 go2 事实：

1. **机型绑定** `GO2`（`go2_skills/binding.py`：契约 + `training.xml` 真值 + 本机型训练实体）；
2. **任务数值** `SPRING_JUMP`（`profile.py`：机型身份 + 几何目标高 / 阈值 / 髋列 / 足端 site）；
3. **入口函数**（公开名不动，profile 的 `entrypoints.env/runner` 照旧解析到这里）。

`mdp/` 下的包内实现（命令 / 观测 / 奖励 / 事件 / 终止 / 对称）已整段上移并删除；
镜像置换也不再写死 —— 族级按"腿数 × 角色数"派生，派生结果与源表逐值相同。
"""

from __future__ import annotations

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.rl import RslRlOnPolicyRunnerCfg

from adapters.mjlab.kits.quadruped_kit.skills import spring_jump as kit_spring_jump

from ..binding import GO2
from .profile import SPRING_JUMP


def make_spring_jump_env_cfg(*, play: bool = False) -> ManagerBasedRlEnvCfg:
    return kit_spring_jump.make_env_cfg(GO2, SPRING_JUMP, play=play)


def make_spring_jump_runner_cfg() -> RslRlOnPolicyRunnerCfg:
    return kit_spring_jump.make_runner_cfg(SPRING_JUMP)
