"""Canonical robot training presets shared by Web, desktop, and workers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from backend.robot_packages import list_robot_packages


ROOT = Path(__file__).resolve().parent.parent
CONTRACT_DIR = ROOT / "contracts" / "fixtures"
TRAINING_DIR = ROOT / "presets" / "training"


def list_robot_presets() -> list[dict[str, Any]]:
    return list_robot_packages()


def get_robot_preset(robot_id: str) -> dict[str, Any] | None:
    """Return a single package record by ``robot_id``.

    ``list_robot_packages`` is backed by the persistent index (a cheap in-
    memory read), so building this lookup fresh each call is fast and always
    reflects the latest index without fragile versioning bookkeeping.
    """
    for item in list_robot_packages():
        if str(item.get("robot_id")) == robot_id:
            return item
    return None
