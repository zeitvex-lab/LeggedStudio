"""薄再导出：族级「站姿类」技能内核（events）。

2026-09-26 上移：本包与 `rear_stand/mdp/events` 的这份文件**逐字节相同** ⇒ 它是技能内核、
不是机型代码，已上移为 `adapters.mjlab.kits.quadruped_kit.skills.stance.events`（唯一真值）。本模块只保留再导出，
公开符号名不变（配置文件按名引用）。

去机型化（在族级那份里）：写死的 go2 关节名/足端几何名 → 族级绑定派生
（关节序走动作项序、足端槽位序走族级足端传感器）。**解析结果与源一致**：
上移前后按"归一化后逐行比对"= 0 差异。
"""

from adapters.mjlab.kits.quadruped_kit.skills.stance.events import *  # noqa: F401, F403
