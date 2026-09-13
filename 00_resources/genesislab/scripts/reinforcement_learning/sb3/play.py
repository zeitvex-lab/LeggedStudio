"""Play a Stable-Baselines3 checkpoint on a GenesisLab task.

This script mirrors IsaacLab's ``scripts/reinforcement_learning/sb3/play.py``
but targets GenesisLab's :class:`ManagerBasedRlEnv` and :mod:`genesis_rl.sb3`.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time
from pathlib import Path

import genesis as gs
import gymnasium as gym
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import VecNormalize

import genesis_tasks.locomotion  # noqa: F401  (ensure tasks are registered)
from genesis_rl.sb3 import Sb3VecEnvWrapper, process_sb3_cfg
from genesis_tasks.utils.dict import print_dict
from genesis_tasks.utils.hydra import hydra_task_config
from genesis_tasks.utils.parse_cfg import get_checkpoint_path
from genesislab.envs.manager_based_rl_env import ManagerBasedRlEnvCfg


parser = argparse.ArgumentParser(description="Play a checkpoint of an SB3 agent on GenesisLab tasks.")
parser.add_argument("--video", action="store_true", default=False, help="Record videos during play.")
parser.add_argument("--video_length", type=int, default=200, help="Length of the recorded video (in steps).")
parser.add_argument("--num_envs", type=int, default=None, help="Number of environments to simulate.")
parser.add_argument("--task", type=str, required=True, help="Gym task name registered by GenesisLab.")
parser.add_argument(
    "--agent",
    type=str,
    default="sb3_cfg_entry_point",
    help="Agent configuration Hydra entry point (same pattern as IsaacLab).",
)
parser.add_argument("--checkpoint", type=str, default=None, help="Path to model checkpoint.")
parser.add_argument("--seed", type=int, default=None, help="Seed used for the environment.")
parser.add_argument(
    "--use_pretrained_checkpoint",
    action="store_true",
    help="Use a published pre-trained checkpoint (not yet implemented for GenesisLab).",
)
parser.add_argument(
    "--use_last_checkpoint",
    action="store_true",
    help="When no checkpoint provided, use the last saved model. Otherwise use the best saved model.",
)
parser.add_argument("--real-time", action="store_true", default=False, help="Run in real-time, if possible.")
parser.add_argument(
    "--keep_all_info",
    action="store_true",
    default=False,
    help="Use a slower SB3 wrapper but keep all the extra training info.",
)
parser.add_argument("--device", type=str, default=None, help="Device for the environment (e.g. cuda:0 or cpu).")


args_cli, hydra_args = parser.parse_known_args()
sys.argv = [sys.argv[0]] + hydra_args


@hydra_task_config(args_cli.task, args_cli.agent)
def main(env_cfg: ManagerBasedRlEnvCfg, agent_cfg: dict) -> None:
    """Load an SB3 checkpoint and play it in GenesisLab."""
    task_name = args_cli.task.split(":")[-1]
    train_task_name = task_name.replace("-Play", "")

    if args_cli.seed == -1:
        args_cli.seed = random.randint(0, 10000)

    env_cfg.scene.num_envs = args_cli.num_envs if args_cli.num_envs is not None else env_cfg.scene.num_envs
    agent_cfg["seed"] = args_cli.seed if args_cli.seed is not None else agent_cfg.get("seed", 0)

    env_cfg.seed = agent_cfg["seed"]
    if args_cli.device is not None:
        env_cfg.sim.device = args_cli.device

    log_root_path = os.path.abspath(os.path.join("logs", "sb3", train_task_name))

    if args_cli.use_pretrained_checkpoint:
        # Placeholder: hook in a future GenesisLab model zoo if available.
        raise NotImplementedError("use_pretrained_checkpoint is not yet implemented for GenesisLab.")
    elif args_cli.checkpoint is None:
        if args_cli.use_last_checkpoint:
            checkpoint = "model_.*.zip"
        else:
            checkpoint = "model.zip"
        checkpoint_path = get_checkpoint_path(log_root_path, ".*", checkpoint, sort_alpha=False)
    else:
        checkpoint_path = args_cli.checkpoint

    log_dir = os.path.dirname(checkpoint_path)

    env_cfg.log_dir = log_dir

    env = gym.make(args_cli.task, cfg=env_cfg, render_mode="rgb_array" if args_cli.video else None)

    agent_cfg = process_sb3_cfg(agent_cfg, env.unwrapped.num_envs)

    if args_cli.video:
        video_kwargs = {
            "video_folder": os.path.join(log_dir, "videos", "play"),
            "step_trigger": lambda step: step == 0,
            "video_length": args_cli.video_length,
            "disable_logger": True,
        }
        print("[INFO] Recording videos during play.")
        print_dict(video_kwargs, nesting=4)
        env = gym.wrappers.RecordVideo(env, **video_kwargs)

    env = Sb3VecEnvWrapper(env, fast_variant=not args_cli.keep_all_info)

    vec_norm_path = Path(
        checkpoint_path.replace("/model", "/model_vecnormalize").replace(".zip", ".pkl")
    )

    if vec_norm_path.exists():
        print(f"Loading saved normalization: {vec_norm_path}")
        env = VecNormalize.load(vec_norm_path, env)
        env.training = False
        env.norm_reward = False
    elif "normalize_input" in agent_cfg:
        env = VecNormalize(
            env,
            training=True,
            norm_obs=agent_cfg.pop("normalize_input"),
            clip_obs=agent_cfg.pop("clip_obs", 100.0),
        )

    print(f"Loading checkpoint from: {checkpoint_path}")
    agent = PPO.load(checkpoint_path, env, print_system_info=True)

    dt = env.unwrapped.step_dt

    obs = env.reset()
    timestep = 0

    while True:
        start_time = time.time()
        with torch.inference_mode():
            actions, _ = agent.predict(obs, deterministic=True)
            obs, _, dones, _ = env.step(actions)

        if args_cli.video:
            timestep += 1
            if timestep == args_cli.video_length:
                break

        if np.all(dones):
            # For purely visual play, just reset when all envs are done.
            obs = env.reset()

        sleep_time = dt - (time.time() - start_time)
        if args_cli.real_time and sleep_time > 0:
            time.sleep(sleep_time)

    env.close()


if __name__ == "__main__":
    gs.init(logging_level="WARNING")

    if torch.cuda.is_available():
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        torch.backends.cudnn.deterministic = False
        torch.backends.cudnn.benchmark = False

    main()

