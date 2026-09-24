"""Go2 侧薄委托：族级特技命令生成器。

族级实现在 `.../quadruped_kit/skills/mdp/commands.py`（逐字上移）。
保留本模块是因为包内**未上移**的技能按老路径继承这里的 `RearStandVelocityCommand`
（backflip / spring_jump 的 mdp/commands.py）。
"""

from __future__ import annotations

from adapters.mjlab.kits.quadruped_kit.skills.mdp.commands import (
    HandstandVelocityCommand,
    HandstandVelocityCommandCfg,
    RearStandVelocityCommand,
    RearStandVelocityCommandCfg,
    TrotVelocityCommand,
    TrotVelocityCommandCfg,
)

__all__ = [
    "HandstandVelocityCommand",
    "HandstandVelocityCommandCfg",
    "RearStandVelocityCommand",
    "RearStandVelocityCommandCfg",
    "TrotVelocityCommand",
    "TrotVelocityCommandCfg",
]
