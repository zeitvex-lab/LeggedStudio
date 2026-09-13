"""Train a GenesisLab RL task with skrl.

This script mirrors IsaacLab's ``scripts/reinforcement_learning/skrl/train.py``
but targets GenesisLab's :class:`ManagerBasedRlEnv` and :mod:`genesis_rl.skrl`.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time
from datetime import datetime

import genesis as gs
import gymnasium as gym
import skrl
import torch
from packaging import version

import genesis_tasks.locomotion  # noqa: F401  (ensure tasks are registered)
from genesis_rl.skrl import SkrlVecEnvWrapper
from genesis_tasks.utils.dict import print_dict
from genesis_tasks.utils.hydra import hydra_task_config
from genesislab.envs.manager_based_rl_env import ManagerBasedRlEnvCfg
from genesislab.utils.io import dump_yaml


parser = argparse.ArgumentParser(description="Train an RL agent with skrl on GenesisLab.")
parser.add_argument("--video", action="store_true", default=False, help="Record videos during training.")
parser.add_argument("--video_length", type=int, default=200, help="Length of the recorded video (in steps).")
parser.add_argument("--video_interval", type=int, default=2000, help="Interval between video recordings (in steps).")
parser.add_argument("--num_envs", type=int, default=None, help="Number of environments to simulate.")
parser.add_argument("--task", type=str, required=True, help="Name of the gym task registered by GenesisLab.")
parser.add_argument(
    "--agent",
    type=str,
    default=None,
    help=(
        "Name of the skrl agent configuration Hydra entry point. If None, "
        "you are expected to handle agent_cfg resolution in your Hydra config."
    ),
)
parser.add_argument("--seed", type=int, default=None, help="Seed used for the environment.")
parser.add_argument(
    "--distributed", action="store_true", default=False, help="Run training with multiple GPUs or nodes."
)
parser.add_argument("--checkpoint", type=str, default=None, help="Path to model checkpoint to resume training.")
parser.add_argument("--max_iterations", type=int, default=None, help="RL policy training iterations.")
parser.add_argument("--export_io_descriptors", action="store_true", default=False, help="Export IO descriptors.")
parser.add_argument(
    "--ml_framework",
    type=str,
    default="torch",
    choices=["torch", "jax", "jax-numpy"],
    help="The ML framework used for training the skrl agent.",
)
parser.add_argument("--device", type=str, default=None, help="Device for the environment (e.g. cuda:0 or cpu).")


args_cli, hydra_args = parser.parse_known_args()
sys.argv = [sys.argv[0]] + hydra_args


# Minimal skrl version check (aligned with IsaacLab)
SKRL_VERSION = "1.4.3"
if version.parse(skrl.__version__) < version.parse(SKRL_VERSION):
    skrl.logger.error(
        f"Unsupported skrl version: {skrl.__version__}. "
        f"Install supported version using 'pip install skrl>={SKRL_VERSION}'"
    )
    raise SystemExit(1)

if args_cli.ml_framework.startswith("torch"):
    from skrl.utils.runner.torch import Runner
elif args_cli.ml_framework.startswith("jax"):
    from skrl.utils.runner.jax import Runner


@hydra_task_config(args_cli.task, args_cli.agent)
def main(env_cfg: ManagerBasedRlEnvCfg, agent_cfg: dict) -> None:
    """Train a skrl agent on a GenesisLab task."""
    env_cfg.scene.num_envs = args_cli.num_envs if args_cli.num_envs is not None else env_cfg.scene.num_envs
    if args_cli.device is not None:
        env_cfg.sim.device = args_cli.device

    if args_cli.distributed and args_cli.device is not None and "cpu" in args_cli.device:
        raise ValueError(
            "Distributed training is not supported when using CPU device. "
            "Please use GPU device (e.g., --device cuda) for distributed training."
        )

    if args_cli.distributed:
        # For now we simply mirror IsaacLab's pattern; users can adjust this
        # according to their launcher / rank logic.
        # Example: env_cfg.sim.device = f\"cuda:{local_rank}\"
        print("[WARN] Distributed training is enabled, but rank handling is minimal in this script.")

    if args_cli.max_iterations:
        # Assuming skrl Runner uses agent_cfg['trainer']['timesteps'] and agent_cfg['agent']['rollouts']
        agent_cfg.setdefault("trainer", {})
        agent_cfg.setdefault("agent", {})
        rollouts = agent_cfg["agent"].get("rollouts", 1)
        agent_cfg["trainer"]["timesteps"] = args_cli.max_iterations * rollouts
    agent_cfg.setdefault("trainer", {})
    agent_cfg["trainer"]["close_environment_at_exit"] = False

    if args_cli.ml_framework.startswith("jax"):
        skrl.config.jax.backend = "jax" if args_cli.ml_framework == "jax" else "numpy"

    if args_cli.seed == -1:
        args_cli.seed = random.randint(0, 10000)

    agent_cfg["seed"] = args_cli.seed if args_cli.seed is not None else agent_cfg.get("seed", 0)
    env_cfg.seed = agent_cfg["seed"]

    log_root_path = os.path.join("logs", "skrl", agent_cfg.get("agent", {}).get("experiment", {}).get("directory", ""))
    log_root_path = os.path.abspath(log_root_path)
    print(f"[INFO] Logging experiment in directory: {log_root_path}")

    algo_name = agent_cfg.get("agent", {}).get("experiment", {}).get("experiment_name", "skrl")
    log_dir = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + f"_{algo_name}_{args_cli.ml_framework}"
    print(f"Exact experiment name requested from command line: {log_dir}")

    agent_cfg.setdefault("agent", {}).setdefault("experiment", {})
    agent_cfg["agent"]["experiment"]["directory"] = log_root_path
    agent_cfg["agent"]["experiment"]["experiment_name"] = log_dir
    log_dir = os.path.join(log_root_path, log_dir)

    dump_yaml(os.path.join(log_dir, "params", "env.yaml"), env_cfg)
    dump_yaml(os.path.join(log_dir, "params", "agent.yaml"), agent_cfg)

    resume_path = args_cli.checkpoint if args_cli.checkpoint else None

    env_cfg.export_io_descriptors = args_cli.export_io_descriptors
    env_cfg.log_dir = log_dir

    env = gym.make(args_cli.task, cfg=env_cfg, render_mode="rgb_array" if args_cli.video else None)

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

    env = SkrlVecEnvWrapper(env, ml_framework=args_cli.ml_framework)

    runner = Runner(env, agent_cfg)

    if resume_path:
        print(f"[INFO] Loading model checkpoint from: {resume_path}")
        runner.agent.load(resume_path)

    runner.run()

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

