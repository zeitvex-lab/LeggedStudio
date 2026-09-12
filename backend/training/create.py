"""BACKEND.TRAINING.create

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

from backend.training.models import (  # noqa: F401
    CreateTrainingRequest, CompareTrainingRequest,
)
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



@router.get("/hardware")
async def training_hardware():
    """Report the runtime capabilities used by the training worker.

    Runs the real interpreter probe (force=True) — this endpoint backs the
    training pages where waiting for torch import is acceptable. Off the event
    loop so a concurrent probe cannot stall unrelated requests.
    """
    from adapters.mjlab.native_adapter import DEFAULT_SOURCE, preflight
    native = await run_in_threadpool(preflight, DEFAULT_SOURCE, True)
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

@router.post("/create")
async def create_training(
    request: CreateTrainingRequest,
    x_idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """
    创建新的训练任务

    启动独立进程进行训练

    Idempotency-Key 头（可选）：重复提交同一 key 时返回已创建的任务而非重复启动；
    resume_from 字段提供 checkpoint 路径时从该检查点继续训练（Feature 13）。
    """
    try:
        # Idempotency guard (Feature 13): replay of the same creation key short-circuits.
        if x_idempotency_key:
            manager = get_training_manager()
            replayed = manager.resolve_idempotency(x_idempotency_key)
            if replayed and manager.get_task(replayed):
                return {
                    "success": True,
                    "task_id": replayed,
                    "idempotent_replay": True,
                    "message": "Idempotent replay: returning existing task",
                }

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

        # 冒烟档（T2.3）：先 64 envs × 5 iters 验证链路，冒烟绿再放行长训练
        num_envs = request.num_envs
        max_iterations = request.max_iterations
        if request.smoke:
            num_envs = min(num_envs, 64)
            max_iterations = min(max_iterations, 5)

        # 准备配置
        config = {
            "algorithm": algorithm,
            "smoke_preset": request.smoke,
            "num_envs": num_envs,
            "max_iterations": max_iterations,
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
            "overrides": request.overrides,
            "backend": request.backend,
            "resume_from": request.resume_from,
        }
        try:
            resolved_recipe = resolve_recipe(config)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        config["resolved_recipe"] = resolved_recipe.model_dump(mode="json")
        if request.backend not in ("native_mjlab", ""):
            raise HTTPException(status_code=501, detail={"message": f"backend '{request.backend}' is reserved for a future framework and is not wired yet"})
        if request.backend == "native_mjlab":
            config["mode"] = "train"
            package = package_for_contract(contract.model_dump(mode="json"))
            config["robot_package"] = package
            config["generic_task"] = True
            from adapters.mjlab.native_adapter import DEFAULT_EXTENSION, DEFAULT_SOURCE, package_runtime_diagnostics, preflight
            # Training launch is the one path that must really probe torch —
            # waiting here is acceptable, and the cached report makes repeats instant.
            native = await run_in_threadpool(preflight, DEFAULT_SOURCE, True)
            if not native["exists"] or not native["manager_env_available"] or not native.get("runtime", {}).get("available"):
                raise HTTPException(status_code=501, detail={"message": "native MJLab adapter is not ready", "preflight": native})
            if not native.get("execution_ready"):
                raise HTTPException(status_code=501, detail={"message": native.get("execution_note", "native MJLab task adapter is not ready"), "preflight": native})
            compatibility = package_runtime_diagnostics(package, native)
            native["package_compatibility"] = compatibility
            if compatibility["status"] == "incompatible":
                raise HTTPException(status_code=501, detail={"message": "selected robot package is incompatible with the active MJLab runtime", "compatibility": compatibility, "preflight": native})
            if compatibility["status"] == "unknown":
                raise HTTPException(status_code=501, detail={"message": "active MJLab runtime version could not be verified for the selected robot package", "compatibility": compatibility, "preflight": native})

        # 创建任务
        manager = get_training_manager()
        task_id = manager.create_task(
            contract=contract,
            config=config,
            idempotency_key=x_idempotency_key,
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
        # 框架选择：由 BackendAdapter 注册表（adapters/backend_adapter.py）单一事实源输出。
        "frameworks": [
            {"id": desc.id, "label": desc.label, "available": desc.available,
             "planned": not desc.available,
             "note": desc.note or f"{desc.label}（{desc.python_env}）"}
            for desc in list_backend_descriptors()
        ],
    }

@router.post("/resolve-recipe")
async def resolve_training_recipe(config: dict):
    """Validate and return the canonical recipe consumed by workers."""
    try:
        recipe = resolve_recipe(config)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"valid": True, "recipe": recipe.model_dump(mode="json")}

@router.get("/resource-packs")
async def resource_packs():
    """模块化资源包目录（T2.5）：把 55+ 预设组织为三线资源包卡片。

    - 盲走包：DreamWaQ / wtw / blind 类（本体感知 + 历史帧 + 隐式姿态编码）
    - 模仿学习三线：DeepMimic 显式跟踪 / AMP 对抗风格 / teacher→student 蒸馏
      （对标两家均无的独有优势，报告 1 §7）
    - 感知观测项：parkour / depth / stair 类（接触 → 高度场 → 深度相机）
    分组按 profile_id 关键词匹配（数据驱动，无 per-robot 分支）。
    """
    from backend.robot_packages import list_robot_packages
    from backend.perception_observations import list_perception_items

    pack_rules = [
        ("blind_walking", "盲走资源包", "DreamWaQ 全家：本体感知观测库 + 历史帧堆叠 + 隐式姿态编码 + 地形课程 + 域随机化",
         ("dreamwaq", "wtw", "walk-these-ways", "blind")),
        ("imitation", "模仿学习三线", "DeepMimic 60 clips 显式跟踪 / AMP 对抗风格 / teacher→student 蒸馏（课程与对称性可选）",
         ("amp", "tracking", "deepmimic", "motion", "distill")),
        ("perception", "感知观测项", "足端接触 → 高度场 → 深度相机（PIE 106×60 楼梯 parkour 内置参考）",
         ("parkour", "depth", "stair", "rough")),
    ]
    perception_items = list_perception_items()
    packs = []
    for pack_id, name, description, keywords in pack_rules:
        profiles = []
        for record in list_robot_packages():
            for profile in record.get("training_profiles", []):
                pid = str(profile.get("profile_id", "")).lower()
                if any(keyword in pid for keyword in keywords):
                    profiles.append({
                        "robot_id": record["robot_id"],
                        "profile_id": profile.get("profile_id"),
                        "algorithm": profile.get("algorithm", "PPO"),
                        "num_envs": profile.get("num_envs"),
                        "max_iterations": profile.get("max_iterations"),
                    })
        packs.append({
            "id": pack_id,
            "name": name,
            "description": description,
            "profile_count": len(profiles),
            "profiles": profiles,
        })
    for pack in packs:
        if pack["id"] == "perception":
            pack["perception_items"] = perception_items
    return {"success": True, "packs": packs}
