"""训练 Run 的一等对象 —— 可复现四件套：seed / 依赖锁 / resolved-config / 输入哈希。

一次训练不是一个进度条，而是一份**不可变、可回溯**的档案：``<task_dir>/`` 里落
``resolved-config.json``（含输入哈希）、``environment-lock.json``（uv.lock 与关键依赖版本）、
``checkpoints/``、``metrics/``。**改任何东西 = 派生新 Run**，不就地覆盖（价值观 V9）。

设计来源（2026-09-14 实地调研 ``00_resources``，均只取形态、不引运行时）：

* **落盘布局 + RunRecord 契型** —— ``lain_job/RoboLab``：``src/robolab/core/contracts.py``
  （frozen dataclass ``RunRecord``：``run_id/recipe/status/resolved_config_path/
  artifact_path/metrics_path/environment``）与 ``frameworks/mjlab/worker.py``（run_dir 里写
  ``resolved_config.json`` + ``metrics.json``）。
* **配置规范化哈希** —— ``genesislab`` ``utils/configclass/dict.py::dict_to_md5_hash``
  （``json.dumps(sort_keys=True)`` → 摘要）。本仓改用 **sha256**（与 ``ContractLegacyV2.compute_hash``
  同一算法族），并统一用紧凑分隔符，保证"同输入必同摘要"。
* **环境元数据字段集** —— ``unilab_new/UniLab`` ``logging/common.py``（run_config.json：git
  commit/branch/dirty + hardware + seed）与 ``wandb`` ``sdk/lib/filenames.py`` +
  ``wandb-metadata.json``（os/python/cuda/cpu_count/git{remote,commit}）。
* **代码状态留档** —— ``rsl_rl`` ``utils/logger.py::_store_code_state``（把 git commit +
  status + diff 写进 run 目录）。
* **依赖锁范式** —— ``rc_old/RC_WheelLeg/05_software/train/rc_mjlab/DEPENDENCIES.md``
  （uv.lock 为准 + 上游固定 commit）。

**分层约束（V5）**：本模块属控制面，**绝不 import torch/mjlab**。依赖版本一律从
adapter venv 的 ``*.dist-info`` 目录名读取（纯文件系统操作），因此不需要启动训练进程。
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from contracts.validator import normalized_sha256  # 归一摘要唯一实现
from backend.jsonio import load_json, read_json, write_json  # JSON 读写唯一实现


#: 仓库根（``backend/training/runs.py`` → 上溯两级）。
ROOT = Path(__file__).resolve().parents[2]

#: 依赖锁文件（environment-lock 的第一顺位证据）。
UV_LOCK = ROOT / "uv.lock"

#: adapter venv 默认落点（与 ``contracts/path_bootstrap.py`` 的约定一致）。
DEFAULT_ADAPTER_VENV = ROOT / "adapters" / "mjlab" / ".venv"

#: 从 adapter venv 读取版本号的关注清单（读 dist-info 目录名，不 import）。
WATCHED_PACKAGES = (
    "torch", "mujoco", "mjlab", "warp-lang", "mujoco-warp", "rsl-rl",
    "onnx", "onnxruntime", "numpy",
)

#: 四件套在 run 目录里的落点（seed 与输入哈希写在 resolved-config.json 内）。
RESOLVED_CONFIG_NAME = "resolved-config.json"
ENVIRONMENT_LOCK_NAME = "environment-lock.json"
CHECKPOINTS_DIR = "checkpoints"
METRICS_DIR = "metrics"
CODE_STATE_NAME = "code-state.json"

#: resolved-config 的 schema 版本（本模块产出、F 组页面消费）。
RUN_SCHEMA = "training-run-1.0"


class RunImmutableError(RuntimeError):
    """已存在的 Run 与本次输入不一致 —— 拒绝就地覆盖（fail-closed）。"""


# --------------------------------------------------------------------------------------
# 摘要
# --------------------------------------------------------------------------------------
def canonical_digest(payload: Any) -> str:
    """对任意 JSON 可序列化结构求**规范化摘要**（sha256，16 进制全串）。

    规范化 = ``sort_keys`` + 紧凑分隔符 + 保留非 ASCII（不转义），因此**字典键顺序、
    平台差异都不影响结果**；同一份输入在任何机器上都会得到同一个摘要 —— 这是"同 seed
    可对账"的前提。
    """
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def file_digest(path: Path) -> str | None:
    """文件内容摘要（CRLF → LF 归一）：委托 ``contracts.validator.normalized_sha256``。

    **为什么不再分块**：归一与分块天然冲突 —— ``\r\n`` 可能恰好被切在两块之间，
    跨块那一处会漏归一（``normalize_line_endings`` 的 docstring 已写明这条），
    而这种错随文件长度随机出现、最难查。本函数只服务策略产物（onnx 几十 MB 级），
    整份读的内存代价换来"一个工件只有一个哈希"，值。

    此前这里是**第二套口径**（原始字节），与 ``policy_artifacts`` 里 B40 收口的
    ``normalized_sha256`` 并存 —— 同一个 onnx 在同一模块里能算出两个哈希。
    """
    try:
        return normalized_sha256(Path(path).read_bytes())
    except OSError:
        return None


# --------------------------------------------------------------------------------------
# 输入哈希（resolved-config 的语义部分）
# --------------------------------------------------------------------------------------
def build_inputs(
    *,
    contract_hash: str,
    recipe: Mapping[str, Any] | None = None,
    profile: Mapping[str, Any] | None = None,
    seed: int,
    params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """组装**输入四元组**并给出其摘要。

    ``inputs.digest`` 是 Run 的"指纹"：只由这份 dict 决定。任何一项变化都会换指纹，
    从而派生新 Run（V9 只读 + 版本化）。
    """
    payload = {
        "contract_hash": str(contract_hash),
        "recipe": dict(recipe or {}),
        "profile": dict(profile or {}),
        "seed": int(seed),
        "params": dict(params or {}),
    }
    payload["digest"] = canonical_digest(payload)
    return payload


def build_resolved_config(
    *,
    robot_id: str,
    task: str,
    inputs: Mapping[str, Any],
    resolved: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """``resolved-config.json`` 的内容：**输入 + 实际生效的全部参数**。

    "resolved" 的含义与 mjlab/RoboLab 一致 —— 不是原始 recipe，而是**合并/展开后真正
    跑起来的那份**（extends 链已深合并、默认值已填、物理层已取契约现值）。
    """
    payload = {
        "schema": RUN_SCHEMA,
        "robot_id": str(robot_id),
        "task": str(task),
        "inputs": dict(inputs),
        "resolved": dict(resolved or {}),
    }
    # `config_digest` 覆盖**整份档案**（不含自身）：任何一处被改动都能查出来，
    # 这是"不可变"从口号变成可校验事实的那一步。
    payload["config_digest"] = canonical_digest(payload)
    return payload


def run_id_for(*, task: str, inputs: Mapping[str, Any], when: datetime | None = None) -> str:
    """Run 目录名：``<UTC 时间戳>_<task>_<输入指纹前 8 位>``。

    时间戳保证"同一份输入可跑多次"（多次 Run 各自留档），指纹段保证**一眼看出两次 Run
    是否同源** —— 指纹相同而时间不同，就是"同输入重跑"，可直接拿来做对账。
    """
    stamp = (when or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^0-9A-Za-z._-]+", "-", str(task)).strip("-") or "task"
    return f"{stamp}_{slug}_{str(inputs.get('digest', ''))[:8]}"


# --------------------------------------------------------------------------------------
# 依赖锁 / 环境元数据
# --------------------------------------------------------------------------------------
def _git_state(repo: Path | None = None) -> dict[str, Any]:
    """git commit + 是否有未提交改动（best-effort：不是 git 仓库就返回 ``{}``）。"""
    root = str(repo or ROOT)
    try:
        commit = subprocess.run(
            ["git", "-C", root, "rev-parse", "HEAD"],
            capture_output=True, text=True, encoding="utf-8", timeout=20, check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", root, "status", "--porcelain"],
            capture_output=True, text=True, encoding="utf-8", timeout=20, check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    return {"commit": commit, "dirty": bool(status.strip())}


def venv_package_versions(venv: Path | str | None = None) -> dict[str, str]:
    """从 venv 的 ``*.dist-info`` 目录名读版本 —— **不 import 任何训练栈**（守 V5）。

    dist-info 目录名形如 ``torch-2.11.0+cu128.dist-info``；这是安装后的权威落盘证据，
    比"试着 import 一次"更安全（控制面一旦 import torch 就再也回不去"双击即用"）。
    """
    root = Path(venv or os.environ.get("LEGGED_STUDIO_MJLAB_VENV") or DEFAULT_ADAPTER_VENV)
    candidates: list[Path] = []
    if (root / "Lib" / "site-packages").is_dir():          # Windows
        candidates.append(root / "Lib" / "site-packages")
    if (root / "lib").is_dir():                            # POSIX
        candidates.extend(sorted((root / "lib").glob("python*/site-packages")))

    found: dict[str, str] = {}
    for site_packages in candidates:
        for info in site_packages.glob("*.dist-info"):
            name, _, version = info.name[: -len(".dist-info")].rpartition("-")
            if not name or not version:
                continue
            found.setdefault(name.lower(), version)
    return {name: found[name] for name in WATCHED_PACKAGES if name in found}


def collect_environment_lock(
    *,
    seed: int,
    device: str | None = None,
    adapter_venv: Path | str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """``environment-lock.json`` 的内容：**这次 Run 到底跑在什么环境里**。

    判据不是"看起来像"，而是**可复核**：``uv.lock`` 的 sha256 决定依赖解析结果，
    dist-info 决定实际装了什么，git 决定代码状态。
    """
    venv = Path(adapter_venv or os.environ.get("LEGGED_STUDIO_MJLAB_VENV") or DEFAULT_ADAPTER_VENV)
    lock_path = UV_LOCK
    lock = {
        "path": str(lock_path.relative_to(ROOT)) if lock_path.is_file() else None,
        "sha256": file_digest(lock_path),
    }
    return {
        "schema": f"{RUN_SCHEMA}-environment",
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": int(seed),
        "device": device,
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "dependency_lock": lock,
        "adapter_venv": {
            "path": str(venv),
            "exists": venv.is_dir(),
            "packages": venv_package_versions(venv),
        },
        "vcs": _git_state(),
        "extra": dict(extra or {}),
    }


# --------------------------------------------------------------------------------------
# Run 记录
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class RunRecord:
    """一份 Run 的索引信息（frozen：落盘后不再变，改输入＝新对象）。"""

    run_id: str
    task: str
    robot_id: str
    run_dir: str
    inputs_digest: str
    config_digest: str
    seed: int
    created_at: str
    resolved_config_path: str
    environment_lock_path: str
    checkpoints_dir: str
    metrics_dir: str
    code_state_path: str | None = None
    status: str = "created"
    notes: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_paths(run_dir: Path | str) -> dict[str, Path]:
    """Run 目录内的标准落点。"""
    base = Path(run_dir)
    return {
        "root": base,
        "resolved_config": base / RESOLVED_CONFIG_NAME,
        "environment_lock": base / ENVIRONMENT_LOCK_NAME,
        "checkpoints": base / CHECKPOINTS_DIR,
        "metrics": base / METRICS_DIR,
        "code_state": base / CODE_STATE_NAME,
        "record": base / "run.json",
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    """读 JSON 对象（编码口径见 ``backend.jsonio``）；缺失 / 坏内容 / 非对象 ``None``。"""

    return read_json(path, default=None, require=dict)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """写 JSON 档案（格式化规则见 ``contracts/jsonio.dumps``）；``sort_keys`` 保持为真
    —— run 档案是提交物，键序稳定才让 diff 只显示真正的改动。"""

    write_json(path, payload, sort_keys=True)


def write_run(
    run_dir: Path | str,
    *,
    resolved_config: Mapping[str, Any],
    environment_lock: Mapping[str, Any],
    run_id: str | None = None,
    status: str = "created",
    notes: str = "",
    extra: Mapping[str, Any] | None = None,
) -> RunRecord:
    """把一份 Run 落盘（幂等 + **不可变**）。

    行为（V9 只读 + 版本化）：

    * 目录不存在 → 建目录 + 四件套 + ``run.json``；
    * 目录已存在且**输入指纹相同** → 直接返回既有记录（幂等，重跑不会污染）；
    * 目录已存在但**指纹不同** → 抛 :class:`RunImmutableError`（绝不就地覆盖，
      必须换新 ``run_id``）。
    """
    paths = run_paths(run_dir)
    paths["root"].mkdir(parents=True, exist_ok=True)
    incoming = dict(resolved_config.get("inputs") or {})
    existing = _read_json(paths["resolved_config"])

    if existing is not None:
        previous = dict(existing.get("inputs") or {})
        same_inputs = previous.get("digest") == incoming.get("digest")
        same_config = existing.get("config_digest") == resolved_config.get("config_digest")
        if not same_inputs or not same_config:
            raise RunImmutableError(
                f"{paths['root']} 已存在且内容不同（输入指纹"
                f" {str(previous.get('digest'))[:12]}… vs {str(incoming.get('digest'))[:12]}…；"
                f"整档摘要 {'一致' if same_config else '不一致'}）"
                "—— 改任何东西都要派生新 Run，不就地覆盖"
            )
        record = _read_json(paths["record"])
        if record:
            return RunRecord(**record)

    for name in ("checkpoints", "metrics"):
        paths[name].mkdir(parents=True, exist_ok=True)

    _write_json(paths["resolved_config"], resolved_config)
    _write_json(paths["environment_lock"], environment_lock)

    record = RunRecord(
        run_id=str(run_id or paths["root"].name),
        task=str(resolved_config.get("task", "")),
        robot_id=str(resolved_config.get("robot_id", "")),
        run_dir=str(paths["root"]),
        inputs_digest=str(incoming.get("digest", "")),
        config_digest=str(resolved_config.get("config_digest", "")),
        seed=int(incoming.get("seed", 0)),
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        resolved_config_path=str(paths["resolved_config"]),
        environment_lock_path=str(paths["environment_lock"]),
        checkpoints_dir=str(paths["checkpoints"]),
        metrics_dir=str(paths["metrics"]),
        code_state_path=str(paths["code_state"]) if paths["code_state"].is_file() else None,
        status=str(status),
        notes=str(notes),
        extra=dict(extra or {}),
    )
    _write_json(paths["record"], record.as_dict())
    return record


def load_run(run_dir: Path | str) -> RunRecord | None:
    """读回一份 Run 记录；目录不是 Run 则返回 ``None``。"""
    payload = _read_json(run_paths(run_dir)["record"])
    return RunRecord(**payload) if payload else None


def verify_run(run_dir: Path | str) -> dict[str, Any]:
    """**对账**：这份 Run 的四件套是否齐全、自洽、且没被动过。

    这就是 B9 的验收动作（"同 seed 可对账"）：重新规范化 ``inputs`` 求摘要，与登记值
    逐字比对；再检查依赖锁文件与四件套文件是否落盘。返回 ``{"ok": bool, "problems": [...]}``，
    **不抛异常**（对账工具不该在坏档案上崩掉）。
    """
    paths = run_paths(run_dir)
    problems: list[str] = []

    resolved = _read_json(paths["resolved_config"])
    if resolved is None:
        problems.append(f"缺 {RESOLVED_CONFIG_NAME}（或不可解析）")
        resolved = {}
    environment = _read_json(paths["environment_lock"])
    if environment is None:
        problems.append(f"缺 {ENVIRONMENT_LOCK_NAME}（或不可解析）")

    inputs = dict(resolved.get("inputs") or {})
    recorded = inputs.pop("digest", None)
    recomputed = canonical_digest(inputs) if inputs else None
    if recorded is None:
        problems.append("resolved-config 缺 inputs.digest")
    elif recomputed != recorded:
        problems.append(
            f"输入指纹不一致（登记 {str(recorded)[:12]}… vs 重算 {str(recomputed)[:12]}…）"
            "—— resolved-config 被改动过"
        )

    # 整档摘要：覆盖 inputs + resolved 的每一处，任一处被改动都逃不掉。
    body = {key: value for key, value in resolved.items() if key != "config_digest"}
    recorded_config = resolved.get("config_digest")
    if not body:
        pass  # 已在上面的"缺 resolved-config"里报过
    elif recorded_config is None:
        problems.append("resolved-config 缺 config_digest")
    elif canonical_digest(body) != recorded_config:
        problems.append(
            f"整档摘要不一致（登记 {str(recorded_config)[:12]}… vs 重算 "
            f"{canonical_digest(body)[:12]}…）—— 档案内容被改动过"
        )

    if environment is not None:
        lock = environment.get("dependency_lock") or {}
        if not lock.get("sha256"):
            problems.append("environment-lock 缺 dependency_lock.sha256（uv.lock 未登记）")
        elif lock.get("path") and file_digest(ROOT / str(lock["path"])) != lock.get("sha256"):
            problems.append("uv.lock 与登记摘要不一致（依赖锁已变）")
        if not (environment.get("adapter_venv") or {}).get("packages"):
            problems.append("environment-lock 未记录 adapter venv 依赖版本")

    for name, label in ((CHECKPOINTS_DIR, "checkpoints/"), (METRICS_DIR, "metrics/")):
        if not paths[name].is_dir():
            problems.append(f"缺 {label} 目录")

    return {
        "ok": not problems,
        "run_id": paths["root"].name,
        "inputs_digest": recorded,
        "task": resolved.get("task"),
        "robot_id": resolved.get("robot_id"),
        "problems": problems,
    }


# --------------------------------------------------------------------------------------
# 接线：训练任务创建时调用
# --------------------------------------------------------------------------------------
#: 已单独抽取为 inputs 的键，其余 config 键全部计入 ``params``（**任一改动都派生新 Run**）。
_INPUT_ONLY_KEYS = ("resolved_recipe", "recipe", "profile_id", "profile_mtime", "seed")


def run_inputs_from_task(*, contract_hash: str, config: Mapping[str, Any]) -> dict[str, Any]:
    """从训练任务的真实 ``config`` 抽取输入四元组（键名对齐 `backend/training/create.py`）。

    * ``recipe`` ← ``config["resolved_recipe"]``（**已解析**的 canonical recipe，非原始请求）；
    * ``profile`` ← ``profile_id`` + ``profile_mtime`` —— profile 被改但没换 id，指纹同样会变；
    * ``seed`` ← ``config["seed"]``；
    * ``params`` ← 其余全部 config 键（含 ``num_envs`` / ``max_iterations`` / ``mode`` 等）。

    这样"任何会影响训练结果的输入"都进了指纹，无需维护一份容易漏项的白名单。
    """
    recipe = config.get("resolved_recipe") or config.get("recipe") or {}
    if not isinstance(recipe, Mapping):
        recipe = {"value": recipe}
    profile = {key: config[key] for key in ("profile_id", "profile_mtime") if key in config}
    params = {
        key: value for key, value in config.items()
        if key not in _INPUT_ONLY_KEYS
    }
    return build_inputs(
        contract_hash=str(contract_hash),
        recipe=recipe,
        profile=profile,
        seed=int(config.get("seed") or 0),
        params=params,
    )


def create_run_for_task(
    run_dir: Path | str,
    *,
    contract: Any,
    config: Mapping[str, Any],
    task: str = "training",
) -> RunRecord:
    """**B9 接线入口**：训练任务创建时把这次 Run 的档案落盘，返回 Run 记录。

    刻意设计成"训练启动**之前**调用"：档案写不出来就不该开训 —— 否则会产出一份
    无法回溯的 Run（违背 V1 可追溯），而此时 worker 还没起，拦下来代价为零。
    """
    contract_hash = (
        contract.compute_hash() if hasattr(contract, "compute_hash") else str(contract)
    )
    robot_id = getattr(contract, "robot_id", None) or config.get("robot_id") or ""
    inputs = run_inputs_from_task(contract_hash=contract_hash, config=config)
    resolved_config = build_resolved_config(
        robot_id=str(robot_id),
        task=str(task),
        inputs=inputs,
        resolved=dict(config),
    )
    environment_lock = collect_environment_lock(
        seed=inputs["seed"], device=config.get("device"),
    )
    return write_run(
        run_dir,
        resolved_config=resolved_config,
        environment_lock=environment_lock,
        run_id=Path(run_dir).name,
    )
