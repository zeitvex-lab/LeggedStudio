"""Isolated task loading and transactional effective configuration assembly."""
from __future__ import annotations

import copy
import importlib
import inspect
import json
import sys
from pathlib import Path
from dataclasses import dataclass

def _ensure_on_path(path) -> None:
    normalized = str(Path(path).resolve())
    if normalized not in sys.path:
        sys.path.insert(0, normalized)


def apply_training_recipe(env_cfg, rl_cfg, config: dict, *, preserve_profile: bool = False) -> dict:
    """Apply the canonical Web/CLI recipe to real MJLab config objects."""
    recipe = config.get("resolved_recipe") or config.get("recipe") or {}
    environment = recipe.get("environment", {}) if isinstance(recipe, dict) else {}
    recipe_rewards = recipe.get("reward_scales", {}) if isinstance(recipe, dict) else {}
    # Generic presets must not overwrite profile-owned rewards without explicit edits.
    explicit_rewards = {
        str(key): float(value)
        for key, value in (config.get("reward_scales") or {}).items()
        if value is not None
    }
    if preserve_profile:
        rewards = explicit_rewards if config.get("reward_overrides", False) else {}
    else:
        rewards = recipe_rewards or explicit_rewards
    terrain_type = str(environment.get("terrain_type", config.get("terrain_type", "plane"))).lower()
    if not preserve_profile and terrain_type not in {"plane", "rough"}:
        raise ValueError(f"native MJLab training supports terrain_type plane or rough; got {terrain_type!r}")
    terrain = getattr(getattr(env_cfg, "scene", None), "terrain", None)
    if terrain is not None and not preserve_profile:
        if terrain_type == "plane":
            terrain.terrain_type = "plane"
            terrain.terrain_generator = None
        elif terrain.terrain_generator is None:
            raise ValueError("rough terrain recipe requires an MJLab terrain generator")

    aliases = {
        "tracking_lin_vel": "track_linear_velocity", "tracking_ang_vel": "track_angular_velocity",
        "track_lin_vel": "track_linear_velocity", "track_ang_vel": "track_angular_velocity",
        "joint_torques": "joint_torques_l2", "joint_acc": "joint_acc_l2",
        "body_ang_vel": "body_angular_velocity_penalty", "body_collision": "self_collision_cost",
        "wheel_roll_tracking": "wheel_roll_tracking",
        "orientation": "body_orientation_l2", "torques": "joint_torques_l2", "dof_vel": "joint_vel_l2",
        "dof_acc": "joint_acc_l2", "action_rate": "action_rate_l2", "collision": "illegal_contact",
        "feet_air_time": "air_time", "base_height": "upright", "stumble": "body_orientation_l2",
    }
    reward_terms = getattr(env_cfg, "rewards", {})
    unmatched = []
    term_candidates = {
        "track_linear_velocity": ("track_linear_velocity", "track_lin_vel"),
        "track_angular_velocity": ("track_angular_velocity", "track_ang_vel"),
        "body_orientation_l2": ("body_orientation_l2", "upright", "flat_orientation"),
        "joint_torques_l2": ("joint_torques_l2", "joint_torques"),
        "joint_acc_l2": ("joint_acc_l2", "joint_acc"),
        "action_rate_l2": ("action_rate_l2", "action_rate"),
        "air_time": ("air_time", "feet_air_time"),
        "base_height_l2": ("base_height_l2", "base_height"),
        "self_collision_cost": ("self_collision_cost", "body_collision"),
    }
    def resolve_term(name: str):
        for candidate in (name, aliases.get(name), *term_candidates.get(aliases.get(name, name), ())):
            if candidate in reward_terms:
                return candidate
        return None
    for name, weight in rewards.items():
        target = resolve_term(name)
        if target not in reward_terms:
            if float(weight) == 0.0 and not config.get("reward_overrides", False):
                continue
            unmatched.append(name)
            continue
        reward_terms[target].weight = float(weight)
    if unmatched:
        raise ValueError(f"reward terms are not available in MJLab task {unmatched}")

    reward_params = (environment.get("reward_params") if isinstance(environment, dict) else None) or config.get("reward_params", {})
    if preserve_profile:
        reward_params = (config.get("reward_params") or {}) if config.get("reward_overrides", False) else {}
    for name, params in reward_params.items():
        target = resolve_term(name)
        if target not in reward_terms or not isinstance(params, dict):
            raise ValueError(f"reward parameter target is not available in MJLab task: {name}")
        term_params = getattr(reward_terms[target], "params", None)
        try:
            parameters = list(inspect.signature(reward_terms[target].func).parameters.values())
        except (AttributeError, TypeError, ValueError):
            parameters = []
        # The manager supplies the first positional argument; **kwargs is not a typo allowlist.
        context = next((p.name for p in parameters if p.kind in (
            inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)), None)
        keyword_names = {p.name for p in parameters if p.name != context and p.kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)}
        for key, value in params.items():
            if isinstance(term_params, dict):
                if key not in term_params and key not in keyword_names:
                    raise ValueError(f"reward parameter is not available in MJLab task: {name}.{key}")
                term_params[key] = value
            elif term_params is not None and hasattr(term_params, key):
                setattr(term_params, key, value)
            else:
                raise ValueError(f"reward parameter is not available in MJLab task: {name}.{key}")

    command_ranges = (environment.get("command_ranges") if isinstance(environment, dict) else None) or config.get("command_ranges", {})
    if command_ranges:
        command = getattr(env_cfg, "commands", {}).get("twist")
        ranges = getattr(command, "ranges", None)
        if ranges is None and any(value is not None for value in command_ranges.values()):
            raise ValueError("command_ranges requires commands.twist.ranges")
        if ranges is not None:
            for key, value in command_ranges.items():
                if value is None:
                    continue
                target = "ang_vel_z" if key in {"wz", "ang_vel_yaw"} else "lin_vel_x" if key in {"vx", "lin_vel_x"} else "lin_vel_y" if key in {"vy", "lin_vel_y"} else key
                if hasattr(ranges, target): setattr(ranges, target, tuple(value))
                elif value is not None: raise ValueError(f"command range is not supported by MJLab: {key}")

    if hasattr(env_cfg, "episode_length_s"):
        # Omitted values preserve the task-owned episode length.
        _episode_length_s = environment.get("episode_length_s")
        if _episode_length_s is None:
            _episode_length_s = config.get("episode_length_s")
        if _episode_length_s is not None:
            env_cfg.episode_length_s = float(_episode_length_s)
    if hasattr(env_cfg.scene, "num_envs"):
        env_cfg.scene.num_envs = max(1, int(environment.get("num_envs", config.get("num_envs", env_cfg.scene.num_envs))))

    algorithm_config = recipe.get("algorithm_config", {}) if isinstance(recipe, dict) else {}
    algorithm_config = {**algorithm_config, **config}
    algorithm = getattr(rl_cfg, "algorithm", None)
    field_aliases = {"gae_lambda": "lam", "num_minibatches": "num_mini_batches"}
    for source, target in field_aliases.items():
        if source in algorithm_config and algorithm is not None and hasattr(algorithm, target):
            setattr(algorithm, target, type(getattr(algorithm, target))(algorithm_config[source]))
    for name in ("learning_rate", "gamma", "clip_param", "entropy_coef"):
        if name in algorithm_config and algorithm is not None and hasattr(algorithm, name):
            setattr(algorithm, name, type(getattr(algorithm, name))(algorithm_config[name]))
    if "num_steps" in algorithm_config and hasattr(rl_cfg, "num_steps_per_env"):
        rl_cfg.num_steps_per_env = max(4, int(algorithm_config["num_steps"]))
    if "max_iterations" in algorithm_config and hasattr(rl_cfg, "max_iterations"):
        rl_cfg.max_iterations = max(1, int(algorithm_config["max_iterations"]))
    if "save_interval" in algorithm_config and hasattr(rl_cfg, "save_interval"):
        rl_cfg.save_interval = max(1, int(algorithm_config["save_interval"]))
    return {"terrain_type": terrain_type, "reward_terms_applied": len(rewards) - len(unmatched), "reward_params_applied": len(reward_params), "command_ranges_applied": len(command_ranges), "algorithm": str(config.get("algorithm", recipe.get("algorithm", "PPO"))).upper()}


def _import_entrypoint(value: str):
    """Import a package-owned ``module:factory`` entrypoint."""
    module_name, separator, attr_name = str(value).partition(":")
    if not separator or not module_name or not attr_name:
        raise ValueError(f"invalid package entrypoint: {value!r}; expected module:callable")
    factory = getattr(importlib.import_module(module_name), attr_name, None)
    if not callable(factory):
        raise TypeError(f"package entrypoint is not callable: {value}")
    return factory


def _resolve_entrypoint(value: str):
    """Resolve a package entrypoint that may be a factory or config object."""
    module_name, separator, attr_name = str(value).partition(":")
    if not separator or not module_name or not attr_name:
        raise ValueError(f"invalid package entrypoint: {value!r}; expected module:callable")
    return getattr(importlib.import_module(module_name), attr_name, None)


def _call_factory(factory, *, play: bool = False):
    """Call factories with the optional MJLab play flag when supported."""
    try:
        signature = inspect.signature(factory)
        if "play" in signature.parameters:
            return factory(play=play)
    except (TypeError, ValueError):
        pass
    return factory()


def strip_visual_geoms(env_cfg) -> int:
    # Removing render-only geometry reduces headless training cost.
    stripped_total = 0
    try:
        entities = env_cfg.scene.entities
    except AttributeError:
        return 0
    for name, entity_cfg in entities.items():
        spec_fn = getattr(entity_cfg, "spec_fn", None)
        if not callable(spec_fn):
            continue
        original = spec_fn

        def wrapped(_original=original):
            import mujoco
            spec = _original()
            stripped = 0
            for geom in list(spec.geoms):
                try:
                    if (int(geom.contype) == 0 and int(geom.conaffinity) == 0
                            and float(getattr(geom, "density", 0) or 0) == 0):
                        spec.delete_geom(geom)
                        stripped += 1
                except Exception:
                    continue
            nonlocal_stripped[0] += stripped
            return spec

        nonlocal_stripped = [0]
        try:
            entity_cfg.spec_fn = wrapped
            # 记录剥离数要等构建后才知道；这里只挂包装
        except Exception:
            entity_cfg.spec_fn = original
    return stripped_total


def _apply_profile_algorithm_plugin(profile: dict | None, rl_cfg) -> dict | None:
    # Only the profile author can choose a plugin over the package-owned runner.

    if not isinstance(profile, dict):
        return None
    name = str(profile.get("algorithm_plugin") or "").strip()
    if not name:
        return None
    from adapters.mjlab.algorithms.plugin_registry import apply_algorithm_plugin

    variant = profile.get("algorithm_variant")
    return apply_algorithm_plugin(rl_cfg, algorithm_plugin=name, variant=str(variant) if variant else None)


def find_training_profile(package: dict, profile_id: str | None) -> dict | None:
    if not profile_id:
        return None
    root = Path(str(package.get("package_root", ""))) / "training" / "profiles"
    for path in sorted(root.glob("*.json")):
        try:
            profile = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if profile.get("profile_id") == profile_id:
            return profile
    raise ValueError(f"training profile not found in robot package: {profile_id}")


def load_profile_bundle(profile: dict, package: dict, config: dict):
    """Load an isolated package profile without robot-id-specific branches."""
    package_root = Path(str(package.get("package_root", ""))).resolve()
    source_root = package_root / str(profile.get("source_root", "training/source"))
    if not source_root.exists():
        raise FileNotFoundError(f"profile source root not found: {source_root}")
    _ensure_on_path(source_root)
    entrypoints = profile.get("entrypoints") or {}
    env_entrypoint = entrypoints.get("env")
    runner_entrypoint = entrypoints.get("runner")
    if not env_entrypoint or not runner_entrypoint:
        raise ValueError(f"profile {profile.get('profile_id')} must declare entrypoints.env and entrypoints.runner")
    env_factory = _import_entrypoint(env_entrypoint)
    runner_factory = _resolve_entrypoint(runner_entrypoint)
    if runner_factory is None:
        raise AttributeError(f"package entrypoint attribute not found: {runner_entrypoint}")
    env_cfg = _call_factory(env_factory, play=False)
    play_env_cfg = _call_factory(env_factory, play=True)
    if bool(config.get("headless_visual", False)) is False and str(config.get("mode", "train")) == "train":
        strip_visual_geoms(env_cfg)
    # Profiles may export config instances; copy them to avoid shared-state mutation.
    rl_cfg = _call_factory(runner_factory) if callable(runner_factory) else copy.deepcopy(runner_factory)
    configure_entrypoint = entrypoints.get("configure")
    if configure_entrypoint:
        configure = _import_entrypoint(configure_entrypoint)
        configured = configure(
            env_cfg=env_cfg,
            play_env_cfg=play_env_cfg,
            rl_cfg=rl_cfg,
            config=copy.deepcopy(config),
        )
        if isinstance(configured, dict):
            env_cfg = configured.get("env_cfg", env_cfg)
            play_env_cfg = configured.get("play_env_cfg", play_env_cfg)
            rl_cfg = configured.get("rl_cfg", rl_cfg)
    return env_cfg, play_env_cfg, rl_cfg


@dataclass
class AssembledTrainingConfig:
    environment: object
    runner: object
    report: dict
    snapshot: dict


def apply_config_overrides(env_cfg, rl_cfg, config: dict) -> list[str]:
    """Validate the entire batch before applying leaf edits to owned configs."""
    from adapters.mjlab.config_introspect import dump_config_tree, iter_leaves, set_by_path
    from adapters.mjlab.param_descriptors import resolve_params
    from backend.training.dot_path import STATIC_READONLY, validate_edits

    overrides = config.get("overrides")
    if overrides is None:
        return []
    if not isinstance(overrides, dict):
        raise ValueError("overrides must be a mapping")
    roots = {"environment": env_cfg, "runner": rl_cfg}
    tree = {key: dump_config_tree(value) for key, value in roots.items()}
    descriptors = {item["id"]: item for item in resolve_params(tree)}
    catalog = []
    for root, obj in roots.items():
        for path, value in iter_leaves(obj, root):
            descriptor = descriptors.get(path, {})
            readonly = any(part in STATIC_READONLY for part in path.split("."))
            catalog.append({**descriptor, "path": path, "value": value,
                            "type": descriptor.get("type", type(value).__name__),
                            "readonly": readonly or descriptor.get("readonly", False)})
    validated = validate_edits(overrides, catalog=catalog)
    if not validated["ok"]:
        raise ValueError("; ".join(validated["problems"]))
    for detail in validated["details"]:
        before, value = detail["before"], detail["value"]
        if isinstance(before, (list, tuple)):
            if not isinstance(value, (list, tuple)):
                raise ValueError(f"{detail['path']}: expected an array")
            if before and any(type(item) is not type(before[0]) for item in value):
                # Numeric arrays permit int-to-float widening, not arbitrary objects.
                numeric = all(isinstance(item, (int, float)) and not isinstance(item, bool)
                              for item in (*before, *value))
                if not numeric:
                    raise ValueError(f"{detail['path']}: incompatible array element type")
    # Probe setters on copies as well: coercion errors cannot leave partial edits.
    trial = copy.deepcopy(roots)
    try:
        for path, value in validated["applied"].items():
            root, suffix = path.split(".", 1)
            set_by_path(trial[root], suffix, value)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"invalid override {path}: {exc}") from exc
    for path, value in validated["applied"].items():
        root, suffix = path.split(".", 1)
        set_by_path(roots[root], suffix, value)
    return list(validated["applied"])


def assemble_training_config(env_cfg, rl_cfg, config, *, profile=None) -> AssembledTrainingConfig:
    """Assemble on copies; snapshots are diagnostic, never executable serialization."""
    from adapters.mjlab.config_introspect import dump_config_tree

    env_cfg, rl_cfg, config = copy.deepcopy((env_cfg, rl_cfg, config))
    recipe = apply_training_recipe(env_cfg, rl_cfg, config, preserve_profile=profile is not None)
    plugin = _apply_profile_algorithm_plugin(profile, rl_cfg)
    if plugin:
        recipe = {**recipe, "algorithm_plugin": plugin}
    env_cfg.scene.num_envs = max(1, int(config.get("num_envs", env_cfg.scene.num_envs)))
    for entity in getattr(env_cfg.scene, "entities", {}).values():
        for collision in getattr(entity, "collisions", None) or ():
            if isinstance(collision.priority, dict) and ".*" not in collision.priority:
                collision.priority[".*"] = 0
    if config.get("seed") is not None:
        env_cfg.seed = int(config["seed"])
    if config.get("mode") == "train":
        rl_cfg.experiment_name = str(config.get("experiment_name", "legged_studio_native"))
        rl_cfg.logger = str(config.get("logger", "tensorboard"))
    applied = apply_config_overrides(env_cfg, rl_cfg, config)
    if config.get("smoke_preset"):
        from backend.training.smoke_gate import SMOKE_MAX_ENVS, SMOKE_MAX_ITERS

        # Validate final expert edits rather than silently changing their requested scale.
        for path, value, maximum in (
            ("environment.scene.num_envs", env_cfg.scene.num_envs, SMOKE_MAX_ENVS),
            ("runner.max_iterations", rl_cfg.max_iterations, SMOKE_MAX_ITERS),
        ):
            if not 1 <= value <= maximum:
                raise ValueError(f"smoke_preset requires {path} within [1, {maximum}]; got {value}")
    report = {"recipe": recipe, "overrides_applied": applied}
    snapshot = {
        "schema": "training-effective-config-1.0",
        "environment": dump_config_tree(env_cfg),
        "runner": dump_config_tree(rl_cfg),
        "provenance": {"profile_id": (profile or {}).get("profile_id", config.get("profile_id")),
                       "overrides_applied": applied},
    }
    return AssembledTrainingConfig(env_cfg, rl_cfg, report, snapshot)


