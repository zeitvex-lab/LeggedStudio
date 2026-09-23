"""BACKEND.TRAINING.create

拆分自 backend/training_api.py（原 god file，~960 行）的独立子模块。
保持原有路由路径与响应结构不变，仅供 backend/training_api 聚合。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Header
from starlette.concurrency import run_in_threadpool

from backend.training.models import CreateTrainingRequest, CompareTrainingRequest
from backend.training.service import create_training_run, TrainingServiceError
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
        return await run_in_threadpool(
            create_training_run, request, idempotency_key=x_idempotency_key,
        )
    except TrainingServiceError as exc:
        status = {
            "invalid_request": 400,
            "smoke_required": 409,
            "invalid_overrides": 422,
            "unsupported": 501,
        }[exc.kind]
        raise HTTPException(status_code=status, detail=exc.detail) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@router.post("/compare")
async def create_comparison(request: CompareTrainingRequest):
    """Create a comparable matrix of runs sharing one contract and recipe."""
    algorithms = [str(item).upper() for item in request.algorithms]
    if len(set(algorithms)) != len(algorithms):
        raise HTTPException(status_code=400, detail="algorithms must be unique")
    tasks = []
    for algorithm in algorithms:
        single = request.model_copy(update={"algorithm": algorithm})
        result = await create_training(single, x_idempotency_key=None)
        tasks.append({"algorithm": algorithm, "task_id": result["task_id"]})
    return {"success": True, "count": len(tasks), "tasks": tasks, "session_config": request.model_dump(mode="json")}

@router.get("/options")
async def training_options():
    from backend.skill_registry import list_skills

    return {
        "algorithms": list_algorithms(),
        "reward_terms": get_reward_terms(),
        # E2：技能列表也进 options —— 训练页开箱即拿到数据源，不必另发一次请求
        "skills": list_skills(),
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

@router.get("/board/{robot_id}")
async def training_obs_board(robot_id: str):
    """**E4**：观测/动作映射板 —— 五元组 + 声明宽度 + 动作槽位，**维度不符即时报错**。

    只读契约声明（控制面安全：不 import torch/mjlab），所以没有 GPU 也能画板子，
    也能在开训前就把维度问题拦下来。
    """
    import json

    from backend.policy_artifacts import ROBOTS_DIR
    from backend.training.obs_board import board

    path = ROBOTS_DIR / robot_id / "contract.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"robot package {robot_id} not found")
    contract = json.loads(path.read_text(encoding="utf-8-sig"))
    return {"success": True, **board(contract)}


@router.get("/skills")
async def training_skills():
    """**E2**：技能选择器的数据源 —— `registry/skills` 的显式清单（base + patches）。

    技能列表**来自数据而非硬编码**：清单是权威（K4），`role` / `patch_of` 让前端能画出
    「基座 + 覆盖」的关系，而不是一堆平铺的名字。
    """
    from backend.skill_registry import list_skills, skill_manifest

    manifest = skill_manifest()
    entries = {str(item["recipe_id"]): dict(item) for item in manifest["skills"]}
    skills = []
    for summary in list_skills():
        entry = entries.get(str(summary["recipe_id"]), {})
        skills.append({
            **summary,
            "role": entry.get("role"),
            "patch_of": entry.get("patch_of"),
            "summary": entry.get("summary"),
            "path": entry.get("path"),
        })
    return {"success": True, "schema": manifest.get("schema"), "skills": skills,
            "available": sorted(entries)}


@router.get("/reward-catalog")
async def training_reward_catalog():
    """**E3**：奖励目录 —— 四层分组（Tracking/Regularization/Style/Contact）+ 每项中文名/说明/
    默认值/supported + **三组经典冲突清单**（冲突是数据，判定是代码）。"""
    from backend.training.reward_catalog import catalog

    return {"success": True, **catalog()}


@router.post("/reward-conflicts")
async def training_reward_conflicts(weights: dict[str, float]):
    """给一份权重表，报出**命中的经典冲突**。

    只报不拦：冲突常常是刻意的（对比实验），拦下来反而挡住探索；但**必须看得见** ——
    否则训练曲线会给出一个"看似合理、实为目标打架"的结果。
    """
    from backend.training.reward_catalog import check_conflicts

    return {"success": True, "conflicts": check_conflicts(weights)}


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
