"""任务清单进度统计（自动、可复跑）——把「已完成 N / 部分完成 N / 未做 N」从手写数字变成实测。

## 为什么需要它

`00_know/05_任务清单.md` 头部有一行「已完成 57 / 部分完成 8 / 未做 34」，它是**手写的**，
而且**不在** `doc_reality_check.py` 的锚点里（CI 不抓），于是随推进一路漂到失真
（2026-09-15 实测：明确「已完成」的条目已有 60+，而它写 57；「未做」实测 6，它写 34）。

## 口径（只认状态列的**开头标记**，规则简单可 review）

- ``✓`` 或 ``已完成``          → done
- ``部分完成`` / ``部分`` / ``半成品`` / ``进行中`` → partial
- ``未做`` / ``未动``          → todo
- ``不做`` / ``不投入``        → wontfix
- ``已归档`` / ``已裁决关闭`` / ``关闭`` / ``结论留档`` / ``勿再提`` → closed
- 其余（路径引用、``覆盖面已达标``、``现有多策略文件``、``依托 XX``、``CLI …`` 等）→ note
  （记录/参考类，**不计入五桶** —— 这正是老计数行混进去后失真的来源）

归类取**各规则标记在状态格里最早出现的位置**，位置最小者胜（同位置按 ``_RULES`` 表序）——
而不是"按规则表顺序做子串包含"。理由：状态格常先写主状态、后写附带事实
（例：B8「**部分完成**：…**go1 已完成**」）——若按表序包含匹配，附带事实会把整格改判成
done，与"只认**开头**标记"的口径相悖（2026-09-19 实测该误判把 B8 记成了已完成）。

用法::

    python tools/count_tasklist.py
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKLIST = ROOT / "00_know" / "05_任务清单.md"

#: 桶判定顺序（先命中先得；``note`` 是兜底）
_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("done", ("✓", "已完成")),
    ("partial", ("部分完成", "部分", "半成品", "进行中")),
    ("todo", ("未做", "未动")),
    ("wontfix", ("不做", "不投入")),
    ("closed", ("已归档", "已裁决关闭", "关闭", "结论留档", "勿再提")),
]


def _bucket_for(status: str) -> str:
    """取状态格里**最早出现的标记**所属的桶（都不命中回落到 ``note``）。"""
    best: tuple[int, int, str] | None = None
    for order, (name, markers) in enumerate(_RULES):
        positions = [status.find(marker) for marker in markers if marker in status]
        if not positions:
            continue
        candidate = (min(positions), order, name)
        if best is None or candidate < best:
            best = candidate
    return best[2] if best else "note"


def count() -> dict:
    """逐条归类，返回分组计数与桶计数。"""
    if not TASKLIST.is_file():
        raise SystemExit(f"找不到 {TASKLIST}")
    group: Counter = Counter()
    buckets: Counter = Counter()
    note_ids: list[str] = []

    for line in TASKLIST.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 3:
            continue
        m = re.match(r"^\*\*([A-Z]+)(\d+)\*\*", cells[0])
        if not m:
            continue
        group[m.group(1)] += 1
        status = cells[2]
        bucket = _bucket_for(status)
        buckets[bucket] += 1
        if bucket == "note":
            note_ids.append(f"{m.group(1)}{m.group(2)}")
    return {"group": dict(group), "buckets": dict(buckets), "note_ids": note_ids}


def main() -> int:
    result = count()
    group = result["group"]
    buckets = result["buckets"]
    order = sorted(group, key=lambda g: (g != "H", g))
    group_text = " / ".join(f"{g} {group[g]}" for g in order)
    total = sum(group.values())

    print(f"条目 {total} 条（{group_text}）")
    print(f"已完成 {buckets.get('done', 0)} / 部分完成 {buckets.get('partial', 0)}"
          f" / 未做 {buckets.get('todo', 0)} / 不做 {buckets.get('wontfix', 0)}"
          f" / 已关闭 {buckets.get('closed', 0)} / 记录·参考 {buckets.get('note', 0)}")
    if result["note_ids"]:
        print(f"记录·参考类（不计五桶）：{'、'.join(result['note_ids'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
