# ------------------------------------------------------------------------------
# 越障技能族级化（2026-09-25）：b2w 的**越障档案**环境装配（第二台机型真跑族级越障课程）。
#
# 分工（三层口径，见 kits/wheel_leg_kit/traversal_env_cfg.py 头注）：
#   * 机器人侧（本文件下面调用的包内基座）：B2-W 的实体 / 动作 / 奖励 / 传感器 —— 包内真值；
#   * 课程侧（族级）：竞赛地形集 + 障碍释放课程 —— 取 ``wheel_leg_kit.traversal_env_cfg``
#     的**同一个工厂函数**（与 zex-w-rough 同源），包内不复制任何课程数值。
#
# 为什么这样算"第二台机型真能训同一套越障课程"：课程不是复制一份改改，而是同一个函数
# 在两次装配里被调用（见档案 ``curriculum.course_source`` 标注 + audit_families 的
# 技能矩阵把 b2w 记进 wheel_leg/traversal）。
# ------------------------------------------------------------------------------

"""B2-W traversal task: package-side robot assembly + family-level obstacle course."""

from __future__ import annotations

import sys
from pathlib import Path

# 仓库根自举（见 kits/wheel_leg_kit 模块注释）：worker / schema-dump / 冒烟三种运行
# 环境都只把 ``training/source``（或包根）放进 sys.path；沿目录向上找 ``adapters/mjlab``
# 对 assets 源树与 workspace 镜像副本两种深度都成立。
for _parent in Path(__file__).resolve().parents:
  if (_parent / "adapters" / "mjlab").is_dir():
    if str(_parent) not in sys.path:
      sys.path.insert(0, str(_parent))
    break

from mjlab.envs import ManagerBasedRlEnvCfg  # noqa: E402

from adapters.mjlab.kits.wheel_leg_kit.traversal_env_cfg import (  # noqa: E402
  make_obstacle_course_terrain,
  make_obstacle_release_curriculum,
)

from .env_cfgs import unitree_go2w_rough_env_cfg  # noqa: E402


def b2w_traversal_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
  """B2-W 越障（课程驱动）：包内 rough 基座 + 族级越障课程。

  机器人侧沿用本包 ``unitree_go2w_rough_env_cfg``（速度跟踪 rough 档）的实体 / 动作 /
  奖励 / 命令装配；地形与课程两项整体换成族级越障课程（竞赛地形集 + 障碍释放课程），
  因此包内不再持有任何课程数值。
  """
  cfg = unitree_go2w_rough_env_cfg(play=play)

  # ---- 族级越障课程（与 zex-w-rough 同一个工厂：竞赛地形集 + 障碍释放课程）----
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
