"""Unitree H1_2 robot constants for the package-local velocity task.

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
H1_2_XML = _PACKAGE_ROOT / "model" / "robot.xml"
assert H1_2_XML.exists()


def get_spec() -> mujoco.MjSpec:
    return mujoco.MjSpec.from_file(str(H1_2_XML))


##
# Actuator config (mjlab constants; no actuators in the source MJCF).
##

H1_2_ACTUATOR_M107_24_2 = BuiltinPositionActuatorCfg(
    target_names_expr=(
        ".*_hip_yaw.*",
        ".*_hip_pitch.*",
        ".*_hip_roll.*",
        "torso_joint",
    ),
    stiffness=98.7,
    damping=6.3,
    effort_limit=200.0,
    armature=0.025,
)
H1_2_ACTUATOR_M107_24_1 = BuiltinPositionActuatorCfg(
    target_names_expr=(".*_knee.*",),
    stiffness=157.7,
    damping=10.1,
    effort_limit=300.0,
    armature=0.04,
)
H1_2_ACTUATOR_GO2HV_1 = BuiltinPositionActuatorCfg(
    target_names_expr=(
        ".*_ankle_pitch.*",
        ".*_ankle_roll.*",
        ".*_shoulder_pitch.*",
        ".*_shoulder_roll.*",
    ),
    stiffness=19.7,
    damping=1.3,
    effort_limit=40.0,
    armature=0.005,
)
H1_2_ACTUATOR_GO2HV_2 = BuiltinPositionActuatorCfg(
    target_names_expr=(
        ".*_shoulder_yaw.*",
        ".*_elbow.*",
        ".*_wrist_pitch.*",
        ".*_wrist_roll.*",
        ".*_wrist_yaw.*",
    ),
    stiffness=7.9,
    damping=0.5,
    effort_limit=18.0,
    armature=0.002,
)

##
# Keyframe.
##

HOME_KEYFRAME = EntityCfg.InitialStateCfg(
    pos=(0, 0, 1.02),
    joint_pos={
        ".*_hip_pitch_joint": -0.2,
        ".*_knee_joint": 0.5,
        ".*_ankle_pitch_joint": -0.3,
        ".*_shoulder_pitch_joint": 0.28,
        ".*_elbow_joint": 0.52,
    },
    joint_vel={".*": 0.0},
)

##
# Collision config.
##

_FOOT_RE = r"^(left|right)_foot[1-7]_collision$"

FULL_COLLISION = CollisionCfg(
    geom_names_expr=(".*_collision",),
    contype=1,
    conaffinity=1,
    condim={_FOOT_RE: 3, ".*_collision": 1},
    priority={_FOOT_RE: 1, ".*": 0},
    friction={_FOOT_RE: (0.6,)},
)

H1_2_ARTICULATION = EntityArticulationInfoCfg(
    actuators=(
        H1_2_ACTUATOR_M107_24_2,
        H1_2_ACTUATOR_M107_24_1,
        H1_2_ACTUATOR_GO2HV_1,
        H1_2_ACTUATOR_GO2HV_2,
    ),
    soft_joint_pos_limit_factor=0.9,
)


def get_h1_2_robot_cfg() -> EntityCfg:
    """Return a fresh H1_2 robot configuration instance.

    A new EntityCfg is returned each call so shared configs are never
    mutated by later task wiring.
    """
    return EntityCfg(
        init_state=HOME_KEYFRAME,
        collisions=(FULL_COLLISION,),
        spec_fn=get_spec,
        articulation=H1_2_ARTICULATION,
    )


H1_2_ACTION_SCALE: dict[str, float] = {}
for actuator in H1_2_ARTICULATION.actuators:
    assert isinstance(actuator, BuiltinPositionActuatorCfg)
    assert actuator.effort_limit is not None
    for expression in actuator.target_names_expr:
        H1_2_ACTION_SCALE[expression] = 0.25 * actuator.effort_limit / actuator.stiffness

__all__ = [
    "H1_2_ACTION_SCALE",
    "H1_2_XML",
    "get_h1_2_robot_cfg",
    "get_spec",
]
