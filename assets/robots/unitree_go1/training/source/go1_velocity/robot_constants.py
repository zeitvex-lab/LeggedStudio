"""Unitree Go1 robot constants for the package-local velocity task.

Source of truth: HIMLoco ``legged_gym/envs/go1/go1_config.py`` (BSD-3) and
walk-these-ways ``go1_gym`` go1 config, plus the package MJCF.  The package
model is ``model/robot.xml`` (no built-in actuators; PD is injected here), so
the training and simulation paths share one model.  Joint naming follows the
Unitree ``*_joint`` convention.
"""

from __future__ import annotations

from pathlib import Path

import mujoco
from mjlab.actuator import BuiltinPositionActuatorCfg
from mjlab.entity import EntityArticulationInfoCfg, EntityCfg
from mjlab.utils.spec_config import CollisionCfg

_PACKAGE_ROOT = Path(__file__).resolve().parents[3]
GO1_XML = _PACKAGE_ROOT / "model" / "robot.xml"
assert GO1_XML.exists()


def get_spec() -> mujoco.MjSpec:
    """Load the package MJCF and drop its built-in actuators.

    The go1 model ships simple ``<position kp=35>`` actuators without damping;
    the velocity task injects its own PD actuators (stiffness 40 / damping 1.0)
    via ``BuiltinPositionActuatorCfg``, so the XML ones must be removed first
    (otherwise mjlab reports a repeated actuator name).
    """
    # 撤 XML 执行器 + 补传感器名 + 传感器只留消费集：唯一入口 adapters/mjlab/spec_utils.py
    # （此前撤执行器在这里与 zex-w / m20 各写一份，2026-09-24 收敛）。
    import sys as _sys

    for _parent in Path(__file__).resolve().parents:
        if (_parent / "adapters" / "mjlab").is_dir():
            if str(_parent) not in _sys.path:
                _sys.path.insert(0, str(_parent))
            break
    from adapters.mjlab.spec_utils import normalize_for_training

    spec = mujoco.MjSpec.from_file(str(GO1_XML))
    normalize_for_training(spec, strip_actuators=True)
    return spec


##
# Actuator config (source: Go1RoughCfg.control -- stiffness 40 N*m/rad,
# damping 1.0 N*m*s/rad; torque limit ~23.7 N*m from the Go1 motor spec).
##

GO1_ACTUATOR_LEG = BuiltinPositionActuatorCfg(
    target_names_expr=(".*_(?:hip|thigh|calf)_joint",),
    stiffness=40.0,
    damping=1.0,
    effort_limit=23.7,
    armature=0.01,
)

##
# Initial state (source: init_state.pos z=0.42 m + default joint angles).
##

INIT_STATE = EntityCfg.InitialStateCfg(
    pos=(0.0, 0.0, 0.42),
    joint_pos={
        "FL_hip_joint": 0.1, "RL_hip_joint": 0.1,
        "FR_hip_joint": -0.1, "RR_hip_joint": -0.1,
        "FL_thigh_joint": 0.8, "FR_thigh_joint": 0.8,
        "RL_thigh_joint": 1.0, "RR_thigh_joint": 1.0,
        "FL_calf_joint": -1.5, "FR_calf_joint": -1.5,
        "RL_calf_joint": -1.5, "RR_calf_joint": -1.5,
        ".*": 0.0,
    },
    joint_vel={".*": 0.0},
)

##
# Collision config.
##

_FOOT_GEOMS_RE = r"^[FR][RL]_foot_collision$"

FULL_COLLISION = CollisionCfg(
    geom_names_expr=(".*_collision",),
    contype=1,
    conaffinity=1,
    condim={_FOOT_GEOMS_RE: 3, ".*_collision": 1},
    priority={_FOOT_GEOMS_RE: 1, ".*_collision": 0},
    friction={_FOOT_GEOMS_RE: (0.6,)},
)

GO1_ARTICULATION = EntityArticulationInfoCfg(
    actuators=(GO1_ACTUATOR_LEG,),
    soft_joint_pos_limit_factor=1.0,
)


def get_go1_robot_cfg() -> EntityCfg:
    """Return a fresh Go1 robot configuration instance."""
    return EntityCfg(
        init_state=INIT_STATE,
        collisions=(FULL_COLLISION,),
        spec_fn=get_spec,
        articulation=GO1_ARTICULATION,
    )


GO1_ACTION_SCALE: dict[str, float] = {".*_(?:hip|thigh|calf)_joint": 0.25}

__all__ = [
    "FULL_COLLISION",
    "GO1_ACTION_SCALE",
    "GO1_ACTUATOR_LEG",
    "GO1_ARTICULATION",
    "GO1_XML",
    "INIT_STATE",
    "get_go1_robot_cfg",
    "get_spec",
]
