"""Isolated MJLab worker used for native preflight and environment smoke tests.

The control-plane never imports MJLab. This process owns the MJLab source path,
optional CUDA runtime, and manager-based environment lifecycle.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from dataclasses import asdict
import time
import shutil
import copy
import importlib
import inspect
import importlib.metadata
from pathlib import Path



def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def apply_training_recipe(env_cfg, rl_cfg, config: dict, *, preserve_profile: bool = False) -> dict:
    """Apply the canonical Web/CLI recipe to real MJLab config objects."""
    recipe = config.get("resolved_recipe") or config.get("recipe") or {}
    environment = recipe.get("environment", {}) if isinstance(recipe, dict) else {}
    rewards = recipe.get("reward_scales", {}) if isinstance(recipe, dict) else {}
    rewards = rewards or config.get("reward_scales", {})
    if preserve_profile and not config.get("reward_overrides", False):
        rewards = {}
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
        "feet_air_time": "feet_air_time", "wheel_roll_tracking": "wheel_roll_tracking",
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
            if float(weight) == 0.0:
                continue
            unmatched.append(name)
            continue
        reward_terms[target].weight = float(weight)
    if unmatched and not preserve_profile:
        raise ValueError(f"reward terms are not available in MJLab task {unmatched}")

    reward_params = (environment.get("reward_params") if isinstance(environment, dict) else None) or config.get("reward_params", {})
    if preserve_profile and not config.get("reward_overrides", False):
        reward_params = {}
    for name, params in reward_params.items():
        target = resolve_term(name)
        if target not in reward_terms or not isinstance(params, dict):
            if preserve_profile:
                continue
            raise ValueError(f"reward parameter target is not available in MJLab task: {name}")
        term_params = getattr(reward_terms[target], "params", None)
        if isinstance(term_params, dict):
            term_params.update(params)
        else:
            for key, value in params.items():
                if hasattr(term_params, key): setattr(term_params, key, value)

    command_ranges = (environment.get("command_ranges") if isinstance(environment, dict) else None) or config.get("command_ranges", {})
    if command_ranges:
        command = getattr(env_cfg, "commands", {}).get("twist")
        ranges = getattr(command, "ranges", None)
        if ranges is not None:
            for key, value in command_ranges.items():
                target = "ang_vel_z" if key in {"wz", "ang_vel_yaw"} else "lin_vel_x" if key in {"vx", "lin_vel_x"} else "lin_vel_y" if key in {"vy", "lin_vel_y"} else key
                if hasattr(ranges, target): setattr(ranges, target, tuple(value))
                elif value is not None: raise ValueError(f"command range is not supported by MJLab: {key}")

    if hasattr(env_cfg, "episode_length_s"):
        env_cfg.episode_length_s = float(environment.get("episode_length_s", config.get("episode_length_s", env_cfg.episode_length_s)))
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


def _load_profile_bundle(profile: dict, package: dict, config: dict):
    """Load an isolated package profile without robot-id-specific branches."""
    package_root = Path(str(package.get("package_root", ""))).resolve()
    source_root = package_root / str(profile.get("source_root", "training/source"))
    if not source_root.exists():
        raise FileNotFoundError(f"profile source root not found: {source_root}")
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))
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
    # MJLab profiles commonly export a runner config instance (for example
    # ``MicroduckRlCfg = RslRlOnPolicyRunnerCfg(...)``) rather than a factory.
    # Accept both forms so package authors do not need a platform-specific
    # wrapper.
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


def _load_package_extension(package: dict) -> dict:
    """Load a package-owned MJLab extension declared by its manifest.

    Extensions are deliberately data-driven: a package may expose an
    ``extension_entrypoint`` (``module:register``) and optional
    ``extension_root``.  The worker never branches on robot identity and the
    shared MJLab source tree remains untouched.
    """
    entrypoint = package.get("extension_entrypoint") or package.get("extension_module")
    if not entrypoint:
        return {}
    package_root = Path(str(package.get("package_root", ""))).resolve()
    extension_root = package.get("extension_root")
    if extension_root:
        root = Path(str(extension_root))
        if not root.is_absolute():
            root = package_root / root
        if root.exists() and str(root) not in sys.path:
            sys.path.insert(0, str(root))
    # Package source is always available for its extension module, even when
    # the selected profile has a different source_root.
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))
    register = _import_entrypoint(str(entrypoint))
    result = _call_factory(register)
    return result if isinstance(result, dict) else {"result": result}


def run(config: dict, source: Path, output: Path, extension_root: Path | None = None) -> int:
    _write(output / "status.json", {"status": "running", "backend": "native_mjlab"})
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from adapters.mjlab.runtime_compat import evaluate_package_runtime
    sys.path.insert(0, str(source / "src"))
    package = config.get("robot_package") or {}
    generic_bundle = None
    profile = None
    profile_id = config.get("profile_id")
    if profile_id:
        profile_root = Path(str(package.get("package_root", ""))) / "training" / "profiles"
        for profile_path in profile_root.glob("*.json") if profile_root.exists() else []:
            try:
                candidate = json.loads(profile_path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                continue
            if candidate.get("profile_id") == profile_id:
                profile = candidate
                break
        if profile is None:
            raise ValueError(f"training profile not found in robot package: {profile_id}")
        config["package_profile"] = profile
    extension_report = _load_package_extension(package)
    import torch
    import mjlab
    import mjlab.tasks  # noqa: F401
    from mjlab.envs import ManagerBasedRlEnv
    from mjlab.tasks.registry import list_tasks, load_env_cfg, load_rl_cfg, load_runner_cls, register_mjlab_task

    # Generic tasks are registered dynamically from the imported Robot Contract.
    # This path is opt-in so historical extension tasks remain untouched while
    # Web/CLI callers can train any valid MJCF asset without a robot-id branch.
    profile_bundle = None
    if profile:
        profile_bundle = _load_profile_bundle(profile, package, config)
        from mjlab.tasks.registry import register_mjlab_task
        profile_task_id = str(config.get("native_task_id") or f"LeggedStudio-{profile.get('profile_id')}")
        runner_cls = None
        runner_entrypoint = (profile.get("entrypoints") or {}).get("runner_class")
        if runner_entrypoint:
            runner_cls = _import_entrypoint(runner_entrypoint)
        register_mjlab_task(profile_task_id, profile_bundle[0], profile_bundle[1], profile_bundle[2], runner_cls=runner_cls)
        config["native_task_id"] = profile_task_id
        config["profile_task"] = True
    if config.get("generic_task", True) and profile_bundle is None:
        contract_path = config.get("contract_path")
        if not contract_path:
            raise ValueError("generic MJLab task requires contract_path")
        from contracts.robot_contract_v2 import RobotContractV2
        from adapters.mjlab.generic_task_builder import build_generic_task

        contract = RobotContractV2.from_json_file(str(contract_path))
        bundle = build_generic_task(
            contract,
            config.get("resolved_recipe") or config.get("recipe") or config,
            asset_root=package.get("package_root") or Path(__file__).resolve().parents[2],
            task_id=str(config.get("native_task_id") or "") or None,
        )
        register_mjlab_task(bundle.task_id, bundle.env_cfg, bundle.play_env_cfg, bundle.rl_cfg)
        config["native_task_id"] = bundle.task_id
        config["generic_task_diagnostics"] = bundle.diagnostics

    task_id = config.get("native_task_id") or config.get("task_name")
    tasks = list_tasks()
    report = {
        "backend": "native_mjlab",
        "task_id": task_id,
        "registered_tasks": tasks,
        "torch_version": torch.__version__,
        "cuda_available": bool(torch.cuda.is_available()),
        "package": {"package_id": package.get("package_id"), "task_kind": "generic", "capabilities": package.get("capabilities", [])},
        "profile": {"profile_id": profile.get("profile_id"), "source": profile.get("source")} if profile else None,
        "package_extension": extension_report or None,
    }
    try:
        mjlab_version = str(importlib.metadata.version("mjlab"))
    except importlib.metadata.PackageNotFoundError:
        mjlab_version = str(getattr(mjlab, "__version__", "")) or None
    report["package_compatibility"] = evaluate_package_runtime(
        package,
        {
            "mjlab_version": mjlab_version,
            "python_version": ".".join(str(value) for value in sys.version_info[:3]),
            "torch_version": str(torch.__version__),
        },
    )
    if report["package_compatibility"]["status"] != "compatible":
        report.update({"status": "runtime_incompatible", "error": "robot package runtime requirements are not satisfied"})
        _write(output / "native_preflight.json", report)
        return 4
    if config.get("generic_task"):
        report["generic_task"] = True
        report["generic_task_diagnostics"] = config.get("generic_task_diagnostics", {})
    if task_id not in tasks:
        report.update({"status": "unsupported_task", "error": f"task {task_id!r} is not registered by MJLab"})
        _write(output / "native_preflight.json", report)
        return 2

    requested = str(config.get("device", "auto")).lower()
    if requested == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    elif requested.startswith("cuda"):
        if not torch.cuda.is_available():
            report.update({"status": "device_unavailable", "error": "CUDA requested but unavailable"})
            _write(output / "native_preflight.json", report)
            return 3
        device = requested
    else:
        device = "cpu"

    if profile_bundle is not None:
        env_cfg, _play_env_cfg, rl_cfg = profile_bundle
    else:
        env_cfg = load_env_cfg(task_id)
        rl_cfg = load_rl_cfg(task_id)
    recipe_report = apply_training_recipe(env_cfg, rl_cfg, config, preserve_profile=profile_bundle is not None)
    env_cfg.scene.num_envs = max(1, int(config.get("num_envs", env_cfg.scene.num_envs)))
    actor_terms = env_cfg.observations.get("actor")
    critic_terms = env_cfg.observations.get("critic")
    # MJLab 1.6 requires structural collision dictionaries to have a default;
    # Unitree's extension was authored against the previous sparse-dict API.
    for entity_cfg in env_cfg.scene.entities.values():
        for collision_cfg in entity_cfg.collisions or ():
            if isinstance(collision_cfg.priority, dict) and ".*" not in collision_cfg.priority:
                collision_cfg.priority[".*"] = 0
    if config.get("seed") is not None:
        env_cfg.seed = int(config["seed"])
    env = None
    try:
        env = ManagerBasedRlEnv(cfg=env_cfg, device=device)
        obs, _ = env.reset()
        action_dim = env.action_manager.total_action_dim
        action = torch.zeros((env.num_envs, action_dim), device=device)
        _step = env.step(action)
        report.update({
            "status": "smoke_passed",
            "device": device,
            "num_envs": env.num_envs,
            "observation_groups": list(obs.keys()),
            "observation_dimensions": {name: list(value.shape[1:]) for name, value in obs.items()},
            "action_dim": action_dim,
            "recipe": recipe_report,
            "generic_task": config.get("generic_task_diagnostics"),
        })
        if config.get("mode") == "train":
            started = time.time()
            from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper
            rl_cfg.max_iterations = max(1, int(config.get("max_iterations", 1)))
            rl_cfg.num_steps_per_env = max(4, int(config.get("num_steps", rl_cfg.num_steps_per_env)))
            rl_cfg.experiment_name = str(config.get("experiment_name", "legged_studio_native"))
            # Keep the isolated worker offline by default. Package extensions
            # may carry optional writers; the control plane uses TensorBoard.
            rl_cfg.logger = str(config.get("logger", "tensorboard"))
            wrapped = RslRlVecEnvWrapper(env, clip_actions=rl_cfg.clip_actions)
            runner_type = load_runner_cls(task_id) or MjlabOnPolicyRunner
            runner = runner_type(wrapped, asdict(rl_cfg), str(output), device)
            runner.learn(num_learning_iterations=rl_cfg.max_iterations, init_at_random_ep_len=True)
            report["status"] = "train_completed"
            report["max_iterations"] = rl_cfg.max_iterations
            report["checkpoint_dir"] = str(output)
            model_path = output / f"model_{rl_cfg.max_iterations - 1}.pt"
            if not model_path.exists():
                candidates = sorted(output.glob("model_*.pt"))
                model_path = candidates[-1] if candidates else model_path
            if model_path.exists() and not (output / "model_final.pt").exists():
                shutil.copy2(model_path, output / "model_final.pt")
            contract_path = config.get("contract_path")
            if model_path.exists() and contract_path:
                from contracts.policy_artifact import TrainingMetrics, create_artifact_from_training
                from contracts.robot_contract_v2 import RobotContractV2
                contract = RobotContractV2.from_json_file(str(contract_path))
                logical_task = str(config.get("task_name", task_id)).lower().replace(" ", "_").replace("-", "_")
                artifact = create_artifact_from_training(
                    contract=contract,
                    task_name=logical_task,
                    algorithm=str(config.get("algorithm", "PPO")),
                    model_path=str(model_path.resolve()),
                    metrics=TrainingMetrics(
                        iterations=rl_cfg.max_iterations,
                        episodes=env.num_envs * rl_cfg.max_iterations,
                        success_rate=0.0,
                        avg_reward=0.0,
                        final_reward=0.0,
                        training_duration_seconds=time.time() - started,
                    ),
                    algorithm_config=asdict(rl_cfg),
                    obs_normalizer={"mean": [], "std": []},
                    mjlab_version="1.6.0-native",
                    tags=["native_mjlab", contract.robot_id],
                )
                artifact.to_json_file(str(output / "artifact.json"))
                report["artifact_id"] = artifact.artifact_id
        elif config.get("mode") == "evaluate":
            from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper
            checkpoint = Path(str(config.get("checkpoint", ""))).resolve()
            if not checkpoint.exists():
                raise FileNotFoundError(f"native checkpoint not found: {checkpoint}")
            if profile_bundle is None:
                rl_cfg = load_rl_cfg(task_id)
            rl_cfg.logger = "tensorboard"
            wrapped = RslRlVecEnvWrapper(env, clip_actions=rl_cfg.clip_actions)
            runner_type = load_runner_cls(task_id) or MjlabOnPolicyRunner
            runner = runner_type(wrapped, asdict(rl_cfg), str(output), device)
            runner.load(str(checkpoint), load_cfg={"actor": True}, strict=True, map_location=device)
            policy = runner.get_inference_policy(device=device)
            episodes = max(1, int(config.get("episodes", 1)))
            max_steps = max(1, int(config.get("max_steps", 500)))
            episode_rewards = []
            with torch.no_grad():
                for _ in range(episodes):
                    obs, _ = wrapped.reset()
                    total = 0.0
                    for _step_index in range(max_steps):
                        action = policy(obs)
                        obs, reward, dones, _extras = wrapped.step(action)
                        total += float(reward.mean().item())
                        if bool(dones.any().item()):
                            break
                    episode_rewards.append(total)
            report.update({"status": "evaluate_completed", "episodes": episodes, "avg_reward": sum(episode_rewards) / len(episode_rewards), "evaluated_env": "native_mjlab"})
            _write(output / "evaluation.json", report)
        elif config.get("mode") == "navigation":
            from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper
            checkpoint = Path(str(config.get("checkpoint", ""))).resolve()
            if not checkpoint.exists():
                raise FileNotFoundError(f"native checkpoint not found: {checkpoint}")
            if profile_bundle is None:
                rl_cfg = load_rl_cfg(task_id)
            rl_cfg.logger = "tensorboard"
            wrapped = RslRlVecEnvWrapper(env, clip_actions=rl_cfg.clip_actions)
            runner_type = load_runner_cls(task_id) or MjlabOnPolicyRunner
            runner = runner_type(wrapped, asdict(rl_cfg), str(output), device)
            runner.load(str(checkpoint), load_cfg={"actor": True}, strict=True, map_location=device)
            policy = runner.get_inference_policy(device=device)
            route = config.get("waypoints") or [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]]
            tolerance = float(config.get("waypoint_tolerance", 0.35))
            max_steps = max(1, int(config.get("max_steps", 500)))
            term = env.command_manager.get_term("twist")
            completions = []
            with torch.no_grad():
                for _ in range(max(1, int(config.get("episodes", 1)))):
                    obs, _ = wrapped.reset()
                    waypoint_index = 0
                    for _step_index in range(max_steps):
                        position = env.scene["robot"].data.root_link_pos_w[0, :2]
                        while waypoint_index < len(route):
                            initial_target = torch.as_tensor(route[waypoint_index], device=device, dtype=position.dtype)
                            if float(torch.linalg.norm(position - initial_target).item()) > tolerance:
                                break
                            waypoint_index += 1
                        if waypoint_index >= len(route):
                            break
                        target = torch.as_tensor(route[min(waypoint_index, len(route) - 1)], device=device, dtype=position.dtype)
                        delta = target - position
                        term.command[:] = torch.stack((torch.clamp(delta[0], -1.0, 1.0), torch.clamp(delta[1], -1.0, 1.0), torch.tensor(0.0, device=device)))
                        action = policy(obs)
                        obs, _reward, dones, _extras = wrapped.step(action)
                        position = env.scene["robot"].data.root_link_pos_w[0, :2]
                        if waypoint_index < len(route) and float(torch.linalg.norm(position - target).item()) <= tolerance:
                            waypoint_index += 1
                        if bool(dones.any().item()) or waypoint_index >= len(route):
                            break
                    completions.append(waypoint_index / len(route))
            report.update({"status": "navigation_completed", "route_completion": sum(completions) / len(completions), "waypoints": route, "evaluated_env": "native_mjlab_navigation"})
            _write(output / "navigation.json", report)
        _write(output / "native_preflight.json", report)
        _write(output / "status.json", {"status": "completed", **report})
        return 0
    finally:
        if env is not None:
            env.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Legged Studio native MJLab worker")
    parser.add_argument("--source", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--extension-root")
    parser.add_argument("--contract")
    args = parser.parse_args()
    output = Path(args.output)
    try:
        # PowerShell's ``-Encoding utf8`` emits a BOM on Windows; accepting
        # utf-8-sig keeps CLI and desktop launches interoperable.
        config = json.loads(Path(args.config).read_text(encoding="utf-8-sig"))
        if args.contract:
            config["contract_path"] = str(Path(args.contract).resolve())
        extension = Path(args.extension_root).resolve() if args.extension_root else None
        return run(config, Path(args.source).resolve(), output, extension)
    except Exception as exc:
        _write(output / "status.json", {"status": "failed", "error": str(exc), "traceback": traceback.format_exc()})
        print(f"[native-worker] failed: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
