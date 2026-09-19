"""BACKEND.TRAINING.monitor

拆分自 backend/training_api.py（原 god file，~960 行）的独立子模块。
保持原有路由路径与响应结构不变，仅供 backend/training_api 聚合。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from typing import Any, List, Optional, Literal
from datetime import datetime
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile

from backend.training_config_helpers import (  # noqa: F401
    _terrain_mixes, _observation_summary, _terminations_summary,
    _domain_randomization, _schema_workspace, _schema_cache_path,
    _schema_interpreter, _read_profile_mtime, _dump_schema_via_worker,
)
from backend.training_manager import get_training_manager
from backend.robot_presets import get_robot_preset
from backend.robot_packages import package_for_contract
from contracts.contract_legacy_v2 import ContractLegacyV2
from adapters.mjlab.env_factory import get_reward_terms
from adapters.mjlab.algorithms.registry import list_algorithms
from adapters.mjlab.recipe_registry import list_tasks, resolve_recipe
from adapters.backend_adapter import list_backend_descriptors


router = APIRouter(prefix="/api/training", tags=["training"])



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

@router.get("/{task_id}/terms")
async def get_training_term_series(task_id: str):
    """分项奖励/指标曲线（T2.2）：解析任务目录 TB events，按四层分组着色。

    total 上涨可能只是 penalty 在降——分项曲线按 Tracking/Regularization/
    Style/Contact 着色是 reward hacking 可见性的唯一解（报告 1 §4）。
    """
    task = get_training_manager().get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    from adapters.mjlab.reward_layers import get_reward_layer
    from backend.tb_events import parse_events_file

    series: dict[str, list] = {}
    for path in sorted(task.task_dir.glob("events.out.tfevents*")):
        try:
            for tag, points in parse_events_file(path).items():
                series.setdefault(tag, []).extend(points)
        except OSError:
            continue
    for tag in series:
        series[tag].sort(key=lambda item: item[0])
    layers = {tag: get_reward_layer(tag.rsplit("/", 1)[-1].removeprefix("rew_")) for tag in series}
    return {"success": True, "task_id": task_id, "terms": series, "layers": layers}

@router.get("/{task_id}/health")
async def get_training_health(task_id: str):
    """五大健康仪表盘 + 中文症状路由卡（T2.2，知识库 Ch25 蓝本）。

    F6 追加告警：指标序列 NaN/±Inf 由 build_health_report 产出，此处再扫描
    training.log 尾部的 OOM 记录并追加进 alerts（只报日志里出现过的事实）。
    """
    task = get_training_manager().get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    from backend.health_cards import build_health_report, scan_oom_alerts

    rows = []
    metrics_file = task.task_dir / "metrics.jsonl"
    if metrics_file.exists():
        for line in metrics_file.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    report = build_health_report(rows)
    report["alerts"] = [*report["alerts"], *scan_oom_alerts(task.task_dir / "training.log")]
    return {"success": True, "task_id": task_id, **report}

@router.get("/{task_id}/checkpoints")
async def get_training_checkpoints(task_id: str):
    """List checkpoint files and exported artifacts produced by the training worker.

    Purely additive read-only inventory over the task directory so the monitor
    page can render checkpoints, ONNX exports and TensorBoard event files.
    """
    task = get_training_manager().get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    def _entry(path: Path) -> dict:
        stat = path.stat()
        return {
            "name": path.name,
            "path": str(path),
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        }

    checkpoints: list[dict] = []
    exports: list[dict] = []
    event_files: list[dict] = []
    if task.task_dir.exists():
        for path in task.task_dir.iterdir():
            try:
                if not path.is_file():
                    continue
                if path.suffix == ".pt" and path.stem.startswith("model_"):
                    entry = _entry(path)
                    digits = path.stem.removeprefix("model_")
                    entry["iteration"] = int(digits) if digits.isdigit() else None
                    entry["final"] = path.name == "model_final.pt"
                    checkpoints.append(entry)
                elif path.suffix == ".onnx":
                    exports.append(_entry(path))
                elif path.name.startswith("events.out.tfevents"):
                    event_files.append(_entry(path))
            except OSError:
                continue
    checkpoints.sort(key=lambda item: (item.get("iteration") is None, item.get("iteration") or 0))

    return {
        "success": True,
        "task_id": task_id,
        "checkpoints": checkpoints,
        "exports": exports,
        "tensorboard_event_files": event_files,
        "artifact_available": (task.task_dir / "artifact.json").exists(),
    }

@router.get("/{task_id}/quality")
async def get_training_quality(task_id: str):
    """聚合任务的质量信号（清单 ⑥⑧）：preflight 探针 + ONNX 验收指标。

    数据源都是 worker 产物：native_preflight.json 的 acceptance_probe、
    exported/policy.onnx 的同目录验收报告。前端训练列表/monitor 用它渲染
    "pre-flight" 与"验收"徽章，而不是只有 reward 曲线。
    """
    task = get_training_manager().get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    task_dir = task.task_dir

    probe = None
    preflight_file = task_dir / "native_preflight.json"
    if preflight_file.exists():
        try:
            preflight = json.loads(preflight_file.read_text(encoding="utf-8-sig"))
            probe = preflight.get("acceptance_probe") or None
            if probe is None and preflight.get("acceptance_probe_error"):
                probe = {"verdict": "error", "error": str(preflight["acceptance_probe_error"])}
        except (OSError, json.JSONDecodeError):
            probe = {"verdict": "error", "error": "native_preflight.json unreadable"}

    acceptance = None
    exported_dir = task_dir / "exported"
    policy_file = exported_dir / "policy.onnx"
    if policy_file.exists():
        report_file = exported_dir / "policy.acceptance.json"
        if report_file.exists():
            try:
                acceptance = json.loads(report_file.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                acceptance = None
        else:
            acceptance = {"verdict": "not_evaluated"}

    probe_verdict = (probe or {}).get("verdict")
    acceptance_verdict = (acceptance or {}).get("verdict")
    return {
        "success": True,
        "task_id": task_id,
        "probe": probe,
        "acceptance": acceptance,
        "onnx_exported": policy_file.exists(),
        "badges": {
            "preflight": probe_verdict,       # pass | warn | error | None(未跑)
            "acceptance": acceptance_verdict, # pass | fail | not_evaluated | None(未导出)
        },
    }
