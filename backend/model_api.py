"""HTTP endpoints for model inspection, previews and package uploads."""

from __future__ import annotations

import base64
import io
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.gl_env import ensure_headless_gl, render_error_hint
from backend.model_validation import read_model_source, validate_model as inspect_model
from backend.package_import import import_staged_package, safe_import_relative_path
from backend.paths import workspace_root as _workspace_root
from contracts.validator import package_digest


router = APIRouter(prefix="/api/models", tags=["models"])
PROJECT_ROOT = Path(__file__).resolve().parents[1]


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


def _package_content_hash(request: ModelImportRequest) -> str:
    return package_digest(
        (
            safe_import_relative_path(item.path),
            base64.b64decode(item.content, validate=True) if item.encoding == "base64" else item.content.encode("utf-8"),
        )
        for item in request.files
    )


@router.post("/validate")
async def validate_model(request: ModelValidationRequest) -> dict[str, Any]:
    try:
        return inspect_model(
            path=request.path, content=request.content, filename=request.filename,
            model_format=request.format, contract=request.contract,
        )
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
    path, temporary = read_model_source(path=request.path, content=request.content, model_format=request.format)
    try:
        root = ET.fromstring(path.read_bytes())
        model_format = root.tag.lower() == "robot" and "urdf" or "mjcf"
        if model_format == "urdf":
            return {"success": True, "format": "urdf", "svg": _urdf_preview_svg(root)}
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


@router.post("/import", description=(
    "Validate and persist a model as a stable robot package（**上传入口**）。\n\n"
    "The package id includes a hash of every imported file. Re-importing the\n"
    "same asset is idempotent, while changing a mesh produces a new immutable\n"
    "package instead of silently mutating a training dependency.\n\n"
    "编排一律交给 :func:`import_staged_package`（与 CLI ``onboard`` 同一份实现）；\n"
    "本函数只负责\"把 base64 载荷落成 staging 目录\"这件事。"
))
async def import_model(request: ModelImportRequest) -> dict[str, Any]:
    try:
        packages_root = _workspace_root() / "packages"
        packages_root.mkdir(parents=True, exist_ok=True)
        names = [safe_import_relative_path(item.path) for item in request.files]
        requested_model = safe_import_relative_path(request.model_filename).as_posix() if request.model_filename else None
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
            result = import_staged_package(
                staging,
                model_relative=model_relative,
                model_format=model_format,
                content_hash=content_hash,
                packages_root=packages_root,
            )
            # 导入成功即起**后台冒烟**（1 iter / 2 envs，约 1~2 分钟）：静态就绪之外的"实测可训"
            # 由真跑背书，结论落包内 trainability.json，供就绪卡显示。失败不影响导入本身。
            if result.get("imported") and result.get("package_root"):
                try:
                    from backend import trainability_check
                    from backend.paths import REPO_ROOT

                    # 导入结果里的 package_root 是**仓库相对 posix 路径**（api_path 口径）
                    target = Path(str(result["package_root"]))
                    if not target.is_absolute():
                        target = REPO_ROOT / target
                    trainability_check.schedule(target)
                    result["trainability"] = {"status": "pending", "note": "已在后台起冒烟，稍后刷新查看"}
                except Exception as exc:  # noqa: BLE001 — 冒烟起不来不该把导入判失败
                    result["trainability"] = {"status": "unknown", "reason": f"{type(exc).__name__}: {exc}"}
            return result
    except Exception as exc:
        return {"valid": False, "imported": False, "errors": [str(exc)], "warnings": []}


@router.get("/formats")
async def model_formats() -> dict[str, Any]:
    return {"formats": [{"id": "urdf", "label": "URDF"}, {"id": "mjcf", "label": "MJCF"}]}


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
