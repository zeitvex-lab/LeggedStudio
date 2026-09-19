"""Model inspection API shared by the Web workbench and future CLI.

This endpoint deliberately performs structural inspection before any training:
XML parsing, joint/actuator counts, mesh references, file hash, and optional
MuJoCo compilation. It does not import or duplicate the URDF Studio viewer.
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
import io
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from contracts.asset_paths import resolve_asset_path
from contracts.validator import normalized_sha256, package_digest
from backend.gl_env import ensure_headless_gl, render_error_hint
from backend.robot_packages import write_package_manifest


router = APIRouter(prefix="/api/models", tags=["models"])
PROJECT_ROOT = Path(__file__).resolve().parents[1]


# 路径约定解析收口到 ``backend.paths``（工作区根 / 数据目录 / 仓库相对路径，各一处实现）。
from backend.paths import api_path, data_dir, workspace_root as _workspace_root


def _api_path(path: Path) -> str:
    """仓库相对 posix 路径（唯一实现见 ``backend.paths.api_path``）。"""

    return api_path(path)


def _content_hash(entries: Iterable[tuple[Path, bytes]]) -> str:
    """规范化内容哈希：把 ``(包内相对路径, 字节)`` 按路径排序后连路径一起摘要。

    digest 与"哪些文件 / 路径长什么样 / 内容是什么"完全绑定 ⇒ **同一份资产重复导入
    得到同一个 ``package_id``**（幂等），换掉一个 mesh 就得到新包（不可变，见 import 文档）。

    三件必须一起成立的事（2026-09-16 I 组；第三件 2026-09-17 补，B39 同族收口）：
      * **上传与目录拷贝必须得到同一个 digest** —— Web 走 base64 上传、CLI 走 `onboard <dir>`
        目录拷贝，两条入口描述的是同一份资产，digest 不同就会产出两个包；
      * 排序键是**包内相对路径**（``as_posix``），与调用方给的绝对路径无关；
      * **内容先 CRLF → LF 归一再摘要**（``contracts.validator.normalize_line_endings``，
        全仓唯一实现）—— 上传的文本载荷经 universal newlines 到达时已是 LF，目录入口是
        原始字节（Windows 文本写入产生 CRLF）；不归一的话同一份资产在两条入口/两个平台
        得到两个 digest，正是 B39 拆掉的"同一工件两套哈希口径"在这条链上的残留。
    """

    return package_digest(entries)


def _package_content_hash(request: "ModelImportRequest") -> str:
    """上传入口的 digest：把 base64/文本载荷还原成字节后交给共享的 :func:`_content_hash`。"""

    return _content_hash(
        (
            _safe_import_relative_path(item.path),
            base64.b64decode(item.content, validate=True) if item.encoding == "base64" else item.content.encode("utf-8"),
        )
        for item in request.files
    )


#: 导入时**不拷贝**的目录名（VCS 元数据 / 字节码缓存 / 依赖树）。
#: 它们是"目录里可能有但不属于模型资产"的东西，拷进去只会污染包内容与 digest。
_PACKAGE_COPY_SKIP_DIRS = frozenset({".git", "__pycache__", ".venv", "node_modules", ".idea", ".vscode"})
#: 目录拷贝的 fail-closed 上限（防止误指一个巨型目录把 workspace 撑爆）。
_PACKAGE_COPY_MAX_FILES = 2000
_PACKAGE_COPY_MAX_BYTES = 512 * 1024 * 1024
_MODEL_SUFFIXES = (".urdf", ".xml", ".mjcf")


def list_package_tree(source_dir: Path) -> tuple[list[Path], list[str]]:
    """列出可作为机器人包内容的文件（返回 ``(相对路径列表, 跳过的目录名)``）。

    只跳过 :data:`_PACKAGE_COPY_SKIP_DIRS` 里的目录（并在结果里**如实报告**跳过了哪些），
    其余文件一律照搬 —— 不做"猜哪些是模型资产"的智能筛选：猜错的代价是包里少文件，
    而少文件要到训练时才炸。
    """

    files: list[Path] = []
    skipped: list[str] = []
    for child in sorted(source_dir.rglob("*")):
        if child.is_dir():
            if child.name in _PACKAGE_COPY_SKIP_DIRS:
                skipped.append(child.relative_to(source_dir).as_posix())
            continue
        if any(part in _PACKAGE_COPY_SKIP_DIRS for part in child.relative_to(source_dir).parts):
            continue
        if child.is_file():
            files.append(child.relative_to(source_dir))
    return files, skipped


def stage_package_tree(source_dir: Path, staging: Path) -> dict[str, Any]:
    """把 ``source_dir`` 的内容拷进 ``staging``（相对路径保持不变），返回文件清单摘要。

    **路径不可信**：与上传入口同一套守卫（:func:`_safe_import_relative_path`）逐条复核，
    并把规模上限当作 fail-closed 判据（超限直接拒绝，不做截断）。
    """

    relative_files, skipped = list_package_tree(source_dir)
    if not relative_files:
        raise ValueError(f"目录里没有文件: {source_dir}")
    if len(relative_files) > _PACKAGE_COPY_MAX_FILES:
        raise ValueError(f"目录文件数 {len(relative_files)} 超过上限 {_PACKAGE_COPY_MAX_FILES}（疑似指错了目录）")

    total_bytes = 0
    staged: list[tuple[Path, bytes]] = []
    for relative in relative_files:
        safe = _safe_import_relative_path(relative.as_posix())
        source = source_dir / relative
        data = source.read_bytes()
        total_bytes += len(data)
        if total_bytes > _PACKAGE_COPY_MAX_BYTES:
            raise ValueError(f"目录体积超过上限 {_PACKAGE_COPY_MAX_BYTES // (1024 * 1024)} MB（疑似指错了目录）")
        target = staging / safe
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        staged.append((safe, data))
    return {"staged": staged, "skipped_dirs": skipped, "total_bytes": total_bytes}


def pick_model_file(files: Iterable[Path], explicit: str | None = None) -> Path:
    """在候选里挑出**唯一的**模型文件；零个或多个（且未显式指定）一律 fail-closed。

    选错模型的代价是生成一份语义完全错误的契约 —— 比报错难查得多，所以这里不"挑一个
    最像的"，而是把候选列出来让人明确指定。
    """

    if explicit:
        candidate = _safe_import_relative_path(explicit)
        if candidate not in set(files):
            raise ValueError(f"指定的模型文件不在目录里: {explicit}")
        return candidate
    models = [item for item in files if item.suffix.lower() in _MODEL_SUFFIXES]
    if not models:
        raise ValueError("目录里找不到 URDF/MJCF 模型文件（后缀 .urdf/.xml/.mjcf）")
    if len(models) > 1:
        listed = ", ".join(item.as_posix() for item in sorted(models)[:12])
        raise ValueError(f"目录里有 {len(models)} 个候选模型文件，请用 --model 指定：{listed}")
    return models[0]


def import_staged_package(
    staging: Path,
    *,
    model_relative: Path,
    model_format: str,
    content_hash: str,
    packages_root: Path,
) -> dict[str, Any]:
    """**导入核心（两条入口共用）**：staging 里已放好该包的全部文件 →

    ① 校验模型（结构 + MuJoCo 编译）→ ② 生成三件 JSON（``contract.json`` /
    ``robot_package.json`` / ``contract_legacy_v2.json``）→ ③ 落到 ``packages/<package_id>/``
    → ④ 登记索引。

    Web 的 ``POST /api/models/import``（base64 上传）与 CLI 的 ``onboard <dir>``（目录拷贝）
    都调这里：编排**只有一份**，否则两条入口迟早给出不同的包（V4 单一真值）。
    校验不过时**一个字节都不写**（fail-closed），只把校验报告返回给调用方。
    """

    staged_model = staging / model_relative
    validation = _validate(ModelValidationRequest(path=str(staged_model), filename=staged_model.name, format=model_format))
    if not validation.get("valid"):
        validation.update({"imported": False, "import_root": None, "model_path": None})
        return validation

    provisional = _contract_draft(staged_model, validation.get("format", model_format), validation.get("inspection", {}), validation.get("sha256", ""))
    package_id = f"{provisional['robot_id']}_{content_hash[:10]}"
    package_root = packages_root / package_id
    final_model = package_root / model_relative
    final_model_value = _api_path(final_model)
    contract = _contract_draft(Path(final_model_value), validation.get("format", model_format), validation.get("inspection", {}), validation.get("sha256", ""))
    contract["robot_id"] = package_id
    contract["contract_id"] = f"{package_id}_contract_v1"

    if not package_root.exists():
        (staging / "contract_legacy_v2.json").write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_package_manifest(staging, package_id=package_id, task_kind="generic")
        descriptor = json.loads((staging / "robot_package.json").read_text(encoding="utf-8-sig"))
        descriptor.update({
            "model": {"format": model_format, "path": model_relative.as_posix(), "assets_path": str(model_relative.parent).replace("\\", "/")},
            "contract_path": "contract_legacy_v2.json",
            "content_sha256": content_hash,
        })
        descriptor_path = staging / "robot_package.json"
        descriptor_path.write_text(json.dumps(descriptor, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        staging.rename(package_root)

    # T1.3 导入闭环：导入即生成契约真值 sidecar（外部裸模型无仿真配置 →
    # 通用执行器默认值并在 description 标注"待校准"；失败不阻断导入）
    contract_note = None
    if package_root.exists() and not (package_root / "contract.json").exists():
        try:
            from backend.contract_migration import migrate_contract_dict

            draft_v3 = migrate_contract_dict(contract, None, generic_defaults=True)
            (package_root / "contract.json").write_text(
                json.dumps(draft_v3, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            contract_note = "generated（通用执行器默认值，训练前请校准）"
        except Exception as exc:
            contract_note = f"skipped: {exc}"

    from backend.robot_packages import upsert_package

    upsert_package(package_root, source="workspace")

    validation.update({
        "imported": True,
        "package_id": package_id,
        "import_root": _api_path(package_root),
        "package_root": _api_path(package_root),
        "model_path": final_model_value,
        "contract_draft": contract,
        "contract": {"generated": contract_note is not None and contract_note.startswith("generated"), "note": contract_note},
    })
    return validation


class ModelValidationRequest(BaseModel):
    path: str | None = None
    content: str | None = None
    filename: str = "model.xml"
    format: Literal["urdf", "mjcf", "auto"] = "auto"
    contract: dict[str, Any] | None = None


class ImportedAssetFile(BaseModel):
    path: str = Field(..., min_length=1, max_length=512)
    content: str
    encoding: Literal["utf-8", "base64"] = "utf-8"


class ModelImportRequest(BaseModel):
    files: list[ImportedAssetFile] = Field(..., min_length=1, max_length=2000)
    model_filename: str | None = None
    format: Literal["urdf", "mjcf", "auto"] = "auto"


class ModelPreviewRequest(ModelValidationRequest):
    width: int = Field(default=960, ge=320, le=1920)
    height: int = Field(default=640, ge=240, le=1440)


def _safe_import_relative_path(value: str) -> Path:
    normalized = value.replace("\\", "/").lstrip("/")
    candidate = Path(normalized)
    if not normalized or candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"invalid asset path: {value}")
    return candidate


def _contract_draft(model_path: Path, model_format: str, inspection: dict[str, Any], digest: str) -> dict[str, Any]:
    joints = inspection.get("joints", [])
    joint_names = [item.get("name") for item in joints if item.get("name")]
    actuated = [item for item in joints if item.get("type") not in {"fixed", "floating", "planar"}]
    actuated_names = [item.get("name") for item in actuated if item.get("name")]
    if model_format == "mjcf":
        targets = inspection.get("actuators", {}).get("targets", [])
        actuated_names = [name for name in targets if name in joint_names]
        if not actuated_names:
            actuated_names = joint_names
    wheel = any("wheel" in name.lower() for name in joint_names)
    robot_name = inspection.get("root_name") or model_path.stem
    robot_id = "imported_" + "".join(char.lower() if char.isalnum() else "_" for char in model_path.stem).strip("_")
    robot_id = robot_id[:48] or "imported_robot"
    mass = inspection.get("inertial", {}).get("total_mass_kg")
    return {
        "schema_version": "robot-contract-2.0",
        "contract_id": f"{robot_id}_contract_v1",
        "robot_id": robot_id,
        "family": str(robot_name),
        "size_class": "M",
        "locomotion_type": "W" if wheel else "P",
        "urdf": {"path": str(model_path).replace("\\", "/"), "hash": digest, "total_mass_kg": float(mass or 0.0), "mass_source": "urdf_inertial", "mesh_files": inspection.get("mesh_files", [])},
        "joints": {"actuated_joints": actuated_names, "passive_joints": [name for name in joint_names if name not in actuated_names], "default_pose": [0.0] * len(actuated_names)},
        "observation": {"dimension": max(1, 9 + len(actuated_names) * 3), "components": ["base_lin_vel", "base_ang_vel", "projected_gravity", "joint_pos", "joint_vel", "last_action"]},
        "action": {"dimension": len(actuated_names), "joint_order": actuated_names, "action_scale": 0.25},
        "control": {"control_hz": 50, "physics_hz": 1000, "decimation": 20},
        "description": "Imported robot asset draft generated by Legged Studio validation.",
        "tags": ["imported", model_format],
        "source": "legged_studio_asset_import",
        "min_mjlab_version": "1.6.0",
        "python_version": "3.12",
    }


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
    roots = [PROJECT_ROOT, _workspace_root()]
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

    def joint_link(item: ET.Element, tag: str) -> str | None:
        node = item.find(tag)
        return (node.get("link") if node is not None else None) or (node.text.strip() if node is not None and node.text else None)
    child_links = {value for item in joints if (value := joint_link(item, "child"))}
    parent_links = {value for item in joints if (value := joint_link(item, "parent"))}
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
        "joints": [{"name": item.get("name"), "type": item.get("type"), "parent": joint_link(item, "parent"), "child": joint_link(item, "child")} for item in joints],
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
        PROJECT_ROOT,
        _workspace_root(),
        data_dir(default=_workspace_root()),
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
        # B39 口径：urdf.hash 必须是规范化哈希（与 contracts.validator._compute_file_hash 同一实现），
        # 否则 Windows 文本写入的 CRLF 会让 onboard 写入的哈希与 verify package 的复算必然分叉。
        digest = normalized_sha256(raw)
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
            from contracts.contract_legacy_v2 import ContractLegacyV2
            from contracts.validator import validate_contract

            try:
                contract = ContractLegacyV2(**request.contract)
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


def _urdf_preview_svg(root: ET.Element) -> str:
    """Render a deterministic topology preview for URDF assets in the browser."""
    links = {item.get("name"): item for item in root.findall("./link") if item.get("name")}
    joints = []
    children: dict[str, list[tuple[str, str]]] = {}
    child_names = set()
    for joint in root.findall("./joint"):
        parent_node = joint.find("parent")
        child_node = joint.find("child")
        parent = (parent_node.get("link") if parent_node is not None else None) or (parent_node.text.strip() if parent_node is not None and parent_node.text else "")
        child = (child_node.get("link") if child_node is not None else None) or (child_node.text.strip() if child_node is not None and child_node.text else "")
        if parent and child and child in links:
            joints.append((parent, child, joint.get("name") or "joint", joint.get("type") or "fixed"))
            children.setdefault(parent, []).append((child, joint.get("type") or "fixed"))
            child_names.add(child)
    roots = [name for name in links if name not in child_names] or list(links)[:1]
    positions: dict[str, tuple[float, float]] = {}
    queue = [(roots[0], 0.0, 0.0)] if roots else []
    while queue:
        name, x, y = queue.pop(0)
        if name in positions:
            continue
        positions[name] = (x, y)
        children_for_parent = children.get(name, [])
        spread = max(1, len(children_for_parent))
        for index, (child, _kind) in enumerate(children_for_parent):
            queue.append((child, x + 150.0, y + (index - (spread - 1) / 2) * 70.0))
    for index, name in enumerate(links):
        positions.setdefault(name, (float(index % 5) * 150.0, float(index // 5) * 70.0))
    max_x = max((point[0] for point in positions.values()), default=0.0) + 100.0
    min_y = min((point[1] for point in positions.values()), default=0.0) - 50.0
    max_y = max((point[1] for point in positions.values()), default=0.0) + 50.0
    width = max(520.0, max_x + 50.0)
    height = max(260.0, max_y - min_y + 50.0)
    lines = []
    for parent, child, joint_name, joint_type in joints:
        px, py = positions[parent]
        cx, cy = positions[child]
        lines.append(f'<line x1="{px + 54:.1f}" y1="{py - min_y + 24:.1f}" x2="{cx + 54:.1f}" y2="{cy - min_y + 24:.1f}" stroke="#7b93a6" stroke-width="2"/><text x="{(px + cx) / 2 + 54:.1f}" y="{(py + cy) / 2 - min_y + 18:.1f}" fill="#496173" font-size="10" text-anchor="middle">{_svg_escape(joint_name)} · {_svg_escape(joint_type)}</text>')
    nodes = []
    for name, (x, y) in positions.items():
        nodes.append(f'<g><rect x="{x + 8:.1f}" y="{y - min_y:.1f}" width="92" height="48" rx="5" fill="#dce8f0" stroke="#3e6e8c"/><text x="{x + 54:.1f}" y="{y - min_y + 22:.1f}" fill="#173247" font-size="11" text-anchor="middle">{_svg_escape(name[:16])}</text><text x="{x + 54:.1f}" y="{y - min_y + 37:.1f}" fill="#5c7484" font-size="9" text-anchor="middle">link</text></g>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" role="img" aria-label="URDF link and joint topology">{"".join(lines)}{"".join(nodes)}</svg>'


def _svg_escape(value: str) -> str:
    return (str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


@router.post("/preview")
async def preview_model(request: ModelPreviewRequest) -> dict[str, Any]:
    path, temporary = _read_source(request)
    try:
        root = ET.fromstring(path.read_bytes())
        model_format = root.tag.lower() == "robot" and "urdf" or "mjcf"
        if model_format == "urdf":
            return {"success": True, "format": "urdf", "svg": _urdf_preview_svg(root)}
        # 幂等兜底：正常由 backend/__init__ 更早设定；这里再确认一次，避免本模块被
        # 单独导入（脚本 / 单测）时错过「必须在 import mujoco 前确定后端」的窗口。
        ensure_headless_gl()
        import mujoco
        import numpy as np
        model = mujoco.MjModel.from_xml_path(str(path))
        width = min(request.width, int(getattr(model.vis.global_, "offwidth", request.width)))
        height = min(request.height, int(getattr(model.vis.global_, "offheight", request.height)))
        renderer = mujoco.Renderer(model, height=max(120, height), width=max(160, width))
        data = mujoco.MjData(model)
        camera = mujoco.MjvCamera()
        mujoco.mjv_defaultFreeCamera(model, camera)
        if model.nbody > 1:
            body_pos = model.body_pos[1:]
            lower = body_pos.min(axis=0)
            upper = body_pos.max(axis=0)
            camera.lookat[:] = (lower + upper) * 0.5
            camera.distance = max(float((upper - lower).max()) * 2.8, 0.8)
            camera.azimuth = 135.0
            camera.elevation = -20.0
        mujoco.mj_forward(model, data)
        renderer.update_scene(data, camera=camera)
        pixels = renderer.render()
        renderer.close()
        try:
            from PIL import Image
            stream = io.BytesIO()
            Image.fromarray(np.asarray(pixels, dtype=np.uint8)).save(stream, format="PNG")
            png_bytes = stream.getvalue()
        except ImportError:
            # Keep preview functional in the lean control-plane environment.
            import struct, zlib
            rgba = np.asarray(pixels, dtype=np.uint8)
            raw_rows = b"".join(b"\0" + row.tobytes() for row in rgba)
            def chunk(kind, data):
                return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
            png_bytes = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw_rows)) + chunk(b"IEND", b"")
        return {"success": True, "format": "mjcf", "image_base64": base64.b64encode(png_bytes).decode("ascii"), "width": width, "height": height}
    except Exception as exc:
        return {"success": False, "format": request.format, "error": render_error_hint(exc)}
    finally:
        if temporary:
            path.unlink(missing_ok=True)


def import_package_directory(
    source_dir: Path | str,
    *,
    model_filename: str | None = None,
    model_format: str = "auto",
    packages_root: Path | None = None,
) -> dict[str, Any]:
    """**目录入口**（CLI ``onboard``／未来的 Web 向导）：把整个目录作为包内容导入。

    与上传入口共用 :func:`import_staged_package`；两侧 digest 由同一 :func:`_content_hash`
    从**同样的字节**算出 ⇒ 同一份资产无论走上传还是走目录，都得到同一个 ``package_id``
    （这正是"两条入口 = 同一件事"的可检验形式）。
    """

    source_dir = Path(source_dir).expanduser().resolve()
    if not source_dir.is_dir():
        raise ValueError(f"目录不存在: {source_dir}")
    packages_root = Path(packages_root) if packages_root else _workspace_root() / "packages"
    packages_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".staging-", dir=packages_root) as staging_value:
        staging = Path(staging_value)
        staged = stage_package_tree(source_dir, staging)
        files = [relative for relative, _data in staged["staged"]]
        model_relative = pick_model_file(files, model_filename)
        resolved_format = model_format if model_format != "auto" else ("urdf" if model_relative.suffix.lower() == ".urdf" else "mjcf")
        result = import_staged_package(
            staging,
            model_relative=model_relative,
            model_format=resolved_format,
            content_hash=_content_hash(staged["staged"]),
            packages_root=packages_root,
        )
        result.update({
            "source_dir": str(source_dir),
            "model_file": model_relative.as_posix(),
            "file_count": len(files),
            "staged_bytes": staged["total_bytes"],
            "skipped_dirs": staged["skipped_dirs"],
        })
        return result


def preview_package_import(
    source_dir: Path | str,
    *,
    model_filename: str | None = None,
    model_format: str = "auto",
    packages_root: Path | None = None,
) -> dict[str, Any]:
    """**预演**：校验 + 出三件 JSON 的内容 + 算出会落在哪里，但**不写任何东西**。

    预演与真导入必须给出同一份 JSON，所以这里复用同一组原语（``pick_model_file`` /
    ``_validate`` / ``_contract_draft`` / ``_content_hash``），区别只在**不落盘、不登记**。

    落点说明（诚实边界）：staging 目录建在 ``packages/`` 下而不是系统临时目录 —— 模型校验
    （``_safe_path``）只接受"项目内 / workspace 内"的路径，系统临时目录会被拒。因此预演会
    创建 ``packages/``（若不存在）并在其中建一个临时 staging 子目录，**用完即删**：
    不改任何已存在的包、不改索引。
    """

    source_dir = Path(source_dir).expanduser().resolve()
    if not source_dir.is_dir():
        raise ValueError(f"目录不存在: {source_dir}")
    packages_root = Path(packages_root) if packages_root else _workspace_root() / "packages"
    packages_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".staging-preview-", dir=packages_root) as staging_value:
        staging = Path(staging_value)
        staged = stage_package_tree(source_dir, staging)
        files = [relative for relative, _data in staged["staged"]]
        model_relative = pick_model_file(files, model_filename)
        resolved_format = model_format if model_format != "auto" else ("urdf" if model_relative.suffix.lower() == ".urdf" else "mjcf")
        staged_model = staging / model_relative
        validation = _validate(ModelValidationRequest(path=str(staged_model), filename=staged_model.name, format=resolved_format))
        preview: dict[str, Any] = {
            "preview": True,
            "valid": bool(validation.get("valid")),
            "format": validation.get("format", resolved_format),
            "source_dir": str(source_dir),
            "model_file": model_relative.as_posix(),
            "file_count": len(files),
            "staged_bytes": staged["total_bytes"],
            "skipped_dirs": staged["skipped_dirs"],
            "errors": list(validation.get("errors") or []),
            "warnings": list(validation.get("warnings") or []),
            "stats": validation.get("stats"),
            "sha256": validation.get("sha256"),
        }
        if not validation.get("valid"):
            return preview
        contract = _contract_draft(staged_model, preview["format"], validation.get("inspection", {}), validation.get("sha256", ""))
        content_hash = _content_hash(staged["staged"])
        package_id = f"{contract['robot_id']}_{content_hash[:10]}"
        contract["robot_id"] = package_id
        contract["contract_id"] = f"{package_id}_contract_v1"
        preview.update({
            "package_id": package_id,
            "package_root": _api_path(Path(packages_root) / package_id if packages_root else _workspace_root() / "packages" / package_id),
            "content_sha256": content_hash,
            "contract_draft": contract,
        })
        try:
            from backend.contract_migration import migrate_contract_dict

            preview["contract_preview"] = migrate_contract_dict(contract, None, generic_defaults=True)
        except Exception as exc:  # 预演不该因 sidecar 生成失败而整体失败，如实标注
            preview["contract_preview"] = None
            preview["warnings"].append(f"contract_truth 预览生成失败: {exc}")
        return preview


@router.post("/import")
async def import_model(request: ModelImportRequest) -> dict[str, Any]:
    """Validate and persist a model as a stable robot package（**上传入口**）。

    The package id includes a hash of every imported file. Re-importing the
    same asset is idempotent, while changing a mesh produces a new immutable
    package instead of silently mutating a training dependency.

    编排一律交给 :func:`import_staged_package`（与 CLI ``onboard`` 同一份实现）；
    本函数只负责"把 base64 载荷落成 staging 目录"这件事。
    """
    try:
        packages_root = _workspace_root() / "packages"
        packages_root.mkdir(parents=True, exist_ok=True)
        names = [_safe_import_relative_path(item.path) for item in request.files]
        requested_model = _safe_import_relative_path(request.model_filename).as_posix() if request.model_filename else None
        content_hash = _package_content_hash(request)
        with tempfile.TemporaryDirectory(prefix=".staging-", dir=packages_root) as staging_value:
            staging = Path(staging_value)
            model_relative: Path | None = None
            for item, relative in zip(request.files, names):
                target = staging / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if item.encoding == "base64":
                    try:
                        target.write_bytes(base64.b64decode(item.content, validate=True))
                    except Exception as exc:
                        raise ValueError(f"invalid base64 content for {item.path}: {exc}") from exc
                else:
                    target.write_text(item.content, encoding="utf-8")
                if requested_model == relative.as_posix() or (model_relative is None and relative.suffix.lower() in {".urdf", ".xml", ".mjcf"}):
                    model_relative = relative
            if model_relative is None:
                raise ValueError("no URDF/MJCF model file found in import")
            staged_model = staging / model_relative
            model_format = request.format if request.format != "auto" else ("urdf" if staged_model.suffix.lower() == ".urdf" else "mjcf")
            return import_staged_package(
                staging,
                model_relative=model_relative,
                model_format=model_format,
                content_hash=content_hash,
                packages_root=packages_root,
            )
    except Exception as exc:
        return {"valid": False, "imported": False, "errors": [str(exc)], "warnings": []}


@router.get("/formats")
async def model_formats() -> dict[str, Any]:
    return {"formats": [{"id": "urdf", "label": "URDF"}, {"id": "mjcf", "label": "MJCF"}]}


# ========== 资产体检五卡（T1.1，批次 1 / M2） ==========

@router.get("/packages/{robot_id}/inspection")
async def inspect_robot_package(robot_id: str) -> dict[str, Any]:
    """体检五卡：质量/碰撞/惯量/电机参数（角色分组+官方 diff）/关节。"""
    from backend.asset_inspection import inspect_package
    from backend.robot_presets import get_robot_preset

    preset = get_robot_preset(robot_id)
    root_value = str(((preset or {}).get("robot_package") or {}).get("package_root", ""))
    root = Path(root_value) if root_value else PROJECT_ROOT / "assets" / "robots" / robot_id
    if not root.exists():
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"robot package not found: {robot_id}")
    return inspect_package(root)
