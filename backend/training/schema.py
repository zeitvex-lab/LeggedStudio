"""BACKEND.TRAINING.schema

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



# ========== 五分类配置预览（read-only, preview-only） ==========

RECIPE_READONLY_NOTE = "由训练配方源码决定"
CONTRACT_READONLY_NOTE = "由机器人契约决定（训练资产页面 02 编辑）"
ARCHIVED_ONLY_NOTE = "仅随任务归档，训练 worker 不应用"
# Keys the create endpoint accepts and the worker really applies.
EDITABLE_CREATE_KEYS = [
    "algorithm", "num_envs", "max_iterations", "learning_rate", "save_interval",
    "episode_length_s", "task_name", "profile_id", "terrain_type", "device",
    "reward_scales", "reward_overrides", "reward_params", "command_ranges",
    "num_steps", "num_minibatches", "gamma", "gae_lambda", "clip_param",
    "entropy_coef", "seed",
]

@router.get("/config-preview")
async def training_config_preview(robot_id: str, profile_id: Optional[str] = None):
    """Five-category structured preview of the training configuration.

    Preview only: reads the persisted package index / profile JSON through the
    existing robot preset accessors. Never imports package code and never
    probes the MJLab runtime, so it is safe to call while typing.
    """
    preset = get_robot_preset(robot_id)
    if preset is None:
        raise HTTPException(status_code=404, detail=f"Unknown robot package: {robot_id}")
    profile: dict = {}
    if profile_id:
        found = next(
            (item for item in preset.get("training_profiles", []) if str(item.get("profile_id")) == profile_id),
            None,
        )
        if found is None:
            raise HTTPException(status_code=404, detail=f"Training profile not found in package {robot_id}: {profile_id}")
        profile = found

    contract = preset.get("contract") or {}
    joints = contract.get("joints") or {}
    contract_action = contract.get("action") or {}
    control = contract.get("control") or {}
    training_config = preset.get("training_config") or {}
    runner = profile.get("runner")
    if not isinstance(runner, dict):
        runner = None

    physics_hz = profile.get("physics_hz") if profile.get("physics_hz") is not None else control.get("physics_hz")
    decimation = profile.get("decimation") if profile.get("decimation") is not None else control.get("decimation")
    num_envs = profile.get("num_envs") if profile.get("num_envs") is not None else training_config.get("num_envs")
    device_hint = "auto 优先选择 CUDA；并行环境 ≥1024 时建议使用 GPU，CPU 调试建议 ≤256 环境" if (num_envs or 0) >= 1024 else "auto 优先选择 CUDA；CPU 调试即可"

    simulator_notes = [
        "physics_hz / decimation 由机器人契约决定，本页只读",
        "MJLab 运行时状态徽标来自 GET /api/training/hardware 探测结果",
    ]
    learning_notes = ["MJLab 当前仅开放 PPO 训练"]
    if runner:
        learning_notes.append("hidden_dims / activation / 观测归一化沿用 runner 配方默认值，本页只读")
        learning_notes.append("学习率自适应调度由 runner 配方决定，此处填写的是初始学习率")
    else:
        learning_notes.append("当前档案未声明 runner 覆盖，将使用通用 runner 默认值")

    payload = {
        "robot_id": robot_id,
        "profile_id": profile_id,
        "task_name": profile.get("task_name") or training_config.get("task_name") or "forward_walk",
        "profile_label": profile.get("display_name"),
        "simulator": {
            "backend": profile.get("backend") or "native_mjlab",
            "device_hint": device_hint,
            "physics_hz": physics_hz,
            "decimation": decimation,
            "control_hz": control.get("control_hz"),
            "notes": simulator_notes,
        },
        "environment": {
            "terrain_type": profile.get("terrain_type") or training_config.get("terrain", {}).get("terrain_type") or "plane",
            "terrain_mixes": _terrain_mixes(profile.get("terrain")),
            "command_ranges": profile.get("command_ranges") or training_config.get("command_ranges") or None,
            "curriculum": profile.get("curriculum") or None,
            "episode_length_s": profile.get("episode_length_s") or training_config.get("episode_length_s") or None,
        },
        "embodiment": {
            "joint_order": contract_action.get("joint_order") or joints.get("actuated_joints") or [],
            "default_pose": joints.get("default_pose") or None,
            "init_pose": profile.get("init_pose") or None,
            "action": profile.get("action") or None,
            "observation_summary": _observation_summary(contract, profile),
        },
        "learning": {
            "algorithm": "PPO",
            "runner": runner,
            "notes": learning_notes,
        },
        "robustness": {
            "reward_terms": profile.get("reward_terms") or None,
            "terminations_summary": _terminations_summary(profile),
            "domain_randomization": _domain_randomization(profile),
        },
        "editable_vs_readonly": {
            "editable_keys": list(EDITABLE_CREATE_KEYS),
            "readonly_categories": [
                {"category": "simulator", "keys": ["physics_hz", "decimation"], "reason": CONTRACT_READONLY_NOTE},
                {"category": "environment", "keys": ["terrain_mixes", "curriculum"], "reason": RECIPE_READONLY_NOTE},
                {"category": "environment", "keys": ["noise", "terrain"], "reason": ARCHIVED_ONLY_NOTE},
                {"category": "embodiment", "keys": ["joint_order", "default_pose"], "reason": CONTRACT_READONLY_NOTE},
                {"category": "learning", "keys": ["hidden_dims", "activation", "obs_normalization"], "reason": RECIPE_READONLY_NOTE + "（runner 默认）"},
                {"category": "robustness", "keys": ["terminations", "domain_randomization"], "reason": RECIPE_READONLY_NOTE},
            ],
        },
    }
    return payload

@router.get("/profile-schema")
async def training_profile_schema(robot_id: str, profile_id: str):
    """Full introspected config tree (environment + runner) for a profile.

    Spawns the isolated adapter interpreter with ``--dump-schema`` so the
    package-owned entrypoints are imported once, outside this process, and the
    resulting tree is cached under ``<workspace>/schema_cache/`` keyed by the
    profile JSON mtime. The response carries three views of the same dump:

    - ``schema`` / ``tree``: the raw config tree (expert mode renders it as
      dot-path override rows),
    - ``params``: the curated descriptor catalog (:mod:`adapters.mjlab.param_registry`)
      resolved against the tree — 中文 label / unit / hint / type per commonly
      tuned parameter, expanded for reward weights, event params, action
      scales and termination thresholds. The 03 training page renders these
      as the primary parameter cards per category.
    """
    preset = get_robot_preset(robot_id)
    if preset is None:
        raise HTTPException(status_code=404, detail=f"Unknown robot package: {robot_id}")
    profile = next(
        (item for item in preset.get("training_profiles", []) if str(item.get("profile_id")) == profile_id),
        None,
    )
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Training profile not found in package {robot_id}: {profile_id}")
    package_root = str((preset.get("robot_package") or {}).get("package_root", ""))
    if not package_root:
        raise HTTPException(status_code=404, detail=f"Package root is not registered for robot {robot_id}")

    from adapters.mjlab.param_groups import build_param_groups
    from adapters.mjlab.param_descriptors import resolve_params

    mtime = _read_profile_mtime(profile)
    cache_path = _schema_cache_path(profile_id)
    if mtime is not None and cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            cached = None
        if isinstance(cached, dict) and cached.get("profile_mtime") == mtime and isinstance(cached.get("schema"), dict):
            schema = cached["schema"]
            return {
                "robot_id": robot_id,
                "profile_id": profile_id,
                "schema": schema,
                "tree": schema,
                "params": resolve_params(schema),
                "groups": {
                    cat: build_param_groups(schema, cat)
                    for cat in ("simulator", "environment", "embodiment", "learning", "rewards", "robustness")
                },
                "cached": True,
            }

    schema = await run_in_threadpool(_dump_schema_via_worker, robot_id, profile_id, profile, package_root)
    if mtime is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            cache_path.write_text(
                json.dumps({"profile_id": profile_id, "profile_mtime": mtime, "generated_at": datetime.now().isoformat(), "schema": schema}, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass
    return {
        "robot_id": robot_id,
        "profile_id": profile_id,
        "schema": schema,
        "tree": schema,
        "params": resolve_params(schema),
        "groups": {
            cat: build_param_groups(schema, cat)
            for cat in ("simulator", "environment", "embodiment", "learning", "rewards", "robustness")
        },
        "cached": False,
    }


def cached_param_catalog(profile_id: str) -> list[dict[str, Any]] | None:
    """从 schema 缓存取参数目录；**没有缓存返回 None**（不在这里触发 dump）。

    E6 的门需要目录才能判"未知路径"，但**不能把一次请求变成几十秒的阻塞**
    （dump 要起 worker 进程）。所以：有缓存就严判，没缓存就退回静态只读表
    （见 `backend/training/dot_path.py` 的 ``STATIC_READONLY``）——"不能改物理"
    这条事实不依赖目录。
    """
    try:
        cached = json.loads(_schema_cache_path(profile_id).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    schema = cached.get("schema") if isinstance(cached, dict) else None
    if not isinstance(schema, dict):
        return None
    try:
        from adapters.mjlab.param_descriptors import resolve_params

        return resolve_params(schema)
    except Exception:  # noqa: BLE001  adapter 不可用不该让门变成 500
        return None


@router.post("/validate-overrides")
async def validate_training_overrides(payload: dict[str, Any]) -> dict[str, Any]:
    """**E6 专家模式**：校验一批点路径覆盖 —— 未知路径 / 只读项 / 类型不符 **一律拒**。

    返回 ``{ok, applied, details, problems, catalog}``；``ok=False`` 时前端**整批拒绝**
    （`applied` 仅供展示，不得写入）。目录优先用缓存（秒级）；缓存缺失时用静态只读表兜底，
    并在 ``catalog`` 字段如实说明 —— 不假装"什么都查过了"。
    """
    robot_id = str(payload.get("robot_id") or "")
    profile_id = str(payload.get("profile_id") or "")
    edits = payload.get("overrides") or {}
    if not isinstance(edits, dict) or not edits:
        raise HTTPException(status_code=400, detail="overrides 必须是非空对象（dot-path → value）")
    if not robot_id or not profile_id:
        raise HTTPException(status_code=400, detail="需要 robot_id 与 profile_id（参数目录按档案解析）")

    from backend.training.dot_path import validate_edits

    catalog = cached_param_catalog(profile_id)
    report = validate_edits(edits, catalog=catalog)
    return {
        "success": True,
        **report,
        "robot_id": robot_id,
        "profile_id": profile_id,
        "catalog": "full" if catalog else "static_only",
        "catalog_note": None if catalog else (
            "参数目录尚未生成（schema 缓存为空）：已按**静态只读表**判过物理/契约类，"
            "但无法判「未知路径」。在训练页选中该档案（或访问 /api/training/schema）即可生成缓存。"
        ),
    }
