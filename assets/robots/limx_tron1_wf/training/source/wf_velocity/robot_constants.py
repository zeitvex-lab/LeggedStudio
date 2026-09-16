"""LimX TRON1 wheel-foot robot constants for the package-local velocity task.

The MJCF, actuator tuning and collision layout are owned by this robot
package.  The training model is ``model/robot.xml`` (built-in position and
velocity actuators; see the adjudication note below), so the training and
simulation paths share one source of truth.  Joint naming follows the LimX
``*_Joint`` convention (``wheel_L_Joint`` / ``wheel_R_Joint``).
"""

from __future__ import annotations

from pathlib import Path

import mujoco
from mjlab.actuator import XmlActuatorCfg
from mjlab.entity import EntityArticulationInfoCfg, EntityCfg
from mjlab.utils.spec_config import CollisionCfg

_PACKAGE_ROOT = Path(__file__).resolve().parents[3]
TRON1_WF_XML = _PACKAGE_ROOT / "model" / "robot.xml"
assert TRON1_WF_XML.exists()


def get_spec() -> mujoco.MjSpec:
    return mujoco.MjSpec.from_file(str(TRON1_WF_XML))


##
# Actuator config.
#
# B28 同族裁决:MJCF 为执行真值。model/robot.xml 的 <actuator> 段已内建全部
# 8 个执行器(6 个 <position>:kp=42 kv=2.5,forcerange ±80;2 个 <velocity>
# 轮执行器:kv=0.8,forcerange ±40;均 forcelimited;执行器名字与目标关节
# 同名,如 "abad_L_Joint"/"wheel_L_Joint"),且所有关节 armature=0.01、
# 腿部 frictionloss=0 / 轮关节 frictionloss=0.01 已写在 <joint> 上。训练源
# 不得对这些关节重复注入执行器(再 spec.add_actuator 同名即抛 repeated name
# 'abad_L_Joint' in actuator → env 构建即崩,即本包冒烟所见)。
#
# 因此这里不再用 BuiltinPosition/VelocityActuatorCfg 重新生成执行器,而是用
# XmlActuatorCfg 显式「以 MJCF 为准」包装既有执行器(B28 先例,参照
# unitree_b2w 轮足同构先例):gains/limits/armature 全部沿用 MJCF 定义,
# 本模块不提供任何覆盖参数,Xml 沿用不重设。包装同时保持 entity._actuators
# 非空——动作侧(JointPositionAction/JointVelocityAction 经
# Entity.find_joints_by_actuator_names 解析被驱动关节)与观测/随机化侧
# (actuator_ids → ctrl_ids)依赖该列表,故「整体跳过注册(空 actuators)」
# 不可行,只能包装。XmlActuator.compute 按 command_field 转发:position 组
# 出 position_target、velocity 组出 velocity_target,与原 Builtin 语义一致。
#
# 参数对照(旧训练 cfg 曾写 vs MJCF 真值):
#   腿(abad/hip/knee):cfg stiffness=42/damping=2.5/effort_limit=80/
#   armature=0.01 与 MJCF kp=42/kv=2.5/forcerange ±80/
#   <joint armature="0.01"> 全部一致。
#   轮:cfg damping=0.8/effort_limit=40/armature=0.01 与 MJCF <velocity>
#   kv=0.8/forcerange ±40/<joint armature="0.01"> 全部一致。
#   frictionloss:cfg 未设置;MJCF 腿 0 / 轮 0.01 生效。
#   即 wf 无实质参数差异,包装后运行时执行器数值与 MJCF 完全相同。
##

TRON1_WF_ACTUATOR_LEG = XmlActuatorCfg(
    target_names_expr=(".*(?:abad|hip|knee)_.*_Joint",),
    command_field="position",
)
TRON1_WF_ACTUATOR_WHEEL = XmlActuatorCfg(
    target_names_expr=(".*wheel_.*_Joint",),
    command_field="velocity",
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
