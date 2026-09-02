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


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_WORKSPACE_ROOT = _PROJECT_ROOT.parent
DEFAULT_SOURCE = Path(os.environ.get("LEGGED_STUDIO_MJLAB_SOURCE", str(_WORKSPACE_ROOT / "mjlab_new" / "mjlab") if os.name == "nt" else str(_PROJECT_ROOT / "vendor" / "mjlab")))
DEFAULT_EXTENSION = Path(os.environ.get("LEGGED_STUDIO_MJLAB_EXTENSION", "C:/Users/31560/Documents/00_open/uni_rl/unitree_rl_mjlab" if os.name == "nt" else str(_PROJECT_ROOT / "vendor" / "unitree_rl_mjlab")))


def _venv_python(venv: Path) -> Path:
    """Resolve the interpreter layout on Windows and POSIX hosts."""
    return venv / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")


def _probe_runtime(source: Path) -> dict[str, Any]:
    """Check native dependencies in candidate worker interpreters."""
    candidates = []
    explicit = os.environ.get("LEGGED_STUDIO_MJLAB_PYTHON")
    if explicit:
        candidates.append(Path(explicit))
    adapter_venv = Path(__file__).parent.parent / "mjlab" / ".venv"
    candidates.append(_venv_python(adapter_venv))
    candidates.append(Path(sys.executable))
    modules = "import tyro, warp, mujoco_warp, rsl_rl, mjlab; import torch; print('ok|torch=' + torch.__version__ + '|cuda=' + str(int(torch.cuda.is_available())) + '|count=' + str(torch.cuda.device_count()))"
    probes = []
    for python in dict.fromkeys(candidates):
        if not python.exists():
            continue
        env = os.environ.copy()
        env["PYTHONPATH"] = str(source / "src") + os.pathsep + env.get("PYTHONPATH", "")
        try:
            result = subprocess.run([str(python), "-c", modules], capture_output=True, text=True, timeout=20, env=env)
            output = result.stdout.strip()
            fields = dict(item.split("=", 1) for item in output.split("|")[1:] if "=" in item) if output.startswith("ok|") else {}
            probes.append({"python": str(python), "available": result.returncode == 0 and output.startswith("ok|"), "torch_version": fields.get("torch"), "cuda_available": fields.get("cuda") == "1", "cuda_device_count": int(fields.get("count", "0")), "error": result.stderr.strip()[-500:] if result.returncode else None})
        except (OSError, subprocess.SubprocessError) as exc:
            probes.append({"python": str(python), "available": False, "error": str(exc)})
    return {"available": any(item["available"] for item in probes), "interpreters": probes}


def preflight(source: Path = DEFAULT_SOURCE) -> dict[str, Any]:
    source = source.expanduser().resolve()
    package_root = source / "src"
    project_root = Path(__file__).resolve().parents[2]
    go2w_xml = project_root / "assets" / "robots" / "unitree_go2w" / "go2w.xml"
    go2w_assets = go2w_xml.parent / "assets"
    report = {
        "source": str(source),
        "exists": source.exists(),
        "package_root": str(package_root),
        "manager_env_available": (package_root / "mjlab" / "envs" / "manager_based_rl_env.py").exists(),
        "runner_available": (package_root / "mjlab" / "rl" / "runner.py").exists(),
        "python_importable_in_control_plane": bool(importlib.util.find_spec("mjlab")),
        "status": "candidate" if source.exists() else "not_found",
        "extension_root": str(DEFAULT_EXTENSION),
        "extension_exists": DEFAULT_EXTENSION.exists(),
        "go2_task_source": (DEFAULT_EXTENSION / "src" / "tasks" / "velocity" / "config" / "go2" / "__init__.py").exists(),
        "go2w_task_source": (project_root / "adapters" / "mjlab" / "native_worker.py").exists(),
        "go2w_asset": str(go2w_xml),
        "go2w_task_available": go2w_xml.exists() and go2w_assets.exists() and any(go2w_assets.iterdir()),
    }
    report["runtime"] = _probe_runtime(source) if source.exists() else {"available": False, "interpreters": []}
    # Core MJLab readiness is independent of any robot package. Package
    # extensions (for example the bundled Go2/Go2W recipes) are checked by
    # the caller only when that package explicitly requests them.
    report["smoke_ready"] = bool(report["exists"] and report["manager_env_available"] and report["runtime"]["available"])
    report["execution_ready"] = report["smoke_ready"]
    report["training_ready"] = report["smoke_ready"]
    report["execution_note"] = "MJLab core is ready; package-specific extensions are optional and are validated when selected. CUDA depends on the selected native Python environment."
    return report


def build_launch_spec(recipe: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    """Produce the manager-based inputs a future worker will consume."""
    return {
        "backend": "native_mjlab",
        "source": str(DEFAULT_SOURCE),
        "extension_root": str(DEFAULT_EXTENSION),
        "task_name": recipe.get("task_name", "forward_walk"),
        "algorithm": recipe.get("algorithm", "PPO"),
        "num_envs": recipe.get("environment", {}).get("num_envs", 4096),
        "terrain": recipe.get("environment", {}).get("terrain_type", "plane"),
        "commands": {"lin_vel_x": [-1.0, 1.0], "lin_vel_y": [-1.0, 1.0], "ang_vel_yaw": [-1.0, 1.0]},
        "observation_components": contract.get("observation", {}).get("components", []),
        "reward_scales": recipe.get("reward_scales", {}),
        "managers": ["scene", "commands", "observations", "actions", "rewards", "terminations", "curriculum", "metrics"],
    }
