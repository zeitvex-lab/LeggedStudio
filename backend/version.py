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
        value = ""
    # 读不到 VERSION 时如实标"未知"——不返回一个看着像真的旧版本号（0.44.0 曾在此宅了三个月）
    return value or "0.0.0+unknown"


APP_VERSION = get_version()
