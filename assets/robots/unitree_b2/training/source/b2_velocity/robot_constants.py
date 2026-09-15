"""Unitree B2 robot constants for the package-local velocity task.

The MJCF, actuator tuning and collision layout are owned by this robot
package.  The training model is ``model/robot.xml`` (built-in position
actuators; see the adjudication note below), so the simulation and
training paths share one source of truth.
"""

from __future__ import annotations

from pathlib import Path

import mujoco
from mjlab.actuator import XmlActuatorCfg
from mjlab.entity import EntityArticulationInfoCfg, EntityCfg
from mjlab.utils.spec_config import CollisionCfg

_PACKAGE_ROOT = Path(__file__).resolve().parents[3]
B2_XML = _PACKAGE_ROOT / "model" / "robot.xml"
assert B2_XML.exists()


def get_spec() -> mujoco.MjSpec:
    return mujoco.MjSpec.from_file(str(B2_XML))


##
# Actuator config.
#
# B35(B28 同族)裁决:MJCF 为执行真值。model/robot.xml 的 <actuator> 段已内建
# 全部 12 个执行器(12 个 <position>:kp=160 kv=5,forcerange hip/thigh ±200、
# calf ±320 且 forcelimited;执行器名字与目标关节同名,如 "FL_hip_joint"),
# 且所有腿关节 armature=0.1、frictionloss=0 已写在 <joint> 上。训练源不得对
# 这些关节重复注入执行器(再 spec.add_actuator 同名即抛 repeated name
# 'FL_hip_joint' in actuator → env 构建即崩,即 B35 冒烟所见)。
#
# 因此这里不再用 BuiltinPositionActuatorCfg 重新生成执行器,而是用
# XmlActuatorCfg 显式「以 MJCF 为准」包装既有执行器(B28 先例):gains/limits/
# armature 全部沿用 MJCF 定义,本模块不提供任何覆盖参数,Xml 沿用不重设。
# 包装同时保持 entity._actuators 非空——动作侧(JointPositionAction 经
# Entity.find_joints_by_actuator_names 解析被驱动关节)与观测/随机化侧
# (actuator_ids → ctrl_ids)依赖该列表,故「整体跳过注册(空 actuators)」
# 不可行,只能包装。XmlActuator.compute 按 command_field 转发:position 组
# 出 position_target,与原 Builtin 语义一致。
#
# 参数差异(旧训练 cfg 曾写 vs MJCF 真值,逐项对照):
#   hip/thigh:cfg stiffness=160/damping=5/effort_limit=200/armature=0.1 与
#   MJCF kp=160/kv=5/forcerange ±200/<joint armature="0.1"> 全部一致。
#   calf:cfg stiffness=160/damping=5/effort_limit=320/armature=0.1 与 MJCF
#   kp=160/kv=5/forcerange ±320/<joint armature="0.1"> 全部一致。
#   即 b2 无实质参数差异(b2w 的 calf effort 300 残留问题在本包不存在),
#   包装后运行时执行器数值与 MJCF 完全相同。
##

B2_ACTUATOR_HIP = XmlActuatorCfg(
    target_names_expr=(".*hip.*",),
    command_field="position",
)
B2_ACTUATOR_THIGH = XmlActuatorCfg(
    target_names_expr=(".*thigh.*",),
    command_field="position",
)
B2_ACTUATOR_CALF = XmlActuatorCfg(
    target_names_expr=(".*calf.*",),
    command_field="position",
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
    assert isinstance(actuator, XmlActuatorCfg)
    for expression in actuator.target_names_expr:
        B2_ACTION_SCALE[expression] = 0.25

__all__ = [
    "B2_ACTION_SCALE",
    "B2_XML",
    "get_b2_robot_cfg",
    "get_spec",
]
