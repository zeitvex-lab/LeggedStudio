"""DeepRobotics M20 的资产与基座实体配置（机型侧真值）。

官方（上游）velocity 配方族级化（2026-09-25）后本模块只剩**族级绑定不覆盖的机型事实**：

* MJCF 来源（``training/source/m20_velocity/xmls/M20.xml`` + 训练域规范化）；
* 碰撞方案（``FULL_COLLISION``：轮与机身不同的 condim/friction 那一份）；
* 柔性关节限位系数（0.9）。

**不在这里**：关节名/序、默认姿、PD 谱、动作缩放、出生高 —— 这些来自契约
（``binding.py`` 经族 Kit 派生）。在这里再写一份就是第二处真值（历史上
``M20_LEG_JOINT_NAMES`` / ``M20_ACTUATOR_*`` 等字面元组就是这样长出来的，已随上移删除）。

证据链（与删除前的注释一致，全部三方一致）：关节名/运动学 = 官方 ``M20.xml``；
PD/力矩 = 契约 ``actuator_profile.by_role`` == DreamWaQ ``m20.yaml``（kps 80/80/80、
wheel kd 0.6）+ 官方 MJCF ``actuatorfrcrange``（腿 76.4 / 轮 21.6）；初始姿 = DreamWaQ
``m20.yaml`` ``default_angles``（前腿 hipy -0.6 / knee 1.0、后腿镜像；序 fl,fr,hl,hr）。
"""

from pathlib import Path

import mujoco

from mjlab.entity import EntityArticulationInfoCfg, EntityCfg
from mjlab.utils.spec_config import CollisionCfg

_PACKAGE_DIR = Path(__file__).resolve().parent

##
# MJCF and assets.
##

M20_XML: Path = _PACKAGE_DIR / "xmls" / "M20.xml"


def get_spec() -> mujoco.MjSpec:
  """训练模型的 MJCF 真值（含训练域规范化）。"""
  if not M20_XML.exists():
    raise FileNotFoundError(
      f"M20 MJCF not found at {M20_XML}. "
      "Place your converted M20.xml and meshes under this package."
    )
  import sys as _sys

  for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
      if str(_parent) not in _sys.path:
        _sys.path.insert(0, str(_parent))
      break
  from adapters.mjlab.spec_utils import normalize_for_training

  spec = mujoco.MjSpec.from_file(str(M20_XML))
  normalize_for_training(spec)
  return spec


##
# Collision config.
##

FULL_COLLISION = CollisionCfg(
  geom_names_expr=(".*_collision",),
  contype=1,
  conaffinity=0,
  condim={r".*wheel_collision$": 3, ".*_collision": 1},
  priority={r".*wheel_collision$": 1, ".*": 0},
  friction={r".*wheel_collision$": (0.6,)},
)

##
# Base entity config (binding 不覆盖的那部分).
##

#: 柔性关节限位系数（机型真值：执行器谱由契约给，这一项契约不声明）。
SOFT_JOINT_POS_LIMIT_FACTOR = 0.9


def get_m20_base_entity_cfg() -> EntityCfg:
  """M20 的基座实体配置。

  只带族级绑定**不覆盖**的机型事实：MJCF 来源、碰撞、柔性限位系数。出生高 / 默认姿 /
  执行器谱由 `m20_velocity.binding.M20.robot_cfg()` 按契约填上（见族 Kit 的
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
