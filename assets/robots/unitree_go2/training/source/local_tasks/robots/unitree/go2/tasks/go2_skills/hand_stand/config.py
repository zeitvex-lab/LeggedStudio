"""Go2 的前腿站立/倒立（handstand）入口（薄委托：族级站姿类技能）。

族级实现在 `adapters/mjlab/kits/quadruped_kit/skills/stance/`。本模块只剩三样 go2 事实：

1. **机型绑定** `GO2`（`go2_skills/binding.py`：契约 + `training.xml` 真值 + 本机型训练实体）；
2. **本档数值** `HANDSTAND`（`profile.py`：机型身份 + 几何目标高 / 命令口径 / 事件微调 / runner）；
3. **入口函数**（公开名不动，profile 的 `entrypoints.env/runner` 照旧解析到这里）。

`mdp/`（观测 / 奖励 / 事件 / 命令 / 对称）已整段上移并成为族级薄再导出；
原先 265 行（handstand）/ 354 行（rear_stand）的装配现在由族级 `stance/config.py`
按**奖励档**表达 —— 两档共用同一套装配机制。
"""

from __future__ import annotations

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.rl import RslRlOnPolicyRunnerCfg

from adapters.mjlab.kits.quadruped_kit.skills import stance as kit_stance

from ..binding import GO2
from .profile import HANDSTAND


def make_handstand_env_cfg(*, play: bool = False) -> ManagerBasedRlEnvCfg:
    return kit_stance.make_env_cfg(GO2, HANDSTAND, play=play)


def make_handstand_runner_cfg() -> RslRlOnPolicyRunnerCfg:
    return kit_stance.make_runner_cfg(HANDSTAND)
