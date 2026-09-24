"""Go2 侧薄委托：特技 MDP 项（供包内未上移的技能按老路径导入）。

族级实现在 `.../quadruped_kit/skills/mdp/`。本包只保留两个 shim 模块：

* `commands` —— backflip / spring_jump 继承的 `RearStandVelocityCommand`；
* `observations` —— 它们复用的 `_SourceHistory` / `contact_observation` / `root_euler`
  与**实体版** `joint_ids`。

原先属于 trot / jump 的 `events` / `curriculums` / `rewards` 已整体上移（族级技能层），
包内不再保留副本 —— 这正是本次迁移要消掉的重复。
"""

from __future__ import annotations

from . import commands, observations  # noqa: F401

__all__ = ["commands", "observations"]
