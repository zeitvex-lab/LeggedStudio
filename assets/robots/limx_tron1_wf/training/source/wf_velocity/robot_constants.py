"""LimX TRON1 wheel-foot robot constants for the package-local velocity task.

Source of truth: LeggedGym-Ex / ``tron1-rl-isaaclab`` WF config
(``limx_wheelfoot_env_cfg.py``) plus the WF model MJCF.  The package model is
``model/robot.xml`` (no built-in actuators; PD/velocity actuators are injected
here), so the training and simulation paths share one model.  Joint naming
follows the LimX ``*_Joint`` convention (``wheel_L_Joint`` / ``wheel_R_Joint``).
"""

from __future__ import annotations

from pathlib import Path

import mujoco
from mjlab.actuator import BuiltinPositionActuatorCfg, BuiltinVelocityActuatorCfg
from mjlab.entity import EntityArticulationInfoCfg, EntityCfg
from mjlab.utils.spec_config import CollisionCfg

_PACKAGE_ROOT = Path(__file__).resolve().parents[3]
TRON1_WF_XML = _PACKAGE_ROOT / "model" / "robot.xml"
assert TRON1_WF_XML.exists()


def get_spec() -> mujoco.MjSpec:
    return mujoco.MjSpec.from_file(str(TRON1_WF_XML))


##
# Actuator config (source: TRON1WFCfg.control -- legs Kp 42 / Kd 2.5,
# torque limit +-80 N*m; wheels are velocity actuators Kd 0.8, torque +-40 N*m).
##

TRON1_WF_ACTUATOR_LEG = BuiltinPositionActuatorCfg(
    target_names_expr=(".*(?:abad|hip|knee)_.*_Joint",),
    stiffness=42.0,
    damping=2.5,
    effort_limit=80.0,
    armature=0.01,
)
TRON1_WF_ACTUATOR_WHEEL = BuiltinVelocityActuatorCfg(
    target_names_expr=(".*wheel_.*_Joint",),
    damping=0.8,
    effort_limit=40.0,
    armature=0.01,
)

##
# Initial state (source: init_state.pos z=0.92 m, default_joint_angles all 0).
##

INIT_STATE = EntityCfg.InitialStateCfg(
    pos=(0.0, 0.0, 0.92),
    joint_pos={".*_Joint": 0.0},
    joint_vel={".*": 0.0},
)

##
# Collision config.
##

_WHEEL_GEOMS_RE = r"^wheel_[LR]_collision$"

FULL_COLLISION = CollisionCfg(
    geom_names_expr=(".*_collision",),
    contype=1,
    conaffinity=1,
    condim={_WHEEL_GEOMS_RE: 3, ".*_collision": 1},
    priority={_WHEEL_GEOMS_RE: 1, ".*_collision": 0},
    friction={_WHEEL_GEOMS_RE: (0.9,)},
)

TRON1_WF_ARTICULATION = EntityArticulationInfoCfg(
    actuators=(TRON1_WF_ACTUATOR_LEG, TRON1_WF_ACTUATOR_WHEEL),
    soft_joint_pos_limit_factor=0.9,
)


def get_tron1_wf_robot_cfg() -> EntityCfg:
    """Return a fresh TRON1-WF robot configuration instance."""
    return EntityCfg(
        init_state=INIT_STATE,
        collisions=(FULL_COLLISION,),
        spec_fn=get_spec,
        articulation=TRON1_WF_ARTICULATION,
    )


##
# Action scale: legs position 0.25 (source control.action_scale_pos);
# wheels velocity 1.0 (source JointVelocityActionCfg scale=1.0).
##

LEG_JOINT_EXPR = (".*(?:abad|hip|knee)_.*_Joint",)
WHEEL_JOINT_EXPR = (".*wheel_.*_Joint",)
TRON1_WF_LEG_ACTION_SCALE: dict[str, float] = {expr: 0.25 for expr in LEG_JOINT_EXPR}
TRON1_WF_WHEEL_ACTION_SCALE: dict[str, float] = {expr: 1.0 for expr in WHEEL_JOINT_EXPR}

__all__ = [
    "INIT_STATE",
    "LEG_JOINT_EXPR",
    "TRON1_WF_ACTUATOR_LEG",
    "TRON1_WF_ACTUATOR_WHEEL",
    "TRON1_WF_ARTICULATION",
    "TRON1_WF_LEG_ACTION_SCALE",
    "TRON1_WF_WHEEL_ACTION_SCALE",
    "TRON1_WF_XML",
    "WHEEL_JOINT_EXPR",
    "get_spec",
    "get_tron1_wf_robot_cfg",
]
