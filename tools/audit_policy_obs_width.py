"""契约声明宽度 vs **策略真实输入宽度**（ONNX）—— 那把一直没上的尺子。

## 为什么必须单独查这一条

观测五元组/组件声明是**包级**的（`contract.observation.dimension`），而**策略是逐个的**：
同一个包里可以有 45、270（=45×6 历史堆叠）、450（MoE）等不同输入宽度。于是
"组件之和 == 声明宽度"只能证明**声明自洽**，**不能**证明它等于策略输入 ——
2026-09-14 我就用前者冒充了后者（给 lite3/m20/b2 补五元组时），差点把 `history` 取错：
`rl_sar` 的 `observations_history: [0,1,2,3,4,5]` 是**6 帧堆叠**，其 himloco 策略输入正是
45×6=270 / 57×6=342。所以判 `history` 必须看**策略输入宽度 ÷ 单帧宽度**。

## 三类结论

- ``match``：宽度 == 声明宽度（单帧）；
- ``history_stack``：宽度是声明宽度的整数倍 → **N 帧堆叠**（`history = N`）；
- ``mismatch``：既不等也不是整数倍 → 声明与策略对不上（**要么声明错、要么布局错**）。

用法（需要 onnxruntime，用训练适配器的 venv）::

    adapters/mjlab/.venv/Scripts/python.exe tools/audit_policy_obs_width.py
    ... --strict    # 有 mismatch 即 exit 1（match/history_stack 不算问题）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def classify(declared: int | None, width: int | None) -> dict:
    """单条策略的三分类（纯函数，便于测试）。"""
    if not declared or width is None:
        return {"kind": "unknown", "frames": None}
    if width == declared:
        return {"kind": "match", "frames": 1}
    if width % declared == 0 and width // declared > 1:
        return {"kind": "history_stack", "frames": width // declared}
    return {"kind": "mismatch", "frames": None}


def _declared_dimension(robot: str) -> int | None:
    path = ROOT / "assets" / "robots" / robot / "contract_v3.json"
    try:
        contract = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    value = (contract.get("observation") or {}).get("dimension")
    return int(value) if isinstance(value, (int, float)) else None


def audit() -> dict:
    """逐策略读 ONNX 输入宽度并分类。"""
    import onnxruntime as ort  # noqa: PLC0415  可选依赖，缺了由 main 给指示

    from backend import policy_artifacts as pa

    rows: list[dict] = []
    for declaration in pa.scan_declarations():
        robot = str(declaration["robot"])
        declared = _declared_dimension(robot)
        blob = pa.policy_blob_path(declaration)
        if blob is None:
            rows.append({"robot": robot, "policy": declaration["policy_id"], "declared": declared,
                         "width": None, "kind": "no_blob", "frames": None})
            continue
        try:
            session = ort.InferenceSession(str(blob), providers=["CPUExecutionProvider"])
            shape = session.get_inputs()[0].shape
            width = next((int(dim) for dim in reversed(shape) if isinstance(dim, int)), None)
        except Exception:  # noqa: BLE001  坏 onnx 如实计一类，不打断整轮
            rows.append({"robot": robot, "policy": declaration["policy_id"], "declared": declared,
                         "width": None, "kind": "unreadable", "frames": None})
            continue
        verdict = classify(declared, width)
        rows.append({"robot": robot, "policy": declaration["policy_id"], "declared": declared,
                     "width": width, **verdict})
    return {
        "total": len(rows),
        "match": [r for r in rows if r["kind"] == "match"],
        "history_stack": [r for r in rows if r["kind"] == "history_stack"],
        "mismatch": [r for r in rows if r["kind"] == "mismatch"],
        "rows": rows,
    }


def main() -> int:
    try:
        report = audit()
    except ImportError:
        print("需要 onnxruntime：请用训练适配器的 venv 运行，例如\n"
              "  adapters/mjlab/.venv/Scripts/python.exe tools/audit_policy_obs_width.py")
        return 2

    print(f"策略 {report['total']} 条："
          f"match {len(report['match'])} / history_stack {len(report['history_stack'])}"
          f" / mismatch {len(report['mismatch'])}")
    if report["history_stack"]:
        print("\n历史堆叠（策略输入 = 声明宽度 × N 帧）：")
        for row in report["history_stack"]:
            print(f"  {row['robot']:<22} {row['policy']:<28} {row['declared']} × {row['frames']}"
                  f" = {row['width']}")
    if report["mismatch"]:
        print("\n**对不上**（既不等、也不是整数倍）—— 声明或布局有一处是错的：")
        for row in report["mismatch"]:
            print(f"  ✗ {row['robot']:<22} {row['policy']:<28} 声明 {row['declared']}"
                  f"  实际 {row['width']}")
    unknown = [r for r in report["rows"] if r["kind"] not in ("match", "history_stack", "mismatch")]
    if unknown:
        print(f"\n无法判定 {len(unknown)} 条：")
        for row in unknown:
            print(f"  ? {row['robot']:<22} {row['policy']:<28} {row['kind']}")
    return 1 if (report["mismatch"] and "--strict" in sys.argv) else 0


if __name__ == "__main__":
    raise SystemExit(main())
