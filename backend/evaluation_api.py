"""Native MJLab policy evaluation API for completed training runs."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])


class EvaluationRequest(BaseModel):
    task_id: str
    episodes: int = Field(default=5, ge=1, le=100)
    max_steps: int | None = Field(default=None, ge=1, le=10000)


def _task(task_id: str):
    from backend.training_manager import get_training_manager

    manager = get_training_manager()
    task = manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task


@router.get("/list")
async def list_evaluable_tasks():
    from backend.training_manager import get_training_manager

    manager = get_training_manager()
    items = []
    for task in manager.tasks.values():
        artifact_path = task.task_dir / "artifact.json"
        model_path = task.task_dir / "model_final.pt"
        if artifact_path.exists() and model_path.exists() and model_path.stat().st_size > 1024:
            items.append({"task_id": task.task_id, "robot": task.contract.family, "status": task.to_dict()["status"], "artifact_path": str(artifact_path)})
    return {"count": len(items), "tasks": items}


@router.post("/run")
async def run_evaluation(request: EvaluationRequest):
    task = _task(request.task_id)
    if task.config.get("backend", "native_mjlab") != "native_mjlab":
        raise HTTPException(status_code=400, detail="Training task is not a native MJLab task")
    return await _run_native_evaluation(task, request)


async def _run_native_evaluation(task, request: EvaluationRequest):
    """Evaluate an RSL-RL native checkpoint in the isolated MJLab worker."""
    from adapters.mjlab.launcher import TrainingLauncher
    from adapters.mjlab.native_adapter import DEFAULT_SOURCE

    artifact_path = task.task_dir / "artifact.json"
    checkpoints = sorted(task.task_dir.glob("model_*.pt"))
    if not artifact_path.exists() or not checkpoints:
        raise HTTPException(status_code=400, detail="Native artifact or checkpoint is not ready")
    config = dict(task.config)
    config.update({"mode": "evaluate", "episodes": request.episodes, "max_steps": request.max_steps or 500, "checkpoint": str(checkpoints[-1].resolve()), "generic_task": True})
    config_path = task.task_dir / "native_evaluation_config.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    launcher = TrainingLauncher(workspace_dir=str(task.task_dir.parent))
    try:
        python_exe = launcher._select_python(config)
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    worker = Path(__file__).resolve().parents[1] / "adapters" / "mjlab" / "native_worker.py"
    cmd = [str(python_exe), str(worker), "--source", str(DEFAULT_SOURCE), "--config", str(config_path), "--output", str(task.task_dir)]
    result = subprocess.run(cmd, cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=300)
    evaluation_file = task.task_dir / "evaluation.json"
    if result.returncode != 0 or not evaluation_file.exists():
        detail = result.stderr.strip()[-2000:] or result.stdout.strip()[-2000:] or f"native evaluation exited with code {result.returncode}"
        raise HTTPException(status_code=500, detail=detail)
    return {"success": True, "result": json.loads(evaluation_file.read_text(encoding="utf-8-sig"))}

# --------------------------------------------------------------------------------------
# B11 评测矩阵（八指标 + 四档）：与训练侧 evaluation 分开，走包内策略（含训练产物）
# --------------------------------------------------------------------------------------
class QualityRequest(BaseModel):
    package_dir: str = Field(description="机器人包目录（仓库相对路径或绝对路径）")
    policy_id: str | None = Field(default=None, description="包内策略 id（走统一解析器）")
    policy: str | None = Field(default=None, description="策略 onnx（包内相对/绝对；与 policy_id 二选一）")
    tier: str = Field(default="single", description="single / multi / level / stress")
    cmd: str = "0.4,0,0"
    steps: int = Field(default=200, ge=1, le=5000)
    quality_min: float = Field(default=0.5, ge=0.0, le=1.0)
    # level 档的难度幅值序列（前端会传；缺了会被静默忽略，档位就跑成默认值 —— 那是"看起来跑了"）
    magnitudes: str = Field(default="0.5,0.75,1.0", description="level 档的幅值序列（逗号分隔）")
    repeats: int = Field(default=1, ge=1, le=20, description="stress 档每条件重跑次数")
    save: bool = Field(default=True, description="把报告落到 <workspace>/evaluation/")


@router.get("/quality/list")
async def list_quality_reports():
    """已有的质量报告（磁盘上的报告才是放行依据，不是内存里的一次结论）。"""

    from backend import quality_matrix

    reports = quality_matrix.list_reports()
    return {"count": len(reports), "reports": reports}


@router.post("/quality/run")
async def run_quality_report(request: QualityRequest):
    """跑一档评测（需适配器 venv 里的 mujoco；缺环境报 501，不静默退回跑不了的解释器）。"""

    import asyncio

    from backend import quality_matrix
    from backend.adapter_runtime import AdapterUnavailable

    try:
        report = await asyncio.to_thread(
            quality_matrix.run_quality,
            package_dir=request.package_dir,
            tier=request.tier,
            policy_id=request.policy_id,
            policy=request.policy,
            cmd=request.cmd,
            steps=request.steps,
            quality_min=request.quality_min,
            magnitudes=request.magnitudes,
            repeats=request.repeats,
        )
    except AdapterUnavailable as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    saved = quality_matrix.save_report(report) if request.save else None
    verdict = quality_matrix.gate(report, min_score=request.quality_min)
    return {
        "success": True,
        "report": report,
        "verdict": verdict,
        "report_path": str(saved) if saved else None,
    }
