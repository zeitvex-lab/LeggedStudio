"""族级 velocity 技能的源配方数据（一机型一档一份实例）。

## 边界：这里放什么

**只放"源配方里的数"** —— 出生高、地形档、命令范围、姿态 std、轮几何、观测噪声、
腿杆惩罚与 legs-only 变体的数值。**不放**机型身份（关节名/腿序/PD 谱：那是契约的），
也不放技能结构（哪些奖励项、哪条分支、动作怎么切段：那是 `config.py` 的）。

数值的默认值 = 该技能源配方的公共口径（四变体一致的部分）；机型侧只需给真正
"这台机型/这一档"才有的数，其余用 `dataclasses.replace` 派生：

```python
ROUGH = VelocityProfile(init_base_height=0.4, wheel_radius=0.09, wheel_track=0.19, ...)
FLAT = replace(ROUGH, leg_motion_penalty_weight=-0.15)          # 平地档只差腿杆惩罚权重
LEGS_ONLY = replace(FLAT, ..., legs_only=LegsOnlyRecipe(...))   # 纯腿档换奖励结构 + 这组数
```
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class UnsetType(Enum):
    """哨兵：`SimOverride` 里"这一项**不改**"。

    与显式的 `None` 区分开 —— 官方配方平地档的 `nconmax=None` 是一个**真值**
    （交给 warp 自适应），不是"不动这一项"。
    """

    UNSET = "unset"


UNSET = UnsetType.UNSET


@dataclass(frozen=True)
class SimOverride:
    """sim 档覆盖（官方配方 rough / flat 两档各自的 sim 真值）。"""

    #: MuJoCo CCD 迭代上限（`cfg.sim.mujoco.ccd_iterations`）。
    ccd_iterations: int
    #: 接触传感器最大匹配数（`cfg.sim.contact_sensor_maxmatch`）。
    contact_sensor_maxmatch: int
    #: 约束数上限；`UNSET` = 不动这一项（继承基座值），`None` = 显式设为 None。
    nconmax: int | None | UnsetType = UNSET
    #: 雅可比上限；`UNSET` = 不动这一项。
    njmax: int | None | UnsetType = UNSET


@dataclass(frozen=True)
class OfficialVelocityProfile:
    """**官方（上游）**速度配方的源配方数据（一机型一档一份）。

    与 `VelocityProfile`（reference 配方）互不混用：两者描述的是两份不同的任务
    （奖励表/观测布局/命令口径都不同），工厂按 `variant` 分流。

    `command_cls` 与 `terms` 是**机型侧注入件**：官方配方的阈值命令类与几个上游专属
    mdp 奖励核住在机型包里（技能层不许 import 机型包），故随 profile 带入 ——
    它们是该机型自己的上游术语，不是技能结构。
    """

    #: 出生高（任务级参数）。
    init_base_height: float
    #: 命令重采样区间（官方口径：固定 10 s）。
    command_resampling_time_range: tuple[float, float]
    #: 命令采样范围。
    command_ranges: CommandRanges
    #: 朝向命令范围（官方档写死 ±3.14，不是 ±π）。
    heading_range: tuple[float, float]
    #: 观测缩放与噪声（官方 rl_sdk 布局）。
    base_ang_vel_scale: float
    base_ang_vel_noise: float
    projected_gravity_noise: float
    joint_pos_scale: float
    joint_pos_noise: float
    joint_vel_scale: float
    joint_vel_noise: float
    #: 奖励里的阈值与目标（权重表见 `reward_weights`）。
    base_height_target: float
    tracking_std: float
    joint_pos_penalty_stand_still_scale: float
    joint_pos_penalty_velocity_threshold: float
    joint_pos_penalty_command_threshold: float
    undesired_contacts_threshold: float
    contact_forces_threshold: float
    #: 奖励项名 → 权重（表结构在工厂里，数值在这里）。
    reward_weights: Mapping[str, float]
    #: rough 档地形课程的初始等级。
    terrain_max_init_terrain_level: int
    #: 两档 sim 值。
    rough_sim: SimOverride
    flat_sim: SimOverride
    #: 镜像关节对的腿序索引（按 `leg_ids` 的位置；对角腿对 = 源实现写死的配对）。
    mirror_leg_pairs: tuple[tuple[int, int], ...]
    #: 该机型的阈值速度命令类（子类化 `mjlab.tasks.velocity.mdp.UniformVelocityCommandCfg`）。
    command_cls: type
    #: 该机型的上游专属 mdp 名称空间（奖励核 + `ContactSensorRef`）。
    terms: Any


@dataclass(frozen=True)
class CommandRanges:
    """twist 命令的采样范围（每轴一个闭区间）。"""

    lin_vel_x: tuple[float, float]
    lin_vel_y: tuple[float, float]
    ang_vel_z: tuple[float, float]


@dataclass(frozen=True)
class LegsOnlyRecipe:
    """"纯腿行走"变体（去掉轮动作、换掉轮奖励）专属的源配方数值。"""

    #: 位置动作缩放（纯腿档用腿杆走路，缩放比轮腿档小）。
    action_scale: float
    #: 轮速限幅奖励的上限（rad/s）。
    wheel_spin_limit_max_speed: float
    #: 机身高度跟踪奖励的目标高度与带宽（米）。
    base_height_target: float
    base_height_std: float
    #: 机身过低终止阈值（米）。
    low_base_height: float
    #: 该档的地面摩擦随机化范围（abs）。
    body_friction_range: tuple[float, float]
    stand_still_weight: float = -0.2
    wheel_spin_limit_weight: float = -0.3
    base_height_weight: float = 1.0
    stand_still_command_threshold: float = 0.05
    wheel_spin_limit_command_threshold: float = 0.05
    flat_orientation_weight: float = -4.0
    body_ang_vel_weight: float = -0.2


@dataclass(frozen=True)
class VelocityProfile:
    """速度跟踪技能的源配方数据（一机型一档一份）。"""

    # --- 出生与轮几何（机型物理量：必须由机型侧给） ------------------------------
    init_base_height: float
    wheel_radius: float
    wheel_track: float
    # --- 命令（任务配方） --------------------------------------------------------
    command_ranges: CommandRanges
    #: `command_vel` 课程的逐段放宽表（每段：`{"step": 环境步, 各轴区间}`）。
    command_vel_stages: Sequence[Mapping[str, Any]]
    # --- 姿态 std 表（按**契约角色词**给：`{"hip": 0.05, ...}`） --------------------
    pose_std_standing: Mapping[str, float]
    pose_std_walking: Mapping[str, float]
    pose_std_running: Mapping[str, float]
    # --- 地形档（rough 变体用；平地/纯腿档不读） ----------------------------------
    terrain_max_init_terrain_level: int
    #: 地形难度区间（生成器级）。
    terrain_difficulty_range: tuple[float, float]
    #: 子地形覆盖表：`{子地形名: {字段: 值}}`（按框架地形集的名字改比例/噪声等）。
    terrain_overrides: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    # --- 命令细节（源配方四变体默认：无朝向指令、站立比与基座一致） -----------------
    heading_command: bool = False
    rel_heading_envs: float = 0.0
    #: 零速站立环境占比（基座默认 0.05：源配方轮腿档未改，纯腿档显式改）。
    rel_standing_envs: float = 0.05
    # --- 观测噪声（传感器模型量：机型侧给，默认用源配方公共口径） -------------------
    wheel_joint_pos_noise: float = 0.01
    wheel_joint_vel_noise: float = 1.0
    # --- 轮奖励（权重是技能配方、几何来自上面两行） --------------------------------
    wheel_roll_tracking_weight: float = 2.0
    wheel_roll_tracking_std: float = 8.0
    wheel_contact_bonus_weight: float = 0.5
    # --- 轮腿档的机身姿态权重（纯腿档由 LegsOnlyRecipe 覆盖） ----------------------
    flat_orientation_weight: float = -2.5
    body_ang_vel_weight: float = -0.1
    # --- 腿杆运动惩罚（rough=自适应、flat=平惩罚；两档权重不同） --------------------
    leg_motion_penalty_weight: float = -0.08
    leg_motion_command_threshold: float = 0.05
    leg_motion_tilt_relax_start: float = 0.08
    leg_motion_tilt_relax_end: float = 0.30
    leg_motion_contact_target: float = 0.85
    leg_motion_min_penalty_scale: float = 0.2
    # --- 纯腿变体专属数值（不给 = 该档不可用，配置工厂会判红） ----------------------
    legs_only: LegsOnlyRecipe | None = None
