"""Lite3 的 velocity 任务数值 + 机型侧任务配方。

族级技能层（`quadruped_kit/skills/velocity/`）装配**族级机制**（基座 env cfg / 实体 /
动作装配 / 地形课程 / viewer / flat 与 play 收尾）；本模块给两样：

1. **`LITE3_VELOCITY`（`VelocityProfile`）**：本档案的族级开关与任务数值；
2. **`recipe`**：本机型源配方里 Kit 装不出来的那几样（观测布局 / 奖励权重 / 传感器表 /
   终止 / 事件 / 命令 / 地形子项），逐项来自原 `lite3_velocity.env_cfg`（官方
   DeepRoboticsLab 训练配置口径）。

## 口径登记（不静默改行为）

* **动作缩放**：本机型 `XmlActuatorCfg` 只包装 MJCF（PD 来自资产），技能层的
  `action_scale_by_joint()` 比值恒 1.0 ⇒ 派生值 = 契约逐角色缩放
  （hipx 0.125 / hipy 0.25 / knee 0.25）= 源配方 `LITE3_ACTION_SCALE` —— 三者一致，
  故 profile **不需要** `action_scale_by_role` 覆盖（与 b2 的契约/源配方冲突情形不同）。
* **足端帧**：MJCF 无足端 site，足端是 `<LR>_FOOT` body（B31 裁决）——族级足端高度扫描
  按 `binding.foot_scan_frames()` 的 body 口径装配（数据能力，不是 Kit 里的机型判断）。
* **flat 档保留 `terrain_scan` 传感器**：本机型 45 维 rl_sdk 观测里**没有** height_scan 项
  （观测整表由本模块替换），传感器照源配方保留 ⇒ `flat_drop_terrain_scan=False`、
  `flat_drop_height_scan=False`。
* **play 档**：源配方只拉满回合 / 关噪声 / 清课程 / 换展厅地形，**不**补
  `randomize_terrain` 事件 ⇒ `play_randomize_terrain=False`；flat 档命令范围照训练档
  （不改宽）⇒ `play_flat_*` 给训练档原值。
* **接触监看**：本机型自备两组传感器（`foot_contact` 按 `<LR>_SHANK` 接触面 +
  `full_contact` 全身）与奖励表，不是族级默认的四组 ⇒ `contact_supervision=False`。
* **gait_level 课程**：源实现里 `terrain_levels_vel_with_gait`（写 `gait_level` 全局量）
  **未接线**（当前训练路径的 `terrain_levels` 就是基座函式，`gait_level` 恒 0）——
  本轮照现状上移，不悄悄换课程（属可另行裁决的存量项）。
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs import mdp as envs_mdp
from mjlab.managers.reward_manager import RewardTermCfg
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.managers.observation_manager import ObservationTermCfg
from mjlab.managers.termination_manager import TerminationTermCfg
from mjlab.sensor import ContactMatch, ContactSensorCfg
from mjlab.tasks.velocity import mdp as velocity_mdp
from mjlab.tasks.velocity.mdp import UniformVelocityCommandCfg
from mjlab.utils.noise import UniformNoiseCfg as Unoise

# 仓库根自举（与 binding.py 同一约定）。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "adapters" / "mjlab").is_dir():
        if str(_parent) not in sys.path:
            sys.path.insert(0, str(_parent))
        break

from adapters.mjlab.kits.quadruped_kit.skills.velocity.profile import (  # noqa: E402
    VelocityProfile,
)

from . import lite3_rewards as lite3_mdp  # noqa: E402

#: 足端接触面（源配方 `FOOT_PATTERN`）：lite3 没有专用足端 link，接触点在 shank 末端球
#: （族内唯一此类资产事实；几何/body 名都是本机型资产的写法，故留在机型侧配方里）。
FOOT_PATTERN = r".*_SHANK"
#: 足端接触面 body 名的尾段（与 FOOT_PATTERN 同一事实的两种写法）。
FOOT_BODY_TOKEN = "SHANK"
#: 足端接触对的角色词（`asset.find_joints` 是大小写敏感的 fullmatch，取源配方拼法）。
_FOOT_ROLE_ALTERNATION = "(HipX|HipY|Knee)"


def _joints_by_role(binding, role: str) -> list[str]:
    """契约角色词 → 该角色的全部关节名（契约关节序过滤 —— 组内序与源配方一致）。"""
    return list(binding.joint_names(binding.family_role(role)))


def _joint_groups(binding) -> dict[str, list[str]]:
    """源配方的三个关节组（全 HipX → 全 HipY → 全 Knee），组内序 = 契约关节序。"""
    return {role: _joints_by_role(binding, role) for role in binding.leg_pattern}


def _foot_bodies(binding) -> list[str]:
    """足端接触面 body（`<腿>_SHANK`），腿序取契约 `leg_ids`。"""
    return [f"{leg}_{FOOT_BODY_TOKEN}" for leg in binding.leg_ids]


def _contact_sensors(binding) -> tuple[ContactSensorCfg, ContactSensorCfg]:
    """源配方的两组传感器：足端接触面（带 air-time）+ 全身接触（力阈值用）。

    **逐字段同构**（模式 `.*_SHANK` / `.*`、`fields=("force",)`、netforce、单槽）。
    """
    feet = ContactSensorCfg(
        name="foot_contact",
        primary=ContactMatch(mode="body", pattern=FOOT_PATTERN, entity="robot"),
        secondary=ContactMatch(mode="body", pattern="terrain"),
        fields=("force",),
        reduce="netforce",
        num_slots=1,
        track_air_time=True,
    )
    full = ContactSensorCfg(
        name="full_contact",
        primary=ContactMatch(mode="body", pattern=r".*", entity="robot"),
        secondary=ContactMatch(mode="body", pattern="terrain"),
        fields=("force",),
        reduce="netforce",
        num_slots=1,
    )
    return feet, full


def _restructure_observations(cfg: ManagerBasedRlEnvCfg, binding) -> None:
    """45 维 rl_sdk 布局（源配方：无 base_lin_vel / 无 height_scan；噪声只挂 actor）。"""
    groups = _joint_groups(binding)
    all_joint_cfg = SceneEntityCfg(
        "robot", joint_names=[n for role in binding.leg_pattern for n in groups[role]],
        preserve_order=True,
    )
    for group_name in ("actor", "critic"):
        noisy = group_name == "actor"
        cfg.observations[group_name].terms = {
            "base_ang_vel": ObservationTermCfg(
                func=envs_mdp.base_ang_vel,
                noise=Unoise(n_min=-0.2, n_max=0.2) if noisy else None,
            ),
            "projected_gravity": ObservationTermCfg(
                func=envs_mdp.projected_gravity,
                noise=Unoise(n_min=-0.05, n_max=0.05) if noisy else None,
            ),
            "command": ObservationTermCfg(
                func=envs_mdp.generated_commands, params={"command_name": "twist"}
            ),
            "joint_pos_rel": ObservationTermCfg(
                func=envs_mdp.joint_pos_rel,
                params={"asset_cfg": all_joint_cfg},
                noise=Unoise(n_min=-0.01, n_max=0.01) if noisy else None,
            ),
            "joint_vel_rel": ObservationTermCfg(
                func=envs_mdp.joint_vel_rel,
                params={"asset_cfg": all_joint_cfg},
                noise=Unoise(n_min=-1.5, n_max=1.5) if noisy else None,
            ),
            "actions": ObservationTermCfg(func=envs_mdp.last_action),
        }


def _lite3_recipe(
    cfg: ManagerBasedRlEnvCfg,
    binding,
    profile: VelocityProfile,
    *,
    terrain_profile: str,
    play: bool,
) -> None:
    """机型侧任务配方（源 `lite3_velocity.env_cfg` 的机型专属接线，逐项同构）。"""
    groups = _joint_groups(binding)
    all_joints = [n for role in binding.leg_pattern for n in groups[role]]
    all_joint_cfg = SceneEntityCfg("robot", joint_names=list(all_joints), preserve_order=True)
    hipx_cfg = SceneEntityCfg("robot", joint_names=list(groups["hipx"]), preserve_order=True)
    hipy_cfg = SceneEntityCfg("robot", joint_names=list(groups["hipy"]), preserve_order=True)
    knee_cfg = SceneEntityCfg("robot", joint_names=list(groups["knee"]), preserve_order=True)
    foot_cfg = SceneEntityCfg("robot", body_names=_foot_bodies(binding))
    # 奖励函式按名查接触传感器（ContactSensorRef：传感器名 + 取用的槽位）。
    feet_sensor = lite3_mdp.ContactSensorRef("foot_contact", (0, 1, 2, 3))
    non_foot_sensor = lite3_mdp.ContactSensorRef("full_contact", None)

    # 1) 传感器表：源配方两组（族级默认的足端几何传感器整表替换 —— 本机型的接触面
    #    是 shank body，不是足端几何）。
    foot_contact, full_contact = _contact_sensors(binding)
    kept = tuple(
        sensor
        for sensor in (cfg.scene.sensors or ())
        if sensor.name not in ("feet_ground_contact", "foot_contact", "full_contact")
    )
    cfg.scene.sensors = kept + (foot_contact, full_contact)

    # 2) 地形（源配方：random rough 0.4 + 两条斜坡各 0.3、楼梯/盒子关；flat 档的
    #    地形生成器已被族级 flat 收尾换成平面，不再触碰。play 档的课程开关由族级
    #    展厅收尾关掉，源配方也是"训才开课"——故 play 时不覆盖）。
    if terrain_profile == "rough":
        if cfg.scene.terrain is not None and cfg.scene.terrain.terrain_generator is not None:
            tg = cfg.scene.terrain.terrain_generator
            if not play:
                tg.curriculum = True
            tg.sub_terrains["random_rough"].proportion = 0.4
            tg.sub_terrains["random_rough"].noise_range = (0.01, 0.06)
            tg.sub_terrains["random_rough"].noise_step = 0.01
            if "hf_pyramid_slope" in tg.sub_terrains:
                tg.sub_terrains["hf_pyramid_slope"].proportion = 0.3
            if "hf_pyramid_slope_inv" in tg.sub_terrains:
                tg.sub_terrains["hf_pyramid_slope_inv"].proportion = 0.3
            for key in ("boxes", "pyramid_stairs", "pyramid_stairs_inv"):
                if key in tg.sub_terrains:
                    tg.sub_terrains[key].proportion = 0.0

    # 3) 命令档：±1.5 / ±0.8 / ±0.8 + 朝向指令、10 s 重采样（flat 的 play 命令范围由
    #    profile 的 play_flat_* 给训练档原值，见 profile 注释）。
    command = cfg.commands["twist"]
    assert isinstance(command, UniformVelocityCommandCfg)
    command.heading_command = True
    command.resampling_time_range = (10.0, 10.0)
    command.ranges.lin_vel_x = (-1.5, 1.5)
    command.ranges.lin_vel_y = (-0.8, 0.8)
    command.ranges.ang_vel_z = (-0.8, 0.8)
    command.ranges.heading = (-3.14, 3.14)

    # 4) 事件：源配方撤销 push / 外力 / 质心随机化（`base_com` 的 body 已由族级按根 body
    #    重指过，这里整项撤掉）。
    cfg.events.pop("push_robot", None)
    cfg.events.pop("randomize_apply_external_force_torque", None)
    cfg.events.pop("base_com", None)
    if "randomize_actuator_gains" in cfg.events:
        cfg.events["randomize_actuator_gains"].params["asset_cfg"].joint_names = list(all_joints)

    # 5) 观测布局（45 维 rl_sdk；源配方 actor/critic 同表、噪声只挂 actor）。
    _restructure_observations(cfg, binding)

    # 6) 奖励表：官方 24 项（源配方整表替换族级默认 —— 各项权重/参数逐字保留）。
    cfg.rewards = {
        # std 取上游 deep_rl 的 math.sqrt(0.5)（velocity_env_cfg.py:589-594）：此前写死的 0.425
        # 在任何上游里都找不到出处（核更锐、奖励衰减更快），2026-09-24 移植核对按上游订正。
        # **本档案已登记的仓库-上游差异：按现状保留，不随本轮改动**。
        "track_lin_vel_xy_exp": RewardTermCfg(
            func=velocity_mdp.track_linear_velocity, weight=4.0,
            params={"command_name": "twist", "std": math.sqrt(0.5)},
        ),
        "track_ang_vel_z_exp": RewardTermCfg(
            func=velocity_mdp.track_angular_velocity, weight=1.5,
            params={"command_name": "twist", "std": math.sqrt(0.5)},
        ),
        "feet_air_time_lin_xy": RewardTermCfg(
            func=lite3_mdp.feet_air_time_lin_xy_cmd,
            weight=5.0,
            params={"command_name": "twist", "threshold": 0.5, "sensor_cfg": feet_sensor},
        ),
        "feet_air_time_ang_z": RewardTermCfg(
            func=lite3_mdp.feet_air_time_ang_z_cmd_lite3,
            weight=5.0,
            params={"command_name": "twist", "threshold": 0.5, "sensor_cfg": feet_sensor},
        ),
        "feet_gait": RewardTermCfg(
            func=lite3_mdp.feet_gait,
            weight=0.5,
            params={
                "command_name": "twist",
                "std": 0.5,
                "max_err": 0.5,
                "velocity_threshold": 0.5,
                "command_threshold": 0.1,
                "sensor_cfg": feet_sensor,
                "synced_feet_pair_names": [
                    [f"{binding.leg_ids[0]}_{FOOT_BODY_TOKEN}", f"{binding.leg_ids[3]}_{FOOT_BODY_TOKEN}"],
                    [f"{binding.leg_ids[1]}_{FOOT_BODY_TOKEN}", f"{binding.leg_ids[2]}_{FOOT_BODY_TOKEN}"],
                ],
            },
        ),
        "phase_foot_trajectory_exp": RewardTermCfg(
            func=lite3_mdp.phase_foot_trajectory_exp,
            weight=2.0,
            params={
                "command_name": "twist",
                "asset_cfg": foot_cfg,
                "cycle_time": 0.425,
                "phase_offsets": (0.0, 1.0, 1.0, 0.0),
            },
        ),
        "feet_slide": RewardTermCfg(
            func=lite3_mdp.feet_slide, weight=-0.05, params={"sensor_cfg": feet_sensor, "asset_cfg": foot_cfg}
        ),
        "foot_impact_velocity": RewardTermCfg(
            func=lite3_mdp.foot_impact_velocity,
            weight=-2.0,
            params={"sensor_cfg": feet_sensor, "asset_cfg": foot_cfg},
        ),
        "stand_still": RewardTermCfg(
            func=lite3_mdp.stand_still_joint_deviation_l1,
            weight=-0.5,
            params={"command_name": "twist", "command_threshold": 0.1, "asset_cfg": all_joint_cfg},
        ),
        "feet_contact_without_cmd": RewardTermCfg(
            func=lite3_mdp.feet_contact_without_cmd,
            weight=0.1,
            params={"command_name": "twist", "sensor_cfg": feet_sensor},
        ),
        "contact_forces": RewardTermCfg(
            func=lite3_mdp.contact_forces, weight=-0.1, params={"sensor_cfg": feet_sensor, "threshold": 100.0}
        ),
        "lin_vel_z_l2": RewardTermCfg(func=lite3_mdp.lin_vel_z_l2, weight=-20.0),
        "ang_vel_xy_l2": RewardTermCfg(func=lite3_mdp.ang_vel_xy_l2, weight=-0.25),
        "flat_orientation_l2": RewardTermCfg(func=lite3_mdp.flat_orientation_l2, weight=-20.0),
        "base_height_l2": RewardTermCfg(
            func=lite3_mdp.base_height_l2, weight=-50.0, params={"target_height": 0.55}
        ),
        "undesired_contacts": RewardTermCfg(
            func=lite3_mdp.undesired_contacts,
            weight=-0.5,
            params={"sensor_cfg": non_foot_sensor, "threshold": 1.0},
        ),
        "joint_torques_l2": RewardTermCfg(
            func=envs_mdp.joint_torques_l2, weight=-2.5e-4, params={"asset_cfg": all_joint_cfg}
        ),
        "joint_acc_l2": RewardTermCfg(
            func=envs_mdp.joint_acc_l2, weight=-1e-8, params={"asset_cfg": all_joint_cfg}
        ),
        "joint_power": RewardTermCfg(
            func=lite3_mdp.joint_power, weight=-8e-4, params={"asset_cfg": all_joint_cfg}
        ),
        "joint_pos_limits": RewardTermCfg(
            func=envs_mdp.joint_pos_limits, weight=-5.0, params={"asset_cfg": all_joint_cfg}
        ),
        "joint_mirror": RewardTermCfg(
            func=lite3_mdp.joint_mirror,
            weight=-0.05,
            params={
                "asset_cfg": all_joint_cfg,
                # 对角对（源配方口径：FL↔HR / FR↔HL）；关节名拼法大小写敏感，取源词表。
                "mirror_joints": [
                    [f"{binding.leg_ids[0]}_{_FOOT_ROLE_ALTERNATION}.*",
                     f"{binding.leg_ids[3]}_{_FOOT_ROLE_ALTERNATION}.*"],
                    [f"{binding.leg_ids[1]}_{_FOOT_ROLE_ALTERNATION}.*",
                     f"{binding.leg_ids[2]}_{_FOOT_ROLE_ALTERNATION}.*"],
                ],
            },
        ),
        "hipx_joint_pos_penalty": RewardTermCfg(
            func=lite3_mdp.joint_pos_penalty,
            weight=-0.4,
            params={
                "command_name": "twist",
                "asset_cfg": hipx_cfg,
                "stand_still_scale": 5.0,
                "velocity_threshold": 0.5,
                "command_threshold": 0.1,
            },
        ),
        "hipy_joint_pos_penalty": RewardTermCfg(
            func=lite3_mdp.joint_pos_penalty,
            weight=0.0,
            params={
                "command_name": "twist",
                "asset_cfg": hipy_cfg,
                "stand_still_scale": 5.0,
                "velocity_threshold": 0.5,
                "command_threshold": 0.1,
            },
        ),
        "knee_joint_pos_penalty": RewardTermCfg(
            func=lite3_mdp.joint_pos_penalty,
            weight=-2.0,
            params={
                "command_name": "twist",
                "asset_cfg": knee_cfg,
                "stand_still_scale": 5.0,
                "velocity_threshold": 0.5,
                "command_threshold": 0.1,
            },
        ),
    }

    # 7) 终止：源配方不装非法接触终止；rough 档保留基座倾角终止（族级 rough 配方撤
    #    fell_over，故在此按源口径补回）；rough 的 play 档保留越界终止（族级 play
    #    收尾会撤它）。
    cfg.terminations.pop("illegal_contact", None)
    if terrain_profile == "rough":
        cfg.terminations["fell_over"] = TerminationTermCfg(
            func=envs_mdp.bad_orientation,
            params={"limit_angle": math.radians(profile.flat_tilt_limit_degrees)},
        )
    if play and terrain_profile == "rough":
        cfg.terminations["out_of_terrain_bounds"] = TerminationTermCfg(
            func=velocity_mdp.out_of_terrain_bounds, time_out=True
        )

    # 8) 课程：源配方撤 `command_vel`（族级默认保留它）。
    cfg.curriculum.pop("command_vel", None)


LITE3_VELOCITY = VelocityProfile(
    # 接触监看块自备（见模块 docstring）⇒ 族级四组传感器 / 三项惩罚 / 摩擦三轴 DR /
    # thigh 终止都不装配。
    contact_supervision=False,
    # 源配方不碰 MuJoCo 的 impratio / cone（族级 go2 配方才调）：保持引擎默认（实测
    # impratio 1.0 / cone pyramidal）。
    mujoco_solver_tuning=False,
    # 源装配骨架（`kit.new_velocity_env_cfg`）统一给 `sim.nconmax = None`（全身接触
    # 传感器需要余量）。
    contact_sensor_headroom=True,
    # flat 档：源配方**保留** terrain_scan 传感器，且 45 维 rl_sdk 观测本就没有
    # height_scan 项 ⇒ 两项都不撤（族级默认撤，故显式关掉）。
    flat_drop_terrain_scan=False,
    flat_drop_height_scan=False,
    # flat 档求解器内存上限 300（源配方；族级默认同值，显式化免得默认漂移）。
    flat_sim_njmax=300,
    # play：源配方不补 `randomize_terrain` 事件（族级默认补），展厅地形照换。
    play_drop_push=True,
    play_randomize_terrain=False,
    play_showroom_terrain=True,
    # play + flat 的命令范围 = 训练档原值（源配方在 play 档不改命令范围）。
    play_flat_lin_vel_x=(-1.5, 1.5),
    play_flat_ang_vel_z=(-0.8, 0.8),
    # 动作缩放不覆盖：契约逐角色值（0.125 / 0.25 / 0.25）就是源配方表（见模块 docstring）。
    # G1 对齐（2026-09-28，legged_gym 系结构；go2 同款实证 motion 0→0.459）：feet_air_time
    # 正激励（源配方 air_time 0.0 静音）、足端三罚归零（上游无此三项）、action_rate -0.01、
    # only_positive_rewards（负总奖励截 0）、stand_still 显式关（F1 实证短预算下惩罚主导）。
    air_time_weight=1.0,
    foot_clearance_weight=0.0,
    foot_swing_height_weight=0.0,
    foot_slip_weight=0.0,
    action_rate_weight=-0.01,
    only_positive_rewards=True,
    stand_still_weight=None,
    recipe=_lite3_recipe,
)
