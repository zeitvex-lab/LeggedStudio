"""Go2 动作项（薄 shim：带延时的关节位置动作已上移族级）。

族级实现：`adapters/mjlab/kits/quadruped_kit/skills/mdp/actions.py`。本模块只按原类名
再导出，`local_tasks.robots.unitree.go2.mdp.Go2DelayedJointPositionActionCfg` 之类的
入口字符串与既有调用方（特技任务的动作观测延时）一律不动。
"""

from __future__ import annotations

from adapters.mjlab.kits.quadruped_kit.skills.mdp.actions import (
  DelayedJointPositionAction as Go2DelayedJointPositionAction,
)
from adapters.mjlab.kits.quadruped_kit.skills.mdp.actions import (
  DelayedJointPositionActionCfg as Go2DelayedJointPositionActionCfg,
)

__all__ = ["Go2DelayedJointPositionAction", "Go2DelayedJointPositionActionCfg"]
