"""LimX TRON1 point-foot robot constants for the package-local velocity task.

The MJCF, actuator tuning and collision layout are owned by this robot
package.  The training model is ``model/robot.xml`` (built-in position
actuators; see the adjudication note below), so the simulation and
training paths share one source of truth.  Joint naming follows the
LimX ``*_Joint`` convention.
"""

from __future__ import annotations

from pathlib import Path

import mujoco
from mjlab.actuator import XmlActuatorCfg
from mjlab.entity import EntityArticulationInfoCfg, EntityCfg
from mjlab.utils.spec_config import CollisionCfg

_PACKAGE_ROOT = Path(__file__).resolve().parents[3]
TRON1_PF_XML = _PACKAGE_ROOT / "model" / "robot.xml"
assert TRON1_PF_XML.exists()


def get_spec() -> mujoco.MjSpec:
    return mujoco.MjSpec.from_file(str(TRON1_PF_XML))


##
# Actuator config.
#
# B28 同族裁决:MJCF 为执行真值。model/robot.xml 的 <actuator> 段已内建全部
# 6 个执行器(6 个 <position>:kp=42 kv=2.5,forcerange ±80 且 forcelimited;
# 执行器名字与目标关节同名,如 "abad_L_Joint"),且所有腿关节 armature=0.01、
# frictionloss=0 已写在 <joint> 上。训练源不得对这些关节重复注入执行器
# (再 spec.add_actuator 同名即抛 repeated name 'abad_L_Joint' in actuator
# → env 构建即崩,即本包冒烟所见)。
#
# 因此这里不再用 BuiltinPositionActuatorCfg 重新生成执行器,而是用
# XmlActuatorCfg 显式「以 MJCF 为准」包装既有执行器(B28 先例,参照
# unitree_b2/deeprobotics_lite3):gains/limits/armature 全部沿用 MJCF 定义,
# 本模块不提供任何覆盖参数,Xml 沿用不重设。包装同时保持 entity._actuators
# 非空——动作侧(JointPositionAction 经 Entity.find_joints_by_actuator_names
# 解析被驱动关节)与观测/随机化侧(actuator_ids → ctrl_ids)依赖该列表,
# 故「整体跳过注册(空 actuators)」不可行,只能包装。XmlActuator.compute
# 按 command_field 转发:position 组出 position_target,与原 Builtin 语义一致。
#
# 参数对照(旧训练 cfg 曾写 vs MJCF 真值):
#   stiffness:cfg 42.0 与 MJCF kp=42 一致。
#   damping:cfg 2.5 与 MJCF kv=2.5 一致。
#   effort_limit:cfg 80.0 与 MJCF forcerange ±80(forcelimited)一致。
#   armature:cfg 0.01 与 MJCF <joint armature="0.01"> 一致。
#   frictionloss:cfg 未设置;MJCF <joint frictionloss="0"> 生效。
#   即 pf 无实质参数差异,包装后运行时执行器数值与 MJCF 完全相同。
##

TRON1_PF_ACTUATOR_LEG = XmlActuatorCfg(
    target_names_expr=(".*_Joint",),
    command_field="position",
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
    assert isinstance(actuator, XmlActuatorCfg)
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
