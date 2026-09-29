"""族级 velocity 技能的环境工厂（轮足族）—— 一份实现，四个变体，零机型字面量。

来源：`assets/robots/unitree_go2w/training/source/go2w_velocity/env_cfgs.py`（333 行）。
除下列**去机型化**改动外逐字段一致（等价性有 before/after 逐字段对拍证据）：

* 机器人实体：源 `get_go2w_scene_robot_cfg()` → `binding.robot_cfg()`；
* 关节名/序/动作缩放/控制模式：源写死字面元组 → 绑定的契约派生量；
* 动作装配：源手写两个动作项 → 共享工厂 `build_joint_actions`（按契约**连续**分段、保序）；
* 轮-地接触匹配：源写死 `.*(FR|FL|RR|RL)_(wheel|foot).*` → 绑定派生（同一匹配集合）；
* 根 body / 腿-轮关节选择器 / 姿态 std 表键：源写死 → 绑定 + profile 派生；
* 全部数值（出生高、地形档、命令范围、轮几何、噪声、权重、课程分段）→ profile 数据。

## 四条变体是**同一份实现**的具名分支

`variant` 只决定结构（地形生成器开不开、动作含不含轮、奖励表换不换、有没有低落终止），
数值一律来自 profile：

| variant | 地形 | 动作 | 腿杆惩罚 | 轮奖励 |
|---|---|---|---|---|
| `rough` | 生成器 + 地形课程 | 腿位置 + 轮速度 | 自适应（`adaptive_leg_motion_penalty`） | 轮跟踪/轮接触/腿杆惩罚 |
| `flat` | 平面 | 腿位置 + 轮速度 | 平惩罚（`leg_motion_penalty`） | 同上 |
| `flat_legs_only` | 平面 | **仅**腿位置 | 无 | 轮速限幅/身高/站立 |
| `flat_legs_only_omni` | 平面 | 仅腿位置 | 无 | 同 `flat_legs_only`（全向命令） |

另两条配方各有自己的具名变体（分流在本模块的族级入口）：
`official_rough` / `official_flat`（`official.py` 官方配方）与
`competition_flat` / `competition_rough`（`competition.py` 竞赛配方）。
"""

from __future__ import annotations

from copy import deepcopy

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.managers import (
    ObservationTermCfg,
    RewardTermCfg,
    SceneEntityCfg,
    TerminationTermCfg,
)
from mjlab.sensor import ContactMatch, ContactSensorCfg
from mjlab.utils.noise import UniformNoiseCfg as Unoise

from ....joint_actions import build_joint_actions
from ...velocity_env_cfg import make_velocity_env_cfg as make_family_base_env_cfg
from ...mdp import (
    adaptive_leg_motion_penalty,
    base_ang_vel,
    base_height_tracking,
    base_lin_vel,
    contact_fraction_reward,
    leg_motion_penalty,
    root_height_below_minimum,
    stand_still,
    wheel_joint_pos_rel,
    wheel_joint_vel_rel,
    wheel_roll_tracking,
    wheel_speed_limit_penalty,
)
from ..binding import WheelLegSkillBinding
from .competition import VARIANTS as COMPETITION_VARIANTS
from .competition import make_env_cfg as competition_make_env_cfg
from .official import VARIANTS as OFFICIAL_VARIANTS
from .official import make_env_cfg as official_make_env_cfg
from .profile import (
    CompetitionVelocityProfile,
    LegsOnlyRecipe,
    OfficialVelocityProfile,
    VelocityProfile,
)

VARIANTS: tuple[str, ...] = (
    "rough",
    "flat",
    "flat_legs_only",
    "flat_legs_only_omni",
)
#: 轮-地接触传感器的族级名字（奖励项按名字取它；族内统一，不随机型变）。
WHEEL_GROUND_SENSOR = "wheel_ground_contact"
#: viewer 三元组（轮足 velocity 族口径：机身边框 1.5 m、俯角 -10°；body 走绑定）。
VIEWER_DISTANCE = 1.5
VIEWER_ELEVATION = -10.0
#: 轮足速度技能不含"足端"奖励项：脚相关的基座项在装配时移除。
_FOOTLESS_REWARD_TERMS = (
    "foot_air_time",
    "foot_clearance",
    "foot_slip",
    "soft_landing",
    "angular_momentum",
)
_WHEEL_RECIPE = "rough"
_FLAT_RECIPE = "flat"


def _is_legs_only(variant: str) -> bool:
    return variant.startswith("flat_legs_only")


def _legs_only_recipe(profile: VelocityProfile, variant: str) -> LegsOnlyRecipe:
    if profile.legs_only is None:
        raise ValueError(
            f"变体 {variant!r} 需要纯腿配方数值，但 profile 未给 legs_only（源配方的轮速限幅/身高/"
            "站立/低落终止阈值必须由机型 profile 显式给出）"
        )
    return profile.legs_only


def _validate_profile(binding: WheelLegSkillBinding, profile: VelocityProfile, variant: str) -> None:
    """数据齐备性判红（缺就抛错，不静默用 0 值跑）。"""
    for name, table in (
        ("pose_std_standing", profile.pose_std_standing),
        ("pose_std_walking", profile.pose_std_walking),
        ("pose_std_running", profile.pose_std_running),
    ):
        if not table:
            raise ValueError(f"profile.{name} 为空 —— 姿态奖励的 std 表必须由机型 profile 给出")
        for role in table:
            try:
                binding.family_role(role)
            except ValueError as exc:
                raise ValueError(f"profile.{name} 的角色 {role!r} 无法解析：{exc}") from exc
    if profile.wheel_radius <= 0.0 or profile.wheel_track <= 0.0:
        raise ValueError(
            f"profile 的轮几何非法（wheel_radius={profile.wheel_radius}, wheel_track={profile.wheel_track}）"
        )
    if _is_legs_only(variant):
        _legs_only_recipe(profile, variant)


def _apply_actions(
    cfg: ManagerBasedRlEnvCfg,
    binding: WheelLegSkillBinding,
    profile: VelocityProfile,
    variant: str,
) -> None:
    """腿段（位置）+ 轮段（速度）两段动作；纯腿变体只留腿段（缩放换 profile 值）。"""
    control_modes = dict(binding.control_modes)
    scale = dict(binding.action_scales)
    if _is_legs_only(variant):
        recipe = _legs_only_recipe(profile, variant)
        joint_order: tuple[str, ...] = binding.leg_joint_order
        term_names: tuple[str, ...] = ("joint_pos",)
        for joint in binding.leg_joint_order:
            scale[joint] = recipe.action_scale
    else:
        joint_order = binding.action_joint_order
        term_names = ("joint_pos", "wheel_vel")
    cfg.actions.update(
        build_joint_actions(
            joint_order=joint_order,
            control_modes=control_modes,
            scale=scale,
            term_names=term_names,
            # 上游 rc_mjlab 低通动作（腿 5Hz / 轮 15Hz）：平滑动作跳变，
            # 是 go2w-traversal 750 轮尾步物理爆炸（obs NaN）的上游防线。
            low_pass=True,
            control_frequency=float(cfg.sim.mujoco.timestep) and (
                1.0 / (float(cfg.sim.mujoco.timestep) * (cfg.decimation or 4))
            ),
        )
    )


def _apply_sensors(cfg: ManagerBasedRlEnvCfg, binding: WheelLegSkillBinding) -> None:
    """轮-地 + 机身-地接触传感器（主匹配由绑定派生：腿标记 + 轮角色别名/根 body）。

    base_ground 供 kit 终止项 `base_ground_contact` 消费（上游 rc_mjlab 同款：
    躯干碰地立刻终止，防翻滚拖行进入物理爆炸区）。
    """
    cfg.scene.sensors = (
        ContactSensorCfg(
            name=WHEEL_GROUND_SENSOR,
            primary=ContactMatch(mode="body", pattern=binding.wheel_contact_pattern, entity="robot"),
            secondary=ContactMatch(mode="body", pattern="terrain"),
            fields=("found", "force"),
            reduce="none",
            num_slots=1,
            track_air_time=False,
        ),
        ContactSensorCfg(
            name="base_ground_contact",
            primary=ContactMatch(mode="body", pattern=binding.root_body, entity="robot"),
            secondary=ContactMatch(mode="body", pattern="terrain"),
            fields=("found",),
            reduce="none",
            num_slots=1,
            history_length=4,
        ),
    )


def _apply_terrain(
    cfg: ManagerBasedRlEnvCfg, profile: VelocityProfile, variant: str
) -> None:
    """rough = 生成器 + 地形课程（比例/噪声/难度全都来自 profile）；其余三档 = 平面。

    `max_init_terrain_level` 四档都写（源实现是在 rough 函数里设一次、平地档沿用该值）。
    """
    terrain = cfg.scene.terrain
    if terrain is None:
        raise ValueError("velocity 基座缺 terrain 段（scene.terrain 为 None）")
    terrain.max_init_terrain_level = int(profile.terrain_max_init_terrain_level)
    if variant == _WHEEL_RECIPE:
        generator = terrain.terrain_generator
        if generator is None:
            raise ValueError("rough 变体要求地形生成器在场（基座地形集被换成平面了）")
        generator.curriculum = True
        generator.difficulty_range = tuple(profile.terrain_difficulty_range)
        for name, overrides in profile.terrain_overrides.items():
            sub = generator.sub_terrains.get(name)
            if sub is None:
                raise ValueError(
                    f"profile.terrain_overrides 的子地形 {name!r} 不在框架地形集里"
                    f"（可用：{sorted(generator.sub_terrains)}）"
                )
            for key, value in overrides.items():
                setattr(sub, key, value)
        return
    terrain.terrain_type = "plane"
    terrain.terrain_generator = None
    if "terrain_levels" not in cfg.curriculum:
        raise ValueError("平地变体要求基座课程里有 terrain_levels（地形课程项）")
    del cfg.curriculum["terrain_levels"]


def _apply_commands(cfg: ManagerBasedRlEnvCfg, profile: VelocityProfile) -> None:
    """twist 命令：范围/朝向开关/站立比全走 profile（源配方四档各自的字面值）。"""
    twist = cfg.commands["twist"]
    twist.heading_command = bool(profile.heading_command)
    twist.rel_heading_envs = float(profile.rel_heading_envs)
    twist.rel_standing_envs = float(profile.rel_standing_envs)
    twist.ranges.heading = None
    twist.ranges.lin_vel_x = tuple(profile.command_ranges.lin_vel_x)
    twist.ranges.lin_vel_y = tuple(profile.command_ranges.lin_vel_y)
    twist.ranges.ang_vel_z = tuple(profile.command_ranges.ang_vel_z)


def _apply_curriculum(cfg: ManagerBasedRlEnvCfg, profile: VelocityProfile) -> None:
    """速度课程分段（deepcopy：profile 是模块级单例，不能被 mjlab 原地改）。"""
    if "command_vel" in cfg.curriculum:
        cfg.curriculum["command_vel"].params["velocity_stages"] = [
            dict(stage) for stage in profile.command_vel_stages
        ]


def _apply_observations(
    cfg: ManagerBasedRlEnvCfg, binding: WheelLegSkillBinding, profile: VelocityProfile
) -> None:
    """关节观测：腿关节走基座两项（换腿选择器），轮关节另起两项（含 profile 噪声）。"""
    leg_cfg = binding.leg_joint_cfg()
    wheel_cfg = binding.wheel_joint_cfg()
    for group_name in ("actor", "critic"):
        terms = cfg.observations[group_name].terms
        actions_term = terms.pop("actions")
        terms["joint_pos"].params = {"asset_cfg": leg_cfg}
        terms["joint_vel"].params = {"asset_cfg": leg_cfg}
        terms["wheel_joint_pos_rel"] = ObservationTermCfg(
            func=wheel_joint_pos_rel,
            params={"asset_cfg": wheel_cfg},
            noise=(
                Unoise(n_min=-profile.wheel_joint_pos_noise, n_max=profile.wheel_joint_pos_noise)
                if group_name == "actor"
                else None
            ),
        )
        terms["wheel_joint_vel_rel"] = ObservationTermCfg(
            func=wheel_joint_vel_rel,
            params={"asset_cfg": wheel_cfg},
            noise=(
                Unoise(n_min=-profile.wheel_joint_vel_noise, n_max=profile.wheel_joint_vel_noise)
                if group_name == "actor"
                else None
            ),
        )
        terms["actions"] = actions_term
        # 基座两项原本读 IMU 传感器声明；轮足速度技能改为直接算（与源配方一致）。
        terms["base_ang_vel"].func = base_ang_vel
        terms["base_ang_vel"].params = {}
    cfg.observations["critic"].terms["base_lin_vel"].func = base_lin_vel
    cfg.observations["critic"].terms["base_lin_vel"].params = {}


def _apply_events(
    cfg: ManagerBasedRlEnvCfg, binding: WheelLegSkillBinding, variant: str, profile: VelocityProfile
) -> None:
    """事件表：机身段用根 body、摩擦随机化覆盖全部几何；轮足速度技能不推机器人。"""
    cfg.events["base_com"].params["asset_cfg"].body_names = (binding.root_body,)
    cfg.events["body_friction"].params["asset_cfg"] = SceneEntityCfg("robot", geom_ids=slice(None))
    if _is_legs_only(variant):
        recipe = _legs_only_recipe(profile, variant)
        cfg.events["body_friction"].params["ranges"] = tuple(recipe.body_friction_range)
    cfg.events.pop("push_robot", None)


def _apply_viewer(cfg: ManagerBasedRlEnvCfg, binding: WheelLegSkillBinding) -> None:
    cfg.viewer.body_name = binding.root_body
    cfg.viewer.distance = VIEWER_DISTANCE
    cfg.viewer.elevation = VIEWER_ELEVATION


def _apply_rewards(
    cfg: ManagerBasedRlEnvCfg,
    binding: WheelLegSkillBinding,
    profile: VelocityProfile,
    variant: str,
) -> None:
    """奖励表：基座项按腿关节重定向 → 移除足端项 → 按变体追加轮奖励或纯腿奖励。"""
    leg_cfg = binding.leg_joint_cfg()
    wheel_cfg = binding.wheel_joint_cfg()
    cfg.rewards["pose"].params["asset_cfg"] = leg_cfg
    cfg.rewards["joint_pos_limits"].params["asset_cfg"] = leg_cfg
    cfg.rewards["joint_acc_l2"].params["asset_cfg"] = leg_cfg
    # 姿态 std 表：profile 给"角色 → std"，这里展开成绑定派生的角色正则。
    cfg.rewards["pose"].params["std_standing"] = {
        binding.role_joint_pattern(role): std for role, std in profile.pose_std_standing.items()
    }
    cfg.rewards["pose"].params["std_walking"] = {
        binding.role_joint_pattern(role): std for role, std in profile.pose_std_walking.items()
    }
    cfg.rewards["pose"].params["std_running"] = {
        binding.role_joint_pattern(role): std for role, std in profile.pose_std_running.items()
    }
    for name in _FOOTLESS_REWARD_TERMS:
        cfg.rewards.pop(name, None)

    if _is_legs_only(variant):
        recipe = _legs_only_recipe(profile, variant)
        cfg.rewards["wheel_spin_limit"] = RewardTermCfg(
            func=wheel_speed_limit_penalty,
            weight=recipe.wheel_spin_limit_weight,
            params={
                "max_abs_speed": recipe.wheel_spin_limit_max_speed,
                "command_name": "twist",
                "command_threshold": recipe.wheel_spin_limit_command_threshold,
                "asset_cfg": wheel_cfg,
            },
        )
        cfg.rewards["base_height"] = RewardTermCfg(
            func=base_height_tracking,
            weight=recipe.base_height_weight,
            params={"target_height": recipe.base_height_target, "std": recipe.base_height_std},
        )
        cfg.rewards["stand_still"] = RewardTermCfg(
            func=stand_still,
            weight=recipe.stand_still_weight,
            params={
                "command_name": "twist",
                "command_threshold": recipe.stand_still_command_threshold,
                "asset_cfg": leg_cfg,
            },
        )
        cfg.rewards["flat_orientation_l2"].weight = recipe.flat_orientation_weight
        cfg.rewards["body_ang_vel"].weight = recipe.body_ang_vel_weight
    else:
        cfg.rewards["wheel_roll_tracking"] = RewardTermCfg(
            func=wheel_roll_tracking,
            weight=profile.wheel_roll_tracking_weight,
            params={
                "command_name": "twist",
                "wheel_radius": profile.wheel_radius,
                "wheel_track": profile.wheel_track,
                "std": profile.wheel_roll_tracking_std,
                "asset_cfg": wheel_cfg,
            },
        )
        cfg.rewards["wheel_contact_bonus"] = RewardTermCfg(
            func=contact_fraction_reward,
            weight=profile.wheel_contact_bonus_weight,
            params={"sensor_name": WHEEL_GROUND_SENSOR},
        )
        cfg.rewards["leg_motion_penalty"] = RewardTermCfg(
            func=(
                adaptive_leg_motion_penalty if variant == _WHEEL_RECIPE else leg_motion_penalty
            ),
            weight=profile.leg_motion_penalty_weight,
            params={
                "command_name": "twist",
                "command_threshold": profile.leg_motion_command_threshold,
                **(
                    {
                        "sensor_name": WHEEL_GROUND_SENSOR,
                        "tilt_relax_start": profile.leg_motion_tilt_relax_start,
                        "tilt_relax_end": profile.leg_motion_tilt_relax_end,
                        "contact_target": profile.leg_motion_contact_target,
                        "min_penalty_scale": profile.leg_motion_min_penalty_scale,
                    }
                    if variant == _WHEEL_RECIPE
                    else {}
                ),
                "asset_cfg": leg_cfg,
            },
        )
        cfg.rewards["flat_orientation_l2"].weight = profile.flat_orientation_weight
        cfg.rewards["body_ang_vel"].weight = profile.body_ang_vel_weight
    cfg.rewards["body_ang_vel"].params["asset_cfg"].body_names = (binding.root_body,)


def _apply_terminations(
    cfg: ManagerBasedRlEnvCfg, profile: VelocityProfile, variant: str
) -> None:
    if _is_legs_only(variant):
        recipe = _legs_only_recipe(profile, variant)
        cfg.terminations["low_base_height"] = TerminationTermCfg(
            func=root_height_below_minimum,
            params={"minimum_height": recipe.low_base_height},
        )


def _apply_play(cfg: ManagerBasedRlEnvCfg) -> None:
    """play 口径：无限时长、关观测噪声、去推扰；地形生成器退成固定小场。"""
    cfg.episode_length_s = int(1e9)
    cfg.observations["actor"].enable_corruption = False
    cfg.events.pop("push_robot", None)
    terrain = cfg.scene.terrain
    generator = terrain.terrain_generator if terrain is not None else None
    if generator is not None:
        generator.curriculum = False
        generator.num_cols = 5
        generator.num_rows = 5
        generator.border_width = 10.0


def make_env_cfg(
    binding: WheelLegSkillBinding,
    profile: VelocityProfile | OfficialVelocityProfile,
    *,
    variant: str = _WHEEL_RECIPE,
    play: bool = False,
) -> ManagerBasedRlEnvCfg:
    """装配族级 velocity 环境（族级入口：按 variant 分流到对应配方）。

    三条配方共用绑定与族级不变量（动作接口序 = 契约 `action.joint_order`）：

    * reference 配方（本模块）：`rough` | `flat` | `flat_legs_only` | `flat_legs_only_omni`；
    * 官方配方（`official.py`）：`official_rough` | `official_flat`；
    * 竞赛配方（`competition.py`）：`competition_flat` | `competition_rough`。

    Args:
        binding: 该机型的绑定（契约 + MJCF 派生；见 `skills/binding.py`）。
        profile: 该机型该档的源配方数据（`velocity/profile.py` 的三种 profile）。
        variant: 见上（reference 四变体 / 官方两变体 / 竞赛两变体）。
        play: 播放口径（无限时长、关噪声、去推扰）。
    """
    if variant in OFFICIAL_VARIANTS:
        return official_make_env_cfg(binding, profile, variant=variant, play=play)
    if variant in COMPETITION_VARIANTS:
        return competition_make_env_cfg(binding, profile, variant=variant, play=play)
    if variant not in VARIANTS:
        raise ValueError(
            f"未知变体 {variant!r}（reference 只认 {VARIANTS}，官方只认 {OFFICIAL_VARIANTS}，"
            f"竞赛只认 {COMPETITION_VARIANTS}）"
        )
    if not isinstance(binding, WheelLegSkillBinding):
        raise TypeError(f"binding 必须是 WheelLegSkillBinding，收到 {type(binding).__name__}")
    if not isinstance(profile, VelocityProfile):
        raise TypeError(f"profile 必须是 VelocityProfile，收到 {type(profile).__name__}")
    _validate_profile(binding, profile, variant)

    cfg = make_family_base_env_cfg(only_positive_rewards=getattr(profile, "only_positive_rewards", False))
    cfg.scene.entities = {"robot": binding.robot_cfg()}
    _apply_actions(cfg, binding, profile, variant)
    _apply_sensors(cfg, binding)
    _apply_terrain(cfg, profile, variant)
    _apply_commands(cfg, profile)
    _apply_curriculum(cfg, profile)
    _apply_observations(cfg, binding, profile)
    _apply_events(cfg, binding, variant, profile)
    _apply_rewards(cfg, binding, profile, variant)
    _apply_terminations(cfg, profile, variant)
    _apply_viewer(cfg, binding)
    if play:
        cfg = deepcopy(cfg)
        _apply_play(cfg)
    return cfg


__all__: tuple[str, ...] = ("VARIANTS", "WHEEL_GROUND_SENSOR", "make_env_cfg")


def make_runner_cfg(profile, *, experiment_name: str = "") -> RslRlOnPolicyRunnerCfg:
    """族级轮足 velocity runner（与四足族同一个签名 `make_runner_cfg(profile)`）。

    PPO 档取本族逐字共享的 `wheel_leg_kit.ppo_runner_cfg_ex`；实验名从 profile 的身份字段来
    （通用装配注入；缺省 = 族级默认名）。这条是给**无档案的新机型**用的：装配表声明它即可。
    """
    from ... import ppo_runner_cfg_ex

    return ppo_runner_cfg_ex("family_wheel_velocity")
