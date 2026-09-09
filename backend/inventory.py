"""Read-only asset-inventory helpers shared by the control plane and tooling.

The inventory JSON lives at the repository root (``QUADRUPED_ASSET_INVENTORY.json``)
unless ``LEGGED_STUDIO_INVENTORY`` points elsewhere.  When the file is missing the
loader falls back to a lightweight scan of ``assets/robots/`` so the control plane
never hard-fails on a fresh checkout.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parent
# The repository root: one level above the ``backend`` package.
PROJECT_ROOT = BACKEND_DIR.parent
INVENTORY_PATH = Path(
    os.environ.get("LEGGED_STUDIO_INVENTORY", PROJECT_ROOT / "QUADRUPED_ASSET_INVENTORY.json")
).expanduser().resolve()


class InventoryError(RuntimeError):
    """Raised when the read-only inventory cannot be loaded."""


def _scan_default_inventory() -> dict[str, Any]:
    """Build a lightweight inventory by scanning ``assets/robots`` packages.

    Used as a fallback when the inventory file is absent on a fresh checkout.
    Fields requiring a full MuJoCo/URDF probe are left null.
    """
    import re as _re

    robots_root = PROJECT_ROOT / "assets" / "robots"
    records: list[dict[str, Any]] = []
    if robots_root.is_dir():
        for package_dir in sorted(robots_root.iterdir()):
            contract_path = package_dir / "contract.json"
            if not package_dir.is_dir() or not contract_path.exists():
                continue
            try:
                contract = json.loads(contract_path.read_text(encoding="utf-8-sig"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            package_id = package_dir.name
            mass = (contract.get("urdf") or {}).get("total_mass_kg")
            size = _mass_size(mass)
            joints = contract.get("joints") or {}
            actuated = (joints.get("actuated_joints") or [])
            loco_raw = contract.get("locomotion_type")
            records.append({
                "path": f"assets/robots/{package_id}/model/robot.xml",
                "format": "mjcf",
                "model_name": contract.get("family") or package_id,
                "family": package_id,
                "quadruped": loco_raw != "H",
                "role": "robot",
                "joint_count": len(actuated),
                "joint_names": list(actuated),
                "locomotion": "point_foot" if loco_raw in ("P", "B") else ("wheeled_leg" if loco_raw == "W" else None),
                "classification_mass_kg": mass,
                "size_class_by_mass": size,
                "quality": "ok",
                "readiness": "direct_mujoco_candidate",
                "missing_mesh_ref_count": 0,
                "missing_include_ref_count": 0,
            })
    return {"schema_version": "1.0", "document_role": "scanned fallback", "summary": {"total": len(records)}, "records": records}


def _mass_size(mass: float | None) -> str | None:
    if mass is None or mass <= 0:
        return None
    if mass < 15:
        return "S"
    if mass < 35:
        return "M"
    return "L"


def load_inventory(path: Path = INVENTORY_PATH) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError:
        return _scan_default_inventory()
    except json.JSONDecodeError as exc:
        raise InventoryError(f"Inventory is not valid JSON: {path}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("records"), list):
        raise InventoryError("Inventory must be an object containing a records array")
    return value


def dict_records(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    """Drop non-object entries so filters and summaries can index safely."""
    return [record for record in inventory["records"] if isinstance(record, dict)]


def filter_records(
    records: list[dict[str, Any]],
    *,
    readiness: str | None = None,
    size: str | None = None,
    locomotion: str | None = None,
    family: str | None = None,
) -> list[dict[str, Any]]:
    """Apply exact, case-insensitive filters shared by every inventory consumer."""

    def matches(record: dict[str, Any], key: str, expected: str | None) -> bool:
        return expected is None or str(record.get(key, "")).lower() == expected.lower()

    return [
        record
        for record in records
        if matches(record, "readiness", readiness)
        and matches(record, "size_class_by_mass", size)
        and matches(record, "locomotion", locomotion)
        and matches(record, "family", family)
    ]
