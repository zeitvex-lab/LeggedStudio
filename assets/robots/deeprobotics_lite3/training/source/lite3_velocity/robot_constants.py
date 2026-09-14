"""Deeprobotics Lite3 robot constants for the package-local velocity task.

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
LITE3_XML = _PACKAGE_ROOT / "model" / "robot.xml"
assert LITE3_XML.exists()


def get_spec() -> mujoco.MjSpec:
    return mujoco.MjSpec.from_file(str(LITE3_XML))


##
# Actuator config.
##

LITE3_ACTUATOR_HIP = BuiltinPositionActuatorCfg(
    target_names_expr=(".*HipX.*",),
    stiffness=40.0,
    damping=1.0,
    effort_limit=30.0,
    armature=0.01,
)
LITE3_ACTUATOR_THIGH = BuiltinPositionActuatorCfg(
    target_names_expr=(".*HipY.*",),
    stiffness=40.0,
    damping=1.0,
    effort_limit=30.0,
    armature=0.01,
)
LITE3_ACTUATOR_CALF = BuiltinPositionActuatorCfg(
    target_names_expr=(".*Knee.*",),
    stiffness=40.0,
    damping=1.0,
    effort_limit=30.0,
    armature=0.01,
)

##
# Keyframe.
##

INIT_STATE = EntityCfg.InitialStateCfg(
    pos=(0.0, 0.0, 0.3),
    joint_pos={
        ".*HipY_joint": -0.8,
        ".*Knee_joint": 1.5,
        ".*HipX_joint": 0.1,
        
    },
    joint_vel={".*": 0.0},
)

##
# Collision config.
##

_FOOT_RE = ".*foot.*"

FULL_COLLISION = CollisionCfg(
    geom_names_expr=(".*",),
    contype=1,
    conaffinity=0,
    condim={".*foot.*": 3, ".*": 1},
    priority={".*foot.*": 1, ".*": 0},
    friction={".*foot.*": (0.6,)},
)

LITE3_ARTICULATION = EntityArticulationInfoCfg(
    actuators=(
        LITE3_ACTUATOR_HIP,
        LITE3_ACTUATOR_THIGH,
        LITE3_ACTUATOR_CALF,
    ),
    soft_joint_pos_limit_factor=0.9,
)


def get_lite3_robot_cfg() -> EntityCfg:
    """Return a fresh robot configuration instance."""
    return EntityCfg(
        init_state=INIT_STATE,
        collisions=(FULL_COLLISION,),
        spec_fn=get_spec,
        articulation=LITE3_ARTICULATION,
    )


LITE3_ACTION_SCALE: dict[str, float] = {}
for actuator in LITE3_ARTICULATION.actuators:
    assert isinstance(actuator, BuiltinPositionActuatorCfg)
    assert actuator.effort_limit is not None
    for expression in actuator.target_names_expr:
        LITE3_ACTION_SCALE[expression] = 0.25

__all__ = [
    "LITE3_ACTION_SCALE",
    "LITE3_XML",
    "get_lite3_robot_cfg",
    "get_spec",
]
