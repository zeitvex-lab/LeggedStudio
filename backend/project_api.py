"""Portable project package exchange for assets, recipes and scenarios."""

from __future__ import annotations

import base64
import io
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, Field
from backend.version import get_version
from backend.robot_packages import package_for_contract
from contracts.validator import normalized_sha256, package_digest  # 内容摘要唯一实现
from backend.model_api import _validate, ModelValidationRequest
from backend.package_import import draft_model_contract


router = APIRouter(prefix="/api/project", tags=["project"])
#: 工作区根的唯一实现见 ``backend/paths.py``（此前本模块自带一份，且与他处规则不一致）。
from backend.paths import api_path, workspace_root as _workspace_root  # noqa: E402  (import 位置跟随既有排版)


def _api_path(path: Path) -> str:
    """仓库相对 posix 路径（唯一实现见 ``backend.paths.api_path``）。"""

    return api_path(path)


def _safe_package_id(value: str) -> str:
    normalized = "".join(char.lower() if char.isalnum() or char in "_-" else "_" for char in value).strip("_-")
    if not normalized:
        raise ValueError("package id is empty")
    return normalized[:80]


def _tree_hash(root: Path) -> str:
    """目录内容摘要：委托 ``contracts.validator.package_digest``（**唯一实现**）。

    此前这里是第二套口径：与 ``model_api`` 的 ``content_sha256`` 相比**少了 CRLF → LF 归一**，
    而两者算出来的值都会写进/读自 ``robot_package.json`` 的同一个 ``content_sha256`` 字段。
    实测（2026-09-19）：本仓 4 个机器人包两种口径**全都不同** ⇒ 只要"带清单字段的源包"与
    "没字段的目标包"被放进同一次比较（或反过来），同一份内容就会被判成两份、生成多余副本。
    """

    return package_digest(
        (item.relative_to(root), item.read_bytes())
        for item in sorted(root.rglob("*"))
        if item.is_file()
    )


class ProjectExportRequest(BaseModel):
    training_config: dict[str, Any] = Field(default_factory=dict)
    scenario: dict[str, Any] = Field(default_factory=dict)
    import_ids: list[str] = Field(default_factory=list, max_length=32)


class ProjectImportRequest(BaseModel):
    archive_base64: str


@router.get("/packages")
async def list_project_packages() -> dict[str, Any]:
    """List locally persisted imported packages available to Web and CLI."""
    packages = []
    root = _workspace_root() / "packages"
    for package_root in sorted(root.iterdir()) if root.exists() else []:
        if not package_root.is_dir():
            continue
        descriptor = package_root / "robot_package.json"
        # 包识别判据：manifest + **至少一份契约**。新导入的包一定有 v2 视图
        # （导入链必写），真值契约要有一次迁移/生成才在——所以先看 v2 视图，再回落真值。
        contract = package_root / "contract_legacy_v2.json"
        if not contract.exists():
            contract = package_root / "contract.json"
        if not descriptor.exists() or not contract.exists():
            continue
        try:
            package = json.loads(descriptor.read_text(encoding="utf-8-sig"))
            contract_data = json.loads(contract.read_text(encoding="utf-8-sig"))
            files = [item for item in package_root.rglob("*") if item.is_file()]
            packages.append({
                "package_id": package.get("package_id") or contract_data.get("robot_id") or package_root.name,
                "package_root": _api_path(package_root),
                "source": "workspace",
                "file_count": len(files),
                "size_bytes": sum(item.stat().st_size for item in files),
                "robot_package": package,
                "contract": contract_data,
            })
        except (OSError, json.JSONDecodeError):
            continue
    return {"success": True, "packages": packages, "count": len(packages)}


@router.delete("/packages/{package_id}")
async def delete_project_package(package_id: str) -> dict[str, Any]:
    """Delete an imported package by its persisted directory id."""
    try:
        safe_id = _safe_package_id(package_id)
    except ValueError:
        safe_id = ""
    if not package_id or safe_id != package_id:
        return {"success": False, "error": "invalid package id"}
    packages_root = (_workspace_root() / "packages").resolve()
    target = (packages_root / package_id).resolve()
    if target.parent != packages_root:
        return {"success": False, "error": "invalid package id"}
    if not target.exists() or not target.is_dir():
        target = None
    if target is None:
        return {"success": False, "error": "package not found"}
    shutil.rmtree(target)
    from backend.robot_packages import remove_package
    remove_package(package_id)
    return {"success": True, "package_id": package_id}


def _safe_zip_path(name: str) -> Path:
    path = Path(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"invalid archive path: {name}")
    return path


@router.post("/export")
async def export_project(request: ProjectExportRequest) -> Response:
    manifest = {"schema_version": "legged-studio-project-1.0", "product_version": get_version(), "imports": [], "files": ["training/config.json", "scenarios/active.json"]}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        exported_roots: set[str] = set()
        package_dirs = sorted((_workspace_root() / "packages").glob("*"), key=lambda item: item.stat().st_mtime, reverse=True) if (_workspace_root() / "packages").exists() else []
        # ``import_ids`` is retained as a wire-compatible field, but now
        # selects formal package ids rather than legacy imports.
        if not request.import_ids:
            package_dirs = []
        for package_dir in package_dirs:
            if request.import_ids and package_dir.name not in request.import_ids:
                continue
            if not package_dir.is_dir():
                continue
            exported_roots.add(package_dir.name)
            for file in package_dir.rglob("*"):
                if file.is_file(): archive.write(file, f"robots/{package_dir.name}/{file.relative_to(package_dir).as_posix()}")
        # A project can reference a built-in or previously imported package
        # outside workspace/packages. Carry that package with the project so a
        # recipe remains reproducible on another machine.
        contract_data = request.training_config.get("contract") if isinstance(request.training_config, dict) else None
        if isinstance(contract_data, dict):
            package = package_for_contract(contract_data)
            package_root = Path(str(package.get("package_root", "")))
            if package_root.exists() and package_root.is_dir():
                package_id = str(package.get("package_id") or package_root.name)
                if package_id in exported_roots:
                    package_root = None
            if package_root is not None and package_root.exists() and package_root.is_dir():
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
        workspace = _workspace_root()
        packages_root = workspace / "packages"
        packages_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="legged-studio-project-", dir=workspace) as extracted_value:
            extracted_root = Path(extracted_value)
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                files = [item for item in archive.infolist() if not item.is_dir()]
                members = [_safe_zip_path(item.filename) for item in files]
                if len(members) > 5000:
                    raise ValueError("project package contains too many files")
                for info, relative in zip(files, members):
                    if relative.parts[0] not in {"imports", "robots", "training", "scenarios", "manifest.json"}:
                        raise ValueError(f"unsupported package entry: {relative}")
                    target = extracted_root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(info))
            manifest_path = extracted_root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig")) if manifest_path.exists() else {}
            _normalise_robot_packages(extracted_root, manifest)
            training_config = json.loads((extracted_root / "training/config.json").read_text(encoding="utf-8-sig")) if (extracted_root / "training/config.json").exists() else {}
            scenario = json.loads((extracted_root / "scenarios/active.json").read_text(encoding="utf-8-sig")) if (extracted_root / "scenarios/active.json").exists() else {}
            robots = _persist_robot_packages(extracted_root, packages_root)
        return {"success": True, "import_root": _api_path(packages_root), "package_ids": [item["package_id"] for item in robots], "manifest": manifest, "robots": robots, "training_config": training_config, "scenario": scenario}
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
        relative = _api_path(model)
        fmt = "urdf" if model.suffix.lower() == ".urdf" else "mjcf"
        report = _validate(ModelValidationRequest(path=relative, filename=model.name, format=fmt))
        if not report.get("valid"):
            continue
        # 归一摘要（CRLF → LF）：这个值会写进契约的 ``urdf.hash``，而契约校验
        # （``contracts.validator._compute_file_hash``）用的是归一版 —— 此前这里是原始字节
        # sha256，于是 CRLF 模型文件导入后**立刻**校验失败（hash mismatch）。
        digest = normalized_sha256(model.read_bytes())
        package_id = "imported_" + "".join(c.lower() if c.isalnum() else "_" for c in model.stem).strip("_")[:40]
        contract = draft_model_contract(Path(relative), fmt, report.get("inspection", {}), digest)
        contract.update({"robot_id": package_id or "imported_robot", "contract_id": f"{package_id}_contract_v1", "source": "legged_studio_project_import", "tags": ["imported", "project_package"]})
        (imported_root / "contract.json").write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        package = {"schema_version": "robot-package-1.0", "package_id": package_id, "task_kind": "generic", "capabilities": ["generic_mjlab", "mujoco_sim"], "model_path": relative}
        (imported_root / "robot_package.json").write_text(json.dumps({**package, "model": {"format": fmt, "path": str(model.relative_to(imported_root)).replace("\\", "/"), "assets_path": "model/assets"}, "contract_path": "contract.json", "training_config_path": "training/config.json", "simulation_config_path": "simulation/config.json"}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        break


def _persist_robot_packages(extracted_root: Path, packages_root: Path) -> list[dict[str, Any]]:
    """Atomically promote valid extracted robot packages into the workspace."""
    package_roots = sorted({path.parent for path in extracted_root.rglob("robot_package.json") if (path.parent / "contract.json").exists()})
    robots: list[dict[str, Any]] = []
    for source in package_roots:
        descriptor = json.loads((source / "robot_package.json").read_text(encoding="utf-8-sig"))
        contract = json.loads((source / "contract.json").read_text(encoding="utf-8-sig"))
        base_id = _safe_package_id(str(descriptor.get("package_id") or contract.get("robot_id") or source.name))
        source_hash = str(descriptor.get("content_sha256") or _tree_hash(source))
        target = packages_root / base_id
        if target.exists():
            existing_descriptor = json.loads((target / "robot_package.json").read_text(encoding="utf-8-sig")) if (target / "robot_package.json").exists() else {}
            existing_hash = str(existing_descriptor.get("content_sha256") or _tree_hash(target))
            if existing_hash != source_hash:
                target = packages_root / f"{base_id}_{source_hash[:10]}"
        if not target.exists():
            staging = packages_root / f".staging-{target.name}"
            if staging.exists():
                shutil.rmtree(staging)
            shutil.copytree(source, staging)
            staging.rename(target)

        contract_path = target / "contract.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8-sig"))
        descriptor_path = target / "robot_package.json"
        descriptor = json.loads(descriptor_path.read_text(encoding="utf-8-sig"))
        model_entry = descriptor.get("model", {}) if isinstance(descriptor.get("model"), dict) else {}
        model = target / str(model_entry.get("path", "")) if model_entry.get("path") else None
        if model is None or not model.is_file():
            old_name = Path(str(contract.get("urdf", {}).get("path", ""))).name
            matches = [item for item in target.rglob(old_name) if item.is_file()] if old_name else []
            model = matches[0] if matches else None
        if model is not None:
            contract.setdefault("urdf", {})["path"] = _api_path(model)
        descriptor["package_id"] = target.name
        descriptor.setdefault("content_sha256", source_hash)
        contract["robot_id"] = target.name
        contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        descriptor_path.write_text(json.dumps(descriptor, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        from backend.robot_packages import upsert_package
        upsert_package(target, source="workspace")
        robots.append({"package_id": target.name, "package_root": _api_path(target), "robot_id": contract.get("robot_id"), "family": contract.get("family"), "contract": contract, "asset_path": contract.get("urdf", {}).get("path"), "robot_package": descriptor})
    return robots
