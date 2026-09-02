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
from pathlib import Path


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def apply_training_recipe(env_cfg, rl_cfg, config: dict) -> dict:
    """Apply the canonical Web/CLI recipe to real MJLab config objects."""
    recipe = config.get("resolved_recipe") or config.get("recipe") or {}
    environment = recipe.get("environment", {}) if isinstance(recipe, dict) else {}
    rewards = recipe.get("reward_scales", {}) if isinstance(recipe, dict) else {}
    rewards = rewards or config.get("reward_scales", {})
    terrain_type = str(environment.get("terrain_type", config.get("terrain_type", "plane"))).lower()
    if terrain_type not in {"plane", "rough"}:
        raise ValueError(f"native MJLab training supports terrain_type plane or rough; got {terrain_type!r}")
    terrain = getattr(getattr(env_cfg, "scene", None), "terrain", None)
    if terrain is not None:
        if terrain_type == "plane":
            terrain.terrain_type = "plane"
            terrain.terrain_generator = None
        elif terrain.terrain_generator is None:
            raise ValueError("rough terrain recipe requires an MJLab terrain generator")

    aliases = {
        "tracking_lin_vel": "track_linear_velocity", "tracking_ang_vel": "track_angular_velocity",
        "orientation": "body_orientation_l2", "torques": "joint_torques_l2", "dof_vel": "joint_vel_l2",
        "dof_acc": "joint_acc_l2", "action_rate": "action_rate_l2", "collision": "illegal_contact",
        "feet_air_time": "air_time", "base_height": "upright", "stumble": "body_orientation_l2",
    }
    reward_terms = getattr(env_cfg, "rewards", {})
    unmatched = []
    for name, weight in rewards.items():
        target = name if name in reward_terms else aliases.get(name)
        if target not in reward_terms:
            if float(weight) == 0.0:
                continue
            unmatched.append(name)
            continue
        reward_terms[target].weight = float(weight)
    if unmatched:
        raise ValueError(f"reward terms are not available in MJLab task {unmatched}")

    reward_params = (environment.get("reward_params") if isinstance(environment, dict) else None) or config.get("reward_params", {})
    for name, params in reward_params.items():
        target = name if name in reward_terms else aliases.get(name)
        if target not in reward_terms or not isinstance(params, dict):
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


def run(config: dict, source: Path, output: Path, extension_root: Path | None = None) -> int:
    _write(output / "status.json", {"status": "running", "backend": "native_mjlab"})
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    sys.path.insert(0, str(source / "src"))
    package = config.get("robot_package") or {}
    generic_bundle = None
    import torch
    import mjlab.tasks  # noqa: F401
    from mjlab.envs import ManagerBasedRlEnv
    from mjlab.tasks.registry import list_tasks, load_env_cfg, load_rl_cfg, register_mjlab_task

    # Generic tasks are registered dynamically from the imported Robot Contract.
    # This path is opt-in so historical extension tasks remain untouched while
    # Web/CLI callers can train any valid MJCF asset without a robot-id branch.
    if config.get("generic_task", True):
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
    }
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

    env_cfg = load_env_cfg(task_id)
    rl_cfg = load_rl_cfg(task_id)
    recipe_report = apply_training_recipe(env_cfg, rl_cfg, config)
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
            # Keep the isolated worker offline by default. The Unitree
            # extension's wandb writer is incompatible with newer wandb.
            rl_cfg.logger = str(config.get("logger", "tensorboard"))
            wrapped = RslRlVecEnvWrapper(env, clip_actions=rl_cfg.clip_actions)
            runner = MjlabOnPolicyRunner(wrapped, asdict(rl_cfg), str(output), device)
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
            rl_cfg = load_rl_cfg(task_id)
            rl_cfg.logger = "tensorboard"
            wrapped = RslRlVecEnvWrapper(env, clip_actions=rl_cfg.clip_actions)
            runner = MjlabOnPolicyRunner(wrapped, asdict(rl_cfg), device)
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
            rl_cfg = load_rl_cfg(task_id)
            rl_cfg.logger = "tensorboard"
            wrapped = RslRlVecEnvWrapper(env, clip_actions=rl_cfg.clip_actions)
            runner = MjlabOnPolicyRunner(wrapped, asdict(rl_cfg), device)
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
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))
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
