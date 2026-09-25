"""Unitree B2-W 的资产与基座实体配置（机型侧真值）。

族级速度技能上移（2026-09-25）后本模块只剩**族级绑定不覆盖的机型事实**：

* MJCF 来源（``model/robot.xml`` + 训练域规范化）；
* 碰撞方案（``FULL_COLLISION``：轮/足端与机身不同的 condim/friction 那一份）；
* 柔性关节限位系数（0.9）；
* **执行器声明归属 = MJCF**（`mjcf_wrapped`）：本机型 ``model/robot.xml`` 自带
  ``<actuator>`` 段（12 个 ``<position>`` kp=160 kv=5、4 个 ``<velocity>`` kv=1，
  forcerange 200/320/20，armature 0.1 写在 ``<joint>`` 上）——gains/limits 是**资产真值**，
  训练侧只能包装（``XmlActuatorCfg``）、不得重复注册（同名再注册即崩）。
  这条归属随 `binding.py` 的 `from_contract(actuator_binding="mjcf_wrapped")` 传给族 Kit
  （族声明 ``mjcf_conventions.actuator_binding`` 的同词表；本机型的偏离登记待收口）。

**不在这里**：关节名/序、默认姿、动作缩放、出生高 —— 这些来自契约（``binding.py``
经族 Kit 派生）。PD 谱（160/5/1）与契约 ``actuator_profile.by_role`` 一致（包装不覆盖它，
一致性由 `audit` 侧的契约/MJCF 对拍保证）。
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

B2W_XML: Path = _PACKAGE_DIR.parents[2] / "model" / "robot.xml"


def get_spec() -> mujoco.MjSpec:
  """训练模型的 MJCF 真值（含训练域规范化；执行器走本包的 XmlActuatorCfg 包装，不撤）。"""
  if not B2W_XML.exists():
    raise FileNotFoundError(
      f"B2-W MJCF not found at {B2W_XML}. "
      "Place your converted robot.xml and meshes under this package."
    )
  import sys as _sys

  for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
      if str(_parent) not in _sys.path:
        _sys.path.insert(0, str(_parent))
      break
  from adapters.mjlab.spec_utils import normalize_for_training

  spec = mujoco.MjSpec.from_file(str(B2W_XML))
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


def get_b2w_base_entity_cfg() -> EntityCfg:
  """B2-W 的基座实体配置。

  只带族级绑定**不覆盖**的机型事实：MJCF 来源、碰撞、柔性限位系数。出生高 / 默认姿 /
  执行器谱由 `b2w_velocity.binding.B2W.robot_cfg()` 按契约（+ 登记的默认姿偏离）填上
  （见族 Kit 的 `skills/binding.py` 的 "只覆盖三项" 口径）。
  """
  return EntityCfg(
    collisions=(FULL_COLLISION,),
    spec_fn=get_spec,
    articulation=EntityArticulationInfoCfg(
      actuators=(),
      soft_joint_pos_limit_factor=SOFT_JOINT_POS_LIMIT_FACTOR,
    ),
  )
