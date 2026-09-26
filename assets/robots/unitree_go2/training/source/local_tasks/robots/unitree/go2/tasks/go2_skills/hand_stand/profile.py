"""Go2 的 handstand 档数据（族级 `StanceProfile` 的 go2 实例）。

族级数据类与机制在 `adapters/mjlab/kits/quadruped_kit/skills/stance/`。本模块只填
**go2 这一档的数**：机型身份 + 几何目标高 + 命令口径 + 事件微调 + runner —— 奖励权重表
与观测/奖励方程都在族级（技能配方，不随机型变）。

数值出处：注册自 Gym `Go2_Trot.py` 系谱的 Handstand 档（原 `profile.py` 的字段逐值保留；
命令/事件/runner 的数值来自原 `config.py` 里写死的那些）。
"""

from __future__ import annotations

from adapters.mjlab.kits.quadruped_kit.skills.stance.profile import StanceProfile

HANDSTAND = StanceProfile(
    variant="handstand",
    display_name="Handstand",
    task_id="Unitree-Go2-Handstand-Flat",
    experiment_name="go2_handstand",
    num_envs=4096,
    episode_length_s=20.0,
    physics_dt=0.005,
    decimation=4,
    action_scale=0.25,
    base_height_target=0.47,
    cycle_time=1.6,
    target_foot_height=0.06,
    # 命令：5 s 重采样、无朝向指令、x/yaw ±0.4（原 config.py 写死）
    command_resample_s=5.0,
    heading_command=False,
    rel_heading_envs=0.0,
    lin_vel_x=(-0.4, 0.4),
    ang_vel_z=(-0.4, 0.4),
    heading=None,
    # 事件微调：推扰动改成"加世界系速度冲量"并放宽到 1.0/1.0；三项关节 DR 区间更宽
    push_max_vel_xy=1.0,
    push_max_ang_vel=1.0,
    joint_friction_range=(0.01, 0.2),
    joint_damping_range=(0.0, 0.2),
    joint_armature_range=(0.005, 0.015),
    restitution_attribute="_handstand_restitution",
    # runner：15k 迭代、lr 1e-3、**不开**镜像损失（原实现如此）
    learning_rate=1.0e-3,
    max_iterations=15_000,
    save_interval=100,
    seed=1,
    mirror_loss=False,
)
