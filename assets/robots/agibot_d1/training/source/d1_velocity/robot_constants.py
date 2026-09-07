"""Agibot D1 robot constants for the package-local velocity task.

The MJCF ships with its own ``<motor>`` actuators (12 leg joints, uppercase
SDK names), so the entity mounts them via ``XmlActuatorCfg`` instead of
redefining gains here.
"""

from __future__ import annotations

from pathlib import Path

import mujoco
from mjlab.actuator import XmlActuatorCfg
from mjlab.entity import EntityArticulationInfoCfg, EntityCfg
from mjlab.utils.spec_config import CollisionCfg

_PACKAGE_ROOT = Path(__file__).resolve().parents[3]
D1_XML = _PACKAGE_ROOT / "model" / "robot.xml"
assert D1_XML.exists()


def get_spec() -> mujoco.MjSpec:
    return mujoco.MjSpec.from_file(str(D1_XML))


# Joint order matches the MJCF (uppercase SDK names, FR/FL/RR/RL x abad/hip/knee).
D1_JOINT_NAMES: tuple[str, ...] = (
    "FR_ABAD_JOINT", "FR_HIP_JOINT", "FR_KNEE_JOINT",
    "FL_ABAD_JOINT", "FL_HIP_JOINT", "FL_KNEE_JOINT",
    "RR_ABAD_JOINT", "RR_HIP_JOINT", "RR_KNEE_JOINT",
    "RL_ABAD_JOINT", "RL_HIP_JOINT", "RL_KNEE_JOINT",
)

INIT_STATE = EntityCfg.InitialStateCfg(
    pos=(0.0, 0.0, 0.45),
    joint_pos={
        ".*_HIP_JOINT": 0.8,
        ".*_KNEE_JOINT": -1.5,
    },
    joint_vel={".*": 0.0},
)

FULL_COLLISION = CollisionCfg(
    geom_names_expr=(".*",),
    contype=1,
    conaffinity=0,
    condim={r".*(foot|sole)_collision$": 3, ".*": 1},
    priority={r".*(foot|sole)_collision$": 1, ".*": 0},
    friction={r".*(foot|sole)_collision$": (0.6,)},
)

D1_ARTICULATION = EntityArticulationInfoCfg(
    actuators=(
        XmlActuatorCfg(target_names_expr=(".*",)),
    ),
    soft_joint_pos_limit_factor=0.9,
)


def get_d1_robot_cfg() -> EntityCfg:
    """Return a fresh D1 robot configuration instance."""
    return EntityCfg(
        init_state=INIT_STATE,
        collisions=(FULL_COLLISION,),
        spec_fn=get_spec,
        articulation=D1_ARTICULATION,
    )


D1_ACTION_SCALE: dict[str, float] = {
    ".*_ABAD_JOINT": 0.125,
    ".*_HIP_JOINT": 0.25,
    ".*_KNEE_JOINT": 0.25,
}

__all__ = [
    "D1_ACTION_SCALE",
    "D1_JOINT_NAMES",
    "D1_XML",
    "get_d1_robot_cfg",
    "get_spec",
]
