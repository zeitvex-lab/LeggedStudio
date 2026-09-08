"""LimX TRON1 sole-foot robot constants for the package-local velocity task.

Source of truth: LeggedGym-Ex ``legged_gym/envs/tron1sf/tron1sf_config.py``
(BSD-3) plus the SF_TRON1A MJCF.  The package model is ``model/robot.xml``
(no built-in actuators; PD is injected here), so the training and simulation
paths share one model.  Joint naming follows the LimX ``*_Joint`` convention.
"""

from __future__ import annotations

from pathlib import Path

import mujoco
from mjlab.actuator import BuiltinPositionActuatorCfg
from mjlab.entity import EntityArticulationInfoCfg, EntityCfg
from mjlab.utils.spec_config import CollisionCfg

_PACKAGE_ROOT = Path(__file__).resolve().parents[3]
TRON1_SF_XML = _PACKAGE_ROOT / "model" / "robot.xml"
assert TRON1_SF_XML.exists()


def get_spec() -> mujoco.MjSpec:
    return mujoco.MjSpec.from_file(str(TRON1_SF_XML))


##
# Actuator config (source: TRON1SFCfg.control -- Kp 45 N*m/rad; Kd 1.5 N*m*s/rad
# for abad/hip/knee and 0.8 for ankles; torque limits +-80 / +-20 N*m from the
# source MJCF motor ctrlrange).
##

TRON1_SF_ACTUATOR_LEG = BuiltinPositionActuatorCfg(
    target_names_expr=(".*(?:abad|hip|knee)_.*_Joint",),
    stiffness=45.0,
    damping=1.5,
    effort_limit=80.0,
    armature=0.01,
)
TRON1_SF_ACTUATOR_ANKLE = BuiltinPositionActuatorCfg(
    target_names_expr=(".*ankle_.*_Joint",),
    stiffness=45.0,
    damping=0.8,
    effort_limit=20.0,
    armature=0.01,
)

##
# Initial state (source: init_state.pos z=0.85 m, default_joint_angles all 0).
##

INIT_STATE = EntityCfg.InitialStateCfg(
    pos=(0.0, 0.0, 0.85),
    joint_pos={".*_Joint": 0.0},
    joint_vel={".*": 0.0},
)

##
# Collision config.
##

_FOOT_GEOMS_RE = r"^ankle_[LR]_collision$"

FULL_COLLISION = CollisionCfg(
    geom_names_expr=(".*_collision",),
    contype=1,
    conaffinity=1,
    condim={_FOOT_GEOMS_RE: 3, ".*_collision": 1},
    priority={_FOOT_GEOMS_RE: 1, ".*_collision": 0},
    friction={_FOOT_GEOMS_RE: (0.6,)},
)

TRON1_SF_ARTICULATION = EntityArticulationInfoCfg(
    actuators=(
        TRON1_SF_ACTUATOR_LEG,
        TRON1_SF_ACTUATOR_ANKLE,
    ),
    soft_joint_pos_limit_factor=0.9,  # source rewards.soft_dof_pos_limit
)


def get_tron1_sf_robot_cfg() -> EntityCfg:
    """Return a fresh TRON1-SF robot configuration instance."""
    return EntityCfg(
        init_state=INIT_STATE,
        collisions=(FULL_COLLISION,),
        spec_fn=get_spec,
        articulation=TRON1_SF_ARTICULATION,
    )


##
# Action scale (source: control.action_scale = 0.25).
##

TRON1_SF_ACTION_SCALE: dict[str, float] = {}
for actuator in TRON1_SF_ARTICULATION.actuators:
    assert isinstance(actuator, BuiltinPositionActuatorCfg)
    for expression in actuator.target_names_expr:
        TRON1_SF_ACTION_SCALE[expression] = 0.25

__all__ = [
    "INIT_STATE",
    "TRON1_SF_ACTION_SCALE",
    "TRON1_SF_ACTUATOR_ANKLE",
    "TRON1_SF_ACTUATOR_LEG",
    "TRON1_SF_ARTICULATION",
    "TRON1_SF_XML",
    "get_spec",
    "get_tron1_sf_robot_cfg",
]
