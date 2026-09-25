"""薄再导出：族级站姿类技能的镜像对称。

2026-09-26 上移：**置换表不再写死**。源里那两张表（动作 12 项、观测 45 项）本质是
"腿对互换 + 髋外展取反"套到帧布局上，已由 `adapters.mjlab.kits.quadruped_kit.skills.
stance.symmetry` 按 4 腿 3 角色派生（**与源表逐值相同**：12/12 与 45/45 已核对）。

本模块只保留再导出：`rear_stand_symmetry`（数据增强函数）与 `SourceSymmetricPPO`
（镜像损失算法类）—— runner 配置按**字符串路径**引用它们，路径不变。
"""

from adapters.mjlab.kits.quadruped_kit.skills.stance.symmetry import (  # noqa: F401
    SourceMirrorSymmetry,
    SourceSymmetricPPO,
    rear_stand_symmetry,
)

__all__ = ["SourceMirrorSymmetry", "SourceSymmetricPPO", "rear_stand_symmetry"]
