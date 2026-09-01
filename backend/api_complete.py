"""
Legged Studio Backend - Complete API v0.5.0
修复：添加缺失的 system API
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import sys
import platform
from typing import Any
from fastapi import HTTPException

# 修复 Windows 控制台编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 添加路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 导入所有路由
from backend.pipeline_api import router as pipeline_router
from backend.training_api import router as training_router
from backend.export_api import router as export_router
from backend.pretrained_api import router as pretrained_router
from backend.app import load_inventory, filter_records, _records, InventoryError
from backend.robot_presets import list_robot_presets, get_robot_preset as load_robot_preset
from backend.evaluation_api import router as evaluation_router

app = FastAPI(
    title="Legged Studio API",
    description="Legged Robot RL Platform - Complete Backend",
    version="0.5.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册所有路由
app.include_router(pipeline_router)
app.include_router(training_router)
app.include_router(export_router)
app.include_router(pretrained_router)
app.include_router(evaluation_router)


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
async def get_robot_presets() -> dict[str, Any]:
    presets = list_robot_presets()
    return {"count": len(presets), "presets": presets}


@app.get("/api/robots/presets/{robot_id}")
async def get_robot_preset(robot_id: str) -> dict[str, Any]:
    preset = load_robot_preset(robot_id)
    if preset is None:
        raise HTTPException(status_code=404, detail=f"Unknown robot preset: {robot_id}")
    return preset

# Web 控制台
WEB_DIR = Path(__file__).parent.parent / "web"

@app.get("/", include_in_schema=False)
async def root_redirect():
    return RedirectResponse(url="/web/dashboard_v2.html", status_code=302)

@app.get("/web/dashboard_v2.html", include_in_schema=False)
async def serve_dashboard():
    dashboard_path = WEB_DIR / "dashboard_v2.html"
    if dashboard_path.exists():
        return FileResponse(dashboard_path, media_type="text/html")
    return {"error": "Dashboard not found"}

@app.get("/web/dashboard_v2.css", include_in_schema=False)
async def serve_css():
    css_path = WEB_DIR / "dashboard_v2.css"
    if css_path.exists():
        return FileResponse(css_path, media_type="text/css")
    return {"error": "CSS not found"}

@app.get("/web/dashboard_v2.js", include_in_schema=False)
async def serve_js():
    js_path = WEB_DIR / "dashboard_v2.js"
    if js_path.exists():
        return FileResponse(js_path, media_type="application/javascript")
    return {"error": "JS not found"}


# Keep the legacy multi-page web console available to the desktop launcher and
# external browser links (training_create/list/monitor and shared assets).
if WEB_DIR.is_dir():
    app.mount("/web", StaticFiles(directory=WEB_DIR, html=True), name="web")

# ============================================================================
# 基础端点
# ============================================================================

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "0.5.0",
        "features": [
            "training_management",
            "onnx_export",
            "contract_validation",
            "policy_artifacts",
            "pretrained_models",
            "urdf_validation",
            "evaluation",
            "sim2sim"
        ]
    }

@app.get("/api")
async def api_info():
    return {
        "name": "Legged Studio API",
        "version": "0.5.0",
        "endpoints": {
            "training": "/api/training",
            "export": "/api/export",
            "pretrained": "/api/pretrained",
            "pipeline": "/api/pipeline",
            "system": "/api/system"
        },
        "docs": "/docs"
    }

@app.get("/api/system/info")
async def get_system_info():
    """获取系统信息"""
    return {
        "platform": platform.system(),
        "platform_version": platform.version(),
        "python_version": sys.version,
        "architecture": platform.machine(),
    }

@app.get("/api/system/environment")
async def get_environment_status():
    """获取环境状态"""
    project_root = Path(__file__).parent.parent
    adapter_paths = {
        "mjlab": project_root / "adapters" / "mjlab" / ".venv",
        "mjlab_new": project_root / "adapters" / "mjlab_new" / ".venv",
    }
    adapters = {}
    for adapter_id, venv_path in adapter_paths.items():
        exists = venv_path.exists()
        adapters[adapter_id] = {
            "name": "MJLab Adapter",
            "venv_exists": exists,
            "python_path": str(venv_path / ("Scripts" if sys.platform == "win32" else "bin") / "python.exe") if exists else None,
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
    print("Legged Studio Backend - v0.5.0")
    print("=" * 70)
    print()
    print("Features:")
    print("  ✅ Training Management API")
    print("  ✅ ONNX Export API")
    print("  ✅ Pretrained Models API")
    print("  ✅ Contract System V2")
    print("  ✅ Policy Artifacts")
    print("  ✅ URDF Validation")
    print("  ✅ Evaluation Tools")
    print("  ✅ Sim2Sim Validation")
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
