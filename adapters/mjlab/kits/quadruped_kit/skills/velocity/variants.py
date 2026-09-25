"""速度跟踪的**算法变体**档（CTS / AMP-CTS / TS / AMP-TS / TS-学生 / HIM / DreamWaQ /
AMP-DreamWaQ）—— 同一技能的配方分支。

来源：`assets/robots/unitree_go2/training/source/local_tasks/robots/unitree/go2/tasks/
locomotion/variants.py`（697 行）里的 `_go2_custom_algorithm_env_cfg`。结构逐项同构：
在 rough velocity cfg 之上按 kind 覆盖出九种变体（观测组、动作项换成带延时的实现、
地形生成器换源配方五类、DR 事件、奖励表换源 LeggedRobot 核、单轴命令类等）。

与轮足族 `skills/velocity/{official,competition}.py` 同一设计：**同一技能的配方分支**。
配方分支之间共用族级底座（`config.make_env_cfg` 的装配骨架 + 绑定派生的关节序/几何），
所以"换机型"只换绑定 + `VariantSpec` 数据。

## 去机型化改动（逐条对照源实现）

* 腿名正则 `(?:FL|FR|RL|RR)_(?:hip|thigh|calf)` → `binding.leg_link_body_pattern()`
  （契约腿序 × 角色词干；同族同构机型得到同一串）；
* `base_link` → `binding.root_body`；`SceneEntityCfg("robot", actuator_names=".*")`
  → 契约关节序（`binding.joint_order`，解析集合相同、解析序同模型序）；
* `site_names=("FR","FL","RR","RL")` → `binding.foot_sites()`（契约腿序；足端高度项是
  **逐足求和**，与足序无关，解析集合相同）；
* 足端接触位里写死的重排 `(1, 0, 3, 2)` → `spec.contact_order`（观测契约声明的足序，
  数据）；腿杆/躯干触地传感器 → 绑定的角色词干（`geom` 或 `body` 两种命名口径）；
* 传感器名 → `skills/mdp/sensors.py` 的族级常量（`TERRAIN_SCAN` / `FEET_SENSOR` / …）；
* 关节/腿选择 → `binding.role_joint_pattern()` / `binding.joint_names()` /
  `binding.leg_link_body_pattern()` / `binding.rear_legs`；
* 全部源配方数值（摩擦/push/PD/力矩倍率/奖励权重表/地形边界/`target_height`/命令区间/
  噪声/历史帧数/学生 rollout 帧数/sim 档）→ `VariantSpec`（机型侧 profile 模块的数据）。

## 九种变体与观测族

| 观测族 | 变体 | actor | 额外组 |
|---|---|---|---|
| `cts` | cts / amp_cts | 45-D 盲帧 + history | terrain / teacher_mask / privileged / critic [+amp] |
| `dreamwaq` | dreamwaq / amp_dreamwaq | 45-D 盲帧 + history | terrain / explicit / critic / privileged [+amp] |
| `him` | him | 堆叠历史（actor 即历史） | terrain / critic |
| `ts` | ts / amp_ts / ts_student / amp_ts_student | 45-D 盲帧 + history | terrain / privileged / critic [+amp] |

`amp_*` 变体多一个判别器状态组。`*_student` 变体撤命令课程、抬高观测噪声、
按更长的 rollout 训练（数值在 spec / runner profile 里）。
"""

from __future__ import annotations

import math

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs import mdp as envs_mdp
from mjlab.envs.mdp.actions import JointPositionActionCfg
from mjlab.managers import (
    EventTermCfg,
    ObservationGroupCfg,
    ObservationTermCfg,
    RewardTermCfg,
    SceneEntityCfg,
    TerminationTermCfg,
)
from mjlab.tasks.velocity.mdp import UniformVelocityCommandCfg
from mjlab.tasks.velocity.mdp.terminations import illegal_contact as _illegal_contact
from mjlab.terrains.config import (
    discrete_obstacles,
    hf_pyramid_slope,
    pyramid_stairs,
    pyramid_stairs_inv,
    random_rough,
)
from mjlab.terrains.terrain_generator import TerrainGeneratorCfg
from mjlab.utils.noise.noise_cfg import UniformNoiseCfg

from ..binding import QuadrupedSkillBinding
from ..mdp import observations as source_obs
from ..mdp import rewards as source_rewards
from ..mdp.actions import DelayedJointPositionActionCfg
from ..mdp.events import reset_joints_by_scale_with_velocity, torque_multiplier
from ..mdp.sensors import FEET_SENSOR, SHANK_SENSOR, TERRAIN_SCAN, THIGH_SENSOR, TRUNK_SENSOR
from . import config as velocity_config
from .config import (
    apply_source_geom_friction,
    apply_source_observation_clipping,
    ensure_contact_supervision,
    ensure_supervision_bodies,
    source_frame_noise,
)
from .profile import VariantSpec, VariantTerrain, VelocityProfile

#: 观测族名（`VariantSpec.family` 的取值）。
FAMILIES = ("cts", "dreamwaq", "him", "ts")

#: 碰撞监看组名 → 族级传感器名（族级常量，四足族各机型同值）。
_SUPERVISION_SENSORS = {
    "thigh": THIGH_SENSOR,
    "shank": SHANK_SENSOR,
    "trunk": TRUNK_SENSOR,
}


def _supervision_sensor_name(group: str) -> str:
    try:
        return _SUPERVISION_SENSORS[group]
    except KeyError as exc:
        raise ValueError(
            f"未知的碰撞监看组 {group!r}（可用：{sorted(_SUPERVISION_SENSORS)}）"
        ) from exc


def _contract_joint_patterns(binding: QuadrupedSkillBinding) -> tuple[str, ...]:
    """本机型**契约全部关节**的紧凑模式（= 绑定执行器组的角色模式并集）。

    "全关节/全执行器"这类项（PD 增益、力矩倍率、力矩平方、关节加速度）走这里：
    源配方写的是 `.*`，族级换成契约派生的角色模式并集 —— 解析集合相同
    （`SceneEntityCfg` 默认按实体序解析、全选中时优化成 `slice(None)`），
    但对"只装部分执行器"的机型不会误伤。
    """
    patterns: list[str] = []
    for group in binding.actuator_groups:
        for expression in group.target_names_expr:
            if expression not in patterns:
                patterns.append(str(expression))
    if not patterns:
        raise ValueError(f"{binding.robot_id}: 绑定没有执行器谱，无法派生关节模式")
    return tuple(patterns)


def _reward_joint_pattern(binding: QuadrupedSkillBinding, family_role: str) -> tuple[str, ...]:
    return binding.role_joint_pattern(family_role)


def _preload_hips(
    cfg: ManagerBasedRlEnvCfg,
    binding: QuadrupedSkillBinding,
    preload: dict[str, float],
) -> None:
    """AMP-CTS 的镜像外展预载（腿标记 → 角度）—— 覆盖初始姿里的髋关节项。"""
    joint_pos = cfg.scene.entities["robot"].init_state.joint_pos
    assert joint_pos is not None
    for leg, value in preload.items():
        names = binding.joint_names("hip_abduction", legs=(leg,))
        if not names:
            raise ValueError(
                f"{binding.robot_id}: 预载表里的腿标记 {leg!r} 在契约腿序 {binding.leg_ids} 里没有髋关节"
            )
        for name in names:
            joint_pos[name] = float(value)


def _apply_terrain(
    cfg: ManagerBasedRlEnvCfg, spec: VariantSpec, terrain: VariantTerrain
) -> None:
    """地形生成器：源配方的地块配方 + 逐变体的边界宽度（spec 覆盖）。"""
    assert cfg.scene.terrain is not None
    cfg.scene.terrain.terrain_generator = TerrainGeneratorCfg(
        size=tuple(terrain.size),
        border_width=float(spec.terrain_border_width),
        num_rows=int(terrain.num_rows),
        num_cols=int(terrain.num_cols),
        curriculum=bool(terrain.curriculum),
        sub_terrains=dict(terrain.sub_terrains),
        add_lights=bool(terrain.add_lights),
    )


def _apply_action_term(
    cfg: ManagerBasedRlEnvCfg, binding: QuadrupedSkillBinding
) -> None:
    """把动作项换成带延时的实现（源：四个物理子步里随机切换新旧目标）。

    动作维与缩放**逐项沿用**族级 `build_joint_actions` 的产物（动作接口序仍 = 契约
    `action.joint_order`，见 `mdp/actions.DelayedJointPositionAction`）。
    """
    joint_pos_action = cfg.actions["joint_pos"]
    assert isinstance(joint_pos_action, JointPositionActionCfg)
    cfg.actions["joint_pos"] = DelayedJointPositionActionCfg(
        entity_name=joint_pos_action.entity_name,
        actuator_names=joint_pos_action.actuator_names,
        scale=joint_pos_action.scale,
        offset=joint_pos_action.offset,
        clip=joint_pos_action.clip,
        preserve_order=joint_pos_action.preserve_order,
        use_default_offset=joint_pos_action.use_default_offset,
        delay=True,
    )


def _apply_events(
    cfg: ManagerBasedRlEnvCfg,
    binding: QuadrupedSkillBinding,
    spec: VariantSpec,
) -> None:
    """复位 / 启动期 DR / 区间扰动（逐项对齐源配方，数值来自 spec）。"""
    # 复位：源变体用**乘性**关节初值（CTS 更窄），而不是公共基座的加性偏移。
    cfg.events["reset_robot_joints"].func = reset_joints_by_scale_with_velocity
    cfg.events["reset_robot_joints"].params.pop("position_range", None)
    cfg.events["reset_robot_joints"].params["scale_range"] = tuple(spec.reset_scale_range)
    cfg.events["reset_base"].params["pose_range"].update(dict(spec.reset_pose_range))
    cfg.events["reset_base"].params["velocity_range"] = dict(spec.reset_velocity_range)

    # 启动期采样（源：每个仿真环境创建时采一次标定/模型字段；逐回合只复位状态与命令）。
    cfg.events["encoder_bias"].mode = "startup"
    cfg.events["encoder_bias"].params["bias_range"] = tuple(spec.encoder_bias_range)
    apply_source_geom_friction(cfg, tuple(spec.geom_friction_range))

    cfg.events["base_com"].mode = "startup"
    cfg.events["base_com"].params["ranges"] = {
        0: (-spec.com_extent, spec.com_extent),
        1: (-spec.com_extent, spec.com_extent),
        2: (-spec.com_extent, spec.com_extent),
    }
    cfg.events["base_mass"] = EventTermCfg(
        func=envs_mdp.dr.body_mass,
        mode="startup",
        params={
            "ranges": tuple(spec.base_mass_range),
            "asset_cfg": SceneEntityCfg("robot", body_names=(binding.root_body,)),
            "operation": "add",
        },
    )
    cfg.events["link_mass"] = EventTermCfg(
        func=envs_mdp.dr.body_mass,
        mode="startup",
        params={
            "ranges": tuple(spec.link_mass_range),
            "asset_cfg": SceneEntityCfg("robot", body_names=(binding.leg_bodies_pattern(),)),
            "operation": "scale",
        },
    )
    if "push_robot" in cfg.events:
        cfg.events["push_robot"].interval_range_s = (
            spec.push_interval_s,
            spec.push_interval_s,
        )
        cfg.events["push_robot"].params["velocity_range"] = {
            "x": (-spec.push_linear, spec.push_linear),
            "y": (-spec.push_linear, spec.push_linear),
            "z": (0.0, 0.0),
            "roll": (-spec.push_angular, spec.push_angular),
            "pitch": (-spec.push_angular, spec.push_angular),
            "yaw": (-spec.push_angular, spec.push_angular),
        }
    joint_patterns = _contract_joint_patterns(binding)
    all_actuators = SceneEntityCfg("robot", actuator_names=joint_patterns)
    cfg.events["pd_gains"] = EventTermCfg(
        func=envs_mdp.dr.pd_gains,
        mode="startup",
        params={
            "kp_range": tuple(spec.pd_gain_range),
            "kd_range": tuple(spec.pd_gain_range),
            "asset_cfg": all_actuators,
            "operation": "scale",
        },
    )
    cfg.events["torque_multiplier"] = EventTermCfg(
        func=torque_multiplier,
        mode="startup",
        params={
            "torque_multiplier_range": tuple(spec.torque_multiplier_range),
            "asset_cfg": all_actuators,
        },
    )


def _apply_rewards(
    cfg: ManagerBasedRlEnvCfg,
    binding: QuadrupedSkillBinding,
    spec: VariantSpec,
) -> None:
    """奖励表换成源 LeggedRobot 核（项名保持不变以稳住日志/清单）。"""
    joint_patterns = _contract_joint_patterns(binding)
    actuator_cfg = SceneEntityCfg("robot", actuator_names=joint_patterns)
    cfg.rewards["track_linear_velocity"] = RewardTermCfg(
        func=source_rewards.source_tracking_linear_velocity,
        weight=spec.tracking_linear_weight,
        params={"command_name": "twist", "sigma": spec.track_sigma},
    )
    cfg.rewards["track_angular_velocity"] = RewardTermCfg(
        func=source_rewards.source_tracking_angular_velocity,
        weight=spec.tracking_angular_weight,
        params={"command_name": "twist", "sigma": spec.track_sigma},
    )
    cfg.rewards["upright"] = RewardTermCfg(
        func=source_rewards.orientation_penalty,
        weight=spec.orientation_weight,
        params={},
    )
    cfg.rewards["body_ang_vel"] = RewardTermCfg(
        func=source_rewards.angular_velocity_xy_penalty,
        weight=spec.angular_velocity_xy_weight,
        params={},
    )
    cfg.rewards["lin_vel_z"] = RewardTermCfg(
        func=source_rewards.linear_velocity_z_penalty,
        weight=spec.linear_velocity_z_weight,
        params={},
    )
    cfg.rewards["base_height"] = RewardTermCfg(
        func=source_rewards.base_height_penalty,
        weight=spec.base_height_weight,
        params={
            "target_height": spec.base_height_target,
            "sensor_name": TERRAIN_SCAN,
        },
    )
    cfg.rewards["torques"] = RewardTermCfg(
        func=envs_mdp.joint_torques_l2,
        weight=spec.torque_weight,
        params={"asset_cfg": actuator_cfg},
    )
    cfg.rewards["dof_acc"] = RewardTermCfg(
        func=source_rewards.joint_acceleration_penalty,
        weight=spec.joint_acceleration_weight,
        params={"asset_cfg": SceneEntityCfg("robot", joint_names=joint_patterns)},
    )
    cfg.rewards["action_smoothness"] = RewardTermCfg(
        func=source_rewards.action_smoothness_penalty,
        weight=spec.action_smoothness_weight,
        params={},
    )
    cfg.rewards["dof_pos_limits"].weight = spec.dof_pos_limits_weight
    cfg.rewards["action_rate_l2"].weight = spec.action_rate_weight
    # 源变体用一个聚合碰撞项；先撤掉公共基座的三项按传感器惩罚，避免罚两次。
    for name in ("self_collisions", "shank_collision", "trunk_head_collision"):
        cfg.rewards.pop(name, None)
    cfg.rewards["collision"] = RewardTermCfg(
        func=source_rewards.collision_penalty,
        weight=spec.collision_weight,
        params={
            "sensor_names": tuple(
                _supervision_sensor_name(group) for group in spec.collision_groups
            )
        },
    )
    cfg.rewards["foot_clearance"] = RewardTermCfg(
        func=source_rewards.source_foot_clearance_penalty,
        weight=spec.foot_clearance_weight,
        params={
            "target_height": spec.foot_clearance_target,
            "asset_cfg": SceneEntityCfg(
                "robot", site_names=binding.foot_sites(), preserve_order=True
            ),
        },
    )
    cfg.rewards["foot_swing_height"].weight = 0.0
    cfg.rewards["foot_slip"].weight = 0.0
    cfg.rewards["soft_landing"].weight = 0.0
    cfg.rewards["pose"].weight = 0.0
    cfg.rewards["angular_momentum"].weight = 0.0
    cfg.rewards["stumble"] = RewardTermCfg(
        func=source_rewards.stumble_penalty,
        weight=spec.stumble_weight,
        params={"sensor_name": FEET_SENSOR},
    )
    if spec.hip_position_weight is not None:
        cfg.rewards["hip_pos"] = RewardTermCfg(
            func=source_rewards.hip_position_squared_penalty,
            weight=spec.hip_position_weight,
            params={
                "asset_cfg": SceneEntityCfg(
                    "robot", joint_names=_reward_joint_pattern(binding, "hip_abduction")
                )
            },
        )
    if spec.rear_hip_limit_weight is not None:
        cfg.rewards["rear_hip_limit"] = RewardTermCfg(
            func=source_rewards.rear_hip_limit_penalty,
            weight=spec.rear_hip_limit_weight,
            params={
                "limit": spec.rear_hip_limit_bound,
                "asset_cfg": SceneEntityCfg(
                    "robot",
                    joint_names=binding.joint_names(
                        "hip_abduction", legs=binding.rear_legs
                    ),
                    preserve_order=True,
                ),
            },
        )
    if spec.air_time_weight:
        cfg.rewards["air_time"] = RewardTermCfg(
            func=source_rewards.source_feet_air_time_reward,
            weight=spec.air_time_weight,
            params={
                "sensor_name": FEET_SENSOR,
                "offset": spec.air_time_offset,
                "command_name": "twist",
                "command_dimensions": 3,
            },
        )
    else:
        # 源变体里没这一项：静音（不是删除 —— 日志/清单仍可见）。
        cfg.rewards["air_time"].weight = 0.0


def _supervision_sensor_name(group: str) -> str:
    """碰撞监看组名 → 族级传感器名。"""
    names = {
        "thigh": "thigh_ground_touch",
        "shank": "shank_ground_touch",
        "trunk": "trunk_ground_touch",
    }
    try:
        return names[group]
    except KeyError as exc:
        raise ValueError(f"未知的碰撞监看组 {group!r}（可用：{sorted(names)}）") from exc


def _apply_command(cfg: ManagerBasedRlEnvCfg, spec: VariantSpec) -> None:
    """单轴/区间命令（源变体全部用 heading_command 口径，不用混合环境比例）。"""
    command = cfg.commands["twist"]
    assert isinstance(command, UniformVelocityCommandCfg)
    command.ranges.lin_vel_x = (-1.0, 1.0)
    command.heading_command = True
    command.ranges.heading = (-math.pi, math.pi)
    command.rel_heading_envs = 1.0
    command.rel_standing_envs = 0.0
    command.rel_forward_envs = 0.0
    command.source_min_lin_norm = spec.command_min_lin_norm
    command.source_zero_command_prob = spec.zero_command_prob
    command.source_zero_xy_prob = spec.zero_xy_prob
    command.ranges.lin_vel_y = tuple(spec.lin_vel_y_range)
    command.ranges.ang_vel_z = tuple(spec.yaw_range)
    command.resampling_time_range = (spec.command_resample_s, spec.command_resample_s)


def _source_noise(
    binding: QuadrupedSkillBinding, spec: VariantSpec
) -> UniformNoiseCfg:
    return source_frame_noise(
        joint_count=len(binding.joint_order),
        command_first=True,
        dof_pos_noise=spec.dof_pos_noise,
        ang_vel_noise=spec.ang_vel_noise,
    )


def _apply_observations(
    cfg: ManagerBasedRlEnvCfg,
    binding: QuadrupedSkillBinding,
    spec: VariantSpec,
    *,
    play: bool,
    noise: UniformNoiseCfg,
) -> None:
    """按观测族装配 actor / history / terrain / 家族专属组（[+amp]）。"""
    cfg.observations["actor"] = ObservationGroupCfg(
        terms={
            "source_stand": ObservationTermCfg(
                func=source_obs.SourceActorFrame,
                params={
                    "command_name": "twist",
                    "command_first": True,
                    "noise": noise,
                    "add_noise": not play,
                },
                history_length=1,
                flatten_history_dim=True,
            )
        },
        concatenate_terms=True,
        enable_corruption=not play,
    )
    contact_order = tuple(spec.contact_order) or None
    if spec.family != "him" and spec.history_frame_count is not None:
        # HIM 直接用堆叠历史当 actor 观测（见下面的 him 分支），不需要单独的前序帧组。
        cfg.observations["history"] = ObservationGroupCfg(
            terms={
                "source_history": ObservationTermCfg(
                    func=source_obs.SourceActorHistory,
                    params={"length": int(spec.history_frame_count)},
                    history_length=1,
                    flatten_history_dim=True,
                )
            },
            concatenate_terms=True,
            enable_corruption=not play,
        )
    if spec.family == "him":
        # HIM actor 观测 = HIMLoco obs_hist_buf：45-D 源帧 × N，最新在前。
        cfg.observations["actor"] = ObservationGroupCfg(
            terms={
                "him_history": ObservationTermCfg(
                    func=source_obs.HimHistory,
                    params={
                        "command_name": "twist",
                        "command_first": True,
                        "noise": noise,
                        "add_noise": not play,
                        "length": 6,
                    },
                    history_length=1,
                    flatten_history_dim=True,
                )
            },
            concatenate_terms=True,
            enable_corruption=not play,
        )
    cfg.observations["terrain"] = ObservationGroupCfg(
        terms={
            "terrain_scan": ObservationTermCfg(
                func=source_obs.source_terrain_heights,
                params={"sensor_name": TERRAIN_SCAN},
            )
        },
        concatenate_terms=True,
        enable_corruption=False,
    )
    if spec.amp:
        cfg.observations["amp"] = ObservationGroupCfg(
            terms={
                "amp_state": ObservationTermCfg(
                    func=source_obs.amp_state_frame,
                    params={"sensor_name": TERRAIN_SCAN},
                    history_length=1,
                    flatten_history_dim=True,
                )
            },
            concatenate_terms=True,
            enable_corruption=False,
        )

    if spec.family == "dreamwaq":
        cfg.observations["explicit"] = ObservationGroupCfg(
            terms={
                "dreamwaq_velocity": ObservationTermCfg(
                    func=source_obs.dreamwaq_velocity_target,
                    params={},
                    history_length=1,
                    flatten_history_dim=True,
                )
            },
            concatenate_terms=True,
            enable_corruption=False,
        )
        cfg.observations["critic"] = ObservationGroupCfg(
            terms={
                "dreamwaq_privileged": ObservationTermCfg(
                    func=source_obs.dreamwaq_privileged_frame,
                    params={"command_name": "twist", "sensor_name": TERRAIN_SCAN},
                    history_length=3,
                    flatten_history_dim=True,
                )
            },
            concatenate_terms=True,
            enable_corruption=False,
        )
        cfg.observations["privileged"] = ObservationGroupCfg(
            terms={
                "dreamwaq_privileged_frame": ObservationTermCfg(
                    func=source_obs.dreamwaq_privileged_frame,
                    params={"command_name": "twist", "sensor_name": TERRAIN_SCAN},
                    history_length=1,
                    flatten_history_dim=True,
                )
            },
            concatenate_terms=True,
            enable_corruption=False,
        )
    elif spec.family == "cts":
        # 源 CTS 用固定的 3:1 教师/学生环境划分。掩码放独立观测组，
        # 不改变 checkpoint 与部署包装消费的 actor 契约宽度。
        cfg.observations["teacher_mask"] = ObservationGroupCfg(
            terms={"cts_teacher_mask": ObservationTermCfg(func=source_obs.cts_teacher_mask)},
            concatenate_terms=True,
            enable_corruption=False,
        )
        cfg.observations["privileged"] = ObservationGroupCfg(
            terms={
                "cts_privileged": ObservationTermCfg(
                    func=source_obs.cts_privileged_frame,
                    params={
                        "sensor_name": TERRAIN_SCAN,
                        "contact_sensor_name": FEET_SENSOR,
                        "contact_order": contact_order,
                    },
                    history_length=1,
                    flatten_history_dim=True,
                )
            },
            concatenate_terms=True,
            enable_corruption=False,
        )
        cfg.observations["critic"] = ObservationGroupCfg(
            terms={
                "cts_critic": ObservationTermCfg(
                    func=source_obs.cts_critic_frame,
                    params={
                        "sensor_name": TERRAIN_SCAN,
                        "contact_sensor_name": FEET_SENSOR,
                        "include_lin_vel": spec.amp,
                        "contact_order": contact_order,
                    },
                    history_length=1,
                    flatten_history_dim=True,
                )
            },
            concatenate_terms=True,
            enable_corruption=False,
        )
    elif spec.family == "him":
        # HIM value 输入：单帧特权块（带噪 45-D 帧 || base_lin_vel * 2）。
        cfg.observations["critic"] = ObservationGroupCfg(
            terms={
                "him_privileged": ObservationTermCfg(
                    func=source_obs.him_privileged_frame,
                    params={"command_name": "twist"},
                    history_length=1,
                    flatten_history_dim=True,
                )
            },
            concatenate_terms=True,
            enable_corruption=False,
        )
    else:
        cfg.observations["privileged"] = ObservationGroupCfg(
            terms={
                # TS 教师编码器吃源口径的域随机化/接触块；完整的价值观测在 critic 组。
                "ts_teacher_privileged": ObservationTermCfg(
                    func=source_obs.ts_privileged_frame,
                    params={
                        "contact_sensor_name": FEET_SENSOR,
                        "contact_order": contact_order,
                    },
                    history_length=1,
                    flatten_history_dim=True,
                )
            },
            concatenate_terms=True,
            enable_corruption=False,
        )
        cfg.observations["critic"] = ObservationGroupCfg(
            terms={
                "ts_critic": ObservationTermCfg(
                    func=source_obs.ts_critic_frame,
                    params={
                        "sensor_name": TERRAIN_SCAN,
                        "contact_sensor_name": FEET_SENSOR,
                        "contact_order": contact_order,
                    },
                    history_length=1,
                    flatten_history_dim=True,
                )
            },
            concatenate_terms=True,
            enable_corruption=False,
        )
    apply_source_observation_clipping(cfg)


def make_variant_env_cfg(
    binding: QuadrupedSkillBinding,
    profile: VelocityProfile,
    spec: VariantSpec,
    *,
    terrain: VariantTerrain,
    play: bool = False,
) -> ManagerBasedRlEnvCfg:
    """在 rough velocity cfg 之上装配一个算法变体（源 `_go2_custom_algorithm_env_cfg` 同序）。"""
    if spec.family not in FAMILIES:
        raise ValueError(f"未知观测族 {spec.family!r}（可用：{FAMILIES}）")
    cfg = velocity_config.make_env_cfg(binding, profile, terrain_profile="rough", play=play)

    # 接触监看：变体的碰撞奖励/终止按名引用这三条腿杆/躯干传感器。基座 profile 关掉
    # 族级接触监看的机型（自备另一套判据）在这里按变体的需要补齐 —— 匹配口径由
    # spec 声明（`geom` = 几何名派生 / `body` = body 名派生，后者服务碰撞几何未命名的资产）。
    if spec.collision_groups or cfg.terminations.get("illegal_contact") is not None:
        if spec.contact_match == "body":
            ensure_supervision_bodies(cfg, binding)
        else:
            ensure_contact_supervision(cfg, binding)

    # 源变体一律用 `terminate_after_contacts_on=['base']` 口径（躯干触地终止），
    # 而不是公共 rough 配方的大腿触地终止。
    cfg.terminations["illegal_contact"] = TerminationTermCfg(
        func=_illegal_contact,
        params={"sensor_name": _supervision_sensor_name("trunk")},
    )

    _apply_terrain(cfg, spec, terrain)
    cfg.clip_rewards_to_positive = bool(spec.clip_rewards_to_positive)
    if spec.hip_preload_by_leg:
        _preload_hips(cfg, binding, dict(spec.hip_preload_by_leg))
    _apply_action_term(cfg, binding)
    _apply_events(cfg, binding, spec)
    _apply_rewards(cfg, binding, spec)
    noise = _source_noise(binding, spec)
    _apply_command(cfg, spec)

    # play 档已经由基座收尾处理（无限长回合/关噪声/撤扰动）；命令与观测组在它之后
    # 装配，故"关噪声"由各观测项的 `add_noise=not play` 表达。
    cfg.sim.broadphase = spec.broadphase
    cfg.sim.nconmax = int(spec.nconmax)

    _apply_observations(cfg, binding, spec, play=play, noise=noise)

    if spec.drop_command_curriculum:
        # 源学生档设 commands.curriculum=False。
        cfg.curriculum.pop("command_vel", None)
    return cfg


#: 变体档的**族级默认地形配方** —— 源 CTS/TS 上游的五类地块（比例/坡度/噪声/台阶尺寸
#: 全是算法配方的常量）。逐档真正不同的只有 `spec.terrain_border_width`（生成器边界），
#: 故这里是默认、由 spec 覆盖；机型侧要用别的配方（例如另一份上游）可自行传 `terrain=`。
SOURCE_VARIANT_TERRAIN = VariantTerrain(
    size=(8.0, 8.0),
    num_rows=10,
    num_cols=20,
    curriculum=True,
    add_lights=True,
    border_width=25.0,
    sub_terrains={
        "smooth_slope": hf_pyramid_slope(
            proportion=0.15, slope_range=(0.0, 0.4), platform_width=3.0, border_width=1.0
        ),
        "rough_slope": random_rough(
            proportion=0.15, noise_range=(0.02, 0.10), noise_step=0.02, border_width=1.0
        ),
        "stairs_up": pyramid_stairs(
            proportion=0.30,
            step_height_range=(0.0, 0.1),
            step_width=0.31,
            platform_width=3.0,
            border_width=1.0,
        ),
        "stairs_down": pyramid_stairs_inv(
            proportion=0.30,
            step_height_range=(0.0, 0.1),
            step_width=0.31,
            platform_width=3.0,
            border_width=1.0,
        ),
        "discrete": discrete_obstacles(
            proportion=0.10,
            obstacle_width_range=(0.3, 1.0),
            obstacle_height_range=(0.05, 0.25),
            num_obstacles=40,
            border_width=1.0,
        ),
    },
)


__all__ = [
    "FAMILIES",
    "SOURCE_VARIANT_TERRAIN",
    "VariantSpec",
    "VariantTerrain",
    "make_variant_env_cfg",
]
