"""Go2 的 rear_stand 档数据（族级 `StanceProfile` 的 go2 实例）。

族级数据类与机制在 `adapters/mjlab/kits/quadruped_kit/skills/stance/`。本模块只填
**go2 这一档的数**：机型身份 + 几何目标高 + 命令口径 + runner（本档**开**镜像损失）。

数值出处：注册自 Gym `Go2_Trot.py` 系谱的 Rear Stand 档（原 `profile.py` 的字段逐值保留；
命令/runner 的数值来自原 `config.py` 里写死的那些）。
"""

from __future__ import annotations

from adapters.mjlab.kits.quadruped_kit.skills.stance.profile import StanceProfile

REAR_STAND = StanceProfile(
    variant="rear_stand",
    display_name="Rear Stand",
    task_id="Unitree-Go2-Rear-Stand-Flat",
    experiment_name="go2_rear_stand",
    num_envs=4096,
    episode_length_s=20.0,
    physics_dt=0.005,
    decimation=4,
    action_scale=0.25,
    base_height_target=0.52,
    cycle_time=1.6,
    target_foot_height=0.06,
    # 命令：10 s 重采样、**带朝向指令**（rel_heading_envs=1.0）、x (-0.2,0.6)
    command_resample_s=10.0,
    heading_command=True,
    rel_heading_envs=1.0,
    lin_vel_x=(-0.2, 0.6),
    ang_vel_z=(-0.4, 0.4),
    heading=(-3.14, 3.14),
    # 事件：本档就是基座表（推扰动用 overwrite_root_velocity 0.4/0.6、关节 DR 区间较窄）
    push_max_vel_xy=None,
    push_max_ang_vel=None,
    joint_friction_range=(0.01, 0.1),
    joint_damping_range=(0.0, 0.1),
    joint_armature_range=(0.003, 0.08),
    restitution_attribute="_rear_stand_restitution",
    # runner：15k 迭代、lr 1e-3、**开**镜像损失
    learning_rate=1.0e-3,
    max_iterations=15_000,
    save_interval=100,
    seed=1,
    mirror_loss=True,
)
