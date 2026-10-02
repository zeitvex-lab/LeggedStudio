#!/usr/bin/env python3
"""recipe_parity.py — 移植保真门：我们的 effective-config vs 参考真值表的**语义 diff**。

为什么存在（2026-10-02 用户根本问题：「统一框架做好后，移植对一下语义就应该直接复用」）：
对语义这一步此前是**人眼+记忆**——go2w legs-only 移植号称逐值对齐，40k 训完判据 0/4
后才手工 diff 出 3 处 delta（缺 angular_momentum、feet_air_time 阈值不同）。本工具把
"对一下语义"变成一条命令：**delta 在开训前就可见**，而不是训完 40k 轮后 forensics。

口径（与 porting_references 的 conclusion 词表同源）：
  * delta ≠ 错——本工具只报告分类（missing / extra / weight / param / command / action /
    termination），**不裁决**；人按 aligned（有意如此）/ suspect（疑点）裁。
  * 参考真值表 = registry/reference_recipes/*.json（带上游文件行号锚点，逐行抄录）；
  * 我方真值 = run 目录的 effective-config.json（训练装配的**实际**生效配置，非声明）。

用法：
  python tools/recipe_parity.py --recipe unitree_rl_mjlab_go2w__velocity_flat_legs_only \
      --run-dir workspace/<run>
  python tools/recipe_parity.py --recipe <id> --effective-config <path> --json

退出码：0 = 无 delta；1 = 有 delta（可作门禁）；2 = 环境缺失（表/run 不存在）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECIPES_DIR = ROOT / "registry" / "reference_recipes"

TOL = 1e-9


def _num_eq(a, b) -> bool:
    try:
        return abs(float(a) - float(b)) <= TOL
    except (TypeError, ValueError):
        return False


def _fmt(v) -> str:
    return json.dumps(v, ensure_ascii=False)


def diff_recipe(truth: dict, effective: dict) -> list[dict]:
    """真值表 vs effective-config 的逐类 delta（空列表 = 语义一致）。"""
    deltas: list[dict] = []
    env = effective.get("environment") or {}
    ours_rewards = env.get("rewards") or {}

    # ① 奖励：名→权重（+真值表声明了 params 的项做参数级对比）
    for name, spec in (truth.get("rewards") or {}).items():
        ours = ours_rewards.get(name)
        if ours is None:
            deltas.append({"kind": "missing", "term": name,
                           "upstream": f"weight={_fmt(spec.get('weight'))}",
                           "ours": "—"})
            continue
        if not _num_eq(ours.get("weight"), spec.get("weight")):
            deltas.append({"kind": "weight", "term": name,
                           "upstream": _fmt(spec.get("weight")), "ours": _fmt(ours.get("weight"))})
        for key, expected in (spec.get("params") or {}).items():
            got = (ours.get("params") or {}).get(key)
            if isinstance(expected, (int, float)) and isinstance(got, (int, float)):
                match = _num_eq(got, expected)
            else:
                match = got == expected
            if not match:
                deltas.append({"kind": "param", "term": f"{name}.{key}",
                               "upstream": _fmt(expected), "ours": _fmt(got)})
    for name in ours_rewards:
        if name not in (truth.get("rewards") or {}):
            deltas.append({"kind": "extra", "term": name,
                           "upstream": "—", "ours": f"weight={_fmt(ours_rewards[name].get('weight'))}"})

    # ② 命令域：ranges / rel_standing_envs / heading / 重采样窗
    truth_cmd = truth.get("commands") or {}
    ours_cmd = env.get("commands") or {}
    twist = ours_cmd.get("twist") or {}
    for axis, expected in (truth_cmd.get("ranges") or {}).items():
        got = (twist.get("ranges") or {}).get(axis)
        if not isinstance(got, list) or len(got) != 2 or not (
            _num_eq(got[0], expected[0]) and _num_eq(got[1], expected[1])
        ):
            deltas.append({"kind": "command", "term": f"twist.ranges.{axis}",
                           "upstream": _fmt(expected), "ours": _fmt(got)})
    for key in ("rel_standing_envs", "heading_command", "resampling_time_range"):
        if key in truth_cmd:
            expected, got = truth_cmd[key], twist.get(key)
            same = (_num_eq(got, expected)
                    if isinstance(expected, (int, float)) and isinstance(got, (int, float))
                    else got == expected)
            if not same:
                deltas.append({"kind": "command", "term": f"twist.{key}",
                               "upstream": _fmt(expected), "ours": _fmt(got)})

    # ③ 动作缩放（部署真值链的源头之一）
    for term, spec in (truth.get("actions") or {}).items():
        ours_scale = ((env.get("actions") or {}).get(term) or {}).get("scale")
        expected = spec.get("scale")
        if not (isinstance(ours_scale, (int, float)) and _num_eq(ours_scale, expected)):
            deltas.append({"kind": "action", "term": f"actions.{term}.scale",
                           "upstream": _fmt(expected), "ours": _fmt(ours_scale)})

    # ④ 终止项参数（存在性 + 声明了的参数值）
    for name, params in (truth.get("terminations") or {}).items():
        ours = (env.get("terminations") or {}).get(name)
        if ours is None:
            deltas.append({"kind": "missing", "term": f"terminations.{name}",
                           "upstream": _fmt(params), "ours": "—"})
            continue
        for key, expected in params.items():
            got = (ours.get("params") or {}).get(key)
            if isinstance(expected, (int, float)) and isinstance(got, (int, float)):
                if not _num_eq(got, expected):
                    deltas.append({"kind": "param", "term": f"terminations.{name}.{key}",
                                   "upstream": _fmt(expected), "ours": _fmt(got)})
            elif got != expected:
                deltas.append({"kind": "param", "term": f"terminations.{name}.{key}",
                               "upstream": _fmt(expected), "ours": _fmt(got)})
    return deltas


def main() -> int:
    ap = argparse.ArgumentParser(description="移植保真门：effective-config vs 参考真值表语义 diff")
    ap.add_argument("--recipe", required=True, help="registry/reference_recipes 下的 recipe_id（文件名去 .json）")
    ap.add_argument("--run-dir", help="run 目录（读 effective-config.json）")
    ap.add_argument("--effective-config", help="直接给 effective-config.json 路径")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    table = RECIPES_DIR / f"{args.recipe}.json"
    if not table.is_file():
        print(f"[env-missing] 参考真值表不存在：{table}", file=sys.stderr)
        return 2
    cfg_path = Path(args.effective_config) if args.effective_config else (
        Path(args.run_dir) / "effective-config.json" if args.run_dir else None
    )
    if cfg_path is None or not cfg_path.is_file():
        print(f"[env-missing] effective-config 不存在：{cfg_path}", file=sys.stderr)
        return 2

    truth = json.loads(table.read_text(encoding="utf-8-sig"))
    effective = json.loads(Path(cfg_path).read_text(encoding="utf-8-sig"))
    deltas = diff_recipe(truth, effective)

    report = {
        "recipe": args.recipe,
        "effective_config": str(cfg_path),
        "delta_count": len(deltas),
        "deltas": deltas,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        print(f"recipe_parity: {args.recipe} vs {cfg_path}")
        if not deltas:
            print("  ✓ 语义一致（奖励/命令域/动作缩放/终止逐值对齐）")
        for d in deltas:
            print(f"  [{d['kind']:>8s}] {d['term']}: 上游 {d['upstream']} ⇄ 我方 {d['ours']}")
        print(f"  → {len(deltas)} 处 delta；按 aligned/intentional/suspect 裁（delta≠错）")
    return 0 if not deltas else 1


if __name__ == "__main__":
    sys.exit(main())
