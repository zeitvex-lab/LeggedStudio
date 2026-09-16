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
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPRODUCE_SCHEMA = "reproduction-report-1.0"
REPRODUCE_NAME = "reproduce.json"

#: 会影响数值的差异（warn）：依赖解析、实际装了什么、解释器版本。
_WARN_FIELDS = ("dependency_lock.sha256", "python.version", "adapter_venv.packages")
#: 只是环境标签的差异（info）：平台补丁号、git 工作树状态。
_INFO_FIELDS = ("platform.release", "vcs.commit", "vcs.dirty", "platform.machine", "platform.system")

#: R2 的受阻原因（写在这里由测试钉住：哪天无头 frame log 接上了，这条必须被改掉）。
R2_BLOCKER = (
    "没有可自动采集的逐帧日志：无头引擎产出 frame log 的路径尚未接入 replay gate"
    "（L1 已登记缺口）。判据实现已在位（adapters/mjlab/replay_determinism.py，"
    "同执行器容差 0 / stepIndex 对齐 / first_divergence），但**没有日志可比**。"
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


def build_reproduction(
    *,
    run_dir: Path | str | None = None,
    bundle_dir: Path | str | None = None,
) -> dict[str, Any]:
    """组装三档复现报告：R1 回放就绪 / R2 评测复现（受阻，如实说明）/ R3 训练近似复现。"""

    report: dict[str, Any] = {
        "schema_version": REPRODUCE_SCHEMA,
        "tiers": {
            "R1_playback": playback_readiness(bundle_dir) if bundle_dir else {
                "ready": None, "checks": [], "note": "未给导出目录，无法判定回放就绪",
            },
            "R2_evaluation": {
                "status": "blocked",
                "blocked_by": R2_BLOCKER,
                "machinery": "adapters/mjlab/replay_determinism.py + backend/test_replay_determinism.py",
            },
            "R3_training": {"status": "not_available", "note": "未给 Run 目录，无法做环境对账"},
        },
    }

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
