"""Unitree B2 的 handstand 档数据（族级 `StanceProfile` 的 b2 实例）。

族级数据类与机制在 `adapters/mjlab/kits/quadruped_kit/skills/stance/`。本模块只填
**b2 这一档的数**：机型身份 + 几何目标高 + 命令口径 + 事件微调 + runner —— 奖励权重表
与观测/奖励方程都在族级（技能配方，不随机型变）。

## 这份数据从哪来

本仓**没有 b2 专属的站姿类上游**（该技能的上游是 `00_resources` 里 Gym 包的
`Go2_Trot.py` 系谱）。所以除机型身份外，逐项取 go2 的 handstand 档数值（该文件里
每一项的出处注释照旧有效），与 `b2-wtw` / `b2-backflip` 同一纪律。

## 别把"能训"当成"训得好" —— 未按 b2 标定

`base_height_target`（0.47 m）与目标足高、事件 DR 区间是 go2 几何（站姿 0.42 m）
与质量量级下的数，b2 站姿 0.54 m 且重一档 ⇒ **未标定**；能训 ≠ 训得好。
登记在 `registry/porting_references.json` 的 `b2-handstand` 条目里。
"""

from __future__ import annotations

from adapters.mjlab.kits.quadruped_kit.skills.stance.profile import StanceProfile

HANDSTAND = StanceProfile(
    variant="handstand",
    display_name="Handstand",
    task_id="Unitree-B2-Handstand-Flat",
    experiment_name="b2_handstand",
    num_envs=4096,
    episode_length_s=20.0,
    physics_dt=0.005,
    decimation=4,
    action_scale=0.25,
    base_height_target=0.47,
    cycle_time=1.6,
    target_foot_height=0.06,
    command_resample_s=5.0,
    heading_command=False,
    rel_heading_envs=0.0,
    lin_vel_x=(-0.4, 0.4),
    ang_vel_z=(-0.4, 0.4),
    heading=None,
    push_max_vel_xy=1.0,
    push_max_ang_vel=1.0,
    joint_friction_range=(0.01, 0.2),
    joint_damping_range=(0.0, 0.2),
    joint_armature_range=(0.005, 0.015),
    restitution_attribute="_handstand_restitution",
    learning_rate=1.0e-3,
    max_iterations=15_000,
    save_interval=100,
    seed=1,
    mirror_loss=False,
)
