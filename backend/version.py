"""Single source of truth for the Legged Studio release version."""

from __future__ import annotations

import os
from pathlib import Path


def get_version() -> str:
    configured = os.environ.get("LEGGED_STUDIO_VERSION", "").strip()
    if configured:
        return configured
    version_file = Path(__file__).resolve().parents[1] / "VERSION"
    try:
        value = version_file.read_text(encoding="utf-8").strip()
    except OSError:
        value = "0.30.0"
    return value or "0.30.0"


APP_VERSION = get_version()
