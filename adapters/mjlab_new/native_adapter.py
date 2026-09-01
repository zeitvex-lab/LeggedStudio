"""Native MJLab adapter boundary.

The latest mjlab source is manager-based and must run in its own locked
environment. This module translates a resolved recipe into a launch spec and
performs preflight without importing mjlab into the FastAPI process.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_SOURCE = Path(os.environ.get("LEGGED_STUDIO_MJLAB_SOURCE", "C:/Users/31560/Documents/00_open/mjlab_new/mjlab"))


def _probe_runtime(source: Path) -> dict[str, Any]:
    """Check native dependencies in candidate worker interpreters."""
    candidates = []
    explicit = os.environ.get("LEGGED_STUDIO_MJLAB_PYTHON")
    if explicit:
        candidates.append(Path(explicit))
    adapter_venv = Path(__file__).parent.parent / "mjlab" / ".venv"
    candidates.append(adapter_venv / "Scripts" / "python.exe")
    candidates.append(Path(sys.executable))
    modules = "import tyro, warp, mujoco_warp, rsl_rl, mjlab; import torch; print('ok cuda=' + str(int(torch.cuda.is_available())))"
    probes = []
    for python in dict.fromkeys(candidates):
        if not python.exists():
            continue
        env = os.environ.copy()
        env["PYTHONPATH"] = str(source / "src") + os.pathsep + env.get("PYTHONPATH", "")
        try:
            result = subprocess.run([str(python), "-c", modules], capture_output=True, text=True, timeout=20, env=env)
            output = result.stdout.strip()
            probes.append({"python": str(python), "available": result.returncode == 0 and output.startswith("ok"), "cuda_available": output.endswith("cuda=1"), "error": result.stderr.strip()[-500:] if result.returncode else None})
        except (OSError, subprocess.SubprocessError) as exc:
            probes.append({"python": str(python), "available": False, "error": str(exc)})
    return {"available": any(item["available"] for item in probes), "interpreters": probes}


def preflight(source: Path = DEFAULT_SOURCE) -> dict[str, Any]:
    source = source.expanduser().resolve()
    package_root = source / "src"
    report = {
        "source": str(source),
        "exists": source.exists(),
        "package_root": str(package_root),
        "manager_env_available": (package_root / "mjlab" / "envs" / "manager_based_rl_env.py").exists(),
        "runner_available": (package_root / "mjlab" / "rl" / "runner.py").exists(),
        "python_importable_in_control_plane": bool(importlib.util.find_spec("mjlab")),
        "status": "candidate" if source.exists() else "not_found",
    }
    report["runtime"] = _probe_runtime(source) if source.exists() else {"available": False, "interpreters": []}
    report["execution_ready"] = False
    report["execution_note"] = "Native worker launch is intentionally gated until a registered Go2/Go2W task adapter is available."
    return report


def build_launch_spec(recipe: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    """Produce the manager-based inputs a future worker will consume."""
    return {
        "backend": "native_mjlab",
        "source": str(DEFAULT_SOURCE),
        "task_name": recipe.get("task_name", "forward_walk"),
        "algorithm": recipe.get("algorithm", "PPO"),
        "num_envs": recipe.get("environment", {}).get("num_envs", 4096),
        "terrain": recipe.get("environment", {}).get("terrain_type", "plane"),
        "commands": {"lin_vel_x": [-1.0, 1.0], "lin_vel_y": [-1.0, 1.0], "ang_vel_yaw": [-1.0, 1.0]},
        "observation_components": contract.get("observation", {}).get("components", []),
        "reward_scales": recipe.get("reward_scales", {}),
        "managers": ["scene", "commands", "observations", "actions", "rewards", "terminations", "curriculum", "metrics"],
    }
