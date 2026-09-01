"""
训练流水线 API 端点
集成到后端 API
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from pathlib import Path
from typing import Optional, Dict
import json
import uuid
import os

# 添加路径
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pipeline.train_pipeline import Pipeline


router = APIRouter(prefix="/api/pipeline", tags=["训练流水线"])


# ============================================================================
# 数据模型
# ============================================================================

class ContractValidateRequest(BaseModel):
    """Contract 验证请求"""
    contract_path: str


class TrainRequest(BaseModel):
    """训练请求"""
    contract_path: str
    num_envs: int = 64
    max_iterations: int = 1000
    work_dir: Optional[str] = None


class PipelineStatus(BaseModel):
    """流水线状态"""
    pipeline_id: str
    status: str  # pending | running | completed | failed
    current_step: Optional[str] = None
    progress: float = 0.0
    results: Optional[Dict] = None


# ============================================================================
# 全局状态
# ============================================================================

# 流水线实例缓存
pipelines: Dict[str, Pipeline] = {}
pipeline_status: Dict[str, PipelineStatus] = {}


# ============================================================================
# 端点
# ============================================================================

@router.post("/validate-contract")
async def validate_contract(request: ContractValidateRequest):
    """
    验证 Contract

    步骤 1：加载并验证 Contract JSON
    """
    contract_path = Path(request.contract_path)

    if not contract_path.exists():
        raise HTTPException(status_code=404, detail=f"Contract 文件不存在: {contract_path}")

    try:
        # 加载 Contract
        with open(contract_path) as f:
            contract_data = json.load(f)

        # Pydantic 验证
        from contracts.models import RobotContract
        validated = RobotContract(**contract_data)

        return {
            "valid": True,
            "robot_id": validated.robot_id,
            "schema_version": validated.schema_version,
            "actuated_joints": len(validated.actuated_joint_names),
            "control_hz": validated.control_hz,
            "physics_hz": validated.physics_hz
        }

    except Exception as e:
        return {
            "valid": False,
            "error": str(e)
        }


@router.post("/start-training")
async def start_training(request: TrainRequest, background_tasks: BackgroundTasks):
    """
    启动训练流水线

    步骤：
    1. 验证 Contract
    2. 生成训练配置
    3. 启动训练（后台）
    4. 评估模型
    5. Sim2Sim 测试
    """
    # 生成 pipeline ID
    pipeline_id = str(uuid.uuid4())[:8]

    # 工作目录
    if request.work_dir:
        work_dir = Path(request.work_dir)
    else:
        work_dir = Path(os.environ.get("LEGGED_STUDIO_OUTPUT", Path(__file__).parent.parent.parent / "pipeline_output")) / pipeline_id

    # 创建流水线
    pipeline = Pipeline(work_dir=work_dir)
    pipelines[pipeline_id] = pipeline

    # 初始状态
    pipeline_status[pipeline_id] = PipelineStatus(
        pipeline_id=pipeline_id,
        status="pending",
        current_step="initializing",
        progress=0.0
    )

    # 后台任务
    def run_pipeline():
        try:
            pipeline_status[pipeline_id].status = "running"
            pipeline_status[pipeline_id].current_step = "validate_contract"
            pipeline_status[pipeline_id].progress = 0.1

            # 步骤 1：验证
            if not pipeline.validate_contract(request.contract_path):
                raise RuntimeError("Contract 验证失败")

            pipeline_status[pipeline_id].progress = 0.2

            # 步骤 2：生成配置
            pipeline_status[pipeline_id].current_step = "generate_config"
            pipeline.generate_train_config()
            pipeline_status[pipeline_id].progress = 0.3

            # 步骤 3：训练
            pipeline_status[pipeline_id].current_step = "training"
            if not pipeline.run_training(
                num_envs=request.num_envs,
                max_iterations=request.max_iterations
            ):
                raise RuntimeError("训练失败")

            pipeline_status[pipeline_id].progress = 0.7

            # 步骤 4：评估
            pipeline_status[pipeline_id].current_step = "evaluation"
            results = pipeline.evaluate()
            pipeline_status[pipeline_id].progress = 0.9

            # 步骤 5：Sim2Sim
            pipeline_status[pipeline_id].current_step = "sim2sim"
            pipeline.sim2sim_transfer()

            # 完成
            pipeline_status[pipeline_id].status = "completed"
            pipeline_status[pipeline_id].current_step = "done"
            pipeline_status[pipeline_id].progress = 1.0
            pipeline_status[pipeline_id].results = results

        except Exception as e:
            pipeline_status[pipeline_id].status = "failed"
            pipeline_status[pipeline_id].results = {"error": str(e)}

    # 添加后台任务
    background_tasks.add_task(run_pipeline)

    return {
        "pipeline_id": pipeline_id,
        "status": "started",
        "work_dir": str(work_dir),
        "message": "训练流水线已启动（后台运行）"
    }


@router.get("/status/{pipeline_id}")
async def get_pipeline_status(pipeline_id: str):
    """
    获取流水线状态
    """
    if pipeline_id not in pipeline_status:
        raise HTTPException(status_code=404, detail=f"Pipeline {pipeline_id} 不存在")

    return pipeline_status[pipeline_id]


@router.get("/results/{pipeline_id}")
async def get_pipeline_results(pipeline_id: str):
    """
    获取流水线结果
    """
    if pipeline_id not in pipeline_status:
        raise HTTPException(status_code=404, detail=f"Pipeline {pipeline_id} 不存在")

    status = pipeline_status[pipeline_id]

    if status.status != "completed":
        raise HTTPException(status_code=400, detail=f"Pipeline 尚未完成（状态: {status.status}）")

    pipeline = pipelines[pipeline_id]

    # 读取结果文件
    results = {}

    if pipeline.checkpoint_path:
        results["checkpoint"] = str(pipeline.checkpoint_path)

    eval_results_path = pipeline.work_dir / "eval_results.json"
    if eval_results_path.exists():
        with open(eval_results_path) as f:
            results["evaluation"] = json.load(f)

    sim2sim_results_path = pipeline.work_dir / "sim2sim_results.json"
    if sim2sim_results_path.exists():
        with open(sim2sim_results_path) as f:
            results["sim2sim"] = json.load(f)

    return results


@router.get("/list")
async def list_pipelines():
    """
    列出所有流水线
    """
    return {
        "count": len(pipeline_status),
        "pipelines": [
            {
                "pipeline_id": pid,
                "status": status.status,
                "progress": status.progress
            }
            for pid, status in pipeline_status.items()
        ]
    }


@router.post("/run-example")
async def run_example_pipeline(background_tasks: BackgroundTasks):
    """
    运行示例流水线（Go2）

    快速测试完整流程
    """
    examples_dir = Path(__file__).parent.parent.parent / "examples"
    contract_path = examples_dir / "go2_example_contract.json"

    if not contract_path.exists():
        raise HTTPException(status_code=404, detail="示例 Contract 不存在")

    request = TrainRequest(
        contract_path=str(contract_path),
        num_envs=64,
        max_iterations=100  # 示例用较少迭代
    )

    return await start_training(request, background_tasks)
