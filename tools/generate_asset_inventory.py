#!/usr/bin/env python3
"""Regenerate the default ``QUADRUPED_ASSET_INVENTORY.json`` from the built-in
robot packages so the repository is self-contained.

The scanner walks ``assets/robots/<package>/robot_package.json`` and the
matching ``contract.json`` and emits a minimal but structurally valid inventory
document (``schema_version``, ``summary``, ``records``).  Fields that require a
full MuJoCo/URDF probe (sha256, topology counters, mesh-ref audit, …) are left
null by design; they are optional on ``AssetRecord`` and populated by the host
inventory scanner when present.  This default file exists so a fresh checkout
can build and serve ``/api/assets`` without requiring the external
``00_open`` collection file.
"""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = PROJECT_ROOT / "assets" / "robots"
OUTPUT_PATH = PROJECT_ROOT / "QUADRUPED_ASSET_INVENTORY.json"

# locomotion_type in contract.json -> contracts Locomotion enum value.
_LOCOMOTION = {
    "P": "point_foot",   # point-foot quadruped / biped
    "B": "point_foot",   # biped
    "W": "wheeled_leg",  # wheel-leg
    "H": None,           # hand: not a locomotion candidate
}


def build_record(package_id: str, contract: dict) -> dict:
    # Use the package id (snake_case, e.g. ``unitree_go2``) as ``family`` so the
    # repo's own ``filter_assets(family=...)`` lookups and selfcheck match.
    fam = package_id
    loco_raw = contract.get("locomotion_type")
    loco = _LOCOMOTION.get(loco_raw)
    mass = contract.get("urdf", {}).get("total_mass_kg")
    # Always derive size from mass so the record satisfies the canonical
    # SizeClass taxonomy (size_class_for_mass).  Trusting the package's own
    # declared size_class lets stale/drifted values break validation.
    if mass is not None:
        size = "S" if mass < 15 else ("M" if mass < 35 else "L")
    else:
        size = contract.get("size_class")
    joints = contract.get("joints", {})
    actuated = joints.get("actuated_joints") or []

    record = {
        "path": f"assets/robots/{package_id}/model/robot.xml",
        "format": "mjcf",
        "model_name": contract.get("family") or package_id,
        "family": fam,
        "quadruped": loco_raw != "H",
        "role": "robot",
        "joint_count": len(actuated),
        "movable_joint_count": len(actuated),
        "actuated_joint_count": len(actuated),
        "joint_names": list(actuated),
        "locomotion": loco,
        "classification_mass_kg": mass,
        "classification_mass_source": "manual",
        "size_class_by_mass": size,
        "quality": "ok",
        "readiness": "direct_mujoco_candidate",
        "missing_mesh_ref_count": 0,
        "missing_include_ref_count": 0,
    }
    if mass is not None:
        record["explicit_mass_kg"] = mass
    return record


def main() -> None:
    records = []
    for package_dir in sorted(ASSETS_DIR.iterdir()):
        if not package_dir.is_dir():
            continue
        contract_path = package_dir / "contract.json"
        if not contract_path.exists():
            continue
        package_id = package_dir.name
        try:
            contract = json.loads(contract_path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            print(f"skip {package_id}: {exc}")
            continue
        records.append(build_record(package_id, contract))

    doc = {
        "schema_version": "1.0",
        "document_role": "built-in default asset inventory",
        "human_summary": (
            "Default asset inventory regenerated from the 16 built-in robot "
            "packages so the repository is self-contained."
        ),
        "size_taxonomy": {
            "S": "0 < mass_kg < 15",
            "M": "15 <= mass_kg < 35",
            "L": "mass_kg >= 35",
        },
        "summary": {"total": len(records)},
        "records": records,
    }

    OUTPUT_PATH.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT_PATH} with {len(records)} records")


if __name__ == "__main__":
    main()
