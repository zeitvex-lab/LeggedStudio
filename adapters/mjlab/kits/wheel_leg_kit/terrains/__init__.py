"""轮足族竞赛地形（越障技能族级模块的地形定义部分）。

来源 = zex-w 包 ``robot/terrains/``（逐字上移，见 ``competition_terrains.py`` 头注）。
三个类都是**课程级**定义：只描述障碍几何随难度的变化，不引用任何机型关节 / 尺寸 /
质量 —— 族内任一机型可用同一套地形定义装配自己的越障课程。
"""

from .competition_terrains import (
    RCLowBarTerrainCfg,
    RCPyramidStairsTerrainCfg,
    RCWallTerrainCfg,
)

__all__ = ["RCWallTerrainCfg", "RCLowBarTerrainCfg", "RCPyramidStairsTerrainCfg"]
