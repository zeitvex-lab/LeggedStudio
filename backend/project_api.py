"""Portable project package exchange for assets, recipes and scenarios."""

from __future__ import annotations

import base64
import io
import json
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, Field
from backend.robot_packages import package_for_contract
from backend.model_api import _validate, ModelValidationRequest, _contract_draft


router = APIRouter(prefix="/api/project", tags=["project"])
PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = PROJECT_ROOT / "workspace"


class ProjectExportRequest(BaseModel):
    training_config: dict[str, Any] = Field(default_factory=dict)
    scenario: dict[str, Any] = Field(default_factory=dict)
    import_ids: list[str] = Field(default_factory=list, max_length=32)


class ProjectImportRequest(BaseModel):
    archive_base64: str


@router.get("/packages")
async def list_project_packages() -> dict[str, Any]:
    """List locally persisted robot packages available to Web and CLI."""
    packages = []
    root = WORKSPACE / "packages"
    for package_root in sorted(root.iterdir()) if root.exists() else []:
        if not package_root.is_dir():
            continue
        descriptor = package_root / "robot_package.json"
        contract = package_root / "contract.json"
        if not descriptor.exists() or not contract.exists():
            continue
        try:
            packages.append({
                "package_root": str(package_root.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "robot_package": json.loads(descriptor.read_text(encoding="utf-8")),
                "contract": json.loads(contract.read_text(encoding="utf-8")),
            })
        except (OSError, json.JSONDecodeError):
            continue
    return {"success": True, "packages": packages, "count": len(packages)}


def _safe_zip_path(name: str) -> Path:
    path = Path(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"invalid archive path: {name}")
    return path


@router.post("/export")
async def export_project(request: ProjectExportRequest) -> Response:
    manifest = {"schema_version": "legged-studio-project-1.0", "product_version": "0.4.0", "imports": [], "files": ["training/config.json", "scenarios/active.json"]}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        exported_roots: set[str] = set()
        for import_dir in sorted((WORKSPACE / "imports").glob("*")) if (WORKSPACE / "imports").exists() else []:
            if request.import_ids and import_dir.name not in request.import_ids:
                continue
            if not import_dir.is_dir():
                continue
            manifest["imports"].append(import_dir.name)
            for file in import_dir.rglob("*"):
                if file.is_file(): archive.write(file, f"imports/{import_dir.name}/{file.relative_to(import_dir).as_posix()}")
        # A project can reference a built-in or previously imported package
        # outside workspace/imports. Carry that package with the project so a
        # recipe remains reproducible on another machine.
        contract_data = request.training_config.get("contract") if isinstance(request.training_config, dict) else None
        if isinstance(contract_data, dict):
            package = package_for_contract(contract_data)
            package_root = Path(str(package.get("package_root", "")))
            if package_root.exists() and package_root.is_dir():
                package_id = str(package.get("package_id") or package_root.name)
                exported_roots.add(package_id)
                for file in package_root.rglob("*"):
                    if file.is_file():
                        archive.write(file, f"robots/{package_id}/{file.relative_to(package_root).as_posix()}")
                contract_path = package_root / "contract.json"
                if not contract_path.exists():
                    archive.writestr(f"robots/{package_id}/contract.json", json.dumps(contract_data, ensure_ascii=False, indent=2))
        manifest["robot_packages"] = sorted(exported_roots)
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("training/config.json", json.dumps(request.training_config, ensure_ascii=False, indent=2))
        archive.writestr("scenarios/active.json", json.dumps(request.scenario, ensure_ascii=False, indent=2))
    return Response(content=stream.getvalue(), media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="legged-studio-project.lsproj.zip"'})


@router.post("/import")
async def import_project(request: ProjectImportRequest) -> dict[str, Any]:
    try:
        raw = base64.b64decode(request.archive_base64, validate=True)
        imported_root = WORKSPACE / "imports" / f"package_{uuid.uuid4().hex[:10]}"
        imported_root.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = [_safe_zip_path(item.filename) for item in archive.infolist() if not item.is_dir()]
            if len(members) > 5000:
                raise ValueError("project package contains too many files")
            for info, relative in zip([item for item in archive.infolist() if not item.is_dir()], members):
                if relative.parts[0] not in {"imports", "robots", "training", "scenarios", "manifest.json"}:
                    raise ValueError(f"unsupported package entry: {relative}")
                target = imported_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(info))
        manifest_path = imported_root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        _normalise_robot_packages(imported_root, manifest)
        # Relocate imported contract model paths to the new workspace package.
        for contract_path in imported_root.rglob("contract.json"):
            try:
                contract = json.loads(contract_path.read_text(encoding="utf-8"))
                old_path = Path(str(contract.get("urdf", {}).get("path", "")))
                matches = list(contract_path.parent.rglob(old_path.name))
                if matches:
                    contract.setdefault("urdf", {})["path"] = str(matches[0].relative_to(PROJECT_ROOT)).replace("\\", "/")
                    contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            except (OSError, json.JSONDecodeError, ValueError):
                continue
        robots = []
        for contract_path in imported_root.rglob("contract.json"):
            try:
                contract = json.loads(contract_path.read_text(encoding="utf-8"))
                package_path = contract_path.parent / "robot_package.json"
                package = json.loads(package_path.read_text(encoding="utf-8")) if package_path.exists() else {}
                robots.append({"robot_id": contract.get("robot_id"), "family": contract.get("family"), "contract": contract, "asset_path": contract.get("urdf", {}).get("path"), "robot_package": package})
            except (OSError, json.JSONDecodeError):
                continue
        return {"success": True, "import_root": str(imported_root.relative_to(PROJECT_ROOT)).replace("\\", "/"), "manifest": manifest, "robots": robots, "training_config": json.loads((imported_root / "training/config.json").read_text(encoding="utf-8")) if (imported_root / "training/config.json").exists() else {}, "scenario": json.loads((imported_root / "scenarios/active.json").read_text(encoding="utf-8")) if (imported_root / "scenarios/active.json").exists() else {}}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _normalise_robot_packages(imported_root: Path, manifest: dict[str, Any]) -> None:
    """Make legacy/raw robot archives conform to the one package contract.

    A ZIP may already contain ``robots/<id>/contract.json`` or may simply be a
    robot project such as the ZEX-W source project. In the latter case the first valid MJCF or
    URDF named by the manifest (or found recursively) receives generated
    Contract and Package metadata next to the model project.
    """
    existing = list(imported_root.rglob("robot_package.json"))
    if existing:
        return
    candidates = []
    requested = manifest.get("model_path") or manifest.get("model")
    for path in imported_root.rglob("*"):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.suffix.lower() not in {".xml", ".mjcf", ".urdf"}:
            continue
        if any(part in {"mjlab", ".git", ".venv", "node_modules"} for part in path.parts):
            continue
        candidates.append(path)
    if requested:
        requested_path = imported_root / _safe_zip_path(str(requested))
        candidates.sort(key=lambda item: 0 if item == requested_path else 1)
    for model in candidates:
        relative = str(model.relative_to(PROJECT_ROOT)).replace("\\", "/")
        fmt = "urdf" if model.suffix.lower() == ".urdf" else "mjcf"
        report = _validate(ModelValidationRequest(path=relative, filename=model.name, format=fmt))
        if not report.get("valid"):
            continue
        digest = __import__("hashlib").sha256(model.read_bytes()).hexdigest()
        package_id = "imported_" + "".join(c.lower() if c.isalnum() else "_" for c in model.stem).strip("_")[:40]
        contract = _contract_draft(Path(relative), fmt, report.get("inspection", {}), digest)
        contract.update({"robot_id": package_id or "imported_robot", "contract_id": f"{package_id}_contract_v1", "source": "legged_studio_project_import", "tags": ["imported", "project_package"]})
        (imported_root / "contract.json").write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        package = {"schema_version": "robot-package-1.0", "package_id": package_id, "task_kind": "generic", "capabilities": ["generic_mjlab", "mujoco_sim"], "model_path": relative}
        (imported_root / "robot_package.json").write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        break
