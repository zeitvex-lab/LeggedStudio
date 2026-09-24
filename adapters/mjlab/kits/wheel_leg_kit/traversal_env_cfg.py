# ------------------------------------------------------------------------------
# 越障技能族级化（2026-09-25）：本文件是**轮足族越障课程**的唯一真值。
# 来源 = zex-w 包 ``robot/config/env_cfgs.py::rough_env_cfg`` 里内联的
# 「竞赛地形集 + 障碍释放课程」两段（zex-w-rough 档案的课程即此）。
#
# 为什么属族级：这段课程只描述**障碍与课程日程**（地块尺寸 / 障碍规格 / 释放步数），
# 不含任何机型的关节 / 尺寸 / 质量引用；障碍释放课程项
# ``terrain_levels_obstacle_release`` 只依赖 mjlab 的地形与命令管理器接口。
# 机型差异仍留在各自包里（机器人装配 / 动作 / 奖励），课程一律从这里取——
# 这就是"第二台机型训同一套越障课程"的接线点。
#
# 值的三层口径（与 00_know/90_归档/07 的三层接口一致）：
#   族级默认（本文件：竞赛课程规格） → 包覆盖（调用参数，如起始难度行） → profile（档案声明）。
# ------------------------------------------------------------------------------

"""Wheel-leg family obstacle course (competition terrains + obstacle release curriculum)."""

from __future__ import annotations

from mjlab.managers.curriculum_manager import CurriculumTermCfg
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.terrains import (
  BoxFlatTerrainCfg,
  BoxInvertedPyramidStairsTerrainCfg,
  BoxPyramidStairsTerrainCfg,
  BoxRandomGridTerrainCfg,
  HfPerlinNoiseTerrainCfg,
  HfPyramidSlopedTerrainCfg,
  HfRandomUniformTerrainCfg,
  TerrainEntityCfg,
  TerrainGeneratorCfg,
)

from .mdp.terrain_curriculums import terrain_levels_obstacle_release
from .terrains import RCWallTerrainCfg

#: 课程地块尺寸（米）：竞赛场地规格，与机型无关。
COURSE_TILE_SIZE: tuple[float, float] = (8.0, 8.0)

#: 初始可用地形（**未释放**项）：顺序即课程难度递增顺序，释放项依次并入其后。
DEFAULT_INITIAL_TERRAIN_NAMES: tuple[str, ...] = (
  "flat",
  "random_rough",
  "perlin_noise",
  "sloped_terrain",
  "pyramid_stairs",
)

#: 障碍释放日程：(env steps, 新释放的地形名)。步数是 **env steps**（= PPO 迭代 ×
#: num_steps_per_env，族默认 24 ⇒ 4800 = 200 迭代），与档案 ``curriculum`` 里记录的
#: ``terrain_release_env_steps`` 同口径（[4800, random_grid] / [12000, pyramid_stairs_inv]
#: / [16800, rc_wall]）。
DEFAULT_RELEASE_SCHEDULE: tuple[tuple[int, tuple[str, ...]], ...] = (
  (4800, ("random_grid",)),
  (12000, ("pyramid_stairs_inv",)),
  (16800, ("rc_wall",)),
)


def make_obstacle_course_sub_terrains(
  *, size: tuple[float, float] = COURSE_TILE_SIZE
) -> dict:
  """族级竞赛地形集（每次调用**新建**对象：地块 cfg 可被包侧就地调参而不串扰）。"""
  sub_terrains = {
    "flat": BoxFlatTerrainCfg(proportion=0.15, size=size),
    "pyramid_stairs": BoxPyramidStairsTerrainCfg(
      proportion=0.05, step_height_range=(0.0, 0.20), step_width=0.30, size=size
    ),
    "pyramid_stairs_inv": BoxInvertedPyramidStairsTerrainCfg(
      proportion=0.35, step_height_range=(0.0, 0.20), step_width=0.30, size=size
    ),
    "random_grid": BoxRandomGridTerrainCfg(
      proportion=0.27, grid_width=0.45, grid_height_range=(0.0, 0.20), size=size
    ),
    "random_rough": HfRandomUniformTerrainCfg(
      proportion=0.01, noise_range=(0.0, 0.06), noise_step=0.01, horizontal_scale=0.20,
      downsampled_scale=0.20, border_width=0.25, base_thickness_ratio=100.0, size=size,
    ),
    "perlin_noise": HfPerlinNoiseTerrainCfg(
      proportion=0.01, height_range=(0.0, 0.06), octaves=2, persistence=0.4, lacunarity=2.0,
      horizontal_scale=0.20, resolution=0.20, border_width=0.50, base_thickness_ratio=100.0,
      size=size,
    ),
    # 竞赛横墙：真实赛规 1.0m 宽 × 0.3m 高 × 0.05m 厚；难度上限 0.35m 略超赛规。
    "rc_wall": RCWallTerrainCfg(
      proportion=0.15,
      wall_height_range=(0.10, 0.35),
      wall_centers_x=(2.1, 3.2, 4.3, 5.4, 6.5),
      size=size,
    ),
    "sloped_terrain": HfPyramidSlopedTerrainCfg(
      proportion=0.01, slope_range=(0.052, 0.325), platform_width=2.0, border_width=0.25,
      base_thickness_ratio=100.0, horizontal_scale=0.20, size=size,
    ),
  }
  return sub_terrains


def make_obstacle_course_terrain_generator(
  *,
  size: tuple[float, float] = COURSE_TILE_SIZE,
  border_width: float = 20.0,
  num_rows: int = 10,
  num_cols: int = 20,
  curriculum: bool = True,
) -> TerrainGeneratorCfg:
  """族级竞赛地形生成器（course 模式：每类地形一列，难度沿行递增）。"""
  return TerrainGeneratorCfg(
    size=size,
    border_width=border_width,
    num_rows=num_rows,
    num_cols=num_cols,
    curriculum=curriculum,
    sub_terrains=make_obstacle_course_sub_terrains(size=size),
  )


def make_obstacle_course_terrain(
  *,
  max_init_terrain_level: int = 5,
  **generator_overrides,
) -> TerrainEntityCfg:
  """族级越障课程的 terrain 实体（机型侧只需给起始难度行等策略参数）。"""
  return TerrainEntityCfg(
    terrain_type="generator",
    terrain_generator=make_obstacle_course_terrain_generator(**generator_overrides),
    max_init_terrain_level=max_init_terrain_level,
  )


def make_obstacle_release_curriculum(
  *,
  command_name: str,
  initial_terrain_names: tuple[str, ...] = DEFAULT_INITIAL_TERRAIN_NAMES,
  release_schedule: tuple[tuple[int, tuple[str, ...]], ...] = DEFAULT_RELEASE_SCHEDULE,
  asset_cfg: SceneEntityCfg | None = None,
) -> CurriculumTermCfg:
  """族级障碍释放课程项（``terrain_levels``）。

  ``command_name`` 必须显式给（命令名是任务的装配选择，不由 Kit 猜）；其余参数
  缺省即族级竞赛课程日程。
  """
  params: dict = {
    "command_name": command_name,
    "initial_terrain_names": tuple(initial_terrain_names),
    "release_schedule": tuple((int(step), tuple(names)) for step, names in release_schedule),
  }
  if asset_cfg is not None:
    params["asset_cfg"] = asset_cfg
  return CurriculumTermCfg(func=terrain_levels_obstacle_release, params=params)
