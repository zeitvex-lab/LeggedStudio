"""B12 后半：复现三档（R1 看 / R2 用 / R3 训）的报告与判据。

## 三档各是什么，以及**今天**各自能证到什么程度

| 档 | 含义 | 判据落点 | 现状 |
|---|---|---|---|
| **R1** | 复现"看"：把训练结果放回来看得见 | :func:`playback_readiness`（策略 blob 可加载 + 契约可校验 + 包清单在） | **可执行** |
| **R2** | 复现"用"：重跑评测得**同一分数** | `adapters/mjlab/replay_determinism.compare_frame_logs`（同执行器容差 0、`stepIndex` 对齐、`first_divergence`） | **受阻**：判据实现已在位，但**没有可自动采集的逐帧日志**（无头引擎未接进来，属 L1 已登记缺口）——如实标 `blocked`，不假装能跑 |
| **R3** | 复现"训"：同 seed **近似**复现 | 本模块 :func:`build_reproduction`（环境对账：`uv.lock` sha256 / adapter venv 逐包版本 / python / 平台 / git） | **可执行** |

## 为什么 R3 只能是"近似"，而报告必须把差别列出来

同 seed 只能保证**采样序列**可复现，不保证**数值逐位**一致：换了 `uv.lock`（依赖解析变了）、
换了 adapter venv 里的 torch/mujoco（内核实现变了）、换了平台（浮点与并行变了），结果就会漂。
所以 R3 的产物不是"我们复现了"这句口号，而是一份**可复核的对账**：

* 逐项比较"当时记录的"与"现在实测的"（同一 :func:`backend.training.runs.collect_environment_lock`）；
* 每个差异标 severity：`warn`（会影响数值：uv.lock / 包版本 / python 版本）与 `info`
  （多半只是环境标签变了：平台 release / git 状态）；
* 结论 `exact` / `approximate` —— **有 warn 级差异时绝不自称 exact**（V6 诚实）。

风格：纯 stdlib（onnxruntime 按需 import，不可用时如实记 `skipped` 而不是假装检查过）。
"""

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPRODUCE_SCHEMA = "reproduction-report-1.0"
REPRODUCE_NAME = "reproduce.json"

#: 会影响数值的差异（warn）：依赖解析、实际装了什么、解释器版本。
_WARN_FIELDS = ("dependency_lock.sha256", "python.version", "adapter_venv.packages")
#: 只是环境标签的差异（info）：平台补丁号、git 工作树状态。
_INFO_FIELDS = ("platform.release", "vcs.commit", "vcs.dirty", "platform.machine", "platform.system")

#: R2 的判据机器（产出端 + 门禁）—— 2026-09-16 补齐，不再是缺口。
R2_MACHINERY = (
    "无头产出端 adapters/mjlab/frame_log.py（与验收同源原语，产出与浏览器 frameLog 同形）+ "
    "门禁 tools/replay_gate.py --produce（**两个独立进程**各跑一遍再比对）"
)
#: R2 未跑时的说明（不是 blocked —— 是没要求跑；两者必须分清）。
R2_NOT_RUN = (
    "未跑（导出时未加 --replay）—— 判据已就位且可执行："
    "python tools/replay_gate.py --produce --package <包> --policy <onnx> --steps 60。"
    "**未跑 ≠ 通过**，故状态记 not_run。"
)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def _dig(data: Any, dotted: str) -> Any:
    """按点路径取值（缺失返回 None）。"""

    current = data
    for part in dotted.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


# --------------------------------------------------------------------------------------
# R3：环境对账（同 seed 近似复现）
# --------------------------------------------------------------------------------------
def _environment_gaps(recorded: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    """逐项比较两份 environment-lock，产出**带 severity 的差异清单**。"""

    gaps: list[dict[str, Any]] = []

    def add(field: str, severity: str, note: str = "") -> None:
        gaps.append({
            "field": field,
            "severity": severity,
            "recorded": _dig(recorded, field),
            "current": _dig(current, field),
            "note": note,
        })

    for field in ("dependency_lock.sha256", "python.version", "python.implementation",
                  "platform.system", "platform.machine", "platform.release"):
        if _dig(recorded, field) != _dig(current, field):
            severity = "warn" if field in _WARN_FIELDS else "info"
            add(field, severity)

    recorded_packages = dict(_dig(recorded, "adapter_venv.packages") or {})
    current_packages = dict(_dig(current, "adapter_venv.packages") or {})
    for name in sorted(set(recorded_packages) | set(current_packages)):
        if recorded_packages.get(name) != current_packages.get(name):
            gaps.append({
                "field": f"adapter_venv.packages.{name}",
                "severity": "warn",
                "recorded": recorded_packages.get(name),
                "current": current_packages.get(name),
                "note": "训练内核实现变了，同 seed 也只能期望近似",
            })
    if _dig(recorded, "adapter_venv.path") != _dig(current, "adapter_venv.path"):
        add("adapter_venv.path", "info", "换了个 venv 跑对账")
    if not _dig(current, "adapter_venv.exists"):
        add("adapter_venv.exists", "warn", "当时那套 venv 现在不在了 ⇒ 连近似复现都做不到")

    recorded_vcs = _dig(recorded, "vcs") or {}
    current_vcs = _dig(current, "vcs") or {}
    for field in ("commit", "dirty"):
        if recorded_vcs.get(field) != current_vcs.get(field):
            gaps.append({
                "field": f"vcs.{field}",
                "severity": "info",
                "recorded": recorded_vcs.get(field),
                "current": current_vcs.get(field),
                "note": "代码状态变了（数据/脚本改动同样会影响数值，按 info 记录）",
            })
    return gaps


def evaluation_replay(
    *,
    package_dir: Path | str,
    policy: str | None = None,
    policy_id: str | None = None,
    cmd: str = "0.4,0,0",
    seed: int = 7,
    steps: int = 60,
    seed_probe: int | None = 99,
    venv: Path | str | None = None,
    timeout: float = 900.0,
) -> dict[str, Any]:
    """R2：同一条策略在**两个独立进程**里重跑，逐帧一致才算「复现得同一结果」。

    判据实现只有一处（`tools/replay_gate.py --produce` → 产出端 `adapters/mjlab/frame_log.py`），
    本函数只是调用方 + **两条诚实闸门**：

    1. **策略必须落在被跑的包内**（`policy.resolution.inside_package`）。在本机（有仓库）跑一份
       Bundle 时，出库索引可能把策略解析到**仓库里的同名文件** —— 那样「这份 Bundle 在干净机器上
       可复现」就是假的。落在包外 ⇒ 记 `blocked` 并写明原因，不给绿。
    2. 环境不满足（缺适配器 venv / 无法 import mujoco）⇒ `blocked`（把退出码 2 的原文照登），
       **不是 fail** —— 「没跑成」与「跑了不一致」是两件事。
    """

    import subprocess

    command = [
        sys.executable, str(ROOT / "tools" / "replay_gate.py"), "--produce",
        "--package", str(package_dir), "--cmd", cmd, "--steps", str(steps),
        "--seed", str(seed), "--min-frames", str(min(50, max(1, steps))), "--json",
    ]
    if policy_id:
        command += ["--policy-id", policy_id]
    if policy:
        command += ["--policy", policy]
    if seed_probe is not None:
        command += ["--seed-probe", str(seed_probe)]
    if venv:
        command += ["--venv", str(venv)]

    try:
        completed = subprocess.run(command, capture_output=True, text=True, cwd=str(ROOT), timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "blocked", "blocked_by": f"无头重跑超时（>{timeout:.0f}s）", "machinery": R2_MACHINERY}

    raw = (completed.stdout or "").strip()
    if completed.returncode not in (0, 1) or not raw:
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()[-4:]
        return {
            "status": "blocked",
            "blocked_by": "环境/参数不满足，未能产出可比较的日志：" + " | ".join(detail),
            "machinery": R2_MACHINERY,
        }
    try:
        summary = json.loads(raw)
    except json.JSONDecodeError:
        return {"status": "blocked", "blocked_by": "门禁输出不是 JSON（未产出结论）", "machinery": R2_MACHINERY}

    runs = summary.get("runs") or {}
    policy_info = runs.get("policy") or {}
    resolution = policy_info.get("resolution") or {}
    report: dict[str, Any] = {
        "status": "pass" if completed.returncode == 0 else "fail",
        "machinery": R2_MACHINERY,
        "determinism": summary.get("determinism"),
        "seed_sensitivity": summary.get("seed_sensitivity"),
        "runs": runs,
        "inputs": {"package": str(package_dir), "policy": policy, "policy_id": policy_id,
                   "cmd": cmd, "seed": seed, "steps": steps},
    }
    if resolution and not resolution.get("inside_package", True):
        report["status"] = "blocked"
        report["blocked_by"] = (
            f"策略解析落在**被跑的包之外**（{policy_info.get('path')}）：本机跑得出结果，"
            "但它不是在「这份包」内复现的 —— 干净机器上跑不起来。"
            "把策略放进包内（如 simulation/policies/）或用 --policy 指向包内路径后重跑。"
        )
    return report


def build_reproduction(
    *,
    run_dir: Path | str | None = None,
    bundle_dir: Path | str | None = None,
    replay: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """组装三档复现报告：R1 回放就绪 / R2 评测复现（受阻，如实说明）/ R3 训练近似复现。"""

    report: dict[str, Any] = {
        "schema_version": REPRODUCE_SCHEMA,
        "tiers": {
            "R1_playback": playback_readiness(bundle_dir) if bundle_dir else {
                "ready": None, "checks": [], "note": "未给导出目录，无法判定回放就绪",
            },
            "R2_evaluation": {
                "status": "not_run",
                "reason": R2_NOT_RUN,
                "machinery": R2_MACHINERY,
            },
            "R3_training": {"status": "not_available", "note": "未给 Run 目录，无法做环境对账"},
        },
    }

    if replay is not None:
        report["tiers"]["R2_evaluation"] = evaluation_replay(**replay)

    if run_dir is None:
        return report

    from backend.training import runs

    directory = Path(run_dir).expanduser()
    record = runs.load_run(directory)
    if record is None:
        report["tiers"]["R3_training"] = {"status": "not_available", "note": f"不是 Run 目录（缺 run.json）：{directory}"}
        return report

    recorded = _read_json(Path(record.environment_lock_path)) or {}
    recorded_seed = recorded.get("seed", record.seed)
    # 用**当时那套 venv**重算，才有比较意义（venv 没了就如实记 exists=false）。
    current = runs.collect_environment_lock(
        seed=int(recorded_seed),
        device=recorded.get("device"),
        adapter_venv=(recorded.get("adapter_venv") or {}).get("path"),
    )
    gaps = _environment_gaps(recorded, current)
    warn_count = sum(1 for gap in gaps if gap["severity"] == "warn")
    report["tiers"]["R3_training"] = {
        "status": "exact" if warn_count == 0 else "approximate",
        "run_id": record.run_id,
        "seed": record.seed,
        "inputs_digest": record.inputs_digest,
        "config_digest": record.config_digest,
        "robot_id": record.robot_id,
        "recorded": recorded,
        "current": current,
        "gaps": gaps,
        "warn_count": warn_count,
        "note": (
            "同 seed 近似复现：采样序列可复现，数值逐位一致**不保证** —— "
            "warn 级差异会改变数值，逐项列在 gaps 里"
        ),
    }
    return report


# --------------------------------------------------------------------------------------
# R1：回放就绪
# --------------------------------------------------------------------------------------
def playback_readiness(bundle_dir: Path | str | None) -> dict[str, Any]:
    """R1：这个导出物能不能"看"（把策略放回来看得见）。

    只列**白纸黑字可查的**检查项：策略 blob 在不在、能不能被 onnxruntime 载入（不可用则记
    ``skipped``，不假装检查过）、契约能不能过既有校验、包清单在不在。**不做**任何"应该能跑"
    的推断 —— R1 的判据是"回放所需的最小集合齐备且可解析"，不是"我猜它能跑"。
    """

    if bundle_dir is None:
        return {"ready": None, "checks": [], "note": "未给导出目录"}
    root = Path(bundle_dir).expanduser()
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str, *, required: bool = True) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail, "required": required})

    onnx_files = sorted(root.rglob("*.onnx"))
    check("policy_blob", bool(onnx_files), f"找到 {len(onnx_files)} 个 onnx：{[p.name for p in onnx_files][:3]}")

    if onnx_files:
        try:
            import onnxruntime  # noqa: F401

            import onnx

            model = onnx.load(str(onnx_files[0]))
            shapes = [
                [dim.dim_value for dim in tensor.type.tensor_type.shape.dim]
                for tensor in list(model.graph.input) + list(model.graph.output)
            ]
            check("onnx_loadable", True, f"{onnx_files[0].name} 可载入，输入输出形状 {shapes}")
        except ImportError as exc:
            checks.append({
                "name": "onnx_loadable", "ok": True, "required": False,
                "detail": f"skipped（缺 {exc.name or 'onnxruntime'}）—— 未检查，不算通过也不算失败",
            })
        except Exception as exc:
            check("onnx_loadable", False, f"{onnx_files[0].name} 载入失败：{type(exc).__name__}: {exc}")

    contract_path = next((path for path in (root / "morphology" / "contract.json", root / "contract.json") if path.is_file()), None)
    v3_path = next((path for path in (root / "morphology" / "contract_v3.json", root / "contract_v3.json") if path.is_file()), None)
    if contract_path is None and v3_path is None:
        check("contract", False, "既没有 contract.json 也没有 contract_v3.json")
    else:
        problems: list[str] = []
        if contract_path is not None:
            try:
                from contracts.validator import validate_contract_file

                result = validate_contract_file(str(contract_path))
                problems.extend(item.message for item in result.errors)
            except Exception as exc:
                problems.append(f"{type(exc).__name__}: {exc}")
        check("contract", not problems, "契约校验通过" if not problems else f"契约问题：{problems[:2]}")

    package_manifest = next((path for path in (root / "morphology" / "robot_package.json", root / "robot_package.json") if path.is_file()), None)
    check("package_manifest", package_manifest is not None, str(package_manifest or "缺 robot_package.json"))

    ready = all(item["ok"] for item in checks if item.get("required"))
    return {
        "ready": ready,
        "checks": checks,
        "note": "R1 只判『回放所需最小集合齐备且可解析』；浏览器/服务端回放本身由既有页面与仿真入口承担",
    }


def summarise(report: dict[str, Any]) -> dict[str, Any]:
    """给 `verify bundle` 用的摘要（不改变导出物自身的 ok 语义：完整性 ≠ 可复现性）。"""

    tiers = report.get("tiers") or {}
    r3 = tiers.get("R3_training") or {}
    r1 = tiers.get("R1_playback") or {}
    r2 = tiers.get("R2_evaluation") or {}
    return {
        "R1_playback": r1.get("ready"),
        "R2_evaluation": r2.get("status"),
        "R3_training": r3.get("status"),
        "R3_gaps": len(r3.get("gaps") or []),
        "R3_warn": r3.get("warn_count"),
    }


def tier_lines(report: dict[str, Any]) -> list[str]:
    """人读的三档摘要（CLI 用；不进导出物 —— 导出物里只放结构化结论）。"""

    tiers = report.get("tiers") or {}
    r1 = tiers.get("R1_playback") or {}
    r2 = tiers.get("R2_evaluation") or {}
    r3 = tiers.get("R3_training") or {}
    r1_label = "是" if r1.get("ready") else ("否" if r1.get("ready") is not None else "未判")
    lines = [f"R1 回放就绪：{r1_label}（{len(r1.get('checks') or [])} 项检查）"]
    r2_line = f"R2 评测复现：{r2.get('status')}"
    if r2.get("blocked_by"):
        r2_line += f" —— {r2['blocked_by']}"
    elif r2.get("reason"):
        r2_line += f" —— {r2['reason']}"
    lines.append(r2_line)
    r3_line = f"R3 训练复现：{r3.get('status')}"
    if r3.get("gaps") is not None:
        r3_line += f"（差异 {len(r3['gaps'])} 条，影响数值 {r3.get('warn_count')} 条）"
    lines.append(r3_line)
    note = (r2.get("seed_sensitivity") or {}).get("note")
    if note:
        lines.append(f"seed 敏感性：{note}")
    return lines


def default_reproduce_path(bundle_dir: Path | str) -> Path:
    return Path(bundle_dir).expanduser() / REPRODUCE_NAME


def write_reproduction(bundle_dir: Path | str, report: dict[str, Any]) -> Path:
    target = default_reproduce_path(bundle_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def platform_summary() -> str:
    """一行平台标签（报告/日志里用，便于人眼核对）。"""

    return f"{platform.system()} {platform.release()} {platform.machine()} / python {platform.python_version()}"
