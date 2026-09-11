"""Python 3.8-compatible worker for the legacy Isaac Gym runtime."""

import argparse
import copy
import gc
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace


def _parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--isaacgym-path", required=True)
    parser.add_argument("--legged-gym-path", required=True)
    parser.add_argument("--rsl-rl-path", required=True)
    parser.add_argument("--robolab-src", required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list")
    smoke = subparsers.add_parser("smoke")
    smoke.add_argument("--task", default="a1")
    smoke.add_argument("--num-envs", type=int, default=1)
    smoke.add_argument("--device", default="cuda:0")
    smoke.add_argument("--seed", type=int, default=0)
    smoke.add_argument("--method", default="ppo")
    train = subparsers.add_parser("train")
    train.add_argument("--task", default="a1")
    train.add_argument("--num-envs", type=int, default=1024)
    train.add_argument("--device", default="cuda:0")
    train.add_argument("--seed", type=int, default=0)
    train.add_argument("--max-iterations", type=int, default=1)
    train.add_argument("--checkpoint-interval", type=int, default=300)
    train.add_argument("--run-dir", required=True)
    train.add_argument("--resume-from")
    train.add_argument("--method", default="ppo")
    train.add_argument("--recipe")
    play = subparsers.add_parser("play")
    play.add_argument("--task", default="a1")
    play.add_argument("--num-envs", type=int, default=1)
    play.add_argument("--device", default="cuda:0")
    play.add_argument("--seed", type=int, default=0)
    play.add_argument("--steps", type=int, default=256)
    play.add_argument("--checkpoint", required=True)
    play.add_argument("--visualize", action="store_true")
    play.add_argument("--method", default="ppo")
    play.add_argument("--evaluation", action="store_true")
    return parser


def _configure_paths(args):
    method_root = Path(args.rsl_rl_path).resolve().parent
    for source in (args.robolab_src, method_root, args.legged_gym_path, args.rsl_rl_path, args.isaacgym_path):
        source = str(Path(source).resolve())
        if source not in sys.path:
            sys.path.insert(0, source)


def _load_recipe(args):
    path = getattr(args, "recipe", None)
    if not path:
        return {}
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _apply_recipe(task_registry, task, recipe):
    if not recipe:
        return
    env_cfg, _ = task_registry.get_cfgs(task)
    control = recipe.get("control", {})
    if "action_scale" in control:
        env_cfg.control.action_scale = float(control["action_scale"])
    if "decimation" in control:
        env_cfg.control.decimation = int(control["decimation"])
    if "kp" in control:
        env_cfg.control.stiffness = {"joint": float(control["kp"])}
    if "kd" in control:
        env_cfg.control.damping = {"joint": float(control["kd"])}
    joint_kp = recipe.get("joint_kp") or {}
    joint_kd = recipe.get("joint_kd") or {}
    if joint_kp:
        env_cfg.control.stiffness = {str(name): float(value) for name, value in joint_kp.items()}
    if joint_kd:
        env_cfg.control.damping = {str(name): float(value) for name, value in joint_kd.items()}
    if "target_height" in control and hasattr(env_cfg.rewards, "base_height_target"):
        env_cfg.rewards.base_height_target = float(control["target_height"])
    if recipe.get("use_standing_pose") and recipe.get("joint_defaults"):
        env_cfg.init_state.default_joint_angles = dict(recipe["joint_defaults"])


def _emit(value):
    print("ROBO_RESULT=" + json.dumps(value, sort_keys=True))


def _configure_play_terrain(task_registry, task, name):
    """Configure one deterministic Isaac Gym terrain tile for interactive play."""
    env_cfg, _ = task_registry.get_cfgs(task)
    # The registry stores one mutable config instance.  Never mutate it while
    # a previous simulation is still running; otherwise a failed switch can
    # corrupt the live environment's config.
    env_cfg = copy.deepcopy(env_cfg)
    terrain = env_cfg.terrain
    if name == "plane":
        terrain.mesh_type = "plane"
        return env_cfg

    # Isaac Gym terrain collision meshes are immutable after simulation
    # creation.  The worker therefore rebuilds the one-env simulation when a
    # Viser terrain control is changed.  A single tile keeps the robot at the
    # terrain that is currently displayed rather than silently sampling a
    # different column from a terrain curriculum.
    proportions = {
        "rough": [0.0, 1.0, 0.0, 0.0, 0.0],
        # ``Terrain.make_terrain`` uses cumulative proportions and chooses
        # stairs-down when choice < proportions[2].  With a single tile the
        # deterministic choice is ~0, so put the stairs bucket in slot 3 to
        # request stairs-up (positive support heights).
        "stairs": [0.0, 0.0, 0.0, 1.0, 0.0],
        "obstacles": [0.0, 0.0, 0.0, 0.0, 1.0],
    }
    if name not in proportions:
        raise ValueError("unknown terrain: %s" % name)
    # Heightfields are the most reliable collision primitive with the legacy
    # GPU PhysX backend.  The same height samples are serialized to Viser, so
    # the displayed surface and the collision surface remain identical.
    terrain.mesh_type = "heightfield"
    terrain.curriculum = True
    terrain.num_rows = 1
    terrain.num_cols = 1
    terrain.max_init_terrain_level = 0
    terrain.interactive_difficulty = 0.75
    terrain.terrain_proportions = proportions[name]
    return env_cfg


def _terrain_payload(env, name, revision):
    """Serialize the active collision tile for the out-of-process viewer."""
    payload = {"name": name, "revision": int(revision)}
    if name == "plane" or not hasattr(env, "terrain"):
        return payload
    terrain = env.terrain
    level = int(env.terrain_levels[0].item())
    terrain_type = int(env.terrain_types[0].item())
    x0 = terrain.border + level * terrain.length_per_env_pixels
    y0 = terrain.border + terrain_type * terrain.width_per_env_pixels
    x1 = x0 + terrain.length_per_env_pixels
    y1 = y0 + terrain.width_per_env_pixels
    payload.update(
        origin=[float(value) for value in env.env_origins[0].detach().cpu().tolist()],
        horizontal_scale=float(terrain.cfg.horizontal_scale),
        vertical_scale=float(terrain.cfg.vertical_scale),
        height_field=terrain.height_field_raw[x0:x1, y0:y1].tolist(),
    )
    return payload


def _place_robot_safely(env, gymtorch):
    """Place the freshly-created play robot at the center of its safe tile."""
    env.root_states[:] = env.base_init_state
    env.root_states[:, :3] += env.env_origins
    env.root_states[:, 7:13] = 0.0
    # legged_gym samples both initial body velocity and commands during reset.
    # Interactive play should start stationary; the Viser command sliders can
    # opt into motion explicitly.
    env.commands[:, :3] = 0.0
    env.commands[:, 3:] = 0.0
    env.cfg.commands.heading_command = False
    env.gym.set_actor_root_state_tensor(
        env.sim, gymtorch.unwrap_tensor(env.root_states)
    )
    env.gym.refresh_actor_root_state_tensor(env.sim)
    env.compute_observations()


def _start_viser_bridge(args):
    root = Path(args.robolab_src).resolve().parent
    python = Path(os.environ.get(
        "ROBO_MJLAB_PYTHON", "/home/lxy/miniconda3/envs/robolab-mjlab16/bin/python"
    )).expanduser()
    # scene.xml contains a standalone demo floor/staircase.  Isaac Gym owns
    # the real terrain, so loading that file gives the Viser viewer a second,
    # unrelated terrain with a different coordinate frame.  Use the robot
    # model only and let the bridge render the selected Isaac terrain.
    recipe = _load_recipe(args)
    if not recipe:
        try:
            with open(Path(args.checkpoint).resolve().parent / "resolved_config.json", encoding="utf-8") as stream:
                recipe = json.load(stream).get("recipe", {})
        except (OSError, ValueError):
            recipe = {}
    configured = recipe.get("visualization_model") or recipe.get("model")
    mjcf = (root / configured).resolve() if configured else root / "resources/robots/unitree_a1/xml/unitree_a1.xml"
    if not python.is_file():
        raise RuntimeError(f"MJLab Python runtime not found for Viser bridge: {python}")
    if not mjcf.is_file():
        raise RuntimeError(f"canonical A1 MJCF not found for Viser bridge: {mjcf}")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(args.robolab_src) + os.pathsep + environment.get("PYTHONPATH", "")
    # Viser belongs to this play session.  Offer checkpoints from the selected
    # run directory only, never every historical model under ``logs``.
    selected_checkpoint = Path(args.checkpoint).resolve()
    checkpoints = sorted(
        selected_checkpoint.parent.glob("model_*.pt"),
        key=lambda path: int(path.stem.rsplit("_", 1)[-1]),
    )
    if selected_checkpoint not in checkpoints:
        checkpoints.append(selected_checkpoint)
    checkpoints = tuple(str(path.resolve()) for path in checkpoints)
    control_port = int(os.environ.get("ROBO_VISER_CONTROL_PORT", "8766"))
    return subprocess.Popen(
        [str(python), "-m", "robolab.visualization.viser_bridge", "--mjcf", str(mjcf),
         "--initial-checkpoint", str(Path(args.checkpoint).resolve()), "--control-port", str(control_port), "--checkpoints", *checkpoints]
        + (["--terrain-sequence", "plane", "rough", "stairs", "obstacles"]
           if os.environ.get("ROBO_VISER_TERRAIN_TEST") == "1" else []),
        cwd=root, env=environment, stdin=subprocess.PIPE, text=True,
    )


def _connect_bridge_control():
    control_port = int(os.environ.get("ROBO_VISER_CONTROL_PORT", "8766"))
    for _ in range(100):
        try:
            return socket.create_connection(("127.0.0.1", control_port), timeout=0.2)
        except OSError:
            time.sleep(0.05)
    return None


def _checkpoint_is_compatible(path, method_id):
    config_path = Path(path).parent / "resolved_config.json"
    try:
        with open(config_path) as stream:
            config = json.load(stream)
    except (OSError, ValueError):
        return False
    return (
        config.get("framework") == "isaacgym"
        and config.get("method", "ppo") == method_id
        and bool(config.get("task"))
    )


def _send_scene_frame(process, frame, *, task="a1", step=0, metrics=None, network_output=(), terrain=None):
    if process is None or process.stdin is None or process.poll() is not None:
        return
    payload = {
        "scene_frame": frame.to_dict(),
        "training_frame": {
            "backend": "isaacgym",
            "task": task,
            "step": int(step),
            "metrics": dict(metrics or {}),
            "schema_version": 1,
        },
        "network_output": [float(value) for value in network_output],
        "terrain": terrain or {"name": "plane", "revision": 0},
    }
    process.stdin.write(json.dumps(payload) + "\n")
    process.stdin.flush()


def main():
    args = _parser().parse_args()
    _configure_paths(args)

    import isaacgym  # noqa: F401 - must be imported before torch.
    import legged_gym.envs  # noqa: F401 - populates the task registry.
    import torch
    from isaacgym import gymapi, gymtorch
    from legged_gym.utils import task_registry
    from robolab.frameworks.isaacgym.semantic_tasks import register_semantic_tasks

    register_semantic_tasks(task_registry)
    from robolab.frameworks.isaacgym.method_plugins import load_method_plugin
    method_plugin = load_method_plugin(getattr(args, "method", "ppo"))
    recipe = _load_recipe(args)
    if args.command != "list":
        args.task = method_plugin.register_task(task_registry, args.task)
        _apply_recipe(task_registry, args.task, recipe)

    tasks = sorted(task_registry.task_classes)
    if args.command == "list":
        _emit({"backend": "isaacgym", "tasks": tasks})
        return 0
    if args.task not in tasks:
        raise ValueError(f"Unknown task {args.task!r}; choose from {tasks}")

    device_type, _, device_id = args.device.partition(":")
    device_id = int(device_id or 0)
    use_gpu = device_type == "cuda"
    runtime_args = SimpleNamespace(
        task=args.task,
        resume=False,
        experiment_name=None,
        run_name=None,
        load_run=None,
        checkpoint=None,
        headless=True,
        horovod=False,
        rl_device=args.device,
        num_envs=args.num_envs,
        seed=args.seed,
        max_iterations=None,
        physics_engine=gymapi.SIM_PHYSX,
        device=device_type,
        use_gpu=use_gpu,
        use_gpu_pipeline=use_gpu,
        subscenes=0,
        num_threads=0,
        sim_device=args.device,
        sim_device_id=device_id,
        compute_device_id=device_id,
        graphics_device_id=-1,
        log_dir=(str(Path(args.run_dir).resolve()) if args.command == "train" else None),
    )
    env = None
    try:
        play_terrain = "plane"
        terrain_revision = 0
        if args.command == "play" and args.visualize:
            env_cfg = _configure_play_terrain(task_registry, args.task, play_terrain)
            env, _ = task_registry.make_env(name=args.task, args=runtime_args, env_cfg=env_cfg)
            _place_robot_safely(env, gymtorch)
        else:
            env, _ = task_registry.make_env(name=args.task, args=runtime_args)
            if args.command == "play" and not args.evaluation:
                _place_robot_safely(env, gymtorch)
        terrain_payload = _terrain_payload(env, play_terrain, terrain_revision)
        if args.command in ("train", "play"):
            checkpoint = args.resume_from if args.command == "train" else args.checkpoint
            runtime_args.resume = checkpoint is not None
            runner, train_cfg = method_plugin.make_runner(
                task_registry, env, args.task, runtime_args,
                log_dir=(str(Path(args.run_dir).resolve()) if args.command == "train" else None),
                checkpoint=checkpoint,
            )
            def _make_play_runner(target_env, checkpoint_path):
                method_runner, _ = method_plugin.make_runner(
                    task_registry, target_env, args.task, runtime_args,
                    log_dir=None, checkpoint=checkpoint_path,
                )
                return method_runner
            if args.command == "play":
                _place_robot_safely(env, gymtorch)
                if args.evaluation:
                    observations, _ = env.reset()
                policy = runner.get_inference_policy(device=env.device)
                observations = env.get_observations()
                rewards = []
                forward_velocity = []
                commanded_forward_velocity = []
                forward_tracking_error = []
                estimator_mse = []
                estimator_mae = []
                done_count = 0
                last_scene_frame = None
                from robolab.frameworks.isaacgym.visualization import scene_frame_from_isaacgym
                step = 0
                viser_bridge = None
                control_socket = None
                control_buffer = b""
                selected_checkpoint = str(Path(args.checkpoint).resolve())
                command_override = None
                last_frame_emit = 0.0
                next_control_tick = time.monotonic()
                if args.visualize:
                    viser_bridge = _start_viser_bridge(args)
                    control_socket = _connect_bridge_control()
                    if control_socket is not None:
                        control_socket.setblocking(False)
                    print("MJLab Viser bridge active at http://localhost:8080; stop with Ctrl-C.", flush=True)
                while args.steps <= 0 or step < args.steps:
                    if control_socket is not None:
                        try:
                            control_buffer += control_socket.recv(65536)
                        except (BlockingIOError, ConnectionResetError):
                            pass
                        while b"\n" in control_buffer:
                            raw, control_buffer = control_buffer.split(b"\n", 1)
                            try:
                                control = json.loads(raw.decode())
                            except (ValueError, UnicodeDecodeError):
                                continue
                            if control.get("type") == "command":
                                command_override = tuple(float(control.get(name, 0.0)) for name in ("vx", "vy", "vw"))
                            elif control.get("type") == "checkpoint":
                                candidate = Path(str(control.get("path", "")))
                                if (
                                    candidate.is_file()
                                    and candidate != Path(selected_checkpoint)
                                    and _checkpoint_is_compatible(candidate, args.method)
                                ):
                                    runner.load(str(candidate))
                                    policy = runner.get_inference_policy(device=env.device)
                                    selected_checkpoint = str(candidate)
                            elif control.get("type") == "terrain":
                                requested_terrain = str(control.get("name", "plane"))
                                if requested_terrain not in ("plane", "rough", "stairs", "obstacles"):
                                    continue
                                if requested_terrain != play_terrain:
                                    # Terrain collision geometry is fixed at Isaac Gym
                                    # simulation creation. Rebuild the one-env play
                                    # world, then reload the same policy.
                                    old_terrain = play_terrain
                                    candidate_env = None
                                    try:
                                        candidate_terrain = requested_terrain
                                        candidate_revision = terrain_revision + 1
                                        env_cfg = _configure_play_terrain(
                                            task_registry, args.task, candidate_terrain
                                        )
                                        # PhysX permits only one Foundation per
                                        # process. Destroy the old simulation
                                        # completely before creating its
                                        # replacement; two simultaneous sims
                                        # cause a native crash (SIGSEGV).
                                        old_env = env
                                        try:
                                            old_env.gym.destroy_sim(old_env.sim)
                                        finally:
                                            env = None
                                            del old_env
                                            # runner/policy/observations can
                                            # retain references to the old
                                            # environment and its tensors.
                                            runner = None
                                            policy = None
                                            observations = None
                                            gc.collect()
                                            if use_gpu:
                                                torch.cuda.empty_cache()
                                        candidate_env, _ = task_registry.make_env(
                                            name=args.task, args=runtime_args, env_cfg=env_cfg
                                        )
                                        _place_robot_safely(candidate_env, gymtorch)
                                        candidate_runner = _make_play_runner(
                                            candidate_env, selected_checkpoint
                                        )
                                        _place_robot_safely(candidate_env, gymtorch)
                                        candidate_policy = candidate_runner.get_inference_policy(
                                            device=candidate_env.device
                                        )
                                        candidate_observations = candidate_env.get_observations()
                                        candidate_payload = _terrain_payload(
                                            candidate_env, candidate_terrain, candidate_revision
                                        )
                                    except Exception as exc:
                                        status = getattr(exc, "__class__", type(exc)).__name__
                                        print(
                                            "Terrain switch failed (%s); keeping current terrain %s"
                                            % (status, old_terrain),
                                            flush=True,
                                        )
                                        if candidate_env is not None:
                                            try:
                                                candidate_env.gym.destroy_sim(candidate_env.sim)
                                            except Exception:
                                                pass
                                        # The old sim was necessarily destroyed
                                        # before the attempted switch. Recreate
                                        # it so the play loop remains usable.
                                        restore_cfg = _configure_play_terrain(
                                            task_registry, args.task, old_terrain
                                        )
                                        env, _ = task_registry.make_env(
                                            name=args.task, args=runtime_args, env_cfg=restore_cfg
                                        )
                                        _place_robot_safely(env, gymtorch)
                                        runner = _make_play_runner(env, selected_checkpoint)
                                        _place_robot_safely(env, gymtorch)
                                        policy = runner.get_inference_policy(device=env.device)
                                        observations = env.get_observations()
                                        terrain_payload = _terrain_payload(
                                            env, old_terrain, terrain_revision
                                        )
                                    else:
                                        # Commit after successful creation.
                                        env = candidate_env
                                        runner = candidate_runner
                                        policy = candidate_policy
                                        observations = candidate_observations
                                        play_terrain = candidate_terrain
                                        terrain_revision = candidate_revision
                                        terrain_payload = candidate_payload
                                        command_override = None
                                        print(
                                            "Terrain switch committed: %s revision=%d"
                                            % (play_terrain, terrain_revision),
                                            flush=True,
                                        )
                    if command_override is not None:
                        env.commands[:, 0] = command_override[0]
                        env.commands[:, 1] = command_override[1]
                        env.commands[:, 2] = command_override[2]
                        env.compute_observations()
                        observations = env.obs_buf
                    with torch.no_grad():
                        actions = policy(observations)
                        # PPO-EE exposes a supervised explicit state estimator.
                        # Keep this metric optional so the standard PPO plugin
                        # remains completely unchanged.
                        if (
                            getattr(args, "method", "ppo") == "ppo_ee"
                            and hasattr(runner, "policy")
                            and hasattr(runner.policy, "estimator")
                            and hasattr(env, "get_estimator_labels")
                        ):
                            estimate = runner.policy.estimator(observations)
                            labels = env.get_estimator_labels()
                            error = estimate - labels
                            estimator_mse.append(float(error.square().mean().item()))
                            estimator_mae.append(float(error.abs().mean().item()))
                    try:
                        observations, _, reward, done, _ = env.step(actions)
                    except SystemExit:
                        # The legacy legged_gym viewer closes by raising
                        # SystemExit from BaseTask.render(). Treat it as a
                        # normal end to an interactive play session.
                        break
                    rewards.append(float(reward.mean().item()))
                    done_count += int(done.sum().item())
                    last_scene_frame = scene_frame_from_isaacgym(
                        env, reward=float(reward[0].item()), robot=recipe.get("robot") or None
                    )
                    now = time.monotonic()
                    if now - last_frame_emit >= (1.0 / 30.0) or step == 0:
                        _send_scene_frame(
                            viser_bridge,
                            last_scene_frame,
                            task=args.task,
                            step=step,
                            metrics={"reward": float(reward.mean().item())},
                            network_output=actions[0].detach().cpu().tolist(),
                            terrain=terrain_payload,
                        )
                        last_frame_emit = now
                    if hasattr(env, "base_lin_vel"):
                        actual_velocity = env.base_lin_vel[:, 0]
                        forward_velocity.append(float(actual_velocity.mean().item()))
                        if hasattr(env, "commands"):
                            command_velocity = env.commands[:, 0]
                            commanded_forward_velocity.append(
                                float(command_velocity.mean().item())
                            )
                            forward_tracking_error.append(
                                float(
                                    (actual_velocity - command_velocity)
                                    .abs()
                                    .mean()
                                    .item()
                                )
                            )
                    step += 1
                    if args.visualize:
                        next_control_tick += 1.0 / 60.0
                        delay = next_control_tick - time.monotonic()
                        if delay > 0:
                            time.sleep(delay)
                        else:
                            next_control_tick = time.monotonic()
                if viser_bridge is not None and args.steps > 0:
                    viser_bridge.stdin.close()
                    viser_bridge.wait(timeout=5)
                _emit(
                    {
                        "backend": "isaacgym",
                        "task_id": args.task,
                        "checkpoint": str(Path(args.checkpoint).resolve()),
                        "steps": step,
                        "mean_reward": (
                            sum(rewards) / len(rewards) if rewards else None
                        ),
                        "mean_forward_velocity": (
                            sum(forward_velocity) / len(forward_velocity)
                            if forward_velocity
                            else None
                        ),
                        "mean_commanded_forward_velocity": (
                            sum(commanded_forward_velocity)
                            / len(commanded_forward_velocity)
                            if commanded_forward_velocity
                            else None
                        ),
                        "mean_abs_forward_tracking_error": (
                            sum(forward_tracking_error) / len(forward_tracking_error)
                            if forward_tracking_error
                            else None
                        ),
                        "mean_estimator_mse": (
                            sum(estimator_mse) / len(estimator_mse)
                            if estimator_mse else None
                        ),
                        "mean_estimator_mae": (
                            sum(estimator_mae) / len(estimator_mae)
                            if estimator_mae else None
                        ),
                        "done_count": done_count,
                        "visualizer": "mjlab_viser_bridge" if args.visualize else None,
                        "mode": "evaluate" if args.evaluation else "play",
                        "scene_frame": (
                            last_scene_frame.to_dict() if last_scene_frame is not None else None
                        ),
                    }
                )
                return 0
            Path(runner.log_dir).mkdir(parents=True, exist_ok=True)
            with open(Path(runner.log_dir) / "resolved_config.json", "w") as stream:
                json.dump(
                    {
                        "framework": "isaacgym",
                        "task": args.task,
                        "method": args.method,
                        "seed": args.seed,
                        "num_envs": args.num_envs,
                        "device": args.device,
                        "max_iterations": args.max_iterations,
                        "checkpoint_interval": args.checkpoint_interval,
                        "resume_from": args.resume_from,
                        "recipe": recipe,
                        "isaacgym_path": str(Path(args.isaacgym_path).resolve()),
                        "legged_gym_path": str(Path(args.legged_gym_path).resolve()),
                        "rsl_rl_path": str(Path(args.rsl_rl_path).resolve()),
                    },
                    stream,
                    indent=2,
                    sort_keys=True,
                )
            train_cfg.runner.max_iterations = args.max_iterations
            train_cfg.runner.save_interval = args.checkpoint_interval
            if hasattr(runner, "save_interval"):
                runner.save_interval = args.checkpoint_interval
            runner.learn(
                num_learning_iterations=args.max_iterations,
                init_at_random_ep_len=True,
            )
            checkpoint_path = Path(runner.log_dir) / f"model_{runner.current_learning_iteration}.pt"
            result = {
                "backend": "isaacgym",
                "task_id": args.task,
                "device": str(env.device),
                "num_envs": env.num_envs,
                "max_iterations": args.max_iterations,
                "checkpoint_interval": args.checkpoint_interval,
                "log_dir": runner.log_dir,
                "checkpoint": str(checkpoint_path),
                "resumed_from": args.resume_from,
            }
            with open(Path(runner.log_dir) / "metrics.json", "w") as stream:
                json.dump(result, stream, indent=2, sort_keys=True)
            _emit(
                result
            )
            return 0
        observations, privileged_observations = env.reset()
        actions = torch.zeros(
            env.num_envs, env.num_actions, device=env.device, requires_grad=False
        )
        next_observations, next_privileged, reward, done, _ = env.step(actions)
        _emit(
            {
                "backend": "isaacgym",
                "task_id": args.task,
                "device": str(env.device),
                "num_envs": env.num_envs,
                "observation_shape": list(observations.shape),
                "privileged_observation_shape": (
                    list(privileged_observations.shape)
                    if privileged_observations is not None
                    else None
                ),
                "action_shape": list(actions.shape),
                "next_observation_shape": list(next_observations.shape),
                "next_privileged_observation_shape": (
                    list(next_privileged.shape) if next_privileged is not None else None
                ),
                "reward_shape": list(reward.shape),
                "done_shape": list(done.shape),
            }
        )
        return 0
    finally:
        if env is not None:
            env.gym.destroy_sim(env.sim)


if __name__ == "__main__":
    sys.exit(main())
