"""DeepRobotics M20 侧的族级 velocity 技能 profile 数据（官方配方，两档共用一份数）。

数值口径 = 上游官方训练真值（`deeprobotics_m20/rough_env_cfg.py` / 发布方
`params/env.yaml`），也就是本包 `env_cfgs.py` 族级化之前的字面值：

* 命令：10 s 固定重采样 + 阈值采样（`UniformThresholdVelocityCommandM20` 的
  `|v_xy| < 0.2` 死区）、`lin_vel_x(-2,2) / lin_vel_y(-1,1) / ang_vel_z(-1,1) / heading(±3.14)`；
* 观测：rl_sdk 57 维布局的缩放与噪声（base_ang_vel ×0.25、joint_pos ×1.0（轮槽置零）、
  joint_vel ×0.05）；
* 奖励：官方 21 项表（权重见 `reward_weights`，阈值见各字段）；
* 地形：rough 档生成器 + 课程（初始等级 5）；sim 两档值见 `rough_sim` / `flat_sim`。

**rough 与 flat 共用同一份数**：两档的差异是**结构**（地形生成器退成平面、撤 terrain_scan
与地形课程、sim 换平地档）与 `flat_sim` 档值，其余数值一字不改 —— 故本模块只出
一个 `OFFICIAL` 实例，客户端把它交给两个变体。

职责边界：本模块**只有数 + 两个机型侧注入件**；结构与装配在族 Kit 的
`skills/velocity/official.py`。
"""

from __future__ import annotations

import sys
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
    OfficialVelocityProfile,
    SimOverride,
)

from .mdp import m20_rewards as TERMS  # noqa: E402
from .mdp.m20_rewards import UniformThresholdVelocityCommandM20  # noqa: E402

#: 出生高（上游 `M20.xml` 关键帧经 DreamWaQ `m20.yaml` 校正后的落地位；契约不声明这一项）。
INIT_BASE_HEIGHT = 0.4

OFFICIAL = OfficialVelocityProfile(
    init_base_height=INIT_BASE_HEIGHT,
    # 上游 fixed 10 s resampling（不是基座的 3~8 s）。
    command_resampling_time_range=(10.0, 10.0),
    command_ranges=CommandRanges(
        lin_vel_x=(-2.0, 2.0),
        lin_vel_y=(-1.0, 1.0),
        ang_vel_z=(-1.0, 1.0),
    ),
    # 上游写死 ±3.14（不是基座的 ±π）。
    heading_range=(-3.14, 3.14),
    # 观测缩放/噪声（上游 rough_env_cfg.py:104-107 的 rl_sdk 布局口径）。
    base_ang_vel_scale=0.25,
    base_ang_vel_noise=0.2,
    projected_gravity_noise=0.05,
    joint_pos_scale=1.0,
    joint_pos_noise=0.01,
    joint_vel_scale=0.05,
    joint_vel_noise=1.5,
    # 奖励阈值与目标。
    base_height_target=0.4,
    #: 速度跟踪带宽（上游 `std = sqrt(0.5)`）。
    tracking_std=0.7071067811865476,
    joint_pos_penalty_stand_still_scale=5.0,
    joint_pos_penalty_velocity_threshold=0.5,
    joint_pos_penalty_command_threshold=0.1,
    undesired_contacts_threshold=1.0,
    contact_forces_threshold=100.0,
    # 官方 21 项奖励权重（表结构在 Kit，数值在这里）。
    reward_weights={
        "lin_vel_z_l2": -2.0,
        "ang_vel_xy_l2": -0.02,
        "flat_orientation_l2": -2.0,
        "base_height_l2": -0.5,
        "joint_torques_l2": -2.5e-05,
        "joint_acc_l2": -2e-07,
        "joint_acc_wheel_l2": -1e-07,
        "joint_pos_limits": -5.0,
        "joint_power": -2e-05,
        "hip_joint_pos_penalty": -0.4,
        "thigh_joint_pos_penalty": -0.1,
        "knee_joint_pos_penalty": -0.1,
        "joint_mirror": -0.03,
        "action_rate_l2": -0.01,
        "undesired_contacts": -1.0,
        "contact_forces": -0.00015,
        "track_lin_vel_xy_exp": 2.0,
        "track_ang_vel_z_exp": 1.0,
        "feet_contact_without_cmd": 0.1,
        "stand_still": -2.0,
        "upward": 0.08,
    },
    # rough 档地形课程的初始等级（上游在 rough 分支里设一次，平地档沿用同值）。
    terrain_max_init_terrain_level=5,
    rough_sim=SimOverride(ccd_iterations=500, contact_sensor_maxmatch=500),
    # 平地档 sim：njmax 收敛、CCD 降档、nconmax 交给 warp 自适应（显式 None）。
    flat_sim=SimOverride(
        ccd_iterations=50,
        contact_sensor_maxmatch=64,
        nconmax=None,
        njmax=300,
    ),
    # 镜像关节对的腿序索引：`leg_ids = (fl, fr, hl, hr)` ⇒ (fl,hr) 与 (fr,hl) 互为对角。
    mirror_leg_pairs=((0, 3), (1, 2)),
    # 机型侧注入件：阈值速度命令类 + 上游专属 mdp 奖励核（技能层不许 import 机型包）。
    command_cls=UniformThresholdVelocityCommandM20,
    terms=TERMS,
)
