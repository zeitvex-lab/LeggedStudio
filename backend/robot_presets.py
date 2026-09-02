"""Canonical robot training presets shared by Web, desktop, and workers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from backend.robot_packages import package_for_contract


ROOT = Path(__file__).resolve().parent.parent
CONTRACT_DIR = ROOT / "contracts" / "fixtures"
TRAINING_DIR = ROOT / "presets" / "training"


def list_robot_presets() -> list[dict[str, Any]]:
    result = []
    for path in sorted(CONTRACT_DIR.glob("unitree_*.v2.json")):
        contract = json.loads(path.read_text(encoding="utf-8"))
        config_path = TRAINING_DIR / f"{contract['robot_id']}_forward_walk.json"
        config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
        result.append({
            "robot_id": contract["robot_id"],
            "family": contract["family"],
            "size_class": contract["size_class"],
            "locomotion_type": contract["locomotion_type"],
            "dof": len(contract["joints"]["actuated_joints"]),
            "mass_kg": contract["urdf"]["total_mass_kg"],
            "contract_id": contract["contract_id"],
            "contract_path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "asset_path": contract["urdf"]["path"],
            "training_config": config,
            "contract": contract,
            "robot_package": package_for_contract(contract),
        })
    return result


def get_robot_preset(robot_id: str) -> dict[str, Any] | None:
    return next((item for item in list_robot_presets() if item["robot_id"] == robot_id), None)
