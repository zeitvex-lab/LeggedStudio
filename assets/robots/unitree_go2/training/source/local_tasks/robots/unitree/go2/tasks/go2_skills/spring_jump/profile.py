"""Go2 的弹簧跳配方数据（族级 `SpringJumpProfile` 的 go2 实例）。

族级数据类与机制在 `adapters/mjlab/kits/quadruped_kit/skills/spring_jump/`。本模块只填
**go2 自己的数**：机型身份与源配方里与几何相关的目标值 —— 其余（奖励权重表、观测噪声、
状态机常量、镜像置换）是算法配方，留在族级模块。

数值出处：注册自 Gym `go2_spring_jump`（原 `profile.py` 的字段逐值保留；几何与阈值取
族级默认 = 原 `config.py` / `rewards.py` 里写死的那些数）。
"""

from __future__ import annotations

from adapters.mjlab.kits.quadruped_kit.skills.spring_jump.profile import (
    SpringJumpProfile,
)

SPRING_JUMP = SpringJumpProfile(
    task_id="Unitree-Go2-Spring-Jump-Flat",
    experiment_name="go2_spring_jump",
    num_envs=4096,
    episode_length_s=5.0,
    physics_dt=0.005,
    decimation=4,
    action_scale=0.25,
    # 出生高：源配方 spring-jump 专属 0.39 m（jump 是 0.42，见 shared/robot.py）
    init_base_height=0.39,
    # 几何目标（原 config.py / rewards.py 写死：飞行 0.47 / 站姿 0.35、下限 0.2、
    # 落地最小飞行高 0.42、落地姿态角 0.6、足端目标 0.20、速度增益 1.6）
    flight_height=0.47,
    stance_height=0.35,
    stance_min_height=0.2,
    min_flight_height=0.42,
    max_landing_tilt=0.6,
    foot_clearance_target=0.20,
    tracking_lin_gain=1.6,
    # 阈值（原写死 30 / 150；落地判定 0.15）
    max_abs_joint_vel=30.0,
    max_contact_force=150.0,
    below_reset_height=0.15,
    base_contact_force_threshold=1.0,
    # 命令：重采样 5 s、起跳帧 50~60、目标前进速度 0.8~1.2 m/s
    command_resample_s=5.0,
    takeoff_frame_range=(50, 60),
    target_lin_vel_x=(0.8, 1.2),
    # 摩擦分桶（原写死 0.3~1.0 / 64 桶）
    friction_buckets=(0.3, 1.0),
    num_friction_buckets=64,
)
