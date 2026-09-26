"""后空翻（backflip）技能的源配方数据。

来源：`go2_skills/backflip/profile.py`（`BackflipProfile`，注册自 Gym `go2_backflip`）
+ `config.py` 里写死的那些**与机型几何相关**的数（飞行/站姿目标高、关节速度上限、
镜像腿对）。

边界：**只放"换机型必须换"的数**（几何目标高、速度上限、镜像腿对、机型身份），
其余（奖励权重、状态机常量、观测噪声向量）是**算法配方**，留 `config.py` 与
`rewards.py` 就地可读 —— 与 `variants.py` 里"任务常量放 Kit 合法"同一口径
（先例：竞赛地形几何）。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BackflipProfile:
    """一台机型的后空翻配方（任务级数值）。"""

    # --- 机型身份与规模 -----------------------------------------------------------
    task_id: str
    experiment_name: str
    num_envs: int = 4096
    episode_length_s: float = 4.0
    physics_dt: float = 0.005
    decimation: int = 4
    action_scale: float = 0.25
    # --- 几何目标（换机型必须换） --------------------------------------------------
    #: 飞行段的躯干高度奖励目标（米）。
    flight_height: float = 0.6
    #: 落地站姿的躯干高度奖励目标（米）。
    stance_height: float = 0.35
    #: 站姿高度奖励的有效下限（低于它不给分）。
    stance_min_height: float = 0.2
    #: 关节速度上限惩罚的阈值（rad/s）。
    max_abs_joint_vel: float = 30.0
    #: 起跳/落地姿态触地的判定高度（米）。
    below_reset_height: float = 0.1
    base_contact_force_threshold: float = 1.0
    max_contact_force: float = 150.0
    #: 镜像腿对（腿序里的"右侧"下标）：对称关节奖励按这些腿取反髋外展。
    #: `None` = **由绑定派生**（族约定：含 R 不含 L 的是右腿）；显式给值则覆盖。
    mirror_leg_indices: tuple[int, ...] | None = None
    # --- 命令（一次性触发） --------------------------------------------------------
    command_resample_s: float = 5.0
    takeoff_frame_range: tuple[int, int] = (50, 60)
    # --- 启动 DR（源配方数值） -----------------------------------------------------
    friction_buckets: tuple[float, float] = (0.2, 1.25)
    num_friction_buckets: int = 64
    base_mass_range: tuple[float, float] = (-1.0, 1.0)
    # --- runner ------------------------------------------------------------------
    learning_rate: float = 1.0e-5
    max_iterations: int = 50_000
    save_interval: int = 100
    seed: int = 1
