"""Python worker for the isolated MJLab training environment."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mjlab-path", required=True)
    parser.add_argument("--rsl-rl-path", required=True)
    parser.add_argument("--robolab-src", required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list")

    def add_common(command: argparse.ArgumentParser) -> None:
        command.add_argument("--task", default="Mjlab-Velocity-Flat-Unitree-Go1")
        command.add_argument("--num-envs", type=int, default=1)
        command.add_argument("--device", default="cuda:0")
        command.add_argument("--seed", type=int, default=0)

    smoke = subparsers.add_parser("smoke")
    add_common(smoke)
    train = subparsers.add_parser("train")
    add_common(train)
    train.add_argument("--max-iterations", type=int, default=1)
    train.add_argument("--checkpoint-interval", type=int, default=300)
    train.add_argument("--run-dir", required=True)
    train.add_argument("--resume-from")
    train.add_argument("--recipe")
    play = subparsers.add_parser("play")
    add_common(play)
    play.add_argument("--checkpoint", required=True)
    play.add_argument("--steps", type=int, default=256)
    play.add_argument(
        "--visualize",
        action="store_true",
        help="run the MJLab web-based Viser viewer until it is closed",
    )
    evaluate = subparsers.add_parser("evaluate")
    add_common(evaluate)
    evaluate.add_argument("--checkpoint", required=True)
    evaluate.add_argument("--steps", type=int, default=512)
    return parser


def _configure_paths(args: argparse.Namespace) -> None:
    for source in (args.robolab_src, args.mjlab_path, args.rsl_rl_path):
        source = str(Path(source).resolve())
        if source not in sys.path:
            sys.path.insert(0, source)


def _register_robolab_tasks() -> None:
    """Import RoboLab-owned MJLab tasks after the native registry is available."""

    import robolab.frameworks.mjlab.a1_task  # noqa: F401
    from robolab.frameworks.mjlab.semantic_tasks import register_semantic_tasks

    register_semantic_tasks()


def _emit(value: dict) -> None:
    print("ROBO_RESULT=" + json.dumps(value, sort_keys=True))


def _imports():
    import torch
    import mjlab.tasks  # noqa: F401 - populate the native task registry.
    _register_robolab_tasks()
    from mjlab.envs import ManagerBasedRlEnv
    from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper
    from mjlab.tasks.registry import (
        list_tasks,
        load_env_cfg,
        load_rl_cfg,
        load_runner_cls,
    )

    return (
        torch,
        ManagerBasedRlEnv,
        MjlabOnPolicyRunner,
        RslRlVecEnvWrapper,
        list_tasks,
        load_env_cfg,
        load_rl_cfg,
        load_runner_cls,
    )


def _make_env(args: argparse.Namespace, *, play: bool):
    (
        torch,
        ManagerBasedRlEnv,
        _runner,
        RslRlVecEnvWrapper,
        _list_tasks,
        load_env_cfg,
        load_rl_cfg,
        _load_runner_cls,
    ) = _imports()
    env_cfg = load_env_cfg(args.task, play=play)
    env_cfg.scene.num_envs = args.num_envs
    env_cfg.seed = args.seed
    env = ManagerBasedRlEnv(cfg=env_cfg, device=args.device)
    agent_cfg = load_rl_cfg(args.task)
    wrapped = RslRlVecEnvWrapper(env, clip_actions=agent_cfg.clip_actions)
    return torch, wrapped, env_cfg, agent_cfg


def _load_policy(args: argparse.Namespace, env, agent_cfg):
    from mjlab.rl import MjlabOnPolicyRunner
    from mjlab.tasks.registry import load_runner_cls

    runner_cls = load_runner_cls(args.task) or MjlabOnPolicyRunner
    runner = runner_cls(env, asdict(agent_cfg), device=args.device)
    runner.load(args.checkpoint, load_cfg={"actor": True}, strict=True, map_location=args.device)
    return runner.get_inference_policy(device=args.device)


def _run_policy(args: argparse.Namespace, *, evaluation: bool) -> dict:
    from robolab.frameworks.mjlab.visualization import scene_frame_from_mjlab

    torch, env, env_cfg, agent_cfg = _make_env(args, play=True)
    policy = _load_policy(args, env, agent_cfg)
    if args.visualize and not evaluation:
        from mjlab.viewer import ViserPlayViewer

        print("[INFO] Starting MJLab Viser web viewer; close the viewer to exit.", flush=True)
        ViserPlayViewer(env, policy).run()
        env.close()
        return {
            "backend": "mjlab",
            "task_id": args.task,
            "checkpoint": str(Path(args.checkpoint).resolve()),
            "mode": "viser",
            "viewer": "mjlab",
        }
    try:
        obs = env.get_observations()
        rewards: list[float] = []
        velocity_errors: list[float] = []
        commanded: list[float] = []
        actual: list[float] = []
        done_count = 0
        last_frame = None
        for _ in range(args.steps):
            command_term = env.unwrapped.command_manager.get_term("twist")
            command = command_term.command[:, 0]
            robot = env.unwrapped.scene["robot"]
            measured = robot.data.root_link_lin_vel_b[:, 0]
            with torch.no_grad():
                actions = policy(obs)
            obs, reward, done, _ = env.step(actions)
            rewards.append(float(reward.mean().item()))
            velocity_errors.append(float((command - measured).abs().mean().item()))
            commanded.append(float(command.mean().item()))
            actual.append(float(measured.mean().item()))
            done_count += int(done.sum().item())
            last_frame = scene_frame_from_mjlab(
                env, env_idx=0, reward=float(reward[0].item())
            )
        return {
            "backend": "mjlab",
            "task_id": args.task,
            "checkpoint": str(Path(args.checkpoint).resolve()),
            "num_envs": args.num_envs,
            "steps": args.steps,
            "mean_reward": sum(rewards) / len(rewards),
            "mean_commanded_forward_velocity": sum(commanded) / len(commanded),
            "mean_forward_velocity": sum(actual) / len(actual),
            "mean_abs_forward_tracking_error": sum(velocity_errors) / len(velocity_errors),
            "done_count": done_count,
            "mode": "evaluate" if evaluation else "play",
            "scene_frame": last_frame.to_dict() if last_frame is not None else None,
        }
    finally:
        env.close()


def _train(args: argparse.Namespace) -> dict:
    _register_robolab_tasks()
    from mjlab.scripts.train import TrainConfig, run_train
    from mjlab.tasks.registry import load_env_cfg, load_rl_cfg

    if args.device.startswith("cuda"):
        os.environ["CUDA_VISIBLE_DEVICES"] = args.device.partition(":")[2] or "0"
    else:
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
    run_dir = Path(args.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    env_cfg = load_env_cfg(args.task)
    recipe = {}
    if args.recipe:
        with open(args.recipe, encoding="utf-8") as stream:
            recipe = json.load(stream)
    control = recipe.get("control", {})
    if "decimation" in control:
        env_cfg.decimation = int(control["decimation"])
    action = env_cfg.actions.get("joint_pos")
    if action is not None and "action_scale" in control:
        action.scale = float(control["action_scale"])
    if "target_height" in control:
        entity = env_cfg.scene.entities.get("robot")
        if entity is not None:
            entity.init_state.pos = (0.0, 0.0, float(control["target_height"]))
    articulation = getattr(env_cfg.scene.entities["robot"], "articulation", None)
    actuators = getattr(articulation, "actuators", ())
    if "kp" in control or "kd" in control:
        for actuator in actuators:
            if "kp" in control and hasattr(actuator, "stiffness"):
                actuator.stiffness = float(control["kp"])
            if "kd" in control and hasattr(actuator, "damping"):
                actuator.damping = float(control["kd"])
    env_cfg.scene.num_envs = args.num_envs
    agent_cfg = load_rl_cfg(args.task)
    agent_cfg.seed = args.seed
    agent_cfg.max_iterations = args.max_iterations
    agent_cfg.save_interval = args.checkpoint_interval
    agent_cfg.logger = "tensorboard"
    agent_cfg.upload_model = False
    experiment_name = agent_cfg.experiment_name
    if args.resume_from:
        checkpoint = Path(args.resume_from).resolve()
        agent_cfg.resume = True
        agent_cfg.load_run = checkpoint.parent.name
        agent_cfg.load_checkpoint = checkpoint.name
        log_root = checkpoint.parent.parent.parent
        experiment_name = checkpoint.parent.parent.name
    else:
        log_root = run_dir.parent
    cfg = TrainConfig(
        env=env_cfg,
        agent=agent_cfg,
        log_root=str(log_root),
    )
    cfg.agent.experiment_name = experiment_name
    run_train(args.task, cfg, run_dir)
    checkpoints = sorted(run_dir.glob("model_*.pt"))
    if not checkpoints:
        raise RuntimeError(f"MJLab training produced no checkpoint in {run_dir}")
    checkpoint = checkpoints[-1]
    result = {
        "backend": "mjlab",
        "task_id": args.task,
        "num_envs": args.num_envs,
        "max_iterations": args.max_iterations,
        "checkpoint_interval": args.checkpoint_interval,
        "seed": args.seed,
        "run_dir": str(run_dir),
        "checkpoint": str(checkpoint),
        "resumed_from": str(Path(args.resume_from).resolve()) if args.resume_from else None,
    }
    resolved_config = {
        "backend": "mjlab",
        "task": args.task,
        "method": "ppo",
        "robot": "unitree_go1",
        "seed": args.seed,
        "num_envs": args.num_envs,
        "device": args.device,
        "max_iterations": args.max_iterations,
        "resume_from": result["resumed_from"],
        "mjlab_path": str(Path(args.mjlab_path).resolve()),
        "rsl_rl_path": str(Path(args.rsl_rl_path).resolve()),
        "recipe": recipe,
    }
    with open(run_dir / "resolved_config.json", "w", encoding="utf-8") as stream:
        json.dump(resolved_config, stream, indent=2, sort_keys=True)
    with open(run_dir / "robolab_metrics.json", "w", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
    return result


def _smoke(args: argparse.Namespace) -> dict:
    torch, env, _env_cfg, _agent_cfg = _make_env(args, play=False)
    try:
        observations = env.get_observations()
        actor_obs = observations["actor"]
        critic_obs = observations["critic"]
        action = torch.zeros((args.num_envs, env.num_actions), device=args.device)
        next_observations, reward, terminated, _ = env.step(action)
        action_term = env.unwrapped.action_manager.get_term("joint_pos")
        return {
            "backend": "mjlab",
            "task_id": args.task,
            "device": args.device,
            "num_envs": args.num_envs,
            "actor_observation_shape": list(actor_obs.shape),
            "critic_observation_shape": list(critic_obs.shape),
            "action_shape": list(action.shape),
            "action_joint_order": list(action_term.target_names),
            "control_dt": env.unwrapped.step_dt,
            "next_actor_observation_shape": list(next_observations["actor"].shape),
            "reward_shape": list(reward.shape),
            "terminated_shape": list(terminated.shape),
            "truncated_shape": list(terminated.shape),
        }
    finally:
        env.close()


def main() -> int:
    args = _parser().parse_args()
    _configure_paths(args)
    if args.command == "list":
        import mjlab.tasks  # noqa: F401
        _register_robolab_tasks()
        from mjlab.tasks.registry import list_tasks

        _emit({"backend": "mjlab", "tasks": list_tasks()})
        return 0
    if args.command == "smoke":
        _emit(_smoke(args))
        return 0
    if args.command == "train":
        _emit(_train(args))
        return 0
    if args.command == "play":
        _emit(_run_policy(args, evaluation=False))
        return 0
    _emit(_run_policy(args, evaluation=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
