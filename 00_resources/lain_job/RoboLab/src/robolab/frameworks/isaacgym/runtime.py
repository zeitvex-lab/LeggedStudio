"""Launch the legacy Isaac Gym stack in its dedicated Python 3.8 process."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any


class IsaacGymRuntimeError(RuntimeError):
    """Raised when the isolated Isaac Gym worker cannot run successfully."""


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def resolve_isaacgym_runtime() -> tuple[Path, Path, Path]:
    """Resolve the Python executable, Isaac Gym package, and legged_gym source."""

    root = _repository_root()
    python = Path(
        os.environ.get(
            "ROBO_ISAACGYM_PYTHON",
            "/home/lxy/miniconda3/envs/robolab-isaacgym/bin/python",
        )
    ).expanduser()
    sdk = Path(
        os.environ.get(
            "ROBO_ISAACGYM_SDK_PATH", "/home/lxy/SDK/isaacgym/python"
        )
    ).expanduser()
    legged_gym = Path(
        os.environ.get("ROBO_LEGGED_GYM_PATH", root / "backends" / "isaacgym" / "legged_gym")
    ).expanduser()

    missing = [
        str(path)
        for path, marker in (
            (python, python),
            (sdk, sdk / "isaacgym" / "__init__.py"),
            (legged_gym, legged_gym / "legged_gym" / "__init__.py"),
        )
        if not marker.exists()
    ]
    if missing:
        raise IsaacGymRuntimeError(
            "Isaac Gym runtime is incomplete; missing: " + ", ".join(missing)
        )
    return python.resolve(), sdk.resolve(), legged_gym.resolve()


def _resolve_rsl_rl_path(legged_gym: Path) -> Path:
    path = Path(
        os.environ.get("ROBO_ISAACGYM_RSL_RL_PATH", legged_gym.parent / "rsl_rl")
    ).expanduser()
    if not (path / "rsl_rl" / "__init__.py").exists():
        raise IsaacGymRuntimeError(
            "Isaac Gym bundle is incomplete; missing rsl_rl source: " + str(path)
        )
    return path.resolve()


def _run_worker(*arguments: str) -> dict[str, Any]:
    python, sdk, legged_gym = resolve_isaacgym_runtime()
    rsl_rl = _resolve_rsl_rl_path(legged_gym)
    worker = Path(__file__).with_name("worker.py")
    command = [
        str(python),
        str(worker),
        "--isaacgym-path",
        str(sdk),
        "--legged-gym-path",
        str(legged_gym),
        "--rsl-rl-path",
        str(rsl_rl),
        "--robolab-src",
        str(_repository_root() / "src"),
        *arguments,
    ]
    environment = _worker_environment(python)
    # A continuous Viser session intentionally does not produce a final
    # ROBO_RESULT until the user stops it.  In that mode, inherit the terminal
    # streams so startup failures and the viewer URL are visible immediately;
    # capturing stdout here makes the command look frozen for the whole session.
    visualize_continuously = (
        "--visualize" in arguments
        and "--steps" in arguments
        and arguments[arguments.index("--steps") + 1] == "0"
    )
    if visualize_continuously:
        completed = subprocess.run(
            command,
            cwd=_repository_root(),
            env=environment,
            check=False,
        )
        if completed.returncode != 0:
            raise IsaacGymRuntimeError(
                f"Isaac Gym worker failed with exit code {completed.returncode}"
            )
        return {"backend": "isaacgym", "visualizer": "mjlab_viser_bridge"}
    process = subprocess.Popen(
        command,
        cwd=_repository_root(),
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output_tail: deque[str] = deque(maxlen=30)
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
        raise IsaacGymRuntimeError(
            f"Isaac Gym worker failed with exit code {returncode}:\n{tail}"
        )
    return json.loads(result_line[len("ROBO_RESULT=") :])


def _worker_environment(python: Path) -> dict[str, str]:
    """Provide the Conda runtime library path required by Isaac Gym bindings."""

    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    bin_dir = str(python.parent)
    current_path = environment.get("PATH")
    environment["PATH"] = bin_dir + (os.pathsep + current_path if current_path else "")
    library_dir = str(python.parent.parent / "lib")
    current = environment.get("LD_LIBRARY_PATH")
    paths = [library_dir]
    if current:
        paths.append(current)
    environment["LD_LIBRARY_PATH"] = os.pathsep.join(paths)
    return environment


def list_isaacgym_tasks() -> list[str]:
    """List tasks registered by the supplied public legged_gym checkout."""

    result = _run_worker("list")
    return list(result["tasks"])


def run_isaacgym_smoke(
    task_id: str = "a1",
    *,
    num_envs: int = 1,
    device: str = "cuda:0",
    seed: int = 0,
    method_id: str = "ppo",
) -> dict[str, Any]:
    """Create, reset, and step one real legged_gym environment."""

    if num_envs < 1:
        raise ValueError("num_envs must be positive")
    return _run_worker(
        "smoke",
        "--task",
        task_id,
        "--num-envs",
        str(num_envs),
        "--device",
        device,
        "--seed",
        str(seed),
        "--method",
        method_id,
    )


def run_isaacgym_train(
    task_id: str = "a1",
    *,
    num_envs: int = 64,
    device: str = "cuda:0",
    seed: int = 0,
    max_iterations: int = 1,
    run_dir: str | Path | None = None,
    resume_from: str | Path | None = None,
    method_id: str = "ppo",
    recipe_path: str | Path | None = None,
    checkpoint_interval: int = 300,
) -> dict[str, Any]:
    """Run a short real rsl_rl PPO training job in the isolated worker."""

    if num_envs < 1:
        raise ValueError("num_envs must be positive")
    if max_iterations < 1 or checkpoint_interval < 1:
        raise ValueError("max_iterations and checkpoint_interval must be positive")
    output_dir = Path(
        run_dir
        or (
            _repository_root()
            / "logs"
            / f"{datetime.now():%Y%m%d-%H%M%S}_{task_id}_isaacgym"
        )
    )
    arguments = [
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
        "--method",
        method_id,
    ]
    if recipe_path is not None:
        arguments.extend(["--recipe", str(Path(recipe_path).resolve())])
    if resume_from is not None:
        checkpoint = Path(resume_from).expanduser()
        if not checkpoint.is_file():
            raise FileNotFoundError(f"checkpoint does not exist: {checkpoint}")
        arguments.extend(["--resume-from", str(checkpoint.resolve())])
    return _run_worker(*arguments)


def run_isaacgym_play(
    checkpoint: str | Path,
    task_id: str = "a1",
    *,
    num_envs: int = 1,
    device: str = "cuda:0",
    seed: int = 0,
    steps: int = 256,
    visualize: bool = False,
    method_id: str = "ppo",
) -> dict[str, Any]:
    """Run a checkpoint policy, optionally in the native Isaac Gym viewer."""

    if num_envs < 1 or steps < 0 or (steps == 0 and not visualize):
        raise ValueError("num_envs must be positive; steps must be positive unless visualizing")
    checkpoint_path = Path(checkpoint).expanduser()
    if not checkpoint_path.is_file():
        raise FileNotFoundError(f"checkpoint does not exist: {checkpoint_path}")
    arguments = [
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
        "--method",
        method_id,
    ]
    if visualize:
        arguments.append("--visualize")
    return _run_worker(*arguments)


def run_isaacgym_evaluate(
    checkpoint: str | Path,
    task_id: str = "a1",
    *,
    num_envs: int = 64,
    device: str = "cuda:0",
    seed: int = 0,
    steps: int = 512,
    method_id: str = "ppo",
) -> dict[str, Any]:
    """Evaluate a checkpoint in an independent Isaac Gym worker."""

    if num_envs < 1 or steps < 1:
        raise ValueError("num_envs and steps must be positive")
    checkpoint_path = Path(checkpoint).expanduser()
    if not checkpoint_path.is_file():
        raise FileNotFoundError(f"checkpoint does not exist: {checkpoint_path}")
    return _run_worker(
        "play",
        "--task", task_id,
        "--num-envs", str(num_envs),
        "--device", device,
        "--seed", str(seed),
        "--steps", str(steps),
        "--checkpoint", str(checkpoint_path.resolve()),
        "--method", method_id,
        "--evaluation",
    )
