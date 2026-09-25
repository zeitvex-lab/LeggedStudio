"""官方（上游）速度配方 —— 轮足族 velocity 技能的**第二个配方分支**。

## 为什么有两份配方

族内两条源流的奖励表与控制口径**不是同一份任务**（位移级差异，不是数值差异）：

| 配方 | 来源 | 观测 | 奖励表 | 谁在用 |
|---|---|---|---|---|
| `config.py`（reference） | 上游 Unitree 系轮足配方（实验室移植版） | 12 腿 + 4 轮分列 | 轮滚跟踪 / 轮接触 / 腿杆惩罚 | go2w / b2w（同模式移植） |
| 本模块（official） | 机型的**官方训练真值**（发布方 env.yaml 级口径） | 16 关节位置（轮槽置零）+ 16 关节速度 + 原始动作 | 官方 21 项表（功耗 / 镜像 / 接触力 / 阈值命令…） | deeprobotics_m20 |

两份配方共用**同一套族级底座**（`..binding.WheelLegSkillBinding` 派生关节序/执行器谱/
动作缩放，`...velocity_env_cfg` 提供框架基座，`....joint_actions` 装配动作段），因此
"换配方"不改变族级不变量：动作接口序仍 = 契约 `action.joint_order`，观测/奖励仍按
绑定派生的 `SceneEntityCfg` 取关节。

## 与源实现的逐字段对应

来源：`assets/robots/deeprobotics_m20/training/source/m20_velocity/env_cfgs.py`。
除下列**去机型化**改动外逐字段一致（等价性有 before/after 逐字段 + 解析级对拍证据）：

* 机器人实体：源 `get_m20_robot_cfg()` → `binding.robot_cfg()`；
* 关节选择器（全关节 / 腿 / 轮 / 按角色）：源写死字面元组 → 绑定派生（同一契约序）；
* 动作装配：源 `build_joint_actions(joint_order=..., control_modes=..., scale=...)`
  → 同一工厂，入参换成绑定的契约派生量；
* 轮-地接触主匹配：源写死 `.*(fr|fl|hr|hl)_wheel.*` → 绑定派生的轮接触正则（同一匹配集合，
  解析集合对拍见 workspace/validation 的 resolve_patterns 输出）；
* 轮 / 非轮 body 匹配（`.*_wheel` / `^(?!.*wheel).*`）→ 族声明的轮角色 token 派生；
* 镜像关节对（源写死 `fl_...` / `hr_...` 字面正则）→ 腿标记来自绑定 + 对角腿对索引来自 profile；
* 全部数值（出生高、命令范围/重采样、观测缩放与噪声、21 项奖励权重与阈值、地形等级、
  sim 档、平地下调档）→ `OfficialVelocityProfile` 数据；
* 机型侧的两个**注入件**（额外 mdp 奖励核 / 阈值命令类）由 profile 带入 —— 技能层不许
  import 机型包，这两样是"该机型自己的上游术语"，故随 profile 走。

## 变体

| variant | 地形 | 与前一档的差 |
|---|---|---|
| `official_rough` | 生成器 + 地形课程 | sim 档：CCD 迭代 500 / 传感器最大匹配 500 |
| `official_flat` | 平面 | 撤地形课程与 terrain_scan 传感器；sim 档换平地值（含 `nconmax=None`） |

`official_flat` 由 `official_rough` 派生后覆盖（与源实现的 flat = rough + 覆盖同序）。
"""

from __future__ import annotations

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs import mdp as envs_mdp
from mjlab.managers.observation_manager import ObservationTermCfg
from mjlab.managers.reward_manager import RewardTermCfg
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.sensor import ContactMatch, ContactSensorCfg
from mjlab.tasks.velocity import mdp as velocity_mdp
from mjlab.tasks.velocity.mdp import UniformVelocityCommandCfg
from mjlab.utils.noise import UniformNoiseCfg as Unoise

from ....joint_actions import build_joint_actions
from ...velocity_env_cfg import make_velocity_env_cfg as make_family_base_env_cfg
from .. import family as family_roles
from ..binding import WheelLegSkillBinding
from .profile import OfficialVelocityProfile

VARIANTS: tuple[str, ...] = ("official_rough", "official_flat")

#: 轮腿档 viewer 三元组（与 reference 配方同口径：机身边框 1.5 m、俯角 -10°）。
VIEWER_DISTANCE = 1.5
VIEWER_ELEVATION = -10.0
#: 平地档要撤掉的"只有 rough 才消费"的传感器名（源实现同一份名单）。
_FLAT_DROPPED_SENSORS = ("terrain_scan",)


def _wheel_body_pattern() -> str:
    """轮 body 匹配：族声明的轮角色 token（`.*_wheel`）。"""
    return f".*_{family_roles.WHEEL_ROLE}"


def _non_wheel_body_pattern() -> str:
    """非轮 body 匹配：负向断言排除轮角色 token（`^(?!.*wheel).*`）。"""
    return rf"^(?!.*{family_roles.WHEEL_ROLE}).*"


def _mirror_joint_pairs(
    binding: WheelLegSkillBinding, profile: OfficialVelocityProfile
) -> list[list[str]]:
    """镜像关节对：对角腿 × 腿段角色（角色段从契约 `leg_pattern` 取，腿标记从绑定取）。

    源实现写死 `[["fl_(hipx|hipy|knee).*", "hr_...*"], ["fr_...*", "hl_...*"]]`；
    这里把"哪两条腿互为对角"交给 profile 的腿序索引，角色候选串由契约派生 ——
    同角色同尾段时生成**同一串**（`fl_(hipx|hipy|knee).*`）。
    """
    leg_roles = [
        role
        for role in binding.leg_pattern
        if binding.family_role(role) != family_roles.WHEEL_ROLE
    ]
    roles_expr = "|".join(leg_roles)
    pairs: list[list[str]] = []
    for first, second in profile.mirror_leg_pairs:
        left = binding.leg_ids[first]
        right = binding.leg_ids[second]
        pairs.append([f"{left}_({roles_expr}).*", f"{right}_({roles_expr}).*"])
    return pairs


def _apply_actions(cfg: ManagerBasedRlEnvCfg, binding: WheelLegSkillBinding) -> None:
    """腿位置段 + 轮速度段（缩放逐关节来自契约 `actuator_profile.by_role`）。"""
    cfg.actions.update(
        build_joint_actions(
            joint_order=binding.action_joint_order,
            control_modes=dict(binding.control_modes),
            scale=dict(binding.action_scales),
            term_names=("joint_pos", "wheel_vel"),
        )
    )


def _apply_sensors(cfg: ManagerBasedRlEnvCfg, binding: WheelLegSkillBinding) -> None:
    """三组接触传感器：轮-地（族派生主匹配）+ 轮受力 + 非轮受力（族角色 token 派生）。"""
    wheel_ground_cfg = ContactSensorCfg(
        name="wheel_ground_contact",
        primary=ContactMatch(
            mode="body", pattern=binding.wheel_contact_pattern, entity="robot"
        ),
        secondary=ContactMatch(mode="body", pattern="terrain"),
        fields=("found", "force"),
        reduce="none",
        num_slots=1,
        track_air_time=False,
    )
    wheel_contact_forces = ContactSensorCfg(
        name="wheel_contact_forces",
        primary=ContactMatch(mode="body", pattern=_wheel_body_pattern(), entity="robot"),
        secondary=ContactMatch(mode="body", pattern="terrain"),
        fields=("force",),
        reduce="netforce",
        num_slots=1,
    )
    non_wheel_contact = ContactSensorCfg(
        name="non_wheel_contact",
        primary=ContactMatch(
            mode="body", pattern=_non_wheel_body_pattern(), entity="robot"
        ),
        secondary=ContactMatch(mode="body", pattern="terrain"),
        fields=("force",),
        reduce="netforce",
        num_slots=1,
    )
    cfg.scene.sensors = (
        (cfg.scene.sensors or ())
        + (wheel_ground_cfg, wheel_contact_forces, non_wheel_contact)
    )


def _apply_terrain(cfg: ManagerBasedRlEnvCfg, profile: OfficialVelocityProfile) -> None:
    """rough = 生成器 + 地形课程 + profile 的初始等级；平地档由 `official_flat` 覆盖。"""
    terrain = cfg.scene.terrain
    if terrain is None or terrain.terrain_generator is None:
        return
    terrain.terrain_generator.curriculum = True
    terrain.max_init_terrain_level = int(profile.terrain_max_init_terrain_level)


def _apply_commands(cfg: ManagerBasedRlEnvCfg, profile: OfficialVelocityProfile) -> None:
    """阈值采样的 SE(2) 速度命令：类来自 profile（机型侧上游术语），范围/重采样来自 profile。"""
    twist_cmd = cfg.commands["twist"]
    if not isinstance(twist_cmd, UniformVelocityCommandCfg):
        raise TypeError(
            "official 配方要求 twist 命令是 UniformVelocityCommandCfg，"
            f"收到 {type(twist_cmd).__name__}"
        )
    twist_cmd.class_type = profile.command_cls
    twist_cmd.heading_command = True
    twist_cmd.resampling_time_range = tuple(profile.command_resampling_time_range)
    twist_cmd.ranges.lin_vel_x = tuple(profile.command_ranges.lin_vel_x)
    twist_cmd.ranges.lin_vel_y = tuple(profile.command_ranges.lin_vel_y)
    twist_cmd.ranges.ang_vel_z = tuple(profile.command_ranges.ang_vel_z)
    twist_cmd.ranges.heading = tuple(profile.heading_range)


def _apply_observations(
    cfg: ManagerBasedRlEnvCfg,
    binding: WheelLegSkillBinding,
    profile: OfficialVelocityProfile,
) -> None:
    """官方观测布局：16 关节位置（轮槽置零）+ 16 关节速度 + 原始动作（缩放/噪声来自 profile）。"""
    all_joint_cfg = SceneEntityCfg(
        "robot", joint_names=list(binding.action_joint_order), preserve_order=True
    )
    wheel_joint_cfg = binding.wheel_joint_cfg()
    for group_name in ("actor", "critic"):
        cfg.observations[group_name].terms = {
            "base_ang_vel": ObservationTermCfg(
                func=envs_mdp.base_ang_vel,
                scale=profile.base_ang_vel_scale,
                noise=Unoise(
                    n_min=-profile.base_ang_vel_noise, n_max=profile.base_ang_vel_noise
                )
                if group_name == "actor"
                else None,
            ),
            "projected_gravity": ObservationTermCfg(
                func=envs_mdp.projected_gravity,
                noise=Unoise(
                    n_min=-profile.projected_gravity_noise,
                    n_max=profile.projected_gravity_noise,
                )
                if group_name == "actor"
                else None,
            ),
            "command": ObservationTermCfg(
                func=envs_mdp.generated_commands, params={"command_name": "twist"}
            ),
            "joint_pos_rel": ObservationTermCfg(
                func=profile.terms.joint_pos_rel_zero_wheel,
                params={"all_cfg": all_joint_cfg, "wheel_cfg": wheel_joint_cfg},
                scale=profile.joint_pos_scale,
                noise=Unoise(n_min=-profile.joint_pos_noise, n_max=profile.joint_pos_noise)
                if group_name == "actor"
                else None,
            ),
            "joint_vel_rel": ObservationTermCfg(
                func=envs_mdp.joint_vel_rel,
                params={"asset_cfg": all_joint_cfg},
                scale=profile.joint_vel_scale,
                noise=Unoise(n_min=-profile.joint_vel_noise, n_max=profile.joint_vel_noise)
                if group_name == "actor"
                else None,
            ),
            "actions": ObservationTermCfg(func=envs_mdp.last_action),
        }


def _apply_rewards(
    cfg: ManagerBasedRlEnvCfg,
    binding: WheelLegSkillBinding,
    profile: OfficialVelocityProfile,
) -> None:
    """官方 21 项奖励表（权重与阈值来自 profile；关节选择器来自绑定）。"""
    terms = profile.terms
    leg_joint_cfg = binding.leg_joint_cfg()
    wheel_joint_cfg = binding.wheel_joint_cfg()
    all_joint_cfg = SceneEntityCfg(
        "robot", joint_names=list(binding.action_joint_order), preserve_order=True
    )
    weights = dict(profile.reward_weights)
    cfg.rewards = {
        "lin_vel_z_l2": RewardTermCfg(
            func=terms.lin_vel_z_l2, weight=weights["lin_vel_z_l2"]
        ),
        "ang_vel_xy_l2": RewardTermCfg(
            func=terms.ang_vel_xy_l2, weight=weights["ang_vel_xy_l2"]
        ),
        "flat_orientation_l2": RewardTermCfg(
            func=terms.flat_orientation_l2, weight=weights["flat_orientation_l2"]
        ),
        "base_height_l2": RewardTermCfg(
            func=terms.base_height_l2,
            weight=weights["base_height_l2"],
            params={"target_height": profile.base_height_target},
        ),
        "joint_torques_l2": RewardTermCfg(
            func=envs_mdp.joint_torques_l2,
            weight=weights["joint_torques_l2"],
            params={"asset_cfg": leg_joint_cfg},
        ),
        "joint_acc_l2": RewardTermCfg(
            func=envs_mdp.joint_acc_l2,
            weight=weights["joint_acc_l2"],
            params={"asset_cfg": leg_joint_cfg},
        ),
        "joint_acc_wheel_l2": RewardTermCfg(
            func=envs_mdp.joint_acc_l2,
            weight=weights["joint_acc_wheel_l2"],
            params={"asset_cfg": wheel_joint_cfg},
        ),
        "joint_pos_limits": RewardTermCfg(
            func=envs_mdp.joint_pos_limits,
            weight=weights["joint_pos_limits"],
            params={"asset_cfg": leg_joint_cfg},
        ),
        "joint_power": RewardTermCfg(
            func=terms.joint_power,
            weight=weights["joint_power"],
            params={"asset_cfg": leg_joint_cfg},
        ),
        "hip_joint_pos_penalty": RewardTermCfg(
            func=terms.joint_pos_penalty,
            weight=weights["hip_joint_pos_penalty"],
            params={
                "command_name": "twist",
                "asset_cfg": binding.role_scene_entity_cfg("hip_abduction", as_list=True),
                "stand_still_scale": profile.joint_pos_penalty_stand_still_scale,
                "velocity_threshold": profile.joint_pos_penalty_velocity_threshold,
                "command_threshold": profile.joint_pos_penalty_command_threshold,
            },
        ),
        "thigh_joint_pos_penalty": RewardTermCfg(
            func=terms.joint_pos_penalty,
            weight=weights["thigh_joint_pos_penalty"],
            params={
                "command_name": "twist",
                "asset_cfg": binding.role_scene_entity_cfg("hip_pitch", as_list=True),
                "stand_still_scale": profile.joint_pos_penalty_stand_still_scale,
                "velocity_threshold": profile.joint_pos_penalty_velocity_threshold,
                "command_threshold": profile.joint_pos_penalty_command_threshold,
            },
        ),
        "knee_joint_pos_penalty": RewardTermCfg(
            func=terms.joint_pos_penalty,
            weight=weights["knee_joint_pos_penalty"],
            params={
                "command_name": "twist",
                "asset_cfg": binding.role_scene_entity_cfg("knee", as_list=True),
                "stand_still_scale": profile.joint_pos_penalty_stand_still_scale,
                "velocity_threshold": profile.joint_pos_penalty_velocity_threshold,
                "command_threshold": profile.joint_pos_penalty_command_threshold,
            },
        ),
        "joint_mirror": RewardTermCfg(
            func=terms.joint_mirror,
            weight=weights["joint_mirror"],
            params={
                "asset_cfg": all_joint_cfg,
                "mirror_joints": _mirror_joint_pairs(binding, profile),
            },
        ),
        "action_rate_l2": RewardTermCfg(
            func=envs_mdp.action_rate_l2, weight=weights["action_rate_l2"]
        ),
        "undesired_contacts": RewardTermCfg(
            func=terms.undesired_contacts,
            weight=weights["undesired_contacts"],
            params={
                "sensor_cfg": terms.ContactSensorRef("non_wheel_contact", None),
                "threshold": profile.undesired_contacts_threshold,
            },
        ),
        "contact_forces": RewardTermCfg(
            func=terms.contact_forces,
            weight=weights["contact_forces"],
            params={
                "sensor_cfg": terms.ContactSensorRef("wheel_contact_forces", None),
                "threshold": profile.contact_forces_threshold,
            },
        ),
        "track_lin_vel_xy_exp": RewardTermCfg(
            func=velocity_mdp.track_linear_velocity,
            weight=weights["track_lin_vel_xy_exp"],
            params={"command_name": "twist", "std": profile.tracking_std},
        ),
        "track_ang_vel_z_exp": RewardTermCfg(
            func=velocity_mdp.track_angular_velocity,
            weight=weights["track_ang_vel_z_exp"],
            params={"command_name": "twist", "std": profile.tracking_std},
        ),
        "feet_contact_without_cmd": RewardTermCfg(
            func=terms.feet_contact_without_cmd,
            weight=weights["feet_contact_without_cmd"],
            params={
                "command_name": "twist",
                "sensor_cfg": terms.ContactSensorRef("wheel_contact_forces", None),
            },
        ),
        "stand_still": RewardTermCfg(
            func=terms.stand_still_joint_deviation_l1,
            weight=weights["stand_still"],
            params={"command_name": "twist", "asset_cfg": leg_joint_cfg},
        ),
        "upward": RewardTermCfg(func=terms.upward, weight=weights["upward"]),
    }


def _apply_viewer_and_events(
    cfg: ManagerBasedRlEnvCfg, binding: WheelLegSkillBinding
) -> None:
    """viewer 三元组（族口径）+ 机身段指向根 body（推扰事件照源实现**保留**）。"""
    cfg.viewer.body_name = binding.root_body
    cfg.viewer.distance = VIEWER_DISTANCE
    cfg.viewer.elevation = VIEWER_ELEVATION
    cfg.events["base_com"].params["asset_cfg"].body_names = (binding.root_body,)


def _apply_flat(cfg: ManagerBasedRlEnvCfg, profile: OfficialVelocityProfile) -> None:
    """平地档：sim 换平地档、地形退成平面、撤地形课程与 terrain_scan 传感器、撤高度观测。"""
    sim = profile.flat_sim
    if sim.njmax is not None:
        cfg.sim.njmax = int(sim.njmax)
    cfg.sim.mujoco.ccd_iterations = int(sim.ccd_iterations)
    cfg.sim.contact_sensor_maxmatch = int(sim.contact_sensor_maxmatch)
    cfg.sim.nconmax = None if sim.nconmax is None else int(sim.nconmax)
    if cfg.scene.terrain is None:
        raise ValueError("official 配方要求地形段在场（scene.terrain 为 None）")
    cfg.scene.terrain.terrain_type = "plane"
    cfg.scene.terrain.terrain_generator = None
    cfg.scene.sensors = tuple(
        sensor
        for sensor in (cfg.scene.sensors or ())
        if sensor.name not in _FLAT_DROPPED_SENSORS
    )
    for group in ("actor", "critic"):
        cfg.observations[group].terms.pop("height_scan", None)
    cfg.terminations.pop("out_of_terrain_bounds", None)
    cfg.curriculum.pop("terrain_levels", None)


def _apply_play(cfg: ManagerBasedRlEnvCfg) -> None:
    """play 口径：无限时长、关观测噪声、去推扰、清课程（源实现整段清空课程表）。"""
    cfg.episode_length_s = int(1e9)
    cfg.observations["actor"].enable_corruption = False
    cfg.events.pop("push_robot", None)
    cfg.terminations.pop("out_of_terrain_bounds", None)
    cfg.curriculum = {}
    terrain = cfg.scene.terrain
    generator = terrain.terrain_generator if terrain is not None else None
    if generator is not None:
        generator.curriculum = False
        generator.num_cols = 5
        generator.num_rows = 5
        generator.border_width = 10.0


def make_env_cfg(
    binding: WheelLegSkillBinding,
    profile: OfficialVelocityProfile,
    *,
    variant: str = "official_rough",
    play: bool = False,
) -> ManagerBasedRlEnvCfg:
    """装配官方（上游）速度配方的环境（rough / flat 同一份实现）。

    Args:
        binding: 该机型的绑定（契约 + MJCF 派生；见 `../binding.py`）。
        profile: 该机型该档的官方配方数据（见 `profile.OfficialVelocityProfile`）。
        variant: `official_rough` | `official_flat`。
        play: 播放口径（无限时长、关噪声、去推扰、清课程）。
    """
    if variant not in VARIANTS:
        raise ValueError(f"未知变体 {variant!r}（官方配方只认 {VARIANTS}）")
    if not isinstance(binding, WheelLegSkillBinding):
        raise TypeError(f"binding 必须是 WheelLegSkillBinding，收到 {type(binding).__name__}")
    if not isinstance(profile, OfficialVelocityProfile):
        raise TypeError(
            f"profile 必须是 OfficialVelocityProfile，收到 {type(profile).__name__}"
        )

    # 基座 = 框架 family velocity cfg（twist 基类取 mjlab 版本：官方配方的阈值命令类
    # 正是子类化它 —— 源包内 stub 显式传的就是这个类）。
    cfg = make_family_base_env_cfg(uniform_velocity_command_cfg=UniformVelocityCommandCfg)
    cfg.sim.mujoco.ccd_iterations = int(profile.rough_sim.ccd_iterations)
    cfg.sim.contact_sensor_maxmatch = int(profile.rough_sim.contact_sensor_maxmatch)
    cfg.scene.entities = {"robot": binding.robot_cfg()}
    _apply_actions(cfg, binding)
    _apply_sensors(cfg, binding)
    _apply_terrain(cfg, profile)
    _apply_commands(cfg, profile)
    _apply_observations(cfg, binding, profile)
    _apply_rewards(cfg, binding, profile)
    _apply_viewer_and_events(cfg, binding)
    if play:
        _apply_play(cfg)
    if variant == "official_flat":
        _apply_flat(cfg, profile)
    return cfg


__all__: tuple[str, ...] = ("VARIANTS", "make_env_cfg")
