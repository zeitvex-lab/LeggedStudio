"""Go2-W 侧的族级 velocity 技能 profile 数据（一机型四档）。

数值口径 = 源配方（`unitree_rl_mjlab_go2w` 移植的 `go2w_velocity/env_cfgs.py`）：
四档共用一份 `ROUGH` 数据，其余三档用 `dataclasses.replace` 只改真正不同的数。

| 变体 | 派生方式 | 与前一档的差 |
|---|---|---|
| `rough` | `ROUGH` | 地形生成器档 + 自适应腿杆惩罚（权重 -0.08） |
| `flat` | `replace(ROUGH, ...)` | 平地 + 平惩罚（权重 -0.15） |
| `flat_legs_only` | `replace(FLAT, ...)` | 纯腿：动作/命令/奖励换档 + `LegsOnlyRecipe` |
| `flat_legs_only_omni` | `replace(LEGS_ONLY, ...)` | 全向命令 + 站立权重/姿态权重微调 |

职责边界：本模块**只有数**（任务配方），结构与装配在族 Kit 的 `skills/velocity/config.py`。
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

# 仓库根自举（见 kits/wheel_leg_kit 模块注释）：worker / 冒烟只把包根与
# training/source 放进 sys.path，不保证仓库根在场。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.kits.wheel_leg_kit.skills import (  # noqa: E402
    CommandRanges,
    LegsOnlyRecipe,
    VelocityProfile,
)

#: 源配方的出生高（`go2w_constants.INIT_STATE.pos` 的 z；契约不声明这一项）。
INIT_BASE_HEIGHT = 0.4

ROUGH = VelocityProfile(
    init_base_height=INIT_BASE_HEIGHT,
    wheel_radius=0.09,
    #: 轮距 = 左右轮 y 跨距，从包内 MJCF 腿链派生：hip_y 0.0465 + thigh_y 0.0955
    #: = 0.142/侧 ⇒ 0.284（2026-09-29 订正：旧值 0.19 无出处，yaw 项贡献算错 33%）。
    wheel_track=0.284,
    # 源配方 rough 档**没改**静态命令范围（沿用基座默认 x(-0.5,1.0) / z(-1.0,1.0)），
    # 训练时的实际范围由课程 stage 覆盖（stage-0 = x(-0.3,0.8) / z(-0.8,0.8)，
    # 只影响 t=0 的那一次采样）——按"迁移不改行为"照原样保留。
    # 2026-09-29 命令范围放宽（用户指令）：越障需要全向机动（侧移避障/倒退调整）；
    # 此前 vy=(0,0) 零采样是侧移档 0 分的直接原因。
    command_ranges=CommandRanges(
        lin_vel_x=(-1.0, 1.0),
        lin_vel_y=(-0.5, 0.5),
        ang_vel_z=(-1.0, 1.0),
    ),
    command_vel_stages=(
        {"step": 0, "lin_vel_x": (-0.6, 0.9), "lin_vel_y": (-0.3, 0.3), "ang_vel_z": (-0.8, 0.8)},
        {"step": 5000 * 24, "lin_vel_x": (-1.0, 1.5), "lin_vel_y": (-0.5, 0.5), "ang_vel_z": (-1.0, 1.0)},
    ),
    # 轮足 economics 对齐（2026-09-29，rc_old vendored 入口逐项对照）：
    #   轮滚跟踪核 std 8.0→3.0（rc 实证 3.0；8.0 时 exp(-err²/64) 近似平的，信号弱）；
    #   track 1.0→2.5（rc 同款——基座 1.0 把跟踪信号稀释 2.5 倍）；
    #   补 base_height_l2 −2.0 @ 0.36（rc 同款——全 dof 档此前没有定高项）。
    wheel_roll_tracking_std=3.0,
    track_linear_weight=2.5,
    track_angular_weight=2.5,
    base_height_target=0.36,
    base_height_weight=-2.0,
    pose_std_standing={"hip": 0.05, "thigh": 0.1, "calf": 0.15},
    pose_std_walking={"hip": 0.15, "thigh": 0.35, "calf": 0.5},
    pose_std_running={"hip": 0.15, "thigh": 0.35, "calf": 0.5},
    terrain_max_init_terrain_level=2,
    terrain_difficulty_range=(0.0, 0.45),
    terrain_overrides={
        "flat": {"proportion": 0.45},
        "random_rough": {"proportion": 0.30, "noise_range": (0.01, 0.05), "noise_step": 0.01},
        "hf_pyramid_slope": {"proportion": 0.15, "slope_range": (0.0, 0.25)},
        "wave_terrain": {"proportion": 0.10, "amplitude_range": (0.0, 0.06), "num_waves": 2.0},
        "pyramid_stairs": {"proportion": 0.0},
        "pyramid_stairs_inv": {"proportion": 0.0},
        "hf_pyramid_slope_inv": {"proportion": 0.0},
    },
    # 源配方轮腿档未改站立比（= 基座默认 0.05）
    rel_standing_envs=0.05,
    wheel_joint_pos_noise=0.01,
    wheel_joint_vel_noise=1.0,
    leg_motion_penalty_weight=-0.08,
)

FLAT = replace(
    ROUGH,
    command_ranges=CommandRanges(
        lin_vel_x=(-1.0, 1.0),
        lin_vel_y=(-0.5, 0.5),
        ang_vel_z=(-1.0, 1.0),
    ),
    command_vel_stages=(
        {"step": 0, "lin_vel_x": (-0.7, 1.0), "lin_vel_y": (-0.3, 0.3), "ang_vel_z": (-1.0, 1.0)},
        {"step": 5000 * 24, "lin_vel_x": (-1.0, 2.0), "lin_vel_y": (-0.5, 0.5), "ang_vel_z": (-1.2, 1.2)},
    ),
    leg_motion_penalty_weight=-0.15,
)

LEGS_ONLY = replace(
    FLAT,
    command_ranges=CommandRanges(
        lin_vel_x=(-0.2, 0.5),
        lin_vel_y=(0.0, 0.0),
        ang_vel_z=(-0.5, 0.5),
    ),
    command_vel_stages=(
        {"step": 0, "lin_vel_x": (-0.1, 0.25), "ang_vel_z": (-0.2, 0.2)},
        {"step": 3000 * 24, "lin_vel_x": (-0.25, 0.5), "ang_vel_z": (-0.4, 0.4)},
        {"step": 8000 * 24, "lin_vel_x": (-0.5, 0.8), "ang_vel_z": (-0.6, 0.6)},
    ),
    rel_standing_envs=0.15,
    legs_only=LegsOnlyRecipe(
        action_scale=0.35,
        wheel_spin_limit_max_speed=3.0,
        base_height_target=0.32,
        base_height_std=0.08,
        low_base_height=0.18,
        body_friction_range=(0.8, 1.8),
        # 学步正激励（2026-09-30 杠杆②，go2 G1 修复同值 +1.0）：1024×2000 对照实证
        # 无此项时 reward+12 全变站稳、vx 零位移——腿末端=轮，"步态"=轮接触节律。
        feet_air_time_weight=1.0,
    ),
)

OMNI = replace(
    LEGS_ONLY,
    command_ranges=CommandRanges(
        lin_vel_x=(-0.2, 0.5),
        lin_vel_y=(-0.15, 0.15),
        ang_vel_z=(-0.5, 0.5),
    ),
    command_vel_stages=(
        {
            "step": 0,
            "lin_vel_x": (-0.1, 0.25),
            "lin_vel_y": (-0.05, 0.05),
            "ang_vel_z": (-0.2, 0.2),
        },
        {
            "step": 3000 * 24,
            "lin_vel_x": (-0.25, 0.5),
            "lin_vel_y": (-0.15, 0.15),
            "ang_vel_z": (-0.4, 0.4),
        },
        {
            "step": 8000 * 24,
            "lin_vel_x": (-0.5, 0.8),
            "lin_vel_y": (-0.3, 0.3),
            "ang_vel_z": (-0.6, 0.6),
        },
        {
            "step": 14000 * 24,
            "lin_vel_x": (-0.8, 1.0),
            "lin_vel_y": (-0.4, 0.4),
            "ang_vel_z": (-0.8, 0.8),
        },
    ),
    rel_standing_envs=0.1,
    legs_only=replace(LEGS_ONLY.legs_only, stand_still_weight=-0.1, flat_orientation_weight=-3.5),
)
