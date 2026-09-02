"""Robot package discovery for the Web, CLI and isolated MJLab worker.

Robot identity is data owned by a package.  The control plane never infers a
special task from ``robot_id``; it only reads the package capability manifest.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "workspace"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def package_for_contract(contract: dict[str, Any]) -> dict[str, Any]:
    """Return the package descriptor owning a contract.

    Imported packages use ``robot_package.json`` next to ``contract.json``.
    Legacy built-in assets get a deterministic generic descriptor until their
    package manifest is added.
    """
    model = Path(str(contract.get("urdf", {}).get("path", "")))
    if not model.is_absolute():
        model = ROOT / model
    model = model.resolve()
    candidates = [model.parent / "robot_package.json", model.parent / "package.json"]
    candidates.extend(model.parents[i] / "robot_package.json" for i in range(min(3, len(model.parents))))
    descriptor: dict[str, Any] = {}
    package_path: Path | None = None
    for candidate in candidates:
        if candidate.exists():
            descriptor = _read_json(candidate)
            package_path = candidate.parent
            break
    if package_path is None:
        package_path = model.parent
    package_id = str(descriptor.get("package_id") or contract.get("robot_id") or package_path.name)
    result = {
        "schema_version": "robot-package-1.0",
        "package_id": package_id,
        "package_root": str(package_path),
        "contract_path": str(package_path / "contract.json"),
        "asset_path": str(model),
        "task_kind": "generic",
        "native_task_id": None,
        "extension_root": None,
        "capabilities": descriptor.get("capabilities", ["generic_mjlab"]),
        "descriptor_source": str(package_path / "robot_package.json") if descriptor else "inferred",
    }
    # Task execution is intentionally uniform: package source may contain
    # historical task modules, but the platform always trains through the
    # generic MJLab builder. Descriptor fields remain available as metadata.
    return {**descriptor, **result}


def write_package_manifest(package_root: Path, *, package_id: str, task_kind: str = "generic", native_task_id: str | None = None, extension_root: str | None = None) -> Path:
    package_root.mkdir(parents=True, exist_ok=True)
    path = package_root / "robot_package.json"
    payload = {
        "schema_version": "robot-package-1.0",
        "package_id": package_id,
        "task_kind": task_kind,
        "native_task_id": native_task_id,
        "extension_root": extension_root,
        "capabilities": ["generic_mjlab"] + (["package_extension"] if native_task_id else []),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def list_robot_packages() -> list[dict[str, Any]]:
    """Discover every persisted robot package using one filesystem contract."""
    # Persisted packages are authoritative. The source asset tree is only a
    # migration fallback for installations created before package discovery.
    roots = [WORKSPACE / "packages", ROOT / "assets" / "robots"]
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for package_root in sorted(root.iterdir()):
            if not package_root.is_dir() or package_root.name in seen:
                continue
            contract_path = package_root / "contract.json"
            descriptor_path = package_root / "robot_package.json"
            if not contract_path.exists() or not descriptor_path.exists():
                continue
            contract = _read_json(contract_path)
            descriptor = _read_json(descriptor_path)
            if not contract:
                continue
            seen.add(package_root.name)
            training_path = package_root / "training" / "config.json"
            descriptor_model = descriptor.get("model", {}) if isinstance(descriptor.get("model"), dict) else {}
            asset_value = contract.get("urdf", {}).get("path") or descriptor_model.get("path")
            if isinstance(asset_value, str) and asset_value.startswith("workspace/packages/") and not (ROOT / asset_value).exists():
                candidate = package_root / Path(asset_value).name
                if (package_root / "model" / "robot.xml").exists():
                    asset_value = str((package_root / "model" / "robot.xml").relative_to(ROOT)).replace("\\", "/")
            result.append({
                "robot_id": contract.get("robot_id", package_root.name),
                "family": contract.get("family", package_root.name),
                "size_class": contract.get("size_class", "M"),
                "locomotion_type": contract.get("locomotion_type", "P"),
                "dof": len(contract.get("joints", {}).get("actuated_joints", [])),
                "mass_kg": contract.get("urdf", {}).get("total_mass_kg", 0.0),
                "contract_id": contract.get("contract_id"),
                "contract_path": str(contract_path.relative_to(ROOT)).replace("\\", "/"),
                "asset_path": asset_value,
                "training_config": _read_json(training_path) if training_path.exists() else {},
                "contract": contract,
                "robot_package": {**descriptor, "package_root": str(package_root), "contract_path": descriptor.get("contract_path", "contract.json"), "model": descriptor_model or {"format": "mjcf", "path": "model/robot.xml", "assets_path": "model/assets"}, "training_config_path": descriptor.get("training_config_path", "training/config.json"), "simulation_config_path": descriptor.get("simulation_config_path", "simulation/config.json")},
            })
    return result
