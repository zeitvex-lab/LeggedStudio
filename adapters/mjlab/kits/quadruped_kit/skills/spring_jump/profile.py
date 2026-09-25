"""弹簧跳（spring jump）的源配方数据（一机型一份）。

来源：`go2_skills/spring_jump/profile.py`（注册自 Gym `go2_spring_jump`）+
`config.py` / `rewards.py` 里写死的**与机型几何相关**的数。

边界与 backflip 一致：**只放"换机型必须换"的数**（几何目标高、速度阈值、髋列、足端
site 名、镜像对称的腿数/角色数、机型身份与规模），其余（奖励权重表、状态机常量、
观噪声向量）是算法配方，留 `config.py` / `rewards.py` / `symmetry.py` 就地可读。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpringJumpProfile:
    """一台机型的弹簧跳配方（任务级数值）。"""

    # --- 机型身份与规模 -----------------------------------------------------------
    task_id: str
    experiment_name: str
    num_envs: int = 4096
    episode_length_s: float = 5.0
    physics_dt: float = 0.005
    decimation: int = 4
    action_scale: float = 0.25
    # --- 出生高（任务级参数，契约不声明） ------------------------------------------
    #: 源配方：spring-jump 用 jump 的非对称站姿但**出生高 0.39 m**（jump 是 0.42）。
    init_base_height: float = 0.39
    # --- 几何目标（换机型必须换） --------------------------------------------------
    #: 飞行段躯干高度目标（米）。
    flight_height: float = 0.47
    #: 落地站姿高度目标（米）。
    stance_height: float = 0.35
    #: 站姿高度有效下限（米）。
    stance_min_height: float = 0.2
    #: `land_pos` 要求的最大飞行高度（米）与落地姿态角上限（rad）。
    min_flight_height: float = 0.42
    max_landing_tilt: float = 0.6
    #: 足端离地目标高（米，`foot_clearance` 的 `|h + x|` 项）。
    foot_clearance_target: float = 0.20
    #: 起跳前的目标前进速度增益（`tracking_lin_vel`：`exp(-(1.6·cmd_x − v_x)²)`）。
    tracking_lin_gain: float = 1.6
    #: 关节速度上限惩罚阈值（rad/s）与足端接触力上限（N）。
    max_abs_joint_vel: float = 30.0
    max_contact_force: float = 150.0
    #: 起跳/落地判定高度（米）。
    below_reset_height: float = 0.15
    base_contact_force_threshold: float = 1.0
    # --- 命令（一次性触发） --------------------------------------------------------
    command_resample_s: float = 5.0
    takeoff_frame_range: tuple[int, int] = (50, 60)
    #: 目标前进速度采样区间（源配方 0.8~1.2 m/s）。
    target_lin_vel_x: tuple[float, float] = (0.8, 1.2)
    # --- 启动 DR（源配方数值） -----------------------------------------------------
    friction_buckets: tuple[float, float] = (0.3, 1.0)
    num_friction_buckets: int = 64
    base_mass_range: tuple[float, float] = (-1.0, 1.0)
    # --- runner ------------------------------------------------------------------
    learning_rate: float = 1.0e-5
    max_iterations: int = 50_000
    save_interval: int = 100
    seed: int = 1
