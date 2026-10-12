"""机器人预设与包管理路由（v3.0 Phase 2：自 ``api_complete`` 巨石下沉的域路由）。

预设只读面（presets ×4）与包生命周期（refresh/import/delete/export/契约 v3 读取/
配置保存 PUT）原先内联在 ``api_complete``——按「api_complete 只做装配、业务路由
归域文件」的拆解纪律移到本模块（路径与行为零变化，测试经 ``app`` 全部照旧）。
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.robot_presets import get_robot_preset as load_robot_preset, list_robot_presets
from contracts.contract_legacy_v2 import ContractLegacyV2
from contracts.validator import normalized_sha256, validate_contract as validate_robot_contract

router = APIRouter(tags=["robots"])


@router.get("/api/robots/presets")
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


@router.get("/api/robots/presets/{robot_id}")
async def get_robot_preset(robot_id: str) -> dict[str, Any]:
    preset = load_robot_preset(robot_id)
    if preset is None:
        raise HTTPException(status_code=404, detail=f"Unknown robot preset: {robot_id}")
    return preset


@router.get("/api/robots/presets/{robot_id}/profiles")
async def get_robot_profiles(robot_id: str) -> dict[str, Any]:
    """Return package-owned training profiles without executing package code."""
    preset = load_robot_preset(robot_id)
    if preset is None:
        raise HTTPException(status_code=404, detail=f"Unknown robot package: {robot_id}")
    return {"robot_id": robot_id, "profiles": preset.get("training_profiles", []), "source": preset.get("robot_package", {}).get("package_root")}


@router.get("/api/robots/presets/{robot_id}/files/{asset_path:path}")
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


@router.post("/api/robots/packages/refresh")
async def refresh_robot_packages() -> dict[str, Any]:
    """Force a full rescan of both package roots and rebuild the index."""
    from backend import robot_packages
    records = robot_packages.rebuild_package_index()
    return {"success": True, "count": len(records), "robot_ids": [r.get("robot_id") for r in records]}


@router.post("/api/robots/packages/import")
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


@router.get("/api/robots/packages/{robot_id}/onboarding")
async def robot_package_onboarding(robot_id: str) -> dict[str, Any]:
    """接入 DoD 四步读数（N4 厂商适配包入口；与 CLI `panel onboarding` / 首页卡片同源）。"""
    from backend.onboarding import package_onboarding

    try:
        return package_onboarding(robot_id)
    except KeyError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/api/robots/packages/{robot_id}")
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


@router.get("/api/robots/packages/{robot_id}/export")
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


@router.get("/api/robots/packages/{robot_id}/contract-v3")
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


@router.put("/api/robots/packages/{robot_id}")
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
        from backend.package_records import package_contract_views

        views = package_contract_views(target)
        return {"success": True, "robot_id": robot_id, "package_root": str(target), "contract": contract, "simulation": merged_simulation, "physics": views["physics"], "action_scale": views["action_scale"], "t_n_curve": views["t_n_curve"], "diagnostics": {"valid": True, "writable_root": str(target), "v3_sync": v3_note, "v3_gains": v3_gains, "v3_t_n_curves": v3_t_n_curves, "control_rates": control_rates}}
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
