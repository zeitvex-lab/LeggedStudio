"""Trot 技能的不可变常量（族级）。

来源：`go2_skills/trot/profile.py`。与 `jump/profile.py` 同一口径：
技能级常量留默认值，机型身份（`task_id` / `experiment_name`）必填、由机型侧传入。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TrotProfile:
    task_id: str
    experiment_name: str
    num_envs: int = 4096
    episode_length_s: float = 24.0
    physics_dt: float = 0.005
    decimation: int = 4
    action_scale: float = 0.25
    actor_frame_dim: int = 47
    actor_history: int = 10
    critic_frame_dim: int = 68
    critic_history: int = 3
    cycle_time: float = 0.5
    target_foot_height: float = 0.06
    base_height_target: float = 0.29
    learning_rate: float = 1.0e-5
    max_iterations: int = 15_000
