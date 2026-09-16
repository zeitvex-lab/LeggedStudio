#!/usr/bin/env python3
"""确定性回放门禁（L1 / G2）：比对两份 frame log，不一致即非 0 退出。

**它填的是哪个洞**：`deterministic_replay` 能力此前只能记 `partial`——"两次跑同一策略
逐帧是否一致"没有判据。判据实现只有一处：`adapters/mjlab/replay_determinism.py`
（本工具只是它的 CLI 外壳 + 退出码）。

## 两种用法

**① 比对两份现成日志**（浏览器产出的，或 `--produce` 留下的）：

1. 打开 `?robot=<机型>&policy=<策略>&replay=0.4,0,0&seed=7&debug=1`
2. 控制台 `__sim2simDebug.startFrameLog()` → 跑 2-3 秒 → `stopFrameLog()` → 存 `run1.json`
3. **刷新页面**（重新 reset 到同一初态）后重复步骤 2 → 存 `run2.json`
4. `python tools/replay_gate.py --a run1.json --b run2.json --min-frames 50`

**② 无头跑两遍（L1 补的那条路，不需要开浏览器）**：

    python tools/replay_gate.py --produce --package assets/robots/zex-w \
        --policy-id zex-w-rough-9600 --steps 60 --min-frames 50 [--seed-probe 99]

产出端是 `adapters/mjlab/frame_log.py`（在适配器 venv 里跑，与验收同源原语），
**两个独立进程**各跑一遍（同进程内跑两次测不出跨进程的非确定性，如线程调度）。
`--seed-probe <另一个 seed>` 会再跑一遍，用来判定"seed 到底影不影响结果"：

* 日志头 `randomization.applied=false`（验收路径不做域随机化）⇒ seed 变了结果不变是**正常的**，
  但这意味着"同 seed 一致"当前**是空转的**，工具会明说（L3 接入 DR 后此处应翻为 changed）；
* `randomization.applied=true` 却 seed 无关 ⇒ 这是**真问题**（声明有随机量却不生效），判 fail。

用法::

    python tools/replay_gate.py --a run1.json --b run2.json [--min-frames 50]
    python tools/replay_gate.py --produce --package <包> --policy-id <id> [--steps 60]
    python tools/replay_gate.py --selftest            # 不需任何输入，自检判据本身

退出码：0 = 一致（通过）；1 = 不一致或输入不可读（fail-closed）；2 = 参数/环境不满足（如缺适配器解释器）。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.mjlab.replay_determinism import (  # noqa: E402
    CROSS_EXECUTOR_TOLERANCE,
    DEFAULT_TOLERANCE,
    compare_frame_logs,
    determinism_verdict,
    summarize,
)


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise SystemExit(f"[replay-gate] 找不到日志：{path}") from None
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[replay-gate] 日志不是合法 JSON：{path}（{exc}）") from None


def selftest() -> int:
    """自检判据：一致必过、改一位必红、帧数不等必红、帧数不足必红。"""
    frame = lambda step, value: {"stepIndex": step, "obs": [value, 0.0, 1.0]}  # noqa: E731
    base = [frame(i, i * 0.1) for i in range(1, 61)]
    same = [frame(i, i * 0.1) for i in range(1, 61)]
    tweaked = list(base)
    tweaked[30] = frame(31, 3.1 + 1e-3)

    checks = [
        ("一致 ⇒ pass", determinism_verdict(base, same, min_frames=50)["verdict"] == "pass"),
        ("差一位 ⇒ fail", determinism_verdict(base, tweaked, min_frames=50)["verdict"] == "fail"),
        ("帧数不等 ⇒ fail",
         determinism_verdict(base, base[:-1], min_frames=1)["reason"] == "length_mismatch"),
        ("帧数不足 ⇒ fail",
         determinism_verdict(base[:3], base[:3], min_frames=50)["reason"] == "too_few_frames"),
        ("stepIndex 对齐 ⇒ 允许乱序输入",
         compare_frame_logs(list(reversed(base)), same)["alignment"] == "step_index"),
        # 跨执行器口径判的是"链路一致"而非"确定性"：1e-3 的小差应放行
        ("跨执行器容差 ⇒ 小差算一致",
         compare_frame_logs(base, tweaked, tolerance=CROSS_EXECUTOR_TOLERANCE)["verdict"] == "pass"),
    ]
    ok = True
    for label, passed in checks:
        print(f"  [{'OK ' if passed else '!! '}] {label}")
        ok = ok and passed
    print(f"[replay-gate] selftest {'通过' if ok else '失败'}")
    return 0 if ok else 1


def _adapter_interpreter(explicit: str | None) -> Path:
    """解释器解析**只有一处实现**（`backend.adapter_runtime`）：候选顺序 + mujoco 探测 + 可执行修法。

    这里曾经自己写了一份；三处各写一套的结果是"静默退回当前解释器"与"探测"两种行为并存
    ——"环境没准备好"于是有时报 ImportError、有时被当成可用环境。
    """

    from backend.adapter_runtime import AdapterUnavailable, adapter_interpreter

    try:
        return adapter_interpreter(explicit)
    except AdapterUnavailable as exc:
        raise SystemExit(f"[replay-gate] {exc}") from exc


def produce_pair(args: argparse.Namespace) -> int:
    """无头跑两遍（独立进程）并比对；可选 seed 敏感性对照。"""

    interpreter = _adapter_interpreter(args.venv)
    script = ROOT / "adapters" / "mjlab" / "frame_log.py"
    if not script.is_file():
        raise SystemExit(f"[replay-gate] 缺产出脚本：{script}")

    workdir = Path(args.keep_logs) if args.keep_logs else Path(tempfile.mkdtemp(prefix="replay-gate-"))
    workdir.mkdir(parents=True, exist_ok=True)
    common = ["--package", str(args.package), "--cmd", args.cmd, "--steps", str(args.steps)]
    if getattr(args, "domain_rand", False):
        common.append("--domain-rand")
    if args.policy_id:
        common += ["--policy-id", args.policy_id]
    if args.policy:
        common += ["--policy", args.policy]

    def run(seed: int, name: str) -> tuple[Path, dict]:
        target = workdir / f"{name}.json"
        command = [str(interpreter), str(script), *common, "--seed", str(seed), "--out", str(target)]
        completed = subprocess.run(command, capture_output=True, text=True, cwd=str(ROOT))
        if completed.returncode != 0:
            tail = (completed.stderr or completed.stdout or "").strip().splitlines()[-4:]
            raise SystemExit(f"[replay-gate] 无头产出失败（seed={seed}）：" + " | ".join(tail))
        return target, _load(target)

    log_a, payload_a = run(args.seed, "run-a")
    log_b, payload_b = run(args.seed, "run-b")   # 独立进程：跨进程的非确定性也要被抓住
    result = determinism_verdict(payload_a, payload_b, tolerance=args.tolerance, min_frames=args.min_frames)

    seed_sensitivity: dict[str, object] | None = None
    if args.seed_probe is not None:
        _, payload_probe = run(args.seed_probe, "run-probe")
        probe = compare_frame_logs(payload_a, payload_probe, tolerance=args.tolerance)
        randomization = bool((payload_a.get("head") or {}).get("randomization", {}).get("applied"))
        changed = probe["verdict"] != "pass"
        if randomization and not changed:
            note = ("日志声明 randomization.applied=true，但换 seed 结果丝毫不变 ⇒ 随机量根本没生效"
                    "（声明与行为不一致，按 fail 处理）")
        elif randomization and changed:
            note = "seed 确实影响结果 ✓（随机量生效）"
        else:
            note = ("本路径不做域随机化（spawn_default 是确定性重置）⇒ seed 变了结果不变是正常的，"
                    "但也意味着「同 seed 一致」当前**是空转的**：域随机化属 L3 缺口，接进来后此处应翻为 changed")
        seed_sensitivity = {
            "probed_seed": args.seed_probe,
            "changed": changed,
            "randomization_declared": randomization,
            "verdict": probe["verdict"],
            "max_delta": probe.get("max_delta"),
            "note": note,
            "is_problem": bool(randomization and not changed),
        }

    heads = {
        "a": (payload_a.get("head") or {}),
        "b": (payload_b.get("head") or {}),
    }
    verdict = result["verdict"]
    if seed_sensitivity and seed_sensitivity["is_problem"]:
        verdict = "fail"
    summary = {
        "schema": "replay-gate-produce-1.0",
        "verdict": verdict,
        "determinism": result,
        "seed_sensitivity": seed_sensitivity,
        "runs": {
            "count": 2 + (1 if args.seed_probe is not None else 0),
            "log_a": str(log_a),
            "log_b": str(log_b),
            "seed": args.seed,
            "package": heads["a"].get("package"),
            "policy": heads["a"].get("policy"),
            "frames": heads["a"].get("recorded"),
            "adapter": heads["a"].get("adapter"),
        },
    }
    if args.json:
        # `--json` = 机器可读：stdout 只有 JSON（人类可读行一律走 stderr），
        # 否则调用方（如 backend/reproduce.py）拿到的是"JSON + 几行自然语言"，parse 必炸。
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print(f"[replay-gate] {summarize(result)}", file=sys.stderr)
        if seed_sensitivity:
            print(f"[replay-gate] seed 对照：{seed_sensitivity['note']}", file=sys.stderr)
        return 0 if verdict == "pass" else 1
    print(f"[replay-gate] {summarize(result)}")
    if seed_sensitivity:
        print(f"[replay-gate] seed 对照（{args.seed} vs {args.seed_probe}）："
              f"{'结果不同' if seed_sensitivity['changed'] else '结果相同'} —— {seed_sensitivity['note']}")
    if verdict != "pass":
        print("[replay-gate] 结论：回放不一致 ⇒ 视为「没学会」（L1/G2 口径）", file=sys.stderr)
        return 1
    print(f"[replay-gate] 通过：两个独立无头进程逐帧一致（{summary['runs']['frames']} 帧）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="确定性回放门禁（两次逐帧一致）")
    parser.add_argument("--a", type=Path, help="第一次运行的 frame log JSON")
    parser.add_argument("--b", type=Path, help="第二次运行的 frame log JSON")
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE,
                        help=f"逐维容差（同执行器重跑用默认 {DEFAULT_TOLERANCE}；"
                             f"跨执行器诊断可给 {CROSS_EXECUTOR_TOLERANCE}）")
    parser.add_argument("--min-frames", type=int, default=1,
                        help="至少要一致多少帧才算通过（门禁建议 ≥50，避免只比初始态）")
    parser.add_argument("--json", action="store_true", help="输出结构化结论（供 CI 归档）")
    parser.add_argument("--selftest", action="store_true", help="自检判据，不需要输入文件")
    produce = parser.add_argument_group("无头产出（L1：不需要开浏览器）")
    produce.add_argument("--produce", action="store_true", help="跑两遍无头产出再比对")
    produce.add_argument("--package", help="机器人包目录（如 assets/robots/zex-w）")
    produce.add_argument("--policy-id", help="策略 id（走后端统一解析器，与页面/验收同一真值源）")
    produce.add_argument("--policy", help="策略 onnx 路径（显式指定；与 --policy-id 二选一）")
    produce.add_argument("--cmd", default="0.4,0,0", help="速度指令 vx,vy,wz")
    produce.add_argument("--seed", type=int, default=7)
    produce.add_argument("--seed-probe", type=int, default=None,
                         help="再跑一个不同 seed，判定 seed 是否真的影响结果（L3 空转检测）")
    produce.add_argument("--steps", type=int, default=60, help="控制步数（≥ min-frames）")
    produce.add_argument("--domain-rand", action="store_true",
                         help="开启域随机化（L3）：此时 seed 探针应报 changed（验收判据），关闭时应报相同")
    produce.add_argument("--venv", default=None, help="适配器 venv 目录或其 python 路径")
    produce.add_argument("--keep-logs", default=None, help="把两份日志留在该目录（便于复盘）")
    args = parser.parse_args()

    if args.selftest:
        return selftest()
    if args.produce:
        if not args.package:
            parser.error("--produce 需要 --package")
        if not args.policy_id and not args.policy:
            parser.error("--produce 需要 --policy-id 或 --policy")
        return produce_pair(args)
    if not args.a or not args.b:
        parser.error("需要 --a 与 --b（或用 --produce / --selftest）")

    result = determinism_verdict(_load(args.a), _load(args.b),
                                 tolerance=args.tolerance, min_frames=args.min_frames)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"[replay-gate] {summarize(result)}", file=sys.stderr)
    else:
        print(f"[replay-gate] {summarize(result)}")
    if result["verdict"] != "pass":
        print("[replay-gate] 结论：回放不一致 ⇒ 视为「没学会」（L1/G2 口径）", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
