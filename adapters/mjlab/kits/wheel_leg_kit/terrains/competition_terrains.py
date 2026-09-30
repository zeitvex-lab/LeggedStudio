# ------------------------------------------------------------------------------
# 2026-09-30 上提转发：三类竞赛地形已上移 kits 共享层（quadruped 盲狗越障共用）。
# ------------------------------------------------------------------------------
"""Re-export shim: obstacle terrain builders live in adapters.mjlab.kits.obstacle_terrains."""

from adapters.mjlab.kits.obstacle_terrains import (  # noqa: F401
    RCWallTerrainCfg,
    RCLowBarTerrainCfg,
    RCPyramidStairsTerrainCfg,
)

__all__ = ["RCWallTerrainCfg", "RCLowBarTerrainCfg", "RCPyramidStairsTerrainCfg"]
