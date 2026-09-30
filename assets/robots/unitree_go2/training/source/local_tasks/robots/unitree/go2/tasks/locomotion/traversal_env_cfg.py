# ------------------------------------------------------------------------------
# 四足盲狗越障档案（2026-09-30）：go2 的越障环境装配（**第一台四足**真跑共享越障课程）。
# 与 go2w 版同构（三层口径）：
#   * 机器人侧（本文件调用的包内基座）：go2 的实体/动作/奖励/传感器——包内真值；
#   * 课程侧（两族共享）：竞赛地形集 + 障碍释放课程——取 kits/obstacle_course
#     的**同一个工厂**（与 go2w/b2w/m20/zex-w 同源），包内不复制任何课程数值。
# 盲狗口径：观测 48 维纯本体（无视觉），越障靠课程地形 + 触地反馈。
# ------------------------------------------------------------------------------

"""Go2 traversal task: package-side robot assembly + shared obstacle course."""

from __future__ import annotations

import sys
from pathlib import Path

# 仓库根自举（与包内其它档同一约定）。
for _parent in Path(__file__).resolve().parents:
  if (_parent / "adapters" / "mjlab").is_dir():
    if str(_parent) not in sys.path:
      sys.path.insert(0, str(_parent))
    break

from mjlab.envs import ManagerBasedRlEnvCfg  # noqa: E402

from adapters.mjlab.kits.obstacle_course import (  # noqa: E402
  make_obstacle_course_terrain,
  make_obstacle_release_curriculum,
)

from .velocity import unitree_go2_rough_env_cfg  # noqa: E402


def unitree_go2_traversal_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
  """Go2 盲狗越障（课程驱动）：包内 rough 基座 + 共享越障课程。

  机器人侧沿用本包 ``unitree_go2_rough_env_cfg`` 的实体/动作/奖励/命令装配；
  地形与课程两项整体换成共享越障课程（竞赛地形集 + 障碍释放课程）。
  """
  cfg = unitree_go2_rough_env_cfg(play=play)

  # ---- 共享越障课程（与轮足四机型同一个工厂）----
  cfg.scene.terrain = make_obstacle_course_terrain()
  cfg.curriculum["terrain_levels"] = make_obstacle_release_curriculum(command_name="twist")

  if play:
    # 与包内其它档的 play 口径一致：课程项停用、地形网格收小（观众/预览用）。
    cfg.curriculum = {}
    terrain_generator = cfg.scene.terrain.terrain_generator
    if terrain_generator is not None:
      terrain_generator.curriculum = False
      terrain_generator.num_cols = 5
      terrain_generator.num_rows = 5
      terrain_generator.border_width = 10.0

  return cfg
