# ------------------------------------------------------------------------------
# 2026-09-30 上提转发：四函数已上移 kits 共享层（quadruped 盲狗越障共用）。
# 本文件保留同名再导出——zex-w 包 stub 与族内引用不变。
# ------------------------------------------------------------------------------
"""Re-export shim: terrain curricula live in adapters.mjlab.kits.terrain_curriculums."""

from adapters.mjlab.kits.terrain_curriculums import (  # noqa: F401
    terrain_levels_vel_strict,
    terrain_levels_ramp_strict,
    terrain_levels_flat_warmup,
    terrain_levels_obstacle_release,
)

__all__ = [
    "terrain_levels_vel_strict",
    "terrain_levels_ramp_strict",
    "terrain_levels_flat_warmup",
    "terrain_levels_obstacle_release",
]
