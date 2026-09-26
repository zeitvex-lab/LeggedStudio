"""Unitree B2 的 rear_stand 档数据（族级 `StanceProfile` 的 b2 实例）。

族级数据类与机制在 `adapters/mjlab/kits/quadruped_kit/skills/stance/`。本模块只填
**b2 这一档的数**：机型身份 + 几何目标高 + 命令口径 + 事件微调 + runner。

## 这份数据从哪来

本仓**没有 b2 专属的站姿类上游**（该技能的上游是 `00_resources` 里 Gym 包的
`Go2_Trot.py` 系谱）。除机型身份外，逐项取 go2 的 rear_stand 档数值，与 `b2-wtw` /
`b2-backflip` 同一纪律。注意本档的**镜像损失开关是开的**（源实现如此：仅 rear_stand 开）。

## 别把"能训"当成"训得好" —— 未按 b2 标定

`base_height_target`（0.52 m）与目标足高、事件 DR 区间是 go2 几何（站姿 0.42 m）
与质量量级下的数，b2 站姿 0.54 m 且重一档 ⇒ **未标定**；能训 ≠ 训得好。
登记在 `registry/porting_references.json` 的 `b2-leggedstand` 条目里。
"""

from __future__ import annotations

from adapters.mjlab.kits.quadruped_kit.skills.stance.profile import StanceProfile

REAR_STAND = StanceProfile(
    variant="rear_stand",
    display_name="Rear Stand",
    task_id="Unitree-B2-Rear-Stand-Flat",
    experiment_name="b2_rear_stand",
    num_envs=4096,
    episode_length_s=20.0,
    physics_dt=0.005,
    decimation=4,
    action_scale=0.25,
    base_height_target=0.52,
    cycle_time=1.6,
    target_foot_height=0.06,
    command_resample_s=10.0,
    heading_command=True,
    rel_heading_envs=1.0,
    lin_vel_x=(-0.2, 0.6),
    ang_vel_z=(-0.4, 0.4),
    heading=(-3.14, 3.14),
    push_max_vel_xy=None,
    push_max_ang_vel=None,
    joint_friction_range=(0.01, 0.1),
    joint_damping_range=(0.0, 0.1),
    joint_armature_range=(0.003, 0.08),
    restitution_attribute="_rear_stand_restitution",
    learning_rate=1.0e-3,
    max_iterations=15_000,
    save_interval=100,
    seed=1,
    mirror_loss=True,
)
