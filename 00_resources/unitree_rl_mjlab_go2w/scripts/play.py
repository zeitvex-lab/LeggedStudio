"""Script to play RL agent with RSL-RL."""

import os
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal
import torch
import tyro

# Ensure script uses local workspace package when invoked as `python scripts/play.py`.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mjlab.rsl_rl.runners import OnPolicyRunner
from mjlab.envs import ManagerBasedRlEnv
from mjlab.rl import RslRlVecEnvWrapper
from mjlab.tasks.registry import (
    list_tasks,
    load_env_cfg,
    load_rl_cfg,
    load_runner_cls,
    resolve_task_name,
)
from mjlab.tasks.tracking.mdp import MotionCommandCfg
from mjlab.terrains import TerrainImporterCfg
from mjlab.terrains.config import ROUGH_TERRAINS_CFG
from mjlab.utils.os import get_wandb_checkpoint_path, resolve_local_checkpoint_path
from mjlab.utils.torch import configure_torch_backends
from mjlab.utils.wrappers import VideoRecorder
from mjlab.viewer import NativeMujocoViewer, ViserPlayViewer
from scripts._task_cli import (
    TaskSelectionError,
    consume_experimental_flag,
    consume_task_selection,
    normalize_task_name,
)


@dataclass(frozen=True)
class PlayConfig:
    agent: Literal["zero", "random", "trained"] = "trained"
    motion_file: str | None = None
    wandb_run_path: str | None = None
    checkpoint_file: str | None = None
    num_envs: int | None = None
    device: str | None = None
    video: bool = False
    video_length: int = 200
    video_height: int | None = None
    video_width: int | None = None
    camera: int | str | None = None
    viewer: Literal["auto", "native", "viser"] = "auto"
    terrain: Literal["default", "rough_only", "flat_only"] = "default"
    fixed_twist: tuple[float, float, float] | None = None

    # Internal flag used by demo script.
    _demo_mode: tyro.conf.Suppress[bool] = False


def run_play(task_id: str, cfg: PlayConfig, include_experimental: bool = False):
    configure_torch_backends()

    device = cfg.device or ("cuda:0" if torch.cuda.is_available() else "cpu")

    env_cfg = load_env_cfg(
        task_id,
        play=True,
        include_experimental=include_experimental,
    )
    agent_cfg = load_rl_cfg(task_id, include_experimental=include_experimental)

    if cfg.terrain == "flat_only":
        if env_cfg.scene.terrain is not None:
            env_cfg.scene.terrain.terrain_type = "plane"
            env_cfg.scene.terrain.terrain_generator = None
        if "terrain_levels" in env_cfg.curriculum:
            del env_cfg.curriculum["terrain_levels"]
    elif cfg.terrain == "rough_only":
        if env_cfg.scene.terrain is None:
            env_cfg.scene.terrain = TerrainImporterCfg(
                terrain_type="generator",
                terrain_generator=replace(ROUGH_TERRAINS_CFG),
                max_init_terrain_level=5,
            )
            print("[INFO] Injected rough terrain generator (task had no terrain config).")
        elif env_cfg.scene.terrain.terrain_generator is None:
            env_cfg.scene.terrain.terrain_type = "generator"
            env_cfg.scene.terrain.terrain_generator = replace(ROUGH_TERRAINS_CFG)
            env_cfg.scene.terrain.max_init_terrain_level = 5
            print(
                "[INFO] Injected rough terrain generator for play "
                "(task is normally flat/plane)."
            )

        tg = env_cfg.scene.terrain.terrain_generator
        if tg is None:
            raise RuntimeError("Failed to configure rough terrain generator.")

        tg.curriculum = False
        tg.difficulty_range = (0.25, 0.65)
        if "flat" in tg.sub_terrains:
            tg.sub_terrains["flat"].proportion = 0.0

    if cfg.fixed_twist is not None:
        if "twist" not in env_cfg.commands:
            raise ValueError(
                "`--fixed-twist` is only supported for velocity tasks that define a `twist` command."
            )

        twist_cmd = env_cfg.commands["twist"]
        if not hasattr(twist_cmd, "ranges"):
            raise TypeError("`twist` command does not expose velocity ranges.")

        vx, vy, wz = cfg.fixed_twist
        twist_cmd.ranges.lin_vel_x = (vx, vx)
        if hasattr(twist_cmd.ranges, "lin_vel_y"):
            twist_cmd.ranges.lin_vel_y = (vy, vy)
        if hasattr(twist_cmd.ranges, "ang_vel_z"):
            twist_cmd.ranges.ang_vel_z = (wz, wz)

        if hasattr(twist_cmd, "heading_command"):
            twist_cmd.heading_command = False
        if hasattr(twist_cmd, "rel_heading_envs"):
            twist_cmd.rel_heading_envs = 0.0
        if hasattr(twist_cmd.ranges, "heading"):
            twist_cmd.ranges.heading = None
        if hasattr(twist_cmd, "rel_standing_envs"):
            twist_cmd.rel_standing_envs = 0.0

        # Keep the command fixed by disabling command-range curriculum updates.
        env_cfg.curriculum.pop("command_vel", None)

        print(
            f"[INFO] Using fixed twist command: vx={vx:.3f} m/s, vy={vy:.3f} m/s, wz={wz:.3f} rad/s"
        )

    DUMMY_MODE = cfg.agent in {"zero", "random"}
    TRAINED_MODE = not DUMMY_MODE

    # Check if this is a tracking task by checking for motion command.
    is_tracking_task = "motion" in env_cfg.commands and isinstance(
        env_cfg.commands["motion"], MotionCommandCfg
    )

    if is_tracking_task and cfg._demo_mode:
        # Demo mode: use uniform sampling to see more diversity with num_envs > 1.
        motion_cmd = env_cfg.commands["motion"]
        assert isinstance(motion_cmd, MotionCommandCfg)
        motion_cmd.sampling_mode = "uniform"

    if is_tracking_task:
        motion_cmd = env_cfg.commands["motion"]
        assert isinstance(motion_cmd, MotionCommandCfg)

        if cfg.motion_file is None:
            raise ValueError(
                "Tracking tasks require --motion-file pointing to a local motion npz."
            )

        motion_path = Path(cfg.motion_file).expanduser().resolve()
        if not motion_path.exists():
          raise FileNotFoundError(f"Motion file not found: {motion_path}")

        motion_cmd.motion_file = str(motion_path)

        if cfg._demo_mode:
          # Demo mode: increase diversity
          motion_cmd.sampling_mode = "uniform"

        print(f"[INFO] Using local motion file: {motion_cmd.motion_file}")

    log_dir: Path | None = None
    resume_path: Path | None = None

    if TRAINED_MODE:
        log_root_path = (Path("logs") / "rsl_rl" / agent_cfg.experiment_name).resolve()
    if cfg.checkpoint_file is not None:
        checkpoint_target = Path(cfg.checkpoint_file).expanduser()
        target_is_dir = checkpoint_target.exists() and checkpoint_target.is_dir()
        resume_path = resolve_local_checkpoint_path(checkpoint_target)
        if target_is_dir:
            print(
                "[INFO]: Loading latest checkpoint from run directory: "
                f"{checkpoint_target.resolve()} -> {resume_path.name}"
            )
        else:
            print(f"[INFO]: Loading checkpoint: {resume_path.name}")
    else:
        if cfg.wandb_run_path is None:
            raise ValueError(
                "`wandb_run_path` is required when `checkpoint_file` is not provided."
            )
        resume_path, was_cached = get_wandb_checkpoint_path(
            log_root_path, Path(cfg.wandb_run_path)
        )
        # Extract run_id and checkpoint name from path for display.
        run_id = resume_path.parent.name
        checkpoint_name = resume_path.name
        cached_str = "cached" if was_cached else "downloaded"
        print(
            f"[INFO]: Loading checkpoint: {checkpoint_name} (run: {run_id}, {cached_str})"
        )
    log_dir = resume_path.parent

    if cfg.num_envs is not None:
        env_cfg.scene.num_envs = cfg.num_envs
    if cfg.video_height is not None:
        env_cfg.viewer.height = cfg.video_height
    if cfg.video_width is not None:
        env_cfg.viewer.width = cfg.video_width

    render_mode = "rgb_array" if (TRAINED_MODE and cfg.video) else None
    if cfg.video and DUMMY_MODE:
        print(
            "[WARN] Video recording with dummy agents is disabled (no checkpoint/log_dir)."
        )
    env = ManagerBasedRlEnv(cfg=env_cfg, device=device, render_mode=render_mode)

    if TRAINED_MODE and cfg.video:
        print("[INFO] Recording videos during play")
    assert log_dir is not None  # log_dir is set in TRAINED_MODE block
    env = VideoRecorder(
      env,
      video_folder=log_dir / "videos" / "play",
      step_trigger=lambda step: step == 0,
      video_length=cfg.video_length,
      disable_logger=True,
    )

    env = RslRlVecEnvWrapper(env, clip_actions=agent_cfg.clip_actions)
    if DUMMY_MODE:
        action_shape: tuple[int, ...] = env.unwrapped.action_space.shape  # type: ignore
        if cfg.agent == "zero":
            class PolicyZero:
                def __call__(self, obs) -> torch.Tensor:
                    del obs
                    return torch.zeros(action_shape, device=env.unwrapped.device)
            policy = PolicyZero()
        else:
            class PolicyRandom:
                def __call__(self, obs) -> torch.Tensor:
                    del obs
                    return 2 * torch.rand(action_shape, device=env.unwrapped.device) - 1
            policy = PolicyRandom()

    else:
        runner_cls = (
            load_runner_cls(task_id, include_experimental=include_experimental)
            or OnPolicyRunner
        )
        runner = runner_cls(env, asdict(agent_cfg), device=device)
        runner.load(str(resume_path), map_location=device)
        policy = runner.get_inference_policy(device=device)

    # Handle "auto" viewer selection.
    if cfg.viewer == "auto":
        has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
        resolved_viewer = "native" if has_display else "viser"
        del has_display
    else:
        resolved_viewer = cfg.viewer

    if resolved_viewer == "native":
        NativeMujocoViewer(env, policy).run()
    elif resolved_viewer == "viser":
        ViserPlayViewer(env, policy).run()
    else:
        raise RuntimeError(f"Unsupported viewer backend: {resolved_viewer}")

    env.close()


def main():
    # Parse first argument to choose the task.
    # Import tasks to populate the registry.
    import mjlab.tasks  # noqa: F401

    experimental, argv = consume_experimental_flag(sys.argv[1:])
    indexed_tasks = list_tasks(
        include_experimental=experimental,
        include_aliases=False,
    )
    all_tasks = list_tasks(
        include_experimental=experimental,
        include_aliases=True,
    )
    try:
        task_selection = consume_task_selection(
            argv=argv,
            named_task_choices=all_tasks,
            indexed_task_choices=indexed_tasks,
        )
    except TaskSelectionError as exc:
        raise SystemExit(f"[ERROR] {exc}") from exc

    chosen_task = task_selection.task_id
    remaining_args = task_selection.remaining_args
    if task_selection.used_index:
        print(
            "[INFO] Selected task index "
            f"{task_selection.requested_selector} -> {chosen_task}"
        )

    resolved_task = resolve_task_name(
        chosen_task,
        include_experimental=experimental,
    )
    if task_selection.used_index:
        chosen_task = resolved_task.task_id
    else:
        chosen_task = normalize_task_name(chosen_task, resolved_task.task_id)

    # Parse the rest of the arguments + allow overriding env_cfg and agent_cfg.
    agent_cfg = load_rl_cfg(chosen_task, include_experimental=experimental)

    args = tyro.cli(
        PlayConfig,
        args=remaining_args,
        default=PlayConfig(),
        prog=sys.argv[0] + f" {chosen_task}",
        config=(
            tyro.conf.AvoidSubcommands,
            tyro.conf.FlagConversionOff,
        ),
    )
    del remaining_args, agent_cfg

    run_play(chosen_task, args, include_experimental=experimental)


if __name__ == "__main__":
  main()
