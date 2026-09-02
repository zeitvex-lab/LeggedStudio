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
    return next((item for item in list_robot_presets() if item["robot_id"] == robot_id), None)
