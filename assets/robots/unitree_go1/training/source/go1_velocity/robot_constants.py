"""Unitree Go1 robot constants for the package-local velocity task.

Source of truth: HIMLoco ``legged_gym/envs/go1/go1_config.py`` (BSD-3) and
walk-these-ways ``go1_gym`` go1 config, plus the package MJCF.  The package
model is ``model/robot.xml`` (built-in position actuators; see the adjudication
note below), so the training and simulation paths share one source of truth.
Joint naming follows the Unitree ``*_joint`` convention.

执行器口径（2026-09-23 用户裁决统一方向，2026-09-28 落地）：**MJCF 为执行真值，
``XmlActuatorCfg`` 只包装不重设**——与族内 b2/lite3 同语义（B28/B35 裁决；先例与
参数对账注释见 ``lite3_velocity/robot_constants.py``）。``model/robot.xml`` 已内建
12 个 ``<position kp=35 kv=0.5>``，关节 ``armature=0.01``、``actuatorfrcrange``
hip/thigh ±23.7 / calf ±33.5——与契约 ``actuator_profile.by_role`` 逐值一致。

切换前后的参数对账（注入值〔HIMLoco 上游〕vs MJCF 真值〔契约/浏览器/部署口径〕）：

* stiffness：注入 40.0 → 运行时 **35**（实质差异①）；
* damping：注入 1.0 → **0.5**（实质差异②）；
* effort_limit：注入 23.7（calf 同值）→ MJCF forcerange **23.7/23.7/33.5**（calf 为契约真值）；
* armature：0.01 两边一致。

行为级影响（如实登记）：训练侧曾长期跑 40/1.0，而浏览器/部署按契约 35/0.5——本次
统一消灭的是这个既有的训练↔仿真增益分歧；既有 go1 策略要按新口径复现需重训。
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
from mjlab.utils.spec_config import CollisionCfg  # noqa: E402

from adapters.mjlab.kits import quadruped_kit as kit  # noqa: E402

GO1_XML, get_spec = kit.package_mjcf(__file__)


##
# Actuator config：XmlActuatorCfg 显式「以 MJCF 为准」包装既有执行器。
# gains/limits/armature 全部沿用 MJCF 定义（见文件头对账），本模块不提供任何
# 覆盖参数——包装保持 ``entity._actuators`` 非空供动作/观测/随机化侧解析，
# 语义与 lite3/b2 先例一致（机制说明见 quadruped_kit.position_actuator_trio）。
##

(
    GO1_ACTUATOR_HIP,
    GO1_ACTUATOR_THIGH,
    GO1_ACTUATOR_CALF,
) = kit.position_actuator_trio((".*_hip_joint", ".*_thigh_joint", ".*_calf_joint"))


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
    actuators=(
        GO1_ACTUATOR_HIP,
        GO1_ACTUATOR_THIGH,
        GO1_ACTUATOR_CALF,
    ),
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


GO1_ACTION_SCALE: dict[str, float] = kit.action_scale_from_actuators(
    GO1_ARTICULATION, 0.25
)

__all__ = [
    "FULL_COLLISION",
    "GO1_ACTION_SCALE",
    "GO1_ACTUATOR_CALF",
    "GO1_ACTUATOR_HIP",
    "GO1_ACTUATOR_THIGH",
    "GO1_ARTICULATION",
    "GO1_XML",
    "INIT_STATE",
    "get_go1_robot_cfg",
    "get_spec",
]
