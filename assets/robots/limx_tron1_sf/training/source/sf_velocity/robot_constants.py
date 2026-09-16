"""LimX TRON1 sole-foot robot constants for the package-local velocity task.

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
TRON1_SF_XML = _PACKAGE_ROOT / "model" / "robot.xml"
assert TRON1_SF_XML.exists()


def get_spec() -> mujoco.MjSpec:
    return mujoco.MjSpec.from_file(str(TRON1_SF_XML))


##
# Actuator config.
#
# B28 同族裁决:MJCF 为执行真值。model/robot.xml 的 <actuator> 段已内建全部
# 8 个执行器(8 个 <position>:abad/hip/knee kp=45 kv=1.5,forcerange ±80;
# ankle kp=45 kv=0.8,forcerange ±20;均 forcelimited;执行器名字与目标关节
# 同名,如 "abad_L_Joint"),且所有关节 armature=0.01、腿部 frictionloss=0 /
# 踝关节 frictionloss=0.01 已写在 <joint> 上。训练源不得对这些关节重复注入
# 执行器(再 spec.add_actuator 同名即抛 repeated name 'abad_L_Joint' in
# actuator → env 构建即崩,即本包冒烟所见)。
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
#   abad/hip/knee:cfg stiffness=45/damping=1.5/effort_limit=80/armature=0.01
#   与 MJCF kp=45/kv=1.5/forcerange ±80/<joint armature="0.01"> 全部一致。
#   ankle:cfg stiffness=45/damping=0.8/effort_limit=20/armature=0.01 与 MJCF
#   kp=45/kv=0.8/forcerange ±20/<joint armature="0.01"> 全部一致。
#   frictionloss:cfg 未设置;MJCF 腿 0 / 踝 0.01 生效。
#   即 sf 无实质参数差异,包装后运行时执行器数值与 MJCF 完全相同。
##

TRON1_SF_ACTUATOR_LEG = XmlActuatorCfg(
    target_names_expr=(".*(?:abad|hip|knee)_.*_Joint",),
    command_field="position",
)
TRON1_SF_ACTUATOR_ANKLE = XmlActuatorCfg(
    target_names_expr=(".*ankle_.*_Joint",),
    command_field="position",
)

##
# Initial state (source: init_state.pos z=0.85 m, default_joint_angles all 0).
##

INIT_STATE = EntityCfg.InitialStateCfg(
    pos=(0.0, 0.0, 0.85),
    joint_pos={".*_Joint": 0.0},
    joint_vel={".*": 0.0},
)

##
# Collision config.
##

_FOOT_GEOMS_RE = r"^ankle_[LR]_collision$"

FULL_COLLISION = CollisionCfg(
    geom_names_expr=(".*_collision",),
    contype=1,
    conaffinity=1,
    condim={_FOOT_GEOMS_RE: 3, ".*_collision": 1},
    priority={_FOOT_GEOMS_RE: 1, ".*_collision": 0},
    friction={_FOOT_GEOMS_RE: (0.6,)},
)

TRON1_SF_ARTICULATION = EntityArticulationInfoCfg(
    actuators=(
        TRON1_SF_ACTUATOR_LEG,
        TRON1_SF_ACTUATOR_ANKLE,
    ),
    soft_joint_pos_limit_factor=0.9,  # source rewards.soft_dof_pos_limit
)


def get_tron1_sf_robot_cfg() -> EntityCfg:
    """Return a fresh TRON1-SF robot configuration instance."""
    return EntityCfg(
        init_state=INIT_STATE,
        collisions=(FULL_COLLISION,),
        spec_fn=get_spec,
        articulation=TRON1_SF_ARTICULATION,
    )


##
# Action scale (source: control.action_scale = 0.25).
##

TRON1_SF_ACTION_SCALE: dict[str, float] = {}
for actuator in TRON1_SF_ARTICULATION.actuators:
    assert isinstance(actuator, XmlActuatorCfg)
    for expression in actuator.target_names_expr:
        TRON1_SF_ACTION_SCALE[expression] = 0.25

__all__ = [
    "INIT_STATE",
    "TRON1_SF_ACTION_SCALE",
    "TRON1_SF_ACTUATOR_ANKLE",
    "TRON1_SF_ACTUATOR_LEG",
    "TRON1_SF_ARTICULATION",
    "TRON1_SF_XML",
    "get_spec",
    "get_tron1_sf_robot_cfg",
]
