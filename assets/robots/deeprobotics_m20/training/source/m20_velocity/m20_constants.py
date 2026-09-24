"""Deeprobotics M20 constants.

Evidence chain (all three agree):
  * joint names / kinematics: official ``deep_robotics_model/M20/mjcf/M20.xml``
    (fl/fr/hl/hr x hipx/hipy/knee/wheel) == contract.json ``joints.actuated``;
  * PD gains / effort: contract ``actuator_profile.by_role`` ==
    DreamWaQ ``deploy_mujoco/configs/m20.yaml`` (kps 80/80/80, wheel kd 0.6)
    with effort limits from the official MJCF ``actuatorfrcrange``
    (legs 76.4, wheels 21.6);
  * initial pose: DreamWaQ ``m20.yaml`` ``default_angles`` (front legs hipy -0.6 /
    knee 1.0, rear legs mirrored; order fl,fr,hl,hr per its MJCF);
  * meshes: package ``model/assets`` (single copy, byte-identical to official
    ``M20/meshes`` STLs — verified by sha256).
"""

from pathlib import Path

import mujoco

from mjlab.actuator import BuiltinPositionActuatorCfg, BuiltinVelocityActuatorCfg
from mjlab.entity import EntityArticulationInfoCfg, EntityCfg
from mjlab.utils.spec_config import CollisionCfg

##
# MJCF and assets.
##

M20_XML: Path = Path(__file__).resolve().parent / "xmls" / "M20.xml"

# Requested action/joint order (matches the DeepRobotics SDK command order:
# FR, FL, HR, HL leg groups).
M20_LEG_JOINT_NAMES: tuple[str, ...] = (
  "fr_hipx_joint",
  "fr_hipy_joint",
  "fr_knee_joint",
  "fl_hipx_joint",
  "fl_hipy_joint",
  "fl_knee_joint",
  "hr_hipx_joint",
  "hr_hipy_joint",
  "hr_knee_joint",
  "hl_hipx_joint",
  "hl_hipy_joint",
  "hl_knee_joint",
)
M20_WHEEL_JOINT_NAMES: tuple[str, ...] = (
  "fr_wheel_joint",
  "fl_wheel_joint",
  "hr_wheel_joint",
  "hl_wheel_joint",
)
M20_ALL_JOINT_NAMES: tuple[str, ...] = M20_LEG_JOINT_NAMES + M20_WHEEL_JOINT_NAMES

M20_HIPX_JOINT_NAMES: tuple[str, ...] = (
  "fr_hipx_joint",
  "fl_hipx_joint",
  "hr_hipx_joint",
  "hl_hipx_joint",
)
M20_HIPY_JOINT_NAMES: tuple[str, ...] = (
  "fr_hipy_joint",
  "fl_hipy_joint",
  "hr_hipy_joint",
  "hl_hipy_joint",
)
M20_KNEE_JOINT_NAMES: tuple[str, ...] = (
  "fr_knee_joint",
  "fl_knee_joint",
  "hr_knee_joint",
  "hl_knee_joint",
)

M20_LEG_JOINT_REGEX: str = r"^(fr|fl|hr|hl)_(hipx|hipy|knee)_joint$"
M20_WHEEL_JOINT_REGEX: str = r"^(fr|fl|hr|hl)_wheel_joint$"


def get_spec() -> mujoco.MjSpec:
  if not M20_XML.exists():
    raise FileNotFoundError(
      f"M20 MJCF not found at {M20_XML}."
    )
  # 训练口径：补传感器名 + 传感器只留消费集（唯一入口 adapters/mjlab/spec_utils.py）。
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
# Actuator config (contract actuator_profile.by_role / DreamWaQ m20.yaml).
##

M20_ACTUATOR_HIPX = BuiltinPositionActuatorCfg(
  target_names_expr=M20_HIPX_JOINT_NAMES,
  stiffness=80.0,
  damping=2.0,
  effort_limit=76.4,
  armature=0.01,
)
M20_ACTUATOR_HIPY = BuiltinPositionActuatorCfg(
  target_names_expr=M20_HIPY_JOINT_NAMES,
  stiffness=80.0,
  damping=2.0,
  effort_limit=76.4,
  armature=0.01,
)
M20_ACTUATOR_KNEE = BuiltinPositionActuatorCfg(
  target_names_expr=M20_KNEE_JOINT_NAMES,
  stiffness=80.0,
  damping=2.0,
  effort_limit=76.4,
  armature=0.01,
)
M20_ACTUATOR_WHEEL = BuiltinVelocityActuatorCfg(
  target_names_expr=M20_WHEEL_JOINT_NAMES,
  damping=0.6,
  effort_limit=21.6,
  armature=0.01,
)

##
# Keyframes (DreamWaQ m20.yaml default_angles; joint order fl,fr,hl,hr:
# front legs hipy -0.6 / knee 1.0, rear legs mirrored).
##

INIT_STATE = EntityCfg.InitialStateCfg(
  pos=(0.0, 0.0, 0.4),
  joint_pos={
    "fl_hipx_joint": 0.0,
    "fl_hipy_joint": -0.6,
    "fl_knee_joint": 1.0,
    "fr_hipx_joint": 0.0,
    "fr_hipy_joint": -0.6,
    "fr_knee_joint": 1.0,
    "hl_hipx_joint": 0.0,
    "hl_hipy_joint": 0.6,
    "hl_knee_joint": -1.0,
    "hr_hipx_joint": 0.0,
    "hr_hipy_joint": 0.6,
    "hr_knee_joint": -1.0,
    "fl_wheel_joint": 0.0,
    "fr_wheel_joint": 0.0,
    "hl_wheel_joint": 0.0,
    "hr_wheel_joint": 0.0,
  },
  joint_vel={".*": 0.0},
)

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
# Final config.
##

M20_ARTICULATION = EntityArticulationInfoCfg(
  actuators=(
    M20_ACTUATOR_HIPX,
    M20_ACTUATOR_HIPY,
    M20_ACTUATOR_KNEE,
    M20_ACTUATOR_WHEEL,
  ),
  soft_joint_pos_limit_factor=0.9,
)


def get_m20_robot_cfg() -> EntityCfg:
  """Get a fresh DeepRobotics M20 robot configuration instance."""
  return EntityCfg(
    init_state=INIT_STATE,
    collisions=(FULL_COLLISION,),
    spec_fn=get_spec,
    articulation=M20_ARTICULATION,
  )
