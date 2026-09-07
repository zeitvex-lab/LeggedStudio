"""Unitree A2 robot constants for the package-local velocity task.

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
A2_XML = _PACKAGE_ROOT / "model" / "robot.xml"
assert A2_XML.exists()


def get_spec() -> mujoco.MjSpec:
    return mujoco.MjSpec.from_file(str(A2_XML))


##
# Actuator config (mjlab constants; no actuators in the source MJCF).
##

A2_ACTUATOR_HIP = BuiltinPositionActuatorCfg(
    target_names_expr=(".*hip_.*",),
    stiffness=100.0,
    damping=4.0,
    effort_limit=120,
    armature=0.03,
)
A2_ACTUATOR_THIGH = BuiltinPositionActuatorCfg(
    target_names_expr=(".*thigh_.*",),
    stiffness=100.0,
    damping=4.0,
    effort_limit=120,
    armature=0.03,
)
A2_ACTUATOR_CALF = BuiltinPositionActuatorCfg(
    target_names_expr=(".*calf_.*",),
    stiffness=150.0,
    damping=6.0,
    effort_limit=180,
    armature=0.03,
)

##
# Keyframe.
##

INIT_STATE = EntityCfg.InitialStateCfg(
    pos=(0.0, 0.0, 0.4),
    joint_pos={
        ".*thigh_joint": 0.9,
        ".*calf_joint": -1.8,
        ".*R_hip_joint": 0.1,
        ".*L_hip_joint": -0.1,
    },
    joint_vel={".*": 0.0},
)

##
# Collision config.
##

_FOOT_RE = "^[FR][LR]_foot_collision$"

FULL_COLLISION = CollisionCfg(
    geom_names_expr=(".*_collision",),
    condim={_FOOT_RE: 3, ".*_collision": 1},
    priority={_FOOT_RE: 1, ".*": 0},
    friction={_FOOT_RE: (0.6,)},
    solimp={_FOOT_RE: (0.9, 0.95, 0.023)},
    contype=1,
    conaffinity=0,
)

A2_ARTICULATION = EntityArticulationInfoCfg(
    actuators=(A2_ACTUATOR_HIP, A2_ACTUATOR_THIGH, A2_ACTUATOR_CALF),
    soft_joint_pos_limit_factor=0.9,
)


def get_a2_robot_cfg() -> EntityCfg:
    """Return a fresh A2 robot configuration instance.

    A new EntityCfg is returned each call so shared configs are never
    mutated by later task wiring.
    """
    return EntityCfg(
        init_state=INIT_STATE,
        collisions=(FULL_COLLISION,),
        spec_fn=get_spec,
        articulation=A2_ARTICULATION,
    )


A2_ACTION_SCALE: dict[str, float] = {}
for actuator in A2_ARTICULATION.actuators:
    assert isinstance(actuator, BuiltinPositionActuatorCfg)
    assert actuator.effort_limit is not None
    for expression in actuator.target_names_expr:
        A2_ACTION_SCALE[expression] = 0.25 * actuator.effort_limit / actuator.stiffness

__all__ = [
    "A2_ACTION_SCALE",
    "A2_XML",
    "get_a2_robot_cfg",
    "get_spec",
]
