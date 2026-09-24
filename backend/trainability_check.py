"""导入后**自动冒烟**：把"静态就绪"升级为"实测可训"。

`backend/family_readiness.py` 回答的是静态问题（契约/族/关节/执行器/PD/质量/观测骨架）；
本模块回答**实测**问题——这台机器人走通用任务路径**真训 1 iter**过不过。判据链与
`tools/validate_family_trainability.py` 同一份实现（该工具改为调这里）：

    rc == 0  且  生效配置 == 预览  且  ONNX 导出  且  解析后的地形 == 目标档

结果落包内 `trainability.json`（导入包在 workspace，不污染仓库），供：
* 页面就绪卡显示"实测可训 / 待测 / 失败 + 依据"；
* `GET /api/models/packages/{id}/inspection` 的 `trainability` 字段。

为什么要有它：静态就绪判红/判绿都可能与真跑不一致（本仓两次真实事故——`m20-dreamwaq` 实体
能建、环境才炸；go2/go2w 的 margin 只在真建环境时才撞 warp 守卫），而"一键导入 ⇒ 一键开训"
的承诺必须由**真跑**背书。
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
RECORD_NAME = "trainability.json"
#: 单次冒烟上限（1 iter / 2 envs，CPU 上约 1~2 分钟；给足余量即可）
DEFAULT_TIMEOUT_S = 1800


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(package_root: Path) -> dict | None:
    """读包内实测记录（没有就返回 None——"没测过"与"测失败"是两回事）。"""

    path = Path(package_root) / RECORD_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write(package_root: Path, payload: dict) -> None:
    path = Path(package_root) / RECORD_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _run_worker(config: dict, contract: Any, output: Path, timeout_s: int) -> subprocess.CompletedProcess:
    from adapters.mjlab.native_adapter import DEFAULT_SOURCE
    from contracts.path_bootstrap import adapter_python

    (output / "request.json").write_text(json.dumps(config), encoding="utf-8")
    contract.to_json_file(str(output / "contract.json"))
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [str(adapter_python()), "-m", "adapters.mjlab.native_worker",
         "--source", str(DEFAULT_SOURCE), "--config", str(output / "request.json"),
         "--contract", str(output / "contract.json"), "--output", str(output)],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout_s,
    )


def check(
    package_root: Path, *, terrain: str, task: str, timeout_s: int = DEFAULT_TIMEOUT_S,
    runner: Callable[[dict, Any, Path, int], subprocess.CompletedProcess] | None = None,
    write_record: bool = True,
) -> dict:
    """走通用任务路径（不带档案）真跑一次；返回实测结论并落 `trainability.json`。"""

    from backend.training.models import CreateTrainingRequest
    from backend.training.service import prepare_training_config
    from backend.training_config_helpers import dump_schema_via_worker

    package_root = Path(package_root)
    started = time.time()
    record: dict[str, Any] = {
        "schema": "trainability-1.0", "checked_at": _now(), "package_root": str(package_root),
        "terrain": terrain, "task": task, "status": "failed", "reason": "",
        "returncode": None, "effective_matches_preview": None, "onnx_exported": None,
        "resolved_terrain": None, "duration_s": None, "tail": "",
    }
    with tempfile.TemporaryDirectory(prefix=f"ls-traincheck-{package_root.name}-") as tmp:
        out = Path(tmp)
        try:
            # 契约读取也在 try 内：包坏了（缺契约/JSON 坏）同样记成"实测不过 + 原因"，
            # 不把异常抛给调用方（后台线程尤其不能抛）。
            contract_data = json.loads((package_root / "contract_legacy_v2.json").read_text(encoding="utf-8-sig"))
            request = CreateTrainingRequest(
                contract=contract_data, profile_id=None, task_name=task, terrain_type=terrain,
                smoke=True, num_envs=2, max_iterations=1, num_steps=4, num_minibatches=1,
                device="auto", overrides={"runner.num_steps_per_env": 8},
            )
            contract, config = prepare_training_config(request)
            package = config["robot_package"]
            preview = dump_schema_via_worker(
                contract.robot_id, "", {}, package["package_root"],
                training_config=config, contract=contract.model_dump(mode="json"))
            result = (runner or _run_worker)(config, contract, out, timeout_s)
        except subprocess.TimeoutExpired:
            record.update({"status": "failed", "reason": f"冒烟超时（>{timeout_s}s）",
                           "duration_s": round(time.time() - started, 1)})
            if write_record:
                _write(package_root, record)
            return record
        except Exception as exc:  # noqa: BLE001 — 装配失败也是"实测不过"，如实记原因
            record.update({"status": "failed", "reason": f"{type(exc).__name__}: {exc}",
                           "duration_s": round(time.time() - started, 1)})
            if write_record:
                _write(package_root, record)
            return record

        effective = None
        if (out / "effective-config.json").is_file():
            effective = json.loads((out / "effective-config.json").read_text(encoding="utf-8-sig"))
        resolved = ((config.get("resolved_recipe") or {}).get("environment") or {}).get("terrain_type")
        matched = bool(effective) and effective.get("environment") == preview.get("environment")
        record.update({
            "returncode": result.returncode,
            "effective_matches_preview": matched,
            "onnx_exported": (out / "exported" / "policy.onnx").is_file(),
            "resolved_terrain": resolved,
            "duration_s": round(time.time() - started, 1),
        })
        problems = []
        if result.returncode != 0:
            problems.append(f"退出码 {result.returncode}")
        if not matched:
            problems.append("生效配置 != 预览")
        if not record["onnx_exported"]:
            problems.append("ONNX 未导出")
        if resolved != terrain:
            problems.append(f"解析地形 {resolved!r} != 目标 {terrain!r}")
        if problems:
            record.update({"status": "failed", "reason": "；".join(problems),
                           "tail": (result.stdout + result.stderr)[-800:]})
        else:
            record.update({"status": "passed", "reason": ""})
        if write_record:
            _write(package_root, record)
        return record


def pick_target(package_root: Path) -> tuple[str, str] | None:
    """选这台机型的实测目标（族 ready 档里的第一档 + 该档对应的任务）。

    静态判红（没族/缺关节/缺 PD…）⇒ 返回 None——那种情况**不该起冒烟**，直接如实报静态原因。
    """

    from backend.family_readiness import readiness
    from backend.skill_registry import task_variants

    verdict = readiness(Path(package_root))
    if verdict.get("verdict") != "ready":
        return None
    terrains = [str(item) for item in verdict.get("trainable_terrain_profiles") or []]
    if not terrains:
        return None
    for terrain in terrains:
        for task_id, spec in task_variants().items():
            if str((spec or {}).get("terrain") or "") == terrain:
                return terrain, str(task_id)
    return None


def skipped_record(package_root: Path) -> dict:
    """静态就绪没过 ⇒ 不冒烟，如实写下"为什么没测"。"""

    from backend.family_readiness import readiness

    verdict = readiness(Path(package_root))
    failing = [str(item.get("summary")) for item in verdict.get("checks") or [] if item.get("status") != "pass"]
    record = {
        "schema": "trainability-1.0", "checked_at": _now(), "package_root": str(package_root),
        "terrain": None, "task": None, "status": "not_ready",
        "reason": "静态就绪未通过：" + ("；".join(failing) or "未知"), "returncode": None,
        "effective_matches_preview": None, "onnx_exported": None, "resolved_terrain": None,
        "duration_s": 0.0, "tail": "",
    }
    _write(Path(package_root), record)
    return record


def run(package_root: Path, *, timeout_s: int = DEFAULT_TIMEOUT_S) -> dict:
    """静态就绪 → 选档 → 真跑；任何一步失败都如实落记录（不抛给调用方）。"""

    package_root = Path(package_root)
    if not (package_root / "robot_package.json").is_file():
        record = {"schema": "trainability-1.0", "checked_at": _now(), "package_root": str(package_root),
                  "terrain": None, "task": None, "status": "not_ready", "reason": "不是机器人包（缺 robot_package.json）",
                  "returncode": None, "effective_matches_preview": None, "onnx_exported": None,
                  "resolved_terrain": None, "duration_s": 0.0, "tail": ""}
        return record
    target = pick_target(package_root)
    if target is None:
        return skipped_record(package_root)
    terrain, task = target
    return check(package_root, terrain=terrain, task=task, timeout_s=timeout_s)


def schedule(package_root: Path, *, timeout_s: int = DEFAULT_TIMEOUT_S) -> bool:
    """后台跑一次（导入后自动用）。返回是否真的起了线程。

    不另立状态机：进度就是"包内有没有 `trainability.json`"——页面据此显示"待测/已测"。
    """

    package_root = Path(package_root)

    def _worker() -> None:
        try:
            run(package_root, timeout_s=timeout_s)
        except Exception:  # noqa: BLE001 — 后台线程不许把异常抛给服务进程
            pass

    thread = threading.Thread(target=_worker, name=f"trainability-{package_root.name}", daemon=True)
    thread.start()
    return thread.is_alive()


__all__ = ["RECORD_NAME", "check", "load", "pick_target", "run", "schedule", "skipped_record"]
