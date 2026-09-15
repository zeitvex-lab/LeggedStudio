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


def _policy_declaration(robot: str, policy_id: str) -> dict:
    """策略自己的 obs 声明（`simulation/config.json` 的 ``obs_dim`` / ``history_len``）。

    **这是策略级观测的既有真值** —— 契约的 ``observation`` 块是**包级**的，天然表达不了
    "同一台机器人的策略一个 45、一个 270"；而逐策略的声明早就在这里了。
    所以别在契约里再抄一份（那就是第二处真值）：**验它，别重复它**。
    """
    path = ROOT / "assets" / "robots" / robot / "simulation" / "config.json"
    try:
        config = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    # `policies` 与 `demo_policies` 都要找：演示策略（如 go2-baseline-164k）声明在后者里。
    for key in ("policies", "demo_policies"):
        for entry in config.get(key) or []:
            if isinstance(entry, dict) and str(entry.get("id")) == policy_id:
                return entry
    return {}


def audit() -> dict:
    """逐策略读 ONNX 输入宽度，并与**包级**声明、**策略级**声明双比。"""
    import onnxruntime as ort  # noqa: PLC0415  可选依赖，缺了由 main 给指示

    from backend import policy_artifacts as pa

    rows: list[dict] = []
    for declaration in pa.scan_declarations():
        robot = str(declaration["robot"])
        policy_id = str(declaration["policy_id"])
        package_dim = _declared_dimension(robot)
        entry = _policy_declaration(robot, policy_id)
        policy_dim = entry.get("obs_dim") if isinstance(entry.get("obs_dim"), int) else None
        policy_hist = entry.get("history_len") if isinstance(entry.get("history_len"), int) else None

        blob = pa.policy_blob_path(declaration)
        base = {"robot": robot, "policy": policy_id, "declared": package_dim,
                "policy_dim": policy_dim, "policy_history": policy_hist, "entry": bool(entry)}
        if blob is None:
            rows.append({**base, "width": None, "kind": "no_blob", "frames": None,
                         "policy_verdict": "no_blob"})
            continue
        try:
            session = ort.InferenceSession(str(blob), providers=["CPUExecutionProvider"])
            shapes = [tuple(item.shape) for item in session.get_inputs()]
            shape = session.get_inputs()[0].shape
            width = next((int(dim) for dim in reversed(shape) if isinstance(dim, int)), None)
        except Exception:  # noqa: BLE001  坏 onnx 如实计一类，不打断整轮
            rows.append({**base, "width": None, "kind": "unreadable", "frames": None,
                         "policy_verdict": "unreadable"})
            continue
        verdict = classify(package_dim, width)
        # 策略级判定：**单帧宽度 × history_len == onnx 宽度** 才算一致。
        # 别拿单帧数直接比堆叠宽度（我自己第一版就漏乘了 history_len，把 16 条堆叠误判成"声明错"）。
        frames = policy_hist or 1
        if len(shapes) > 1:
            # 多输入策略（obs + 历史缓冲 / 深度 / 循环隐状态）：**单输入口径不适用** —— 不当错。
            # 若策略已用 `aux_inputs` 把"外部提供的输入"逐项声明（名/形状/produced_by），
            # 则记为 `aux_declared`（**已accounted**）；否则记为 `multi_input`（待声明）。
            policy_verdict = "aux_declared" if entry.get("aux_inputs") else "multi_input"
        elif policy_dim is None:
            policy_verdict = "undeclared"
        elif policy_dim * frames == width:
            policy_verdict = "consistent"
        elif policy_dim == width:
            policy_verdict = "history_off"      # 声明叠了 history 帧，onnx 却只有单帧
        else:
            policy_verdict = "wrong"
        # **encoder 架构**（TRON1）：策略吃的是 latent，`obs_dim` 描述的是 **encoder 输入** ——
        # 那就别拿策略宽度去比，改拿 **encoder 的 onnx** 去验：encoder_in == obs_dim × history_len。
        # 实测：pf 30×10 = 300 = encoder 输入 ✓、sf 36×10 = 360 ✓、wf 28×10 = 280 ✓
        # （策略输入 36/42/34 = obs + latent(3) + command(3) ✓）。
        if policy_verdict == "wrong":
            # 注意用 `policy_aux_blobs()`（**现算**并带 source/hash）——
            # 声明里的 `aux_blobs` 只有 {role, declared}，直接读它会静默跳过（我第一版就是这么错的）。
            for aux in pa.policy_aux_blobs(declaration):
                if aux.get("role") != "encoder" or not aux.get("source"):
                    continue
                try:
                    encoder = ort.InferenceSession(str(ROOT / str(aux["source"])),
                                                   providers=["CPUExecutionProvider"])
                    enc_shape = encoder.get_inputs()[0].shape
                    enc_width = next((int(dim) for dim in reversed(enc_shape) if isinstance(dim, int)), None)
                except Exception:  # noqa: BLE001
                    continue
                if policy_dim and enc_width is not None and policy_dim * frames == enc_width:
                    policy_verdict = "encoder_consistent"
                    break
        # 包级块只是"标准单帧布局"：**策略级声明能解释的，就不算包级的错**。
        # encoder 架构尤其要放行：包级 30（obs 单帧）与策略输入 36（obs+latent+command）
        # 本来就不同 —— 拿包级去比策略输入是假警报。
        if verdict["kind"] == "mismatch" and policy_verdict in ("consistent", "encoder_consistent"):
            verdict = {"kind": "policy_explained", "frames": frames}
        rows.append({**base, "width": width, "inputs": len(shapes), **verdict,
                     "policy_verdict": policy_verdict})
    return {
        "total": len(rows),
        "match": [r for r in rows if r["kind"] == "match"],
        "history_stack": [r for r in rows if r["kind"] == "history_stack"],
        "policy_explained": [r for r in rows if r["kind"] == "policy_explained"],
        "mismatch": [r for r in rows if r["kind"] == "mismatch"],
        "policy_ok": [r for r in rows if r["policy_verdict"] in ("consistent", "encoder_consistent")],
        "policy_encoder": [r for r in rows if r["policy_verdict"] == "encoder_consistent"],
        "policy_wrong": [r for r in rows if r["policy_verdict"] in ("wrong", "history_off")],
        "policy_undeclared": [r for r in rows if r["policy_verdict"] == "undeclared"],
        # **未声明**的多输入策略（已用 aux_inputs 声明的不算 —— 否则报告会自相矛盾：
        # 同一条既出现在"已声明"又出现在"未声明"里，我第一版就是这么错的）。
        "multi_input": [r for r in rows
                        if r.get("inputs", 1) > 1 and r["policy_verdict"] != "aux_declared"],
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
          f" / policy_explained {len(report['policy_explained'])}"
          f" / mismatch {len(report['mismatch'])}")
    print(f"策略级声明（config.json 的 obs_dim/history_len）：一致 {len(report['policy_ok'])}"
          f" / 不一致 {len(report['policy_wrong'])} / 未声明 {len(report['policy_undeclared'])}")
    if report["policy_wrong"]:
        print("\n**策略自己的 obs 声明与它的 onnx 不符**（声明或 blob 有一处是错的）：")
        for row in report["policy_wrong"]:
            print(f"  ✗ {row['robot']:<22} {row['policy']:<28} 声明 {row['policy_dim']}"
                  f"（history {row['policy_history']}） 实际 {row['width']}  [{row['policy_verdict']}]")
    if report["policy_undeclared"]:
        print(f"\n策略级未声明 obs_dim：{len(report['policy_undeclared'])} 条"
              "（包级块表达不了逐策略布局，这些只能靠策略级声明）")
        for row in report["policy_undeclared"][:12]:
            print(f"  ? {row['robot']:<22} {row['policy']:<28} 实际 {row['width']}")
    aux_declared = [row for row in report["rows"] if row["policy_verdict"] == "aux_declared"]
    if aux_declared:
        print(f"\n多输入且**已用 aux_inputs 声明**：{len(aux_declared)} 条"
              "（名/形状/来源逐项在策略声明里，可核）")
        for row in aux_declared:
            print(f"  ✓ {row['robot']:<22} {row['policy']:<28} inputs={row.get('inputs')}"
                  f" 首输入={row['width']}")
    if report["multi_input"]:
        print(f"\n**未声明**的多输入策略：{len(report['multi_input'])} 条"
              "（单输入口径不适用，应补 aux_inputs）")
        for row in report["multi_input"]:
            print(f"  ? {row['robot']:<22} {row['policy']:<28} inputs={row.get('inputs')}"
                  f" 首输入={row['width']}")
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
