# ------------------------------------------------------------------------------
# 越障技能族级化（2026-09-25）：本文件原先是 zex-w 包**自带正文**的竞赛地形定义
# （RCWallTerrainCfg / RCLowBarTerrainCfg / RCPyramidStairsTerrainCfg）。正文已
# **逐字上移**为 ``adapters/mjlab/kits/wheel_leg_kit/terrains/competition_terrains.py``
# （唯一真值，轮足族级）；包内只留再导出 —— 入口 ``robot.terrains.competition_terrains``
# 与 ``robot.terrains`` 的名字、类身份、构造语义全部不变（同一批类对象）。
#
# 为什么属族级：三个类只描述障碍几何随难度的变化（横墙 / 低杆 / 前移出生点的金字塔
# 台阶），不引用任何机型关节 / 尺寸 / 质量 —— 族内任一机型可用同一套地形定义。
# ------------------------------------------------------------------------------

"""ZEX-W competition terrains —— 薄委托：正文在轮足族 Kit（越障技能族级模块）。"""

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

from adapters.mjlab.kits.wheel_leg_kit.terrains.competition_terrains import (  # noqa: E402, F401
    RCLowBarTerrainCfg,
    RCPyramidStairsTerrainCfg,
    RCWallTerrainCfg,
)
