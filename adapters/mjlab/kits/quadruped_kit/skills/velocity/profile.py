"""Velocity 技能的不可变常量（族级）。

口径与 `trot/profile.py` 一致：**只放任务级数值**（命令/地形/DR/奖励权重/终止阈值），
机型差异一律走 `QuadrupedSkillBinding`。默认值 = 源配方（mjlab velocity 基座 + 四足机型定制）
里的通用档：四足族各机型在这些数值上一致，机型侧只需覆盖真正不同的项
（例：go2 的 `dof_power_weight` 来自其结构层实验，见机型侧 profile 实例的取证注释）。

姿势奖励 std 表按**族角色**成键（`registry/families/<族>.json` 的 `joint_roles`），
键到关节名的翻译在技能层做（`binding.family_role` + `role_joint_pattern`）——
因此机型侧只填"哪个族角色、什么容差"，不写任何关节名。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


def _standing_std() -> dict[str, float]:
    return {"hip_abduction": 0.05, "hip_pitch": 0.05, "knee": 0.1}


def _moving_std() -> dict[str, float]:
    return {"hip_abduction": 0.3, "hip_pitch": 0.3, "knee": 0.6}


@dataclass(frozen=True)
class VelocityProfile:
    # --- 回合 / 命令 ---------------------------------------------------------------
    #: 基座已经是 20.0；显式声明让"改回合长度"成为机型 profile 可覆盖的数据。
    episode_length_s: float = 20.0
    #: play+flat 档的命令范围（源配方在展厅模式下放宽前向/偏航）。
    play_flat_lin_vel_x: tuple[float, float] = (-1.5, 2.0)
    play_flat_ang_vel_z: tuple[float, float] = (-0.7, 0.7)

    # --- 地形 ---------------------------------------------------------------------
    #: rough 档地形课程开关（play 档由族级展厅收尾统一关课程并换成 5×5 + 10 m 边界）。
    terrain_curriculum: bool = True

    # --- 启动 DR -------------------------------------------------------------------
    #: 足端三个摩擦轴（滑动 / 自旋 / 滚动）的绝对取值档。
    foot_friction_slide: tuple[float, float] = (0.3, 1.5)
    foot_friction_spin: tuple[float, float] = (1e-4, 2e-2)
    foot_friction_roll: tuple[float, float] = (1e-5, 5e-3)

    # --- 姿势奖励 std（按族角色）----------------------------------------------------
    pose_std_standing: Mapping[str, float] = field(default_factory=_standing_std)
    pose_std_moving: Mapping[str, float] = field(default_factory=_moving_std)

    # --- 奖励权重 ------------------------------------------------------------------
    #: 基座项的三个静音（源配方的奖励契约里没有这三项）。
    body_ang_vel_weight: float = 0.0
    angular_momentum_weight: float = 0.0
    air_time_weight: float = 0.0
    #: 三组自碰撞/腿杆/躯干接触惩罚共用的权重（rough 档注册）。
    collision_penalty_weight: float = -0.1
    #: 机械功率惩罚 `|tau*v|`：None = 不注册（族级默认）；数值 = 注册并给权重。
    dof_power_weight: float | None = None
    dof_power_kernel: str = "mean_abs"

    # --- 终止 ---------------------------------------------------------------------
    #: flat 档 `fell_over` 的倾角上限（度）。
    flat_tilt_limit_degrees: float = 70.0
