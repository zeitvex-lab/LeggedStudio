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
    """列出预训练模型。

    首选 ``pretrained_models/index.json``（训练脚本产物）；**缺失时回落到各包
    ``simulation/config.json`` 的 policies/demo_policies 扫描**——与
    ``/api/health/demo-cards`` 同源、数据驱动，避免"索引文件不存在 => 首页 demo
    卡为空"这种静默失败。
    """
    try:
        index_file = PRETRAINED_DIR / "index.json"

        if index_file.exists():
            models = json.loads(index_file.read_text(encoding="utf-8-sig"))
            return {
                "success": True,
                "models": models,
                "count": len(models),
                "source": "index",
            }

        from backend.health_api import demo_cards

        cards = (await demo_cards()).get("cards", [])
        models = [
            {
                "id": f"{card.get('robot_id')}--{card.get('id')}",
                "name": card.get("label") or card.get("id"),
                "robot": card.get("robot_id"),
                "family": card.get("family"),
                "algorithm": "pretrained",
                "path": card.get("url"),
                "play_url": card.get("play_url"),
                "obs_dim": card.get("obs_dim"),
                "action_dim": card.get("action_dim"),
            }
            for card in cards
        ]
        return {
            "success": True,
            "models": models,
            "count": len(models),
            "source": "package-scan",
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

        models = json.loads(index_file.read_text(encoding="utf-8-sig"))

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

        models = json.loads(index_file.read_text(encoding="utf-8-sig"))

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
    """运行预训练模型演示。

    **501 未实现，如实说**：此端点曾返回用索引 ``avg_reward`` 合成的假 episode
    （"临时：模拟结果"）——本仓的原则是"没有评估报告就不算通过"，返回编造数比
    404 更坏（404 让人去找原因，假 200 让人相信不存在的 rollout）。真实现需要
    加载模型 + 创建环境 + 跑 episode，那是评测矩阵（`/api/evaluation/run`）的职责，
    不该在这里造一份低保真副本。前端无消费方（旧 dashboard.js 明确"不造假卡"，该页已删除）。
    """
    index_file = PRETRAINED_DIR / "index.json"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="No pretrained models found")
    models = json.loads(index_file.read_text(encoding="utf-8-sig"))
    if not any(m.get("id") == model_id for m in models):
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    raise HTTPException(
        status_code=501,
        detail=(
            "预训练模型演示未实现：跑真实 rollout 属于评测矩阵（POST /api/evaluation/run），"
            "本端点不再返回编造的 episode 数据"
        ),
    )


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
