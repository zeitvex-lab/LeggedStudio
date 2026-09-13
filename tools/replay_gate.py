#!/usr/bin/env python3
"""确定性回放门禁（L1 / G2）：比对两份 frame log，不一致即非 0 退出。

**它填的是哪个洞**：`deterministic_replay` 能力此前只能记 `partial`——"两次跑同一策略
逐帧是否一致"没有判据。判据实现只有一处：`adapters/mjlab/replay_determinism.py`
（本工具只是它的 CLI 外壳 + 退出码）。

浏览器里怎么产出两份日志（与 `adapters/mjlab/replay_diff.py` 的用法同一套）：

1. 打开 `?robot=<机型>&policy=<策略>&replay=0.4,0,0&seed=7&debug=1`
2. 控制台 `__sim2simDebug.startFrameLog()` → 跑 2-3 秒 → `stopFrameLog()` → 存 `run1.json`
3. **刷新页面**（重新 reset 到同一初态）后重复步骤 2 → 存 `run2.json`
4. `python tools/replay_gate.py --a run1.json --b run2.json --min-frames 50`

用法::

    python tools/replay_gate.py --a run1.json --b run2.json [--min-frames 50]
    python tools/replay_gate.py --selftest            # 不需任何输入，自检判据本身

退出码：0 = 一致（通过）；1 = 不一致或输入不可读（fail-closed）；2 = 参数/输入格式错误。
"""

from __future__ import annotations

import argparse
import json
import sys
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
    args = parser.parse_args()

    if args.selftest:
        return selftest()
    if not args.a or not args.b:
        parser.error("需要 --a 与 --b（或用 --selftest）")

    result = determinism_verdict(_load(args.a), _load(args.b),
                                 tolerance=args.tolerance, min_frames=args.min_frames)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"[replay-gate] {summarize(result)}")
    if result["verdict"] != "pass":
        print("[replay-gate] 结论：回放不一致 ⇒ 视为「没学会」（L1/G2 口径）", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
