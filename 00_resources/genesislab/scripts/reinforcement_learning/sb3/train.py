"""Train a GenesisLab RL task with Stable-Baselines3.

This script mirrors IsaacLab's ``scripts/reinforcement_learning/sb3/train.py``,
but is implemented on top of:

- GenesisLab's :class:`ManagerBasedRlEnv`
- The SB3 adapter in :mod:`genesis_rl.sb3.Sb3VecEnvWrapper`

It is intentionally lightweight: Hydra / logging layout / task registry are
kept close to IsaacLab, but you should feel free to customize it for your own
workflows.
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import genesis as gs
import gymnasium as gym
import numpy as np
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import CheckpointCallback, LogEveryNTimesteps
from stable_baselines3.common.vec_env import VecNormalize

import genesis_tasks.locomotion  # noqa: F401  (ensure tasks are registered)
from genesis_rl.sb3 import Sb3VecEnvWrapper, process_sb3_cfg
from genesislab.envs.manager_based_rl_env import ManagerBasedRlEnvCfg
from genesislab.utils.io import dump_yaml

from genesis_tasks.utils.hydra import hydra_task_config
from genesis_tasks.utils.dict import print_dict


parser = argparse.ArgumentParser(description="Train a GenesisLab RL agent with Stable-Baselines3.")
parser.add_argument("--video", action="store_true", default=False, help="Record videos during training.")
parser.add_argument("--video_length", type=int, default=200, help="Length of the recorded video (in steps).")
parser.add_argument("--video_interval", type=int, default=2000, help="Interval between video recordings (in steps).")
parser.add_argument("--num_envs", type=int, default=None, help="Number of environments to simulate.")
parser.add_argument("--task", type=str, required=True, help="Gym task name registered by GenesisLab.")
parser.add_argument(
    "--agent",
    type=str,
    default="sb3_cfg_entry_point",
    help="Agent configuration Hydra entry point (same pattern as IsaacLab).",
)
parser.add_argument("--seed", type=int, default=None, help="Seed used for the environment.")
parser.add_argument("--log_interval", type=int, default=100_000, help="Log data every n timesteps.")
parser.add_argument("--checkpoint", type=str, default=None, help="Continue the training from checkpoint.")
parser.add_argument("--max_iterations", type=int, default=None, help="RL policy training iterations.")
parser.add_argument("--export_io_descriptors", action="store_true", default=False, help="Export IO descriptors.")
parser.add_argument(
    "--keep_all_info",
    action="store_true",
    default=False,
    help="Use a slower SB3 wrapper but keep all the extra training info.",
)
parser.add_argument("--device", type=str, default=None, help="Device for the environment (e.g. cuda:0 or cpu).")


# Parse arguments once up-front; Hydra will re-parse inside the decorated main.
args_cli, hydra_args = parser.parse_known_args()
sys.argv = [sys.argv[0]] + hydra_args

logger = logging.getLogger(__name__)


@hydra_task_config(args_cli.task, args_cli.agent)
def main(env_cfg: ManagerBasedRlEnvCfg, agent_cfg: dict) -> None:
    """Train a policy with Stable-Baselines3 PPO."""
    # Random seed handling
    if args_cli.seed == -1:
        args_cli.seed = random.randint(0, 10000)

    # Override configs from CLI
    env_cfg.scene.num_envs = args_cli.num_envs if args_cli.num_envs is not None else env_cfg.scene.num_envs
    agent_cfg["seed"] = args_cli.seed if args_cli.seed is not None else agent_cfg.get("seed", 0)

    if args_cli.max_iterations is not None:
        agent_cfg["n_timesteps"] = args_cli.max_iterations * agent_cfg["n_steps"] * env_cfg.scene.num_envs

    env_cfg.seed = agent_cfg["seed"]
    if args_cli.device is not None:
        env_cfg.sim.device = args_cli.device

    # Logging directory
    run_info = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_root_path = os.path.abspath(os.path.join("logs", "sb3", args_cli.task))
    print(f"[INFO] Logging experiment in directory: {log_root_path}")
    print(f"Exact experiment name requested from command line: {run_info}")
    log_dir = os.path.join(log_root_path, run_info)

    # Dump configs
    dump_yaml(os.path.join(log_dir, "params", "env.yaml"), env_cfg)
    dump_yaml(os.path.join(log_dir, "params", "agent.yaml"), agent_cfg)

    # Save command-line invocation
    command = " ".join(sys.orig_argv)
    (Path(log_dir) / "command.txt").write_text(command)

    # Post-process SB3 config
    agent_cfg = process_sb3_cfg(agent_cfg, env_cfg.scene.num_envs)
    policy_arch = agent_cfg.pop("policy")
    n_timesteps = agent_cfg.pop("n_timesteps")

    # IO descriptor export flag (only meaningful for manager-based envs)
    env_cfg.export_io_descriptors = args_cli.export_io_descriptors

    # Let env write logs under the same directory
    env_cfg.log_dir = log_dir

    # Construct gym environment (GenesisLab registers tasks as gym environments)
    env = gym.make(args_cli.task, cfg=env_cfg, render_mode="rgb_array" if args_cli.video else None)

    # Optional video recording
    if args_cli.video:
        video_kwargs = {
            "video_folder": os.path.join(log_dir, "videos", "train"),
            "step_trigger": lambda step: step % args_cli.video_interval == 0,
            "video_length": args_cli.video_length,
            "disable_logger": True,
        }
        print("[INFO] Recording videos during training.")
        print_dict(video_kwargs, nesting=4)
        env = gym.wrappers.RecordVideo(env, **video_kwargs)

    start_time = time.time()

    # Wrap Genesis env for SB3
    env = Sb3VecEnvWrapper(env, fast_variant=not args_cli.keep_all_info)

    # VecNormalize support (optional)
    norm_keys = {"normalize_input", "normalize_value", "clip_obs"}
    norm_args = {k: agent_cfg.pop(k) for k in list(agent_cfg.keys()) if k in norm_keys}
    if norm_args.get("normalize_input", False):
        print(f"Normalizing input, norm_args={norm_args}")
        env = VecNormalize(
            env,
            training=True,
            norm_obs=norm_args["normalize_input"],
            norm_reward=norm_args.get("normalize_value", False),
            clip_obs=norm_args.get("clip_obs", 100.0),
            gamma=agent_cfg["gamma"],
            clip_reward=np.inf,
        )

    # Create SB3 agent
    agent = PPO(policy_arch, env, verbose=1, tensorboard_log=log_dir, **agent_cfg)
    if args_cli.checkpoint is not None:
        agent = agent.load(args_cli.checkpoint, env, print_system_info=True)

    # Callbacks
    checkpoint_callback = CheckpointCallback(save_freq=1000, save_path=log_dir, name_prefix="model", verbose=2)
    callbacks = [checkpoint_callback, LogEveryNTimesteps(n_steps=args_cli.log_interval)]

    # Train
    with contextlib.suppress(KeyboardInterrupt):
        agent.learn(
            total_timesteps=n_timesteps,
            callback=callbacks,
            progress_bar=True,
            log_interval=None,
        )

    # Save final model
    agent.save(os.path.join(log_dir, "model"))
    print("Saving to:")
    print(os.path.join(log_dir, "model.zip"))

    if isinstance(env, VecNormalize):
        print("Saving normalization")
        env.save(os.path.join(log_dir, "model_vecnormalize.pkl"))

    print(f"Training time: {round(time.time() - start_time, 2)} seconds")

    env.close()


if __name__ == "__main__":
    gs.init(logging_level="WARNING")

    if torch.cuda.is_available():
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        torch.backends.cudnn.deterministic = False
        torch.backends.cudnn.benchmark = False

    main()

