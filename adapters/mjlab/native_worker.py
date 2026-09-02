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


def _go2w_base_lin_vel_xy(env, sensor_name: str = "robot/local_linvel"):
    """Return planar base velocity for the 56D Go2W actor contract."""
    from mjlab.envs.mdp.observations import builtin_sensor

    return builtin_sensor(env, sensor_name)[..., :2]


def _register_go2w_task(project_root: Path, register_mjlab_task, load_env_cfg, load_rl_cfg) -> None:
    """Register a wheel-leg task using the versioned Legged Studio Go2W MJCF."""
    import mujoco
    from mjlab.actuator import BuiltinPositionActuatorCfg, BuiltinVelocityActuatorCfg
    from mjlab.entity import EntityArticulationInfoCfg, EntityCfg
    from mjlab.envs.mdp.actions import JointPositionActionCfg, JointVelocityActionCfg

    xml_path = project_root / "assets" / "robots" / "unitree_go2w" / "go2w.xml"
    asset_dir = xml_path.parent / "assets"

    def get_spec():
        spec = mujoco.MjSpec.from_file(str(xml_path))
        spec.assets = {item.name: item.read_bytes() for item in asset_dir.iterdir() if item.is_file()}
        return spec

    robot = EntityCfg(
        init_state=EntityCfg.InitialStateCfg(pos=(0.0, 0.0, 0.38), joint_pos={".*": 0.0}, joint_vel={".*": 0.0}),
        collisions=(),
        spec_fn=get_spec,
        articulation=EntityArticulationInfoCfg(actuators=(
            BuiltinPositionActuatorCfg(target_names_expr=(".*_hip_joint", ".*_thigh_joint", ".*_calf_joint"), stiffness=20.0, damping=1.0, effort_limit=45.0, armature=0.01),
            BuiltinVelocityActuatorCfg(target_names_expr=(".*_wheel_joint",), damping=0.5, effort_limit=15.0, armature=0.0042),
        ), soft_joint_pos_limit_factor=0.9),
    )
    env_cfg = copy.deepcopy(load_env_cfg("Unitree-Go2-Flat"))
    play_cfg = copy.deepcopy(load_env_cfg("Unitree-Go2-Flat", play=True))
    env_cfg.scene.entities = {"robot": robot}
    play_cfg.scene.entities = {"robot": copy.deepcopy(robot)}
    # 16D wheel-leg action contract: 12 joint positions + 4 wheel velocities.
    env_cfg.actions = {
        "joint_pos": JointPositionActionCfg(entity_name="robot", actuator_names=(".*_(hip|thigh|calf)_joint",), scale=0.25, use_default_offset=True),
        "wheel_vel": JointVelocityActionCfg(entity_name="robot", actuator_names=(".*_wheel_joint",), scale=6.0, use_default_offset=False),
    }
    play_cfg.actions = copy.deepcopy(env_cfg.actions)
    # Keep the 56D Go2W actor contract: gait phase (2) replaces command (3).
    for cfg in (env_cfg, play_cfg):
        actor = cfg.observations["actor"]
        actor.terms.pop("command", None)
        actor.terms.pop("phase", None)
        actor.terms["base_lin_vel"] = copy.deepcopy(cfg.observations["critic"].terms["base_lin_vel"])
        actor.terms["base_ang_vel"].params["sensor_name"] = "robot/gyro"
        actor.terms["base_lin_vel"].params["sensor_name"] = "robot/local_linvel"
        actor.terms["base_lin_vel"].func = _go2w_base_lin_vel_xy
        cfg.observations["critic"].terms["base_ang_vel"].params["sensor_name"] = "robot/gyro"
        cfg.observations["critic"].terms["base_lin_vel"].params["sensor_name"] = "robot/local_linvel"
        # Go2W MJCF uses unnamed collision geoms, so the Go2 contact-sensor
        # patterns cannot be resolved. Keep the wheel-leg flat task free of
        # those optional sensors and contact-dependent terms.
        cfg.scene.sensors = ()
        for group in cfg.observations.values():
            for name in ("height_scan", "foot_height", "foot_air_time", "foot_contact", "foot_contact_forces"):
                group.terms.pop(name, None)
        for name in ("feet_ground_contact", "foot_gait", "soft_landing", "self_collision", "thigh_ground_touch", "shank_ground_touch", "trunk_head_ground_touch", "foot_clearance", "foot_slip", "air_time", "illegal_contact", "pose", "angular_momentum"):
            cfg.rewards.pop(name, None)
            cfg.terminations.pop(name, None)
        for name in ("foot_friction", "foot_friction_slide", "foot_friction_spin", "foot_friction_roll"):
            cfg.events.pop(name, None)
    register_mjlab_task("Unitree-Go2W-Flat", env_cfg, play_cfg, load_rl_cfg("Unitree-Go2-Flat"))


def run(config: dict, source: Path, output: Path, extension_root: Path | None = None) -> int:
    _write(output / "status.json", {"status": "running", "backend": "native_mjlab"})
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    sys.path.insert(0, str(source / "src"))
    if extension_root and extension_root.exists():
        sys.path.insert(0, str(extension_root))
        # Unitree's extension targets the pre-1.6 helper name. Keep the
        # compatibility shim local to this isolated process.
        import mjlab.utils.os as mjlab_os
        if not hasattr(mjlab_os, "update_assets"):
            def update_assets(assets, asset_dir, _meshdir):
                for asset in Path(asset_dir).rglob("*"):
                    if asset.is_file():
                        assets[asset.name] = asset.read_bytes()
            mjlab_os.update_assets = update_assets
    import torch
    import mjlab.tasks  # noqa: F401
    if extension_root and (extension_root / "src" / "tasks").exists():
        # Avoid importing every historical Unitree task: older configs use
        # CollisionCfg fields removed in MJLab 1.6. Load only Go2 velocity.
        import types
        tasks_pkg = types.ModuleType("src.tasks")
        tasks_pkg.__path__ = [str(extension_root / "src" / "tasks")]
        sys.modules.setdefault("src.tasks", tasks_pkg)
        assets_pkg = types.ModuleType("src.assets")
        assets_pkg.__path__ = [str(extension_root / "src" / "assets")]
        sys.modules.setdefault("src.assets", assets_pkg)
        robots_pkg = types.ModuleType("src.assets.robots")
        robots_pkg.__path__ = [str(extension_root / "src" / "assets" / "robots")]
        sys.modules.setdefault("src.assets.robots", robots_pkg)
        go2_constants = __import__("src.assets.robots.unitree_go2.go2_constants", fromlist=["get_go2_robot_cfg"])
        robots_pkg.get_go2_robot_cfg = go2_constants.get_go2_robot_cfg
        import src.tasks.velocity.config.go2  # noqa: F401
    if config.get("native_task_id") == "Unitree-Go2W-Flat":
        from mjlab.tasks.registry import register_mjlab_task, load_env_cfg, load_rl_cfg
        _register_go2w_task(project_root, register_mjlab_task, load_env_cfg, load_rl_cfg)
    from mjlab.envs import ManagerBasedRlEnv
    from mjlab.tasks.registry import list_tasks, load_env_cfg, load_rl_cfg

    task_id = config.get("native_task_id") or config.get("task_name")
    tasks = list_tasks()
    report = {
        "backend": "native_mjlab",
        "task_id": task_id,
        "registered_tasks": tasks,
        "torch_version": torch.__version__,
        "cuda_available": bool(torch.cuda.is_available()),
    }
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
    env_cfg.scene.num_envs = max(1, int(config.get("num_envs", env_cfg.scene.num_envs)))
    actor_terms = env_cfg.observations.get("actor")
    critic_terms = env_cfg.observations.get("critic")
    if task_id != "Unitree-Go2W-Flat" and actor_terms and critic_terms and "phase" in actor_terms.terms and "base_lin_vel" in critic_terms.terms:
        # Match the unified Go2 Contract actor layout: 3 base linear velocity
        # values replace the extension's 2-value gait phase.
        actor_terms.terms.pop("phase", None)
        actor_terms.terms["base_lin_vel"] = critic_terms.terms["base_lin_vel"]
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
        })
        if config.get("mode") == "train":
            started = time.time()
            from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper
            rl_cfg = load_rl_cfg(task_id)
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
