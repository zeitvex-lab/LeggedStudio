#!/usr/bin/env python
"""策略任务族分类审计：把「声明的 task_type」与「证据推出的族」摆在一起看。

**为什么必须先做这件事**：`tools/sim2sim_headless.py::task_family()` 用任务族决定套哪套判据
（`DEFAULT_CRITERIA[family]`）。分类错了，判据就错了 —— 于是"这条策略站不住"与
"我把这条策略判错了"混成一个结果，无法分辨。

**证据（全部来自包内声明与文件，不需要仿真、不需要 mujoco）**：

1. ``contract.observation_kind`` —— 最强信号（``*_motion_*`` → imitation；
   ``himloco_*`` → velocity；``*_reorient_*`` → reorient）；
2. ``command_dims`` —— 3 表示可做速度跟踪；非 3 是复合命令，速度扫描对它不适用；
3. **同目录的参考动作 csv** —— 模仿/特技类几乎都带 motion csv；
4. ``id`` / ``label`` 关键词 —— 最后的兜底。

用法::

    python tools/audit_policy_families.py            # 人读表
    python tools/audit_policy_families.py --json     # 机读（供扫描器/CI 用）
    python tools/audit_policy_families.py --only-mismatch

退出码恒为 0 —— 这是**审计**不是门禁：分类口径需要人来裁决，工具只负责把分歧摆清楚。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import policy_artifacts as pa  # noqa: E402

#: ``tools/sim2sim_headless.py::DEFAULT_CRITERIA`` 认识的族。
KNOWN_FAMILIES = (
    "velocity", "stand", "balance", "imitation", "acrobatics", "parkour",
    "manipulation", "reorient",
)

#: **技能**关键词：描述"这条策略要做什么"，优先级**高于**"用什么框架训出来的"。
#: （`go2w-himloco-handstand` 的 observation_kind 是 himloco → 框架是运动跟踪，
#: 但技能是倒立 —— 判据该按技能选，所以技能先判。）
_SKILL_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("parkour", ("parkour", "stair", "pie")),
    ("reorient", ("reorient", "inhand", "in-hand")),
    ("imitation", ("backflip", "jump", "dance", "mimic", "gangnam", "subject")),
    ("acrobatics", ("handstand", "roulade", "flip", "kickup", "kick-up")),
    ("manipulation", ("pick", "grasp", "retarget", "ball-kick", "kick-left", "kick-right")),
    ("balance", ("balance", "leggedstand", "stand-front", "front-stand")),
    ("stand", ("stand", "sitstand", "hold")),
)

#: ``observation_kind`` 的 **token**（按 `_`/`-` 分词）→ 族。
#: 分词是必须的：早期版本用子串匹配，`locomotion` 会被 'motion' 命中，把 g1 的速度策略
#: 误判成模仿类。`motion`（动作模仿）刻意排在最后。
_OBS_TOKEN_RULES: tuple[tuple[str, str], ...] = (
    ("reorient", "reorient"),
    ("locomotion", "velocity"),
    ("himloco", "velocity"),
    ("velocity", "velocity"),
    ("sdk", "velocity"),
    ("cts", "velocity"),
    ("moe", "velocity"),
    ("zexw", "velocity"),
    ("dreamwaq", "velocity"),
    ("motion", "imitation"),
)


def _tokens(text: str) -> list[str]:
    """按非字母数字切词（`g1_mjswan_locomotion` → [g1, mjswan, locomotion]）。"""
    normalized = str(text).lower()
    for separator in ("-", "_", ".", "/"):
        normalized = normalized.replace(separator, " ")
    return normalized.split()


def _keywords(declaration: dict[str, Any]) -> str:
    return " ".join(str(declaration.get(key) or "") for key in ("policy_id", "label")).lower()


def recommend_family(declaration: dict[str, Any]) -> dict[str, Any]:
    """按证据推族，返回 ``{"family", "confidence", "reasons"}``。

    优先级：**技能关键词 → 观测种类 token → command_dims 推断**。
    ``confidence`` 如实区分「有证据」与「只能推断」，避免把猜测当成结论。
    """
    contract = declaration.get("contract") or {}
    obs_kind = str(contract.get("observation_kind") or "")
    keywords = _keywords(declaration)

    for family, tokens in _SKILL_RULES:
        hit = [token for token in tokens if token in keywords]
        if hit:
            return {
                "family": family, "confidence": "high",
                "reasons": [f"id/label 命中 {hit} → {family}（技能优先于训练框架）"],
            }

    obs_tokens = _tokens(obs_kind)
    for token, family in _OBS_TOKEN_RULES:
        if token in obs_tokens:
            return {
                "family": family, "confidence": "high",
                "reasons": [f"observation_kind={obs_kind} 的 token 含 {token!r} → {family}"],
            }

    # 参考动作 csv：只在**文件名与策略 id 有共同词**时才算证据 ——
    # 同一个 policies/ 目录里往往躺着别的策略的 motion csv（go2 包里 backflip/jump 的 csv
    # 曾把 parkour 策略误判成模仿类），按目录整体判定是错的。
    policy_tokens = set(_tokens(declaration.get("policy_id") or ""))
    for csv_path in sorted((_declaration_dir(declaration) or Path()).glob("*.csv")):
        if policy_tokens & set(_tokens(csv_path.stem)):
            return {
                "family": "imitation", "confidence": "high",
                "reasons": [f"参考动作 {csv_path.name} 与策略 id 同词 → imitation"],
            }

    command_dims = contract.get("command_dims") or declaration.get("command_dims")
    family = "velocity" if command_dims == 3 else "stand"
    return {
        "family": family, "confidence": "low",
        "reasons": [f"无技能关键词/观测 token 证据；仅按 command_dims={command_dims} 推断 → {family}"],
    }


def _declaration_dir(declaration: dict[str, Any]) -> Path | None:
    """声明里主 blob 所在目录（用于找参考动作 csv）；解析不到就返回 ``None``。"""
    blob = declaration.get("onnx") or pa.policy_blob_path(declaration)
    return blob.parent if blob else None


def audit(*, robots_dir: Path | str = pa.ROBOTS_DIR) -> dict[str, Any]:
    """逐条比对「声明族」与「证据族」，产出分歧清单。"""
    rows: list[dict[str, Any]] = []
    for declaration in pa.scan_declarations(robots_dir):
        contract = declaration.get("contract") or {}
        declared = contract.get("task_type") or declaration.get("task_type")
        recommendation = recommend_family(declaration)
        rows.append({
            "robot": declaration["robot"],
            "policy_id": declaration["policy_id"],
            "label": declaration.get("label"),
            "declared_family": declared,
            "recommended_family": recommendation["family"],
            "confidence": recommendation["confidence"],
            "reasons": recommendation["reasons"],
            "observation_kind": contract.get("observation_kind"),
            "command_dims": contract.get("command_dims"),
            "history_len": declaration.get("history_len"),
            "kind": declaration.get("kind"),
            "status": _status(declared, recommendation),
        })
    return {
        "declared_total": len(rows),
        "mismatch": [row for row in rows if row["status"] != "agree"],
        "rows": rows,
        "unknown_declared": sorted({
            str(row["declared_family"]) for row in rows
            if row["declared_family"] and row["declared_family"] not in KNOWN_FAMILIES
        }),
    }


def _status(declared: Any, recommendation: dict[str, Any]) -> str:
    """``mismatch`` = 有证据的分歧（多半是声明错了）；``weak`` = 只有推断，待人工裁决。"""
    if not declared:
        return "missing"          # 声明缺失：判据只能靠推断，风险最高
    if str(declared) == recommendation["family"]:
        return "agree"
    return "mismatch" if recommendation["confidence"] == "high" else "weak"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="策略任务族分类审计（声明 vs 证据）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--only-mismatch", action="store_true", help="只列分歧项")
    args = parser.parse_args(argv)

    report = audit()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    rows = report["mismatch"] if args.only_mismatch else report["rows"]
    print(f"策略声明 {report['declared_total']} 条；分歧/缺失 {len(report['mismatch'])} 条")
    if report["unknown_declared"]:
        print(f"未知的声明族（判据表里没有）：{', '.join(report['unknown_declared'])}")
    print()
    print(f"{'机器人':<20}{'策略':<26}{'声明':<12}{'证据推出':<12}状态")
    print("-" * 92)
    for row in rows:
        print(
            f"{row['robot']:<20}{row['policy_id']:<26}"
            f"{str(row['declared_family'] or '—'):<12}{row['recommended_family']:<12}"
            f"{ {'agree': '一致', 'missing': '声明缺失', 'mismatch': '不一致', 'weak': '仅推断'}[row['status']] }"
        )
        if row["status"] != "agree":
            for reason in row["reasons"]:
                print(f"{'':<20}└ {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
