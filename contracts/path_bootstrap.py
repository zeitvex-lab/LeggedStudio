"""Unified sys.path bootstrap for the Legged Studio control plane.

Centralises the scattered, copy-pasted ``sys.path.insert(0, str(ROOT))`` calls
that were formerly duplicated across ``backend/``, ``contracts/``, ``tools/``
and ``scripts/``.

Why:
  Every module that runs as a bare script (``python tools/x.py``,
  ``python scripts/y.py``, a migration CLI, or a worker subprocess started
  outside the installed package) needs the repository root on ``sys.path`` so it
  can ``import backend.*`` / ``import contracts.*``. That logic used to be
  copy-pasted with fragile ``Path(__file__).resolve().parents[N]`` arithmetic and
  non-identical idempotency behaviour.

Scope / limitations (stated honestly):
  Python puts a bare script's own directory (not the CWD) at ``sys.path[0]``, so
  a bare script **must** add the repo root before it can import any top-level
  package. That single self-bootstrap step cannot itself be removed by a library
  import — but it is now centralised and idempotent here, and it is the *only*
  place that touches ``sys.path`` for project-root resolution.

Contract:
  * ``ensure_on_path`` is idempotent (never duplicates an entry).
  * It *prefixes* the entry (``sys.path.insert(0, ...)``) to preserve the
    historical resolution priority.
  * It does not mutate the process environment or CWD.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

__all__ = [
    "PROJECT_ROOT",
    "ADAPTER_VENV_ENV",
    "ADAPTER_PYTHON_ENVS",
    "bootstrap_root",
    "ensure_on_path",
    "ensure_project_root_on_path",
    "ensure_many_on_path",
    "adapter_venv_dir",
    "adapter_python",
    "venv_python",
]


# Repository root, resolved once. ``contracts/path_bootstrap.py``'s parent is
# ``contracts/``; its grandparent is the repo root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def ensure_on_path(path: str | Path, *, front: bool = True) -> str:
    """Ensure *path* is on ``sys.path``.

    Idempotent and prefix-inserting (``front=True``) to match the historical
    ``sys.path.insert(0, ...)`` resolution priority.  Returns the string form of
    the resolved path that is now on ``sys.path``.
    """
    normalized = str(Path(path).resolve())
    if normalized in sys.path:
        return normalized
    if front:
        sys.path.insert(0, normalized)
    else:
        sys.path.append(normalized)
    return normalized


def ensure_project_root_on_path() -> str:
    """Ensure the repository root is importable (``import backend.*`` etc.)."""
    return ensure_on_path(PROJECT_ROOT)


def bootstrap_root() -> Path:
    """Ensure the repo root is on ``sys.path`` and return it as a ``Path``.

    Thin convenience shim for call sites that only need the root ``Path``.
    """
    ensure_project_root_on_path()
    return PROJECT_ROOT


def ensure_many_on_path(paths: Iterable[str | Path], *, front: bool = True) -> list[str]:
    """Ensure several paths are on ``sys.path`` in the given order.

    Later entries in *paths* are inserted ahead of earlier ones (matching
    ``insert(0)`` semantics applied sequentially), so the last item wins if two
    entries name the same module.  Returns the list of ensured path strings.
    """
    ensured: list[str] = []
    for p in paths:
        ensured.append(ensure_on_path(p, front=front))
    return ensured


# ---------------------------------------------------------------------------
# 训练栈解释器解析（控制面永不 import torch/mjlab，只负责找到跑它们的解释器）
# ---------------------------------------------------------------------------

#: 环境变量：直接指定训练适配器 venv 目录（云原生开发镜像用它在仓库外固化 venv，
#: 从而不受 bind mount 覆盖影响）。见 scripts/provision_cpu_training.sh。
ADAPTER_VENV_ENV = "LEGGED_STUDIO_MJLAB_VENV"

#: 环境变量：直接指定训练链路的 Python 解释器（可执行文件，优先级最高）。
#: 与桌面启动器/PowerShell 供应脚本既有约定一致（见 electron/launcher/main.js）。
ADAPTER_PYTHON_ENVS = (
    "LEGGED_STUDIO_MJLAB_PYTHON",
    "LEGGED_STUDIO_TRAIN_PYTHON",
    "LEGGED_STUDIO_RUNTIME_PYTHON",
)

#: 仓库内的默认适配器 venv（本地开发 / 桌面版的常规落点）。
DEFAULT_ADAPTER_VENV = PROJECT_ROOT / "adapters" / "mjlab" / ".venv"


def venv_python(venv: str | Path, *, platform: str | None = None) -> Path:
    """Return the interpreter path inside *venv* for the current (or given) OS.

    Windows virtualenvs put the interpreter under ``Scripts/python.exe``,
    POSIX ones under ``bin/python``. Centralised so the layout assumption is
    written down once instead of in ten call sites.
    """
    import sys as _sys

    os_name = platform if platform is not None else _sys.platform
    if os_name == "win32":
        return Path(venv) / "Scripts" / "python.exe"
    return Path(venv) / "bin" / "python"


def adapter_venv_dir(*, default: str | Path | None = None) -> Path:
    """Resolve the training adapter venv directory.

    Priority:
      1. ``$LEGGED_STUDIO_MJLAB_VENV`` — explicit venv directory (container image
         installs the CPU training venv outside the bind-mounted repo).
      2. A directory implied by an explicit interpreter from
         ``ADAPTER_PYTHON_ENVS`` (its parent-of-parent, i.e. the venv root).
      3. *default* (or :data:`DEFAULT_ADAPTER_VENV`).

    Returns a ``Path`` even when it does not exist; callers decide how to react
    so the "not installed" message stays actionable.
    """
    import os as _os

    configured = (_os.environ.get(ADAPTER_VENV_ENV) or "").strip()
    if configured:
        return Path(configured).expanduser()

    for name in ADAPTER_PYTHON_ENVS:
        explicit = (_os.environ.get(name) or "").strip()
        if not explicit:
            continue
        interpreter = Path(explicit).expanduser()
        # <venv>/bin/python or <venv>/Scripts/python.exe -> <venv>
        if interpreter.parent.name in {"bin", "Scripts"}:
            return interpreter.parent.parent
        return interpreter.parent

    return Path(default) if default is not None else DEFAULT_ADAPTER_VENV


def adapter_python(*, default: str | Path | None = None) -> Path:
    """Resolve the interpreter that hosts the training stack (torch/mjlab).

    Prefers ``ADAPTER_PYTHON_ENVS`` (explicit executable) and otherwise derives
    the interpreter from :func:`adapter_venv_dir`.
    """
    import os as _os

    for name in ADAPTER_PYTHON_ENVS:
        explicit = (_os.environ.get(name) or "").strip()
        if explicit:
            return Path(explicit).expanduser()
    return venv_python(adapter_venv_dir(default=default))
