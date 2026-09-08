"""LimX TRON1 point-foot robot constants for the package-local velocity task.

Source of truth: LeggedGym-Ex ``legged_gym/envs/tron1pf/tron1pf_config.py``
(BSD-3) plus the PF_TRON1A MJCF.  The package model is ``model/robot.xml``
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
TRON1_PF_XML = _PACKAGE_ROOT / "model" / "robot.xml"
assert TRON1_PF_XML.exists()


def get_spec() -> mujoco.MjSpec:
    return mujoco.MjSpec.from_file(str(TRON1_PF_XML))


##
# Actuator config (source: TRON1PFCfg.control -- Kp 42 N*m/rad, Kd 2.5 N*m*s/rad;
# torque limit +-80 N*m from the source MJCF motor ctrlrange).
##

TRON1_PF_ACTUATOR_LEG = BuiltinPositionActuatorCfg(
    target_names_expr=(".*_Joint",),
    stiffness=42.0,
    damping=2.5,
    effort_limit=80.0,
    armature=0.01,
)

##
# Initial state (source: init_state.pos z=0.82 m, default_joint_angles all 0).
##

INIT_STATE = EntityCfg.InitialStateCfg(
    pos=(0.0, 0.0, 0.82),
    joint_pos={".*_Joint": 0.0},
    joint_vel={".*": 0.0},
)

##
# Collision config.
##

_FOOT_GEOMS_RE = r"^foot_[LR]_collision$"

FULL_COLLISION = CollisionCfg(
    geom_names_expr=(".*_collision",),
    contype=1,
    conaffinity=1,
    condim={_FOOT_GEOMS_RE: 3, ".*_collision": 1},
    priority={_FOOT_GEOMS_RE: 1, ".*_collision": 0},
    friction={_FOOT_GEOMS_RE: (0.6,)},
)

TRON1_PF_ARTICULATION = EntityArticulationInfoCfg(
    actuators=(
        TRON1_PF_ACTUATOR_LEG,
    ),
    soft_joint_pos_limit_factor=0.9,  # source rewards.soft_dof_pos_limit
)


def get_tron1_pf_robot_cfg() -> EntityCfg:
    """Return a fresh TRON1-PF robot configuration instance."""
    return EntityCfg(
        init_state=INIT_STATE,
        collisions=(FULL_COLLISION,),
        spec_fn=get_spec,
        articulation=TRON1_PF_ARTICULATION,
    )


##
# Action scale (source: control.action_scale = 0.25).
##

TRON1_PF_ACTION_SCALE: dict[str, float] = {}
for actuator in TRON1_PF_ARTICULATION.actuators:
    assert isinstance(actuator, BuiltinPositionActuatorCfg)
    for expression in actuator.target_names_expr:
        TRON1_PF_ACTION_SCALE[expression] = 0.25

__all__ = [
    "INIT_STATE",
    "TRON1_PF_ACTION_SCALE",
    "TRON1_PF_ACTUATOR_LEG",
    "TRON1_PF_ARTICULATION",
    "TRON1_PF_XML",
    "get_spec",
    "get_tron1_pf_robot_cfg",
]
