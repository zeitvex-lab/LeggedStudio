"""WTW（Walk-These-Ways 周期步态先验）技能的不可变常量（族级）。

来源：`local_tasks/robots/unitree/go2/tasks/locomotion/wtw.py` + `wtw_mdp.py` 里
的**任务数值**（theta 采样池、行为参数采样区间、奖励权重与核参数、命令/动作/求解
上限）。口径与 `trot/profile.py` 一致：技能级常量留默认值，机型身份（`task_id` /
`experiment_name`）必填、由机型侧传入 —— 换机型只换这份数据。

## 命名步态与 theta 池（相位数据）

Resample 池按**契约腿序**排列（`theta_pool[i]` = 第 i 条腿在各 gait 下的偏移）：

* `trot` = (0.0, 0.5, 0.5, 0.0)（对角步，`num_gaits=1` 时只采这一档）
* `pronk` = (0.0, 0.0, 0.0, 0.0)；`pace` = (0.5, 0.5, 0.0, 0.0)；
  `bound` = (0.0, 0.5, 0.5, 0.5)（源实现把它们记在 `_THETA_TABLE` 里，仅作说明）

## 行为参数

四个行为参数（步态周期 / 足高 / 基座高 / 俯仰）都只有**区间与初值**是真值：resample
事件按区间均匀采样，startup 事件用初值建立状态。源实现把初值写死在 `_state()` 里
（0.45 / 0.08 / 0.27 / 0.0，恰为各自区间中点）—— 本模块把它们显式列出（`*_init`），
区间与初值都由机型侧数据面持有。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


def _source_reward_weights() -> dict[str, float]:
    """源配方的奖励权重表（WTW 官方权重，逐值）。"""
    return {
        "tracking_lin_vel": 1.0,
        "tracking_ang_vel": 0.5,
        "tracking_base_height": 0.6,
        "tracking_orientation": 0.6,
        "tracking_foot_clearance": 0.9,
        "quad_periodic_gait": 1.5,
        "lin_vel_z": -0.5,
        "ang_vel_xy": -0.05,
        "dof_vel": -5e-4,
        "dof_acc": -2e-7,
        "action_rate": -0.01,
        "action_smoothness": -0.01,
        "torques": -2e-4,
        "foot_landing_vel": -0.1,
        "hip_pos": -1.0,
        "dof_pos_limits": -10.0,
        "collision": -1.0,
    }


def _source_theta_pool() -> tuple[tuple[float, ...], ...]:
    """Resample 池（按**契约腿序**；每腿四个候选偏移，源 `_THETA_LISTS` 的转置）。"""
    return (
        (0.0, 0.0, 0.5, 0.0),  # 第 1 腿（fl）
        (0.5, 0.0, 0.0, 0.0),  # 第 2 腿（fr）
        (0.5, 0.0, 0.5, 0.5),  # 第 3 腿（rl）
        (0.0, 0.0, 0.0, 0.5),  # 第 4 腿（rr）
    )


@dataclass(frozen=True)
class WtwProfile:
    # --- 机型身份（必填）-----------------------------------------------------------
    task_id: str
    experiment_name: str

    # --- 相位与行为参数（源 wtw_mdp 的初值 + resample 区间）-------------------------
    #: 全局相位推进用的控制步长（源 `ObservationTermCfg(params={"dt": 0.02})`）。
    clock_dt: float = 0.02
    #: 采样池里参与采样的步态档数（源 `num_gaits=1` ⇒ 只采第一档 = trot）。
    num_gaits: int = 1
    theta_pool: tuple[tuple[float, ...], ...] = field(default_factory=_source_theta_pool)
    gait_period_range: tuple[float, float] = (0.3, 0.6)
    foot_clearance_range: tuple[float, float] = (0.04, 0.12)
    base_height_range: tuple[float, float] = (0.2, 0.34)
    pitch_range: tuple[float, float] = (-0.3, 0.3)
    #: 四个行为参数的状态初值（源 `wtw_mdp._state()` 的写死值；恰为各自区间中点，
    #: 但**显式列出** —— 初值不是"从区间推出来的"，换机型可以另行取值）。
    gait_period_init: float = 0.45
    foot_clearance_init: float = 0.08
    base_height_init: float = 0.27
    pitch_init: float = 0.0

    # --- 任务 ----------------------------------------------------------------------
    #: 动作缩放（源 `cfg.actions["joint_pos"].scale = 0.25`，标量、全关节同值）。
    action_scale: float = 0.25
    episode_length_s: float = 20.0
    command_resampling_time_range: tuple[float, float] = (10.0, 10.0)
    #: rough 档 sim 上限（源 `ccd_iterations / contact_sensor_maxmatch = 500`）。
    rough_ccd_iterations: int = 500
    rough_contact_sensor_maxmatch: int = 500
    #: flat 档 sim 上限（源 `go2_wtw_flat_env_cfg`：njmax 300 / ccd 50 / maxmatch 64；
    #: 注意**不动** `nconmax` —— 源配方的 flat 档保留基座 35）。
    flat_sim_njmax: int = 300
    flat_ccd_iterations: int = 50
    flat_contact_sensor_maxmatch: int = 64

    # --- 奖励（权重 + 核参数）-------------------------------------------------------
    reward_weights: Mapping[str, float] = field(default_factory=_source_reward_weights)
    #: 速度跟踪核的 std（源 params，mjlab `exp(-err/std²)` 口径）。
    track_lin_vel_std: float = 0.425
    track_ang_vel_std: float = 0.7854
    #: 三个 exp 核的 sigma（源实现里是函数默认值；族级提为数据，机型可覆盖）。
    sigma_base_height: float = 0.01
    sigma_orientation: float = 0.1
    sigma_foot_clearance: float = 0.01
    #: 足端高度核的固定偏移（源 `foot_height_offset=0.022`）。
    foot_height_offset: float = 0.022
    #: 摆动/支撑相位的分界（源 `a_swing=0.0, b_swing=0.5`，弧度制相位）。
    a_swing: float = 0.0
    b_swing: float = 0.5
    #: 非足端触地惩罚的力阈值（源 `undesired_contacts(threshold=1.0)`）。
    collision_force_threshold: float = 1.0

    # --- 派生的初值 ----------------------------------------------------------------

    def initial_behavior(self) -> dict[str, float]:
        """状态初值（源实现 `_state()` 的写死值，逐值相同）。"""
        return {
            "gait_period": float(self.gait_period_init),
            "foot_clearance": float(self.foot_clearance_init),
            "base_height": float(self.base_height_init),
            "pitch": float(self.pitch_init),
        }
