"""DeepRobotics M20 越障环境（包内 rough 基座 + 族级越障课程）。

分工（三层口径，见 `adapters/mjlab/kits/wheel_leg_kit/traversal_env_cfg.py` 头注）：

* 机器人侧：本包 ``m20_rough_env_cfg``（官方配方的 rough 档）的实体 / 动作 / 奖励 /
  命令装配 —— 包内真值；
* 课程侧（族级）：竞赛地形集 + 障碍释放课程 —— 取轮足族 Kit 的**同一个课程工厂**
  （与 zex-w-rough / b2w-traversal / go2w-traversal 同源），包内不复制任何课程数值。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 仓库根自举（见 kits/wheel_leg_kit 模块注释）：worker / schema-dump / 冒烟三种运行环境
# 都只把 training/source 或包根放进 sys.path。
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

from .env_cfgs import m20_rough_env_cfg  # noqa: E402


def m20_traversal_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """M20 越障（课程驱动）：包内 rough 基座 + 族级越障课程。"""
    cfg = m20_rough_env_cfg(play=play)

    # ---- 族级越障课程（与 zex-w-rough / b2w-traversal / go2w-traversal 同一个工厂）----
    cfg.scene.terrain = make_obstacle_course_terrain()
    cfg.curriculum["terrain_levels"] = make_obstacle_release_curriculum(
        command_name="twist"
    )

    if play:
        cfg.curriculum = {}
        terrain_generator = cfg.scene.terrain.terrain_generator
        if terrain_generator is not None:
            terrain_generator.curriculum = False
            terrain_generator.num_cols = 5
            terrain_generator.num_rows = 5
            terrain_generator.border_width = 10.0

    return cfg
