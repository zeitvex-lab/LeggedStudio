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
from typing import Any, Callable


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MJLAB_PATH = WORKSPACE_ROOT / "mjlab_new" / "mjlab"
TARGET_PYTHON = (3, 12)
PACKAGE_NAMES = ("mjlab", "torch", "warp-lang", "mujoco", "mujoco-warp", "onnxruntime")


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


#: GPU 设备形态三态。不能只用 available 布尔——"有 CUDA 设备" / "刻意跑
#: CPU" / "环境根本没装训练栈" 是三种完全不同的故障与处置。
GPU_MODE_CUDA = "cuda"          # 检测到可用 NVIDIA GPU（正式训练推荐）
GPU_MODE_CPU_ONLY = "cpu-only"  # 无 GPU，但训练栈可用 → 显式 CPU 路径
GPU_MODE_UNAVAILABLE = "unavailable"  # 训练栈不可用 → 查环境供应，别硬跑


def gpu_probe(*, torch_probe: Callable[[], dict[str, Any]] | None = None) -> dict[str, Any]:
    """探测计算设备形态，返回三态 ``mode``（cuda / cpu-only / unavailable）。

    只测一次、两条证据：

    1. ``nvidia-smi``：设备存在性（OS 级，最便宜，且不 import torch）。
    2. 训练栈可导入性：判别"无 GPU"到底是 **CPU 可用** 还是 **环境没装**。
       没有这条，CPU-only 主机与"压根没供应训练栈"的主机会给出同一个结论，
       排障时必须靠猜。

    返回结构在保留历史布尔 ``available``（= ``mode == "cuda"``）与 ``devices`` 的
    同时，新增 ``mode`` / ``cpu_ready`` / ``action``（中文处置），让调用方不必再
    自己拼装结论。
    """
    executable = shutil.which("nvidia-smi")
    gpu_smi_reason: str | None = None
    devices: list[dict[str, Any]] = []
    if executable is None:
        gpu_smi_reason = "nvidia-smi not found"
    else:
        command = [
            executable,
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=True)
        except (OSError, subprocess.SubprocessError) as exc:
            gpu_smi_reason = str(exc)
        else:
            for line in result.stdout.splitlines():
                fields = [field.strip() for field in line.split(",")]
                if len(fields) == 3:
                    devices.append({"name": fields[0], "memory_mib": fields[1], "driver": fields[2]})
            if not devices:
                gpu_smi_reason = "nvidia-smi returned no devices"

    # 训练栈可用性：决定 cpu-only 与 unavailable 的分界。
    stack = (torch_probe or _default_torch_probe)()
    cpu_ready = bool(stack.get("available"))

    if devices:
        mode = GPU_MODE_CUDA
        action = "无需处置；正式训练将使用 CUDA"
    elif cpu_ready:
        mode = GPU_MODE_CPU_ONLY
        action = (
            "CPU 训练链路可用：仿真 / 最小训练冒烟（64 envs × N iters）直接可跑，"
            "device=auto 会落 cpu。正式训练建议使用 NVIDIA GPU（CPU 吞吐低约一个量级）；"
            "需要 GPU 时确认驱动已装并在『配置环境 · 计算设备』切换到 GPU profile。"
        )
    else:
        mode = GPU_MODE_UNAVAILABLE
        action = (
            "既无 NVIDIA GPU，训练栈也未供应——先跑训练环境供应"
            "（scripts/provision_cpu_training.sh，云原生开发镜像已内置 CPU extra），"
            "否则训练/冒烟会在拉起 worker 时失败。"
        )

    return {
        "available": bool(devices),
        "mode": mode,
        "cpu_ready": cpu_ready,
        "devices": devices,
        "torch": stack,
        "action": action,
        "reason": gpu_smi_reason or (f"{len(devices)} device(s)" if devices else None),
    }


def _default_torch_probe() -> dict[str, Any]:
    """训练栈是否可导入（torch/warp/mjlab）——不 import，只看已安装元数据。"""
    names = ("torch", "warp-lang", "mujoco-warp", "mjlab")
    versions = {name: package_version(name) for name in names}
    missing = [name for name, value in versions.items() if not value]
    return {
        "available": not missing,
        "versions": versions,
        "missing": missing,
    }


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
    # 设备形态三态（cuda / cpu-only / unavailable）：给上层一个可直接渲染与
    # 排障的结论，而不是让它从 gpu_available + 包清单里自行推导。
    device_mode = gpu.get("mode") or (GPU_MODE_CUDA if gpu_available else GPU_MODE_UNAVAILABLE)
    return {
        "schema_version": "mjlab-preflight-1.0",
        "ready": all(checks.values()) and all(runtime_checks.values()),
        "baseline_ready": all(checks.values()),
        "gpu_required": False,
        "gpu_recommended": True,
        "gpu_available": gpu_available,
        "device_mode": device_mode,
        "cpu_training_ready": bool(gpu.get("cpu_ready")),
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
