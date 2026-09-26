"""Go2 的后空翻配方数据（族级 `BackflipProfile` 的 go2 实例）。

族级数据类与机制在 `adapters/mjlab/kits/quadruped_kit/skills/backflip/`。本模块只填
**go2 自己的数**：机型身份（task_id / experiment_name）与源配方里与几何相关的目标值 ——
其余（奖励权重表、观测噪声、状态机常量）是算法配方，留在族级 `config.py` / `rewards.py`。

数值出处：注册自 Gym `go2_backflip`（原 `go2_skills/backflip/profile.py` 的八个字段
逐值保留，新增字段取族级默认 = 原 `config.py` 里写死的那些数）。
"""

from __future__ import annotations

from adapters.mjlab.kits.quadruped_kit.skills.backflip.profile import BackflipProfile

BACKFLIP = BackflipProfile(
    task_id="Unitree-Go2-Backflip-Flat",
    experiment_name="go2_backflip",
    num_envs=4096,
    episode_length_s=4.0,
    physics_dt=0.005,
    decimation=4,
    action_scale=0.25,
    # 几何目标（原 config.py 写死：飞行 0.6 / 站姿 0.35，站姿下限 0.2）
    flight_height=0.6,
    stance_height=0.35,
    stance_min_height=0.2,
    # 关节速度上限与接触阈值（原 config.py 写死 30 / 150；落地判定 0.1）
    max_abs_joint_vel=30.0,
    below_reset_height=0.1,
    base_contact_force_threshold=1.0,
    max_contact_force=150.0,
    # 镜像腿对不在此声明：由绑定从腿标记派生（go2 腿序 FL,FR,RL,RR ⇒ (1,3)，与源写死值一致）
    # 命令重采样 5 s、起跳帧 50~60（原 config.py 写死）
    command_resample_s=5.0,
    takeoff_frame_range=(50, 60),
)
