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
    """足端高度扫描挂到本机型的足端 site（族约定：site 与足端几何同腿前缀）。

    **能力缺口**：没有足端 site 的机型（go1 的 MJCF 只有 imu 一个 site；足端就是
    calf 体）不装配这一传感器 —— 依赖它的项（足端高度扫描观测 / 足端高度与滑移奖励）
    一并按能力撤掉（见 `_drop_site_dependent_items`），不静默换口径、也不判死整个技能。
    """
    if not binding.has_foot_sites():
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
                ObjRef(type="site", name=name, entity="robot")
                for name in binding.foot_sites()
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
