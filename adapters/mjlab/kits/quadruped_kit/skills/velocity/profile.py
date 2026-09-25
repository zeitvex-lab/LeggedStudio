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

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - 只为注解，运行期不导入（避免 Kit↔包循环）
    from mjlab.envs import ManagerBasedRlEnvCfg

    from ..binding import QuadrupedSkillBinding


def _standing_std() -> dict[str, float]:
    return {"hip_abduction": 0.05, "hip_pitch": 0.05, "knee": 0.1}


def _moving_std() -> dict[str, float]:
    return {"hip_abduction": 0.3, "hip_pitch": 0.3, "knee": 0.6}


@dataclass(frozen=True)
class VelocityProfile:
    # --- 族级装配开关（默认 = 族级默认配方） ---------------------------------------
    #: rough 档的**族级接触监看块**：四组接触传感器（自碰撞 / 大腿 / 小腿 / 躯干）
    #: + 三项碰撞惩罚 + 足端摩擦三轴 startup DR + 大腿非法接触终止。
    #: `False` = 本机型自备这几样（传感器/事件/终止由机型 recipe 给，Kit 不装配）——
    #: 缺哪一样是**机型能力/配方决定**，不是机型名判断。
    contact_supervision: bool = True
    #: MuJoCo 求解器调优（`impratio 10` + `cone elliptic`，go2 配方）。`False` = 不碰这两项
    #: （保持基座/引擎默认）——机型按自己的源配方决定。
    mujoco_solver_tuning: bool = True
    #: 接触传感器留头（`sim.nconmax = None`）：机型的源装配骨架
    #: （`quadruped_kit.new_velocity_env_cfg`）统一给的一项（全身接触传感器需要余量）。
    #: 族级默认（go2 配方）不碰该项；`True` = 显式置 None。
    contact_sensor_headroom: bool = False
    #: flat 档的求解器内存上限（`sim.njmax`）。族级默认 300（b2 / lite3 源配方）；
    #: `None` = 保留基座默认（go1 源配方没设这一项）。
    flat_sim_njmax: int | None = 300
    #: flat 档是否撤 `terrain_scan` 传感器（族级默认撤；观测里没有高度扫描的机型保留）。
    flat_drop_terrain_scan: bool = True
    #: flat 档是否撤 actor/critic 的 `height_scan` 观测项（族级默认撤）。
    flat_drop_height_scan: bool = True
    #: **play 档三开关**（默认 = 族级/ go2 配方）：
    #: `play_drop_push` 撤扰动事件；`play_randomize_terrain` 补展厅重建地形事件；
    #: `play_showroom_terrain` 把地形生成器换成 5×5 + 10 m 边界的展厅档（False = 保留
    #: 训练档地形设置，只把回合拉满、关噪声、清课程）。
    play_drop_push: bool = True
    play_randomize_terrain: bool = True
    play_showroom_terrain: bool = True
    #: 机型侧**任务配方**（Kit 装不出来的那几样：观测布局 / 奖励表 / 传感器表 / 终止 /
    #: 事件 / 命令 / 地形子项）。签名 `(cfg, binding, profile, *, terrain_profile, play) -> None`，
    #: 在族级装配全部完成（含 flat / play 档）之后调用 —— 机型配方的最后一句。
    #: `None` = 族级默认配方。
    recipe: Callable[..., None] | None = None
    #: 逐**族角色**的动作缩放（`{"hip_abduction": 0.25, ...}`）。
    #: 契约 `action_scale` 有两种口径：go2 / lite3 声明的是**归一化**缩放（实际缩放 =
    #: 契约值 × 实体 effort/stiffness，见 `binding.action_scale_by_joint()`）；go1 / b2 的
    #: 源配方与 sim2sim 声明的是**实际**缩放（0.25，与实体谱无关）。口径不同的机型在此
    #: 显式给值（数据，不是 Kit 里的机型判断），缺省 = 用契约派生值。
    action_scale_by_role: Mapping[str, float] = field(default_factory=dict)

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
