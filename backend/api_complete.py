"""
Legged Studio Backend - Complete API v0.4.0
修复：添加缺失的 system API
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os
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

# 注册所有路由
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
async def get_robot_presets() -> dict[str, Any]:
    presets = list_robot_presets()
    return {"count": len(presets), "presets": presets}


@app.get("/api/robots/presets/{robot_id}")
async def get_robot_preset(robot_id: str) -> dict[str, Any]:
    preset = load_robot_preset(robot_id)
    if preset is None:
        raise HTTPException(status_code=404, detail=f"Unknown robot preset: {robot_id}")
    return preset


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

# Web 控制台
WEB_DIR = Path(__file__).parent.parent / "web"

@app.get("/", include_in_schema=False)
async def root_redirect():
    return RedirectResponse(url="/web/workbench.html#home", status_code=302)

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


# Keep the legacy multi-page web console available to the desktop launcher and
# external browser links (training_create/list/monitor and shared assets).
if WEB_DIR.is_dir():
    app.mount("/web", StaticFiles(directory=WEB_DIR, html=True), name="web")

# ============================================================================
# 基础端点
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
    """Expose adapter availability without importing optional runtimes."""
    return {
        "control_plane": True,
        "adapters": {
            "native_mjlab": native_mjlab_preflight().get("execution_ready", False),
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
    native = native_mjlab_preflight()
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
