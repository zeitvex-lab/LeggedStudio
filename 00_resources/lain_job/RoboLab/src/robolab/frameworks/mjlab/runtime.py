"""The smallest useful RoboLab boundary around an MJLab installation.

MJLab is deliberately not imported when RoboLab itself is imported. This keeps
the Isaac Gym and MJLab environments isolatable and makes a missing optional
backend a diagnosable error instead of an import-time failure.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from collections import deque
from pathlib import Path
from typing import Any


class MjlabSourceError(RuntimeError):
    """Raised when the local MJLab source or its runtime cannot be found."""


def _resolve_mjlab_python() -> Path:
    return Path(
        os.environ.get(
            "ROBO_MJLAB_PYTHON",
            "/home/lxy/miniconda3/envs/robolab-mjlab16/bin/python",
        )
    ).expanduser()


def _resolve_mjlab_rsl_rl(source_root: Path) -> Path:
    path = Path(
        os.environ.get("ROBO_MJLAB_RSL_RL_PATH", source_root.parent.parent / "rsl_rl")
    ).expanduser()
    if not (path / "rsl_rl" / "__init__.py").is_file():
        raise MjlabSourceError(f"MJLab bundle is incomplete; missing rsl_rl: {path}")
    return path.resolve()


def _run_worker(*arguments: str) -> dict[str, Any]:
    source_root = resolve_mjlab_source()
    python = _resolve_mjlab_python()
    if not python.is_file():
        raise MjlabSourceError(f"MJLab Python runtime not found: {python}")
    rsl_rl = _resolve_mjlab_rsl_rl(source_root)
    worker = Path(__file__).with_name("worker.py")
    command = [
        str(python),
        str(worker),
        "--mjlab-path",
        str(source_root),
        "--rsl-rl-path",
        str(rsl_rl),
        "--robolab-src",
        str(Path(__file__).resolve().parents[3]),
        *arguments,
    ]
    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    bin_dir = str(python.parent)
    environment["PATH"] = bin_dir + os.pathsep + environment.get("PATH", "")
    process = subprocess.Popen(
        command,
        cwd=Path(__file__).resolve().parents[4],
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output_tail: deque[str] = deque(maxlen=40)
    result_line = None
    assert process.stdout is not None
    for line in process.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        clean = line.rstrip("\n")
        output_tail.append(clean)
        if clean.startswith("ROBO_RESULT="):
            result_line = clean
    returncode = process.wait()
    if returncode != 0 or result_line is None:
        tail = "\n".join(output_tail)
        raise MjlabSourceError(
            f"MJLab worker failed with exit code {returncode}:\n{tail}"
        )
    return json.loads(result_line[len("ROBO_RESULT=") :])


def resolve_mjlab_source(source: str | os.PathLike[str] | None = None) -> Path:
    """Resolve an MJLab ``src`` directory without importing the framework."""

    if source is None:
        source = os.environ.get("ROBO_MJLAB_PATH")
    if source is None:
        source = Path(__file__).resolve().parents[4] / "backends" / "mjlab" / "mjlab"

    root = Path(source).expanduser().resolve()
    src_root = root / "src" if (root / "src" / "mjlab").is_dir() else root
    package_init = src_root / "mjlab" / "__init__.py"
    if not package_init.is_file():
        raise MjlabSourceError(
            f"MJLab source not found at {src_root}. Set ROBO_MJLAB_PATH to its "
            "checkout or install MJLab in the selected environment."
        )
    return src_root


def _import_mjlab(source: str | os.PathLike[str] | None = None) -> Any:
    """Import MJLab from the resolved source path in this process."""

    src_root = resolve_mjlab_source(source)
    bundled_rsl_rl = src_root.parent.parent / "rsl_rl"
    if (bundled_rsl_rl / "rsl_rl" / "__init__.py").is_file():
        bundled_rsl_rl_str = str(bundled_rsl_rl)
        if bundled_rsl_rl_str not in sys.path:
            sys.path.insert(0, bundled_rsl_rl_str)
    source_str = str(src_root)
    if source_str not in sys.path:
        sys.path.insert(0, source_str)
    importlib.invalidate_caches()
    try:
        return importlib.import_module("mjlab")
    except ImportError as exc:
        raise MjlabSourceError(
            "MJLab source was found, but its dependencies are unavailable in the "
            "current Python environment. Use the dedicated MJLab environment."
        ) from exc


def list_mjlab_tasks(
    source: str | os.PathLike[str] | None = None,
) -> list[str]:
    """Return task IDs after importing MJLab's task packages."""

    if source is None:
        return list(_run_worker("list")["tasks"])
    _import_mjlab(source)
    importlib.import_module("mjlab.tasks")
    registry = importlib.import_module("mjlab.tasks.registry")
    return list(registry.list_tasks())


def run_mjlab_smoke(
    task_id: str = "Mjlab-Velocity-Flat-Unitree-Go1",
    *,
    num_envs: int = 1,
    device: str | None = None,
    seed: int = 0,
    source: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Load, reset, and step one real MJLab task.

    The result is JSON-serializable and is intentionally a framework-neutral
    diagnostic record rather than a new environment abstraction.
    """

    if num_envs < 1:
        raise ValueError("num_envs must be positive")
    if source is None:
        return _run_worker(
            "smoke",
            "--task",
            task_id,
            "--num-envs",
            str(num_envs),
            "--device",
            device or "cuda:0",
            "--seed",
            str(seed),
        )
    _import_mjlab(source)
    importlib.import_module("mjlab.tasks")
    import torch

    registry = importlib.import_module("mjlab.tasks.registry")
    known_tasks = registry.list_tasks()
    if task_id not in known_tasks:
        raise ValueError(f"Unknown MJLab task {task_id!r}; choose from {known_tasks}")

    env_cfg = registry.load_env_cfg(task_id)
    env_cfg.scene.num_envs = num_envs
    selected_device = device or ("cuda:0" if torch.cuda.is_available() else "cpu")
    env_cls = importlib.import_module("mjlab.envs").ManagerBasedRlEnv
    env = env_cls(cfg=env_cfg, device=selected_device)
    try:
        observations, _ = env.reset(seed=seed)
        actor_obs = observations["actor"]
        if not isinstance(actor_obs, torch.Tensor):
            raise TypeError(
                "MJLab actor observations must be a tensor for the RL contract"
            )
        action_dim = env.single_action_space.shape[0]
        action = torch.zeros((num_envs, action_dim), device=selected_device)
        next_observations, reward, terminated, truncated, _ = env.step(action)
        next_actor_obs = next_observations["actor"]
        return {
            "backend": "mjlab",
            "task_id": task_id,
            "device": selected_device,
            "num_envs": num_envs,
            "actor_observation_shape": list(actor_obs.shape),
            "critic_observation_shape": list(observations["critic"].shape),
            "action_shape": list(action.shape),
            "next_actor_observation_shape": list(next_actor_obs.shape),
            "reward_shape": list(reward.shape),
            "terminated_shape": list(terminated.shape),
            "truncated_shape": list(truncated.shape),
        }
    finally:
        env.close()


def run_mjlab_train(
    task_id: str = "Mjlab-Velocity-Flat-Unitree-Go1",
    *,
    num_envs: int = 64,
    device: str = "cuda:0",
    seed: int = 0,
    max_iterations: int = 1,
    run_dir: str | Path | None = None,
    resume_from: str | Path | None = None,
    recipe_path: str | Path | None = None,
    checkpoint_interval: int = 300,
) -> dict[str, Any]:
    """Run MJLab's native RSL-RL PPO training loop in its worker environment."""

    if num_envs < 1 or max_iterations < 1 or checkpoint_interval < 1:
        raise ValueError("num_envs, max_iterations and checkpoint_interval must be positive")
    output_dir = Path(run_dir or (Path.cwd() / "logs" / f"mjlab_{task_id}"))
    args = [
        "train",
        "--task",
        task_id,
        "--num-envs",
        str(num_envs),
        "--device",
        device,
        "--seed",
        str(seed),
        "--max-iterations",
        str(max_iterations),
        "--checkpoint-interval",
        str(checkpoint_interval),
        "--run-dir",
        str(output_dir),
    ]
    if recipe_path is not None:
        args.extend(["--recipe", str(Path(recipe_path).resolve())])
    if resume_from is not None:
        checkpoint = Path(resume_from).expanduser()
        if not checkpoint.is_file():
            raise FileNotFoundError(f"checkpoint does not exist: {checkpoint}")
        args.extend(["--resume-from", str(checkpoint.resolve())])
    return _run_worker(*args)


def run_mjlab_play(
    checkpoint: str | Path,
    task_id: str = "Mjlab-Velocity-Flat-Unitree-Go1",
    *,
    num_envs: int = 1,
    device: str = "cuda:0",
    seed: int = 0,
    steps: int = 256,
    visualize: bool = False,
) -> dict[str, Any]:
    """Run a trained policy in the native MJLab environment."""

    checkpoint_path = Path(checkpoint).expanduser()
    if not checkpoint_path.is_file():
        raise FileNotFoundError(f"checkpoint does not exist: {checkpoint_path}")
    args = [
        "play",
        "--task",
        task_id,
        "--num-envs",
        str(num_envs),
        "--device",
        device,
        "--seed",
        str(seed),
        "--steps",
        str(steps),
        "--checkpoint",
        str(checkpoint_path.resolve()),
    ]
    if visualize:
        args.append("--visualize")
    return _run_worker(*args)


def run_mjlab_evaluate(
    checkpoint: str | Path,
    task_id: str = "Mjlab-Velocity-Flat-Unitree-Go1",
    *,
    num_envs: int = 64,
    device: str = "cuda:0",
    seed: int = 0,
    steps: int = 512,
) -> dict[str, Any]:
    """Evaluate a trained velocity policy with normalized tracking metrics."""

    checkpoint_path = Path(checkpoint).expanduser()
    if not checkpoint_path.is_file():
        raise FileNotFoundError(f"checkpoint does not exist: {checkpoint_path}")
    return _run_worker(
        "evaluate",
        "--task",
        task_id,
        "--num-envs",
        str(num_envs),
        "--device",
        device,
        "--seed",
        str(seed),
        "--steps",
        str(steps),
        "--checkpoint",
        str(checkpoint_path.resolve()),
    )
