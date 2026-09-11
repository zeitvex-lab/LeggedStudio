# Copyright (c) 2026
# SPDX-License-Identifier: BSD-3-Clause

"""ONNX play script – locomotion + ROS2 bridge + autonomous Nav2 control.

新增 --nav 模式：
  • 启动 CmdVelBridge 订阅 /cmd_vel（Nav2 发出）
  • 将 (vx, vy, wz) 注入 policy 的 velocity_commands observation
  • 与 --keyboard 互斥（Nav2 / keyboard 二选一）

典型用法：
  # 建图阶段（teleop）
  python play_onnx_perception.py --task=... --onnx=policy.onnx --keyboard --enable_ros2_bridge

  # 自主导航阶段
  python play_onnx_perception.py --task=... --onnx=policy.onnx --nav --enable_ros2_bridge
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from isaaclab.app import AppLauncher

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import cli_args  # noqa: E402

parser = argparse.ArgumentParser(description="Play an ONNX policy with ROS2-published sensors.")
parser.add_argument("--video", action="store_true", default=False)
parser.add_argument("--video_length", type=int, default=200)
parser.add_argument("--disable_fabric", action="store_true", default=False)
parser.add_argument("--num_envs", type=int, default=None)
parser.add_argument("--task", type=str, default=None)
parser.add_argument("--agent", type=str, default="rsl_rl_cfg_entry_point")
parser.add_argument("--seed", type=int, default=None)
parser.add_argument("--real-time", action="store_true", default=False)
parser.add_argument("--keyboard", action="store_true", default=False,
                    help="Teleop via keyboard (建图阶段使用).")
# ★ new
parser.add_argument("--nav", action="store_true", default=False,
                    help="Autonomous mode: subscribe /cmd_vel from Nav2.")
parser.add_argument("--cmd_vel_topic", type=str, default="/cmd_vel",
                    help="ROS2 topic Nav2 publishes velocity commands on.")
parser.add_argument("--max_lin_x", type=float, default=1.0,
                    help="Clamp |vx| to policy training range (m/s).")
parser.add_argument("--max_lin_y", type=float, default=0.5,
                    help="Clamp |vy| to policy training range (m/s).")
parser.add_argument("--max_ang_z", type=float, default=1.5,
                    help="Clamp |wz| to policy training range (rad/s).")
# existing
parser.add_argument("--onnx", type=str, default=None)
parser.add_argument("--onnx_cpu", action="store_true", default=False)
parser.add_argument("--enable_ros2_bridge", action="store_true", default=True)
cli_args.add_rsl_rl_args(parser)
AppLauncher.add_app_launcher_args(parser)
args_cli, hydra_args = parser.parse_known_args()

if args_cli.keyboard and args_cli.nav:
    raise SystemExit("--keyboard and --nav are mutually exclusive.")

args_cli.enable_cameras = True
sys.argv = [sys.argv[0]] + hydra_args

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import carb
import gymnasium as gym  # noqa: E402
import onnxruntime as ort  # noqa: E402
import time  # noqa: E402
import torch  # noqa: E402

# Suppress time interpolation warnings from simulation manager
carb.logging.acquire_logging().set_level_threshold_for_source(
    "isaacsim.core.simulation_manager.plugin", carb.logging.LogSettingBehavior.OVERRIDE, carb.logging.LEVEL_ERROR
)

# Suppress timeline plugin warnings
carb.logging.acquire_logging().set_level_threshold_for_source(
    "omni.timeline.plugin", carb.logging.LogSettingBehavior.OVERRIDE, carb.logging.LEVEL_ERROR
)

from isaaclab.devices import Se2Keyboard, Se2KeyboardCfg  # noqa: E402
from isaaclab.envs import (  # noqa: E402
    DirectMARLEnv,
    DirectMARLEnvCfg,
    DirectRLEnvCfg,
    ManagerBasedRLEnvCfg,
    multi_agent_to_single_agent,
)
from isaaclab.managers import ObservationTermCfg as ObsTerm  # noqa: E402
from isaaclab.utils.assets import retrieve_file_path  # noqa: E402
from isaaclab_rl.rsl_rl import RslRlOnPolicyRunnerCfg, RslRlVecEnvWrapper  # noqa: E402
from isaaclab_tasks.utils import get_checkpoint_path  # noqa: E402
from isaaclab_tasks.utils.hydra import hydra_task_config  # noqa: E402

import rl_training.tasks  # noqa: F401, E402
from rl_utils import camera_follow  # noqa: E402
from ros2_bridge_graph_m20 import Ros2M20BridgeCfg, build_ros2_bridge_graph  # noqa: E402
from ros2_cmd_vel_bridge import CmdVelBridge  # noqa: E402  ★ new


# -----------------------------------------------------------------------
# helpers (unchanged from original)
# -----------------------------------------------------------------------

def _resolve_onnx_path(log_dir: str, explicit_onnx: str | None) -> str:
    if explicit_onnx:
        try:
            return retrieve_file_path(explicit_onnx)
        except Exception:
            path = Path(explicit_onnx).expanduser().resolve()
            if not path.is_file():
                raise FileNotFoundError(f"Cannot find ONNX file: {path}")
            return str(path)
    default_onnx = Path(log_dir) / "exported" / "policy.onnx"
    if not default_onnx.is_file():
        raise FileNotFoundError(
            f"Could not find default ONNX file at: {default_onnx}. Use --onnx to specify a file."
        )
    return str(default_onnx)


def _make_onnx_session(onnx_path: str, prefer_gpu: bool) -> ort.InferenceSession:
    sess_options = ort.SessionOptions()
    sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if prefer_gpu else ["CPUExecutionProvider"]
    try:
        return ort.InferenceSession(onnx_path, sess_options=sess_options, providers=providers)
    except Exception:
        if prefer_gpu:
            return ort.InferenceSession(onnx_path, sess_options=sess_options, providers=["CPUExecutionProvider"])
        raise


def _extract_policy_obs(obs):
    if isinstance(obs, torch.Tensor):
        return obs
    if hasattr(obs, "keys"):
        try:
            keys = list(obs.keys())
        except Exception:
            keys = []
        for key in ("policy", "obs", "observations"):
            try:
                if key in keys or (hasattr(obs, "__contains__") and key in obs):
                    value = obs[key]
                    if isinstance(value, torch.Tensor):
                        return value
            except Exception:
                pass
        for key in keys:
            try:
                value = obs[key]
                if isinstance(value, torch.Tensor):
                    return value
            except Exception:
                pass
        raise TypeError(f"Unsupported observation container keys: {keys}")
    if isinstance(obs, (tuple, list)) and len(obs) > 0:
        return _extract_policy_obs(obs[0])
    raise TypeError(f"Unsupported observation type: {type(obs)}")


# -----------------------------------------------------------------------
# main
# -----------------------------------------------------------------------

@hydra_task_config(args_cli.task, args_cli.agent)
def main(env_cfg: ManagerBasedRLEnvCfg | DirectRLEnvCfg | DirectMARLEnvCfg,
         agent_cfg: RslRlOnPolicyRunnerCfg):

    agent_cfg = cli_args.update_rsl_rl_cfg(agent_cfg, args_cli)
    env_cfg.scene.num_envs = args_cli.num_envs if args_cli.num_envs is not None else 1
    env_cfg.seed = agent_cfg.seed
    env_cfg.sim.device = args_cli.device if args_cli.device is not None else env_cfg.sim.device

    # ------------------------------------------------------------------
    # keyboard mode (teleop / 建图)
    # ------------------------------------------------------------------
    if args_cli.keyboard:
        env_cfg.scene.num_envs = 1
        env_cfg.terminations.time_out = None
        env_cfg.commands.base_velocity.debug_vis = False
        kb_cfg = Se2KeyboardCfg(
            v_x_sensitivity=env_cfg.commands.base_velocity.ranges.lin_vel_x[1] / 2,
            v_y_sensitivity=env_cfg.commands.base_velocity.ranges.lin_vel_y[1],
            omega_z_sensitivity=env_cfg.commands.base_velocity.ranges.ang_vel_z[1],
        )
        controller = Se2Keyboard(kb_cfg)
        env_cfg.observations.policy.velocity_commands = ObsTerm(
            func=lambda env: torch.tensor(controller.advance(), dtype=torch.float32)
                             .unsqueeze(0).to(env.device),
        )

    # ------------------------------------------------------------------
    # ★ nav mode (autonomous / 自主导航)
    # ------------------------------------------------------------------
    cmd_vel_bridge: CmdVelBridge | None = None
    if args_cli.nav:
        env_cfg.scene.num_envs = 1
        env_cfg.terminations.time_out = None
        env_cfg.commands.base_velocity.debug_vis = False

        # 使用用户指定的速度命令话题
        cmd_vel_topic = args_cli.cmd_vel_topic

        cmd_vel_bridge = CmdVelBridge(
            topic=cmd_vel_topic,
            max_lin_x=args_cli.max_lin_x,
            max_lin_y=args_cli.max_lin_y,
            max_ang_z=args_cli.max_ang_z,
        )
        cmd_vel_bridge.start()

        # Capture reference so the lambda doesn't close over a changing variable
        _bridge = cmd_vel_bridge

        def _nav_velocity_cmd(env):
            vx, vy, wz = _bridge.get()
            return torch.tensor([[vx, vy, wz]], dtype=torch.float32).to(env.device)

        env_cfg.observations.policy.velocity_commands = ObsTerm(func=_nav_velocity_cmd)
        print(f"[NAV] Autonomous mode active – listening on {args_cli.cmd_vel_topic}")

    # ------------------------------------------------------------------
    # ONNX session
    # ------------------------------------------------------------------
    log_root_path = os.path.abspath(os.path.join("logs", "rsl_rl", agent_cfg.experiment_name))
    if args_cli.checkpoint:
        resume_path = retrieve_file_path(args_cli.checkpoint)
    else:
        resume_path = get_checkpoint_path(log_root_path, agent_cfg.load_run, agent_cfg.load_checkpoint)
    log_dir = os.path.dirname(resume_path)

    onnx_path = _resolve_onnx_path(log_dir, args_cli.onnx)
    ort_session = _make_onnx_session(onnx_path, prefer_gpu=(not args_cli.onnx_cpu))
    input_name = ort_session.get_inputs()[0].name

    # ------------------------------------------------------------------
    # Environment
    # ------------------------------------------------------------------
    env = gym.make(args_cli.task, cfg=env_cfg, render_mode="rgb_array" if args_cli.video else None)
    if isinstance(env.unwrapped, DirectMARLEnv):
        env = multi_agent_to_single_agent(env)
    env = RslRlVecEnvWrapper(env, clip_actions=agent_cfg.clip_actions)

    # ------------------------------------------------------------------
    # ROS2 bridge graph
    # ------------------------------------------------------------------
    if args_cli.enable_ros2_bridge:
        bridge_cfg = Ros2M20BridgeCfg()
        build_ros2_bridge_graph(bridge_cfg)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    obs = env.get_observations()
    dt = env.unwrapped.step_dt

    while simulation_app.is_running():
        start_time = time.time()
        with torch.inference_mode():
            policy_obs = _extract_policy_obs(obs)
            actions_np = ort_session.run(None, {input_name: policy_obs.detach().cpu().numpy()})[0]
            actions = torch.from_numpy(actions_np).to(env.unwrapped.device)
            obs, _, _, _ = env.step(actions)

        if args_cli.keyboard:
            camera_follow(env)

        if args_cli.nav:
            # Optional: print current cmd_vel for debugging
            # vx, vy, wz = cmd_vel_bridge.get()
            # print(f"[NAV] cmd_vel vx={vx:.2f} vy={vy:.2f} wz={wz:.2f}")
            pass

        sleep_time = dt - (time.time() - start_time)
        if args_cli.real_time and sleep_time > 0:
            time.sleep(sleep_time)

    if cmd_vel_bridge is not None:
        cmd_vel_bridge.stop()
    env.close()


if __name__ == "__main__":
    main()
    simulation_app.close()