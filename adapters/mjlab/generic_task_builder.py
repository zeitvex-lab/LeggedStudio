"""Build a robot-agnostic MJLab manager-based task from a Robot Contract.

The builder intentionally contains only generic MDP terms.  Robot-specific
contact sensors, gait rewards, actuator groups and terrain curricula belong in
an optional project extension and are not inferred from ``robot_id``.
"""

from __future__ import annotations

import math
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class GenericTaskBundle:
    """Configs and diagnostics produced by :func:`build_generic_task`."""

    task_id: str
    env_cfg: Any
    play_env_cfg: Any
    rl_cfg: Any
    diagnostics: dict[str, Any]


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _contract_value(contract: Any, path: str, default: Any = None) -> Any:
    current = contract
    for item in path.split("."):
        current = _get(current, item, default)
        if current is default:
            return default
    return current


def _action_scale_for(contract: Any) -> Any:
    """B5：动作缩放走**角色展开视图**（`role_resolver.action_scale_for_contract`）。

    `action.action_scale` 只是标量缺省，角色间真实档位不同（G1 髋俯仰 0.55 vs 腕俯仰
    0.07；轮足 leg 0.5 vs wheel 35.0）。读同一份契约数据，才能让"工作台改了 ⇒ 训练也改"。
    角色内一致时该函数返回 float，与旧行为逐值等价。
    """

    try:
        from contracts.role_resolver import action_scale_for_contract

        return action_scale_for_contract(contract)
    except Exception:
        return float(_contract_value(contract, "action.action_scale", 0.25))


def _asset_path(contract: Any, asset_root: str | Path | None = None) -> Path:
    raw = Path(str(_contract_value(contract, "urdf.path", "")))
    if raw.is_absolute():
        return raw.resolve()
    candidates = []
    if asset_root:
        candidates.append(Path(asset_root) / raw)
    # resolve_asset_path is kept lazy: this module remains importable without
    # MJLab installed (the control-plane uses it for diagnostics and tests).
    try:
        from contracts.asset_paths import resolve_asset_path

        candidates.append(resolve_asset_path(str(raw)))
    except Exception:
        pass
    candidates.append(Path.cwd() / raw)
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[0].resolve() if candidates else raw.resolve()


def _safe_id(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_")
    return value[:64] or "robot"


def _component_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")


def _recipe_environment(recipe: Any) -> dict[str, Any]:
    return dict(_get(recipe, "environment", {}) or {})


def _episode_length_s(environment: dict[str, Any]) -> float:
    """generic 路径的 episode_length_s 取值：显式键优先，缺键落构建缺省 20.0（B24，裁决见 build_generic_task 内注释）。"""
    return float(environment.get("episode_length_s", 20.0))


def _recipe_rewards(recipe: Any) -> dict[str, float]:
    values = _get(recipe, "reward_scales", {}) or {}
    return {str(key): float(value) for key, value in values.items() if value is not None}


def _name_unnamed_sensors(spec: Any) -> None:
    """给 MJCF 里**无 name 的传感器**补稳定名（类型/挂载点/语义都不动）。

    MuJoCo 接受无名传感器，但 mjlab 的 scene 会把每个 spec 传感器按名包成
    ``BuiltinSensor``（`mj_model.sensor('')` → ``KeyError: Invalid name ''``），环境直接
    建不起来——lite3 / m20 的 MJCF 就带无名 ``<gyro>``/``<accelerometer>``。
    """
    import mujoco

    fallback = {
        int(mujoco.mjtSensor.mjSENS_ACCELEROMETER): "imu_accelerometer",
        int(mujoco.mjtSensor.mjSENS_GYRO): "imu_gyro",
    }
    taken = {sensor.name for sensor in spec.sensors if sensor.name}
    for sensor in spec.sensors:
        if sensor.name:
            continue
        base = fallback.get(int(sensor.type), f"sensor_type{int(sensor.type)}")
        name = base
        suffix = 0
        while name in taken:
            suffix += 1
            name = f"{base}_{suffix}"
        sensor.name = name
        taken.add(name)


def _make_spec_fn(xml_path: Path, *, strip_actuators: bool = False):
    import mujoco

    def get_spec():
        spec = mujoco.MjSpec.from_file(str(xml_path))
        if strip_actuators:
            for actuator in list(spec.actuators):
                actuator.delete()
        _name_unnamed_sensors(spec)
        return spec

    return get_spec


#: 模型带非零接触余量时必须关掉的 warp CCD 开关（顺序即写入顺序）。
_CCD_UNSUPPORTED_FLAGS = ("multiccd", "nativeccd")


def _ccd_disable_flags(xml_path: Path) -> tuple[str, ...]:
    """模型带非零 geom/pair margin 时禁用 MULTICCD + NATIVECCD。

    ``mujoco_warp._src.io._check_margin``：BOX/MESH 成对且任一 margin≠0 时，MULTICCD
    （该构建里**默认开启**）直接 ``NotImplementedError``；把 MULTICCD 关掉还有 NATIVECCD
    那一关（BOX-BOX 同样抛），所以两个都要关。另一条出路是把 margin 抹平——那是动物理参数
    （接触检测距离），不做。无 margin 的模型原样不动（"不修改就不起作用"）。
    """
    import mujoco

    try:
        model = mujoco.MjSpec.from_file(str(xml_path)).compile()
    except Exception:  # noqa: BLE001 —— 资产缺件等问题交给后续建环境时报真错
        return ()
    box_or_mesh = {int(mujoco.mjtGeom.mjGEOM_BOX), int(mujoco.mjtGeom.mjGEOM_MESH)}
    for geom in range(model.ngeom):
        if int(model.geom_type[geom]) in box_or_mesh and float(model.geom_margin[geom]) > 0:
            return _CCD_UNSUPPORTED_FLAGS
    for pair in range(model.npair):
        if float(model.pair_margin[pair]) > 0:
            return _CCD_UNSUPPORTED_FLAGS
    return ()


def _xml_actuated_targets(xml_path: Path) -> tuple[set[str], dict[str, str], set[str], dict[str, str]]:
    """Return joint names, the XML actuator per joint, unsupported joints, and each
    joint's **command field**（`position` / `velocity` / `effort`）。

    为什么要带出 command field：XML 里同一台机器人可能**混用**执行器类型（轮足的腿是
    position、轮是 velocity），而 mjlab 的 `XmlActuatorCfg` 一组只允许一种类型——不分组
    就会在建环境时抛 "Mixed XML actuator types"。分组依据必须来自 XML 本身，不能靠关节
    名字里有没有 "wheel" 猜。
    """
    import mujoco

    spec = mujoco.MjSpec.from_file(str(xml_path))
    joints = {str(item.name) for item in spec.joints if item.name}
    targets: dict[str, str] = {}
    fields: dict[str, str] = {}
    unsupported: set[str] = set()
    for actuator in spec.actuators:
        target = getattr(actuator, "target", None)
        if target:
            targets.setdefault(str(target), str(actuator.name))
            try:
                from mjlab.utils.mujoco import detect_command_field
                fields[str(target)] = str(detect_command_field(actuator))
            except (ValueError, TypeError):
                unsupported.add(str(target))
    return joints, targets, unsupported, fields


def _build_entity(contract: Any, xml_path: Path):
    from mjlab.actuator import BuiltinPositionActuatorCfg, BuiltinVelocityActuatorCfg
    from mjlab.actuator.xml_actuator import XmlActuatorCfg
    from mjlab.entity import EntityArticulationInfoCfg, EntityCfg

    joint_order = [str(item) for item in _contract_value(contract, "action.joint_order", [])]
    if not joint_order:
        joint_order = [str(item) for item in _contract_value(contract, "joints.actuated_joints", [])]
    if not joint_order:
        raise ValueError("generic MJLab task requires at least one actuated joint")

    _, xml_targets, unsupported_targets, xml_fields = _xml_actuated_targets(xml_path)
    xml_names = tuple(item for item in joint_order if item in xml_targets and item not in unsupported_targets)
    generated_names = tuple(item for item in joint_order if item not in xml_targets or item in unsupported_targets)
    actuators = []
    # P1：`control.actuator_model=dc_motor` 时，对该批关节改用 mjlab 的 DC 电机执行器
    # （转矩-转速 T-N 曲线，dc_actuator.py）。缺省（ideal_pd / 未声明）时 dc_settings 为空元组，
    # **下面一行都不会改**——这就是"不修改不起作用"。任一关节缺 t_n_curve 会在
    # dc_actuator_settings 里抛错（不静默退回理想 PD）。
    # ⚠️ 本分支在无 mjlab 的环境无法验证（本机 mjlab 未安装）：首次在 adapter venv 里
    #    跑 dc_motor 前，请先用 ideal_pd 跑通同一任务做对照。
    from contracts.physics_binding import dc_actuator_settings

    dc_settings = dc_actuator_settings(xml_path.parent.parent)
    if dc_settings:
        from mjlab.actuator import DcMotorActuatorCfg

        dc_joints = set(dc_settings)
        xml_names = tuple(name for name in xml_names if name not in dc_joints)
        generated_names = tuple(name for name in generated_names if name not in dc_joints)
        for joint, settings in dc_settings.items():
            actuators.append(DcMotorActuatorCfg(target_names_expr=(joint,), **settings))
    if xml_names:
        # **按 XML 执行器类型分组**：一台机器人的 XML 可以混用（轮足 = 腿 position + 轮
        # velocity），而 mjlab 一组只允许一种 command_field。分组依据取 XML 实测的
        # detect_command_field，不靠关节名猜——否则换台命名的机型就会静默走错分支。
        grouped: dict[str, list[str]] = {}
        for name in xml_names:
            grouped.setdefault(xml_fields.get(name, ""), []).append(name)
        for field_name in sorted(grouped):
            actuators.append(XmlActuatorCfg(
                target_names_expr=tuple(grouped[field_name]),
                command_field=field_name or None,
            ))
    if generated_names:
        # A conservative generic PD actuator makes MJCF files without an
        # actuator section trainable while preserving XML actuator semantics.
        position_names = tuple(item for item in generated_names if "wheel" not in item.lower())
        velocity_names = tuple(item for item in generated_names if "wheel" in item.lower())
        if position_names:
            actuators.append(BuiltinPositionActuatorCfg(target_names_expr=position_names, stiffness=20.0, damping=1.0, effort_limit=None))
        if velocity_names:
            actuators.append(BuiltinVelocityActuatorCfg(target_names_expr=velocity_names, damping=1.0, effort_limit=None))

    pose = list(_contract_value(contract, "joints.default_pose", []))
    if len(pose) != len(joint_order):
        pose = [0.0] * len(joint_order)
    init = EntityCfg.InitialStateCfg(
        pos=(0.0, 0.0, 0.3),
        joint_pos={name: float(value) for name, value in zip(joint_order, pose)},
        joint_vel={".*": 0.0},
    )
    entity = EntityCfg(
        init_state=init,
        spec_fn=_make_spec_fn(xml_path, strip_actuators=bool(unsupported_targets)),
        articulation=EntityArticulationInfoCfg(actuators=tuple(actuators)),
    )
    action_actuator_names = tuple(xml_targets[item] for item in xml_names) + generated_names
    return entity, joint_order, {
        "xml_actuated_joints": list(xml_names),
        "generated_actuated_joints": list(generated_names),
        "action_actuator_names": list(action_actuator_names),
        "unsupported_xml_actuators_rebuilt": sorted(unsupported_targets),
    }


def _build_observations(contract: Any):
    from mjlab.envs import mdp
    from mjlab.managers.observation_manager import ObservationGroupCfg, ObservationTermCfg
    from mjlab.managers.scene_entity_config import SceneEntityCfg

    joint_names = tuple(str(item) for item in _contract_value(contract, "action.joint_order", []))
    joint_cfg = SceneEntityCfg("robot", joint_names=joint_names or (".*",))
    aliases = {
        "base_linear_velocity": "base_lin_vel",
        "linear_velocity": "base_lin_vel",
        "base_angular_velocity": "base_ang_vel",
        "angular_velocity": "base_ang_vel",
        "gravity": "projected_gravity",
        "joint_positions": "joint_pos",
        "joint_velocities": "joint_vel",
        "actions": "last_action",
        "last_actions": "last_action",
        "commands": "command",
    }
    factories = {
        "base_lin_vel": lambda: ObservationTermCfg(func=mdp.base_lin_vel),
        "base_ang_vel": lambda: ObservationTermCfg(func=mdp.base_ang_vel),
        "projected_gravity": lambda: ObservationTermCfg(func=mdp.projected_gravity),
        "joint_pos": lambda: ObservationTermCfg(func=mdp.joint_pos_rel, params={"asset_cfg": joint_cfg}),
        "joint_vel": lambda: ObservationTermCfg(func=mdp.joint_vel_rel, params={"asset_cfg": joint_cfg}),
        "last_action": lambda: ObservationTermCfg(func=mdp.last_action),
        "command": lambda: ObservationTermCfg(func=mdp.generated_commands, params={"command_name": "twist"}),
    }
    requested = list(_contract_value(contract, "observation.components", []) or [])
    if not requested:
        requested = ["base_lin_vel", "base_ang_vel", "projected_gravity", "joint_pos", "joint_vel", "last_action"]
    terms = {}
    unsupported = []
    for component in requested:
        key = aliases.get(_component_key(component), _component_key(component))
        if key not in factories:
            unsupported.append(str(component))
            continue
        terms.setdefault(key, factories[key]())
    if unsupported:
        raise ValueError(f"unsupported generic observation components: {', '.join(unsupported)}")
    actor = ObservationGroupCfg(terms=terms, concatenate_terms=True, enable_corruption=True)
    critic = ObservationGroupCfg(terms=deepcopy(terms), concatenate_terms=True, enable_corruption=False)
    return {"actor": actor, "critic": critic}, list(terms), unsupported


def _build_commands(environment: dict[str, Any], observation_terms: list[str]):
    if "command" not in observation_terms:
        return {}
    from mjlab.tasks.velocity.velocity_env_cfg import make_velocity_env_cfg

    ranges = environment.get("command_ranges", {}) or {}
    def pair(name: str, default: tuple[float, float]):
        value = ranges.get(name)
        if value is None:
            aliases = {"lin_vel_x": "vx", "lin_vel_y": "vy", "ang_vel_z": "wz"}
            value = ranges.get(aliases[name])
        return tuple(float(item) for item in value) if value is not None else default
    # Mirror MJLab's own velocity task (heading_command / resampling / rel_* envs are
    # version-owned truth); only the user-facing velocity ranges get overridden.
    command = deepcopy(make_velocity_env_cfg().commands["twist"])
    command.debug_vis = False
    command.ranges.lin_vel_x = pair("lin_vel_x", command.ranges.lin_vel_x)
    command.ranges.lin_vel_y = pair("lin_vel_y", command.ranges.lin_vel_y)
    command.ranges.ang_vel_z = pair("ang_vel_z", command.ranges.ang_vel_z)
    return {"twist": command}


def _xml_root_body(xml_path: Path) -> str | None:
    """Name of the robot's root body (first body under worldbody)."""
    import mujoco

    spec = mujoco.MjSpec.from_file(str(xml_path))
    bodies = list(spec.worldbody.bodies)
    return str(bodies[0].name) if bodies and bodies[0].name else None


def _base_asset_cfg(root_body: str | None):
    """Scope a base-attitude reward to the root body only.

    MJLab's velocity task leaves ``body_names=()`` for each robot to fill; without
    that scope the whole-entity body slice reaches ``upright`` and breaks its
    [B, 4] quaternion math (2026-09-23 generic path: 2 envs x 13 bodies = 26).
    """
    from mjlab.managers.scene_entity_config import SceneEntityCfg

    if root_body:
        return SceneEntityCfg("robot", body_names=(root_body,))
    return SceneEntityCfg("robot", body_ids=[0])


def _build_rewards(recipe: Any, has_commands: bool, root_body: str | None = None):
    from mjlab.envs import mdp
    from mjlab.tasks.velocity import mdp as velocity_mdp
    from mjlab.managers.reward_manager import RewardTermCfg
    from mjlab.managers.scene_entity_config import SceneEntityCfg

    asset = SceneEntityCfg("robot", joint_names=(".*",))
    aliases = {
        "tracking_lin_vel": "track_linear_velocity",
        "tracking_ang_vel": "track_angular_velocity",
        "orientation": "upright",
        "body_orientation_l2": "upright",
        "torques": "joint_torques_l2",
        "dof_vel": "joint_vel_l2",
        "dof_acc": "joint_acc_l2",
        "action_rate": "action_rate_l2",
        "joint_pos_limits": "joint_pos_limits",
    }
    funcs = {
        "track_linear_velocity": (velocity_mdp.track_linear_velocity, {"std": 0.5, "command_name": "twist"}),
        "track_angular_velocity": (velocity_mdp.track_angular_velocity, {"std": 0.7, "command_name": "twist"}),
        "upright": (velocity_mdp.upright, {"std": math.sqrt(0.2), "asset_cfg": _base_asset_cfg(root_body)}),
        "joint_torques_l2": (mdp.joint_torques_l2, {"asset_cfg": asset}),
        "joint_vel_l2": (mdp.joint_vel_l2, {"asset_cfg": asset}),
        "joint_acc_l2": (mdp.joint_acc_l2, {"asset_cfg": asset}),
        "action_rate_l2": (mdp.action_rate_l2, {}),
        "joint_pos_limits": (mdp.joint_pos_limits, {"asset_cfg": asset}),
        "is_alive": (mdp.is_alive, {}),
    }
    configured = _recipe_rewards(recipe)
    if not configured:
        configured = {"track_linear_velocity": 1.0, "track_angular_velocity": 0.5, "upright": 0.2, "joint_torques_l2": -2e-4, "action_rate_l2": -0.01}
    result = {}
    skipped = []
    for raw_name, weight in configured.items():
        name = aliases.get(_component_key(raw_name), _component_key(raw_name))
        if name in {"track_linear_velocity", "track_angular_velocity"} and not has_commands:
            skipped.append(raw_name)
            continue
        if name not in funcs:
            if float(weight) == 0.0:
                continue
            skipped.append(raw_name)
            continue
        func, params = funcs[name]
        result[name] = RewardTermCfg(func=func, weight=float(weight), params=params)
    return result, skipped


def build_generic_task(contract: Any, recipe: Any, *, asset_root: str | Path | None = None, task_id: str | None = None) -> GenericTaskBundle:
    """Construct a generic MJLab task from a Contract and resolved recipe.

    Only MJCF assets are accepted because MJLab's Entity consumes a compiled
    ``mujoco.MjSpec``. URDF assets must first be converted by the validation
    workbench, which then stores the resulting MJCF path in the project package.
    """
    xml_path = _asset_path(contract, asset_root)
    if xml_path.suffix.lower() not in {".xml", ".mjcf"}:
        raise ValueError(f"generic MJLab task requires MJCF/XML asset, got {xml_path}")
    if not xml_path.exists():
        raise FileNotFoundError(f"MJCF asset not found: {xml_path}")
    from mjlab.envs import ManagerBasedRlEnvCfg, mdp
    from mjlab.managers.event_manager import EventTermCfg
    from mjlab.managers.observation_manager import ObservationGroupCfg
    from mjlab.managers.termination_manager import TerminationTermCfg
    from mjlab.rl import RslRlOnPolicyRunnerCfg
    from mjlab.scene import SceneCfg
    from mjlab.sim import MujocoCfg, SimulationCfg
    from dataclasses import replace

    environment = _recipe_environment(recipe)
    entity, joint_order, actuator_report = _build_entity(contract, xml_path)
    observations, observation_terms, unsupported_obs = _build_observations(contract)
    commands = _build_commands(environment, observation_terms)
    rewards, skipped_rewards = _build_rewards(recipe, bool(commands), _xml_root_body(xml_path))
    terrain_type = str(environment.get("terrain_type", "plane")).lower()
    # 地形一律按**档位 id**装配（registry/terrains）：此前这里硬编码 {plane, rough}，
    # 于是技能表宣称的 stairs 档在通用路径上直接报错——"同族换机型能不能训同一档"
    # 没有单一真值。现在未知档/未就绪档由 terrain_profiles 统一 fail-closed 并列出可用档。
    from adapters.mjlab import terrain_profiles as _terrain_profiles

    terrain = _terrain_profiles.build_terrain_entity(terrain_type)
    num_envs = max(1, int(environment.get("num_envs", 1)))
    # B24 裁决：这里的 20.0 是**构建缺省**（非覆盖真值）——generic 路径服务于用户导入、
    # 无训练源码/无 profile 的包，没有任务真值层可沿用，20.0 是唯一显式来源，且被显式
    # 写进 env_cfg 与 resolved 配置（可见、可查）。请求显式提供的 episode_length_s 经
    # environment 传入即生效（B23 真值守卫只拦 None/缺键，不拦 generic 路径的显式值）。
    # 否决「改契约声明」：episode_length_s 是任务层字段，B13 三层拆分裁决物理/契约层
    # 不放任务字段；否决「强制显式提供」：generic 路径的存在意义就是零配置可跑（V7）。
    episode_length = _episode_length_s(environment)
    decimation = max(1, int(_contract_value(contract, "control.decimation", 1)))
    ccd_disable_flags = _ccd_disable_flags(xml_path)
    env_cfg = ManagerBasedRlEnvCfg(
        decimation=decimation,
        scene=SceneCfg(terrain=terrain, entities={"robot": entity}, num_envs=num_envs, extent=2.0),
        observations=observations,
        # MJLab action selectors are transmission targets (joint names), not
        # MuJoCo actuator element names. This remains stable for XML and
        # generated actuator groups alike.
        actions={"joint_pos": __import__("mjlab.envs.mdp.actions", fromlist=["JointPositionActionCfg"]).JointPositionActionCfg(entity_name="robot", actuator_names=tuple(joint_order), scale=_action_scale_for(contract), use_default_offset=True)},
        events={"reset_scene_to_default": EventTermCfg(func=mdp.reset_scene_to_default, mode="reset")},
        rewards=rewards,
        terminations={"time_out": TerminationTermCfg(func=mdp.time_out, time_out=True)},
        commands=commands,
        seed=int(_get(recipe, "seed", 0) or 0),
        sim=SimulationCfg(mujoco=MujocoCfg(timestep=1.0 / max(1, int(_contract_value(contract, "control.physics_hz", 1000))), disableflags=ccd_disable_flags)),
        episode_length_s=episode_length,
    )
    play_cfg = deepcopy(env_cfg)
    play_cfg.scene.num_envs = min(num_envs, 64)
    play_cfg.episode_length_s = max(episode_length, 1e6)
    play_cfg.observations["actor"].enable_corruption = False

    algorithm = dict(_get(recipe, "algorithm_config", {}) or {})
    rl_cfg = RslRlOnPolicyRunnerCfg(
        num_steps_per_env=max(4, int(algorithm.get("num_steps", 24))),
        max_iterations=max(1, int(algorithm.get("max_iterations", 1000))),
        save_interval=max(1, int(algorithm.get("save_interval", 100))),
        experiment_name=_safe_id(str(_get(recipe, "task_name", "generic"))),
        logger="tensorboard",
    )
    for source, target in (("learning_rate", "learning_rate"), ("gamma", "gamma"), ("gae_lambda", "lam"), ("clip_param", "clip_param"), ("entropy_coef", "entropy_coef")):
        if source in algorithm and hasattr(rl_cfg.algorithm, target):
            setattr(rl_cfg.algorithm, target, type(getattr(rl_cfg.algorithm, target))(algorithm[source]))
    if "num_minibatches" in algorithm:
        rl_cfg.algorithm.num_mini_batches = max(1, int(algorithm["num_minibatches"]))
    generated_id = task_id or f"LeggedStudio-Generic-{_safe_id(str(_get(contract, 'contract_id', 'robot')))}"
    diagnostics = {
        "asset": str(xml_path),
        "joint_order": joint_order,
        "observation_terms": observation_terms,
        "terrain_type": terrain_type,
        "reward_terms": sorted(rewards),
        "skipped_rewards": skipped_rewards,
        "unsupported_observations": unsupported_obs,
        "mujoco_disableflags": list(ccd_disable_flags),
        **actuator_report,
    }
    return GenericTaskBundle(generated_id, env_cfg, play_cfg, rl_cfg, diagnostics)


__all__ = ["GenericTaskBundle", "build_generic_task"]
