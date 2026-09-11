"""Report whether this interpreter can host the Legged Studio MJLab adapter."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MJLAB_PATH = WORKSPACE_ROOT / "mjlab_new" / "mjlab"
TARGET_PYTHON = (3, 12)
PACKAGE_NAMES = ("mjlab", "torch", "warp-lang", "mujoco", "mujoco-warp", "onnxruntime")


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def gpu_probe() -> dict[str, Any]:
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return {"available": False, "reason": "nvidia-smi not found"}
    command = [
        executable,
        "--query-gpu=name,memory.total,driver_version",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": False, "reason": str(exc)}
    devices = []
    for line in result.stdout.splitlines():
        fields = [field.strip() for field in line.split(",")]
        if len(fields) == 3:
            devices.append({"name": fields[0], "memory_mib": fields[1], "driver": fields[2]})
    return {"available": bool(devices), "devices": devices}


def source_metadata(path: Path) -> dict[str, Any]:
    pyproject = path / "pyproject.toml"
    python_file = path / ".python-version"
    result: dict[str, Any] = {
        "path": str(path.resolve()),
        "exists": path.is_dir(),
        "pyproject": str(pyproject.resolve()),
    }
    if pyproject.is_file():
        with pyproject.open("rb") as stream:
            project = tomllib.load(stream).get("project", {})
        result.update(
            {
                "name": project.get("name"),
                "version": project.get("version"),
                "requires_python": project.get("requires-python"),
            }
        )
    if python_file.is_file():
        result["upstream_python_default"] = python_file.read_text(encoding="utf-8").strip()
    return result


def build_report(mjlab_path: Path = DEFAULT_MJLAB_PATH) -> dict[str, Any]:
    version = platform.python_version()
    python_match = sys.version_info[:2] == TARGET_PYTHON
    source = source_metadata(mjlab_path)
    packages = {name: package_version(name) for name in PACKAGE_NAMES}
    gpu = gpu_probe()
    checks = {
        "python_3_12": python_match,
        "uv_available": shutil.which("uv") is not None,
        "mjlab_source_available": source["exists"] and bool(source.get("version")),
    }
    gpu_available = bool(gpu.get("available"))
    # GPU 不再是 ready 的硬条件：CPU 可以托管仿真与最小训练冒烟，只是吞吐低。
    # GPU 只决定“正式训练”的推荐程度，故单列 gpu_recommended 而不卡 ready。
    runtime_checks = {
        "adapter_packages_installed": all(packages[name] for name in ("mjlab", "torch", "warp-lang", "mujoco", "mujoco-warp")),
    }
    return {
        "schema_version": "mjlab-preflight-1.0",
        "ready": all(checks.values()) and all(runtime_checks.values()),
        "baseline_ready": all(checks.values()),
        "gpu_required": False,
        "gpu_recommended": True,
        "gpu_available": gpu_available,
        "checks": checks,
        "runtime_checks": runtime_checks,
        "python": {
            "executable": sys.executable,
            "version": version,
            "target": "3.12.x",
            "target_match": python_match,
        },
        "uv": shutil.which("uv"),
        "mjlab_source": source,
        "installed_packages": packages,
        "gpu": gpu,
        "notes": [
            "MJLab runs in an isolated adapter process; these packages are not control-plane dependencies.",
            "Upstream MJLab may default to Python 3.13, while the current product baseline remains 3.12.",
            "CPU-only hosts are supported for simulation and smoke validation; formal training is recommended on an NVIDIA GPU (CPU throughput is roughly an order of magnitude lower). MJLab requires an NVIDIA GPU for training upstream.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mjlab-path", type=Path, default=DEFAULT_MJLAB_PATH)
    parser.add_argument("--strict", action="store_true", help="return non-zero when baseline checks fail")
    args = parser.parse_args()
    report = build_report(args.mjlab_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if args.strict and not report["ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
