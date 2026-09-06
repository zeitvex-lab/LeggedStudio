"""
Legged Studio Backend - Complete API v0.6.1
濞ｅ浂鍠栭ˇ鏌ユ晬濮橆厼娼戦柛鏃傚Х瀹歌鲸寰勬潏鈺傜暠 system API
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import json
import mimetypes
import os
import socket
import sys
import platform
import shutil

# Module scripts and WASM streaming need exact MIME types. The registry-backed
# mimetypes table on Windows (and the launcher's runtime Python) can report
# .mjs as text/plain, which makes Chromium refuse the dynamic import of the
# ONNX runtime with "Failed to fetch dynamically imported module".
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("application/wasm", ".wasm")
from typing import Any
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware

# 濞ｅ浂鍠栭ˇ?Windows 闁硅矇鍐ㄧ厬闁告瑦澹嗙槐顏堟儘?
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 婵烇綀顕ф慨鐐垫崉椤栨氨绐?
sys.path.insert(0, str(Path(__file__).parent.parent))

# 閻庣數鍘ч崣鍡涘箥閳ь剟寮垫径搴ｇ唴闁?
try:
    from backend.training_api import router as training_router
except ImportError as exc:  # optional training stack; enabled after adapter setup
    training_router = None
    TRAINING_IMPORT_ERROR = str(exc)
try:
    from backend.export_api import router as export_router
except ImportError as exc:  # optional export stack (torch/ONNX)
    export_router = None
    EXPORT_IMPORT_ERROR = str(exc)
from backend.pretrained_api import router as pretrained_router
from backend.app import load_inventory, filter_records, _records, InventoryError
from backend.robot_presets import list_robot_presets, get_robot_preset as load_robot_preset
try:
    from backend.evaluation_api import router as evaluation_router
    from backend.navigation_api import router as navigation_router
except ImportError as exc:  # optional MuJoCo/NumPy stack
    evaluation_router = None
    navigation_router = None
    SIM_IMPORT_ERROR = str(exc)
from backend.model_api import router as model_router
try:
    from backend.simulation_api import router as simulation_router
except ImportError as exc:  # optional MuJoCo/NumPy stack
    simulation_router = None
    SIM_IMPORT_ERROR = str(exc)
from contracts.robot_contract_v2 import RobotContractV2
from contracts.validator import validate_contract as validate_robot_contract
from contracts.scenario_contract import ScenarioContract
from adapters.mjlab.native_adapter import preflight as native_mjlab_preflight
from backend.version import APP_VERSION
from backend.project_api import router as project_router

app = FastAPI(
    title="Legged Studio API",
    description="Legged Robot RL Platform - Complete Backend",
    version=APP_VERSION
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class BrowserSimulationIsolationMiddleware(BaseHTTPMiddleware):
    """Enable SharedArrayBuffer for the browser MuJoCo pthread build."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/web"):
            # Dev edits must show up on reload, but a full no-store re-downloads
            # ~1.3 MB of vendored three.js plus every stylesheet on every page
            # load. ETag revalidation keeps edits fresh (changed files get a new
            # ETag) while unchanged files resolve to a 304.
            response.headers["Cache-Control"] = "no-cache"
        if request.url.path.startswith("/web/sim2sim"):
            response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
            response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
            response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        return response


app.add_middleware(BrowserSimulationIsolationMiddleware)

# 婵炲鍔岄崬浠嬪箥閳ь剟寮垫径搴ｇ唴闁?
if training_router is not None:
    app.include_router(training_router)
if export_router is not None:
    app.include_router(export_router)
app.include_router(pretrained_router)
if evaluation_router is not None:
    app.include_router(evaluation_router)
if navigation_router is not None:
    app.include_router(navigation_router)
app.include_router(model_router)
app.include_router(project_router)
if simulation_router is not None:
    app.include_router(simulation_router)


# Asset inventory endpoints are kept on the complete API as well as the
# read-only inventory service so the desktop launcher has one control-plane
# process to start.
def _inventory_summary(inventory: dict[str, Any]) -> dict[str, Any]:
    records = _records(inventory)
    by_size: dict[str, int] = {}
    by_locomotion: dict[str, int] = {}
    families: set[str] = set()
    for record in records:
        size = str(record.get("size_class_by_mass") or "UNKNOWN")
        locomotion = str(record.get("locomotion") or "UNKNOWN")
        by_size[size] = by_size.get(size, 0) + 1
        by_locomotion[locomotion] = by_locomotion.get(locomotion, 0) + 1
        if record.get("family"):
            families.add(str(record["family"]))
    summary = dict(inventory.get("summary", {}))
    summary.update({
        "total": len(records),
        "count": len(records),
        "by_size": by_size,
        "by_locomotion": by_locomotion,
        "families": sorted(families),
        "schema_version": inventory.get("schema_version"),
        "document_role": inventory.get("document_role"),
        "size_taxonomy": inventory.get("size_taxonomy", {}),
    })
    return summary


@app.get("/api/assets/summary")
async def get_assets_summary() -> dict[str, Any]:
    try:
        return _inventory_summary(load_inventory())
    except InventoryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/summary")
async def get_inventory_summary() -> dict[str, Any]:
    return await get_assets_summary()


@app.get("/api/assets")
async def get_assets(
    readiness: str | None = None,
    size: str | None = None,
    locomotion: str | None = None,
    family: str | None = None,
    offset: int = 0,
    limit: int = 500,
) -> dict[str, Any]:
    try:
        inventory = load_inventory()
    except InventoryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    records = filter_records(
        _records(inventory), readiness=readiness, size=size,
        locomotion=locomotion, family=family,
    )
    offset = max(0, offset)
    limit = min(500, max(1, limit))
    return {"count": len(records), "offset": offset, "limit": limit, "records": records[offset:offset + limit]}


@app.get("/api/assets/{family_name}")
async def get_asset_family(family_name: str, readiness: str | None = None, size: str | None = None, locomotion: str | None = None) -> dict[str, Any]:
    try:
        inventory = load_inventory()
    except InventoryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    records = filter_records(_records(inventory), readiness=readiness, size=size, locomotion=locomotion, family=family_name)
    if not records:
        raise HTTPException(status_code=404, detail=f"Unknown asset family: {family_name}")
    return {"family": family_name, "count": len(records), "records": records}


@app.get("/api/robots/presets")
async def get_robot_presets(summary: bool = False) -> dict[str, Any]:
    presets = list_robot_presets()
    if summary:
        presets = [
            {
                "source": item.get("source"),
                "robot_id": item.get("robot_id"),
                "package_id": item.get("package_id"),
                "family": item.get("family"),
                "size_class": item.get("size_class"),
                "locomotion_type": item.get("locomotion_type"),
                "dof": item.get("dof"),
                "mass_kg": item.get("mass_kg"),
                "contract_id": item.get("contract_id"),
                "robot_package": {
                    "model": (item.get("robot_package") or {}).get("model", {}),
                },
            }
            for item in presets
        ]
    return {"count": len(presets), "presets": presets}


@app.get("/api/robots/presets/{robot_id}")
async def get_robot_preset(robot_id: str) -> dict[str, Any]:
    preset = load_robot_preset(robot_id)
    if preset is None:
        raise HTTPException(status_code=404, detail=f"Unknown robot preset: {robot_id}")
    return preset


@app.get("/api/robots/presets/{robot_id}/profiles")
async def get_robot_profiles(robot_id: str) -> dict[str, Any]:
    """Return package-owned training profiles without executing package code."""
    preset = load_robot_preset(robot_id)
    if preset is None:
        raise HTTPException(status_code=404, detail=f"Unknown robot package: {robot_id}")
    return {"robot_id": robot_id, "profiles": preset.get("training_profiles", []), "source": preset.get("robot_package", {}).get("package_root")}
@app.get("/api/robots/presets/{robot_id}/files/{asset_path:path}")
async def get_robot_package_file(robot_id: str, asset_path: str):
    """Serve a read-only file from any discovered robot package."""
    preset = load_robot_preset(robot_id)
    if preset is None:
        raise HTTPException(status_code=404, detail=f"Unknown robot package: {robot_id}")
    package_root_value = preset.get("robot_package", {}).get("package_root")
    if not package_root_value:
        raise HTTPException(status_code=404, detail="Robot package root is unavailable")
    root = Path(str(package_root_value)).resolve()
    normalized = asset_path.replace("\\", "/").lstrip("/")
    candidate = (root / normalized).resolve()
    if candidate != root and root not in candidate.parents:
        raise HTTPException(status_code=400, detail="invalid package asset path")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Robot package file not found")
    # Mesh/XML re-downloads dominate the robot page preview time. FileResponse
    # already carries ETag + Last-Modified; no-cache turns repeat selections
    # into cheap 304 revalidations instead of full transfers.
    response = FileResponse(candidate)
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.post("/api/robots/packages/refresh")
async def refresh_robot_packages() -> dict[str, Any]:
    """Force a full rescan of both package roots and rebuild the index."""
    from backend import robot_packages
    records = robot_packages.rebuild_package_index()
    return {"success": True, "count": len(records), "robot_ids": [r.get("robot_id") for r in records]}


@app.post("/api/robots/packages/import")
async def import_robot_package(payload: dict[str, Any]) -> dict[str, Any]:
    """Import a robot package from an absolute source path.

    Validates contract + manifest, copies the whole package directory into the
    workspace ``packages/`` root (the writable, persisted location) and
    refreshes the index.  Re-importing an existing ``package_id`` refreshes it
    in place.
    """
    from backend import robot_packages
    source = Path(str(payload.get("path", "")).strip()).expanduser()
    if not source.is_absolute():
        raise HTTPException(status_code=400, detail="path 必须是绝对路径")
    if not source.is_dir():
        raise HTTPException(status_code=404, detail=f"目录不存在: {source}")
    if not (source / "contract.json").is_file() or not (source / "robot_package.json").is_file():
        raise HTTPException(status_code=400, detail="目标目录缺少 contract.json 或 robot_package.json，不是有效的机器人包")
    contract = robot_packages._read_json(source / "contract.json")
    robot_id = str(contract.get("robot_id") or robot_packages._read_json(source / "robot_package.json").get("package_id") or source.name)
    workspace_root = robot_packages._workspace_root()
    packages_root = (workspace_root / "packages").resolve()
    source_resolved = source.resolve()
    if packages_root in source_resolved.parents or source_resolved == packages_root:
        target = source_resolved  # 已在工作区内，直接登记
    else:
        target = packages_root / source_resolved.name
        if target.exists():
            raise HTTPException(status_code=409, detail=f"工作区已存在同名目录: {target.name}；如需覆盖请先删除")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_resolved, target)
    upserted = robot_packages.upsert_package(target, source="workspace")
    if upserted is None:
        raise HTTPException(status_code=400, detail="包校验失败：contract/manifest 缺失或不可读")
    robot_packages._write_index_meta(robot_packages._package_signature())
    record = next((r for r in robot_packages.list_robot_packages() if r.get("robot_id") == upserted), None)
    return {"success": True, "robot_id": upserted, "package_root": str(target), "record_summary": {
        "family": (record or {}).get("family"),
        "dof": (record or {}).get("dof"),
        "mass_kg": (record or {}).get("mass_kg"),
        "profiles": [p.get("profile_id") for p in (record or {}).get("training_profiles", [])],
    }}


@app.delete("/api/robots/packages/{robot_id}")
async def delete_robot_package(robot_id: str) -> dict[str, Any]:
    """Delete a workspace-resident package (shipped assets are read-only)."""
    from backend import robot_packages
    record = next((r for r in robot_packages.list_robot_packages() if r.get("robot_id") == robot_id), None)
    if record is None:
        raise HTTPException(status_code=404, detail=f"未知机器人包: {robot_id}")
    root = Path(str(record.get("robot_package", {}).get("package_root", ""))).resolve()
    workspace_packages = (robot_packages._workspace_root() / "packages").resolve()
    assets_root = (Path(__file__).resolve().parents[1] / "assets" / "robots").resolve()
    if assets_root in root.parents or root == assets_root:
        raise HTTPException(status_code=400, detail="内置包为只读，只能删除工作区中的包")
    if workspace_packages not in root.parents:
        raise HTTPException(status_code=400, detail="仅支持删除工作区 packages/ 目录下的包")
    shutil.rmtree(root, ignore_errors=True)
    robot_packages.invalidate_package_cache()
    records = robot_packages.rebuild_package_index()
    return {"success": True, "deleted": robot_id, "robot_ids": [r.get("robot_id") for r in records]}


@app.get("/api/robots/packages/{robot_id}/export")
async def export_robot_package(robot_id: str):
    """Download the whole package as a zip (model + contract + configs + profiles)."""
    import tempfile
    import zipfile
    from starlette.background import BackgroundTask
    from backend import robot_packages
    record = next((r for r in robot_packages.list_robot_packages() if r.get("robot_id") == robot_id), None)
    if record is None:
        raise HTTPException(status_code=404, detail=f"未知机器人包: {robot_id}")
    root = Path(str(record.get("robot_package", {}).get("package_root", ""))).resolve()
    if not root.is_dir():
        raise HTTPException(status_code=404, detail="包目录不存在")
    fd, zip_path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(root.rglob("*")):
            if f.is_file() and "logs" not in f.parts:
                zf.write(f, f.relative_to(root))
    return FileResponse(zip_path, media_type="application/zip", filename=f"{robot_id}-package.zip",
                        background=BackgroundTask(os.remove, zip_path))


@app.put("/api/robots/packages/{robot_id}")
async def update_robot_package(robot_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist a generic robot package configuration with copy-on-write."""
    preset = load_robot_preset(robot_id)
    if preset is None:
        raise HTTPException(status_code=404, detail=f"Unknown robot package: {robot_id}")
    contract = payload.get("contract") if isinstance(payload.get("contract"), dict) else payload
    if not isinstance(contract, dict):
        raise HTTPException(status_code=400, detail="contract must be an object")
    try:
        contract_model = RobotContractV2(**contract)
        contract_result = validate_robot_contract(contract_model)
        if not contract_result.valid:
            raise ValueError("; ".join(item.message for item in contract_result.errors))
        from backend.robot_packages import _workspace_root, upsert_package
        root = Path(str(preset.get("robot_package", {}).get("package_root", ""))).resolve()
        workspace_root = _workspace_root().resolve()
        packages_root = (workspace_root / "packages").resolve()
        assets_root = (Path(__file__).resolve().parents[1] / "assets" / "robots").resolve()
        if root == packages_root or packages_root in root.parents:
            target = root
        elif root == assets_root or assets_root in root.parents:
            target = packages_root / root.name
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(root, target)
        else:
            raise ValueError("package is outside writable package roots")
        contract_path = target / "contract.json"
        contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
        simulation = payload.get("simulation") if isinstance(payload.get("simulation"), dict) else {}
        simulation_path = target / "simulation" / "config.json"
        previous = {}
        if simulation_path.exists():
            try:
                previous = json.loads(simulation_path.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError:
                previous = {}
        simulation_path.parent.mkdir(parents=True, exist_ok=True)
        merged_simulation = {**previous, **simulation}
        simulation_path.write_text(json.dumps(merged_simulation, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
        descriptor_path = target / "robot_package.json"
        if descriptor_path.exists():
            descriptor = json.loads(descriptor_path.read_text(encoding="utf-8-sig"))
            descriptor["content_sha256"] = __import__("hashlib").sha256(contract_path.read_bytes()).hexdigest()
            descriptor_path.write_text(json.dumps(descriptor, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
        upsert_package(target)
        return {"success": True, "robot_id": robot_id, "package_root": str(target), "contract": contract, "simulation": merged_simulation, "diagnostics": {"valid": True, "writable_root": str(target)}}
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/contracts/validate")
async def validate_robot_contract_endpoint(contract_data: dict[str, Any]) -> dict[str, Any]:
    """Validate the canonical Robot Contract v2 used by every workflow step."""
    try:
        contract = RobotContractV2(**contract_data)
    except Exception as exc:
        return {"valid": False, "errors": [str(exc)], "warnings": []}

    result = validate_robot_contract(contract)
    return {
        "valid": result.valid,
        "errors": [item.message for item in result.errors],
        "warnings": [item.message for item in result.warnings],
        "robot_id": contract.robot_id,
        "contract_id": contract.contract_id,
        "schema_version": contract.schema_version,
        "actuated_joints": len(contract.joints.actuated_joints),
        "control_hz": contract.control.control_hz,
        "summary": contract.get_summary(),
    }


@app.post("/api/scenarios/validate")
async def validate_scenario(scenario_data: dict[str, Any]) -> dict[str, Any]:
    try:
        scenario = ScenarioContract(**scenario_data)
    except Exception as exc:
        return {"valid": False, "errors": [str(exc)], "warnings": []}
    return {"valid": True, "errors": [], "warnings": [], "scenario": scenario.to_payload()}

# Web 闁硅矇鍐ㄧ厬闁?
WEB_DIR = Path(__file__).parent.parent / "web"

@app.get("/", include_in_schema=False)
async def root_redirect():
    return RedirectResponse(url="/web/workbench.html#home", status_code=302)


@app.get("/sim2sim/", include_in_schema=False)
async def browser_sim2sim_redirect():
    """Open the simulation module inside the unified workbench."""
    return RedirectResponse(url="/web/workbench.html#simulation", status_code=302)

@app.get("/web/dashboard.html", include_in_schema=False)
async def serve_dashboard():
    dashboard_path = WEB_DIR / "dashboard.html"
    if dashboard_path.exists():
        return FileResponse(dashboard_path, media_type="text/html")
    return {"error": "Dashboard not found"}

@app.get("/web/dashboard.css", include_in_schema=False)
async def serve_css():
    css_path = WEB_DIR / "dashboard.css"
    if css_path.exists():
        return FileResponse(css_path, media_type="text/css")
    return {"error": "CSS not found"}

@app.get("/web/dashboard.js", include_in_schema=False)
async def serve_js():
    js_path = WEB_DIR / "dashboard.js"
    if js_path.exists():
        return FileResponse(js_path, media_type="application/javascript")
    return {"error": "JS not found"}


@app.get("/web/sim2sim/vendor/onnxruntime-web/dist/ort.wasm.min.mjs", include_in_schema=False)
async def serve_onnx_runtime_module():
    """Serve the ONNX Runtime ESM shim as JavaScript.

    On Windows Starlette may infer ``.mjs`` as ``text/plain``. Chromium then
    rejects the module before the MuJoCo page can finish initializing.
    """
    module_path = WEB_DIR / "sim2sim" / "vendor" / "onnxruntime-web" / "dist" / "ort.wasm.min.mjs"
    if module_path.exists():
        return FileResponse(module_path, media_type="text/javascript")
    raise HTTPException(status_code=404, detail="ONNX Runtime module not found")


@app.get("/web/sim2sim/vendor/onnxruntime-web/dist/ort-wasm-simd-threaded.mjs", include_in_schema=False)
async def serve_onnx_runtime_threaded_module():
    module_path = WEB_DIR / "sim2sim" / "vendor" / "onnxruntime-web" / "dist" / "ort-wasm-simd-threaded.mjs"
    if module_path.exists():
        return FileResponse(module_path, media_type="text/javascript")
    raise HTTPException(status_code=404, detail="ONNX Runtime threaded module not found")


@app.get("/web/sim2sim/vendor/onnxruntime-web/dist/{runtime_file}", include_in_schema=False)
async def serve_onnx_runtime_asset(runtime_file: str):
    """Serve bundled ORT WASM sidecars with correct MIME types."""
    allowed = {
        "ort.wasm.min.js": "text/javascript",
        "ort.wasm.js": "text/javascript",
        "ort-wasm-simd-threaded.wasm": "application/wasm",
        "ort-wasm-simd-threaded.asyncify.mjs": "text/javascript",
        "ort-wasm-simd-threaded.jsep.mjs": "text/javascript",
        "ort-wasm-simd-threaded.asyncify.wasm": "application/wasm",
        "ort-wasm-simd-threaded.jsep.wasm": "application/wasm",
    }
    media_type = allowed.get(runtime_file)
    if not media_type:
        raise HTTPException(status_code=404, detail="ONNX Runtime asset not found")
    path = WEB_DIR / "sim2sim" / "vendor" / "onnxruntime-web" / "dist" / runtime_file
    if not path.exists():
        raise HTTPException(status_code=404, detail="ONNX Runtime asset not found")
    return FileResponse(path, media_type=media_type)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


# Keep the legacy multi-page web console available to the desktop launcher and
# external browser links (training_create/list/monitor and shared assets).
if WEB_DIR.is_dir():
    app.mount("/web", StaticFiles(directory=WEB_DIR, html=True), name="web")

# ============================================================================
# 闁糕晞娅ｉ、鍛博椤栨粌浠?
# ============================================================================

@app.get("/health")
async def health():
    optional = {
        "training": training_router is not None,
        "export": export_router is not None,
        "evaluation": evaluation_router is not None,
        "navigation": navigation_router is not None,
        "simulation": simulation_router is not None,
    }
    return {
        "app_id": "legged-studio",
        "api_schema": "legged-studio-api-1",
        "instance_id": os.environ.get("LEGGED_STUDIO_INSTANCE_ID"),
        "process_id": os.getpid(),
        "source_root": str(Path(__file__).resolve().parents[1]),
        "hostname": socket.gethostname(),
        "status": "ok",
        "version": APP_VERSION,
        "optional": optional,
        "features": [
            "training_management",
            "onnx_export",
            "contract_validation",
            "policy_artifacts",
            "pretrained_models",
            "urdf_validation",
            "evaluation",
            "sim2sim",
            "navigation_replay"
        ] if all(optional.values()) else [name for name, enabled in optional.items() if enabled]
    }

@app.get("/api/system/capabilities")
async def get_capabilities():
    """Expose adapter availability without touching optional runtimes.

    The MJLab readiness probe imports torch in worker interpreters, which only
    training needs; page loads get the cached snapshot (or not_probed) so the
    event loop is never blocked by a subprocess probe.
    """
    native = await run_in_threadpool(native_mjlab_preflight)
    return {
        "control_plane": True,
        "adapters": {
            "native_mjlab": native.get("execution_ready", False),
            "native_mjlab_status": native.get("status", "not_probed"),
            "mujoco_simulation": simulation_router is not None,
            "export_onnx": export_router is not None,
        },
        "import_errors": {
            key: value for key, value in {
                "training": globals().get("TRAINING_IMPORT_ERROR"),
                "export": globals().get("EXPORT_IMPORT_ERROR"),
                "simulation": globals().get("SIM_IMPORT_ERROR"),
            }.items() if value
        },
    }


@app.get("/api/adapters/status")
async def get_adapter_status():
    """Report native MJLab training and MuJoCo simulation readiness."""
    native = await run_in_threadpool(native_mjlab_preflight)
    return {
        "native_mjlab": native,
        "mujoco_simulation": {"status": "ready" if simulation_router is not None else "missing_dependencies", "api_loaded": simulation_router is not None},
        "policy": "training uses native MJLab in its isolated adapter environment; interactive simulation uses MuJoCo",
    }

@app.get("/api")
async def api_info():
    return {
        "name": "Legged Studio API",
        "version": APP_VERSION,
        "endpoints": {
            "training": "/api/training",
            "export": "/api/export",
            "pretrained": "/api/pretrained",
            "navigation": "/api/navigation",
            "simulation": "/api/simulation",
            "scenarios": "/api/scenarios/validate",
            "adapters": "/api/adapters/status",
            "system": "/api/system"
        },
        "docs": "/docs"
    }

@app.get("/api/system/info")
async def get_system_info():
    """Return basic system information."""
    return {
        "platform": platform.system(),
        "platform_version": platform.version(),
        "python_version": sys.version,
        "architecture": platform.machine(),
    }

@app.get("/api/system/environment")
async def get_environment_status():
    """Report runtime environment status."""
    project_root = Path(__file__).parent.parent
    embedded_python_value = os.environ.get("LEGGED_STUDIO_RUNTIME_PYTHON", "").strip()
    embedded_python = Path(embedded_python_value) if embedded_python_value else None
    adapter_paths = {
        "mjlab": project_root / "adapters" / "mjlab" / ".venv",
    }
    adapters = {}
    for adapter_id, venv_path in adapter_paths.items():
        python_path = embedded_python if embedded_python and embedded_python.exists() else venv_path / ("Scripts" if sys.platform == "win32" else "bin") / ("python.exe" if sys.platform == "win32" else "python")
        exists = python_path.exists()
        adapters[adapter_id] = {
            "name": "MJLab Adapter",
            "venv_exists": exists,
            "python_path": str(python_path) if exists else None,
            "embedded": bool(embedded_python and embedded_python.exists()),
            "status": "installed" if exists else "not_installed",
        }

    return {
        "control_plane": {
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "python_target": "3.12",
            "python_target_match": sys.version_info[:2] == (3, 12),
            "status": "running"
        },
        "adapters": adapters,
    }

if __name__ == "__main__":
    import uvicorn

    print("=" * 70)
    print(f"Legged Studio Backend - v{APP_VERSION}")
    print("=" * 70)
    print()
    print("Features:")
    print("  闁?Training Management API")
    print("  闁?ONNX Export API")
    print("  闁?Pretrained Models API")
    print("  闁?Contract System V2")
    print("  闁?Policy Artifacts")
    print("  闁?URDF Validation")
    print("  闁?Evaluation Tools")
    print("  闁?Sim2Sim Validation")
    print()
    print("Web Console: http://127.0.0.1:8765")
    print("API Docs:    http://127.0.0.1:8765/docs")
    print()
    print("Starting server...")
    print("=" * 70)

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8765,
        log_level="info"
    )
