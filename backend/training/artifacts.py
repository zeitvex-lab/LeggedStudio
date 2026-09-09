"""BACKEND.TRAINING.artifacts

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
from contracts.robot_contract_v2 import RobotContractV2
from adapters.mjlab.env_factory import get_reward_terms
from adapters.mjlab.algorithms.registry import list_algorithms
from adapters.mjlab.recipe_registry import list_tasks, resolve_recipe
from adapters.backend_adapter import list_backend_descriptors


router = APIRouter(prefix="/api/training", tags=["training"])



@router.get("/{task_id}/artifact")
async def get_policy_artifact(task_id: str):
    """策略档案（T3.1）：训练元数据/观测-动作规范/lineage/双 gate 报告。"""
    task = get_training_manager().get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    artifact_file = task.task_dir / "artifact.json"
    if not artifact_file.exists():
        return {"success": True, "task_id": task_id, "available": False,
                "note": "训练完成后生成 PolicyArtifact；含 lineage 与双 gate 报告"}
    try:
        artifact = json.loads(artifact_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=f"artifact.json 解析失败: {exc}") from exc
    return {"success": True, "task_id": task_id, "available": True, "artifact": artifact}

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
