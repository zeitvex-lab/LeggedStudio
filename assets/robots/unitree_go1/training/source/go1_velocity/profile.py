"""Go1 的 velocity 任务数值 + 机型侧任务配方。

族级技能层（`quadruped_kit/skills/velocity/`）装配**族级机制**（基座 env cfg / 实体 /
动作装配 / 地形课程 / viewer / flat 与 play 收尾）；本模块给两样：

1. **`GO1_VELOCITY`（`VelocityProfile`）**：本档案的族级开关与任务数值；
2. **`recipe`**：本机型源配方里 Kit 装不出来的那几样（观测布局 / 奖励权重 / 传感器表 /
   终止 / 事件 / 命令），逐项来自原 `go1_velocity.env_cfg`（HIMLoco + walk-these-ways 口径）。

## 两条档位的源配方（`go1-velocity` = flat / `go1-velocity-rough` = HIMLoco Go1RoughCfg）

flat 与 rough 共用同一份实现：命令档（±1.0 / ±1.0 / ±3.14 + 朝向指令、10 s 重采样）、
观测布局（actor 45 维 × history 5：命令 / 重力 / 角速度 / 关节位置 / 关节速度 / 动作；
critic 60 维含 base_lin_vel 与足端接触力；角速度 ×0.25、关节速度 ×0.05）、
奖励表（tracking 1.0 / 0.5、ang_vel_xy -0.05、action_rate -0.01、dof_pos_limits -2.0、
air_time 0.0）与非足端非法接触终止（力阈值 10）；rough 另加地形课程与越界终止。

**足端类项按能力撤掉**：go1 的 MJCF 没有足端 site（足端就是 calf 体），
`binding.has_foot_sites()` 为假 ⇒ 族级装配撤掉 `foot_height_scan` 与四项依赖 site 的
奖励（`foot_clearance` / `foot_swing_height` / `soft_landing` / `foot_slip`）——与源
配方逐项同构，故 recipe 不必再管它们（`_configure_rewards` 里那四行被族能力取代）。
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs import mdp as envs_mdp
from mjlab.envs.mdp import dr
from mjlab.managers import EventTermCfg, SceneEntityCfg, TerminationTermCfg
from mjlab.sensor import ContactMatch, ContactSensorCfg
from mjlab.tasks.velocity import mdp as velocity_mdp
from mjlab.tasks.velocity.mdp import UniformVelocityCommandCfg

# 仓库根自举（与 binding.py 同一约定）。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.kits.quadruped_kit.skills.velocity.profile import (  # noqa: E402
    VelocityProfile,
)

#: 源配方的腿序（MJCF 序 FR/FL/RL/RR；契约腿序是 FL/FR/RL/RR）。
#: 足端几何/传感器的槽位序沿用源配方 —— 受影响的只有 `air_time`（权重 0.0，静音）
#: 与 critic 的 `foot_contact_forces` 段序，本笔不改（见报告：可另行统一到契约序）。
GO1_FOOT_GEOMS = ("FR_foot_collision", "FL_foot_collision", "RL_foot_collision", "RR_foot_collision")
#: 观测历史长度（源配方：actor 与 critic 都是 5）。
GO1_HISTORY_LEN = 5
#: 非足端非法接触阈值（源配方值）。
GO1_ILLEGAL_CONTACT_FORCE_THRESHOLD = 10.0


def _contact_sensors() -> tuple[ContactSensorCfg, ContactSensorCfg]:
    """源配方的两组传感器（足端 + 非足端），**逐字段同构**（足端不带 secondary）。"""
    feet = ContactSensorCfg(
        name="feet_ground_contact",
        primary=ContactMatch(mode="geom", pattern=GO1_FOOT_GEOMS, entity="robot"),
        fields=("found", "force"),
        reduce="netforce",
        num_slots=1,
        track_air_time=True,
    )
    other = ContactSensorCfg(
        name="nonfoot_ground_touch",
        primary=ContactMatch(
            mode="geom", pattern=".*_collision", entity="robot", exclude=GO1_FOOT_GEOMS
        ),
        fields=("found", "force"),
        reduce="netforce",
        num_slots=1,
        track_air_time=True,
    )
    return feet, other


def _restructure_actor_obs(cfg: ManagerBasedRlEnvCfg) -> None:
    """Actor 组：cmd / projected_gravity / ang_vel / joint_pos / joint_vel / action（源配方布局）。"""
    actor = cfg.observations["actor"]
    terms = dict(actor.terms)

    command = terms.pop("command")
    gravity = terms.pop("projected_gravity")
    ang_vel = terms.pop("base_ang_vel")
    ang_vel.scale = 0.25  # source obs_scales.ang_vel
    joint_pos = terms.pop("joint_pos")
    joint_vel = terms.pop("joint_vel")
    joint_vel.scale = 0.05  # source obs_scales.dof_vel
    actions = terms.pop("actions")
    for drop in ("base_lin_vel", "height_scan", "foot_height", "foot_air_time", "foot_contact"):
        terms.pop(drop, None)

    actor.terms = {
        "command": command,
        "projected_gravity": gravity,
        "base_ang_vel": ang_vel,
        "joint_pos": joint_pos,
        "joint_vel": joint_vel,
        "actions": actions,
    }
    actor.history_length = GO1_HISTORY_LEN
    critic = cfg.observations["critic"]
    critic.history_length = GO1_HISTORY_LEN
    for drop in ("height_scan", "foot_height", "foot_air_time", "foot_contact"):
        critic.terms.pop(drop, None)


def _configure_rewards(cfg: ManagerBasedRlEnvCfg) -> None:
    """源指令的奖励权重（足端四项由族级**能力**撤掉，见模块 docstring）。"""
    cfg.rewards["track_linear_velocity"].weight = 1.0  # tracking_lin_vel
    cfg.rewards["track_angular_velocity"].weight = 0.5  # tracking_ang_vel
    cfg.rewards["body_ang_vel"].weight = -0.05  # ang_vel_xy
    cfg.rewards["action_rate_l2"].weight = -0.01  # action_rate
    cfg.rewards["dof_pos_limits"].weight = -2.0
    cfg.rewards["air_time"].weight = 0.0  # feet_air_time (source 0.0)


def _go1_recipe(
    cfg: ManagerBasedRlEnvCfg,
    binding,
    profile: VelocityProfile,
    *,
    terrain_profile: str,
    play: bool,
) -> None:
    """机型侧任务配方（源 `go1_velocity.env_cfg` 的机型专属接线，逐项同构）。"""
    # 1) 命令档：±1.0 / ±1.0 / ±3.14 + 朝向指令、10 s 重采样、可视化偏移。
    command = cfg.commands["twist"]
    assert isinstance(command, UniformVelocityCommandCfg)
    command.resampling_time_range = (10.0, 10.0)
    command.ranges.lin_vel_x = (-1.0, 1.0)
    command.ranges.lin_vel_y = (-1.0, 1.0)
    command.ranges.ang_vel_z = (-3.14, 3.14)
    command.ranges.heading = (-3.14, 3.14)
    command.viz.z_offset = 0.5

    # 2) 传感器表：源配方两组（族级只装足端且带 secondary、按契约腿序 —— 本机型按源口径整表替换）。
    feet_sensor, other_sensor = _contact_sensors()
    kept = tuple(
        sensor
        for sensor in (cfg.scene.sensors or ())
        if sensor.name not in ("feet_ground_contact", "nonfoot_ground_touch")
    )
    cfg.scene.sensors = kept + (feet_sensor, other_sensor)

    # 3) 终止：非足端非法接触（力阈值 10）；源配方 rough 档的 play 保留越界终止
    #    （族级 play 收尾会撤它）。
    cfg.terminations["illegal_contact"] = TerminationTermCfg(
        func=velocity_mdp.illegal_contact,
        params={
            "sensor_name": other_sensor.name,
            "force_threshold": GO1_ILLEGAL_CONTACT_FORCE_THRESHOLD,
        },
    )
    if play and terrain_profile == "rough":
        cfg.terminations["out_of_terrain_bounds"] = TerminationTermCfg(
            func=velocity_mdp.out_of_terrain_bounds, time_out=True
        )

    # 4) 课程：源配方两档都撤 `command_vel`（族级默认保留它）。
    cfg.curriculum.pop("command_vel", None)

    # 5) 事件：足端摩擦（单项、±(0.5,1.25)、源腿序几何）/ 质心三轴 ±0.03 / 扰动 10 s 档。
    if play:
        cfg.events.pop("foot_friction", None)
    else:
        cfg.events["foot_friction"] = EventTermCfg(
            mode="startup",
            func=dr.geom_friction,
            params={
                "asset_cfg": SceneEntityCfg("robot", geom_names=GO1_FOOT_GEOMS),
                "operation": "abs",
                "ranges": (0.5, 1.25),
                "shared_random": True,
            },
        )
    cfg.events["base_com"].params["ranges"] = {
        0: (-0.03, 0.03),
        1: (-0.03, 0.03),
        2: (-0.03, 0.03),
    }
    if not play:
        # interval_range_s 是 EventTermCfg 的字段，不是 params（见原档案注释）。
        cfg.events["push_robot"].interval_range_s = (10.0, 10.0)
        cfg.events["push_robot"].params["velocity_range"] = {
            "x": (-1.0, 1.0),
            "y": (-1.0, 1.0),
            "z": (-0.4, 0.4),
        }

    # 6) 观测布局（源配方：命令在前、角速度/关节速度带缩放、history 5）。
    _restructure_actor_obs(cfg)

    # 7) 奖励权重（足端四项已由族级能力撤掉）。
    _configure_rewards(cfg)
    # 族级 rough 配方给 upright 加 terrain_sensor_names（按地形法线算倾角）；源配方按世界 up 算。
    cfg.rewards["upright"].params.pop("terrain_sensor_names", None)

    # 8) 其余机型事实：viewer 距离（源配方 2.0，族级默认 1.5）；rough 档保留基座的倾角
    #    终止（族级 rough 配方撤 felt_over —— go1 源配方只加非法接触，不撤倾角终止）。
    cfg.viewer.distance = 2.0
    if terrain_profile == "rough":
        cfg.terminations["fell_over"] = TerminationTermCfg(
            func=envs_mdp.bad_orientation,
            params={"limit_angle": math.radians(profile.flat_tilt_limit_degrees)},
        )


GO1_VELOCITY = VelocityProfile(
    # 接触监看块自备（源配方：足端 + 非足端，非足端终止阈值 10）⇒ 族级四组传感器 /
    # 三项惩罚 / 摩擦三轴 DR / thigh 终止都不装配。
    contact_supervision=False,
    # 源配方不碰 impratio / cone（`sim.nconmax = None` 是它的装配骨架统一给的项）。
    mujoco_solver_tuning=False,
    contact_sensor_headroom=True,
    # flat 档撤 terrain_scan 传感器（源配方 flat 丢它 + 丢 height_scan 观测项）。
    flat_drop_terrain_scan=True,
    flat_drop_height_scan=True,
    # play 档：源配方只拉满回合 / 关噪声 / 清课程 / 撤扰动与摩擦，不动地形生成器，
    # 也不补展厅重建地形事件（族级展厅三项默认全开，故逐项关掉）。
    play_drop_push=True,
    play_randomize_terrain=False,
    play_showroom_terrain=False,
    # flat 档的求解器内存上限：源配方没设这一项（基座默认），族级默认 300 是 b2/lite3 的口径。
    flat_sim_njmax=None,
    # G1 对齐（2026-09-28，legged_gym 系结构；go2 同款实证 motion 0→0.459）：
    # feet_air_time 正激励（源配方 air_time 0.0 静音，legged_gym 系 +1~+2 是学走主正奖励）；
    # action_rate 显式化（源配方 -0.01）；only_positive_rewards（基座技巧：负总奖励截 0）；
    # stand_still 显式关（族级默认 -1.0 会自动注册，F1 实证短预算下惩罚主导）。
    air_time_weight=1.0,
    foot_clearance_override=0.0,
    foot_swing_height_override=0.0,
    foot_slip_override=0.0,
    action_rate_override=-0.01,
    only_positive_rewards=True,
    # 源配方严格按世界 up 算倾角（见 recipe 第 7 条）。
    pose_std_standing={"hip_abduction": 0.05, "hip_pitch": 0.05, "knee": 0.05},
    pose_std_moving={"hip_abduction": 0.15, "hip_pitch": 0.3, "knee": 0.35},
    # 动作缩放：源配方与 sim2sim 都声明实际缩放 0.25（见 binding 模块 docstring）。
    action_scale_by_role={"hip_abduction": 0.25, "hip_pitch": 0.25, "knee": 0.25},
    recipe=_go1_recipe,
)
