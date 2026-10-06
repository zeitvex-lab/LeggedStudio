"""
Legged Studio Backend - Complete API（v3.0 Phase 2：纯装配壳）

FastAPI 控制面的**装配文件**：app 工厂 + 中间件 + 路由挂载 + 系统/静态面。
业务路由全部在域文件（backend/*_api.py）——本文件不再内联业务端点
（2026-10-06 巨石拆解：31 条内联 → 13 条系统级，业务 18 条下沉
assets/robots/contracts/panels 四个域路由，路径与行为零变化）。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pathlib import Path

import mimetypes
import os
import socket
import sys
import platform

# Module scripts and WASM streaming need exact MIME types. The registry-backed
# mimetypes table on Windows (and the launcher's runtime Python) can report
# .mjs as text/plain, which makes Chromium refuse the dynamic import of the
# ONNX runtime with "Failed to fetch dynamically imported module".
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("application/wasm", ".wasm")
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware

# Force UTF-8 console output on Windows regardless of the active code page.
# 保留模块级引用：多余的 TextIOWrapper 若被 GC 会在 __del__ 里 close 共享的底层
# buffer，pytest capture 期间表现为 "ValueError: I/O operation on closed file"
# （曾让所有 import 本模块的后端测试在 pytest 下全挂）。
_UTF8_STDOUT_WRAPPERS: tuple = ()
if sys.platform == 'win32':
    import io
    _UTF8_STDOUT_WRAPPERS = (
        io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True),
        io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True),
    )
    sys.stdout = _UTF8_STDOUT_WRAPPERS[0]
    sys.stderr = _UTF8_STDOUT_WRAPPERS[1]

# Make the repository root importable when started as a plain script.
# 统一自举：见 contracts/path_bootstrap.py。
if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from contracts.path_bootstrap import ensure_project_root_on_path
ensure_project_root_on_path()

# Optional stacks: keep the control plane importable without them.
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
from backend.deploy_api import router as deploy_router
from backend.terrain_api import router as terrain_router
from backend.health_api import router as health_router
from backend.pretrained_api import router as pretrained_router
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
from adapters.mjlab.native_adapter import preflight as native_mjlab_preflight
from backend.version import APP_VERSION
from backend.project_api import router as project_router
from backend.exports_api import router as exports_router
from backend.task_plugins_api import router as task_plugins_router
from backend.task_profiles_api import router as task_profiles_router
from backend.settings_api import router as settings_router
from backend.map_editor_api import router as map_editor_router
from backend.perception_observations import router as perception_router
from backend.sensor_suite import router as sensor_suite_router
from backend.perception_api import router as perception_api_router
from backend.height_scan import router as height_scan_router
from backend.camera_projection import router as camera_projection_router
from backend.limits_api import router as limits_router
from backend.pack_catalog import router as pack_catalog_router
# v3.0 Phase 2 巨石拆解：业务域路由（原内联端点的下沉落点，路径与行为零变化）
from backend.assets_api import router as assets_router
from backend.robots_api import router as robots_router
from backend.contracts_api import router as contracts_router
from backend.panels_api import router as panels_router


def _shutdown_training_workers() -> None:
    """控制面退出时停止全部 running 训练任务（F6：训练进程生命周期无僵尸）。

    接线取舍：选 FastAPI lifespan（shutdown 段）而非 atexit——uvicorn 的正常
    退出（含 Ctrl+C 的 SIGINT → graceful shutdown）都会走 lifespan，时序上先于
    解释器退出，异常也更可控。已实测（starlette TestClient 语义）：不作为
    context manager 使用的 ``TestClient(app).get(...)`` 不触发 lifespan，所以
    test_api_complete.py 的大量裸 TestClient 用法不受影响。
    清理函数内部吞错：shutdown 钩子再抛异常只会污染退出码、掩盖真实清理结果。
    SIGKILL/断电等非正常退出仍无解——那正是启动侧孤儿判定（orphaned/failed
    补账，见 TrainingManager._reconcile_orphaned_task）存在的理由。
    """
    try:
        from backend import training_manager

        training_manager.shutdown_global_manager()
    except Exception as exc:  # noqa: BLE001
        print(f"[Shutdown] 训练 worker 清理失败: {exc}")


@asynccontextmanager
async def _lifespan(_: FastAPI):
    yield
    _shutdown_training_workers()


app = FastAPI(
    title="Legged Studio API",
    description="Legged Robot RL Platform - Complete Backend",
    version=APP_VERSION,
    lifespan=_lifespan,
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

# Register only the routers whose optional stacks are installed.
if training_router is not None:
    app.include_router(training_router)
if export_router is not None:
    app.include_router(export_router)
app.include_router(pretrained_router)
if evaluation_router is not None:
    app.include_router(evaluation_router)
if navigation_router is not None:
    app.include_router(navigation_router)
app.include_router(deploy_router)
app.include_router(terrain_router)
app.include_router(health_router)
app.include_router(model_router)
app.include_router(project_router)
app.include_router(exports_router)  # 序 10：Capability 导出物的 Web 入口（打包 / 校验 / 收包）
app.include_router(task_plugins_router)  # 任务插件：列目录 + 把"需要传感器的任务"实例化到场景
app.include_router(task_profiles_router)  # 任务档：列目录 + 组装成可跑场景（含浏览器端口的诚实阻断）
app.include_router(settings_router)
app.include_router(map_editor_router)
app.include_router(perception_router)
app.include_router(sensor_suite_router)
app.include_router(perception_api_router)
app.include_router(height_scan_router)
app.include_router(pack_catalog_router)
app.include_router(camera_projection_router)
app.include_router(limits_router)
if simulation_router is not None:
    app.include_router(simulation_router)
# v3.0 Phase 2 下沉的四个业务域路由
app.include_router(assets_router)     # /api/assets*、/api/summary（资产清点）
app.include_router(robots_router)     # /api/robots/*（预设只读面 + 包生命周期）
app.include_router(contracts_router)  # /api/{contracts,scenarios}/validate（无副作用校验）
app.include_router(panels_router)     # /api/panels*（面板插件 HTTP 投影）

# Web workbench static files
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
    """旧控制台已并入工作台首页（2026-09-23 用户裁决）：老地址 302 到 workbench#home。"""
    return RedirectResponse(url="/web/workbench.html#home", status_code=302)


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
# Health and system status（系统级端点：依赖装配态的可选栈信息，属装配文件本职）
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

async def _gpu_status() -> dict:
    """GPU 三态（cuda / cpu-only / unavailable）——**与 /api/health 口径同源**。

    直接复用 ``adapters.mjlab.preflight.gpu_probe``（L0 体检的同一实现：nvidia-smi
    子进程列设备 + 训练栈元数据判 cpu-only/unavailable，全程不 import torch）。
    探测是子进程调用（nvidia-smi 最多 10s），放到线程池避免阻塞事件循环。
    fail-soft：任何失败返回 ``unknown`` + 中文 reason，绝不让端点 500。
    """
    try:
        from adapters.mjlab.preflight import gpu_probe

        gpu = await run_in_threadpool(gpu_probe)
        devices = gpu.get("devices") or []
        mode = gpu.get("mode") or ("cuda" if devices else "unknown")
        return {
            "mode": mode,
            "devices": devices,
            "cpu_ready": bool(gpu.get("cpu_ready")),
            "available": bool(gpu.get("available")),
            "reason": gpu.get("reason"),
            "status": "ok",
        }
    except Exception as exc:  # noqa: BLE001 — fail-soft：探测失败如实降级，不让端点 500
        return {"mode": "unknown", "devices": [], "cpu_ready": False, "available": False,
                "reason": f"GPU 探测失败：{exc}", "status": "error"}


async def _mjlab_version_status() -> dict:
    """MJLab 实装版本 —— 复用 training/runs.py 的 dist-info 读取（纯文件系统，不 import）。

    venv 不存在 → ``not_installed``；存在但读不到 mjlab 的 dist-info → ``unknown``。
    全程 fail-soft：探测异常返回 ``version=None`` + 中文 reason。
    """
    try:
        project_root = Path(__file__).parent.parent
        from contracts.path_bootstrap import adapter_venv_dir

        venv_path = adapter_venv_dir(default=project_root / "adapters" / "mjlab" / ".venv")
        if not venv_path.exists():
            return {"version": None, "status": "not_installed",
                    "reason": f"适配器 venv 不存在（{venv_path}）——先在启动器『配置运行环境』供应"}
        from backend.training.runs import venv_package_versions

        versions = await run_in_threadpool(venv_package_versions, venv_path)
        version = versions.get("mjlab")
        if not version:
            return {"version": None, "status": "unknown",
                    "reason": f"venv 存在但未读到 mjlab 的 dist-info（{venv_path}）"}
        return {"version": version, "status": "installed", "reason": None}
    except Exception as exc:  # noqa: BLE001 — fail-soft
        return {"version": None, "status": "unknown", "reason": f"MJLab 版本读取失败：{exc}"}


@app.get("/api/system/environment")
async def get_environment_status():
    """Report runtime environment status.

    数据真值化（U11）：GPU 走 health 同源的 ``gpu_probe``，MJLab 版本走
    ``venv_package_versions`` 的 dist-info 实装版本 —— 展示层不再硬编码占位。
    控制面不 import torch/mjlab（dist-info 是读文件，不是 import）。
    """
    project_root = Path(__file__).parent.parent
    embedded_python_value = os.environ.get("LEGGED_STUDIO_RUNTIME_PYTHON", "").strip()
    embedded_python = Path(embedded_python_value) if embedded_python_value else None
    # 适配器 venv 落点统一由 contracts.path_bootstrap 解析（支持
    # LEGGED_STUDIO_MJLAB_VENV 覆盖与显式解释器环境变量）。
    from contracts.path_bootstrap import adapter_venv_dir

    adapter_paths = {
        "mjlab": adapter_venv_dir(default=project_root / "adapters" / "mjlab" / ".venv"),
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
    # U11：实装版本（dist-info 读文件，非 import）。venv 不存在时如实 not_installed；
    # 探测失败/缺包时 version=None，状态与中文原因随 version_status 如实透出。
    version_status = await _mjlab_version_status()
    adapters["mjlab"]["version"] = version_status["version"]
    adapters["mjlab"]["version_status"] = {
        "status": version_status["status"],
        "reason": version_status["reason"],
    }

    return {
        "control_plane": {
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "python_target": "3.12",
            "python_target_match": sys.version_info[:2] == (3, 12),
            "status": "running"
        },
        "adapters": adapters,
        # U11：GPU 三态，与 /api/health/layers 的 L0 同一探测实现（gpu_probe）。
        "gpu": await _gpu_status(),
    }

if __name__ == "__main__":
    import uvicorn

    print("=" * 70)
    print(f"Legged Studio Backend - v{APP_VERSION}")
    print("=" * 70)
    print()
    print("Features:")
    print("  ✓ Training Management API")
    print("  ✓ ONNX Export API")
    print("  ✓ Pretrained Models API")
    print("  ✓ Contract System V2")
    print("  ✓ Policy Artifacts")
    print("  ✓ URDF Validation")
    print("  ✓ Evaluation Tools")
    print("  ✓ Sim2Sim Validation")
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
