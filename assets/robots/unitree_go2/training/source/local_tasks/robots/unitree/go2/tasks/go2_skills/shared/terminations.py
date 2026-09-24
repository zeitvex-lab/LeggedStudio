"""Go2 侧薄委托：终止项。

族级实现在 `.../quadruped_kit/skills/mdp/terminations.py`（逐字上移，无机型常量）。
包内未上移的技能按老路径 `shared.terminations.base_contact` 继续导入。
"""

from __future__ import annotations

from adapters.mjlab.kits.quadruped_kit.skills.mdp.terminations import base_contact

__all__ = ["base_contact"]
