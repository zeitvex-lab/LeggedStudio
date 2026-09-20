"""
Legged Studio Backend - Complete API

FastAPI control plane for the Web workbench: robot packages, asset inventory,
training orchestration, simulation, evaluation, and export endpoints.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pathlib import Path
from contracts.validator import normalized_sha256  # 归一摘要唯一实现

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
from backend.inventory import InventoryError, dict_records, filter_records, load_inventory
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
from contracts.contract_legacy_v2 import ContractLegacyV2
from contracts.validator import validate_contract as validate_robot_contract
from contracts.scenario_contract import ScenarioContract
from adapters.mjlab.native_adapter import preflight as native_mjlab_preflight
from backend.version import APP_VERSION
from backend.project_api import router as project_router
from backend.exports_api import router as exports_router
from backend.settings_api import router as settings_router
from backend.map_editor_api import router as map_editor_router
from backend.perception_observations import router as perception_router
from backend.sensor_suite import router as sensor_suite_router
from backend.perception_api import router as perception_api_router
from backend.height_scan import router as height_scan_router
from backend.camera_projection import router as camera_projection_router
from backend.limits_api import router as limits_router
from backend.episode_api import router as episode_router
from backend.pack_catalog import router as pack_catalog_router

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
app.include_router(settings_router)
app.include_router(map_editor_router)
app.include_router(perception_router)
app.include_router(sensor_suite_router)
app.include_router(perception_api_router)
app.include_router(height_scan_router)
app.include_router(pack_catalog_router)
app.include_router(camera_projection_router)
app.include_router(limits_router)
app.include_router(episode_router)
if simulation_router is not None:
    app.include_router(simulation_router)


# Asset inventory endpoints are kept on the complete API as well as the
# read-only inventory service so the desktop launcher has one control-plane
# process to start.
def _inventory_summary(inventory: dict[str, Any]) -> dict[str, Any]:
    records = dict_records(inventory)
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
        dict_records(inventory), readiness=readiness, size=size,
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
    records = filter_records(dict_records(inventory), readiness=readiness, size=size, locomotion=locomotion, family=family_name)
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
                "capabilities": (item.get("robot_package") or {}).get("capabilities", []),
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
    if not (source / "contract_legacy_v2.json").is_file() or not (source / "robot_package.json").is_file():
        raise HTTPException(status_code=400, detail="目标目录缺少 contract_legacy_v2.json 或 robot_package.json，不是有效的机器人包")
    contract = robot_packages._read_json(source / "contract_legacy_v2.json")
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


@app.get("/api/robots/packages/{robot_id}/contract-v3")
async def get_robot_contract(robot_id: str) -> dict[str, Any]:
    """D2：读包内契约真值——动作映射页的 reindex_from_model 可见可比对。"""
    preset = load_robot_preset(robot_id)
    if preset is None:
        raise HTTPException(status_code=404, detail=f"Unknown robot package: {robot_id}")
    root = Path(str((preset.get("robot_package") or {}).get("package_root", "")))
    v3_path = root / "contract.json"
    if not v3_path.exists():
        return {"success": True, "contract": None}
    try:
        return {"success": True, "contract": json.loads(v3_path.read_text(encoding="utf-8-sig"))}
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/robots/packages/{robot_id}")
async def update_robot_package(robot_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist a generic robot package configuration with copy-on-write."""
    preset = load_robot_preset(robot_id)
    if preset is None:
        raise HTTPException(status_code=404, detail=f"Unknown robot package: {robot_id}")
    contract = payload.get("contract") if isinstance(payload.get("contract"), dict) else payload
    if not isinstance(contract, dict):
        raise HTTPException(status_code=400, detail="contract must be an object")
    # P1：T-N 曲线（高级参数）走**独立顶层键**，不塞进 v2 contract——它只有契约真值 语义
    # （`actuator_profile[].t_n_curve`），写进 v2 只会又造一个"两个家"。
    # 兼容 `contract.control.t_n_curve` 的写法（手写请求也会被正确接收）。
    t_n_curve_payload = payload.get("t_n_curve")
    if t_n_curve_payload is None:
        t_n_curve_payload = (contract.get("control") or {}).get("t_n_curve")
    if isinstance(contract.get("control"), dict):
        contract["control"].pop("t_n_curve", None)
    # T-N 曲线相关校验共用（校验函数与开关取值域在写盘前就要到位，避免"只在有载荷时才定义"）
    from contracts.physics_binding import (
        ACTUATOR_MODELS,
        apply_t_n_curves as _validate_t_n_curves,
    )
    # P1 fail-closed：T-N 曲线"要么可解析、要么不提交"。v3 同步段是「失败不阻塞 v2 保存」的设计，
    # 若把校验放那里，坏曲线会被吞成 diagnostics.v3_sync=failed 而接口仍返回 200（面板显示"已保存"
    # 但曲线没落地）——这正是本项目反复出现的静默失败。故**写盘前**先校验。
    if t_n_curve_payload:
        try:
            _validate_t_n_curves({}, t_n_curve_payload)  # 空 v3 上跑：只触发解析与单调性校验，无副作用
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=f"T-N 曲线非法：{exc}") from exc
    requested_model = (contract.get("control") or {}).get("actuator_model")
    if requested_model is not None and requested_model not in ACTUATOR_MODELS:
        raise HTTPException(status_code=400, detail=f"actuator_model 取值非法：{requested_model!r}")
    if requested_model == "dc_motor":
        # 开了 DC 模型却没有任何曲线 → 拒绝（不静默回退到 ideal_pd：那等于用户以为生效了）
        _existing_root = Path(str((preset.get("robot_package") or {}).get("package_root", "")))
        _existing_v3 = _existing_root / "contract.json"
        _scratch = json.loads(_existing_v3.read_text(encoding="utf-8-sig")) if _existing_v3.is_file() else {}
        _validate_t_n_curves(_scratch, t_n_curve_payload)
        _profile = _scratch.get("actuator_profile") or {}
        _declared = bool((_profile.get("default") or {}).get("t_n_curve")) or any(
            isinstance(params, dict) and params.get("t_n_curve")
            for params in (list((_profile.get("by_role") or {}).values()) + list((_profile.get("by_joint") or {}).values()))
        )
        if not _declared:
            raise HTTPException(
                status_code=400,
                detail="actuator_model=dc_motor 但包内没有任何 t_n_curve 曲线：请先填写 T-N 曲线（不静默回退到 ideal_pd）",
            )
    try:
        contract_model = ContractLegacyV2(**contract)
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
        contract_path = target / "contract_legacy_v2.json"
        contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        simulation = payload.get("simulation") if isinstance(payload.get("simulation"), dict) else {}
        simulation_path = target / "simulation" / "config.json"
        previous = {}
        if simulation_path.exists():
            try:
                previous = json.loads(simulation_path.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError:
                previous = {}
        simulation_path.parent.mkdir(parents=True, exist_ok=True)
        # B3 收尾：merged_simulation 仍保留全部键（下方 D4 段要把控制层标量同步进
        # 契约真值），但**落盘时剔除已废弃的物理键**——物理事实只剩契约真值 一处，
        # 否则前端每次保存都会把这组重复键写回来，训练/验收侧又读到失效的 armature。
        from contracts.physics_binding import LEGACY_CONFIG_PHYSICS_KEYS

        merged_simulation = {**previous, **simulation}
        persisted_simulation = {
            key: value for key, value in merged_simulation.items() if key not in LEGACY_CONFIG_PHYSICS_KEYS
        }
        simulation_path.write_text(json.dumps(persisted_simulation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # D4：同步 contract.json——v3 是训练/浏览器仿真的单一真值（B2/B5），
        # 只写 v2 会让"工作台保存"对训练与仿真静默失效（无两处不一致的验收）。
        # 不重新迁移（会丢人工校准的 by_role/role_hints），而是外科手术式地把
        # 本次编辑的字段同步进 v3：joint_order / default_pose / control / 增益。
        v3_note = "absent"
        v3_gains: list[str] = []
        v3_t_n_curves: list[str] = []
        control_rates: dict[str, Any] = {}
        v3_path = target / "contract.json"
        if v3_path.exists():
            try:
                from contracts.generated import dump_v3, parse_contract

                v3 = json.loads(v3_path.read_text(encoding="utf-8-sig"))
                new_order = contract.get("action", {}).get("joint_order") or \
                    contract.get("joints", {}).get("actuated_joints") or []
                if new_order:
                    v3.setdefault("action", {})["joint_order"] = list(new_order)
                    # actuated 数组按新动作序重排（改名/新增的关节不动 v3 角色信息）
                    entries = {e.get("name"): e for e in v3.get("joints", {}).get("actuated", [])}
                    known = [entries[name] for name in new_order if name in entries]
                    v3["joints"]["actuated"] = known + \
                        [e for n, e in entries.items() if n not in new_order]
                payload_pose = contract.get("joints", {}).get("default_pose")
                if isinstance(payload_pose, list) and payload_pose:
                    v3.setdefault("joints", {})["default_pose"] = payload_pose
                # P2：控制三件套**不许被这条保存链改写**。
                # 此前无条件从 merged_simulation 写入 v3，而工作台送来的正是 **v2 契约里的
                # 旧值**（go2 实测 v2=1000/20 vs v3=500/10）→ 点一次「保存配置」就把 v3 的
                # 物理频率改成 2 倍，静默改变训练/验收/浏览器的时间基。v3 是唯一真值：
                # 这里只**对照并回报**（diagnostics.control_rates），不覆盖。
                v3.setdefault("control", {})
                _rates = ("control_hz", "physics_hz", "decimation")
                control_rates = {
                    "v3": {key: v3["control"].get(key) for key in _rates},
                    "payload": {key: merged_simulation.get(key) for key in _rates},
                }
                control_rates["agreed"] = all(
                    control_rates["payload"][key] is None or control_rates["payload"][key] == control_rates["v3"][key]
                    for key in _rates
                )
                # D10：action_scale 的**标量缺省**也要同步进 v3——工作台的「动作缩放」
                # 卡片既有标量框也有逐段框，只写 v2 的 action.action_scale 会让浏览器
                # 与训练侧继续读 v3 的旧值（B5/2 起 action_scale 唯一真值在契约真值）。
                payload_scale = (contract.get("action") or {}).get("action_scale")
                if payload_scale is not None:
                    v3.setdefault("action", {})["action_scale"] = payload_scale
                # P1：执行器模型开关（缺省不写 = ideal_pd = 现役行为不变）
                payload_model = (contract.get("control") or {}).get("actuator_model")
                if payload_model is not None:
                    v3["control"]["actuator_model"] = payload_model
                # 增益：逐关节值按"角色内全同 → by_role，否则 by_joint"归层
                # （与 role_resolver 的 default < by_role < by_joint 合并序一致）。
                # D8：映射实现已抽到 contracts.physics_binding.apply_actuator_gains
                # （纯函数、可单测），并统一含 armature / friction_loss —— 它们与
                # stiffness/damping/effort 同为 v3 一等参数，只写 v3、不落 sim config。
                from contracts.physics_binding import apply_t_n_curves, apply_actuator_gains

                v3_gains = apply_actuator_gains(v3, contract.get("control") or {})
                # P1：T-N 曲线（高级参数）——同一归层规则，值为折线点列
                v3_t_n_curves = apply_t_n_curves(v3, t_n_curve_payload)
                v3_model = parse_contract(v3)  # 校验；失败则不写，保留原 v3
                v3_path.write_text(
                    json.dumps(dump_v3(v3_model), ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                v3_note = "synced"
            except Exception as exc:  # noqa: BLE001  v3 同步失败不阻塞 v2 保存
                v3_note = f"failed: {exc}"
        descriptor_path = target / "robot_package.json"
        if descriptor_path.exists():
            descriptor = json.loads(descriptor_path.read_text(encoding="utf-8-sig"))
            # content_sha256 是"包内容摘要"字段：口径必须与 model_api / project_api 同源
            descriptor["content_sha256"] = normalized_sha256(contract_path.read_bytes())
            descriptor_path.write_text(json.dumps(descriptor, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        upsert_package(target)
        from backend import robot_packages as _packages

        return {"success": True, "robot_id": robot_id, "package_root": str(target), "contract": contract, "simulation": merged_simulation, "physics": _packages._physics_view(target), "action_scale": _packages._action_scale_view(target), "t_n_curve": _packages._t_n_curve_view(target), "diagnostics": {"valid": True, "writable_root": str(target), "v3_sync": v3_note, "v3_gains": v3_gains, "v3_t_n_curves": v3_t_n_curves, "control_rates": control_rates}}
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/contracts/validate")
async def validate_robot_contract_endpoint(contract_data: dict[str, Any]) -> dict[str, Any]:
    """Validate the canonical Robot Contract v2 used by every workflow step."""
    try:
        contract = ContractLegacyV2(**contract_data)
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
# Health and system status
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
