"""Velocity 技能的族级环境工厂。

来源：`assets/robots/unitree_go2/training/source/local_tasks/robots/unitree/go2/tasks/locomotion/velocity.py`
（mjlab 公共 velocity 基座 + 该机型的逐项定制）。除下列去机型化改动外逐项同构：

* **足端几何 / 足端 site / 腿杆与躯干碰撞几何**：从契约与 MJCF 清单派生（`binding.foot_geoms`、
  `binding.foot_sites()`、`binding.collision_geoms_for_role()`、`binding.trunk_collision_pattern()`），
  不再写 `<腿>_<角色>_collision` 字面量 —— 小腿几何个数（go2 = calf1+calf2）由清单决定；
* **关节序与动作缩放**：`kits/joint_actions.build_joint_actions`（契约关节序 + 字面名 +
  `preserve_order`；缩放 = 契约角色缩放 × 机型实体执行器谱 `effort/stiffness`）；
* **`pose` std 表**：按**族角色**成键（profile 提供取值，`binding.family_role` + 角色关节正则成键）；
* **根 body 引用**（`terrain_scan` 帧、`self_collision` 子树、`base_com`、`upright`、
  `body_ang_vel`、viewer）→ `binding.root_body`；
* **机型实体**：沿用机型自己的基座实体（`binding.base_entity_cfg()`，PD 谱/初始姿由机型包声明）——
  源配方的 velocity 实体就是该机型基座实体本身，技能层不覆盖它；
* **任务数值**（命令/地形/DR/奖励权重/终止阈值/play 覆盖）→ `VelocityProfile`。

留在本模块的是**族级机制**：sim 上限、传感器字段表（found+force / reduce / slots / history）、
foot height scan 的 ring 参数、viewer 三元组、三个基座奖励项的静音位 —— 四足族各机型同值。
"""

from __future__ import annotations

import math
from typing import Literal

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs import mdp as envs_mdp
from mjlab.envs.mdp import dr
from mjlab.managers import (
    EventTermCfg,
    RewardTermCfg,
    SceneEntityCfg,
    TerminationTermCfg,
)
from mjlab.sensor import (
    ContactMatch,
    ContactSensorCfg,
    ObjRef,
    RayCastSensorCfg,
    RingPatternCfg,
    TerrainHeightSensorCfg,
)
from mjlab.tasks.velocity import mdp as velocity_mdp
from mjlab.tasks.velocity.mdp import UniformVelocityCommandCfg
from mjlab.tasks.velocity.velocity_env_cfg import make_velocity_env_cfg
from mjlab.utils.noise.noise_cfg import UniformNoiseCfg

from ....joint_actions import build_joint_actions
from ... import apply_flat_postlude, apply_play_postlude
from ..binding import QuadrupedSkillBinding
from ..mdp import rewards as shared_rewards
from .profile import VelocityProfile

TerrainProfile = Literal["rough", "flat"]

#: 基座传感器名（族级技能统一常量；奖励/终止/观测按名引用）。
TERRAIN_SCAN = "terrain_scan"
FOOT_HEIGHT_SCAN = "foot_height_scan"
FEET_SENSOR = "feet_ground_contact"
SELF_COLLISION_SENSOR = "self_collision"
THIGH_SENSOR = "thigh_ground_touch"
SHANK_SENSOR = "shank_ground_touch"
TRUNK_SENSOR = "trunk_ground_touch"

#: 平地档要撤掉"只有 rough 才消费"的传感器（与源实现同一份名单）。
_FLAT_DROPPED_SENSORS = (
    TERRAIN_SCAN,
    SELF_COLLISION_SENSOR,
    THIGH_SENSOR,
    SHANK_SENSOR,
    TRUNK_SENSOR,
)


def _repoint_terrain_scan(cfg: ManagerBasedRlEnvCfg, binding: QuadrupedSkillBinding) -> None:
    for sensor in cfg.scene.sensors or ():
        if sensor.name == TERRAIN_SCAN:
            assert isinstance(sensor, RayCastSensorCfg)
            assert isinstance(sensor.frame, ObjRef)
            sensor.frame.name = binding.root_body


def _wire_foot_height_scan(
    cfg: ManagerBasedRlEnvCfg, binding: QuadrupedSkillBinding
) -> None:
    """足端高度扫描挂到本机型的**足端帧**（绑定按能力给：优先 site，其次足端 body）。

    帧的两种口径都由 `binding.foot_scan_frames()` 表达（数据，不是 Kit 里的机型判断）：

    * go2 这类有足端 site 的机型 → `("site", "FL")` 一类的帧（与源实现逐项同构）；
    * **lite3 这类没有足端 site、足端是 `*_FOOT` body** 的机型 → `("body", "FL_FOOT")`
      帧（B31 裁决：射线原点仍在足端，语义不变；源配方即如此装配）；
    * **一台足端帧都没有的机型**（go1 的足端就是 calf 体：既无 site 也无
      `*_foot*` body）→ 不装配这一传感器。足端**site** 版奖励与三项足端观测另按
      `has_foot_sites()` 撤掉（`_drop_site_dependent_items`；lite3 这类"无 site、有
      body 帧"的机型由机型配方的观测/奖励整表接管，不受影响）—— 不静默换口径、
      也不判死整个技能。
    """
    frames = binding.foot_scan_frames()
    if not frames:
        cfg.scene.sensors = tuple(
            sensor
            for sensor in (cfg.scene.sensors or ())
            if sensor.name != FOOT_HEIGHT_SCAN
        )
        return
    for sensor in cfg.scene.sensors or ():
        if sensor.name == FOOT_HEIGHT_SCAN:
            assert isinstance(sensor, TerrainHeightSensorCfg)
            sensor.frame = tuple(
                ObjRef(type=kind, name=name, entity="robot") for kind, name in frames
            )
            sensor.pattern = RingPatternCfg.single_ring(radius=0.04, num_samples=4)


def _drop_site_dependent_items(cfg: ManagerBasedRlEnvCfg) -> None:
    """撤掉**依赖足端 site** 的项（能力缺口机型）：四项足端奖励 + 三项足端观测。

    与 go1 现行的处置逐项同构（`go1_velocity.env_cfg::_configure_rewards` 的四项与
    `_restructure_actor_obs` 的三项）：go1 的足端就是 calf 体、没有专用 site，
    这些项在它身上不成立。判据是**绑定能力**（`binding.has_foot_sites()`），
    不是机型名。
    """
    for name in ("foot_clearance", "foot_swing_height", "soft_landing", "foot_slip"):
        cfg.rewards.pop(name, None)
    for group in ("actor", "critic"):
        terms = cfg.observations[group].terms
        for name in ("foot_height", "foot_air_time", "foot_contact"):
            terms.pop(name, None)


def _contact_sensors(
    binding: QuadrupedSkillBinding, profile: VelocityProfile
) -> tuple[ContactSensorCfg, ...]:
    """足端接触传感器 + 族级**接触监看块**（rough 档的四组：自碰撞 / 大腿 / 小腿 / 躯干）。

    腿杆传感器按**族角色**选（髋以外的那两根：hip_pitch / knee），几何名由绑定按本机型
    的契约角色词与 MJCF 清单派生 —— 换机型不需要改这里。

    `profile.contact_supervision=False` 时只装配足端传感器：机型自备那四组的判据
    （传感器表 / 终止 / 摩擦事件与它配套），Kit 不替它装配（见 `VelocityProfile` 注释）。
    """
    terrain = ContactMatch(mode="body", pattern="terrain")
    sensors: tuple[ContactSensorCfg, ...] = (
        ContactSensorCfg(
            name=FEET_SENSOR,
            primary=ContactMatch(mode="geom", pattern=binding.foot_geoms, entity="robot"),
            secondary=terrain,
            fields=("found", "force"),
            reduce="netforce",
            num_slots=1,
            track_air_time=True,
        ),
    )
    if not profile.contact_supervision:
        return sensors
    return sensors + (
        ContactSensorCfg(
            name=SELF_COLLISION_SENSOR,
            primary=ContactMatch(mode="subtree", pattern=binding.root_body, entity="robot"),
            secondary=ContactMatch(mode="subtree", pattern=binding.root_body, entity="robot"),
            fields=("found", "force"),
            reduce="none",
            num_slots=1,
            history_length=4,
        ),
    ) + supervision_sensors(binding)


def supervision_sensors(binding: QuadrupedSkillBinding) -> tuple[ContactSensorCfg, ...]:
    """族级接触监看块的三条腿杆/躯干传感器（按**几何名**派生）。

    与 `ensure_contact_supervision` 配套：算法变体档按名引用这三条，故即使基座 profile
    关闭了族级接触监看（`contact_supervision=False`），变体装配也会把它们补上。
    """
    terrain = ContactMatch(mode="body", pattern="terrain")
    return (
        _ground_touch_sensor(
            binding, THIGH_SENSOR, _role_for_ground_touch(binding, "hip_pitch"), terrain
        ),
        _ground_touch_sensor(
            binding, SHANK_SENSOR, _role_for_ground_touch(binding, "knee"), terrain
        ),
        ContactSensorCfg(
            name=TRUNK_SENSOR,
            primary=ContactMatch(
                mode="geom", entity="robot", pattern=binding.trunk_collision_pattern()
            ),
            secondary=terrain,
            fields=("found", "force"),
            reduce="none",
            num_slots=1,
            history_length=4,
        ),
    )


def ensure_contact_supervision(
    cfg: ManagerBasedRlEnvCfg, binding: QuadrupedSkillBinding
) -> None:
    """确保三条腿杆/躯干触地传感器在场（缺哪条补哪条，已在场的原样不动）。

    `ensure_supervision_bodies` 的几何名版本；两种口径都从绑定派生词干，
    只有"资产的碰撞几何有没有名字"这一条资产事实不同。
    """
    names = {sensor.name for sensor in (cfg.scene.sensors or ())}
    missing = tuple(
        sensor for sensor in supervision_sensors(binding) if sensor.name not in names
    )
    if missing:
        cfg.scene.sensors = tuple(cfg.scene.sensors or ()) + missing


def ensure_supervision_bodies(
    cfg: ManagerBasedRlEnvCfg, binding: QuadrupedSkillBinding
) -> None:
    """同 `ensure_contact_supervision`，但按 **body 名**匹配（几何未命名的资产）。

    语义相同（"这些腿杆/躯干与地形的接触"），差别只在资产命名：家族 MJCF 约定要求
    可碰撞几何名以 `_collision` 结尾，几何未命名的机型（碰撞几何由 `CollisionCfg`
    在实体构建期重建）只能按 body 匹配。词干仍从绑定派生（`<腿>_<角色>` / 根 body）。
    """
    terrain = ContactMatch(mode="body", pattern="terrain")
    sensors: tuple[ContactSensorCfg, ...] = (
        ContactSensorCfg(
            name=THIGH_SENSOR,
            primary=ContactMatch(
                mode="body",
                entity="robot",
                pattern=binding.leg_link_body_pattern("hip_pitch"),
            ),
            secondary=terrain,
            fields=("found", "force"),
            reduce="none",
            num_slots=1,
            history_length=4,
        ),
        ContactSensorCfg(
            name=SHANK_SENSOR,
            primary=ContactMatch(
                mode="body",
                entity="robot",
                pattern=binding.leg_link_body_pattern("knee"),
            ),
            secondary=terrain,
            fields=("found", "force"),
            reduce="none",
            num_slots=1,
            history_length=4,
        ),
        ContactSensorCfg(
            name=TRUNK_SENSOR,
            primary=ContactMatch(mode="body", entity="robot", pattern=binding.root_body),
            secondary=terrain,
            fields=("found", "force"),
            reduce="none",
            num_slots=1,
            history_length=4,
        ),
    )
    names = {sensor.name for sensor in (cfg.scene.sensors or ())}
    missing = tuple(sensor for sensor in sensors if sensor.name not in names)
    if missing:
        cfg.scene.sensors = tuple(cfg.scene.sensors or ()) + missing


def _ground_touch_sensor(
    binding: QuadrupedSkillBinding,
    name: str,
    contract_role: str,
    terrain: ContactMatch,
) -> ContactSensorCfg:
    return ContactSensorCfg(
        name=name,
        primary=ContactMatch(
            mode="geom",
            entity="robot",
            pattern=binding.collision_geoms_for_role(contract_role),
        ),
        secondary=terrain,
        fields=("found", "force"),
        reduce="none",
        num_slots=1,
        history_length=4,
    )


def _role_for_ground_touch(binding: QuadrupedSkillBinding, family_role: str) -> str:
    """族角色 → 该机型契约里的角色词（传感器取几何名要用本机型的词表）。"""
    for role in binding.leg_pattern:
        if binding.family_role(role) == family_role:
            return role
    raise ValueError(
        f"{binding.robot_id}: 契约 leg_pattern {binding.leg_pattern} 里找不到族角色 {family_role!r}"
        "（腿杆触地传感器按族角色装配：髋以外的那两根）"
    )


def _action_scale_table(
    binding: QuadrupedSkillBinding, profile: VelocityProfile
) -> dict[str, float]:
    """逐关节动作缩放：契约角色缩放 × 实体执行器谱；profile 的按角色口径优先。

    契约 `action_scale` 的口径在某机型上可能不是"归一化值"（go1 / b2 的源配方声明的是
    实际缩放，见 `VelocityProfile.action_scale_by_role`）——此时 profile 给值，Kit 只做
    "族角色 → 本机型关节名"的翻译，不含任何机型判断。
    """
    derived = binding.action_scale_by_joint()
    if not profile.action_scale_by_role:
        return derived
    table: dict[str, float] = {}
    for joint, value in derived.items():
        role = binding.family_role(binding.contract_role_of_joint(joint))
        table[joint] = float(profile.action_scale_by_role.get(role, value))
    return table


def _configure_events(
    cfg: ManagerBasedRlEnvCfg, binding: QuadrupedSkillBinding, profile: VelocityProfile
) -> None:
    """足端摩擦按轴随机化 + 基座质心随机化的机型侧接线（名/值分别来自绑定与 profile）。

    `profile.contact_supervision=False` 时**不动**足端摩擦事件（基座的单项
    `foot_friction` 原样留着）——机型自己的源配方口径（go1 的单项事件 / b2 的撤项）
    由机型 recipe 负责，Kit 不替它决定。
    """
    if profile.contact_supervision:
        geom_names = binding.foot_geoms
        # 基座 foot_friction 是单轴口径；源配方按 condim=6 的三轴分别在启动期随机化。
        cfg.events.pop("foot_friction", None)
        cfg.events["foot_friction_slide"] = EventTermCfg(
            mode="startup",
            func=dr.geom_friction,
            params={
                "asset_cfg": SceneEntityCfg("robot", geom_names=geom_names),
                "operation": "abs",
                "axes": [0],
                "ranges": profile.foot_friction_slide,
                "shared_random": True,
            },
        )
        cfg.events["foot_friction_spin"] = EventTermCfg(
            mode="startup",
            func=dr.geom_friction,
            params={
                "asset_cfg": SceneEntityCfg("robot", geom_names=geom_names),
                "operation": "abs",
                "distribution": "log_uniform",
                "axes": [1],
                "ranges": profile.foot_friction_spin,
                "shared_random": True,
            },
        )
        cfg.events["foot_friction_roll"] = EventTermCfg(
            mode="startup",
            func=dr.geom_friction,
            params={
                "asset_cfg": SceneEntityCfg("robot", geom_names=geom_names),
                "operation": "abs",
                "distribution": "log_uniform",
                "axes": [2],
                "ranges": profile.foot_friction_roll,
                "shared_random": True,
            },
        )
    cfg.events["base_com"].params["asset_cfg"].body_names = (binding.root_body,)


def _role_std_table(
    binding: QuadrupedSkillBinding, table: dict[str, float]
) -> dict[str, float]:
    """族角色 → 关节名正则的 std 表（同角色各腿同尾段 ⇒ `.*_<尾段>`，否则并列全名）。"""
    resolved: dict[str, float] = {}
    for role in binding.leg_pattern:
        family_role = binding.family_role(role)
        if family_role not in table:
            raise KeyError(
                f"{binding.robot_id}: profile 的 std 表缺族角色 {family_role!r}"
                f"（契约角色 {role!r} 映射得到）—— 表内：{sorted(table)}"
            )
        patterns = binding.role_joint_pattern(family_role)
        key = patterns[0] if len(patterns) == 1 else "(?:" + "|".join(patterns) + ")"
        resolved[key] = float(table[family_role])
    return resolved


def _configure_posture(
    cfg: ManagerBasedRlEnvCfg, binding: QuadrupedSkillBinding, profile: VelocityProfile
) -> None:
    cfg.rewards["pose"].params["std_standing"] = _role_std_table(
        binding, dict(profile.pose_std_standing)
    )
    moving = _role_std_table(binding, dict(profile.pose_std_moving))
    cfg.rewards["pose"].params["std_walking"] = dict(moving)
    cfg.rewards["pose"].params["std_running"] = dict(moving)


def _configure_rewards(
    cfg: ManagerBasedRlEnvCfg, binding: QuadrupedSkillBinding, profile: VelocityProfile
) -> None:
    cfg.rewards["upright"].params["asset_cfg"].body_names = (binding.root_body,)
    cfg.rewards["upright"].params["terrain_sensor_names"] = (TERRAIN_SCAN,)
    cfg.rewards["body_ang_vel"].params["asset_cfg"].body_names = (binding.root_body,)
    if binding.has_foot_sites():
        for reward_name in ("foot_clearance", "foot_slip"):
            cfg.rewards[reward_name].params["asset_cfg"].site_names = binding.foot_sites()
    else:
        # 能力缺口机型：四项依赖足端 site 的奖励整项撤销（不是静默改成别的口径）。
        _drop_site_dependent_items(cfg)

    # 源配方的奖励契约里没有这三项（静音，不是删除：日志/清单仍可见）。
    cfg.rewards["body_ang_vel"].weight = profile.body_ang_vel_weight
    cfg.rewards["angular_momentum"].weight = profile.angular_momentum_weight
    cfg.rewards["air_time"].weight = profile.air_time_weight

    # 根因修复（2026-09-28，量纲校准轮）：奖励经济学的"站着不动是优势策略"。
    # lainlab trot 拿不到白站的分靠两道闸：track 核带 gait 门控（不迈步不给分）+
    # stand_still 罚；通用 velocity 没有 gait 门（步态是 trot 特有概念），故补
    # stand_still 罚（命令幅值 > 0.1 时按关节与默认姿偏差之和惩罚，lainlab trot
    # 同款）——自产配方此前缺它，"站得住不走"成为优势策略（自产产物
    # motion=0.003 实证）。σ 用 profile.track_sigma（族默认 = 基座语义不变）。
    cfg.rewards["track_linear_velocity"].params["std"] = profile.track_sigma
    cfg.rewards["track_angular_velocity"].params["std"] = profile.track_sigma
    if profile.stand_still_weight is not None:
        cfg.rewards["stand_still"] = RewardTermCfg(
            func=shared_rewards.stand_still_penalty,
            weight=profile.stand_still_weight,
            params={"command_name": "twist"},
        )

    # 按身体分组的碰撞惩罚（只进 rough 档；机型自备接触监看块时不装配）。
    if profile.contact_supervision:
        cfg.rewards["self_collisions"] = RewardTermCfg(
            func=velocity_mdp.self_collision_cost,
            weight=profile.collision_penalty_weight,
            params={"sensor_name": SELF_COLLISION_SENSOR},
        )
        cfg.rewards["shank_collision"] = RewardTermCfg(
            func=velocity_mdp.self_collision_cost,
            weight=profile.collision_penalty_weight,
            params={"sensor_name": SHANK_SENSOR},
        )
        cfg.rewards["trunk_head_collision"] = RewardTermCfg(
            func=velocity_mdp.self_collision_cost,
            weight=profile.collision_penalty_weight,
            params={"sensor_name": TRUNK_SENSOR},
        )
    if profile.dof_power_weight is not None:
        cfg.rewards["dof_power_abs"] = RewardTermCfg(
            func=shared_rewards.dof_power_penalty,
            weight=profile.dof_power_weight,
            params={
                "asset_cfg": SceneEntityCfg("robot"),
                "kernel": profile.dof_power_kernel,
            },
        )


def make_env_cfg(
    binding: QuadrupedSkillBinding,
    profile: VelocityProfile,
    *,
    terrain_profile: TerrainProfile,
    play: bool = False,
) -> ManagerBasedRlEnvCfg:
    """Build the family velocity task from its source implementation."""
    if terrain_profile not in ("rough", "flat"):
        raise ValueError(f"未知地形档 {terrain_profile!r}（族级 velocity 只装配 rough / flat）")
    cfg = make_velocity_env_cfg()

    cfg.sim.mujoco.ccd_iterations = 500
    if profile.mujoco_solver_tuning:
        cfg.sim.mujoco.impratio = 10
        cfg.sim.mujoco.cone = "elliptic"
    cfg.sim.contact_sensor_maxmatch = 500
    if profile.contact_sensor_headroom:
        cfg.sim.nconmax = None  # full-body contact sensors need headroom

    cfg.scene.entities = {"robot": binding.base_entity_cfg()}

    _repoint_terrain_scan(cfg, binding)
    _wire_foot_height_scan(cfg, binding)
    cfg.scene.sensors = (cfg.scene.sensors or ()) + _contact_sensors(binding, profile)

    if cfg.scene.terrain is not None and cfg.scene.terrain.terrain_generator is not None:
        cfg.scene.terrain.terrain_generator.curriculum = profile.terrain_curriculum

    cfg.actions = build_joint_actions(
        joint_order=binding.joint_order,
        control_modes=binding.control_modes(),
        scale=_action_scale_table(binding, profile),
        term_names=("joint_pos",),
    )
    cfg.episode_length_s = profile.episode_length_s

    cfg.viewer.body_name = binding.root_body
    cfg.viewer.distance = 1.5
    cfg.viewer.elevation = -10.0

    _configure_events(cfg, binding, profile)
    _configure_posture(cfg, binding, profile)
    _configure_rewards(cfg, binding, profile)

    # 源实现：rough 档不按朝向单独终止（地形上倾斜是常态，交给越界终止）。
    cfg.terminations.pop("fell_over", None)
    if profile.contact_supervision:
        cfg.terminations["illegal_contact"] = TerminationTermCfg(
            func=velocity_mdp.illegal_contact,
            params={"sensor_name": THIGH_SENSOR},
        )

    if terrain_profile == "flat":
        _apply_flat_branch(cfg, profile)

    if play:
        _apply_play_branch(cfg, profile, terrain_profile=terrain_profile)

    # 机型侧任务配方（观测布局 / 奖励表 / 传感器表 / 终止 / 事件 / 命令 / 地形子项）：
    # 族级装配全部完成之后调用，机型配方的最后一句 —— 族级默认配方的机型传 None。
    if profile.recipe is not None:
        profile.recipe(
            cfg, binding, profile, terrain_profile=terrain_profile, play=play
        )
    return cfg


def _apply_flat_branch(cfg: ManagerBasedRlEnvCfg, profile: VelocityProfile) -> None:
    """flat 档：公共平地收尾（轻 sim 上限/平地形/撤高度扫描）+ 源实现的撤项与 70° 终止。"""
    apply_flat_postlude(
        cfg,
        drop_terrain_scan_sensor=profile.flat_drop_terrain_scan,
        drop_height_scan_obs=profile.flat_drop_height_scan,
        njmax=profile.flat_sim_njmax,
    )

    dropped = tuple(
        name
        for name in _FLAT_DROPPED_SENSORS
        if name != TERRAIN_SCAN or profile.flat_drop_terrain_scan
    )
    cfg.scene.sensors = tuple(
        sensor for sensor in (cfg.scene.sensors or ()) if sensor.name not in dropped
    )
    cfg.rewards["upright"].params.pop("terrain_sensor_names", None)
    for key in ("self_collisions", "shank_collision", "trunk_head_collision"):
        cfg.rewards.pop(key, None)
    cfg.terminations.pop("illegal_contact", None)
    cfg.terminations.pop("out_of_terrain_bounds", None)
    cfg.terminations["fell_over"] = TerminationTermCfg(
        func=envs_mdp.bad_orientation,
        params={"limit_angle": math.radians(profile.flat_tilt_limit_degrees)},
    )


def _apply_play_branch(
    cfg: ManagerBasedRlEnvCfg, profile: VelocityProfile, *, terrain_profile: TerrainProfile
) -> None:
    """play 档：公共展厅收尾（无限长回合/关噪声/撤扰动/5×5 地形）+ flat 档命令放宽。"""
    apply_play_postlude(
        cfg,
        drop_push_event=profile.play_drop_push,
        add_randomize_terrain=profile.play_randomize_terrain,
        showroom_terrain=profile.play_showroom_terrain,
    )
    cfg.terminations.pop("out_of_terrain_bounds", None)

    if terrain_profile == "flat":
        twist_cmd = cfg.commands["twist"]
        assert isinstance(twist_cmd, UniformVelocityCommandCfg)
        twist_cmd.ranges.lin_vel_x = profile.play_flat_lin_vel_x
        twist_cmd.ranges.ang_vel_z = profile.play_flat_ang_vel_z


# ---------------------------------------------------------------------------
# 源配方的公共收尾（来源：包内 `...go2/tasks/common.py` 的三个 `_go2_source_*` helper
# 与 `velocity/config.py` 的接线；三个 helper 与速度跟踪的算法变体同源，故一并上移）
#
# 去机型化：不再引用任何几何/关节字面量 —— 几何范围由调用方给（机型 profile 数据），
# 帧宽按实际关节数展开。
# ---------------------------------------------------------------------------


def apply_source_observation_clipping(cfg: ManagerBasedRlEnvCfg) -> None:
    """源环境最后的观测裁剪（`[-100, 100]`，作用于全部观测项）。"""
    for group in cfg.observations.values():
        for term in group.terms.values():
            term.clip = (-100.0, 100.0)


def apply_source_geom_friction(
    cfg: ManagerBasedRlEnvCfg,
    ranges: tuple[float, float],
) -> None:
    """把共享摩擦采样放到**每一个刚体形状**上（源 `_process_rigid_shape_props` 口径）。

    源回调给一个环境里的每个刚体形状赋同一个标量系数；MuJoCo 侧取 geom friction 的
    第一分量。**同步撤掉通用三轴随机化**（`foot_friction_spin` / `foot_friction_roll`）：
    它们对公共 mjlab 基座有用，但源任务不采样这两个轴。

    几何集合由绑定按本机型给出（`geom_names=(.*)` + 实体的 geom 清单），
    故这里只改数值与轴，不写任何几何名。
    """
    event = cfg.events.get("foot_friction_slide")
    if event is None:
        return
    asset_cfg = event.params["asset_cfg"]
    asset_cfg.geom_names = (r".*",)
    event.params.update(
        {
            "ranges": ranges,
            "axes": [0],
            "shared_random": True,
        }
    )
    cfg.events.pop("foot_friction_spin", None)
    cfg.events.pop("foot_friction_roll", None)


def source_frame_noise(
    *,
    joint_count: int,
    command_first: bool,
    dof_pos_noise: float = 0.01,
    ang_vel_noise: float = 0.2,
) -> UniformNoiseCfg:
    """源观测噪声向量（按帧布局：命令 / IMU / 重力 / 关节位置 / 关节速度 / 动作）。

    来源噪声在 `[-scale, scale]` 上均匀采样。站姿类任务把 IMU、重力放前面再放命令，
    CTS/DreamWaQ/TS 把命令放最前 —— `command_first` 表达两种契约。
    帧宽不再写死 12 个关节：关节段按**实际关节数**展开（换关节数不会静默错位）。
    """
    imu = [ang_vel_noise * 0.25] * 3
    gravity = [0.05] * 3
    command = [0.0] * 3
    q = [dof_pos_noise] * int(joint_count)
    dq = [1.5 * 0.05] * int(joint_count)
    actions = [0.0] * int(joint_count)
    values = (
        command + imu + gravity + q + dq + actions
        if command_first
        else imu + gravity + command + q + dq + actions
    )
    return UniformNoiseCfg(
        n_min=tuple(-value for value in values),
        n_max=tuple(values),
    )


def make_runner_cfg(profile: VelocityProfile) -> RslRlOnPolicyRunnerCfg:
    """族级 velocity runner（与其余技能同签名 `make_runner_cfg(profile)`）。

    速度跟踪的 PPO 档是**四足组逐字共享**的那一份（`quadruped_kit.ppo_runner_cfg`，唯一差异是
    `experiment_name`）；名字从 profile 的身份字段来（通用装配注入；缺省 = 族级默认名）。
    """
    from ... import ppo_runner_cfg

    return ppo_runner_cfg(profile.experiment_name or "family_velocity")
