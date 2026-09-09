"""部署包 API（T3.2/T3.3，批次 3 / M4）。

POST /api/deploy/package   生成部署包 zip（四件套：契约/FSM/解码层/确认清单）
GET  /api/deploy/download?path=...  下载已生成的 zip（限 workspace/deploy 目录）

安全边界：只生成物料，不直接发电机命令（"一键生成 ≠ 一键上机"）。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.deploy_pack import ROOT, generate_deploy_package

router = APIRouter(prefix="/api/deploy", tags=["deploy"])


class DeployPackageRequest(BaseModel):
    robot_id: str
    policy_onnx_path: str | None = None  # 可选：随包携带策略 ONNX
    degraded: bool = False  # T3.4 劣化参数档：力矩 ×0.8（跑稳再上真机）
    target_platform: str = "unitree_sdk2"  # 目标平台模板：unitree_sdk2 / ros2
    bench_mode: bool = False  # D2 台架模式：额外生成 d2_bench_test.py（对应清单 #12）


@router.post("/package")
async def create_deploy_package(request: DeployPackageRequest):
    try:
        report = generate_deploy_package(request.robot_id, degraded=request.degraded, target_platform=request.target_platform, bench_mode=request.bench_mode)
        if request.policy_onnx_path:
            from pathlib import Path as _P
            import zipfile

            onnx = _P(request.policy_onnx_path)
            if onnx.exists():
                with zipfile.ZipFile(report["path"], "a", zipfile.ZIP_DEFLATED) as zf:
                    zf.write(onnx, "policy.onnx")
                report["files"].append("policy.onnx")
        report["download_url"] = f"/api/deploy/download?path={Path(report['path']).name}"
        return {"success": True, **report}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/download")
async def download_deploy_package(path: str):
    safe = Path(path).name  # 只允许文件名（防路径穿越）
    target = ROOT / "workspace" / "deploy" / safe
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"deploy package not found: {safe}")
    return FileResponse(
        target,
        media_type="application/zip",
        filename=safe,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/gate/{robot_id}")
async def deploy_gate(robot_id: str):
    """向导步骤 2：当前契约一致性快检（v3 vs v2）。

    真正的强校验在导出侧（训练快照 vs 当前契约，contract_snapshot 固化后自动收紧）；
    本端点供向导在导出前即时核对包内契约的层间一致性。
    """
    from backend.deploy_pack import _load_json
    from backend.export_gate import compare_contracts
    from backend.robot_presets import get_robot_preset

    preset = get_robot_preset(robot_id)
    root_value = str(((preset or {}).get("robot_package") or {}).get("package_root", ""))
    root = Path(root_value) if root_value else ROOT / "assets" / "robots" / robot_id
    if not root.exists():
        raise HTTPException(status_code=404, detail=f"robot package not found: {robot_id}")
    v3 = _load_json(root / "contract_v3.json") or {}
    v2 = _load_json(root / "contract.json") or {}
    return {"robot_id": robot_id, **compare_contracts(v3, v2)}
