"""Deeprobotics M20 constants."""

from pathlib import Path

import mujoco

from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent
from mjlab.actuator import BuiltinPositionActuatorCfg, BuiltinVelocityActuatorCfg
from mjlab.entity import EntityArticulationInfoCfg, EntityCfg
from mjlab.utils.spec_config import CollisionCfg

##
# MJCF and assets.
##

M20_XML: Path = (
  _PACKAGE_DIR / "xmls" / "go2w.xml"
)

# Requested action/joint order (matches Unitree SDK command order).
M20_LEG_JOINT_NAMES: tuple[str, ...] = (
  "FR_hip_joint",
  "FR_thigh_joint",
  "FR_calf_joint",
  "FL_hip_joint",
  "FL_thigh_joint",
  "FL_calf_joint",
  "RR_hip_joint",
  "RR_thigh_joint",
  "RR_calf_joint",
  "RL_hip_joint",
  "RL_thigh_joint",
  "RL_calf_joint",
)
M20_WHEEL_JOINT_NAMES: tuple[str, ...] = (
  r"FR_(foot|wheel)_joint",
  r"FL_(foot|wheel)_joint",
  r"RR_(foot|wheel)_joint",
  r"RL_(foot|wheel)_joint",
)
GO2W_ALL_JOINT_NAMES: tuple[str, ...] = M20_LEG_JOINT_NAMES + M20_WHEEL_JOINT_NAMES

M20_HIP_JOINT_NAMES: tuple[str, ...] = (
  "FR_hip_joint",
  "FL_hip_joint",
  "RR_hip_joint",
  "RL_hip_joint",
)
M20_THIGH_JOINT_NAMES: tuple[str, ...] = (
  "FR_thigh_joint",
  "FL_thigh_joint",
  "RR_thigh_joint",
  "RL_thigh_joint",
)
M20_CALF_JOINT_NAMES: tuple[str, ...] = (
  "FR_calf_joint",
  "FL_calf_joint",
  "RR_calf_joint",
  "RL_calf_joint",
)

M20_LEG_JOINT_REGEX: str = r"^(FR|FL|RR|RL)_(hip|thigh|calf)_joint$"
M20_WHEEL_JOINT_REGEX: str = r"^(FR|FL|RR|RL)_(foot|wheel)_joint$"


def get_spec() -> mujoco.MjSpec:
  if not M20_XML.exists():
    raise FileNotFoundError(
      f"Go2-W MJCF not found at {M20_XML}. "
      "Place your converted go2w.xml and meshes under this package."
    )
  return mujoco.MjSpec.from_file(str(M20_XML))


##
# Actuator config.
##

M20_ACTUATOR_HIP = BuiltinPositionActuatorCfg(
  target_names_expr=M20_HIP_JOINT_NAMES,
  stiffness=20.0,
  damping=1.0,
  effort_limit=23.5,
  armature=0.01,
)
M20_ACTUATOR_THIGH = BuiltinPositionActuatorCfg(
  target_names_expr=M20_THIGH_JOINT_NAMES,
  stiffness=20.0,
  damping=1.0,
  effort_limit=23.5,
  armature=0.01,
)
M20_ACTUATOR_CALF = BuiltinPositionActuatorCfg(
  target_names_expr=M20_CALF_JOINT_NAMES,
  stiffness=40.0,
  damping=2.0,
  effort_limit=45.0,
  armature=0.02,
)
M20_ACTUATOR_WHEEL = BuiltinVelocityActuatorCfg(
  target_names_expr=M20_WHEEL_JOINT_NAMES,
  damping=2.0,
  effort_limit=45.0,
  armature=0.02,
)

##
# Keyframes.
##


INIT_STATE = EntityCfg.InitialStateCfg(
  pos=(0.0, 0.0, 0.4),
  joint_pos={
    "FR_hip_joint": 0.1,
    "FR_thigh_joint": 0.9,
    "FR_calf_joint": -1.8,
    "FL_hip_joint": -0.1,
    "FL_thigh_joint": 0.9,
    "FL_calf_joint": -1.8,
    "RR_hip_joint": 0.1,
    "RR_thigh_joint": 0.9,
    "RR_calf_joint": -1.8,
    "RL_hip_joint": -0.1,
    "RL_thigh_joint": 0.9,
    "RL_calf_joint": -1.8,
    r"FR_(foot|wheel)_joint": 0.0,
    r"FL_(foot|wheel)_joint": 0.0,
    r"RR_(foot|wheel)_joint": 0.0,
    r"RL_(foot|wheel)_joint": 0.0,
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
  condim={r".*(wheel|foot)_collision$": 3, ".*_collision": 1},
  priority={r".*(wheel|foot)_collision$": 1, ".*": 0},
  friction={r".*(wheel|foot)_collision$": (0.6,)},
)

##
# Final config.
##

M20_ARTICULATION = EntityArticulationInfoCfg(
  actuators=(
    M20_ACTUATOR_HIP,
    M20_ACTUATOR_THIGH,
    M20_ACTUATOR_CALF,
    M20_ACTUATOR_WHEEL,
  ),
  soft_joint_pos_limit_factor=0.9,
)


def get_m20_robot_cfg() -> EntityCfg:
  """Get a fresh Go2-W robot configuration instance."""
  return EntityCfg(
    init_state=INIT_STATE,
    collisions=(FULL_COLLISION,),
    spec_fn=get_spec,
    articulation=M20_ARTICULATION,
  )
