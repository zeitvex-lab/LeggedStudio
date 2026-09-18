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
  但这意味着"同 seed 一致"在**关闭 DR 的配置下**是空转的，工具会明说（开 `--domain-rand` 后此处应翻为 changed）；
* `randomization.applied=true` 却 seed 无关 ⇒ 这是**真问题**（声明有随机量却不生效），判 fail。

**③ 自动连跑两遍的采集器（`--auto`，S4 剩余项）**：给**一个目标**，采集器自己把
（包，策略）解析出来，然后**自动起两个独立子进程**各跑一遍无头仿真产 frame log，
再走同一个判据出结论 —— 人不用再手动跑两次。目标认得三种：

    python tools/replay_gate.py --auto workspace/packages/zex-w --steps 60 --min-frames 50
        # ↑ 包 / Bundle 目录（含 simulation/config.json）：Bundle、机器人包都行，
        #   不给 --policy-id 时用包内声明的第一条策略
    python tools/replay_gate.py --auto policies/zex-w__zex-w-rough-9600
        # ↑ 已提升产物目录（含 artifact.json 且绑定 robot/policy_id）：包按 artifact.robot
        #   解析到 assets/robots/<robot>，策略用 artifact.policy_id（走后端统一解析器）
    python tools/replay_gate.py --auto <某个.onnx> --package <包目录>
        # ↑ 裸 onnx 文件：文件自己说不了住哪个包，--package 必须给

`--auto` 只做**目标解析 + 编排**：采集循环（subprocess×2）、判据、比对、汇总、退出码
全部是 `--produce` 的既有代码路径（单一真值，不另写一套）；子进程产出还会过一遍
记录器共享帧校验（`frame_log.validate_frame_log`），形状坏了按"没跑成"处理。
单次 `--auto` 的代价 ≈ 两个无头进程（zex-w 40 步在 CI 的 sim2sim 档实测够用）。

用法::

    python tools/replay_gate.py --a run1.json --b run2.json [--min-frames 50]
    python tools/replay_gate.py --produce --package <包> --policy-id <id> [--steps 60]
    python tools/replay_gate.py --auto <包/Bundle/产物目录 或 onnx> [--policy-id <id>]
    python tools/replay_gate.py --selftest            # 不需任何输入，自检判据本身

退出码：0 = 一致（通过）；1 = 不一致或输入日志不可读（fail-closed）；
2 = 参数/环境/产出端不满足（缺适配器解释器、子进程崩溃、产出未过帧校验）——
**「没跑成」与「跑了不一致」是两件事**，别混在同一个码里（backend/reproduce.py 据此分 fail/blocked）。
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


def _fail_environment(message: str) -> SystemExit:
    """「没跑成」（环境/产出端问题）：stderr 说清原因，退出码 2 —— 不与「判据说了不一致」（1）混用。"""

    print(message, file=sys.stderr)
    return SystemExit(2)


def _adapter_interpreter(explicit: str | None) -> Path:
    """解释器解析**只有一处实现**（`backend.adapter_runtime`）：候选顺序 + mujoco 探测 + 可执行修法。

    这里曾经自己写了一份；三处各写一套的结果是"静默退回当前解释器"与"探测"两种行为并存
    ——"环境没准备好"于是有时报 ImportError、有时被当成可用环境。
    """

    from backend.adapter_runtime import AdapterUnavailable, adapter_interpreter

    try:
        return adapter_interpreter(explicit)
    except AdapterUnavailable as exc:
        raise _fail_environment(f"[replay-gate] {exc}") from exc


def _validate_produced(payload: object) -> list[str]:
    """无头产出过一遍**记录器共享帧校验**（单一实现：adapters/mjlab/frame_log.validate_frame_log）。

    延迟 import：`--selftest` / `--a --b` 不该被 frame_log 的 numpy 牵连（保持裸 python 可用）。
    """

    from adapters.mjlab.frame_log import validate_frame_log

    return validate_frame_log(payload, require_head=True)


def resolve_auto_target(
    target: Path,
    *,
    package: str | None,
    policy: str | None,
    policy_id: str | None,
) -> dict:
    """把 `--auto` 的一个目标解析成（包，策略）—— **采集器唯一自己做的决定**。

    解析完就交给 `--produce` 的既有代码路径（采集循环/判据/比对/退出码零重写）。
    认得三种目标（解析不出就退出码 2，说清为什么、怎么改）：

    * **包 / Bundle 目录**（含 ``simulation/config.json``）：assets/robots 下的机器人包、
      workspace/packages 下的导出 Bundle 都长这样；不给策略时用包内声明的第一条；
    * **已提升产物目录**（含 ``artifact.json``）：绑定过 robot/policy_id 的（kind=policies）
      按 artifact.robot 解析到 ``assets/robots/<robot>``（``--package`` 可覆盖）、策略走
      artifact.policy_id（后端统一解析器，与页面/验收同一真值源）；未绑定的 produced 产物
      只有裸 onnx，必须用 ``--package`` 说明它属于哪个包（这是已登记现状，不假装能猜）；
    * **onnx 文件**：策略即该文件，``--package`` 必须给。
    """

    def bad(message: str) -> SystemExit:
        return _fail_environment(f"[replay-gate] --auto 无法解析目标 {target}：{message}")

    if not target.exists():
        raise bad("路径不存在")

    if target.is_file():
        if target.suffix.lower() != ".onnx":
            raise bad("只认 .onnx 文件（目录请直接给包/Bundle/产物目录）")
        if not package:
            raise bad("裸 onnx 文件说不了自己住哪个包 —— 请同时给 --package <包目录>")
        return {"kind": "onnx", "package": package, "policy": str(target), "policy_id": policy_id}

    if (target / "simulation" / "config.json").is_file():
        return {
            "kind": "package_or_bundle",
            "package": str(target),
            "policy": policy,
            "policy_id": policy_id,
            "note": "" if (policy or policy_id) else "未指定策略 ⇒ 用包内 simulation/config.json 声明的第一条",
        }

    if (target / "artifact.json").is_file():
        try:
            artifact = json.loads((target / "artifact.json").read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise bad(f"artifact.json 不是合法 JSON（{exc}）") from None
        if not isinstance(artifact, dict):
            raise bad("artifact.json 顶层不是对象")
        resolved_package = package or (
            f"assets/robots/{artifact['robot']}" if artifact.get("robot") else None
        )
        if not resolved_package:
            raise bad(
                "该产物未绑定机器人包（artifact.json 没有 robot 字段，kind=produced 的已登记现状）—— "
                "请用 --package <包目录> 说明它属于哪个包"
            )
        onnx_in_dir = target / "policy.onnx"
        if policy or onnx_in_dir.is_file():
            resolved_policy = policy or str(onnx_in_dir)
            resolved_policy_id = policy_id
        else:
            resolved_policy = None
            resolved_policy_id = policy_id or (str(artifact["policy_id"]) if artifact.get("policy_id") else None)
        if not resolved_policy and not resolved_policy_id:
            raise bad("产物里既没有 policy.onnx，artifact.json 也没有 policy_id —— 不知道该跑哪条策略")
        return {
            "kind": "artifact",
            "package": resolved_package,
            "policy": resolved_policy,
            "policy_id": resolved_policy_id,
        }

    raise bad(
        "不认识的目录形状（既没有 simulation/config.json，也没有 artifact.json）—— "
        "要 包/Bundle 目录、已提升产物目录，或直接给 .onnx 文件"
    )


def _check_auto_package(plan: dict) -> None:
    """解析出的包必须真的能当包用（存在 + 有 simulation/config.json），否则 exit 2。"""

    package = Path(plan["package"])
    if not package.is_dir():
        raise _fail_environment(
            f"[replay-gate] --auto 解析出的包目录不存在：{package}"
            + ("（产物按 artifact.robot 指到 assets/robots/<robot>；不在仓里就用 --package 覆盖）"
               if plan["kind"] == "artifact" else "")
        )
    if not (package / "simulation" / "config.json").is_file():
        raise _fail_environment(f"[replay-gate] --auto 解析出的包里缺 simulation/config.json：{package}")


def produce_pair(args: argparse.Namespace) -> int:
    """无头跑两遍（独立进程）并比对；可选 seed 敏感性对照。"""

    interpreter = _adapter_interpreter(args.venv)
    script = ROOT / "adapters" / "mjlab" / "frame_log.py"
    if not script.is_file():
        raise _fail_environment(f"[replay-gate] 缺产出脚本：{script}")

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
            raise _fail_environment(
                f"[replay-gate] 无头产出失败（seed={seed}，exit={completed.returncode}，「没跑成」≠「不一致」）："
                + " | ".join(tail)
            )
        try:
            payload = _load(target)
        except SystemExit as exc:
            raise _fail_environment(f"[replay-gate] 产出日志不可读（seed={seed}）：{exc}") from None
        problems = _validate_produced(payload)
        if problems:
            raise _fail_environment(
                "[replay-gate] 产出日志未通过记录器共享帧校验（frame_log.validate_frame_log）：\n  "
                + "\n  ".join(problems[:8])
            )
        return target, payload

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
            note = ("本路径**没开**域随机化（spawn_default 是确定性重置）⇒ seed 变了结果不变是正常的，"
                    "但也意味着「同 seed 一致」在关闭 DR 的配置下**是空转的**：开 DR 用 --domain-rand，"
                    "开了之后换 seed 应当翻为 changed（L3 验收判据）")
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
    auto_plan = getattr(args, "auto_plan", None)
    if auto_plan:
        # --auto 的溯源：这次采集是从哪个目标解析来的、解析成了什么（报告要能自证编排决定）
        summary["auto"] = {"target": str(args.auto), **auto_plan}
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
    auto = parser.add_argument_group("自动采集器（--auto：一个目标 → 自动两进程采集 + 比对）")
    auto.add_argument("--auto", metavar="目标", default=None,
                      help="包/Bundle 目录（含 simulation/config.json）、已提升产物目录（含 artifact.json）"
                           "或裸 .onnx（需 --package）；解析后自动起两个独立子进程采集并比对")
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
    if args.auto:
        if args.produce:
            parser.error("--auto 与 --produce 二选一（--auto 已含「跑两遍再比对」）")
        plan = resolve_auto_target(Path(args.auto), package=args.package,
                                   policy=args.policy, policy_id=args.policy_id)
        _check_auto_package(plan)
        # 编排到此为止：解析结果回填进既有 --produce 参数，采集/判据/比对/退出码全走原代码路径。
        args.package = plan["package"]
        args.policy = plan.get("policy")
        args.policy_id = plan.get("policy_id")
        args.auto_plan = plan
        stream = sys.stderr if args.json else sys.stdout
        print(f"[replay-gate] --auto 目标 {args.auto} ⇒ 包 {plan['package']} / "
              f"策略 {plan.get('policy') or plan.get('policy_id') or '（包内第一条）'}"
              f"{'（' + plan['note'] + '）' if plan.get('note') else ''}", file=stream)
        return produce_pair(args)
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
