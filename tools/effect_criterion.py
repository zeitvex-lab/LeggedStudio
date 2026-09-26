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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="打印对照表")
    parser.add_argument("--check", action="store_true", help="低于阈值判红；没测的单列（不算通过）")
    parser.add_argument("--record", metavar="ROBOT", help="录入某机型的一次实测（须给 --tier/--value/预算）")
    parser.add_argument("--tier", default=None)
    parser.add_argument("--value", type=float, default=None)
    parser.add_argument("--num-envs", type=int, default=None)
    parser.add_argument("--iters", type=int, default=None)
    parser.add_argument("--report", default=None, help="产出该数字的报告文件（登记用）")
    args = parser.parse_args()

    payload = load()
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
