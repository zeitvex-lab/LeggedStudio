"""Train a GenesisLab RL task with RL-Games.

This script mirrors IsaacLab's ``scripts/reinforcement_learning/rl_games/train.py``
but targets GenesisLab's :class:`ManagerBasedRlEnv` and :mod:`genesis_rl.rl_games`.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys
import time
from datetime import datetime

import genesis as gs
import gymnasium as gym
from rl_games.common import env_configurations, vecenv
from rl_games.common.algo_observer import IsaacAlgoObserver
from rl_games.torch_runner import Runner

import genesis_tasks.locomotion  # noqa: F401  (ensure tasks are registered)
from genesis_rl.rl_games import RlGamesGpuEnv, RlGamesVecEnvWrapper
from genesis_tasks.utils.dict import print_dict
from genesis_tasks.utils.hydra import hydra_task_config
from genesislab.envs.manager_based_rl_env import ManagerBasedRlEnvCfg
from genesislab.utils.io import dump_yaml


parser = argparse.ArgumentParser(description="Train an RL agent with RL-Games on GenesisLab.")
parser.add_argument("--video", action="store_true", default=False, help="Record videos during training.")
parser.add_argument("--video_length", type=int, default=200, help="Length of the recorded video (in steps).")
parser.add_argument("--video_interval", type=int, default=2000, help="Interval between video recordings (in steps).")
parser.add_argument("--num_envs", type=int, default=None, help="Number of environments to simulate.")
parser.add_argument("--task", type=str, required=True, help="Name of the gym task registered by GenesisLab.")
parser.add_argument(
    "--agent",
    type=str,
    default="rl_games_cfg_entry_point",
    help="Name of the RL-Games configuration Hydra entry point.",
)
parser.add_argument("--seed", type=int, default=None, help="Seed used for the environment.")
parser.add_argument(
    "--distributed", action="store_true", default=False, help="Run training with multiple GPUs or nodes."
)
parser.add_argument("--checkpoint", type=str, default=None, help="Path to model checkpoint.")
parser.add_argument("--sigma", type=str, default=None, help="The policy's initial standard deviation.")
parser.add_argument("--max_iterations", type=int, default=None, help="RL policy training iterations.")
parser.add_argument("--export_io_descriptors", action="store_true", default=False, help="Export IO descriptors.")
parser.add_argument("--device", type=str, default=None, help="Device for the environment (e.g. cuda:0 or cpu).")


args_cli, hydra_args = parser.parse_known_args()
sys.argv = [sys.argv[0]] + hydra_args


@hydra_task_config(args_cli.task, args_cli.agent)
def main(env_cfg: ManagerBasedRlEnvCfg, agent_cfg: dict) -> None:
    """Train an RL-Games agent on a GenesisLab task."""
    env_cfg.scene.num_envs = args_cli.num_envs if args_cli.num_envs is not None else env_cfg.scene.num_envs
    if args_cli.device is not None:
        env_cfg.sim.device = args_cli.device

    if args_cli.distributed and args_cli.device is not None and "cpu" in args_cli.device:
        raise ValueError(
            "Distributed training is not supported when using CPU device. "
            "Please use GPU device (e.g., --device cuda) for distributed training."
        )

    if args_cli.seed == -1:
        args_cli.seed = random.randint(0, 10000)

    # RL-Games config layout mirrors IsaacLab's:
    # agent_cfg['params']['seed'], ['params']['config'], ['params']['env'], ...
    params = agent_cfg.setdefault("params", {})
    cfg = params.setdefault("config", {})
    env_params = params.setdefault("env", {})

    params["seed"] = args_cli.seed if args_cli.seed is not None else params.get("seed", 0)
    cfg["max_epochs"] = args_cli.max_iterations if args_cli.max_iterations is not None else cfg.get("max_epochs", 1000)

    if args_cli.checkpoint is not None:
        params["load_checkpoint"] = True
        params["load_path"] = args_cli.checkpoint
        print(f"[INFO]: Loading model checkpoint from: {params['load_path']}")

    train_sigma = float(args_cli.sigma) if args_cli.sigma is not None else None

    if args_cli.distributed:
        # Minimal distributed support: device selection left to the user.
        print("[WARN] Distributed training is enabled, but rank handling is minimal in this script.")

    env_cfg.seed = params["seed"]

    config_name = cfg.get("name", "rl_games")
    log_root_path = os.path.join("logs", "rl_games", config_name)
    log_root_path = os.path.abspath(log_root_path)

    print(f"[INFO] Logging experiment in directory: {log_root_path}")
    log_dir = cfg.get("full_experiment_name", datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
    cfg["train_dir"] = log_root_path
    cfg["full_experiment_name"] = log_dir

    dump_yaml(os.path.join(log_root_path, log_dir, "params", "env.yaml"), env_cfg)
    dump_yaml(os.path.join(log_root_path, log_dir, "params", "agent.yaml"), agent_cfg)
    print(f"Exact experiment name requested from command line: {os.path.join(log_root_path, log_dir)}")

    rl_device = cfg.get("device", "cuda:0")
    clip_obs = env_params.get("clip_observations", math.inf)
    clip_actions = env_params.get("clip_actions", math.inf)
    obs_groups = env_params.get("obs_groups")
    concate_obs_groups = env_params.get("concate_obs_groups", True)

    env_cfg.export_io_descriptors = args_cli.export_io_descriptors
    env_cfg.log_dir = os.path.join(log_root_path, log_dir)

    env = gym.make(args_cli.task, cfg=env_cfg, render_mode="rgb_array" if args_cli.video else None)

    if args_cli.video:
        video_kwargs = {
            "video_folder": os.path.join(log_root_path, log_dir, "videos", "train"),
            "step_trigger": lambda step: step % args_cli.video_interval == 0,
            "video_length": args_cli.video_length,
            "disable_logger": True,
        }
        print("[INFO] Recording videos during training.")
        print_dict(video_kwargs, nesting=4)
        env = gym.wrappers.RecordVideo(env, **video_kwargs)

    start_time = time.time()

    env = RlGamesVecEnvWrapper(env, rl_device, clip_obs, clip_actions, obs_groups, concate_obs_groups)

    vecenv.register(
        "GenesisRlgWrapper",
        lambda config_name, num_actors, **kwargs: RlGamesGpuEnv(config_name, num_actors, **kwargs),
    )
    env_configurations.register("rlgpu", {"vecenv_type": "GenesisRlgWrapper", "env_creator": lambda **kwargs: env})

    cfg["num_actors"] = env.unwrapped.num_envs

    runner = Runner(IsaacAlgoObserver())
    runner.load(agent_cfg)
    runner.reset()

    if args_cli.checkpoint is not None:
        runner.run({"train": True, "play": False, "sigma": train_sigma, "checkpoint": params["load_path"]})
    else:
        runner.run({"train": True, "play": False, "sigma": train_sigma})

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

