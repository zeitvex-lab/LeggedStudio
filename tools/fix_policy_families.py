#!/usr/bin/env python
"""按训练源头证据修正策略 `task_type`（分类错误的定点修复）。

**为什么要有这个工具而不是手改**：`task_type` 决定 `tools/sim2sim_headless.py` 套哪套判据，
改它是"改判据归属"，必须留痕、可复核、可回放；而且它天然是**数据修复**（不属于审计、不属于门禁）。

**本次裁决依据**（2026-09-14，用户口径"按你的来"）：

| 策略 | 原声明 | 改为 | 训练源头证据 |
|---|---|---|---|
| `go2w-himloco-stand-front` | velocity | **balance** | label「前腿站立行走」；前腿站立不是速度跟踪 |
| `go2w-himloco-leggedstand` | acrobatics | **balance** | label「后腿站立」；是姿态技能不是特技 |
| `microduck-ball-kick-left` | stand | **manipulation** | `training_ref.upstream=microduck_ball_kick_env_cfg.py`（专门踢球任务） |
| `microduck-ball-kick-right` | stand | **manipulation** | 同上 |
| `go2-baseline-164k` | （无 contract） | **velocity** | 文件名 `go2_moe_cts_high_slope_164k.onnx`（MoE-CTS 速度族）+ 45 维/5 帧历史 |

`go2w-himloco-handstand`（倒立）**不动** —— 声明 acrobatics 是对的，属"特技暂缓"。

**注意**：`stand-front` / `leggedstand` 归 `balance` 只是"族名准确"，
它们的稳态高度天然偏离 `static_stand_height`，**不能套 height_ratio 硬门** ——
扫描器需把它们列入例外（用"自身稳态稳定性"判据），见任务清单 ★ 行的记录。

用法::

    python tools/fix_policy_families.py --check    # 只报告差异（默认）
    python tools/fix_policy_families.py --write    # 应用修正（逐份 JSON 校验后才写）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.policy_artifacts import ROBOTS_DIR  # noqa: E402

#: 定点修正表：``(robot, policy_id, family, 依据)``。
FIXES: tuple[tuple[str, str, str, str], ...] = (
    ("unitree_go2w", "go2w-himloco-stand-front", "balance",
     "label「前腿站立行走」——前腿站立不是速度跟踪"),
    ("unitree_go2w", "go2w-himloco-leggedstand", "balance",
     "label「后腿站立」——姿态技能，不是特技"),
    ("microduck", "microduck-ball-kick-left", "manipulation",
     "training_ref.upstream=microduck_ball_kick_env_cfg.py（专门踢球任务）"),
    ("microduck", "microduck-ball-kick-right", "manipulation",
     "training_ref.upstream=microduck_ball_kick_env_cfg.py（专门踢球任务）"),
)

#: 声明里完全没有 `contract` 块的条目：补一个最小 contract（族名可被引擎读到）。
#: 其余字段（observation_kind / action_joint_order / action_scale…）属**已知缺口**，
#: 需按同族策略对齐，不在本工具范围内（见任务清单 ★ 行）。
CONTRACT_BACKFILL: tuple[tuple[str, str, str, str], ...] = (
    ("unitree_go2", "go2-baseline-164k", "velocity",
     "文件名 moe_cts 属速度族 + 45 维/5 帧历史；原声明无 contract 块"),
)


def _config_path(robot: str) -> Path:
    return Path(ROBOTS_DIR) / robot / "simulation" / "config.json"


def _edit_task_type(text: str, policy_id: str, family: str) -> tuple[str, str | None]:
    """把 ``policy_id`` 那条策略对象内的 ``task_type`` 改成 ``family``。

    以策略 id 字符串为锚，只改它之后**第一次**出现的 ``task_type`` ——
    避免"同一文件里多条策略都写着 velocity 时改错行"。
    """
    try:
        anchor = text.index(f'"{policy_id}"')
    except ValueError:
        return text, None
    match = re.compile(r'"task_type":\s*"([a-z_]+)"').search(text, anchor)
    if not match:
        return text, None
    previous = match.group(1)
    return f"{text[:match.start(1)]}{family}{text[match.end(1):]}", previous


def _edit_backfill_contract(text: str, policy_id: str, family: str) -> tuple[str, bool]:
    """给没有 contract 块的条目插入一个最小 contract。"""
    marker = f'"id": "{policy_id}",\n'
    if text.count(marker) != 1 or '"contract"' in text.split(marker)[0][-400:]:
        return text, False
    inserted = (
        f'{marker}      "contract": {{\n'
        f'        "task_type": "{family}"\n'
        f'      }},\n'
    )
    return text.replace(marker, inserted, 1), True


def apply_fixes(*, write: bool = False) -> dict:
    """逐条应用修正；**任一份文件 JSON 校验不过就整份跳过**（绝不写坏配置）。"""
    changes: list[dict] = []
    problems: list[str] = []
    by_file: dict[str, str] = {}

    for robot, policy_id, family, reason in FIXES:
        path = _config_path(robot)
        text = by_file.get(str(path)) or path.read_text(encoding="utf-8")
        updated, previous = _edit_task_type(text, policy_id, family)
        if previous is None:
            problems.append(f"{robot}/{policy_id}：在配置里找不到该策略的 task_type")
            continue
        by_file[str(path)] = updated
        changes.append({
            "robot": robot, "policy_id": policy_id,
            "from": previous, "to": family, "reason": reason,
            "changed": previous != family,
        })

    for robot, policy_id, family, reason in CONTRACT_BACKFILL:
        path = _config_path(robot)
        text = by_file.get(str(path)) or path.read_text(encoding="utf-8")
        updated, ok = _edit_backfill_contract(text, policy_id, family)
        if not ok:
            problems.append(f"{robot}/{policy_id}：无法插入最小 contract（锚点不唯一或已存在）")
            continue
        by_file[str(path)] = updated
        changes.append({
            "robot": robot, "policy_id": policy_id,
            "from": None, "to": f"contract.task_type={family}", "reason": reason, "changed": True,
        })

    written: list[str] = []
    for path_str, text in by_file.items():
        path = Path(path_str)
        if not write or text == path.read_text(encoding="utf-8"):
            continue
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:      # fail-closed：绝不留下读不出来的配置
            problems.append(f"{path.parent.parent.name}：改写后 JSON 不合法，整份跳过（{exc}）")
            continue
        path.write_text(text, encoding="utf-8")
        written.append(str(path.relative_to(Path(ROBOTS_DIR).parent.parent)))

    return {
        "ok": not problems,
        "changed": [item for item in changes if item["changed"]],
        "unchanged": [item for item in changes if not item["changed"]],
        "written": written,
        "problems": problems,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="按训练源头证据修正策略 task_type")
    parser.add_argument("--write", action="store_true", help="应用修正（默认只报告）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = apply_fixes(write=args.write)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1

    for item in report["changed"]:
        before = item["from"] if item["from"] is not None else "（无）"
        print(f"  {item['robot']}/{item['policy_id']}：{before} → {item['to']}")
        print(f"      依据：{item['reason']}")
    if report["unchanged"]:
        print(f"  已是最新：{len(report['unchanged'])} 条")
    for problem in report["problems"]:
        print(f"  ✗ {problem}")
    print(f"{'已写入' if args.write else '待写入'} {len(report['written'])} 份配置；"
          f"改动 {len(report['changed'])} 条")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
