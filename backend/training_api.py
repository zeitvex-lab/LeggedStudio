"""
Training API
训练任务管理的 REST API
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional

from backend.training_manager import get_training_manager
from contracts.robot_contract_v2 import RobotContractV2
from adapters.mjlab_new.env_factory import get_reward_terms


router = APIRouter(prefix="/api/training", tags=["training"])


# ========== 请求/响应模型 ==========

class CreateTrainingRequest(BaseModel):
    """创建训练请求"""
    contract: dict  # Robot Contract JSON
    algorithm: str = "PPO"
    num_envs: int = 4096
    max_iterations: int = 1000
    learning_rate: float = 3e-4
    save_interval: int = 100
    episode_length_s: float = 20.0
    task_name: str = "forward_walk"
    terrain_type: str = "plane"
    device: str = "auto"
    reward_scales: dict[str, float] = Field(default_factory=dict)


class TrainingStatusResponse(BaseModel):
    """训练状态响应"""
    task_id: str
    contract_id: str
    robot: str
    algorithm: str
    status: str
    progress: float
    created_at: str
    current_iteration: int
    max_iterations: int
    reward: float


# ========== API 端点 ==========

@router.post("/create")
async def create_training(request: CreateTrainingRequest):
    """
    创建新的训练任务

    启动独立进程进行训练
    """
    try:
        if request.algorithm != "PPO":
            raise HTTPException(status_code=400, detail=f"算法 {request.algorithm} 尚未接入真实训练，目前可用算法：PPO")
        # 解析 Contract
        contract = RobotContractV2(**request.contract)

        # 验证 Contract
        from contracts.validator import validate_contract
        validation = validate_contract(contract)
        if not validation.valid:
            errors = [e.message for e in validation.errors]
            raise HTTPException(
                status_code=400,
                detail=f"Invalid contract: {', '.join(errors)}"
            )

        # 准备配置
        config = {
            "algorithm": request.algorithm,
            "num_envs": request.num_envs,
            "max_iterations": request.max_iterations,
            "learning_rate": request.learning_rate,
            "save_interval": request.save_interval,
            "episode_length_s": request.episode_length_s,
            "task_name": request.task_name,
            "terrain_type": request.terrain_type,
            "device": request.device,
            "reward_scales": request.reward_scales,
        }

        # 创建任务
        manager = get_training_manager()
        task_id = manager.create_task(
            contract=contract,
            config=config
        )

        return {
            "success": True,
            "task_id": task_id,
            "message": "Training task created successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/options")
async def training_options():
    return {
        "algorithms": [{"id": "PPO", "label": "PPO", "available": True}, {"id": "SAC", "label": "SAC", "available": False}, {"id": "TD3", "label": "TD3", "available": False}],
        "reward_terms": get_reward_terms(),
        "tasks": ["forward_walk", "trot", "rough_terrain"],
    }


@router.get("/list")
async def list_trainings():
    """列出所有训练任务"""
    manager = get_training_manager()
    tasks = manager.list_tasks()

    return {
        "success": True,
        "tasks": tasks,
        "count": len(tasks)
    }


@router.get("/{task_id}/status")
async def get_training_status(task_id: str):
    """获取训练任务状态"""
    try:
        manager = get_training_manager()
        status = manager.get_task_status(task_id)

        return {
            "success": True,
            "status": status
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/stop")
async def stop_training(task_id: str):
    """停止训练任务"""
    try:
        manager = get_training_manager()
        manager.stop_task(task_id)

        return {
            "success": True,
            "message": f"Training task {task_id} stopped"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{task_id}")
async def delete_training(task_id: str):
    """删除训练任务"""
    try:
        manager = get_training_manager()
        manager.delete_task(task_id)

        return {
            "success": True,
            "message": f"Training task {task_id} deleted"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}/logs")
async def get_training_logs(task_id: str, lines: int = 100):
    """获取训练日志"""
    try:
        manager = get_training_manager()
        task = manager.get_task(task_id)

        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        log_file = task.task_dir / "training.log"

        if not log_file.exists():
            return {
                "success": True,
                "logs": []
            }

        # 读取最后 N 行
        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines

        return {
            "success": True,
            "logs": [line.strip() for line in recent_lines],
            "total_lines": len(all_lines)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}/artifact")
async def get_training_artifact(task_id: str):
    """获取训练产物（Artifact）"""
    try:
        manager = get_training_manager()
        task = manager.get_task(task_id)

        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        artifact_file = task.task_dir / "artifact.json"

        if not artifact_file.exists():
            return {
                "success": False,
                "message": "Artifact not found (training may not be completed)"
            }

        # 读取 Artifact
        from contracts.policy_artifact import PolicyArtifact
        artifact = PolicyArtifact.from_json_file(str(artifact_file))

        return {
            "success": True,
            "artifact": artifact.model_dump()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
