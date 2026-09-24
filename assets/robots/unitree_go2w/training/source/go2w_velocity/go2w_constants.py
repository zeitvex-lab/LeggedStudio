"""Unitree Go2-W constants."""

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

GO2W_XML: Path = (
  _PACKAGE_DIR / "xmls" / "go2w.xml"
)

# Requested action/joint order (matches Unitree SDK command order).
GO2W_LEG_JOINT_NAMES: tuple[str, ...] = (
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
GO2W_WHEEL_JOINT_NAMES: tuple[str, ...] = (
  r"FR_(foot|wheel)_joint",
  r"FL_(foot|wheel)_joint",
  r"RR_(foot|wheel)_joint",
  r"RL_(foot|wheel)_joint",
)
GO2W_ALL_JOINT_NAMES: tuple[str, ...] = GO2W_LEG_JOINT_NAMES + GO2W_WHEEL_JOINT_NAMES

GO2W_HIP_JOINT_NAMES: tuple[str, ...] = (
  "FR_hip_joint",
  "FL_hip_joint",
  "RR_hip_joint",
  "RL_hip_joint",
)
GO2W_THIGH_JOINT_NAMES: tuple[str, ...] = (
  "FR_thigh_joint",
  "FL_thigh_joint",
  "RR_thigh_joint",
  "RL_thigh_joint",
)
GO2W_CALF_JOINT_NAMES: tuple[str, ...] = (
  "FR_calf_joint",
  "FL_calf_joint",
  "RR_calf_joint",
  "RL_calf_joint",
)

GO2W_LEG_JOINT_REGEX: str = r"^(FR|FL|RR|RL)_(hip|thigh|calf)_joint$"
GO2W_WHEEL_JOINT_REGEX: str = r"^(FR|FL|RR|RL)_(foot|wheel)_joint$"


def get_spec() -> mujoco.MjSpec:
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
# Actuator config.
##

GO2W_ACTUATOR_HIP = BuiltinPositionActuatorCfg(
  target_names_expr=GO2W_HIP_JOINT_NAMES,
  stiffness=20.0,
  damping=0.5,
  effort_limit=23.5,
  armature=0.01,
)
GO2W_ACTUATOR_THIGH = BuiltinPositionActuatorCfg(
  target_names_expr=GO2W_THIGH_JOINT_NAMES,
  stiffness=20.0,
  damping=0.5,
  effort_limit=23.5,
  armature=0.01,
)
GO2W_ACTUATOR_CALF = BuiltinPositionActuatorCfg(
  target_names_expr=GO2W_CALF_JOINT_NAMES,
  stiffness=20.0,
  damping=0.5,
  effort_limit=35.5,
  armature=0.02,
)
GO2W_ACTUATOR_WHEEL = BuiltinVelocityActuatorCfg(
  target_names_expr=GO2W_WHEEL_JOINT_NAMES,
  damping=0.5,
  effort_limit=23.5,
  armature=0.01,
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

GO2W_ARTICULATION = EntityArticulationInfoCfg(
  actuators=(
    GO2W_ACTUATOR_HIP,
    GO2W_ACTUATOR_THIGH,
    GO2W_ACTUATOR_CALF,
    GO2W_ACTUATOR_WHEEL,
  ),
  soft_joint_pos_limit_factor=0.9,
)


def get_go2w_robot_cfg() -> EntityCfg:
  """Get a fresh Go2-W robot configuration instance."""
  return EntityCfg(
    init_state=INIT_STATE,
    collisions=(FULL_COLLISION,),
    spec_fn=get_spec,
    articulation=GO2W_ARTICULATION,
  )
