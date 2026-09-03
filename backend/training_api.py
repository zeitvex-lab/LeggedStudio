"""
Training API
训练任务管理的 REST API
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
import json

from backend.training_manager import get_training_manager
from contracts.robot_contract_v2 import RobotContractV2
from adapters.mjlab.env_factory import get_reward_terms
from adapters.mjlab.algorithms.registry import list_algorithms
from adapters.mjlab.recipe_registry import list_tasks, resolve_recipe
from backend.robot_packages import package_for_contract


router = APIRouter(prefix="/api/training", tags=["training"])


@router.get("/hardware")
async def training_hardware():
    """Report the runtime capabilities used by the training worker."""
    from adapters.mjlab.native_adapter import preflight
    native = preflight()
    interpreters = native.get("runtime", {}).get("interpreters", [])
    selected = next((item for item in interpreters if item.get("available")), {})
    cuda_count = int(selected.get("cuda_device_count", 0))
    result = {
        "python": selected.get("python"),
        "torch": {
            "available": bool(selected.get("available")),
            "version": selected.get("torch_version"),
            "cuda_available": bool(selected.get("cuda_available")),
            "cuda_version": None,
            "devices": [{"index": index} for index in range(cuda_count)] if selected.get("cuda_available") else [],
        },
    }
    result["native_mjlab"] = {
        **native,
        "dependencies_importable": bool(native.get("runtime", {}).get("available")),
    }
    result["supported_devices"] = ["auto", "cpu"] + (["cuda"] + [f"cuda:{i}" for i in range(cuda_count)] if result["torch"]["cuda_available"] else [])
    return result


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
    profile_id: str | None = None
    terrain_type: str = "plane"
    device: str = Field(default="auto", pattern=r"^(auto|cpu|cuda(?::\d+)?)$")
    reward_scales: dict[str, float] = Field(default_factory=dict)
    reward_overrides: bool = False
    reward_params: dict[str, dict] = Field(default_factory=dict)
    terrain: dict = Field(default_factory=dict)
    command_ranges: dict[str, list[float]] = Field(default_factory=dict)
    noise: dict = Field(default_factory=dict)
    curriculum: dict = Field(default_factory=dict)
    # Shared advanced fields. PPO ignores off-policy-only values; keeping one
    # request shape makes Web, CLI, and future adapters interchangeable.
    num_steps: int = Field(default=24, ge=4, le=4096)
    num_minibatches: int = Field(default=4, ge=1, le=64)
    gamma: float = Field(default=0.99, gt=0.0, lt=1.0)
    gae_lambda: float = Field(default=0.95, gt=0.0, le=1.0)
    clip_param: float = Field(default=0.2, gt=0.0, lt=1.0)
    entropy_coef: float = Field(default=0.01, ge=0.0)
    tau: float = Field(default=0.005, gt=0.0, le=1.0)
    batch_size: int = Field(default=256, ge=1, le=8192)
    replay_size: int = Field(default=100_000, ge=1024, le=10_000_000)
    alpha: float = Field(default=0.2, gt=0.0)
    policy_delay: int = Field(default=2, ge=1, le=16)
    exploration_noise: float = Field(default=0.1, ge=0.0, le=2.0)
    seed: int = Field(default=0, ge=0, le=2_147_483_647)
    backend: Literal["native_mjlab"] = "native_mjlab"


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


class CompareTrainingRequest(CreateTrainingRequest):
    algorithms: list[str] = Field(default_factory=lambda: ["PPO"], min_length=1, max_length=6)


# ========== API 端点 ==========

@router.post("/create")
async def create_training(request: CreateTrainingRequest):
    """
    创建新的训练任务

    启动独立进程进行训练
    """
    try:
        algorithm = request.algorithm.upper()
        available = {item["id"] for item in list_algorithms() if item.get("available")}
        if algorithm not in available:
            raise HTTPException(status_code=400, detail=f"算法 {request.algorithm} 不可用，目前可用算法：{', '.join(sorted(available))}")
        if algorithm != "PPO":
            raise HTTPException(status_code=501, detail="native MJLab currently exposes PPO training; native SAC/TD3 are not implemented")
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
            "algorithm": algorithm,
            "num_envs": request.num_envs,
            "max_iterations": request.max_iterations,
            "learning_rate": request.learning_rate,
            "save_interval": request.save_interval,
            "episode_length_s": request.episode_length_s,
            "task_name": request.task_name,
            "profile_id": request.profile_id,
            "terrain_type": request.terrain_type,
            "device": request.device,
            "reward_scales": request.reward_scales,
            "reward_overrides": request.reward_overrides,
            "reward_params": request.reward_params,
            "terrain": request.terrain,
            "command_ranges": request.command_ranges,
            "noise": request.noise,
            "curriculum": request.curriculum,
            "num_steps": request.num_steps,
            "num_minibatches": request.num_minibatches,
            "gamma": request.gamma,
            "gae_lambda": request.gae_lambda,
            "clip_param": request.clip_param,
            "entropy_coef": request.entropy_coef,
            "tau": request.tau,
            "batch_size": request.batch_size,
            "replay_size": request.replay_size,
            "alpha": request.alpha,
            "policy_delay": request.policy_delay,
            "exploration_noise": request.exploration_noise,
            "seed": request.seed,
            "backend": request.backend,
        }
        try:
            resolved_recipe = resolve_recipe(config)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        config["resolved_recipe"] = resolved_recipe.model_dump(mode="json")
        if request.backend == "native_mjlab":
            config["mode"] = "train"
            package = package_for_contract(contract.model_dump(mode="json"))
            config["robot_package"] = package
            config["generic_task"] = True
            from adapters.mjlab.native_adapter import DEFAULT_EXTENSION, preflight
            native = preflight()
            if not native["exists"] or not native["manager_env_available"] or not native.get("runtime", {}).get("available"):
                raise HTTPException(status_code=501, detail={"message": "native MJLab adapter is not ready", "preflight": native})
            if not native.get("execution_ready"):
                raise HTTPException(status_code=501, detail={"message": native.get("execution_note", "native MJLab task adapter is not ready"), "preflight": native})

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


@router.post("/compare")
async def create_comparison(request: CompareTrainingRequest):
    """Create a comparable matrix of runs sharing one contract and recipe."""
    algorithms = [str(item).upper() for item in request.algorithms]
    if len(set(algorithms)) != len(algorithms):
        raise HTTPException(status_code=400, detail="algorithms must be unique")
    tasks = []
    for algorithm in algorithms:
        single = request.model_copy(update={"algorithm": algorithm})
        result = await create_training(single)
        tasks.append({"algorithm": algorithm, "task_id": result["task_id"]})
    return {"success": True, "count": len(tasks), "tasks": tasks, "session_config": request.model_dump(mode="json")}


@router.get("/options")
async def training_options():
    return {
        "algorithms": list_algorithms(),
        "reward_terms": get_reward_terms(),
        "tasks": list_tasks(),
        "hardware": await training_hardware(),
    }


@router.post("/resolve-recipe")
async def resolve_training_recipe(config: dict):
    """Validate and return the canonical recipe consumed by workers."""
    try:
        recipe = resolve_recipe(config)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"valid": True, "recipe": recipe.model_dump(mode="json")}


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
    except HTTPException:
        raise
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
    except HTTPException:
        raise
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

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}/metrics")
async def get_training_metrics(task_id: str):
    """Return the append-only metric series for plotting and comparisons."""
    task = get_training_manager().get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    metrics_file = task.task_dir / "metrics.jsonl"
    rows = []
    if metrics_file.exists():
        for line in metrics_file.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if not rows:
        progress = task.get_progress()
        if progress:
            rows.append(progress)
    return {"success": True, "task_id": task_id, "metrics": rows}


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

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
