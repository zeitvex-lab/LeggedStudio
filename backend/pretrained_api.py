"""
Pretrained Models API
预训练模型管理的 REST API
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from typing import List, Optional
import json

router = APIRouter(prefix="/api/pretrained", tags=["pretrained"])

PRETRAINED_DIR = Path("pretrained_models")


@router.get("/list")
async def list_pretrained_models():
    """列出所有预训练模型"""
    try:
        index_file = PRETRAINED_DIR / "index.json"

        if not index_file.exists():
            return {
                "success": True,
                "models": [],
                "count": 0,
                "message": "No pretrained models found. Run generate_pretrained_models.py first."
            }

        with open(index_file, 'r') as f:
            models = json.load(f)

        return {
            "success": True,
            "models": models,
            "count": len(models)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{model_id}")
async def get_pretrained_model(model_id: str):
    """获取预训练模型详情"""
    try:
        # 查找模型
        index_file = PRETRAINED_DIR / "index.json"

        if not index_file.exists():
            raise HTTPException(status_code=404, detail="No pretrained models found")

        with open(index_file, 'r') as f:
            models = json.load(f)

        model = next((m for m in models if m['id'] == model_id), None)

        if not model:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

        # 读取完整 Artifact
        artifact_path = Path(model['path']) / "artifact.json"

        if not artifact_path.exists():
            raise HTTPException(status_code=404, detail="Artifact not found")

        from contracts.policy_artifact import PolicyArtifact
        artifact = PolicyArtifact.from_json_file(str(artifact_path))

        return {
            "success": True,
            "model": model,
            "artifact": artifact.model_dump()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{model_id}/download")
async def download_pretrained_model(model_id: str, format: str = "pytorch"):
    """下载预训练模型"""
    try:
        # 查找模型
        index_file = PRETRAINED_DIR / "index.json"

        if not index_file.exists():
            raise HTTPException(status_code=404, detail="No pretrained models found")

        with open(index_file, 'r') as f:
            models = json.load(f)

        model = next((m for m in models if m['id'] == model_id), None)

        if not model:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

        model_dir = Path(model['path'])

        # 根据格式选择文件
        if format == "pytorch":
            model_file = model_dir / "model_final.pt"
        elif format == "onnx":
            model_file = model_dir / "model_final.onnx"
        else:
            raise HTTPException(status_code=400, detail=f"Invalid format: {format}")

        if not model_file.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Model file not found: {format}"
            )

        return FileResponse(
            path=str(model_file),
            filename=f"{model_id}.{format}",
            media_type="application/octet-stream"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{model_id}/demo")
async def run_pretrained_demo(model_id: str, num_episodes: int = 5):
    """运行预训练模型演示"""
    try:
        # 加载模型
        index_file = PRETRAINED_DIR / "index.json"

        if not index_file.exists():
            raise HTTPException(status_code=404, detail="No pretrained models found")

        with open(index_file, 'r') as f:
            models = json.load(f)

        model = next((m for m in models if m['id'] == model_id), None)

        if not model:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

        # TODO: 实际运行演示
        # 需要加载模型、创建环境、运行 episode

        # 临时：模拟结果
        demo_results = {
            "model_id": model_id,
            "num_episodes": num_episodes,
            "avg_reward": model['avg_reward'],
            "success_rate": model['success_rate'],
            "episodes": [
                {
                    "episode": i,
                    "reward": model['avg_reward'] + (i - num_episodes/2) * 5,
                    "success": True
                }
                for i in range(num_episodes)
            ]
        }

        return {
            "success": True,
            "demo_results": demo_results
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate")
async def generate_pretrained_models():
    """生成预训练模型（触发生成脚本）"""
    try:
        import subprocess

        # 启动生成脚本
        script_path = Path(__file__).parent.parent.parent / "scripts" / "generate_pretrained_models.py"

        if not script_path.exists():
            raise HTTPException(
                status_code=404,
                detail="Generate script not found"
            )

        # 后台运行
        process = subprocess.Popen(
            ["python", str(script_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        return {
            "success": True,
            "message": "Pretrained models generation started",
            "pid": process.pid
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
