"""WTW（Walk-These-Ways 周期步态先验）技能的族级环境/运行器工厂。

来源：`assets/robots/unitree_go2/training/source/local_tasks/robots/unitree/go2/tasks/
locomotion/wtw.py`（在 mjlab velocity 基座之上装配 WTW 任务）。除下列去机型化改动外
逐项同构：

* **足端几何**（`feet_ground_contact` 的 primary 模式）、**足端帧**（`foot_height_scan`）、
  **足端链接 body**（足端位置/速度奖励的 `asset_cfg`）、**根 body**（terrain_scan 帧、
  viewer）→ 绑定派生（`binding.foot_geoms` / `foot_scan_frames()` / `foot_link_bodies()` /
  `root_body`），不再写 `FR_foot_collision`、`FL` 站点、`<腿>_calf`、`base_link`；
* **非足端触地模式**（源 `^(?!.*_calf).*`）→ `binding.non_foot_body_pattern()`（族角色
  `knee` 的词干派生，四足族两者同字面量）；
* **动作装配**：`kits/joint_actions.build_joint_actions`（契约关节序 + 字面名 +
  `preserve_order`；缩放 = profile 的 `action_scale`，源配方为全关节 0.25 标量）；
* **腿数**：足端传感器槽位 / θ 与时钟宽度由 `binding.legs` 给出，不再写死 4；
* **状态初始化**：新增 startup 事件 `wtw_state_init`（`wtw_mdp.init_behavior_state`），
  把初值/采样区间/θ 池交给状态 —— 技能层零任务数值字面量（见 `wtw/mdp.py` 注释）；
* **任务数值**（相位与行为参数区间、奖励权重与核参数、命令重采样、sim 上限）→
  `WtwProfile`；
* **flat / play 收尾**：flat 档与源实现逐项同构（njmax / ccd / maxmatch + 平地形 +
  撤地形课程与越界终止；**保留** 基座 `nconmax` 与 `terrain_scan` 传感器）；play 档走
  族级 `apply_play_postlude`（源实现的四条：回合拉满 / 关噪声 / 清课程 / 5×5 展厅地形）。

留在本模块的是**族级机制**：传感器字段表（found+force / netforce / 单槽）、
`terrain_scan` 与 `foot_height_scan` 的重指口径、viewer 三元组、事件表结构。
"""

from __future__ import annotations

from typing import Literal

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs import mdp as envs_mdp
from mjlab.managers import (
    EventTermCfg,
    ObservationTermCfg,
    RewardTermCfg,
    SceneEntityCfg,
)
from mjlab.rl import RslRlOnPolicyRunnerCfg
from mjlab.sensor import ContactMatch, ContactSensorCfg, ObjRef
from mjlab.tasks.velocity import mdp as velocity_mdp
from mjlab.tasks.velocity.mdp import UniformVelocityCommandCfg
from mjlab.tasks.velocity.velocity_env_cfg import make_velocity_env_cfg

from ....joint_actions import build_joint_actions
from ... import apply_play_postlude, ppo_runner_cfg, set_viewer
from ..binding import QuadrupedSkillBinding
from . import mdp as wtw_mdp
from .profile import WtwProfile

TerrainProfile = Literal["rough", "flat"]

#: 传感器名（WTW 技能级常量；奖励/观测按名引用）。
TERRAIN_SCAN = "terrain_scan"
FOOT_HEIGHT_SCAN = "foot_height_scan"
FEET_SENSOR = "feet_ground_contact"
NONFOOT_SENSOR = "nonfoot_ground_touch"

#: 动作项名（族级统一；观测/奖励的关节序经 `mdp.contacts.joint_ids` 从它解析）。
ACTION_TERM = "joint_pos"


def _repoint_scan_frames(
    cfg: ManagerBasedRlEnvCfg, binding: QuadrupedSkillBinding
) -> None:
    """高度扫描重指：`terrain_scan` → 根 body；`foot_height_scan` → 足端帧。

    足端帧按能力派生（`binding.foot_scan_frames()`：优先足端 site，其次足端 body）。
    **一台足端帧都没有的机型**（足端就是小腿体、既无 site 也无足端 body）：撤掉该
    传感器与依赖它的 critic `foot_height` 观测项 —— 能力缺口不静默换口径。
    """
    frames = binding.foot_scan_frames()
    for sensor in cfg.scene.sensors or ():
        if sensor.name == TERRAIN_SCAN:
            sensor.frame.name = binding.root_body
        elif sensor.name == FOOT_HEIGHT_SCAN:
            if frames:
                sensor.frame = tuple(
                    ObjRef(type=kind, name=name, entity="robot") for kind, name in frames
                )
            else:
                cfg.scene.sensors = tuple(
                    item for item in (cfg.scene.sensors or ()) if item.name != FOOT_HEIGHT_SCAN
                )
                cfg.observations["critic"].terms.pop("foot_height", None)


def _contact_sensors(
    binding: QuadrupedSkillBinding, profile: WtwProfile
) -> tuple[ContactSensorCfg, ...]:
    """WTW 的两组接触传感器：足端（带 air-time）+ **非足端**全身 body。

    足端几何按契约腿序（`binding.foot_geoms`）；非足端模式排除膝角色 body
    （`binding.non_foot_body_pattern()`，源配方 `^(?!.*_calf).*`）。
    """
    terrain = ContactMatch(mode="body", pattern="terrain")
    return (
        ContactSensorCfg(
            name=FEET_SENSOR,
            primary=ContactMatch(mode="geom", pattern=binding.foot_geoms, entity="robot"),
            secondary=terrain,
            fields=("found", "force"),
            reduce="netforce",
            num_slots=1,
            track_air_time=True,
        ),
        ContactSensorCfg(
            name=NONFOOT_SENSOR,
            primary=ContactMatch(
                mode="body", pattern=binding.non_foot_body_pattern(), entity="robot"
            ),
            secondary=terrain,
            fields=("force",),
            reduce="netforce",
            num_slots=1,
        ),
    )


def _configure_observations(cfg: ManagerBasedRlEnvCfg, profile: WtwProfile) -> None:
    """actor / critic 各加三项 WTW 观测（源实现逐组同三步）。"""
    for group_name in ("actor", "critic"):
        terms = cfg.observations[group_name].terms
        terms["wtw_clock"] = ObservationTermCfg(
            func=wtw_mdp.clock_observation, params={"dt": profile.clock_dt}
        )
        terms["wtw_theta"] = ObservationTermCfg(func=wtw_mdp.theta_observation)
        terms["wtw_behavior"] = ObservationTermCfg(
            func=wtw_mdp.behavior_params_observation
        )


def _configure_events(
    cfg: ManagerBasedRlEnvCfg, binding: QuadrupedSkillBinding, profile: WtwProfile
) -> None:
    """状态建立（startup，携带 profile 数据）+ reset 重采样（源实现的同名事件）。"""
    cfg.events["wtw_state_init"] = EventTermCfg(
        func=wtw_mdp.init_behavior_state,
        mode="startup",
        params={
            "legs": binding.legs,
            "theta_pool": profile.theta_pool,
            "initial": profile.initial_behavior(),
            "ranges": {
                "gait_period": profile.gait_period_range,
                "foot_clearance": profile.foot_clearance_range,
                "base_height": profile.base_height_range,
                "pitch": profile.pitch_range,
            },
            "num_gaits": profile.num_gaits,
        },
    )
    cfg.events["wtw_behavior_resample"] = EventTermCfg(
        func=wtw_mdp.resample_behavior_params, mode="reset"
    )


def _configure_rewards(
    cfg: ManagerBasedRlEnvCfg,
    binding: QuadrupedSkillBinding,
    profile: WtwProfile,
    feet_sensor: wtw_mdp.ContactSensorRef,
    nonfoot_sensor: wtw_mdp.ContactSensorRef,
    foot_cfg: SceneEntityCfg,
) -> None:
    """官方 WTW 权重表（权重与核参数来自 profile）。"""
    weights = profile.reward_weights
    cfg.rewards = {
        "tracking_lin_vel": RewardTermCfg(
            func=velocity_mdp.track_linear_velocity,
            weight=weights["tracking_lin_vel"],
            params={"command_name": "twist", "std": profile.track_lin_vel_std},
        ),
        "tracking_ang_vel": RewardTermCfg(
            func=velocity_mdp.track_angular_velocity,
            weight=weights["tracking_ang_vel"],
            params={"command_name": "twist", "std": profile.track_ang_vel_std},
        ),
        "tracking_base_height": RewardTermCfg(
            func=wtw_mdp.tracking_base_height,
            weight=weights["tracking_base_height"],
            params={"asset_cfg": SceneEntityCfg("robot"), "sigma": profile.sigma_base_height},
        ),
        "tracking_orientation": RewardTermCfg(
            func=wtw_mdp.tracking_orientation,
            weight=weights["tracking_orientation"],
            params={"asset_cfg": SceneEntityCfg("robot"), "sigma": profile.sigma_orientation},
        ),
        "tracking_foot_clearance": RewardTermCfg(
            func=wtw_mdp.tracking_foot_clearance,
            weight=weights["tracking_foot_clearance"],
            params={
                "sensor_cfg": feet_sensor,
                "asset_cfg": foot_cfg,
                "sigma": profile.sigma_foot_clearance,
                "foot_height_offset": profile.foot_height_offset,
            },
        ),
        "quad_periodic_gait": RewardTermCfg(
            func=wtw_mdp.quad_periodic_gait,
            weight=weights["quad_periodic_gait"],
            params={
                "sensor_cfg": feet_sensor,
                "asset_cfg": foot_cfg,
                "a_swing": profile.a_swing,
                "b_swing": profile.b_swing,
            },
        ),
        "lin_vel_z": RewardTermCfg(func=wtw_mdp.lin_vel_z_l2, weight=weights["lin_vel_z"]),
        "ang_vel_xy": RewardTermCfg(func=wtw_mdp.ang_vel_xy_l2, weight=weights["ang_vel_xy"]),
        "dof_vel": RewardTermCfg(func=envs_mdp.joint_vel_l2, weight=weights["dof_vel"]),
        "dof_acc": RewardTermCfg(func=envs_mdp.joint_acc_l2, weight=weights["dof_acc"]),
        "action_rate": RewardTermCfg(
            func=envs_mdp.action_rate_l2, weight=weights["action_rate"]
        ),
        "action_smoothness": RewardTermCfg(
            func=wtw_mdp.action_smoothness, weight=weights["action_smoothness"]
        ),
        "torques": RewardTermCfg(func=envs_mdp.joint_torques_l2, weight=weights["torques"]),
        "foot_landing_vel": RewardTermCfg(
            func=wtw_mdp.foot_landing_vel,
            weight=weights["foot_landing_vel"],
            params={"sensor_cfg": feet_sensor, "asset_cfg": foot_cfg},
        ),
        "hip_pos": RewardTermCfg(func=wtw_mdp.hip_pos, weight=weights["hip_pos"]),
        "dof_pos_limits": RewardTermCfg(
            func=envs_mdp.joint_pos_limits,
            weight=weights["dof_pos_limits"],
            params={"asset_cfg": SceneEntityCfg("robot")},
        ),
        "collision": RewardTermCfg(
            func=wtw_mdp.undesired_contacts,
            weight=weights["collision"],
            params={
                "sensor_cfg": nonfoot_sensor,
                "threshold": profile.collision_force_threshold,
            },
        ),
    }


def _apply_flat_branch(cfg: ManagerBasedRlEnvCfg, profile: WtwProfile) -> None:
    """flat 档（源 `go2_wtw_flat_env_cfg`）：轻 sim 上限 + 平地形 + 撤地形课程/越界终止。

    **不**像族级 velocity 的 flat 收尾那样动 `nconmax`（源配方保留基座值），
    也**不**撤 `terrain_scan` 传感器与 `height_scan` 观测（源配方保留）。
    """
    cfg.sim.njmax = profile.flat_sim_njmax
    cfg.sim.mujoco.ccd_iterations = profile.flat_ccd_iterations
    cfg.sim.contact_sensor_maxmatch = profile.flat_contact_sensor_maxmatch
    assert cfg.scene.terrain is not None
    cfg.scene.terrain.terrain_type = "plane"
    cfg.scene.terrain.terrain_generator = None
    cfg.terminations.pop("out_of_terrain_bounds", None)
    cfg.curriculum.pop("terrain_levels", None)


def make_env_cfg(
    binding: QuadrupedSkillBinding,
    profile: WtwProfile,
    *,
    terrain_profile: TerrainProfile = "rough",
    play: bool = False,
) -> ManagerBasedRlEnvCfg:
    """Build the family WTW task from its source implementation."""
    if terrain_profile not in ("rough", "flat"):
        raise ValueError(f"未知地形档 {terrain_profile!r}（族级 WTW 只装配 rough / flat）")

    cfg = make_velocity_env_cfg()
    cfg.sim.mujoco.ccd_iterations = profile.rough_ccd_iterations
    cfg.sim.contact_sensor_maxmatch = profile.rough_contact_sensor_maxmatch
    # 实体整份沿用机型自己的基座配置（源的 WTW 实体就是该机型的训练实体，不覆盖）。
    cfg.scene.entities = {"robot": binding.base_entity_cfg()}

    _repoint_scan_frames(cfg, binding)
    cfg.scene.sensors = tuple(cfg.scene.sensors or ()) + _contact_sensors(binding, profile)

    feet_sensor = wtw_mdp.ContactSensorRef(FEET_SENSOR, tuple(range(binding.legs)))
    nonfoot_sensor = wtw_mdp.ContactSensorRef(NONFOOT_SENSOR, None)
    # 足端位置/速度的帧：足端几何的父 body（源配方写 `<腿>_calf`）。
    foot_cfg = SceneEntityCfg("robot", body_names=binding.foot_link_bodies())

    ##
    # Actions：契约关节序的位置控制（缩放由 profile 携带，源配方 = 全关节 0.25）
    ##
    cfg.actions = build_joint_actions(
        joint_order=binding.joint_order,
        control_modes=binding.control_modes(),
        scale=profile.action_scale,
        term_names=(ACTION_TERM,),
    )

    ##
    # Events：状态建立（startup）+ 行为重采样（reset）
    ##
    _configure_events(cfg, binding, profile)

    ##
    # Terrain curriculum（WTW 依赖地形档位；源实现显式打开）
    ##
    if cfg.scene.terrain is not None and cfg.scene.terrain.terrain_generator is not None:
        cfg.scene.terrain.terrain_generator.curriculum = True

    ##
    # Commands：WTW 在 reset 时重采样相位/θ，命令重采样周期由 profile 携带
    ##
    twist_cmd = cfg.commands["twist"]
    assert isinstance(twist_cmd, UniformVelocityCommandCfg)
    twist_cmd.resampling_time_range = profile.command_resampling_time_range

    ##
    # Observations / Rewards
    ##
    cfg.episode_length_s = profile.episode_length_s
    _configure_observations(cfg, profile)
    _configure_rewards(cfg, binding, profile, feet_sensor, nonfoot_sensor, foot_cfg)

    set_viewer(cfg, body_name=binding.root_body, distance=1.5, elevation=-10.0)

    if terrain_profile == "flat":
        _apply_flat_branch(cfg, profile)

    if play:
        apply_play_postlude(cfg)
    return cfg


def make_runner_cfg(profile: WtwProfile) -> RslRlOnPolicyRunnerCfg:
    """官方 WTW PPO 运行器配置 —— 与族级 PPO 默认值逐字段相同（机型身份除外）。"""
    return ppo_runner_cfg(profile.experiment_name)
