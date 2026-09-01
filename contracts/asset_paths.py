"""Resolve project-relative robot assets consistently across desktop and CLI runs."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def resolve_asset_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    candidates = [Path.cwd() / path, PROJECT_ROOT / path]
    return next((candidate.resolve() for candidate in candidates if candidate.exists()), candidates[-1].resolve())
