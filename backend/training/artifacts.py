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
from contracts.contract_legacy_v2 import ContractLegacyV2
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
        artifact = json.loads(artifact_file.read_text(encoding="utf-8-sig"))
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


@router.get("/{task_id}/run")
async def get_training_run(task_id: str, summary: bool = False):
    """**B9 Run 档案**：可复现四件套 + 对账报告 + 已入库产物（F1/F2/F7 页面消费）。

    直接给出 ``verify`` 结论，页面据此显示"这份 Run 能否复现"，而不是靠人肉比对；
    接线之前建立的旧任务没有档案，返回 ``available: false`` 并说明原因（不编造）。
    ``?summary=1`` 只给 run 记录 / verify / produced（列表页徽章用），不带
    resolved-config 与 environment-lock 两个大块 —— 列表每 5 秒刷一次，不能拖全文。
    """
    from backend.policy_artifacts import produced_for_run
    from backend.training.runs import (
        ENVIRONMENT_LOCK_NAME, RESOLVED_CONFIG_NAME, load_run, verify_run,
    )

    task = get_training_manager().get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    record = load_run(task.task_dir)
    if record is None:
        return {
            "success": True,
            "available": False,
            "task_id": task_id,
            "note": "该任务建立于 B9 接线之前，未落 Run 档案；新建任务即带可复现四件套",
        }

    payload = {
        "success": True,
        "available": True,
        "task_id": task_id,
        "run": record.as_dict(),
        "verify": verify_run(task.task_dir),
        "produced": produced_for_run(record.run_id),
    }
    if summary:
        return payload

    def _read(name: str):
        try:
            return json.loads((task.task_dir / name).read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return None

    payload["resolved_config"] = _read(RESOLVED_CONFIG_NAME)
    payload["environment_lock"] = _read(ENVIRONMENT_LOCK_NAME)
    payload["effective_config"] = _read("effective-config.json")
    return payload


@router.post("/{task_id}/promote")
async def promote_training_run(task_id: str, payload: dict[str, Any] | None = None):
    """**L7「训练→导出→入库」的入库端点**：把一份已完成 Run 的导出产物收进出库。

    显式动作（与 ``--write-baseline`` 同哲学）：训练完成不自动入库 —— 出库是产品决策，
    不是训练的副作用。判据全取自 Run 档案：run.json（可追溯）/ status=completed /
    exported/policy.onnx（worker ⑤ 的导出产物），任一不满足即 4xx 如实报因。
    幂等：同一 run 重复入库覆盖同一 artifact_id（onnx 内容变了 hash 会变，如实反映）。
    """
    task = get_training_manager().get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    from backend.policy_artifacts import promote_from_run

    artifact_id = None
    if isinstance(payload, dict):
        artifact_id = str(payload.get("artifact_id") or "") or None

    def _run() -> dict[str, Any]:
        # 产品入口默认**安装进包 + 回挂 Pack**（2026-09-16）：训练产出的策略要在页面/CLI 上
        # 按 --policy-id 可用、且 Pack 记得住它，才算"训练→出库→复现"闭环；
        # 库函数默认关（它改写包内资产文件，不该由测试或脚本随手触发）。
        return promote_from_run(
            task.task_dir,
            artifact_id=artifact_id,
            policy_id=(payload or {}).get("policy_id") if isinstance(payload, dict) else None,
            install=True,
            attach_pack=True,
        )

    try:
        artifact = await run_in_threadpool(_run)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "success": True,
        "task_id": task_id,
        "artifact": artifact,
        "index": "policies/index.json（produced 条目随 build_all 重建保留）",
    }
