"""
Export API
ONNX 导出的 REST API
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path
from contracts.validator import normalized_sha256  # 归一摘要唯一实现
import json

from backend.export_gate import check_export_result, compare_contracts


router = APIRouter(prefix="/api/export", tags=["export"])


# ========== 请求/响应模型 ==========

class ExportONNXRequest(BaseModel):
    """导出 ONNX 请求"""
    model_path: str  # PyTorch 模型路径
    output_path: str  # ONNX 输出路径
    obs_dim: int
    act_dim: int
    include_normalizer: bool = False
    obs_mean: list = None
    obs_std: list = None


# ========== API 端点 ==========

@router.post("/onnx")
async def export_to_onnx(request: ExportONNXRequest):
    """
    导出 PyTorch 模型为 ONNX

    执行导出并验证数值一致性
    """
    try:
        # 检查模型文件存在
        if not Path(request.model_path).exists():
            raise HTTPException(
                status_code=404,
                detail=f"Model file not found: {request.model_path}"
            )

        # 准备 normalizer（懒加载：控制面不导入训练栈，torch 链仅在导出时引入）
        from adapters.mjlab.onnx_exporter import export_policy_to_onnx
        import numpy as np
        obs_mean = np.array(request.obs_mean) if request.obs_mean else None
        obs_std = np.array(request.obs_std) if request.obs_std else None

        # 导出
        result = export_policy_to_onnx(
            model_path=request.model_path,
            onnx_output_path=request.output_path,
            obs_dim=request.obs_dim,
            act_dim=request.act_dim,
            obs_mean=obs_mean if request.include_normalizer else None,
            obs_std=obs_std if request.include_normalizer else None
        )

        if not result.success:
            raise HTTPException(
                status_code=500,
                detail=f"Export failed: {result.error_message}"
            )

        return {
            "success": True,
            "onnx_path": result.onnx_path,
            "max_numerical_diff": result.max_numerical_diff,
            "inference_time_ms": result.inference_time_ms,
            "input_shape": result.input_shape,
            "output_shape": result.output_shape,
            "opset_version": result.opset_version
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}/download")
async def download_onnx(task_id: str):
    """下载训练任务的 ONNX 模型"""
    try:
        from backend.training_manager import get_training_manager

        manager = get_training_manager()
        task = manager.get_task(task_id)

        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        # 查找 ONNX 文件
        onnx_file = task.task_dir / "model_final.onnx"

        if not onnx_file.exists():
            # 尝试从 Artifact 读取路径
            artifact_file = task.task_dir / "artifact.json"
            if artifact_file.exists():
                with open(artifact_file, 'r') as f:
                    artifact = json.load(f)
                    if artifact.get('onnx_model_path'):
                        onnx_file = Path(artifact['onnx_model_path'])

        if not onnx_file.exists():
            raise HTTPException(
                status_code=404,
                detail="ONNX model not found (may not be exported yet)"
            )

        return FileResponse(
            path=str(onnx_file),
            filename=f"{task_id}.onnx",
            media_type="application/octet-stream"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _training_snapshot_from_task(task) -> dict:
    """训练侧契约快照：优先 create_task 固化的 contract_snapshot.json（v3 全量，
    DENYLIST 强校验）；缺省退化为 v1 契约字段映射（部分字段降级为 warning）。"""

    snapshot_path = task.task_dir / "contract_snapshot.json"
    if snapshot_path.exists():
        try:
            return json.loads(snapshot_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            pass
    contract = task.contract
    joints = getattr(contract, "joints", None)
    observation = getattr(contract, "observation", None)
    dimension = getattr(observation, "dimension", None) if observation is not None else None
    return {
        "action": {
            "joint_order": list(getattr(joints, "canonical_order", []) or []),
            "action_scale": getattr(contract, "action_scale", None),
        },
        "observation": {"dimension": dimension},
        "control": {
            "control_hz": getattr(contract, "control_hz", None),
            "physics_hz": getattr(contract, "physics_hz", None),
        },
    }


def _current_contract_for(robot_id: str) -> dict:
    """包当前契约：优先 contract.json，回落 contract_legacy_v2.json。"""

    from backend.robot_presets import get_robot_preset

    preset = get_robot_preset(robot_id)
    root = Path(str(((preset or {}).get("robot_package") or {}).get("package_root", ""))) if preset else None
    if root is None:
        return {}
    for name in ("contract.json", "contract_legacy_v2.json"):
        path = root / name
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                continue
    return {}


@router.post("/gate-check")
async def gate_check(training_snapshot: dict, current_contract: dict):
    """DENYLIST 契约一致性检查（M4 部署向导步骤 2 的数据源）。"""
    return compare_contracts(training_snapshot, current_contract)


@router.post("/{task_id}/export-onnx")
async def export_task_to_onnx(task_id: str):
    """导出训练任务的模型为 ONNX（双 gate：契约 DENYLIST + 形状/数值）"""
    try:
        from backend.training_manager import get_training_manager
        from contracts.policy_artifact import PolicyArtifact

        manager = get_training_manager()
        task = manager.get_task(task_id)

        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        # 读取 Artifact
        artifact_file = task.task_dir / "artifact.json"
        if not artifact_file.exists():
            raise HTTPException(
                status_code=400,
                detail="Training not completed or artifact not found"
            )

        artifact = PolicyArtifact.from_json_file(str(artifact_file))

        # gate A：契约 DENYLIST（训练快照 vs 当前包契约，不一致即拒绝）
        snapshot = _training_snapshot_from_task(task)
        gate_report = compare_contracts(snapshot, _current_contract_for(str(getattr(task.contract, "robot_id", ""))))
        if not gate_report["ok"]:
            raise HTTPException(
                status_code=422,
                detail={"message": "导出被 DENYLIST gate 拒绝", "gate": gate_report},
            )

        # 导出 ONNX（懒加载：控制面不导入训练栈，torch 链仅在导出时引入）
        onnx_path = task.task_dir / "model_final.onnx"

        from adapters.mjlab.onnx_exporter import export_policy_to_onnx
        import numpy as np
        result = export_policy_to_onnx(
            model_path=artifact.pytorch_model_path,
            onnx_output_path=str(onnx_path),
            obs_dim=task.contract.observation.dimension,
            act_dim=task.contract.action.dimension,
            obs_mean=np.array(artifact.obs_normalizer.get('mean', [])) if artifact.obs_normalizer else None,
            obs_std=np.array(artifact.obs_normalizer.get('std', [])) if artifact.obs_normalizer else None
        )

        if not result.success:
            raise HTTPException(
                status_code=500,
                detail=f"Export failed: {result.error_message}"
            )

        # gate B：dummy forward 形状 + 数值回放（<1e-5），不过即删除产物（fail-closed）
        shape_gate = check_export_result(
            result, task.contract.observation.dimension, task.contract.action.dimension
        )
        if not shape_gate["ok"]:
            Path(onnx_path).unlink(missing_ok=True)
            raise HTTPException(
                status_code=422,
                detail={"message": "导出被形状/数值 gate 拒绝（产物已删除）", "gate": shape_gate},
            )

        # 更新 Artifact：产物哈希用归一摘要（与 policy_artifacts 的 onnx_sha256 同口径）
        onnx_hash = normalized_sha256(Path(onnx_path).read_bytes())

        artifact.onnx_model_path = str(onnx_path)
        artifact.onnx_model_hash = onnx_hash
        artifact.onnx_validation = {
            "exported": True,
            "onnx_path": str(onnx_path),
            "max_numerical_diff": result.max_numerical_diff,
            "opset_version": result.opset_version,
            "input_shape": result.input_shape,
            "output_shape": result.output_shape,
            "inference_time_ms": result.inference_time_ms,
            "gate": {"contract": gate_report, "shape_numeric": shape_gate},
        }

        # 保存更新的 Artifact
        artifact.to_json_file(str(artifact_file))

        return {
            "success": True,
            "onnx_path": str(onnx_path),
            "validation": artifact.onnx_validation
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_exports():
    """列出所有导出的 ONNX 模型"""
    try:
        from backend.training_manager import get_training_manager

        manager = get_training_manager()
        tasks = manager.list_tasks()

        exports = []
        for task_dict in tasks:
            task = manager.get_task(task_dict['task_id'])
            if task:
                onnx_file = task.task_dir / "model_final.onnx"
                if onnx_file.exists():
                    exports.append({
                        "task_id": task.task_id,
                        "robot": task.contract.family,
                        "onnx_path": str(onnx_file),
                        "size_mb": onnx_file.stat().st_size / (1024 * 1024)
                    })

        return {
            "success": True,
            "exports": exports,
            "count": len(exports)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
