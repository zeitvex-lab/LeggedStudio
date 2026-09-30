# ------------------------------------------------------------------------------
# 2026-09-30 上提转发：越障课程工厂已上移 kits 共享层（quadruped 盲狗越障共用同一工厂）。
# 本文件保留同名再导出——go2w / b2w / m20 包侧引用与 registry builder 不变。
# ------------------------------------------------------------------------------
"""Re-export shim: obstacle-course factories live in adapters.mjlab.kits.obstacle_course."""

from adapters.mjlab.kits.obstacle_course import (  # noqa: F401
    COURSE_TILE_SIZE,
    DEFAULT_INITIAL_TERRAIN_NAMES,
    DEFAULT_RELEASE_SCHEDULE,
    make_obstacle_course_sub_terrains,
    make_obstacle_course_terrain_generator,
    make_obstacle_course_terrain,
    make_obstacle_release_curriculum,
)

__all__ = [
    "COURSE_TILE_SIZE",
    "DEFAULT_INITIAL_TERRAIN_NAMES",
    "DEFAULT_RELEASE_SCHEDULE",
    "make_obstacle_course_sub_terrains",
    "make_obstacle_course_terrain_generator",
    "make_obstacle_course_terrain",
    "make_obstacle_release_curriculum",
]
