"""Read-only asset-inventory helpers shared by the control plane and tooling.

The inventory JSON lives in the ``00_open`` collection root (one level above
this repository) unless ``LEGGED_STUDIO_INVENTORY`` points elsewhere.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent.parent
INVENTORY_PATH = Path(
    os.environ.get("LEGGED_STUDIO_INVENTORY", PROJECT_ROOT / "QUADRUPED_ASSET_INVENTORY.json")
).expanduser().resolve()


class InventoryError(RuntimeError):
    """Raised when the read-only inventory cannot be loaded."""


def load_inventory(path: Path = INVENTORY_PATH) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError as exc:
        raise InventoryError(f"Inventory not found: {path}") from exc
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
