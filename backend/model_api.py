"""Model inspection API shared by the Web workbench and future CLI.

This endpoint deliberately performs structural inspection before any training:
XML parsing, joint/actuator counts, mesh references, file hash, and optional
MuJoCo compilation. It does not import or duplicate the URDF Studio viewer.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from contracts.asset_paths import resolve_asset_path


router = APIRouter(prefix="/api/models", tags=["models"])


class ModelValidationRequest(BaseModel):
    path: str | None = None
    content: str | None = None
    filename: str = "model.xml"
    format: Literal["urdf", "mjcf", "auto"] = "auto"
    contract: dict[str, Any] | None = None


def _resolve_resource(raw_value: str, source_path: Path) -> Path:
    """Resolve URDF/package resources using the same relative semantics as viewers."""
    value = raw_value.strip()
    if value.startswith("package://"):
        value = value[len("package://"):]
        candidates = [source_path.parent / value]
        parts = value.split("/", 1)
        if len(parts) == 2:
            candidates.append(source_path.parent / parts[1])
    else:
        candidates = [Path(value) if Path(value).is_absolute() else source_path.parent / value]
    roots = [Path(__file__).resolve().parent.parent, Path(os.environ.get("LEGGED_STUDIO_WORKSPACE", "workspace")).resolve()]
    candidates.extend(root / value for root in roots)
    return next((candidate.resolve() for candidate in candidates if candidate.exists()), candidates[0].resolve())


def _urdf_inspection(root: ET.Element, source_path: Path, errors: list[str], warnings: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    links = root.findall(".//link")
    joints = root.findall("./joint")
    actuated = [item for item in joints if item.get("type") not in {"fixed", "floating", "planar"}]
    mesh_files = sorted({item.get("filename") for item in root.findall(".//geometry/mesh") if item.get("filename")})
    missing_meshes = [mesh for mesh in mesh_files if not _resolve_resource(mesh, source_path).exists()]
    errors.extend([f"mesh file not found: {item}" for item in missing_meshes[:20]])

    link_names = [item.get("name") for item in links if item.get("name")]
    joint_names = [item.get("name") for item in joints if item.get("name")]
    duplicate_links = sorted({name for name in link_names if link_names.count(name) > 1})
    duplicate_joints = sorted({name for name in joint_names if joint_names.count(name) > 1})
    if duplicate_links:
        errors.append(f"duplicate link names: {', '.join(duplicate_links[:12])}")
    if duplicate_joints:
        errors.append(f"duplicate joint names: {', '.join(duplicate_joints[:12])}")

    child_links = {item.findtext("child") for item in joints if item.findtext("child")}
    parent_links = {item.findtext("parent") for item in joints if item.findtext("parent")}
    roots = sorted(set(link_names) - child_links)
    disconnected = sorted(set(link_names) - (parent_links | child_links | set(roots)))
    if len(roots) != 1 and links:
        warnings.append(f"URDF has {len(roots)} root links; expected one")
    if disconnected:
        warnings.append(f"disconnected links: {', '.join(disconnected[:12])}")

    inertial_missing: list[str] = []
    invalid_mass: list[str] = []
    total_mass = 0.0
    for link in links:
        inertial = link.find("inertial")
        if inertial is None:
            inertial_missing.append(link.get("name", "<unnamed>"))
            continue
        mass_node = inertial.find("mass")
        try:
            mass = float(mass_node.get("value", "nan")) if mass_node is not None else float("nan")
            if not mass > 0:
                raise ValueError
            total_mass += mass
        except (TypeError, ValueError):
            invalid_mass.append(link.get("name", "<unnamed>"))
    if inertial_missing:
        warnings.append(f"links without inertial: {len(inertial_missing)}")
    if invalid_mass:
        errors.append(f"invalid or non-positive mass on: {', '.join(invalid_mass[:12])}")

    limit_issues: list[str] = []
    for joint in actuated:
        kind = joint.get("type", "")
        limit = joint.find("limit")
        if kind in {"revolute", "prismatic"} and limit is None:
            limit_issues.append(f"{joint.get('name', '<unnamed>')}: missing limit")
        if limit is not None and limit.get("lower") is not None and limit.get("upper") is not None:
            try:
                if float(limit.get("lower")) > float(limit.get("upper")):
                    limit_issues.append(f"{joint.get('name', '<unnamed>')}: lower > upper")
            except ValueError:
                limit_issues.append(f"{joint.get('name', '<unnamed>')}: invalid limits")
    errors.extend(limit_issues[:20])

    stats = {"links": len(links), "joints": len(joints), "actuated_joints": len(actuated), "actuators": None, "total_mass_kg": total_mass}
    inspection = {
        "root_name": root.get("name"),
        "links": link_names,
        "joints": [{"name": item.get("name"), "type": item.get("type"), "parent": item.findtext("parent"), "child": item.findtext("child")} for item in joints],
        "mesh_files": mesh_files,
        "missing_meshes": missing_meshes,
        "topology": {"root_links": roots, "disconnected_links": disconnected, "duplicate_links": duplicate_links, "duplicate_joints": duplicate_joints},
        "inertial": {"missing_links": inertial_missing, "invalid_mass_links": invalid_mass, "total_mass_kg": total_mass},
        "limits": {"issues": limit_issues},
    }
    return stats, inspection


def _mjcf_inspection(root: ET.Element, errors: list[str], warnings: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    bodies = root.findall(".//body")
    joints = root.findall(".//joint")
    actuators = root.findall(".//actuator/*")
    joint_names = [item.get("name") for item in joints if item.get("name")]
    actuator_names = [item.get("name") for item in actuators if item.get("name")]
    actuator_targets = [item.get("joint") or item.get("tendon") for item in actuators]
    missing_targets = [name for name in actuator_targets if name and name not in joint_names and name not in {item.get("name") for item in root.findall(".//tendon/*")}]
    if missing_targets:
        errors.extend([f"actuator target not found: {item}" for item in missing_targets[:20]])
    if joints and not actuators:
        warnings.append("MJCF contains joints but no actuators")
    stats = {"links": len(bodies), "joints": len(joints), "actuated_joints": len(joints), "actuators": len(actuators), "total_mass_kg": None}
    inspection = {
        "root_name": root.get("model"),
        "links": [item.get("name") for item in bodies if item.get("name")],
        "joints": [{"name": item.get("name"), "type": item.get("type"), "parent": None, "child": None} for item in joints],
        "mesh_files": sorted({item.get("file") for item in root.findall(".//mesh") if item.get("file")}),
        "missing_meshes": [],
        "topology": {"root_links": [], "disconnected_links": [], "duplicate_links": [], "duplicate_joints": []},
        "inertial": {"missing_links": [], "invalid_mass_links": [], "total_mass_kg": None},
        "limits": {"issues": []},
        "actuators": {"names": actuator_names, "targets": actuator_targets, "missing_targets": missing_targets},
    }
    return stats, inspection


def _safe_path(value: str) -> Path:
    candidate = resolve_asset_path(value)
    allowed_roots = [
        Path(__file__).resolve().parent.parent,
        Path(os.environ.get("LEGGED_STUDIO_WORKSPACE", "workspace")).resolve(),
        Path(os.environ.get("LEGGED_STUDIO_DATA_DIR", "workspace")).resolve(),
    ]
    if not any(candidate == root or root in candidate.parents for root in allowed_roots):
        raise ValueError("model path must be inside the Legged Studio project or workspace")
    return candidate


def _read_source(request: ModelValidationRequest) -> tuple[Path, bool]:
    if request.content is not None:
        suffix = ".urdf" if request.format == "urdf" else ".xml"
        fd, name = tempfile.mkstemp(prefix="legged-studio-model-", suffix=suffix)
        os.close(fd)
        path = Path(name)
        path.write_text(request.content, encoding="utf-8")
        return path, True
    if not request.path:
        raise ValueError("provide either path or content")
    path = _safe_path(request.path)
    if not path.exists() or not path.is_file():
        raise ValueError(f"model file not found: {request.path}")
    return path, False


def _validate(request: ModelValidationRequest) -> dict[str, Any]:
    path, temporary = _read_source(request)
    errors: list[str] = []
    warnings: list[str] = []
    try:
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            return {"valid": False, "format": request.format, "errors": [f"XML parse failed: {exc}"], "warnings": [], "sha256": digest}

        inferred = "urdf" if root.tag.lower() == "robot" else "mjcf" if root.tag.lower() == "mujoco" else "unknown"
        model_format = inferred if request.format == "auto" else request.format
        if model_format == "urdf" and root.tag.lower() != "robot":
            errors.append("URDF root element must be <robot>")
        if model_format == "mjcf" and root.tag.lower() != "mujoco":
            errors.append("MJCF root element must be <mujoco>")

        if model_format == "urdf":
            stats, inspection = _urdf_inspection(root, path, errors, warnings)
            if not stats["links"]:
                errors.append("URDF contains no links")
            if not stats["joints"]:
                warnings.append("model contains no joints")
            mujoco_loadable = None
            mujoco_error = "URDF inspection does not compile through MJCF loader; convert/import it in the asset workbench"
        elif model_format == "mjcf":
            stats, inspection = _mjcf_inspection(root, errors, warnings)
            if not stats["links"]:
                errors.append("MJCF contains no bodies")
            mujoco_loadable = False
            mujoco_error = ""
            try:
                import mujoco

                mujoco.MjModel.from_xml_path(str(path))
                mujoco_loadable = True
            except Exception as exc:
                mujoco_error = str(exc)
                errors.append(f"MuJoCo compilation failed: {exc}")
        else:
            stats = {"links": 0, "joints": 0, "actuated_joints": 0, "actuators": 0, "total_mass_kg": None}
            inspection = {"root_name": None, "links": [], "joints": [], "mesh_files": [], "missing_meshes": [], "topology": {}, "inertial": {}, "limits": {}}
            errors.append("could not infer URDF or MJCF format")
            mujoco_loadable = False
            mujoco_error = "unknown XML root"

        contract_result = None
        if request.contract:
            from contracts.robot_contract_v2 import RobotContractV2
            from contracts.validator import validate_contract

            try:
                contract = RobotContractV2(**request.contract)
                validation = validate_contract(contract)
                contract_result = {
                    "valid": validation.valid,
                    "errors": [item.message for item in validation.errors],
                    "warnings": [item.message for item in validation.warnings],
                }
                if model_format == "urdf":
                    model_joint_names = {item.get("name") for item in root.findall("./joint")} if model_format == "urdf" else {item.get("name") for item in root.findall(".//joint")}
                    missing = [name for name in contract.joints.actuated_joints if name not in model_joint_names]
                    if missing:
                        errors.append(f"Contract joints missing from model: {', '.join(missing[:12])}")
            except Exception as exc:
                contract_result = {"valid": False, "errors": [str(exc)], "warnings": []}
                errors.append(f"Contract validation failed: {exc}")

        return {
            "valid": not errors,
            "format": model_format,
            "filename": request.filename or path.name,
            "source_path": str(path),
            "sha256": digest,
            "stats": stats,
            "inspection": inspection,
            "joint_names": [item.get("name") for item in root.findall(".//joint") if item.get("name")],
            "actuator_names": [item.get("name") for item in root.findall(".//actuator/*") if item.get("name")],
            "mujoco_loadable": mujoco_loadable,
            "mujoco_error": mujoco_error,
            "contract": contract_result,
            "errors": errors,
            "warnings": warnings,
        }
    finally:
        if temporary:
            path.unlink(missing_ok=True)


@router.post("/validate")
async def validate_model(request: ModelValidationRequest) -> dict[str, Any]:
    try:
        return _validate(request)
    except Exception as exc:
        return {"valid": False, "errors": [str(exc)], "warnings": []}


@router.get("/formats")
async def model_formats() -> dict[str, Any]:
    return {"formats": [{"id": "urdf", "label": "URDF"}, {"id": "mjcf", "label": "MJCF"}]}
