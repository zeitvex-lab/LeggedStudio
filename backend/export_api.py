"""
Export API
ONNX 导出的 REST API
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path
import json

from adapters.mjlab_new.onnx_exporter import export_policy_to_onnx


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

        # 准备 normalizer
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


@router.post("/{task_id}/export-onnx")
async def export_task_to_onnx(task_id: str):
    """导出训练任务的模型为 ONNX"""
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

        # 导出 ONNX
        onnx_path = task.task_dir / "model_final.onnx"

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

        # 更新 Artifact
        import hashlib
        with open(onnx_path, 'rb') as f:
            onnx_hash = hashlib.sha256(f.read()).hexdigest()

        artifact.onnx_model_path = str(onnx_path)
        artifact.onnx_model_hash = onnx_hash
        artifact.onnx_validation = {
            "exported": True,
            "onnx_path": str(onnx_path),
            "max_numerical_diff": result.max_numerical_diff,
            "opset_version": result.opset_version,
            "input_shape": result.input_shape,
            "output_shape": result.output_shape,
            "inference_time_ms": result.inference_time_ms
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
