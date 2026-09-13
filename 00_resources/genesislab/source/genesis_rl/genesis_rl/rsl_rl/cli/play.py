"""Play a trained GenesisLab + RSL-RL policy.

Python-side CLI entrypoint that mirrors:

    scripts/reinforcement_learning/rsl_rl/play.py
"""

from __future__ import annotations

import os
from pathlib import Path
import argparse

import torch
import genesis as gs
import gymnasium as gym
from rsl_rl.runners import OnPolicyRunner

from genesislab.envs.manager_based_rl_env import ManagerBasedRlEnv
from genesislab.engine.visualize import stop_video_recorder
from genesis_rl.rsl_rl import GenesisRslRlVecEnv
from genesis_rl.rsl_rl.gym_utils import resolve_env_cfg_entry_point
from genesis_rl.rsl_rl.args_cli import add_play_args
from genesis_rl.rsl_rl.utils.env_cfg import load_env_cfg, apply_cli_overrides
from genesis_rl.rsl_rl.utils.config_io import load_train_cfg, infer_paths_from_checkpoint

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Play a trained GenesisLab task with RSL-RL.")
    add_play_args(parser)
    parser.add_argument(
        "--video",
        action="store_true",
        default=False,
        help="If set, record a video of the rollout to LOG_DIR/videos/play.mp4.",
    )
    parser.add_argument(
        "--video-fps",
        type=int,
        default=50,
        help="FPS for the recorded video.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # If possible, infer env-id, train-cfg and log-dir from the checkpoint path
    # so that users can simply provide --checkpoint.
    infer_paths_from_checkpoint(args)

    # Prepare log directory early so we can derive video paths from it.
    log_dir = os.path.abspath(args.log_dir)
    os.makedirs(log_dir, exist_ok=True)

    video_path: Path = None
    if args.video:
        video_dir = Path(log_dir) / "videos"
        video_dir.mkdir(parents=True, exist_ok=True)
        video_path = video_dir / "play.mp4"

    # ------------------------------------------------------------------ #
    # Environment construction
    # ------------------------------------------------------------------ #
    if args.env_id is not None:
        env_cfg_entry_point = resolve_env_cfg_entry_point(args.env_id)
        env_cfg = load_env_cfg(env_cfg_entry_point)
        apply_cli_overrides(env_cfg, args)
        if video_path is not None and hasattr(env_cfg, "scene"):
            setattr(env_cfg.scene, "record_video_path", str(video_path))
        env = ManagerBasedRlEnv(cfg=env_cfg, device=args.device)
    else:
        if not args.env_cfg_entry:
            raise ValueError("Either '--env-id' or '--env-cfg-entry' must be provided.")
        env_cfg = load_env_cfg(args.env_cfg_entry)
        apply_cli_overrides(env_cfg, args)
        if video_path is not None and hasattr(env_cfg, "scene"):
            setattr(env_cfg.scene, "record_video_path", str(video_path))
        env = ManagerBasedRlEnv(cfg=env_cfg, device=args.device)

    vec_env = GenesisRslRlVecEnv(env)

    # ------------------------------------------------------------------ #
    # Runner and checkpoint loading
    # ------------------------------------------------------------------ #
    train_cfg = load_train_cfg(args.train_cfg)

    # For play we don't use num_learning_iterations, but the runner expects it
    # to be present for logging. If missing, set a dummy value.
    train_cfg.setdefault("num_learning_iterations", 1)

    runner = OnPolicyRunner(vec_env, train_cfg=train_cfg, log_dir=log_dir, device=args.device)
    print(f"[GenesisLab][rsl_rl] Loading checkpoint from: {args.checkpoint}")
    runner.load(args.checkpoint, map_location=args.device)

    # ------------------------------------------------------------------ #
    # Rollout loop
    # ------------------------------------------------------------------ #
    num_envs = vec_env.num_envs
    max_episode_length = int(vec_env.max_episode_length) if vec_env.max_episode_length is not None else None

    if args.max_steps is not None:
        horizon = args.max_steps
    elif max_episode_length is not None:
        horizon = max_episode_length
    else:
        horizon = 1000  # sensible fallback

    print(
        f"[GenesisLab][rsl_rl] Playing {args.num_episodes} episodes "
        f"with horizon {horizon} steps (num_envs={num_envs})."
    )

    import tqdm

    try:
        for ep in range(args.num_episodes):
            # Reset underlying Genesis env and sync observations.
            env.reset(seed=args.seed)
            obs = vec_env.get_observations()

            episode_reward = torch.zeros(num_envs, device=args.device)
            pbar = tqdm.tqdm(range(horizon))

            for step in pbar:
                with torch.no_grad():
                    actions = runner.alg.act(obs)
                obs, rewards, dones, extras = vec_env.step(actions.to(vec_env.device))

                episode_reward += rewards.to(args.device)

            mean_reward = episode_reward.mean().item()
            print(f"[GenesisLab][rsl_rl][Play] Episode {ep + 1}/{args.num_episodes} - mean reward: {mean_reward:.3f}")
    finally:
        # Ensure any active recording is stopped cleanly.
        if args.video and hasattr(env, "_binding"):
            stop_video_recorder(env._binding.scene)


if __name__ == "__main__":
    # Initialize Genesis engine before creating any environments.
    gs.init(logging_level="WARNING")

    if torch.cuda.is_available():
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        torch.backends.cudnn.deterministic = False
        torch.backends.cudnn.benchmark = False

    main()

