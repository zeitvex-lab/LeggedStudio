"""Unitree B2 robot constants for the package-local velocity task.

The MJCF, actuator tuning and collision layout are owned by this robot
package.  The training model is ``model/robot.xml`` (no built-in actuators;
they are injected here), so the simulation and training paths share one
source of truth.
"""

from __future__ import annotations

from pathlib import Path

import mujoco
from mjlab.actuator import BuiltinPositionActuatorCfg
from mjlab.entity import EntityArticulationInfoCfg, EntityCfg
from mjlab.utils.spec_config import CollisionCfg

_PACKAGE_ROOT = Path(__file__).resolve().parents[3]
B2_XML = _PACKAGE_ROOT / "model" / "robot.xml"
assert B2_XML.exists()


def get_spec() -> mujoco.MjSpec:
    return mujoco.MjSpec.from_file(str(B2_XML))


##
# Actuator config.
##

B2_ACTUATOR_HIP = BuiltinPositionActuatorCfg(
    target_names_expr=(".*hip.*",),
    stiffness=160.0,
    damping=5.0,
    effort_limit=200.0,
    armature=0.1,
)
B2_ACTUATOR_THIGH = BuiltinPositionActuatorCfg(
    target_names_expr=(".*thigh.*",),
    stiffness=160.0,
    damping=5.0,
    effort_limit=200.0,
    armature=0.1,
)
B2_ACTUATOR_CALF = BuiltinPositionActuatorCfg(
    target_names_expr=(".*calf.*",),
    stiffness=160.0,
    damping=5.0,
    effort_limit=320.0,
    armature=0.1,
)

##
# Keyframe.
##

INIT_STATE = EntityCfg.InitialStateCfg(
    pos=(0.0, 0.0, 0.54),
    joint_pos={
        ".*thigh_joint": 0.8,
        ".*calf_joint": -1.5,
        ".*R_hip_joint": 0.1,
        ".*L_hip_joint": -0.1,
    },
    joint_vel={".*": 0.0},
)

##
# Collision config.
##

_FOOT_RE = "^[FR][LR][RL]_foot_collision$"

FULL_COLLISION = CollisionCfg(
    geom_names_expr=(".*",),
    contype=1,
    conaffinity=0,
    condim={".*foot.*": 3, ".*": 1},
    priority={".*foot.*": 1, ".*": 0},
    friction={".*foot.*": (0.6,)},
)

B2_ARTICULATION = EntityArticulationInfoCfg(
    actuators=(
        B2_ACTUATOR_HIP,
        B2_ACTUATOR_THIGH,
        B2_ACTUATOR_CALF,
    ),
    soft_joint_pos_limit_factor=0.9,
)


def get_b2_robot_cfg() -> EntityCfg:
    """Return a fresh robot configuration instance."""
    return EntityCfg(
        init_state=INIT_STATE,
        collisions=(FULL_COLLISION,),
        spec_fn=get_spec,
        articulation=B2_ARTICULATION,
    )


B2_ACTION_SCALE: dict[str, float] = {}
for actuator in B2_ARTICULATION.actuators:
    assert isinstance(actuator, BuiltinPositionActuatorCfg)
    assert actuator.effort_limit is not None
    for expression in actuator.target_names_expr:
        B2_ACTION_SCALE[expression] = 0.25

__all__ = [
    "B2_ACTION_SCALE",
    "B2_XML",
    "get_b2_robot_cfg",
    "get_spec",
]
