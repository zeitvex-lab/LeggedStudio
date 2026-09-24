"""Go2 侧薄委托：族级动作项。

族级实现在 `.../quadruped_kit/skills/mdp/actions.py`（逐字上移）。
这里原样转出两个符号，包内未上移的技能（backflip / hand_stand / rear_stand / spring_jump）
继续按 `shared.actions.EpisodeDelayedJointPositionActionCfg` 调用。
"""

from __future__ import annotations

from adapters.mjlab.kits.quadruped_kit.skills.mdp.actions import (
    EpisodeDelayedJointPositionAction,
    EpisodeDelayedJointPositionActionCfg,
)

__all__ = [
    "EpisodeDelayedJointPositionAction",
    "EpisodeDelayedJointPositionActionCfg",
]
