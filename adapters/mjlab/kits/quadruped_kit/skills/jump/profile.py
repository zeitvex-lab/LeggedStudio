"""Jump 技能的不可变常量（族级）。

来源：`go2_skills/jump/profile.py`。**技能级常量**（周期、目标足高、帧数、PPO 超参）
保留为默认值 —— 同族机型共享同一套配方；**机型身份**（`task_id` / `experiment_name`）
改为必填参数，由机型侧传入（例：go2 传 `Unitree-Go2-Jump-Flat` / `go2_jump`，
go1 传 `Unitree-Go1-Jump-Flat` / `go1_jump`）。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class JumpProfile:
    task_id: str
    experiment_name: str
    num_envs: int = 4096
    episode_length_s: float = 24.0
    physics_dt: float = 0.005
    decimation: int = 4
    action_scale: float = 0.25
    actor_frame_dim: int = 47
    actor_history: int = 10
    critic_frame_dim: int = 70
    critic_history: int = 3
    cycle_time: float = 1.5
    target_foot_height: float = 0.05
    base_height_target: float = 0.3
    learning_rate: float = 1.0e-4
    max_iterations: int = 15_000
