"""
Training API
训练任务管理的 REST API
"""

from fastapi import APIRouter, HTTPException
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

from backend.training_manager import get_training_manager
from contracts.robot_contract_v2 import RobotContractV2
from adapters.mjlab.env_factory import get_reward_terms
from adapters.mjlab.algorithms.registry import list_algorithms
from adapters.mjlab.recipe_registry import list_tasks, resolve_recipe
from backend.robot_packages import package_for_contract
from backend.robot_presets import get_robot_preset


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
    # Generic dot-path overrides over the profile's full config tree (e.g.
    # "environment.sim.mujoco.timestep": 0.002). Applied by the worker after
    # the recipe so user edits always win; unknown paths are skipped there.
    overrides: dict[str, Any] = Field(default_factory=dict)
    backend: str = "native_mjlab"  # runtime-validated; other frameworks reserved (unilab)


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
            "overrides": request.overrides,
            "backend": request.backend,
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
        # 框架选择：native_mjlab 可用；unilab 为已规划、尚未接入的框架。
        "frameworks": [
            {"id": "native_mjlab", "label": "MJLab", "available": True,
             "note": "当前唯一接入的框架，训练走隔离 adapter 环境"},
            {"id": "unilab", "label": "UniLab", "available": False,
             "planned": True,
             "note": "Hydra/OmegaConf 配置体系已调研，适配后开放"},
        ],
    }


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


def _terrain_mixes(terrain: Any) -> Optional[List[dict]]:
    """Normalize a profile terrain block into a flat sub-terrain mix list."""
    if not isinstance(terrain, dict):
        return None
    subs = terrain.get("sub_terrains")
    if isinstance(subs, dict):
        return [{"name": str(name), "proportion": value} for name, value in subs.items()]
    if isinstance(subs, list):
        return [{"name": str(name), "proportion": None} for name in subs]
    return None


def _observation_summary(contract: dict, profile: dict) -> Optional[str]:
    observation = contract.get("observation") if isinstance(contract.get("observation"), dict) else {}
    parts: List[str] = []
    if observation.get("dimension") is not None:
        parts.append(f"{observation['dimension']} 维")
    components = observation.get("components")
    if isinstance(components, list) and components:
        parts.append(" + ".join(str(item) for item in components))
    if profile.get("history_length"):
        parts.append(f"历史 {profile['history_length']} 步堆叠")
    return "；".join(parts) if parts else None


def _terminations_summary(profile: dict) -> Optional[str]:
    terminations = profile.get("terminations")
    if isinstance(terminations, dict) and terminations:
        return "、".join(str(name) for name in terminations)
    if isinstance(terminations, list) and terminations:
        return "、".join(str(item) for item in terminations)
    reward_terms = profile.get("reward_terms")
    if isinstance(reward_terms, list) and any("terminat" in str(term) for term in reward_terms):
        return "配方内置失败终止（is_terminated 计入奖励惩罚）；完整终止项由配方源码决定"
    return None


def _domain_randomization(profile: dict) -> Optional[dict]:
    for key in ("domain_randomization", "domain_rand", "randomization", "noise"):
        value = profile.get(key)
        if isinstance(value, dict) and value:
            return {"source_key": key, **value}
    return None


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


# ========== 训练配方全量配置 schema（introspected profile config tree） ==========

_SCHEMA_TIMEOUT_S = 180
_ROOT = Path(__file__).resolve().parents[1]


def _schema_workspace() -> Path:
    configured = os.environ.get("LEGGED_STUDIO_WORKSPACE")
    return Path(configured).expanduser().resolve() if configured else _ROOT / "workspace"


def _schema_cache_path(profile_id: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(profile_id)) or "profile"
    return _schema_workspace() / "schema_cache" / f"{safe}.json"


def _schema_interpreter() -> Optional[Path]:
    """Pick an interpreter able to import the profile's source dependencies.

    The schema dump imports the profile entrypoints, which depend on packages
    installed in the adapter venv (mjlab, bam, ...). The desktop runtime
    python (LEGGED_STUDIO_MJLAB_PYTHON) launches training workers but does
    not carry those deps, so it is only a last-resort candidate.
    """
    from adapters.mjlab.native_adapter import _venv_python

    candidates = []
    candidates.append(_venv_python(_ROOT / "adapters" / "mjlab" / ".venv"))
    explicit = os.environ.get("LEGGED_STUDIO_MJLAB_PYTHON")
    if explicit:
        candidates.append(Path(explicit))
    candidates.append(Path(sys.executable))
    for candidate in candidates:
        if not candidate.exists():
            continue
        # Cheap capability probe: the dump imports heavy deps lazily inside
        # the worker, but the entrypoint import itself needs the framework.
        try:
            probe = subprocess.run(
                [str(candidate), "-c", "import mjlab"],
                capture_output=True,
                timeout=30,
            )
            if probe.returncode == 0:
                return candidate
        except (OSError, subprocess.SubprocessError):
            continue
    # All probes failed (or mjlab missing everywhere): fall back to the first
    # existing candidate so the 502 carries the real import error instead of
    # a bare 501 "interpreter not found".
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _read_profile_mtime(profile: dict) -> Optional[float]:
    raw_path = profile.get("path")
    if not raw_path:
        return None
    profile_path = Path(str(raw_path))
    if not profile_path.is_absolute():
        profile_path = _ROOT / profile_path
    try:
        return profile_path.stat().st_mtime
    except OSError:
        return None


def _dump_schema_via_worker(robot_id: str, profile_id: str, profile: dict, package_root: str) -> dict:
    """Spawn the adapter interpreter in --dump-schema mode and parse its JSON."""
    interpreter = _schema_interpreter()
    if interpreter is None:
        raise HTTPException(
            status_code=501,
            detail={"message": "需要先配置运行时：未找到 MJLab 适配器 Python 解释器（adapters/mjlab/.venv）", "robot_id": robot_id, "profile_id": profile_id},
        )
    source_root = str(profile.get("source_root", "training/source"))
    dump_config = {
        "profile_id": profile_id,
        "package_root": package_root,
        "source_root": source_root,
        "entrypoints": profile.get("entrypoints") or {},
    }
    tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    schema_out = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    try:
        json.dump(dump_config, tmp, ensure_ascii=False)
        tmp.close()
        schema_out.close()
        source_abs = Path(source_root)
        if not source_abs.is_absolute():
            source_abs = Path(package_root) / source_abs
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join([str(source_abs), env.get("PYTHONPATH", "")]).strip(os.pathsep)
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            completed = subprocess.run(
                [
                    str(interpreter),
                    "-m", "adapters.mjlab.native_worker",
                    "--dump-schema",
                    "--config", tmp.name,
                    "--schema-output", schema_out.name,
                ],
                cwd=str(_ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=_SCHEMA_TIMEOUT_S,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise HTTPException(status_code=502, detail={"message": f"schema dump worker failed to launch: {exc}", "interpreter": str(interpreter)}) from exc
        # The worker writes the tree to --schema-output; stdout pipes on
        # Windows truncated large dumps (Errno 22), so the file is the
        # reliable transport and stdout is only a legacy fallback.
        schema = None
        schema_file = Path(schema_out.name)
        if schema_file.exists() and schema_file.stat().st_size > 0:
            try:
                schema = json.loads(schema_file.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError:
                schema = None
        if schema is None:
            stdout = completed.stdout or ""
            start = stdout.find("{")
            if start >= 0:
                try:
                    schema, _end = json.JSONDecoder().raw_decode(stdout[start:])
                except json.JSONDecodeError:
                    schema = None
        if completed.returncode != 0 or not isinstance(schema, dict) or not schema:
            raise HTTPException(
                status_code=502,
                detail={
                    "message": "schema dump worker did not return a config tree",
                    "interpreter": str(interpreter),
                    "returncode": completed.returncode,
                    "stderr": (completed.stderr or "")[-800:],
                    "stdout_head": (completed.stdout or "")[:300],
                },
            )
        return schema
    finally:
        for handle in (tmp, schema_out):
            try:
                os.unlink(handle.name)
            except OSError:
                pass


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
    """五大健康仪表盘 + 中文症状路由卡（T2.2，知识库 Ch25 蓝本）。"""
    task = get_training_manager().get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    from backend.health_cards import build_health_report

    rows = []
    metrics_file = task.task_dir / "metrics.jsonl"
    if metrics_file.exists():
        for line in metrics_file.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return {"success": True, "task_id": task_id, **build_health_report(rows)}


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
