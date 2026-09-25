"""Unitree Go2-W 的资产与基座实体配置（机型侧真值）。

技能上移（2026-09-25，族级轮足 velocity）后本模块只剩**族级绑定不覆盖的机型事实**：

* MJCF 来源（``xmls/go2w.xml`` + 训练域规范化）；
* 碰撞方案（``FULL_COLLISION``：轮/足端与机身不同的 condim/friction 那一份）；
* 柔性关节限位系数（0.9）。

**不在这里**：关节名/序、默认姿、PD 谱、动作缩放、出生高 —— 这些来自契约
（``binding.py`` 经族 Kit 派生）。在这里再写一份就是第二处真值（历史上
``GO2W_LEG_JOINT_NAMES`` 等字面元组就是这样长出来的，已随上移删除）。
"""

from __future__ import annotations

from pathlib import Path

import mujoco
from mjlab.entity import EntityArticulationInfoCfg, EntityCfg
from mjlab.utils.spec_config import CollisionCfg

_PACKAGE_DIR = Path(__file__).resolve().parent

##
# MJCF and assets.
##

GO2W_XML: Path = _PACKAGE_DIR / "xmls" / "go2w.xml"


def get_spec() -> mujoco.MjSpec:
    """训练模型的 MJCF 真值（含训练域规范化）。"""
    if not GO2W_XML.exists():
        raise FileNotFoundError(
            f"Go2-W MJCF not found at {GO2W_XML}. "
            "Place your converted go2w.xml and meshes under this package."
        )
    from adapters.mjlab.spec_utils import normalize_for_training

    spec = mujoco.MjSpec.from_file(str(GO2W_XML))
    normalize_for_training(spec)
    return spec


##
# Collision config.
##

FULL_COLLISION = CollisionCfg(
    geom_names_expr=(".*_collision",),
    contype=1,
    conaffinity=0,
    condim={r".*(wheel|foot)_collision$": 3, ".*_collision": 1},
    priority={r".*(wheel|foot)_collision$": 1, ".*": 0},
    friction={r".*(wheel|foot)_collision$": (0.6,)},
)

##
# Base entity config (binding 不覆盖的那部分).
##

#: 柔性关节限位系数（机型真值：执行器谱由契约给，这一项契约不声明）。
SOFT_JOINT_POS_LIMIT_FACTOR = 0.9


def get_go2w_base_entity_cfg() -> EntityCfg:
    """Go2-W 的基座实体配置。

    只带族级绑定**不覆盖**的机型事实：MJCF 来源、碰撞、柔性限位系数。出生高 / 默认姿 /
    执行器谱由 `go2w_velocity.binding.GO2W.robot_cfg()` 按契约填上（见族 Kit 的
    `skills/binding.py` 的 "只覆盖三项" 口径）。
    """
    return EntityCfg(
        collisions=(FULL_COLLISION,),
        spec_fn=get_spec,
        articulation=EntityArticulationInfoCfg(
            actuators=(),
            soft_joint_pos_limit_factor=SOFT_JOINT_POS_LIMIT_FACTOR,
        ),
    )
