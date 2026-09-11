"""Explicit task semantics shared by Isaac Gym and MJLab adapters.

These profiles are intentionally conservative locomotion defaults.  They make
the contract explicit and reproducible; backend-specific code may refine
actuator gains after a simulator smoke test without changing joint ordering.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class RobotTaskProfile:
    robot_id: str
    asset_variant: str
    joint_order: tuple[str, ...]
    default_joint_pos: Mapping[str, float]
    effort_limit: float
    velocity_limit: float
    control_dt: float
    action_scale: float
    base_height: float
    base_body: str
    contact_bodies: tuple[str, ...]
    terminate_bodies: tuple[str, ...]
    sensors: tuple[str, ...]
    observation_terms: tuple[str, ...]
    reward_terms: tuple[str, ...]
    mjlab_base_body: str | None = None
    mjlab_contact_bodies: tuple[str, ...] = ()

    @property
    def action_dim(self) -> int:
        return len(self.joint_order)

    @property
    def resolved_mjlab_base_body(self) -> str:
        return self.mjlab_base_body or self.base_body

    @property
    def resolved_mjlab_contact_bodies(self) -> tuple[str, ...]:
        return self.mjlab_contact_bodies or self.contact_bodies


def _leg_defaults(joints: tuple[str, ...]) -> dict[str, float]:
    result = {name: 0.0 for name in joints}
    for name in joints:
        low = name.lower()
        if "thigh" in low or "hip_flex" in low or "hip_pitch" in low or "hfe" in low:
            result[name] = 0.8
        elif "knee" in low or "calf" in low or "kfe" in low:
            result[name] = -1.5
    return result


COMMON_OBS = ("base_lin_vel", "base_ang_vel", "projected_gravity", "command", "joint_pos", "joint_vel")
COMMON_REWARDS = ("tracking_lin_vel", "tracking_ang_vel", "upright", "torque", "joint_accel", "action_rate", "feet_air_time", "collision")


def _profile(robot_id: str, variant: str, joints: tuple[str, ...], *, effort: float, velocity: float, base: str = "base", contacts: tuple[str, ...] = ("foot",), base_height: float = 0.5) -> RobotTaskProfile:
    return RobotTaskProfile(robot_id, variant, joints, _leg_defaults(joints), effort, velocity, 0.02, 0.25, base_height, base, contacts, (base,), ("imu_linear_velocity", "imu_angular_velocity"), COMMON_OBS, COMMON_REWARDS)


PROFILES: dict[str, RobotTaskProfile] = {
    "unitree_a1": RobotTaskProfile("unitree_a1", "default", ("FL_hip_joint", "RL_hip_joint", "FR_hip_joint", "RR_hip_joint", "FL_thigh_joint", "RL_thigh_joint", "FR_thigh_joint", "RR_thigh_joint", "FL_calf_joint", "RL_calf_joint", "FR_calf_joint", "RR_calf_joint"), _leg_defaults(("FL_hip_joint", "RL_hip_joint", "FR_hip_joint", "RR_hip_joint", "FL_thigh_joint", "RL_thigh_joint", "FR_thigh_joint", "RR_thigh_joint", "FL_calf_joint", "RL_calf_joint", "FR_calf_joint", "RR_calf_joint")), 33.5, 21.0, 0.02, 0.25, 0.42, "base", ("FL_foot", "FR_foot", "RL_foot", "RR_foot"), ("base",), ("imu_linear_velocity", "imu_angular_velocity"), COMMON_OBS, COMMON_REWARDS, "robot", ("FL_calf", "FR_calf", "RL_calf", "RR_calf")),
    "anymal_b": _profile("anymal_b", "default", ("LF_HAA", "LF_HFE", "LF_KFE", "RF_HAA", "RF_HFE", "RF_KFE", "LH_HAA", "LH_HFE", "LH_KFE", "RH_HAA", "RH_HFE", "RH_KFE"), effort=40.0, velocity=20.0, base="base", contacts=("LF_FOOT", "RF_FOOT", "LH_FOOT", "RH_FOOT")),
    "anymal_c": _profile("anymal_c", "default", ("LF_HAA", "LF_HFE", "LF_KFE", "RF_HAA", "RF_HFE", "RF_KFE", "LH_HAA", "LH_HFE", "LH_KFE", "RH_HAA", "RH_HFE", "RH_KFE"), effort=40.0, velocity=20.0, base="base", contacts=("LF_FOOT", "RF_FOOT", "LH_FOOT", "RH_FOOT")),
    "bipedal_walker": _profile("bipedal_walker", "walker3d_hip3d", ("hip_joint_saggital_right", "hip_joint_frontal_right", "hip_joint_transversal_right", "knee_joint_right", "ankle_joint_right", "hip_joint_saggital_left", "hip_joint_frontal_left", "hip_joint_transversal_left", "knee_joint_left", "ankle_joint_left"), effort=100.0, velocity=20.0, base="torso", contacts=("right_foot", "left_foot"),),
    "cassie": _profile("cassie", "default", ("hip_abduction_left", "hip_rotation_left", "hip_flexion_left", "thigh_joint_left", "ankle_joint_left", "toe_joint_left", "hip_abduction_right", "hip_rotation_right", "hip_flexion_right", "thigh_joint_right", "ankle_joint_right", "toe_joint_right"), effort=80.0, velocity=20.0, base="pelvis", contacts=("left_toe", "right_toe")),
    "booster_k1": _profile("booster_k1", "K1_22dof", ("AAHead_yaw", "Head_pitch", "ALeft_Shoulder_Pitch", "Left_Shoulder_Roll", "Left_Elbow_Pitch", "Left_Elbow_Yaw", "ARight_Shoulder_Pitch", "Right_Shoulder_Roll", "Right_Elbow_Pitch", "Right_Elbow_Yaw", "Left_Hip_Pitch", "Left_Hip_Roll", "Left_Hip_Yaw", "Left_Knee_Pitch", "Left_Ankle_Pitch", "Left_Ankle_Roll", "Right_Hip_Pitch", "Right_Hip_Roll", "Right_Hip_Yaw", "Right_Knee_Pitch", "Right_Ankle_Pitch", "Right_Ankle_Roll"), effort=30.0, velocity=18.0, base="Trunk", contacts=("left_foot_link", "right_foot_link")),
    "limx_tron1pf": _profile("limx_tron1pf", "default", ("abad_L_Joint", "hip_L_Joint", "knee_L_Joint", "abad_R_Joint", "hip_R_Joint", "knee_R_Joint"), effort=80.0, velocity=20.0, base="base_Link", contacts=("foot_L_Link", "foot_R_Link")),
    "limx_tron1sf": _profile("limx_tron1sf", "default", ("abad_L_Joint", "hip_L_Joint", "knee_L_Joint", "ankle_L_Joint", "abad_R_Joint", "hip_R_Joint", "knee_R_Joint", "ankle_R_Joint"), effort=80.0, velocity=20.0, base="base_Link", contacts=("ankle_L_Link", "ankle_R_Link")),
    "unitree_go2": _profile("unitree_go2", "default", ("FL_hip_joint", "RL_hip_joint", "FR_hip_joint", "RR_hip_joint", "FL_thigh_joint", "RL_thigh_joint", "FR_thigh_joint", "RR_thigh_joint", "FL_calf_joint", "RL_calf_joint", "FR_calf_joint", "RR_calf_joint"), effort=45.0, velocity=30.0, base="base", contacts=("FL_foot", "FR_foot", "RL_foot", "RR_foot")),
    "unitree_g1": _profile("unitree_g1", "g1_12dof", ("left_hip_pitch_joint", "left_hip_roll_joint", "left_hip_yaw_joint", "left_knee_joint", "left_ankle_pitch_joint", "left_ankle_roll_joint", "right_hip_pitch_joint", "right_hip_roll_joint", "right_hip_yaw_joint", "right_knee_joint", "right_ankle_pitch_joint", "right_ankle_roll_joint"), effort=139.0, velocity=32.0, base="pelvis", contacts=("left_ankle_roll_link", "right_ankle_roll_link")),
}


def get_task_profile(robot_id: str) -> RobotTaskProfile:
    try:
        return PROFILES[robot_id]
    except KeyError as exc:
        raise KeyError(f"no task semantic profile for {robot_id}") from exc


__all__ = ["PROFILES", "RobotTaskProfile", "get_task_profile"]
