"""Go2 的机器人工厂（薄委托 + 包内未上移技能自己的变体）。

**已上移的**：`trot_robot_cfg` / `jump_robot_cfg` 现在只是族级绑定的直通
（族级实现在 `.../quadruped_kit/skills/binding.py::robot_cfg`）——
默认姿、PD、力矩、armature、柔性限位系数全部从 go2 契约/MJCF 派生，
`armature=0.0` 属源配方刻意偏离契约（见 `go2_skills/binding.py` 的取证注释）。

**未上移的**：姿态类技能（rear_stand / handstand）与 DreamWaQ / spring-jump 的
机型变体仍留在本模块 —— 它们不在本次特技试点范围内（各自是独立技能）。
"""

from __future__ import annotations

from copy import deepcopy

from mjlab.actuator import IdealPdActuatorCfg
from mjlab.entity import EntityArticulationInfoCfg

from ..binding import GO2, GO2_TROT


def trot_robot_cfg():
    """[族级] 契约默认姿被 trot 源配方姿态覆盖（髋归零、四腿同姿）。"""
    return GO2_TROT.robot_cfg()


def jump_robot_cfg():
    """[族级] 契约默认姿 + 契约 PD（armature 按源配方）。"""
    return GO2.robot_cfg()


def spring_jump_robot_cfg():
    """Gym spring-jump has Jump's asymmetric pose but starts at 0.39 m."""
    cfg = jump_robot_cfg()
    cfg.init_state.pos = (0.0, 0.0, 0.39)
    return cfg


def dreamwaq_robot_cfg():
    """DreamWaQ uses Jump's asymmetric nominal stance and 20/.5 PD gains."""
    return jump_robot_cfg()


def rear_stand_robot_cfg():
    cfg = deepcopy(GO2.base_entity_cfg())
    cfg.init_state.pos = (0.0, 0.0, 0.42)
    cfg.init_state.joint_pos = {
        "FL_hip_joint": 0.1,
        "FR_hip_joint": -0.1,
        "RL_hip_joint": 0.1,
        "RR_hip_joint": -0.1,
        "FL_thigh_joint": 0.8,
        "FR_thigh_joint": 0.8,
        "RL_thigh_joint": 1.0,
        "RR_thigh_joint": 1.0,
        ".*calf_joint": -1.5,
    }
    cfg.articulation = EntityArticulationInfoCfg(
        actuators=(
            IdealPdActuatorCfg(
                target_names_expr=(".*hip_joint",),
                stiffness=40.0,
                damping=1.0,
                effort_limit=21.33,
                armature=0.0,
            ),
            IdealPdActuatorCfg(
                target_names_expr=(".*thigh_joint",),
                stiffness=40.0,
                damping=1.0,
                effort_limit=21.33,
                armature=0.0,
            ),
            IdealPdActuatorCfg(
                target_names_expr=(".*calf_joint",),
                stiffness=40.0,
                damping=1.0,
                effort_limit=31.995,
                armature=0.0,
            ),
        ),
        soft_joint_pos_limit_factor=0.9,
    )
    return cfg


def handstand_robot_cfg():
    cfg = rear_stand_robot_cfg()
    cfg.init_state.joint_pos = {
        "FL_hip_joint": 0.1,
        "FR_hip_joint": -0.1,
        "RL_hip_joint": 0.1,
        "RR_hip_joint": -0.1,
        "FL_thigh_joint": 0.8,
        "FR_thigh_joint": 0.8,
        "RL_thigh_joint": 1.0,
        "RR_thigh_joint": 1.0,
        ".*calf_joint": -1.5,
    }
    return cfg
