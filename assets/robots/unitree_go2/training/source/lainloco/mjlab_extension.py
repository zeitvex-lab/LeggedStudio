"""Package-local MJLab asset extension for Unitree Go2.

The upstream mjlab distribution intentionally keeps its asset zoo small.  A
robot package can provide this module and register its assets at runtime,
without modifying the shared mjlab source tree or the control-plane backend.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import mujoco

from mjlab.actuator import BuiltinPositionActuatorCfg
from mjlab.entity import EntityArticulationInfoCfg, EntityCfg
from mjlab.utils.spec_config import CollisionCfg

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
# Keep the simulation model untouched; LLoco's manager config expects the
# canonical collision/site names from this training-specific MJCF.
GO2_XML = PACKAGE_ROOT / "model" / "training.xml"


def get_spec() -> mujoco.MjSpec:
    # MJLab 1.6 resolves meshdir relative to the XML file. The old
    # ``update_assets`` helper is no longer part of its public API.
    return mujoco.MjSpec.from_file(str(GO2_XML))


GO2_ACTUATOR_HIP = BuiltinPositionActuatorCfg(
    target_names_expr=(".*hip_.*",), stiffness=20.0, damping=1.0,
    effort_limit=23.5, armature=0.01,
)
GO2_ACTUATOR_THIGH = BuiltinPositionActuatorCfg(
    target_names_expr=(".*thigh_.*",), stiffness=20.0, damping=1.0,
    effort_limit=23.5, armature=0.01,
)
GO2_ACTUATOR_CALF = BuiltinPositionActuatorCfg(
    target_names_expr=(".*calf_.*",), stiffness=40.0, damping=2.0,
    effort_limit=45.0, armature=0.02,
)

INIT_STATE = EntityCfg.InitialStateCfg(
    pos=(0.0, 0.0, 0.32),
    joint_pos={
        ".*thigh_joint": 0.9,
        ".*calf_joint": -1.8,
        ".*R_hip_joint": 0.1,
        ".*L_hip_joint": -0.1,
    },
    joint_vel={".*": 0.0},
)

_FOOT_REGEX = "^[FR][LR]_foot_collision$"
FULL_COLLISION = CollisionCfg(
    geom_names_expr=(".*_collision",),
    condim={_FOOT_REGEX: 3, ".*_collision": 1},
    priority={_FOOT_REGEX: 1, ".*": 0},
    friction={_FOOT_REGEX: (0.6,)},
    solimp={_FOOT_REGEX: (0.9, 0.95, 0.023)},
    contype=1,
    conaffinity=0,
)
GO2_ARTICULATION = EntityArticulationInfoCfg(
    actuators=(GO2_ACTUATOR_HIP, GO2_ACTUATOR_THIGH, GO2_ACTUATOR_CALF),
    soft_joint_pos_limit_factor=0.9,
)


def get_go2_robot_cfg() -> EntityCfg:
    return EntityCfg(
        init_state=INIT_STATE,
        collisions=(FULL_COLLISION,),
        spec_fn=get_spec,
        articulation=GO2_ARTICULATION,
    )


GO2_ACTION_SCALE: dict[str, float] = {}
for actuator in GO2_ARTICULATION.actuators:
    assert isinstance(actuator, BuiltinPositionActuatorCfg)
    assert actuator.effort_limit is not None
    for expression in actuator.target_names_expr:
        GO2_ACTION_SCALE[expression] = 0.25 * actuator.effort_limit / actuator.stiffness


def register() -> dict[str, str]:
    """Install Go2 symbols under the canonical mjlab asset-zoo paths."""
    import mjlab.asset_zoo.robots as robots

    package_name = "mjlab.asset_zoo.robots.unitree_go2"
    module_name = f"{package_name}.go2_constants"
    package_module = sys.modules.get(package_name)
    if package_module is None:
        package_module = types.ModuleType(package_name)
        package_module.__path__ = []  # type: ignore[attr-defined]
        sys.modules[package_name] = package_module
    constants_module = sys.modules.get(module_name)
    if constants_module is None:
        constants_module = types.ModuleType(module_name)
        sys.modules[module_name] = constants_module
    for name in ("GO2_XML", "get_spec", "get_go2_robot_cfg", "GO2_ACTION_SCALE"):
        value = globals()[name]
        setattr(constants_module, name, value)
        setattr(package_module, name, value)
        setattr(robots, name, value)
    return {"module": module_name, "asset": str(GO2_XML)}


__all__ = ["GO2_XML", "GO2_ACTION_SCALE", "get_go2_robot_cfg", "get_spec", "register"]
