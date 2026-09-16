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
import threading
import time
from pathlib import Path
from typing import Any

from adapters.mjlab.runtime_compat import evaluate_package_runtime


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_WORKSPACE_ROOT = _PROJECT_ROOT.parent

# Preflight reports are expensive (torch import in up to three interpreters)
# and only depend on the source tree + installed environments, so a short TTL
# keeps the web console responsive without making runtime changes invisible.
_PREFLIGHT_TTL_S = 300.0
_PROBE_TIMEOUT_S = 20.0 * 3 + 5.0  # worst case: three sequential probes
_PREFLIGHT_LOCK = threading.Lock()
_PREFLIGHT_CACHE: dict[str, dict[str, Any]] = {}
_PREFLIGHT_INFLIGHT: dict[str, threading.Event] = {}
DEFAULT_SOURCE = Path(os.environ.get("LEGGED_STUDIO_MJLAB_SOURCE", str(_WORKSPACE_ROOT / "mjlab_new" / "mjlab") if os.name == "nt" else str(_PROJECT_ROOT / "vendor" / "mjlab")))
# Robot assets are package-owned.  The optional override is retained for
# future third-party packages, but the default no longer points at the legacy
# ``unitree_rl_mjlab`` repository.
DEFAULT_EXTENSION = Path(os.environ["LEGGED_STUDIO_MJLAB_EXTENSION"]) if os.environ.get("LEGGED_STUDIO_MJLAB_EXTENSION") else (_PROJECT_ROOT / "assets" / "robots")


def _venv_python(venv: Path) -> Path:
    """Resolve the interpreter layout on Windows and POSIX hosts."""
    from contracts.path_bootstrap import venv_python

    return venv_python(venv)


def _probe_runtime(source: Path) -> dict[str, Any]:
    """Check native dependencies in candidate worker interpreters."""
    candidates = []
    explicit = os.environ.get("LEGGED_STUDIO_MJLAB_PYTHON")
    if explicit:
        candidates.append(Path(explicit))
    # 适配器 venv 落点可由 LEGGED_STUDIO_MJLAB_VENV 覆盖（云原生开发镜像把 CPU 训练
    # venv 装在仓库外，避免被 bind mount 覆盖）。
    from contracts.path_bootstrap import adapter_venv_dir

    adapter_venv = adapter_venv_dir(default=Path(__file__).parent / ".venv")
    candidates.append(_venv_python(adapter_venv))
    candidates.append(Path(sys.executable))
    modules = "import importlib.metadata as md; import tyro, warp, mujoco_warp, rsl_rl, mjlab; import torch; print('ok|torch=' + torch.__version__ + '|cuda=' + str(int(torch.cuda.is_available())) + '|count=' + str(torch.cuda.device_count()) + '|mjlab=' + str(getattr(mjlab, '__version__', md.version('mjlab'))) + '|python=' + __import__('sys').version.split()[0])"
    probes = []
    source_path = source / "src"
    for python in dict.fromkeys(candidates):
        if not python.exists():
            continue
        env = os.environ.copy()
        # 源码树存在才前置 PYTHONPATH（开发 checkout 遮蔽已安装版本）；不存在时不前置 ——
        # 前置一个不存在的目录虽是 no-op，但把"源码树可以没有"这件事说清楚更重要（A5）。
        if source_path.exists():
            env["PYTHONPATH"] = str(source_path) + os.pathsep + env.get("PYTHONPATH", "")
        try:
            result = subprocess.run([str(python), "-c", modules], capture_output=True, text=True, timeout=20, env=env)
            output = result.stdout.strip()
            fields = dict(item.split("=", 1) for item in output.split("|")[1:] if "=" in item) if output.startswith("ok|") else {}
            probes.append({"python": str(python), "available": result.returncode == 0 and output.startswith("ok|"), "torch_version": fields.get("torch"), "cuda_available": fields.get("cuda") == "1", "cuda_device_count": int(fields.get("count", "0")), "mjlab_version": fields.get("mjlab"), "python_version": fields.get("python"), "error": result.stderr.strip()[-500:] if result.returncode else None})
        except (OSError, subprocess.SubprocessError) as exc:
            probes.append({"python": str(python), "available": False, "error": str(exc)})
    return {"available": any(item["available"] for item in probes), "interpreters": probes}


def preflight(source: Path = DEFAULT_SOURCE, force: bool = False) -> dict[str, Any]:
    """Report native MJLab readiness.

    The runtime probe shells out to worker interpreters and imports torch, so
    it can take tens of seconds — and nothing outside training needs it. Page
    loads therefore call this with ``force=False``: they get the last known
    snapshot (cheap filesystem checks included) or a ``not_probed`` skeleton
    and never spawn a subprocess. Only the training path passes
    ``force=True``, which runs (or reuses an in-flight) probe and caches the
    report.
    """
    source = source.expanduser().resolve()
    cache_key = str(source)
    with _PREFLIGHT_LOCK:
        cached = _PREFLIGHT_CACHE.get(cache_key)
    if cached:
        report = dict(cached["report"])
        report["cached"] = True
        report["cache_age_s"] = round(time.monotonic() - cached["at"], 1)
        report["stale"] = time.monotonic() - cached["at"] >= _PREFLIGHT_TTL_S
        return report
    if not force:
        # Cheap filesystem-only snapshot: no worker interpreter, no torch.
        report = _filesystem_preflight(source)
        report["status"] = "not_probed"
        report["not_probed"] = True
        return report

    deadline = time.monotonic() + _PROBE_TIMEOUT_S * 4
    while True:
        with _PREFLIGHT_LOCK:
            event = _PREFLIGHT_INFLIGHT.get(cache_key)
            if event is None:
                event = threading.Event()
                _PREFLIGHT_INFLIGHT[cache_key] = event
                break
        # Another thread is probing right now; wait for its result instead of
        # spawning a duplicate torch import.
        event.wait(timeout=max(deadline - time.monotonic(), 0.1))
        with _PREFLIGHT_LOCK:
            cached = _PREFLIGHT_CACHE.get(cache_key)
        if cached:
            report = dict(cached["report"])
            report["cached"] = True
            return report
    try:
        report = _preflight_uncached(source)
    finally:
        with _PREFLIGHT_LOCK:
            _PREFLIGHT_CACHE[cache_key] = {"at": time.monotonic(), "report": dict(report)}
            done = _PREFLIGHT_INFLIGHT.pop(cache_key, None)
        if done:
            done.set()
    return report


def _filesystem_preflight(source: Path) -> dict[str, Any]:
    """Preflight without the interpreter probe (stat calls only)."""
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
        "extension_root": str(DEFAULT_EXTENSION),
        "extension_exists": DEFAULT_EXTENSION.exists(),
        "package_extensions_root": str(DEFAULT_EXTENSION),
    }
    report["runtime"] = {"available": False, "interpreters": []}
    report["smoke_ready"] = False
    report["execution_ready"] = False
    report["training_ready"] = False
    # 形状与探测后的报告保持一致（前端/接口读同一个字段名，缺了会各自兜底出第二套语义）。
    report["source_mode"] = None
    report["not_ready_reason"] = None
    report["execution_note"] = "training runtime has not been probed yet; it is verified when a training run starts"
    return report


def _preflight_uncached(source: Path) -> dict[str, Any]:
    source = source.expanduser().resolve()
    package_root = source / "src"
    manager_env = (package_root / "mjlab" / "envs" / "manager_based_rl_env.py").exists()
    runner = (package_root / "mjlab" / "rl" / "runner.py").exists()
    report = {
        "source": str(source),
        "exists": source.exists(),
        "package_root": str(package_root),
        "manager_env_available": manager_env,
        "runner_available": runner,
        "python_importable_in_control_plane": bool(importlib.util.find_spec("mjlab")),
        "status": "candidate" if source.exists() else "not_found",
        "extension_root": str(DEFAULT_EXTENSION),
        "extension_exists": DEFAULT_EXTENSION.exists(),
        "package_extensions_root": str(DEFAULT_EXTENSION),
    }
    # **运行时探测是唯一硬证据**：它回答"worker 解释器里到底能不能 import mjlab"。
    # 源码树存在时 <source>/src 前置到 PYTHONPATH（开发 checkout 遮蔽已安装版本）；
    # 不存在时 mjlab 来自**已安装发行版**（`adapters/mjlab/pyproject.toml` 钉着
    # `mjlab==1.6.0`，venv 里一定有一份完整的），源码树只是可选遮蔽层。
    report["runtime"] = _probe_runtime(source)
    runtime_ok = bool(report["runtime"]["available"])
    source_complete = bool(report["exists"] and manager_env and runner)

    # 就绪判据（V4 单一真值：调用方只读这里，不许自己再拼一遍条件 —— 见 create.py）。
    #   * 运行时必须能 import mjlab：这是真依赖，缺了必 fail-closed（行为不变）；
    #   * **源码树不存在** ⇒ 走已安装发行版。**2026-09-16 A5 修的就是这条**：旧判据要求
    #     `exists ∧ manager_env_available`，"必须有源码 checkout"是历史前提（mjlab 曾是
    #     源码安装），于是云开发容器/服务端没有 `vendor/mjlab` 时点"开始训练"恒 501，
    #     而同一环境里 `scripts/cpu_training_smoke_gate.sh` 明明能真练；
    #   * 源码树存在但**不完整** ⇒ 仍判未就绪：残份 checkout 会遮蔽已安装版本，
    #     "半份源码"比没有更危险（宁可报错，也不静默用半份）。
    if not runtime_ok:
        report["source_mode"] = "unavailable"
        report["not_ready_reason"] = (
            "no candidate worker interpreter can import torch/mjlab/rsl_rl — provision the training "
            "venv (scripts/provision_cpu_training.sh) or point LEGGED_STUDIO_MJLAB_VENV at one"
        )
    elif report["exists"] and not source_complete:
        report["source_mode"] = "checkout_incomplete"
        report["not_ready_reason"] = (
            f"MJLab source checkout at {source} is incomplete (needs src/mjlab/envs/"
            "manager_based_rl_env.py and src/mjlab/rl/runner.py) — repair the checkout, or remove it "
            "so the installed mjlab distribution is used instead"
        )
    else:
        report["source_mode"] = "checkout" if source_complete else "installed_package"
        report["not_ready_reason"] = None

    ready = report["source_mode"] in ("checkout", "installed_package")
    # Core MJLab readiness is independent of any robot package; package extensions are
    # checked by the caller only when that package explicitly requests them.
    report["smoke_ready"] = ready
    report["execution_ready"] = ready
    report["training_ready"] = ready
    report["execution_note"] = (
        f"MJLab core is ready ({report['source_mode']}); package-specific extensions are optional "
        "and are validated when selected. CUDA depends on the selected native Python environment."
        if ready
        else str(report["not_ready_reason"])
    )
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


def package_runtime_diagnostics(package: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    """Return package/runtime compatibility without importing package code."""
    runtime = report.get("runtime", {}) if isinstance(report, dict) else {}
    selected = next((item for item in runtime.get("interpreters", []) if item.get("available")), {})
    values = {
        "mjlab_version": selected.get("mjlab_version"),
        "python_version": selected.get("python_version"),
        "torch_version": selected.get("torch_version"),
    }
    return evaluate_package_runtime(package, values)
