"""Go2 复位/随机化事件（薄 shim：两条已上移族级）。

族级实现：`adapters/mjlab/kits/quadruped_kit/skills/mdp/events.py`
（`reset_joints_by_scale_with_velocity` / `torque_multiplier`）。
本模块按原函数名再导出：`reset_joints_by_scale`（乘性关节初值 + 速度抖动区间）
与 `go2_torque_multiplier`（启动期整体 PD 力矩倍率），既有调用方与
`cfg.events[...]` 的参数表一律不动。
"""

from __future__ import annotations

from adapters.mjlab.kits.quadruped_kit.skills.mdp.events import (
  reset_joints_by_scale_with_velocity as reset_joints_by_scale,
)
from adapters.mjlab.kits.quadruped_kit.skills.mdp.events import (
  torque_multiplier as go2_torque_multiplier,
)

__all__ = ["go2_torque_multiplier", "reset_joints_by_scale"]
