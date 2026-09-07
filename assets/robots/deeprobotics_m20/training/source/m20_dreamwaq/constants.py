"""Deeprobotics M20 constants and DreamWaQ source-training values.

The DreamWaQ wheel-legged training recipe (BSD-3-Clause) was field-verified on
the Deeprobotics M20.  This module pins the package-level MJCF
(``model/robot.xml``) and the source control/observation constants so the
``m20_dreamwaq`` task stays reproducible without importing IsaacGym code.
"""

from dataclasses import dataclass
from pathlib import Path

import mujoco

from mjlab.actuator import BuiltinPositionActuatorCfg, BuiltinVelocityActuatorCfg
from mjlab.entity import EntityArticulationInfoCfg, EntityCfg

##
# MJCF (package-level model; matches contract.json joint order).
##

_PACKAGE_DIR = Path(__file__).resolve().parent
M20_XML: Path = _PACKAGE_DIR.parents[2] / "model" / "robot.xml"

# Policy joint order: 12 legs (fl/fr/hl/hr x hipx/hipy/knee) then 4 wheels
# (fl/fr/hl/hr), matching contract.json ``action.joint_order`` and the m20
# velocity task action layout.
M20_LEG_JOINT_NAMES: tuple[str, ...] = tuple(
  f"{leg}_{joint}_joint"
  for leg in ("fl", "fr", "hl", "hr")
  for joint in ("hipx", "hipy", "knee")
)
M20_WHEEL_JOINT_NAMES: tuple[str, ...] = tuple(
  f"{leg}_wheel_joint" for leg in ("fl", "fr", "hl", "hr")
)
M20_ALL_JOINT_NAMES: tuple[str, ...] = M20_LEG_JOINT_NAMES + M20_WHEEL_JOINT_NAMES
M20_HIPX_JOINT_NAMES: tuple[str, ...] = tuple(
  f"{leg}_hipx_joint" for leg in ("fl", "fr", "hl", "hr")
)

_NUM_LEGS = len(M20_LEG_JOINT_NAMES)
_NUM_WHEELS = len(M20_WHEEL_JOINT_NAMES)

##
# Source control constants (DreamWaQ M20 config).
##

LEG_STIFFNESS: float = 80.0
LEG_DAMPING: float = 2.0
WHEEL_DAMPING: float = 0.6
LEG_EFFORT_LIMIT: float = 76.4
WHEEL_EFFORT_LIMIT: float = 21.6
ACTION_SCALE: float = 0.25
WHEEL_VEL_SCALE: float = 5.0
# Small rotor-style armature keeps the direct-drive wheels stable in MuJoCo
# (the IsaacGym asset ran with armature 0 and PhysX velocity clamps).
LEG_ARMATURE: float = 0.01
WHEEL_ARMATURE: float = 0.01

# Observation scales (source ``normalization.obs_scales``).
LIN_VEL_SCALE: float = 2.0
ANG_VEL_SCALE: float = 0.25
DOF_POS_SCALE: float = 1.0
DOF_VEL_SCALE: float = 0.05
# Source noise vector (dof_pos 0.01, dof_vel 1.5 x 0.05, ang_vel 0.2 x 0.25,
# gravity 0.05, command/action 0).  The source noise vector was misaligned by
# one 3-slot (command slots received the angular-velocity noise); this port
# aligns noise to the physical fields instead of replicating the bug.
OBS_NOISE_ANG_VEL: float = 0.05
OBS_NOISE_GRAVITY: float = 0.05
OBS_NOISE_DOF_POS: float = 0.01
OBS_NOISE_DOF_VEL: float = 0.075

##
# Robot configuration.
##


def get_spec() -> mujoco.MjSpec:
  if not M20_XML.exists():
    raise FileNotFoundError(f"M20 MJCF not found at {M20_XML}.")
  return mujoco.MjSpec.from_file(str(M20_XML))


INIT_STATE = EntityCfg.InitialStateCfg(
  # Source init_state.pos z = 0.60 (base_height_target 0.52).
  pos=(0.0, 0.0, 0.60),
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
    r"fl_wheel_joint": 0.0,
    r"fr_wheel_joint": 0.0,
    r"hl_wheel_joint": 0.0,
    r"hr_wheel_joint": 0.0,
  },
  joint_vel={".*": 0.0},
)

LEG_ACTUATOR = BuiltinPositionActuatorCfg(
  target_names_expr=M20_LEG_JOINT_NAMES,
  stiffness=LEG_STIFFNESS,
  damping=LEG_DAMPING,
  effort_limit=LEG_EFFORT_LIMIT,
  armature=LEG_ARMATURE,
)
# The source drives wheels with pure damping (kp 0, kd 0.6): a MuJoCo
# ``velocity`` actuator reproduces tau = kd * (vel_target - qvel) exactly.
WHEEL_ACTUATOR = BuiltinVelocityActuatorCfg(
  target_names_expr=M20_WHEEL_JOINT_NAMES,
  damping=WHEEL_DAMPING,
  effort_limit=WHEEL_EFFORT_LIMIT,
  armature=WHEEL_ARMATURE,
)

M20_ARTICULATION = EntityArticulationInfoCfg(
  actuators=(LEG_ACTUATOR, WHEEL_ACTUATOR),
  # Source ``rewards.soft_dof_pos_limit`` = 0.9.
  soft_joint_pos_limit_factor=0.9,
)


def m20_dreamwaq_robot_cfg() -> EntityCfg:
  """Fresh M20 EntityCfg tuned for the DreamWaQ training recipe."""
  return EntityCfg(
    init_state=INIT_STATE,
    spec_fn=get_spec,
    articulation=M20_ARTICULATION,
  )


##
# Immutable source-training constants.
##


@dataclass(frozen=True)
class M20DreamWaQProfile:
  """Source M20 DreamWaQ training constants (legged_gym M20 config)."""

  task_id: str = "Deeprobotics-M20-DreamWaQ-Rough"
  experiment_name: str = "m20_dreamwaq"
  num_envs: int = 4096
  episode_length_s: float = 20.0
  physics_dt: float = 0.005
  decimation: int = 4
  action_scale: float = ACTION_SCALE
  wheel_vel_scale: float = WHEEL_VEL_SCALE
  actor_dim: int = 57  # cmd 3 + ang_vel 3 + gravity 3 + dof_err 16 + dof_vel 16 + action 16
  actor_history: int = 5
  critic_dim: int = 247  # lin_vel 3 + heights 187 + actor 57
  latent_dim: int = 16
  explicit_dim: int = 3
  base_height_target: float = 0.52
  tracking_sigma: float = 0.25


M20_DREAMWAQ = M20DreamWaQProfile()
