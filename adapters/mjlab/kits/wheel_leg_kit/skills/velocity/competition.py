"""竞赛配方 —— 轮足族 velocity 技能的**第三个配方分支**。

## 为什么是第三份配方（而不是 reference + 不同数值）

族内三条源流的**任务结构**不同，位移级差异不是数值差异：

| 配方 | 动作接口 | 命令 | 观测 | 奖励表 | 谁在用 |
|---|---|---|---|---|---|
| `config.py`（reference） | 位置 + 速度两段（共享动作工厂） | 均匀采样 twist | 12 腿 + 4 轮分列 | 轮滚跟踪 / 轮接触 / 腿杆惩罚 | go2w / b2w |
| `official.py`（官方） | 位置 + 速度两段 | 官方阈值命令类 | 16 关节位置（轮槽置零）+ 16 关节速度 | 官方 21 项表 | deeprobotics_m20 |
| 本模块（竞赛） | **延时 + 一阶低通**的机型动作项 | **阈值 + 单轴采样 + 地形自适应**的机型命令类 | 腿 12 / 轮 4 / 原始动作 16，**逐项自带缩放与噪声**；critic 多足接触 + 高度扫描 | **逐档不同**：平地 16 项（轮奖励为主）/ 越障 24 项（分轴跟踪 + 镜像 + 接触力） | zex-w |

三条都共用**同一套族级底座**：`..binding.WheelLegSkillBinding` 派生关节序 / 执行器谱 /
动作缩放 / 根 body / 接触匹配，`..family` 提供族角色解析。因此"换配方"不改族级不变量：
动作接口序仍等于契约 `action.joint_order`，观测/奖励一律按绑定派生的 `SceneEntityCfg` 取关节。

## 与源实现的逐字段对应

来源：`assets/robots/zex-w/training/source/robot/config/env_cfgs.py`
（`_make_base_env_cfg` + `flat_env_cfg` + `rough_env_cfg`，共 851 行；crawl 档是另一条任务，
不住本模块）。两档都在本模块里是 `variant` 具名分支：`competition_flat` = 基座表 + 平地
地块生成器；`competition_rough` = 越障表 + 族级竞赛课程 + 自适应命令课程 + 诊断指标。

除下列**去机型化**改动外逐字段一致（等价性有 before/after 逐字段 + 解析级对拍证据）：

* 机器人实体：源 `get_robot_cfg()` → `binding.robot_cfg()`（默认姿/PD 谱来自契约）；
* 关节选择器（腿 / 轮 / 按角色）：源写死 `.*_hip_abduction_joint` 一类模式串 →
  绑定派生的 `SceneEntityCfg`（契约动作序，解析集合相同）；
* 轮-地接触匹配：源写死 `("fl_wheel_Link", …)` → 族声明的轮角色别名派生正则（同一匹配集合）；
* 机身段（根 body）：源写死 `"base_link"` → `binding.root_body`（MJCF 真值）；
* 镜像关节对（源写死 `fl_(hip_pitch|knee)_joint` 等字面正则）→ 腿标记来自绑定、
  配对来自 profile 的腿序索引、关节模式由契约关节名派生（生成同一串）；
* 动作项类与命令类（源在机型包里）→ profile 注入（技能层不 import 机型包）；
* 全部数值（并行环境数 / 出生高 / sim 档 / 地形地块 / 命令区间 / 噪声 / 事件区间 /
  奖励权重与阈值 / 课程数值 / 指标带宽）→ `CompetitionVelocityProfile`。

## 两档的结构差异（都在本模块里，数值在 profile）

| variant | 地形 | 奖励表 | 课程 | 指标 |
|---|---|---|---|---|
| `competition_flat` | 只含平地的地块生成器 | 基座 16 项 | 无 | 基座 1 项 |
| `competition_rough` | 族级竞赛课程（障碍释放） | 越障 24 项 | 自适应 x / y / yaw | 附加诊断表 |

奖励项的**存在性**由 profile 的权重表决定（键集合即项集合）—— 源实现里两档互相 pop 的
那一串项，在这里就是"该档的权重表没给这一项"，不会出现"结构里写了却静默不生效"。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs import mdp as envs_mdp
from mjlab.envs.mdp import dr as envs_dr
from mjlab.managers.command_manager import CommandTermCfg
from mjlab.managers.curriculum_manager import CurriculumTermCfg
from mjlab.managers.event_manager import EventTermCfg
from mjlab.managers.metrics_manager import MetricsTermCfg
from mjlab.managers.observation_manager import ObservationGroupCfg, ObservationTermCfg
from mjlab.managers.reward_manager import RewardTermCfg
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.managers.termination_manager import TerminationTermCfg
from mjlab.scene import SceneCfg
from mjlab.sensor import (
    ContactMatch,
    ContactSensorCfg,
    GridPatternCfg,
    ObjRef,
    RayCastSensorCfg,
)
from mjlab.sim import MujocoCfg, SimulationCfg
from mjlab.tasks.velocity import mdp as velocity_mdp
from mjlab.terrains import BoxFlatTerrainCfg, TerrainEntityCfg, TerrainGeneratorCfg
from mjlab.utils.noise import UniformNoiseCfg as Unoise
from mjlab.viewer import ViewerConfig

from ...traversal_env_cfg import (
    make_obstacle_course_terrain,
    make_obstacle_release_curriculum,
)
from .. import family as family_roles
from ..binding import WheelLegSkillBinding
from .profile import CompetitionVelocityProfile

VARIANTS: tuple[str, ...] = ("competition_flat", "competition_rough")
#: 两档的具名分支（越障档 = 基座上叠越障地形/课程/表）。
_FLAT = "competition_flat"
_ROUGH = "competition_rough"

#: 命令项名（策略输入里的命令槽；机型侧的课程/指标按名取它）。
COMMAND_NAME = "twist"
#: 动作项名（策略动作接口两段，顺序即接口序；机型侧诊断按名取动作项）。
LEG_ACTION_NAME = "leg_joint_pos"
WHEEL_ACTION_NAME = "wheel_joint_vel"
#: 传感器名（族的奖励核按名取传感器；族内统一，不随机型变）。
FEET_GROUND_SENSOR = "feet_ground_contact"
BASE_GROUND_SENSOR = "base_ground_contact"
BODY_COLLISION_SENSOR = "body_collision"
HEIGHT_SCAN_SENSOR = "height_scanner"

#: viewer 三元组（竞赛配方口径：机身边框 3 m、俯角 -20°、方位 45°；body 走绑定）。
VIEWER_DISTANCE = 3.0
VIEWER_ELEVATION = -20.0
VIEWER_AZIMUTH = 45.0
#: play 口径的固定小场（与另两份配方同口径：关课程、缩成 5×5、边框 10 m）。
_PLAY_TERRAIN_COLS = 5
_PLAY_TERRAIN_ROWS = 5
_PLAY_TERRAIN_BORDER = 10.0
#: play 档的"无限时长"（分钟级长跑用 int 秒；与源实现的 `int(1e9)` 同值）。
_PLAY_EPISODE_LENGTH_S = int(1e9)


def _leg_role_pattern(
    binding: WheelLegSkillBinding, leg: str, roles: Sequence[str]
) -> str:
    """`<腿>_[<角色…>_]<尾段>`：该腿这些角色的关节模式（源实现的字面正则同串）。

    角色词与尾段都从契约关节名派生：取该腿这些角色的**完整尾段**（`role_suffix`，
    如 `hip_pitch_joint` / `knee_joint`），抽公共尾段（`_joint`）后压成
    `fl_(hip_pitch|knee)_joint`；单角色时不加括号（`fl_hip_abduction_joint`）。
    尾段不齐时退回逐名列出 —— 同角色同尾段是族约定，退路只为不静默错拼。
    """
    wanted = {binding.family_role(role) for role in roles}
    suffixes: list[str] = []
    for joint in binding.action_joint_order:
        if family_roles.leg_of_joint(joint, binding.leg_ids) != leg:
            continue
        role = family_roles.role_of_joint(joint, binding.family_id)
        if role is None or binding.family_role(role) not in wanted:
            continue
        suffixes.append(family_roles.role_suffix(joint, binding.leg_ids))
    if not suffixes:
        raise ValueError(
            f"{binding.robot_id}: 腿 {leg!r} 在这些角色 {tuple(roles)} 下没有关节 —— 镜像对无法派生"
        )
    if len(suffixes) == 1:
        return f"{leg}_{suffixes[0]}"
    # 公共尾段：从尾部逐 token 比，全部相同才留下（`hip_pitch_joint`/`knee_joint` → `_joint`）。
    parts = [suffix.split("_") for suffix in suffixes]
    tail: list[str] = []
    for token in zip(*[reversed(p) for p in parts]):
        if len(set(token)) != 1:
            break
        tail.append(token[0])
    if not tail:
        return f"{leg}_({'|'.join(suffixes)})"
    suffix_tail = "_" + "_".join(reversed(tail))
    heads = [suffix[: -len(suffix_tail)] for suffix in suffixes]
    return f"{leg}_({'|'.join(heads)}){suffix_tail}"


def _mirror_patterns(
    binding: WheelLegSkillBinding,
    leg_pairs: Sequence[tuple[int, int]],
    roles: Sequence[str],
) -> list[list[str]]:
    """镜像关节对 → 源实现口径的两串关节模式（配对来自 profile 的腿序索引）。"""
    return [
        [
            _leg_role_pattern(binding, binding.leg_ids[first], roles),
            _leg_role_pattern(binding, binding.leg_ids[second], roles),
        ]
        for first, second in leg_pairs
    ]


def _segment_scale(binding: WheelLegSkillBinding, joints: Sequence[str]):
    """动作段的缩放：逐关节同值 ⇒ 标量，否则逐关节表（解析结果与源字面表相同）。"""
    values = {joint: float(binding.action_scales[joint]) for joint in joints}
    if len(set(values.values())) == 1:
        return next(iter(values.values()))
    return values


# ------------------------------------------------------------------------------
# 装配：动作 / 基座地形 / 传感器 / 观测 / 命令 / 事件 / 奖励 / 终止 / 课程 / 指标
# ------------------------------------------------------------------------------


def _apply_actions(
    binding: WheelLegSkillBinding, profile: CompetitionVelocityProfile
) -> dict[str, object]:
    """腿段（位置，默认姿偏移）+ 轮段（速度，零偏移）；两段都带延时与一阶低通。

    动作项类由 profile 注入（机型实现），关节名与缩放来自绑定（契约真值）。两段的
    `actuator_names` 是**契约字面名**：接口序因此可逐项核对（= 契约 `action.joint_order`）。
    """
    leg, wheel = profile.leg_action, profile.wheel_action
    return {
        LEG_ACTION_NAME: profile.position_action_cls(
            entity_name="robot",
            actuator_names=tuple(binding.leg_joint_order),
            scale=_segment_scale(binding, binding.leg_joint_order),
            use_default_offset=True,
            control_frequency=leg.control_frequency,
            cut_off_frequency=leg.cut_off_frequency,
            min_delay=leg.min_delay,
            max_delay=leg.max_delay,
        ),
        WHEEL_ACTION_NAME: profile.velocity_action_cls(
            entity_name="robot",
            actuator_names=tuple(binding.wheel_joint_order),
            scale=_segment_scale(binding, binding.wheel_joint_order),
            offset=0.0,
            use_default_offset=False,
            control_frequency=wheel.control_frequency,
            cut_off_frequency=wheel.cut_off_frequency,
            min_delay=wheel.min_delay,
            max_delay=wheel.max_delay,
        ),
    }


def _flat_terrain(profile: CompetitionVelocityProfile) -> TerrainEntityCfg:
    """平地档地形：**只含平地**的地块生成器（地块尺寸/行列/边框来自 profile）。"""
    return TerrainEntityCfg(
        terrain_type="generator",
        terrain_generator=TerrainGeneratorCfg(
            size=tuple(profile.terrain_flat_tile_size),
            border_width=profile.terrain_flat_border_width,
            num_rows=profile.terrain_flat_num_rows,
            num_cols=profile.terrain_flat_num_cols,
            sub_terrains={"flat": BoxFlatTerrainCfg(proportion=1.0)},
        ),
    )


def _sensors(
    binding: WheelLegSkillBinding, profile: CompetitionVelocityProfile
) -> tuple[ContactSensorCfg, ...]:
    """四组传感器：轮-地接触（带 air time）、机身-地、机身碰撞监督、高度扫描。

    主匹配全部由声明派生：轮-地走族角色的轮别名（同一匹配集合），机身/扫描帧走绑定的
    根 body，碰撞监督的几何匹配是该机型的 link 命名事实（profile 给）。
    """
    feet_ground = ContactSensorCfg(
        name=FEET_GROUND_SENSOR,
        primary=ContactMatch(
            mode="body", pattern=binding.wheel_contact_pattern, entity="robot"
        ),
        secondary=ContactMatch(mode="body", pattern="terrain"),
        fields=("found", "force"),
        reduce="none",
        num_slots=1,
        history_length=3,
        track_air_time=True,
    )
    base_ground = ContactSensorCfg(
        name=BASE_GROUND_SENSOR,
        primary=ContactMatch(mode="body", pattern=binding.root_body, entity="robot"),
        secondary=ContactMatch(mode="body", pattern="terrain"),
        fields=("found",),
        reduce="none",
        num_slots=1,
        history_length=4,
    )
    body_collision = ContactSensorCfg(
        name=BODY_COLLISION_SENSOR,
        primary=ContactMatch(
            mode="body", pattern=tuple(profile.body_collision_patterns), entity="robot"
        ),
        secondary=ContactMatch(mode="body", pattern="terrain"),
        fields=("found", "force"),
        reduce="none",
        num_slots=1,
        history_length=4,
    )
    height_scan = RayCastSensorCfg(
        name=HEIGHT_SCAN_SENSOR,
        frame=ObjRef(type="body", name=binding.root_body, entity="robot"),
        pattern=GridPatternCfg(
            resolution=profile.height_scan_resolution,
            size=tuple(profile.height_scan_size),
        ),
        ray_alignment="yaw",
        max_distance=profile.height_scan_max_distance,
        exclude_parent_body=True,
        include_geom_groups=(0,),
        debug_vis=False,
    )
    return (feet_ground, base_ground, body_collision, height_scan)


def _observations(
    binding: WheelLegSkillBinding, profile: CompetitionVelocityProfile
) -> dict[str, ObservationGroupCfg]:
    """观测：actor 七项（腿 12 + 轮 4 分列，逐项自带缩放/噪声）；critic 再加三组特权项。

    腿/轮选择器来自绑定（契约序 ⇒ 观测里的关节序与动作序同源），数值来自 profile。
    """
    obs = profile.observations
    leg_cfg = binding.leg_joint_cfg()
    wheel_cfg = binding.wheel_joint_cfg()
    actor_terms = {
        "base_ang_vel": ObservationTermCfg(
            func=envs_mdp.base_ang_vel,
            scale=obs.base_ang_vel_scale,
            noise=Unoise(n_min=-obs.base_ang_vel_noise, n_max=obs.base_ang_vel_noise),
        ),
        "projected_gravity": ObservationTermCfg(
            func=velocity_mdp.projected_gravity,
            noise=Unoise(
                n_min=-obs.projected_gravity_noise, n_max=obs.projected_gravity_noise
            ),
        ),
        "command": ObservationTermCfg(
            func=velocity_mdp.generated_commands,
            params={"command_name": COMMAND_NAME},
        ),
        "joint_pos": ObservationTermCfg(
            func=envs_mdp.joint_pos_rel,
            params={"asset_cfg": leg_cfg},
            noise=Unoise(n_min=-obs.joint_pos_noise, n_max=obs.joint_pos_noise),
        ),
        "joint_vel": ObservationTermCfg(
            func=envs_mdp.joint_vel_rel,
            params={"asset_cfg": leg_cfg},
            scale=obs.joint_vel_scale,
            noise=Unoise(n_min=-obs.joint_vel_noise, n_max=obs.joint_vel_noise),
        ),
        "wheel_vel": ObservationTermCfg(
            func=envs_mdp.joint_vel_rel,
            params={"asset_cfg": wheel_cfg},
            scale=obs.wheel_vel_scale,
            noise=Unoise(n_min=-obs.wheel_vel_noise, n_max=obs.wheel_vel_noise),
        ),
        "actions": ObservationTermCfg(func=velocity_mdp.last_action),
    }
    critic_terms = {
        **actor_terms,
        "base_lin_vel": ObservationTermCfg(
            func=profile.terms.safe_base_lin_vel, scale=obs.critic_base_lin_vel_scale
        ),
        "foot_contact": ObservationTermCfg(
            func=profile.terms.safe_foot_contact,
            params={"sensor_name": FEET_GROUND_SENSOR},
        ),
        "height_scan": ObservationTermCfg(
            func=profile.terms.safe_height_scan,
            params={"sensor_name": HEIGHT_SCAN_SENSOR},
            clip=tuple(obs.height_scan_clip),
        ),
    }
    return {
        "actor": ObservationGroupCfg(
            terms=actor_terms, concatenate_terms=True, enable_corruption=True
        ),
        "critic": ObservationGroupCfg(
            terms=critic_terms, concatenate_terms=True, enable_corruption=False
        ),
    }


def _commands(profile: CompetitionVelocityProfile) -> dict[str, CommandTermCfg]:
    """阈值速度命令（命令类由 profile 注入；范围/朝向比/刚度来自 profile）。"""
    spec = profile.command
    command_cls = profile.command_cls
    return {
        COMMAND_NAME: command_cls(
            entity_name="robot",
            resampling_time_range=tuple(spec.resampling_time_range),
            rel_standing_envs=spec.rel_standing_envs,
            rel_heading_envs=spec.rel_heading_envs,
            heading_command=spec.heading_command,
            heading_control_stiffness=spec.heading_control_stiffness,
            rel_forward_envs=spec.rel_forward_envs,
            rel_lateral_envs=spec.rel_lateral_envs,
            rel_yaw_envs=spec.rel_yaw_envs,
            ranges=command_cls.Ranges(
                lin_vel_x=tuple(spec.ranges.lin_vel_x),
                lin_vel_y=tuple(spec.ranges.lin_vel_y),
                ang_vel_z=tuple(spec.ranges.ang_vel_z),
                heading=tuple(spec.heading_range),
            ),
        )
    }


def _events(
    binding: WheelLegSkillBinding, profile: CompetitionVelocityProfile
) -> dict[str, EventTermCfg]:
    """事件表：重置（机体/关节）、推扰、机身质心/摩擦/增益/质量随机化。

    数值全来自 profile 的事件档；`reset_joints` 只在给区间时建（平地档没有这一条）。
    机身段一律取绑定的根 body（源实现写死 `"base_link"`）。
    """
    spec = profile.events
    root = SceneEntityCfg("robot", body_names=(binding.root_body,))
    events = {
        "reset_scene": EventTermCfg(func=envs_mdp.reset_scene_to_default, mode="reset"),
        "reset_base": EventTermCfg(
            func=envs_mdp.reset_root_state_uniform,
            mode="reset",
            params={
                "pose_range": dict(spec.reset_pose_range),
                "velocity_range": dict(spec.reset_velocity_range),
                "asset_cfg": SceneEntityCfg("robot"),
            },
        ),
        "push_robot": EventTermCfg(
            func=envs_mdp.push_by_setting_velocity,
            mode="interval",
            interval_range_s=tuple(spec.push_interval_range_s),
            params={
                "velocity_range": dict(spec.push_velocity_range),
                "asset_cfg": SceneEntityCfg("robot"),
            },
        ),
        "base_com": EventTermCfg(
            func=envs_dr.body_com_offset,
            mode="startup",
            params={
                "asset_cfg": root,
                "operation": "add",
                "ranges": {
                    0: tuple(spec.com_offset_range),
                    1: tuple(spec.com_offset_range),
                    2: tuple(spec.com_offset_range),
                },
            },
        ),
        "body_friction": EventTermCfg(
            func=envs_dr.geom_friction,
            mode="startup",
            params={
                "asset_cfg": SceneEntityCfg("robot", geom_names=(".*",)),
                "operation": "abs",
                "ranges": tuple(spec.friction_range),
            },
        ),
        "actuator_stiffness": EventTermCfg(
            func=envs_dr.joint_stiffness,
            mode="startup",
            params={
                "asset_cfg": SceneEntityCfg("robot"),
                "ranges": tuple(spec.actuator_gain_scale_range),
                "operation": "scale",
                "distribution": "log_uniform",
            },
        ),
        "actuator_damping": EventTermCfg(
            func=envs_dr.joint_damping,
            mode="startup",
            params={
                "asset_cfg": SceneEntityCfg("robot"),
                "ranges": tuple(spec.actuator_gain_scale_range),
                "operation": "scale",
                "distribution": "log_uniform",
            },
        ),
        "body_mass_base": EventTermCfg(
            func=envs_dr.body_mass,
            mode="startup",
            params={
                "asset_cfg": root,
                "operation": "add",
                "ranges": tuple(spec.base_mass_range),
            },
        ),
    }
    if spec.reset_joints_position_range is not None:
        events["reset_joints"] = EventTermCfg(
            func=envs_mdp.reset_joints_by_offset,
            mode="reset",
            params={
                "position_range": tuple(spec.reset_joints_position_range),
                "velocity_range": (0.0, 0.0),
                "asset_cfg": SceneEntityCfg("robot", joint_names=(".*",)),
            },
        )
    return events


def _reward_builders(
    binding: WheelLegSkillBinding, profile: CompetitionVelocityProfile
) -> dict[str, Callable[[float], RewardTermCfg]]:
    """奖励表**结构**：项名 → 建项函数（权重作参数，来自该档的权重表）。

    核的来源分三类：族 Kit 的 mdp（`profile.terms` 注入的机型核）、框架 mdp
    （`mjlab.envs.mdp` / `mjlab.tasks.velocity.mdp`）。关节选择器一律来自绑定。
    """
    spec = profile.rewards
    terms = profile.terms
    leg_cfg = binding.leg_joint_cfg()
    wheel_cfg = binding.wheel_joint_cfg()
    robot_all = SceneEntityCfg("robot")
    robot_body = SceneEntityCfg("robot", body_names=(binding.root_body,))

    def tracking(func: Callable) -> Callable[[float], RewardTermCfg]:
        return lambda weight: RewardTermCfg(
            func=func,
            weight=weight,
            params={"std": spec.tracking_std, "command_name": COMMAND_NAME},
        )

    def joint_pos_penalty(roles: Sequence[str]):
        """姿态偏离惩罚（按族角色选关节；单角色用绑定的角色选择器）。"""
        asset_cfg = (
            binding.role_scene_entity_cfg(roles[0])
            if len(roles) == 1
            else _multi_role_cfg(binding, roles)
        )
        return lambda weight: RewardTermCfg(
            func=terms.joint_pos_penalty,
            weight=weight,
            params={
                "stand_still_scale": spec.joint_pos_penalty_stand_still_scale,
                "velocity_threshold": spec.joint_pos_penalty_velocity_threshold,
                "command_threshold": spec.command_threshold,
                "asset_cfg": asset_cfg,
                "command_name": COMMAND_NAME,
            },
        )

    return {
        # --- 基座表（平地档全用；越障档用其中一部分） ---------------------------
        "track_lin_vel": tracking(terms.track_linear_velocity),
        "track_ang_vel": tracking(terms.track_angular_velocity),
        "upright": lambda weight: RewardTermCfg(
            func=velocity_mdp.upright,
            weight=weight,
            params={"std": spec.upright_std, "asset_cfg": robot_body},
        ),
        "base_height_l2": lambda weight: RewardTermCfg(
            func=terms.base_height_l2,
            weight=weight,
            params={
                "target_height": spec.base_height_target,
                **(
                    {"sensor_cfg": SceneEntityCfg(HEIGHT_SCAN_SENSOR)}
                    if spec.base_height_uses_height_scan
                    else {}
                ),
            },
        ),
        "body_ang_vel": lambda weight: RewardTermCfg(
            func=velocity_mdp.body_angular_velocity_penalty,
            weight=weight,
            params={"asset_cfg": robot_body},
        ),
        "is_terminated": lambda weight: RewardTermCfg(
            func=envs_mdp.is_terminated, weight=weight
        ),
        "joint_torques": lambda weight: RewardTermCfg(
            func=envs_mdp.joint_torques_l2, weight=weight
        ),
        "joint_acc": lambda weight: RewardTermCfg(
            func=envs_mdp.joint_acc_l2, weight=weight
        ),
        "action_rate": lambda weight: RewardTermCfg(
            func=envs_mdp.action_rate_l2, weight=weight
        ),
        "joint_pos_limits": lambda weight: RewardTermCfg(
            func=envs_mdp.joint_pos_limits, weight=weight
        ),
        "wheel_roll_tracking": lambda weight: RewardTermCfg(
            func=terms.wheel_roll_tracking,
            weight=weight,
            params={
                "command_name": COMMAND_NAME,
                "wheel_radius": spec.wheel_radius,
                "wheel_track": spec.wheel_track,
                "std": spec.wheel_roll_tracking_std,
                "asset_cfg": wheel_cfg,
            },
        ),
        "wheel_contact_bonus": lambda weight: RewardTermCfg(
            func=terms.contact_fraction_reward,
            weight=weight,
            params={"sensor_name": FEET_GROUND_SENSOR},
        ),
        "feet_air_time": lambda weight: RewardTermCfg(
            func=velocity_mdp.feet_air_time,
            weight=weight,
            params={
                "sensor_name": FEET_GROUND_SENSOR,
                "threshold_min": spec.air_time_thresholds[0],
                "threshold_max": spec.air_time_thresholds[1],
                "command_name": COMMAND_NAME,
                "command_threshold": spec.air_time_velocity_threshold,
            },
        ),
        "leg_motion_penalty": lambda weight: RewardTermCfg(
            func=terms.adaptive_leg_motion_penalty,
            weight=weight,
            params={
                "command_name": COMMAND_NAME,
                "sensor_name": FEET_GROUND_SENSOR,
                "command_threshold": spec.leg_motion_command_threshold,
                "tilt_relax_start": spec.leg_motion_tilt_relax_start,
                "tilt_relax_end": spec.leg_motion_tilt_relax_end,
                "contact_target": spec.leg_motion_contact_target,
                "min_penalty_scale": spec.leg_motion_min_penalty_scale,
                "asset_cfg": leg_cfg,
            },
        ),
        "stand_still": lambda weight: RewardTermCfg(
            func=terms.stand_still,
            weight=weight,
            params={
                "command_name": COMMAND_NAME,
                "command_threshold": spec.command_threshold,
            },
        ),
        "body_collision": lambda weight: RewardTermCfg(
            func=velocity_mdp.self_collision_cost,
            weight=weight,
            params={"sensor_name": BODY_COLLISION_SENSOR},
        ),
        # --- 越障表专属项 ------------------------------------------------------
        "track_lin_vel_x_exp": tracking(terms.track_linear_velocity_x),
        "track_lin_vel_y_exp": tracking(terms.track_linear_velocity_y),
        "track_ang_vel_z_exp": tracking(terms.track_angular_velocity_z),
        "stair_lateral_yaw_drift": lambda weight: RewardTermCfg(
            func=terms.stair_lateral_yaw_drift_l2,
            weight=weight,
            params={
                "terrain_names": tuple(spec.drift_terrain_names),
                "y_scale": spec.drift_y_scale,
                "yaw_scale": spec.drift_yaw_scale,
                "asset_cfg": robot_all,
            },
        ),
        "lin_vel_z": lambda weight: RewardTermCfg(
            func=terms.lin_vel_z_l2, weight=weight
        ),
        "ang_vel_xy": lambda weight: RewardTermCfg(
            func=terms.ang_vel_xy_l2, weight=weight, params={"asset_cfg": robot_all}
        ),
        "joint_power": lambda weight: RewardTermCfg(
            func=terms.joint_power, weight=weight
        ),
        "leg_joint_acc_l2": lambda weight: RewardTermCfg(
            func=envs_mdp.joint_acc_l2, weight=weight, params={"asset_cfg": leg_cfg}
        ),
        "wheel_joint_acc_l2": lambda weight: RewardTermCfg(
            func=envs_mdp.joint_acc_l2, weight=weight, params={"asset_cfg": wheel_cfg}
        ),
        "joint_mirror": lambda weight: RewardTermCfg(
            func=terms.joint_mirror,
            weight=weight,
            params={
                "mirror_joints": _mirror_patterns(
                    binding, spec.mirror_leg_pairs, spec.mirror_roles
                ),
                "asset_cfg": robot_all,
            },
        ),
        "joint_pos_penalty_ab": joint_pos_penalty(("hip_abduction",)),
        "joint_pos_penalty_sagittal": joint_pos_penalty(("hip_pitch", "knee")),
        "abduction_mirror": lambda weight: RewardTermCfg(
            func=terms.joint_mirror,
            weight=weight,
            params={
                "mirror_joints": _mirror_patterns(
                    binding,
                    spec.abduction_mirror_leg_pairs,
                    (spec.abduction_mirror_role,),
                ),
                "asset_cfg": robot_all,
            },
        ),
        "feet_contact_without_cmd": lambda weight: RewardTermCfg(
            func=terms.feet_contact_without_cmd,
            weight=weight,
            params={
                "command_name": COMMAND_NAME,
                "sensor_name": FEET_GROUND_SENSOR,
            },
        ),
        "upward": lambda weight: RewardTermCfg(func=terms.upward, weight=weight),
        "undesired_contacts": lambda weight: RewardTermCfg(
            func=terms.undesired_contacts,
            weight=weight,
            params={
                "sensor_name": BODY_COLLISION_SENSOR,
                "threshold": spec.undesired_contacts_threshold,
            },
        ),
        "contact_forces": lambda weight: RewardTermCfg(
            func=terms.contact_forces,
            weight=weight,
            params={
                "sensor_name": FEET_GROUND_SENSOR,
                "threshold": spec.contact_forces_threshold,
            },
        ),
    }


def _multi_role_cfg(binding: WheelLegSkillBinding, roles: Sequence[str]) -> SceneEntityCfg:
    """多角色一组关节的选择器（腿段角色按动作序排，保序）。"""
    names: list[str] = []
    wanted = {binding.family_role(role) for role in roles}
    for joint in binding.action_joint_order:
        role = family_roles.role_of_joint(joint, binding.family_id)
        if role is not None and binding.family_role(role) in wanted:
            names.append(joint)
    if not names:
        raise ValueError(f"{binding.robot_id}: 角色 {tuple(roles)} 在动作序里没有关节")
    return SceneEntityCfg("robot", joint_names=tuple(names), preserve_order=True)


def _rewards(
    binding: WheelLegSkillBinding, profile: CompetitionVelocityProfile
) -> dict[str, RewardTermCfg]:
    """按该档的权重表装配奖励（键集合 = 项集合；权重表里的陌生名字判红）。"""
    weights = dict(profile.rewards.weights)
    builders = _reward_builders(binding, profile)
    unknown = sorted(set(weights) - set(builders))
    if unknown:
        raise ValueError(
            f"{binding.robot_id}: 奖励权重表里的 {unknown} 没有对应的结构定义（名字写错或结构缺项）"
        )
    return {
        name: build(float(weights[name]))
        for name, build in builders.items()
        if name in weights
    }


def _terminations(profile: CompetitionVelocityProfile) -> dict[str, TerminationTermCfg]:
    """终止表：超时 / 过倾 / 机身着地 / NaN（阈值来自 profile）。"""
    return {
        "time_out": TerminationTermCfg(func=envs_mdp.time_out, time_out=True),
        "bad_orientation": TerminationTermCfg(
            func=envs_mdp.bad_orientation,
            params={"limit_angle": profile.bad_orientation_limit_angle},
        ),
        "base_ground_contact": TerminationTermCfg(
            func=velocity_mdp.illegal_contact,
            params={"sensor_name": BASE_GROUND_SENSOR},
        ),
        "nan_detection": TerminationTermCfg(func=envs_mdp.nan_detection),
    }


def _curriculum(profile: CompetitionVelocityProfile, variant: str) -> dict[str, CurriculumTermCfg]:
    """平地档无课程；越障档 = 族级障碍释放课程 + profile 的逐轴自适应命令课程。"""
    if variant != _ROUGH:
        return {}
    curriculum: dict[str, CurriculumTermCfg] = {
        "terrain_levels": make_obstacle_release_curriculum(command_name=COMMAND_NAME)
    }
    for level in profile.command_levels:
        func = getattr(profile.terms, level.func_name)
        curriculum[level.term_name] = CurriculumTermCfg(
            func=func,
            params={
                "command_name": COMMAND_NAME,
                "reward_term_name": level.reward_term_name,
                "axis": level.axis,
                "initial_range": tuple(level.initial_range),
                "delta_command": level.delta_command,
                "target_ratio": level.target_ratio,
                "ema_alpha": level.ema_alpha,
            },
        )
    return curriculum


def _metrics(
    profile: CompetitionVelocityProfile, variant: str
) -> dict[str, MetricsTermCfg]:
    """指标：基座一项（框架的腿部动作加速度均值）+ 越障档的机型诊断表。"""
    metrics = {"mean_leg_action_acc": MetricsTermCfg(func=velocity_mdp.mean_action_acc)}
    if variant != _ROUGH:
        return metrics
    for name, metric in profile.extra_metrics:
        metrics[name] = MetricsTermCfg(
            func=getattr(profile.terms, metric.func_name), params=dict(metric.params)
        )
    return metrics


def _sim(profile: CompetitionVelocityProfile) -> SimulationCfg:
    """sim 档：数值来自 profile（越障档额外给接触传感器上限与 CCD 迭代）。"""
    spec = profile.sim
    mujoco = MujocoCfg(timestep=spec.timestep, impratio=spec.impratio, cone=spec.cone)
    if spec.ccd_iterations is not None:
        mujoco.ccd_iterations = int(spec.ccd_iterations)
    sim = SimulationCfg(mujoco=mujoco)
    if spec.contact_sensor_maxmatch is not None:
        sim.contact_sensor_maxmatch = int(spec.contact_sensor_maxmatch)
    return sim


def _base_env_cfg(
    binding: WheelLegSkillBinding, profile: CompetitionVelocityProfile, variant: str
) -> ManagerBasedRlEnvCfg:
    """基座装配（源实现 `_make_base_env_cfg` 的去机型化版 + 两档各自的表）。"""
    terrain = _flat_terrain(profile)
    if variant == _ROUGH:
        terrain = make_obstacle_course_terrain(
            max_init_terrain_level=profile.terrain_max_init_terrain_level
        )
    cfg = ManagerBasedRlEnvCfg(
        scene=SceneCfg(
            num_envs=profile.num_envs,
            env_spacing=profile.env_spacing,
            terrain=terrain,
            sensors=_sensors(binding, profile),
            entities={"robot": binding.robot_cfg()},
        ),
        commands=_commands(profile),
        actions=_apply_actions(binding, profile),
        observations=_observations(binding, profile),
        rewards=_rewards(binding, profile),
        terminations=_terminations(profile),
        events=_events(binding, profile),
        metrics=_metrics(profile, variant),
        curriculum=_curriculum(profile, variant),
        decimation=profile.decimation,
        episode_length_s=profile.episode_length_s,
        sim=_sim(profile),
        viewer=ViewerConfig(
            body_name=binding.root_body,
            distance=VIEWER_DISTANCE,
            elevation=VIEWER_ELEVATION,
            azimuth=VIEWER_AZIMUTH,
        ),
    )
    if profile.seed is not None:
        cfg.seed = int(profile.seed)
    if variant == _ROUGH:
        # 场景并行数与间距在越障地形上必须与 scene 一致（源实现在这里显式对齐）。
        cfg.scene.terrain.num_envs = cfg.scene.num_envs
        cfg.scene.terrain.env_spacing = cfg.scene.env_spacing
    return cfg


def _apply_play(cfg: ManagerBasedRlEnvCfg, variant: str) -> None:
    """play 口径：无限时长、关观测噪声、去推扰、清课程；越障档把生成器退成固定小场。"""
    cfg.episode_length_s = _PLAY_EPISODE_LENGTH_S
    cfg.observations["actor"].enable_corruption = False
    cfg.events.pop("push_robot", None)
    cfg.curriculum = {}
    terrain = cfg.scene.terrain
    generator = terrain.terrain_generator if terrain is not None else None
    if variant == _ROUGH and generator is not None:
        generator.curriculum = False
        generator.num_cols = _PLAY_TERRAIN_COLS
        generator.num_rows = _PLAY_TERRAIN_ROWS
        generator.border_width = _PLAY_TERRAIN_BORDER


def make_env_cfg(
    binding: WheelLegSkillBinding,
    profile: CompetitionVelocityProfile,
    *,
    variant: str = _ROUGH,
    play: bool = False,
) -> ManagerBasedRlEnvCfg:
    """装配竞赛配方的环境（平地 / 越障同一份实现，数值全在 profile）。

    Args:
        binding: 该机型的绑定（契约 + MJCF 派生；见 `../binding.py`）。
        profile: 该机型该档的竞赛配方数据（见 `profile.CompetitionVelocityProfile`）。
        variant: `competition_flat` | `competition_rough`。
        play: 播放口径（无限时长、关噪声、去推扰、清课程）。
    """
    if variant not in VARIANTS:
        raise ValueError(f"未知变体 {variant!r}（竞赛配方只认 {VARIANTS}）")
    if not isinstance(binding, WheelLegSkillBinding):
        raise TypeError(f"binding 必须是 WheelLegSkillBinding，收到 {type(binding).__name__}")
    if not isinstance(profile, CompetitionVelocityProfile):
        raise TypeError(
            f"profile 必须是 CompetitionVelocityProfile，收到 {type(profile).__name__}"
        )
    if profile.setup_hook is not None:
        # 机型侧全局开关（如 HIMLoco 式"总奖励裁剪到 ≥0"）：源实现在建 cfg 之前调用，
        # 且是**幂等**的进程级开关 —— 装配时机保持一致。
        profile.setup_hook()
    cfg = _base_env_cfg(binding, profile, variant)
    if play:
        _apply_play(cfg, variant)
    return cfg


__all__: tuple[str, ...] = (
    "COMMAND_NAME",
    "LEG_ACTION_NAME",
    "VARIANTS",
    "WHEEL_ACTION_NAME",
    "make_env_cfg",
)
