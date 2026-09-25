"""ZEX-W 侧的族级 velocity 技能 profile 数据（**竞赛配方**，平地 / 越障两档）。

数值口径 = 源配方（`robot/config/env_cfgs.py` 的 `_make_base_env_cfg` / `flat_env_cfg` /
`rough_env_cfg`，族级化之前的字面值），**纯搬运**：一处数值都不改。两档的差异既在数值
（命令区间与朝向比、事件区间、跟踪核带宽与权重、地形）也在结构（奖励项集合、课程、
指标）——结构在族 Kit 的 `skills/velocity/competition.py`，本模块只给数 + 注入件。

| 档 | 变体 | 地形 | 奖励项 | 课程 | 指标 |
|---|---|---|---|---|---|
| `zex-w-flat` | `competition_flat` | 只含平地的地块生成器 | 16 项（轮奖励为主） | 无 | 1 项 |
| `zex-w-rough` | `competition_rough` | 族级竞赛课程（障碍释放） | 24 项（分轴跟踪 + 镜像 + 接触力） | 障碍释放 + 自适应 x/y/yaw | 30 项 |

`weights` 的键集合即该档的奖励项集合（见 `CompetitionRewardSpec` 的说明）：
越障档没给 `wheel_roll_tracking` / `wheel_contact_bonus` / `leg_motion_penalty` /
`body_collision` / `upright` / `joint_acc` / `track_lin_vel` / `track_ang_vel`
—— 与源实现里那一串 `pop` 一一对应。

职责边界：本模块**只有数 + 注入件**（命令类 / 动作项类 / mdp 名称空间 / 全局开关）；
结构与装配在族 Kit 的 `skills/velocity/competition.py`。

登记的既有事实（本轮纯搬运，不改）：

* `contract.json` 的 `observation.dimension=57`（16+16+16 统一布局）**与训练真值不符**：
  本包训练仍产出 53 维 actor（腿 12 + 轮 4 分列、各自缩放）。契约是 2026-09-24 观测统一
  时改的声明，训练侧未同步；按"上移不改行为"原样保留，是否统一由档案所有者裁决。
* `contract.json` 的 `control.decimation=10`（物理 500 Hz）与训练真值 `decimation=4`
  （物理 200 Hz）同样不符，来源同上。
"""

from __future__ import annotations

import math
import sys
from dataclasses import replace
from pathlib import Path

# 仓库根自举（见 kits/wheel_leg_kit 模块注释）：worker / schema-dump / 冒烟三种运行
# 环境都只把 ``training/source``（或包根）放进 sys.path；沿目录向上找 ``adapters/mjlab``
# 对 assets 源树与 workspace 镜像副本两种深度都成立。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.kits.wheel_leg_kit.skills import (  # noqa: E402
    CommandRanges,
    CompetitionActionSpec,
    CompetitionCommandLevel,
    CompetitionCommandSpec,
    CompetitionEventSpec,
    CompetitionMetric,
    CompetitionObservationSpec,
    CompetitionRewardSpec,
    CompetitionSimSpec,
    CompetitionVelocityProfile,
)

from ..mdp.commands import UniformThresholdVelocityCommandCfg  # noqa: E402
from ..mdp.lowpass_actions import (  # noqa: E402
    JointPositionDelayedLowPassActionCfg,
    JointVelocityDelayedLowPassActionCfg,
)
from ..mdp.only_positive_rewards import enable_only_positive_rewards  # noqa: E402
from . import terms as TERMS  # noqa: E402

#: 出生高（源 `robot_cfg.INIT_STATE.pos` 的 z；契约不声明这一项）。
INIT_BASE_HEIGHT = 0.42

#: 越障档的镜像关节对（腿序索引；`leg_ids = (fl, fr, rl, rr)`）：
#: 对角腿对（前后腿的俯仰/膝关节）与同侧腿对（同一侧的髋外展关节）。
_DIAGONAL_LEG_PAIRS = ((0, 3), (1, 2))
_SAME_SIDE_LEG_PAIRS = ((0, 2), (1, 3))

#: 越障档的命令区间课程（三轴各一项；函数名取注入名称空间里的课程类）。
_COMMAND_LEVELS = (
    CompetitionCommandLevel(
        term_name="command_x_levels",
        func_name="command_levels_adaptive",
        axis="x",
        reward_term_name="track_lin_vel_x_exp",
        initial_range=(-0.5, 0.5),
        delta_command=0.05,
        target_ratio=0.8,
        ema_alpha=0.5,
    ),
    CompetitionCommandLevel(
        term_name="command_y_levels",
        func_name="command_levels_adaptive",
        axis="y",
        reward_term_name="track_lin_vel_y_exp",
        initial_range=(-0.5, 0.5),
        delta_command=0.05,
        target_ratio=0.8,
        ema_alpha=0.5,
    ),
    CompetitionCommandLevel(
        term_name="command_yaw_levels",
        func_name="command_levels_adaptive",
        axis="yaw",
        reward_term_name="track_ang_vel_z_exp",
        initial_range=(-0.5, 0.5),
        delta_command=0.05,
        target_ratio=0.8,
        ema_alpha=0.5,
    ),
)

#: 越障档附加诊断指标：指标名 → (注入名称空间里的函数名, 参数)。
#: 名字不等于函数名（`tracking_lin_vel_along_cmd_error` ← `..._along_command_error` 等），
#: 故两样都显式登记 —— 指标只进日志，不影响训练行为。
_ROUGH_METRICS: tuple[tuple[str, CompetitionMetric], ...] = (
    ("tracking_lin_vel_error", CompetitionMetric("tracking_lin_vel_error", {"command_name": "twist"})),
    ("tracking_lin_vel_x_error", CompetitionMetric("tracking_lin_vel_x_error", {"command_name": "twist"})),
    ("tracking_lin_vel_y_error", CompetitionMetric("tracking_lin_vel_y_error", {"command_name": "twist"})),
    (
        "tracking_lin_vel_along_cmd_error",
        CompetitionMetric("tracking_lin_vel_along_command_error", {"command_name": "twist"}),
    ),
    (
        "actual_lin_vel_orthogonal_cmd",
        CompetitionMetric("actual_lin_vel_orthogonal_command_mean", {"command_name": "twist"}),
    ),
    ("tracking_yaw_vel_error", CompetitionMetric("tracking_yaw_vel_error", {"command_name": "twist"})),
    ("cmd_lin_vel", CompetitionMetric("command_lin_vel_mean", {"command_name": "twist"})),
    ("cmd_yaw_vel", CompetitionMetric("command_yaw_vel_abs_mean", {"command_name": "twist"})),
    ("actual_lin_vel", CompetitionMetric("actual_lin_vel_mean")),
    (
        "tracking_lin_vel_error_cmd_0_03",
        CompetitionMetric(
            "tracking_lin_vel_error_band_mean",
            {"command_name": "twist", "min_speed": 0.0, "max_speed": 0.3},
        ),
    ),
    (
        "tracking_lin_vel_error_cmd_03_07",
        CompetitionMetric(
            "tracking_lin_vel_error_band_mean",
            {"command_name": "twist", "min_speed": 0.3, "max_speed": 0.7},
        ),
    ),
    (
        "tracking_lin_vel_error_cmd_07_up",
        CompetitionMetric(
            "tracking_lin_vel_error_band_mean",
            {"command_name": "twist", "min_speed": 0.7, "max_speed": 10.0},
        ),
    ),
    (
        "tracking_lin_vel_x_error_cmd_0_03",
        CompetitionMetric(
            "tracking_lin_vel_axis_error_band_mean",
            {"axis": 0, "command_name": "twist", "min_speed": 0.0, "max_speed": 0.3},
        ),
    ),
    (
        "tracking_lin_vel_x_error_cmd_03_07",
        CompetitionMetric(
            "tracking_lin_vel_axis_error_band_mean",
            {"axis": 0, "command_name": "twist", "min_speed": 0.3, "max_speed": 0.7},
        ),
    ),
    (
        "tracking_lin_vel_x_error_cmd_07_up",
        CompetitionMetric(
            "tracking_lin_vel_axis_error_band_mean",
            {"axis": 0, "command_name": "twist", "min_speed": 0.7, "max_speed": 10.0},
        ),
    ),
    (
        "tracking_lin_vel_y_error_cmd_0_03",
        CompetitionMetric(
            "tracking_lin_vel_axis_error_band_mean",
            {"axis": 1, "command_name": "twist", "min_speed": 0.0, "max_speed": 0.3},
        ),
    ),
    (
        "tracking_lin_vel_y_error_cmd_03_07",
        CompetitionMetric(
            "tracking_lin_vel_axis_error_band_mean",
            {"axis": 1, "command_name": "twist", "min_speed": 0.3, "max_speed": 0.7},
        ),
    ),
    (
        "tracking_lin_vel_y_error_cmd_07_up",
        CompetitionMetric(
            "tracking_lin_vel_axis_error_band_mean",
            {"axis": 1, "command_name": "twist", "min_speed": 0.7, "max_speed": 10.0},
        ),
    ),
    (
        "cmd_band_0_03",
        CompetitionMetric(
            "command_band_active", {"command_name": "twist", "min_speed": 0.0, "max_speed": 0.3}
        ),
    ),
    (
        "cmd_band_03_07",
        CompetitionMetric(
            "command_band_active", {"command_name": "twist", "min_speed": 0.3, "max_speed": 0.7}
        ),
    ),
    (
        "cmd_band_07_up",
        CompetitionMetric(
            "command_band_active", {"command_name": "twist", "min_speed": 0.7, "max_speed": 10.0}
        ),
    ),
    ("wheel_raw_action_abs", CompetitionMetric("wheel_raw_action_abs_mean")),
    ("wheel_target_vel_abs", CompetitionMetric("wheel_target_vel_abs_mean")),
    ("wheel_actual_vel_abs", CompetitionMetric("wheel_actual_vel_abs_mean")),
    ("wheel_target_actual_vel_error", CompetitionMetric("wheel_target_actual_vel_error_mean")),
    ("wheel_actual_to_target_vel_ratio", CompetitionMetric("wheel_actual_to_target_vel_ratio_mean")),
    ("wheel_target_actual_sign_agreement", CompetitionMetric("wheel_target_actual_sign_agreement")),
    ("upright", CompetitionMetric("upright_metric")),
    (
        "base_ground_contact_rate",
        CompetitionMetric("base_ground_contact_metric", {"sensor_name": "base_ground_contact"}),
    ),
)

#: 平地档权重表（源 `_make_base_env_cfg` 的 16 项字面值）。
_FLAT_WEIGHTS = {
    "track_lin_vel": 2.5,
    "track_ang_vel": 2.5,
    "upright": 1.0,
    "base_height_l2": -2.0,
    "body_ang_vel": -0.1,
    "is_terminated": -200.0,
    "joint_torques": -2.0e-4,
    "joint_acc": -2.5e-7,
    "action_rate": -0.01,
    "joint_pos_limits": -10.0,
    "wheel_roll_tracking": 2.0,
    "wheel_contact_bonus": 0.5,
    "feet_air_time": 0.5,
    "leg_motion_penalty": -0.02,
    "stand_still": -0.2,
    "body_collision": -1.0,
}

#: 越障档权重表（源 `rough_env_cfg` 的 24 项；被 pop 掉的项不在表内 —— 键集合即项集合）。
_ROUGH_WEIGHTS = {
    "track_lin_vel_x_exp": 1.0,
    "track_lin_vel_y_exp": 1.0,
    "track_ang_vel_z_exp": 1.0,
    "base_height_l2": 0.0,
    "is_terminated": 0.0,
    "joint_torques": -2.5e-5,
    "action_rate": -0.01,
    "joint_pos_limits": -5.0,
    "feet_air_time": 0.15,
    "stair_lateral_yaw_drift": -1.0,
    "lin_vel_z": -2.0,
    "ang_vel_xy": -0.05,
    "joint_power": -2.0e-5,
    "leg_joint_acc_l2": -2.5e-7,
    "wheel_joint_acc_l2": -2.5e-9,
    "joint_mirror": -0.05,
    "joint_pos_penalty_ab": -1.0,
    "joint_pos_penalty_sagittal": -0.3,
    "abduction_mirror": -0.5,
    "feet_contact_without_cmd": 0.1,
    "upward": 0.5,
    "stand_still": -2.0,
    "undesired_contacts": -1.0,
    "contact_forces": -1.5e-4,
}

_COMMON_REWARDS = CompetitionRewardSpec(
    weights=_FLAT_WEIGHTS,
    tracking_std=0.5,
    upright_std=0.5,
    base_height_target=0.36,
    base_height_uses_height_scan=False,
    wheel_radius=0.10,
    wheel_track=0.32,
    wheel_roll_tracking_std=3.0,
    air_time_thresholds=(0.1, 0.5),
    air_time_velocity_threshold=0.1,
    command_threshold=0.1,
    leg_motion_command_threshold=0.05,
    leg_motion_tilt_relax_start=0.08,
    leg_motion_tilt_relax_end=0.30,
    leg_motion_contact_target=0.85,
    leg_motion_min_penalty_scale=0.2,
    joint_pos_penalty_stand_still_scale=5.0,
    joint_pos_penalty_velocity_threshold=0.5,
    undesired_contacts_threshold=1.0,
    contact_forces_threshold=100.0,
    drift_terrain_names=("pyramid_stairs", "pyramid_stairs_inv", "random_grid"),
    drift_y_scale=1.0,
    drift_yaw_scale=1.0,
    mirror_roles=("hip_pitch", "knee"),
    mirror_leg_pairs=_DIAGONAL_LEG_PAIRS,
    abduction_mirror_role="hip_abduction",
    abduction_mirror_leg_pairs=_SAME_SIDE_LEG_PAIRS,
)

#: 平地档（含全部公共数值；越障档由它 `replace` 派生）。
FLAT = CompetitionVelocityProfile(
    init_base_height=INIT_BASE_HEIGHT,
    num_envs=2048,
    env_spacing=2.5,
    decimation=4,
    episode_length_s=20.0,
    seed=None,
    # 平地档 sim：只有 timestep / impratio / cone（源实现不设接触传感器上限与 CCD 迭代）。
    sim=CompetitionSimSpec(timestep=0.005, impratio=100, cone="elliptic"),
    bad_orientation_limit_angle=1.0,
    # 平地地形：只含平地的地块生成器（源 `_make_base_env_cfg` 的字面值）。
    terrain_flat_tile_size=(8.0, 8.0),
    terrain_flat_border_width=20.0,
    terrain_flat_num_rows=10,
    terrain_flat_num_cols=20,
    terrain_max_init_terrain_level=5,
    # 命令：阈值命令类（死区 + 单轴采样 + 地形自适应）随本 profile 注入。
    command_cls=UniformThresholdVelocityCommandCfg,
    command=CompetitionCommandSpec(
        resampling_time_range=(10.0, 10.0),
        heading_command=True,
        heading_control_stiffness=0.6,
        rel_heading_envs=1.0,
        rel_standing_envs=0.15,
        rel_forward_envs=0.40,
        rel_lateral_envs=0.0,
        rel_yaw_envs=0.0,
        ranges=CommandRanges(
            lin_vel_x=(-1.0, 1.0), lin_vel_y=(-0.5, 0.5), ang_vel_z=(-1.0, 1.0)
        ),
        heading_range=(-math.pi, math.pi),
    ),
    # 动作：延时 + 一阶低通的动作项类（机型实现）随本 profile 注入。
    position_action_cls=JointPositionDelayedLowPassActionCfg,
    velocity_action_cls=JointVelocityDelayedLowPassActionCfg,
    leg_action=CompetitionActionSpec(
        control_frequency=50.0, cut_off_frequency=5.0, min_delay=0, max_delay=2
    ),
    wheel_action=CompetitionActionSpec(
        control_frequency=50.0, cut_off_frequency=15.0, min_delay=0, max_delay=2
    ),
    observations=CompetitionObservationSpec(
        base_ang_vel_scale=0.25,
        base_ang_vel_noise=0.2,
        projected_gravity_noise=0.05,
        joint_pos_noise=0.01,
        joint_vel_scale=0.05,
        joint_vel_noise=1.5,
        wheel_vel_scale=0.05,
        wheel_vel_noise=1.0,
        critic_base_lin_vel_scale=2.0,
        height_scan_clip=(-1.0, 1.0),
    ),
    height_scan_resolution=0.08,
    height_scan_size=(1.6, 1.0),
    height_scan_max_distance=5.0,
    # 机身碰撞监督的几何：该机型腿杆三段（link 命名事实，不含轮）。
    body_collision_patterns=(
        ".*_hip_abduction_Link",
        ".*_hip_pitch_Link",
        ".*_knee_Link",
    ),
    events=CompetitionEventSpec(
        reset_pose_range={"x": (-0.5, 0.5), "y": (-0.5, 0.5), "yaw": (-math.pi, math.pi)},
        reset_velocity_range={
            "x": (-0.5, 0.5),
            "y": (-0.5, 0.5),
            "z": (-0.5, 0.5),
            "roll": (-0.5, 0.5),
            "pitch": (-0.5, 0.5),
            "yaw": (-0.5, 0.5),
        },
        reset_joints_position_range=None,
        push_interval_range_s=(10.0, 15.0),
        push_velocity_range={"x": (-0.5, 0.5), "y": (-0.5, 0.5)},
        com_offset_range=(-0.05, 0.05),
        friction_range=(0.3, 1.0),
        actuator_gain_scale_range=(0.9, 1.1),
        base_mass_range=(-1.0, 3.0),
    ),
    rewards=_COMMON_REWARDS,
    command_levels=(),
    extra_metrics=(),
    terms=TERMS,
    # 平地档不开"总奖励裁剪"（源实现只在 rough / crawl 两档开）。
    setup_hook=None,
)

#: 越障档：地形课程 + 地形自适应命令 + 分轴命令课程 + 诊断指标；sim 加上限与 CCD 迭代。
ROUGH = replace(
    FLAT,
    seed=42,
    sim=CompetitionSimSpec(
        timestep=0.005, impratio=100, cone="elliptic", contact_sensor_maxmatch=128, ccd_iterations=80
    ),
    command=replace(
        FLAT.command,
        heading_control_stiffness=0.5,
        rel_standing_envs=0.02,
        rel_forward_envs=0.30,
        rel_lateral_envs=0.20,
        rel_yaw_envs=0.20,
        ranges=CommandRanges(
            lin_vel_x=(-1.0, 1.0), lin_vel_y=(-1.0, 1.0), ang_vel_z=(-1.0, 1.0)
        ),
    ),
    # 越障档重置：固定出生高 0.42 + 关节零偏重置；推扰更频繁。
    events=replace(
        FLAT.events,
        reset_pose_range={"z": (0.42, 0.42), "yaw": (-math.pi, math.pi)},
        reset_velocity_range={"x": (-0.2, 0.2), "y": (-0.1, 0.1), "yaw": (-0.2, 0.2)},
        reset_joints_position_range=(0.0, 0.0),
        push_interval_range_s=(5.0, 10.0),
    ),
    rewards=replace(
        _COMMON_REWARDS,
        weights=_ROUGH_WEIGHTS,
        tracking_std=0.25,
        base_height_target=0.42,
        base_height_uses_height_scan=True,
    ),
    command_levels=_COMMAND_LEVELS,
    extra_metrics=_ROUGH_METRICS,
    # 越障档开 HIMLoco 式"总奖励裁剪到 ≥0"（进程级、幂等的全局开关；源实现在建 cfg 前调用）。
    setup_hook=enable_only_positive_rewards,
)
