"""效果口径：**同档、同预算、同度量**的跨机型效果对照（用户定的 8–9 成）。

## 它回答什么

"这套族架构把技能铺到另一台机型上，效果能不能到参考实现的 8–9 成？"
—— 声明在 `registry/effect_criterion.json`（档 × 度量 × 预算 × 参考机型 × 阈值），
数字由**既有工具**产出（越障验收器 `tools/validate_traversal_progress.py`、
冒烟 `tools/validate_training_smoke.py`、仿真验收 `tools/sim2sim_headless.py`），
本工具只做三件事：**列出对照表 / 录入一次实测 / 按阈值判**。

## 口径纪律（与仓里其它门禁同一条）

* **不发明数字**：`observed` / `reference` 没测过就是 `null`；
  `--check` 把"测了但低于阈值"判红，把"没测"单列成 `untested`（**不当作通过**）；
* **预算必须写清**（环境数 × 迭代数）：不同预算下的数字不可比，缺预算的实测拒绝录入；
* **参考也是实测**：参考机型的历史产物若不满足本口径（如旧观测布局），
  它的参考值同样要按本口径跑一轮——声明里写明，不拿历史 ONNX 的分数充数。

用法（解释器用仓自带的 `.venv` 即可，本工具不 import 训练栈）：

    python tools/effect_criterion.py --list
    python tools/effect_criterion.py --check            # 低于阈值判红；没测的单列
    python tools/effect_criterion.py --record unitree_b2w --tier traversal_obstacle_release \
        --value 0.62 --num-envs 1024 --iters 2000 [--report <json>]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "registry" / "effect_criterion.json"


def load() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8-sig"))


def save(payload: dict) -> None:
    REGISTRY.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def find_entry(payload: dict, tier: str) -> dict:
    for entry in payload.get("entries") or []:
        if entry.get("tier") == tier:
            return entry
    raise SystemExit(f"登记表里没有档 {tier!r}（--list 看现有档）")


def ratio_of(entry: dict, value: float | None) -> float | None:
    reference = entry.get("reference")
    if value is None or not reference:
        return None
    reference_value = float((reference or {}).get("value") or 0.0)
    if reference_value <= 0:
        return None  # 参考值为 0/未定 ⇒ 比值无意义，不硬算
    return float(value) / reference_value


def budget_text(entry: dict, budget: dict) -> str:
    """预算文案：训练预算与"不来自训练预算"的档要分开说，别把 n/a 说成未声明。"""
    if not budget and (entry.get("budget") or {}).get("num_envs") is None:
        return "该档度量不来自训练预算（见 budget_note）"
    return f"预算 {budget or '未声明'}"


def report(payload: dict) -> tuple[list[dict], list[str], list[str]]:
    defaults = payload.get("defaults") or {}
    pass_ratio = float(defaults.get("pass_ratio", 0.8))
    good_ratio = float(defaults.get("good_ratio", 0.9))
    rows: list[dict] = []
    failures: list[str] = []
    untested: list[str] = []
    for entry in payload.get("entries") or []:
        tier = str(entry.get("tier"))
        reference = entry.get("reference")
        reference_value = None if not reference else reference.get("value")
        if reference_value is None:
            untested.append(f"{tier}: 参考值未测（参考机型 {entry.get('reference_profile')}）")
        for robot, observed in (entry.get("observed") or {}).items():
            value = None if not observed else observed.get("value")
            budget = (observed or {}).get("budget") or {}
            row = {
                "tier": tier,
                "robot": robot,
                "metric": entry.get("metric"),
                "value": value,
                "reference_profile": entry.get("reference_profile"),
                "reference_value": reference_value,
                "budget": budget,
            }
            if value is None:
                untested.append(f"{tier} / {robot}: 未测（{budget_text(entry, budget)}）")
                row["verdict"] = "untested"
            elif reference_value is None:
                row["verdict"] = "no_reference"
            else:
                ratio = ratio_of(entry, value)
                row["ratio"] = None if ratio is None else round(ratio, 3)
                row["verdict"] = (
                    "good" if ratio is not None and ratio >= good_ratio
                    else "pass" if ratio is not None and ratio >= pass_ratio
                    else "fail"
                )
                if row["verdict"] == "fail":
                    failures.append(
                        f"{tier} / {robot}: 效果 {value} vs 参考 {reference_value} "
                        f"= {row['ratio']} < {pass_ratio}（{budget_text(entry, budget)}）"
                    )
            rows.append(row)
    return rows, failures, untested


def _dig(payload: dict, field: str):
    """按点路径从产出方的报告里取指标（`policy.progress_env_ratio` 这类）。"""
    node = payload
    for part in field.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _adapter_interpreter() -> str:
    """训练栈所在的解释器（跑产出方用）。

    **不 import `contracts.path_bootstrap`**：那会拉起控制面依赖（pydantic 等），
    而本工具按设计只依赖标准库（用仓根 `.venv` 的 python 跑）。这里按它的同一口径自己解析：
    先认显式环境变量，再认 `adapters/mjlab/.venv` 的两种布局，都没有才回落到当前解释器
    （并在命令行里明说，避免"用错解释器却静默失败"）。
    """
    import os

    for name in ("ADAPTER_PYTHON", "LEGGED_STUDIO_ADAPTER_PYTHON", "ADAPTER_PYTHON_ENV"):
        explicit = (os.environ.get(name) or "").strip()
        if explicit:
            return str(Path(explicit).expanduser())
    venv = ROOT / "adapters" / "mjlab" / ".venv"
    for candidate in (venv / "Scripts" / "python.exe", venv / "bin" / "python"):
        if candidate.is_file():
            return str(candidate)
    return sys.executable


def run_tier(payload: dict, robot: str, tier: str, iters: int | None, num_envs: int | None,
             seconds: float | None, allow_underbudget: bool) -> int:
    """一键效果对照：按登记的产出方跑训练+验收，取出指标，**按声明预算**才登记。"""
    import subprocess

    entry = find_entry(payload, tier)
    producer = entry.get("producer")
    metric_field = entry.get("metric_field")
    profile_id = (entry.get("profiles") or {}).get(robot)
    if not producer or not metric_field or not profile_id:
        raise SystemExit(
            f"{tier} / {robot}: 该档没有登记一键跑的三样（producer / metric_field / profiles）—— "
            "见 `python tools/effect_criterion.py --list`；速度跟踪档走 sim2sim 验收器自己的 CLI"
        )
    declared = entry.get("budget") or {}
    budget_iters = int(iters or declared.get("iters") or 0)
    budget_envs = int(num_envs or declared.get("num_envs") or 0)
    if not budget_iters or not budget_envs:
        raise SystemExit(f"{tier}: 档案没声明预算（num_envs/iters），用 --iters / --num-envs 显式给")

    report_dir = ROOT / "workspace" / "validation"
    report_path = report_dir / f"effect-{tier}-{robot}.json"
    report_dir.mkdir(parents=True, exist_ok=True)
    interpreter = _adapter_interpreter()
    command = [
        interpreter, str(ROOT / producer),
        "--profile", profile_id,
        "--train-iters", str(budget_iters),
        "--num-envs", str(budget_envs),
        "--output", str(report_path),
    ]
    if seconds:
        command += ["--seconds", str(seconds)]
    print(f"[effect] 跑 {tier} / {robot}（解释器 {interpreter}）")
    print(f"[effect] {' '.join(command[1:])}")
    completed = subprocess.run(command, cwd=str(ROOT), text=True, encoding="utf-8",
                              errors="replace")
    if not report_path.is_file():
        raise SystemExit(f"产出方没有留下报告（退出码 {completed.returncode}）：{report_path}")
    produced = json.loads(report_path.read_text(encoding="utf-8-sig"))
    value = _dig(produced, metric_field)
    verdict = produced.get("verdict")
    declared_budget = {"num_envs": declared.get("num_envs"), "iters": declared.get("iters")}
    matches_declared = declared_budget == {"num_envs": budget_envs, "iters": budget_iters}
    print(f"[effect] 指标 {metric_field} = {value}（产出方判定 {verdict}）")
    if value is None:
        raise SystemExit(f"报告里取不到 {metric_field}：{report_path}")
    if matches_declared:
        observed = entry.setdefault("observed", {})
        observed[robot] = {
            "value": float(value),
            "budget": {"num_envs": budget_envs, "iters": budget_iters},
            "checked_at": "2026-09-26",
            "report": str(report_path.relative_to(ROOT)),
        }
        save(payload)
        print(f"[effect] 已按声明预算登记 {tier} / {robot} = {value}")
    elif allow_underbudget:
        observed = entry.setdefault("observed", {})
        observed[robot] = {
            "value": float(value),
            "budget": {"num_envs": budget_envs, "iters": budget_iters},
            "checked_at": "2026-09-26",
            "report": str(report_path.relative_to(ROOT)),
            "note": f"**未按声明预算**（声明 {declared_budget}）—— 只作诊断，不作为效果对照依据",
        }
        save(payload)
        print(f"[effect] 已按**未达声明预算**登记（带注记）{tier} / {robot} = {value}")
    else:
        print(
            f"[effect] 预算 {budget_envs}×{budget_iters} 与声明 {declared_budget} 不一致 ⇒ **不登记**"
            "（不同预算的数字不可比；要诊断加 --allow-underbudget，它会带注记）"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="打印对照表")
    parser.add_argument("--check", action="store_true", help="低于阈值判红；没测的单列（不算通过）")
    parser.add_argument("--record", metavar="ROBOT", help="录入某机型的一次实测（须给 --tier/--value/预算）")
    parser.add_argument("--run", metavar="ROBOT", help="一键跑：按登记的产出方训练+验收并登记（须给 --tier）")
    parser.add_argument("--tier", default=None)
    parser.add_argument("--value", type=float, default=None)
    parser.add_argument("--num-envs", type=int, default=None)
    parser.add_argument("--iters", type=int, default=None)
    parser.add_argument("--seconds", type=float, default=None)
    parser.add_argument("--allow-underbudget", action="store_true",
                        help="允许把「未达声明预算」的结果登记进去（会带注记，不作对照依据）")
    parser.add_argument("--report", default=None, help="产出该数字的报告文件（登记用）")
    args = parser.parse_args()

    payload = load()
    if args.run:
        if args.tier is None:
            raise SystemExit("--run 必须给 --tier")
        return run_tier(payload, args.run, args.tier, args.iters, args.num_envs,
                        args.seconds, args.allow_underbudget)
    if args.record:
        if args.tier is None or args.value is None:
            raise SystemExit("--record 必须同时给 --tier 与 --value")
        if args.num_envs is None or args.iters is None:
            raise SystemExit("--record 必须写清预算（--num-envs / --iters）：不同预算的数字不可比")
        entry = find_entry(payload, args.tier)
        observed = entry.setdefault("observed", {})
        observed[args.record] = {
            "value": float(args.value),
            "budget": {"num_envs": int(args.num_envs), "iters": int(args.iters)},
            "checked_at": "2026-09-26",
            **({"report": args.report} if args.report else {}),
        }
        save(payload)
        print(f"[effect] 已录入 {args.tier} / {args.record} = {args.value}（预算 {args.num_envs}×{args.iters}）")
        return 0

    rows, failures, untested = report(payload)
    if args.list or not args.check:
        print(f"[effect] 效果对照表（{len(rows)} 行）")
        for row in rows:
            reference = row["reference_value"]
            target = "" if row.get("ratio") is None else f" → 参考比 {row['ratio']}"
            print(
                f"  {row['tier']:34s} {row['robot']:22s} {row['metric']:20s} "
                f"实测={row['value']} 参考={reference}{target} [{row['verdict']}]"
            )
        if untested:
            print("[effect] 未测/无参考（**不算通过**）：")
            for item in untested:
                print(f"  · {item}")
        pending = payload.get("pending") or []
        if pending:
            print("[effect] 还没有可比值量的档（如实留痕，未接入）：")
            for item in pending:
                print(f"  · {item['tier']}：{item['why']}")
    if args.check:
        if failures:
            print(f"\n[effect] 判红 {len(failures)} 处：")
            for item in failures:
                print(f"  ✗ {item}")
            return 1
        measured = [row for row in rows if row.get("verdict") in ("pass", "good")]
        print(f"\n[effect] 已测 {len(measured)} 行全部达标；未测 {len(untested)} 行（单列，不计通过）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
