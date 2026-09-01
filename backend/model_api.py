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
            links = root.findall(".//link")
            joints = root.findall("./joint")
            actuated = [item for item in joints if item.get("type") not in {"fixed", "floating", "planar"}]
            mesh_files = [item.get("filename") for item in root.findall(".//geometry/mesh") if item.get("filename")]
            missing_meshes = []
            for mesh in mesh_files:
                mesh_path = Path(mesh.replace("package://", ""))
                if not mesh_path.is_absolute():
                    mesh_path = path.parent / mesh_path
                if not mesh_path.exists():
                    missing_meshes.append(mesh)
            if missing_meshes:
                errors.extend([f"mesh file not found: {item}" for item in missing_meshes[:20]])
            mass = 0.0
            for element in root.findall(".//inertial/mass"):
                try:
                    mass += float(element.get("value", "0"))
                except ValueError:
                    errors.append(f"invalid mass value on link: {element.get('value')}")
            stats = {"links": len(links), "joints": len(joints), "actuated_joints": len(actuated), "actuators": None, "total_mass_kg": mass}
            if not links:
                errors.append("URDF contains no links")
            if not joints:
                warnings.append("model contains no joints")
            mujoco_loadable = None
            mujoco_error = "URDF inspection does not compile through MJCF loader; convert/import it in the asset workbench"
        elif model_format == "mjcf":
            bodies = root.findall(".//body")
            joints = root.findall(".//joint")
            actuators = root.findall(".//actuator/*")
            stats = {"links": len(bodies), "joints": len(joints), "actuated_joints": len(joints), "actuators": len(actuators), "total_mass_kg": None}
            if not bodies:
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
                    model_joint_names = {item.get("name") for item in root.findall("./joint")}
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
