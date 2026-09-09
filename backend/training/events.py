"""BACKEND.TRAINING.events

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



@router.get("/{task_id}/events")
async def training_event_stream(task_id: str, interval: float = 1.0):
    """SSE：实时推送训练日志增量与状态（前端 EventSource + 断线重连）。

    事件格式：
      event: log    data: {"lines": [...]}        （training.log 新增行）
      event: status data: {"status": ..., ...}     （status.json 变化）
      event: ping   data: {}                       （保活）
    终止条件：任务到达终态（completed/failed/stopped）后再推送一次状态即关闭。
    """
    import asyncio

    from fastapi.responses import StreamingResponse

    task = get_training_manager().get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    async def stream():
        log_offset = 0
        last_status = None
        terminal = {"completed", "failed", "stopped", "error"}
        while True:
            payload_lines = []
            log_file = task.task_dir / "training.log"
            if log_file.exists():
                try:
                    with log_file.open("r", encoding="utf-8", errors="replace") as handle:
                        handle.seek(log_offset)
                        chunk = handle.read()
                        log_offset = handle.tell()
                    if chunk:
                        payload_lines = chunk.splitlines()[-200:]
                except OSError:
                    pass
            status_payload = None
            try:
                status_payload = task.get_status_info()
            except Exception:
                status_payload = None
            if payload_lines:
                yield f"event: log\ndata: {json.dumps({'lines': payload_lines}, ensure_ascii=False)}\n\n"
            if status_payload and status_payload != last_status:
                last_status = status_payload
                yield f"event: status\ndata: {json.dumps(status_payload, ensure_ascii=False, default=str)}\n\n"
            if status_payload and str(status_payload.get("status", "")).lower() in terminal:
                break
            yield "event: ping\ndata: {}\n\n"
            await asyncio.sleep(max(0.2, interval))

    return StreamingResponse(stream(), media_type="text/event-stream")
