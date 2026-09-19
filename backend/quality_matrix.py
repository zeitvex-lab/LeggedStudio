"""B11 评测矩阵的产品侧：跑八指标/四档、落报告、给"达标才放行打包"提供判据。

## 分层

* **算**在适配器侧：`adapters/mjlab/quality_metrics.py`（需要 mujoco/onnxruntime，与 frame log、
  验收同源原语）；
* **接**在产品侧：本模块负责"找解释器 → 跑 → 收 JSON → 落报告 → 供门禁读"，
  解释器解析只用 `backend.adapter_runtime`（单一实现，不静默退回跑不了的解释器）。

## 报告放哪

``<workspace>/evaluation/<robot>__<policy>.json``：报告是**可复核的产物**（含八指标、
质量分、阈值、skipped 名单、生成时间），不是内存里的一次性结论 —— 门禁与导出门禁都读同一份文件，
"放行"依据的是磁盘上那份报告，而不是谁口述的分数。
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "adapters" / "mjlab" / "quality_metrics.py"

#: 打包放行的默认质量分下限（可被调用方覆盖；pack 的 bindings 里没有这一项，故用默认值 + 显式入参）
DEFAULT_MIN_SCORE = 0.5


from backend.paths import workspace_root as _workspace_root  # 唯一实现见 backend/paths.py


def reports_dir() -> Path:
    return _workspace_root() / "evaluation"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9_.-]+", "-", str(value).lower()).strip("-") or "policy"


def report_path(robot_id: str, policy_label: str, *, tier: str = "single", directory: Path | None = None) -> Path:
    return (directory or reports_dir()) / f"{_slug(robot_id)}__{_slug(policy_label)}__{_slug(tier)}.json"


def run_quality(
    *,
    package_dir: Path | str,
    tier: str = "single",
    policy_id: str | None = None,
    policy: str | None = None,
    cmd: str = "0.4,0,0",
    steps: int = 200,
    quality_min: float = DEFAULT_MIN_SCORE,
    magnitudes: str = "0.5,0.75,1.0",
    repeats: int = 1,
    interpreter: Path | str | None = None,
    timeout: float = 1200.0,
) -> dict[str, Any]:
    """跑一档评测并返回报告（与适配器脚本同一份 JSON，不在这里重新算）。

    B11-GAP-2（multi 档单策略降级）：本接口只接收**一个**策略（``policy_id``/``policy``），
    传 ``tier="multi"`` 时适配器侧只会摆出 1×1 矩阵（一策略 × 一指令），那格分数与 single
    同分 —— 为一个假矩阵多跑一遍 MuJoCo 是纯冗余。语义选择「**跳过并说明**」而不是
    「复用 single 结果」：复用会把单条件跑分冠以 multi 报告之名，是同一造假问题的另一种
    服装；跳过报告带 ``multi="skipped-single-policy"`` + ``reason``，``ok=False`` 且含
    blocker，`gate` 不放行（未评测 ≠ 达标）。真正多策略矩阵请直接用适配器脚本
    ``adapters/mjlab/quality_metrics.py``（``run_multi`` 接受策略列表）。
    """

    if tier == "multi":
        return {
            # 与适配器 run_multi 的 MATRIX_SCHEMA 同字面量（不 import，避免把 numpy 拖进控制面进程）
            "schema": "quality-matrix-1.0",
            "tier": "multi",
            "generated_at": now(),
            "package": str(package_dir),
            "policy": {"policy": policy, "policy_id": policy_id},
            "multi": "skipped-single-policy",
            "reason": (
                "multi 档是多策略×多指令矩阵；本接口只接收单个策略，跑出来是 1×1 冗余矩阵"
                "（与 single 同分）。需要跨策略对比请用适配器脚本 run_multi 传策略列表，"
                "或对各策略分别跑 single。"
            ),
            "requested": {"cmd": cmd, "steps": steps, "quality_min": quality_min},
            "skipped": ["multi 档按单策略跳过（skipped-single-policy）"],
            "ok": False,
            "blockers": ["multi 档未运行：单策略请求（skipped-single-policy，见 reason）——未评测 ≠ 达标"],
        }

    from backend.adapter_runtime import run_json_script

    args = ["--package", str(package_dir), "--tier", tier, "--cmd", cmd, "--steps", str(steps),
            "--quality-min", str(quality_min), "--magnitudes", magnitudes, "--repeats", str(repeats), "--json"]
    if policy_id:
        args += ["--policy-id", policy_id]
    if policy:
        args += ["--policy", policy]
    return run_json_script(SCRIPT, args, interpreter=interpreter, timeout=timeout)


def save_report(report: dict[str, Any], path: Path | None = None, *, directory: Path | None = None) -> Path:
    """落盘（供门禁与页面读同一份真值）。"""

    if path is None:
        package = Path(str(report.get("package") or "robot"))
        policy = report.get("policy") or {}
        label = str(policy.get("id") or policy.get("policy_id") or policy.get("path") or "policy")
        path = report_path(package.name, label, tier=str(report.get("tier") or "single"), directory=directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_report(path: Path | str) -> dict[str, Any] | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def list_reports(*, directory: Path | None = None) -> list[dict[str, Any]]:
    root = directory or reports_dir()
    if not root.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        report = load_report(path)
        if not isinstance(report, dict):
            continue
        items.append({
            "name": path.name,
            "path": str(path),
            "tier": report.get("tier") or "single",
            "package": report.get("package"),
            "policy": report.get("policy"),
            "quality_score": report.get("quality_score") or report.get("benchmark_score"),
            "ok": report.get("ok"),
            "generated_at": report.get("generated_at"),
        })
    return items


def score_of(report: dict[str, Any]) -> float | None:
    """报告的代表分：single/multi 用 `quality_score`，stress 用 `benchmark_score`，level 用通过层占比。"""

    if not isinstance(report, dict):
        return None
    tier = str(report.get("tier") or "single")
    if tier == "stress":
        value = report.get("benchmark_score")
    elif tier == "level":
        levels = report.get("levels") or []
        value = (sum(1 for level in levels if level.get("passed")) / len(levels)) if levels else None
    else:
        value = report.get("quality_score") or (report.get("aggregate") or {}).get("mean")
    return float(value) if isinstance(value, (int, float)) else None


def gate(report: dict[str, Any] | None, *, min_score: float = DEFAULT_MIN_SCORE) -> dict[str, Any]:
    """**放行判据**：报告存在且代表分 ≥ 下限才算过。

    没有报告**不算过**（"没评测"与"评测达标"必须分清）——这是"达标才放行打包"的关键：
    宁可拦下来让人去跑一次评测，也不要拿"没有坏消息"当好消息。
    """

    if report is None:
        return {
            "ok": False,
            "score": None,
            "min_score": float(min_score),
            "blockers": [f"没有质量报告（打包放行需要一份 ≥{min_score} 的评测；先跑 export/quality 评测）"],
            "generated_at": None,
        }
    score = score_of(report)
    blockers: list[str] = []
    if score is None:
        blockers.append("报告里没有可用的分数（quality_score / benchmark_score / levels 全缺）")
    elif score < min_score:
        blockers.append(f"质量分 {score:.4f} < 下限 {min_score}")
    if report.get("ok") is False and not blockers:
        blockers.extend(report.get("blockers") or ["评测报告自身判为未达标"])
    if report.get("skipped"):
        blockers.extend(f"未真正计算的指标：{item}" for item in report["skipped"] if "按上游口径记 1.0" in str(item))
    return {
        "ok": not blockers,
        "score": score,
        "min_score": float(min_score),
        "tier": report.get("tier"),
        "generated_at": report.get("generated_at"),
        "package": report.get("package"),
        "policy": report.get("policy"),
        "blockers": blockers,
    }


def gate_summary(verdict: dict[str, Any]) -> str:
    score = verdict.get("score")
    label = "达标" if verdict["ok"] else "未达标"
    shown = f"{score:.4f}" if isinstance(score, (int, float)) else "无分数"
    return f"[quality-gate] {label}（{shown} / 下限 {verdict['min_score']}）"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
