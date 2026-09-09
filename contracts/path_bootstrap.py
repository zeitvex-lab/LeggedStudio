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
    "bootstrap_root",
    "ensure_on_path",
    "ensure_project_root_on_path",
    "ensure_many_on_path",
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
