"""Deeprobotics Lite3 robot constants for the package-local velocity task.

The MJCF, actuator tuning and collision layout are owned by this robot
package.  The training model is ``model/robot.xml`` (built-in actuators;
see the adjudication note below), so the simulation and training paths
share one source of truth.

B8 训练去包化（试点轮）：与 unitree_b2 逐字重复的框架机制（MJCF 解析、
XmlActuatorCfg 包装、碰撞/动作缩放推导）上移到 ``adapters/mjlab/kits/quadruped_kit``；
本文件只留 Lite3 专属常量与裁决记录。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 仓库根自举（见 kits/quadruped_kit 模块注释）：worker / schema-dump / 冒烟三种
# 运行环境都只把 training/source 或包根放进 sys.path；沿目录向上找 adapters/mjlab
# 对 assets 源树与 workspace 镜像副本两种深度都成立。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from mjlab.entity import EntityArticulationInfoCfg, EntityCfg  # noqa: E402

from adapters.mjlab.kits import quadruped_kit as kit  # noqa: E402

LITE3_XML, get_spec = kit.package_mjcf(__file__)


##
# Actuator config.
#
# B28 同族裁决:MJCF 为执行真值。model/robot.xml 的 <actuator> 段已内建全部
# 12 个执行器(12 个 <position>:kp=30 kv=1,forcerange ±30 且 forcelimited;
# 执行器名字与目标关节同名,如 "FL_HipX_joint"),且所有关节 armature=0.01、
# frictionloss=0.2 已写在 <joint> 上。训练源不得对这些关节重复注册执行器
# (再 spec.add_actuator 同名即抛 repeated name 'FL_HipX_joint' in actuator
# → env 构建即崩)。
#
# 因此这里不再用 BuiltinPositionActuatorCfg 重新生成执行器,而是用
# XmlActuatorCfg 显式「以 MJCF 为准」包装既有执行器:gains/limits/armature
# 全部沿用 MJCF 定义,本模块不提供任何覆盖参数。包装同时保持
# entity._actuators 非空——动作侧(JointPositionAction 经
# Entity.find_joints_by_actuator_names 解析被驱动关节)与观测/随机化侧
# (actuator_ids → ctrl_ids)依赖该列表,故「整体跳过注册(空 actuators)」
# 不可行,只能包装。XmlActuator.compute 按 command_field 转发:position 组
# 出 position_target,与原 Builtin 语义一致。
#
# 参数差异(训练 cfg 曾写 vs MJCF 真值,按裁决以 MJCF 为准,参数对齐另行裁决):
#   stiffness:训练 cfg 曾写 40.0;MJCF kp=30 → 运行时 30(唯一实质差异)。
#   damping:cfg 1.0 与 MJCF kv=1 数值一致。
#   effort_limit:cfg 30.0 与 MJCF forcerange ±30 一致。
#   armature:cfg 0.01 与 MJCF <joint armature="0.01"> 一致。
#   frictionloss:cfg 未设置;MJCF <joint frictionloss="0.2"> 生效。
##

(
    LITE3_ACTUATOR_HIP,
    LITE3_ACTUATOR_THIGH,
    LITE3_ACTUATOR_CALF,
) = kit.position_actuator_trio((".*HipX.*", ".*HipY.*", ".*Knee.*"))

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

FULL_COLLISION = kit.quadruped_foot_collision()

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


LITE3_ACTION_SCALE: dict[str, float] = kit.action_scale_from_actuators(
    LITE3_ARTICULATION, 0.25
)

__all__ = [
    "LITE3_ACTION_SCALE",
    "LITE3_XML",
    "get_lite3_robot_cfg",
    "get_spec",
]
