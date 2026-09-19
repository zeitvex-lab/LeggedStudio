"""Settings API for the Legged Studio control plane (Feature 2).

The Electron launcher owns the runtime provisioning metadata (userData/settings.json)
because it drives the Windows runtime bootstrap. The backend exposes the settings
that the *front-end workbench* needs so the settings page works without the
launcher: backend port preference, Python override, GPU/CPU profile, PyPI/Torch
mirror source, and workspace cleanup.

Settings are persisted to a versioned JSON file under the backend data dir
(LEGGED_STUDIO_DATA_DIR or `workspace/`). Values are validated on write so a
malformed file never crashes the control plane.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

router = APIRouter(prefix="/api/settings", tags=["settings"])

DEFAULT_BACKEND_PORT = 8765

# Mirror sources known to the domestic provisioning pipeline
# (scripts/provision_windows_runtime.ps1 reads these env vars).
MIRRORS: dict[str, dict[str, str]] = {
    "tsinghua": {
        "label": "清华 PyPI + 上海交大 cu128",
        "pypi_index": "https://pypi.tuna.tsinghua.edu.cn/simple",
        "torch_index": "https://mirror.sjtu.edu.cn/pytorch-wheels/cu128/",
    },
    "sjtu": {
        "label": "上海交大（PyPI + cu128）",
        "pypi_index": "https://mirror.sjtu.edu.cn/pypi/simple",
        "torch_index": "https://mirror.sjtu.edu.cn/pytorch-wheels/cu128/",
    },
    "official": {
        "label": "官方源（PyPI + PyTorch cu128）",
        "pypi_index": "https://pypi.org/simple",
        "torch_index": "https://download.pytorch.org/whl/cu128",
    },
}


def _data_dir() -> Path:
    configured = os.environ.get("LEGGED_STUDIO_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[1] / "workspace"


def _settings_path() -> Path:
    return _data_dir() / "settings" / "settings.json"


DEFAULT_SETTINGS: dict[str, Any] = {
    "schema_version": "legged-studio-settings-1",
    "backend_port": DEFAULT_BACKEND_PORT,
    "python_path": "",
    "torch_device": "gpu",       # gpu | cpu
    "mirror": "tsinghua",
    "auto_start_backend": False,
}


def read_settings() -> dict[str, Any]:
    try:
        value = json.loads(_settings_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_SETTINGS)
    settings = {**DEFAULT_SETTINGS, **value}
    settings["backend_port"] = _coerce_port(settings.get("backend_port"))
    settings["torch_device"] = "cpu" if settings.get("torch_device") == "cpu" else "gpu"
    settings["mirror"] = settings.get("mirror") if settings.get("mirror") in MIRRORS else "tsinghua"
    return settings


def _coerce_port(value: Any) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError):
        return DEFAULT_BACKEND_PORT
    return port if 1024 <= port <= 65535 else DEFAULT_BACKEND_PORT


def _write_settings(value: dict[str, Any]) -> dict[str, Any]:
    settings = dict(DEFAULT_SETTINGS)
    settings.update(value)
    settings["backend_port"] = _coerce_port(settings.get("backend_port"))
    settings["torch_device"] = "cpu" if settings.get("torch_device") == "cpu" else "gpu"
    settings["mirror"] = settings.get("mirror") if settings.get("mirror") in MIRRORS else "tsinghua"
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return settings


class SettingsUpdate(BaseModel):
    backend_port: int | None = Field(default=None, ge=1024, le=65535)
    python_path: str | None = None
    torch_device: str | None = Field(default=None, pattern="^(gpu|cpu)$")
    mirror: str | None = Field(default=None, pattern="^(tsinghua|sjtu|official)$")
    auto_start_backend: bool | None = None


from backend.paths import workspace_root as _workspace_root  # 唯一实现见 backend/paths.py


@router.get("")
async def get_settings():
    """Return the current workbench settings plus mirror/GPU catalog."""
    settings = read_settings()
    return {
        "success": True,
        "settings": settings,
        "catalog": {
            "mirrors": MIRRORS,
            "torch_devices": ["gpu", "cpu"],
            "runtime": {
                "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                "python_path": settings.get("python_path", ""),
                "data_dir": str(_data_dir()),
                "workspace": str(_workspace_root()),
            },
        },
    }


@router.put("")
async def update_settings(update: SettingsUpdate):
    """Persist changed settings. Fields not provided keep their current value."""
    current = read_settings()
    patch = update.model_dump(exclude_unset=True)
    for key, value in patch.items():
        if value is not None:
            current[key] = value
    saved = _write_settings(current)
    return {"success": True, "settings": saved}


@router.get("/mirrors")
async def list_mirrors():
    """Catalog of supported package mirror sources."""
    return {"success": True, "current": read_settings().get("mirror", "tsinghua"), "mirrors": MIRRORS}


@router.get("/gpu-profiles")
async def gpu_profiles():
    """GPU/CPU profile info + mirror source that determines the install index."""
    settings = read_settings()
    device = settings.get("torch_device", "gpu")
    mirror = MIRRORS.get(settings.get("mirror", "tsinghua"), MIRRORS["tsinghua"])
    profile = {
        "device": device,
        "torch": "2.11.0+cu128" if device == "gpu" else "2.11.0+cpu",
        "pypi_index": mirror["pypi_index"],
        "torch_index": mirror["torch_index"],
        "installed": bool(_adapter_venv_exists()),
        "adapter_python": str(_adapter_python()),
    }
    profiles = [
        {"device": "gpu", "note": "推荐：正式训练（需 NVIDIA GPU）"},
        {"device": "cpu", "note": "验证用：可跑仿真与最小训练冒烟，速度慢约一个量级；配置长期保留"},
    ]
    return {
        "success": True,
        "current": profile,
        "recommended_device": "gpu",
        "profiles": profiles,
    }


def _adapter_venv() -> Path:
    """适配器 venv 落点（支持 LEGGED_STUDIO_MJLAB_VENV 覆盖，见 path_bootstrap）。"""
    from contracts.path_bootstrap import adapter_venv_dir

    return adapter_venv_dir(default=Path(__file__).resolve().parents[1] / "adapters" / "mjlab" / ".venv")


def _adapter_python() -> Path:
    from contracts.path_bootstrap import venv_python

    return venv_python(_adapter_venv())


def _adapter_venv_exists() -> bool:
    return _adapter_python().exists()


@router.post("/gpu-profile/switch")
async def switch_gpu_profile(update: SettingsUpdate):
    """Switch GPU/CPU profile and persist the device preference.

    The actual reinstall is driven by the launcher's provisioning pipeline
    (provision_windows_runtime.ps1); this endpoint records the choice and
    reports the mirror index that will be used.
    """
    device = update.torch_device or "cpu"
    if device not in ("gpu", "cpu"):
        raise HTTPException(status_code=400, detail="torch_device must be 'gpu' or 'cpu'")
    current = read_settings()
    current["torch_device"] = device
    saved = _write_settings(current)
    return {"success": True, "settings": saved, "requires_reinstall": True}


@router.post("/gpu-profile/reinstall")
async def reinstall_gpu_profile():
    """Reinstall the GPU profile (mirror + device) into the adapter venv.

    Returns the exact pip command the launcher/CLI mirrors use so the user can
    drive it; the control plane itself never imports torch.
    """
    settings = read_settings()
    device = settings.get("torch_device", "gpu")
    mirror = MIRRORS.get(settings.get("mirror", "tsinghua"), MIRRORS["tsinghua"])
    torch_req = "torch==2.11.0+cu128" if device == "gpu" else "torch==2.11.0+cpu"
    return {
        "success": True,
        "device": device,
        "torch": torch_req,
        "pypi_index": mirror["pypi_index"],
        "torch_index": mirror["torch_index"],
        "adapter_python": str(_adapter_python()),
        "command": (
            f"uv pip install --break-system-packages --python {_adapter_python()} "
            f"--index-strategy unsafe-best-match --index {mirror['torch_index']} "
            f"--default-index {mirror['pypi_index']} {torch_req} mjlab==1.6.0"
        ),
    }


@router.post("/workspace/cleanup")
async def cleanup_workspace():
    """Remove auto-generated workspace artifacts (imports, caches, temp runs).

    Only writes into clearly disposable subdirectories of the workspace that
    are safe to regenerate: imported packages, per-run scratch, logs and output
    staging. Training history under run/ is left intact to avoid data loss.
    """
    workspace = _workspace_root()
    if not workspace.exists():
        return {"success": True, "removed": [], "freed_bytes": 0}

    removable_targets: list[Path] = []
    # Scratch caches generated by import/export flows.
    for name in ("_import_staging", "_export_staging", ".cache"):
        target = workspace / name
        if target.exists():
            removable_targets.append(target)
    # Imports are re-derivable from the source packages; leave the vendored
    # source tree under packages/ but drop copy artifacts in staging.
    staging = workspace / "packages"
    if staging.exists():
        for target in staging.glob("._tmp_*"):
            removable_targets.append(target)

    removed: list[str] = []
    freed = 0
    for target in removable_targets:
        try:
            if target.is_dir():
                for item in target.rglob("*"):
                    try:
                        freed += item.stat().st_size
                    except OSError:
                        pass
                shutil.rmtree(target)
            else:
                freed += target.stat().st_size
                target.unlink()
            removed.append(str(target.relative_to(workspace)))
        except OSError as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Unable to clean {target}: {exc}") from exc
    return {"success": True, "removed": removed, "freed_bytes": freed, "workspace": str(workspace)}
