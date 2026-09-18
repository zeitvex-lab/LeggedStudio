#!/usr/bin/env python3
"""N6：任务清单「验收判据」的可查性门禁（**守回归**，不假装能自动分类）。

## 设计为什么改了两次（值得记下来）

第一版按"验收列里有没有写 `tools/xxx.py` / `test_xxx.py`"来判定可机验 —— 跑出来 **108 条"人工"**，
明显失真：绝大多数验收是**行为描述**（如"断 CUDA / 卸 mjlab / 空注册表，各能定位到层"），
本来就不会写出工具路径。**这个判据把"没写路径"当成了"没验证"** —— 与事实不符。

所以本门禁不再假装能判定"这条到底有没有机器判据"，只做一件**能诚实做到**的事：
**从任务清单里能否查到机器判据的线索**（该条提到的产物真实存在），并**守住这个数量不倒退**。

* `machine_textual`：条目里提到了**真实存在**的产物（`tools/*.py`、`test_*.py`、`registry/*.json`、`npm run *`）
  且状态里有验证词（进 CI / 门禁 / 勾 / 已达成）—— 即"**有据可查**"；
* 其余记为**未发现机器判据线索** —— 注意这是"**没查到**"，**不是**"没有"（可能有测试但清单没提）。

**守的是**：`machine_textual` 数量一旦**下降** ⇒ 判红（有人把"有据可查"改成了"查不到据"，
或者删掉了引用）。上升只报告不判红（改善不需要批准）。

## 边界

文本级 + 只判"线索是否存在"：绿 = "有据可查的条数没倒退"，**不 = "每条都被验证过"**。
真正精确的可机验性分类需要人工逐条判读（审计里那次 34/30 的判断就是人工读出来的）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKLIST = ROOT / "00_know" / "05_任务清单.md"

ARTIFACT = re.compile(r"(tools/[\w./-]+\.py|test_[\w]+\.py|registry/[\w./-]+\.json|\.cnb\.yml|npm run [\w:]+)")
VERIFY_WORDS = ("进 CI", "已进 CI", "门禁", "✓", "已达成", "全绿")

#: **冻结基线**：有据可查的条数（2026-09-16 实测）。下降 ⇒ 判红。
BASELINE_MACHINE_TEXTUAL = 52  # 2026-09-18 重排后重冻：结构性重排压缩巨行、但按行补回证据指针（上一冻结值 43）

#: **解析覆盖基线**：能解析出的 4 列任务行数（2026-09-16 实测 110）。
#: 行数掉了 ⇒ 判红（否则"条目被改成别的表形"会让统计静默失真）。
BASELINE_PARSED_ROWS = 139  # 2026-09-18 重排后重冻：140 条全量 4 列可解析（上一冻结值 110）


def _rows(text: str) -> list[dict]:
    rows: list[dict] = []
    for line in text.splitlines():
        if not line.startswith("| **"):
            continue
        cells = [cell.strip() for cell in line.split("|")[1:-1]]
        if len(cells) < 4:
            continue
        identifier = re.sub(r"[*\s]", "", cells[0])
        if not re.fullmatch(r"[A-Z]{1,2}\d+", identifier):
            continue
        rows.append({
            "id": identifier,
            "task": cells[1],
            "status": cells[2],
            "acceptance": cells[3],
            "row": " | ".join(cells),
        })
    return rows


def _artifact_exists(reference: str) -> bool:
    if reference == ".cnb.yml":
        return (ROOT / ".cnb.yml").is_file()
    if reference.startswith("npm run"):
        return True  # 由 package.json 定义
    path = ROOT / reference
    if path.is_file():
        return True
    return any(ROOT.rglob(Path(reference).name))


def has_evidence(row: dict) -> tuple[bool, str]:
    """该条目**在清单文本里**有没有可查的机器判据线索。"""

    text = row["row"]
    hits = [hit for hit in ARTIFACT.findall(text) if _artifact_exists(hit)]
    verified = any(word in row["status"] or word in row["acceptance"] for word in VERIFY_WORDS)
    if hits and verified:
        return True, f"{hits[0]}"
    if hits and not verified:
        return False, f"提到产物 {hits[0]} 但没说验证过"
    return False, "清单里没写产物/测试路径"


def audit(path: Path | None = None) -> dict:
    target = path or TASKLIST
    if not target.is_file():
        return {"ok": False, "problems": [f"任务清单不存在：{target}"], "text_level_only": True}
    rows = _rows(target.read_text(encoding="utf-8"))

    evidenced: list[dict] = []
    unevidenced: list[dict] = []
    for row in rows:
        ok, reason = has_evidence(row)
        (evidenced if ok else unevidenced).append({"id": row["id"], "why": reason})

    problems: list[str] = []
    if len(rows) < BASELINE_PARSED_ROWS:
        problems.append(
            f"能解析出的任务行数从 {BASELINE_PARSED_ROWS} **降到 {len(rows)}** —— "
            "要么条目被删，要么表形变了（本门禁只认 4 列任务表）。请核对后同步基线"
        )
    if len(evidenced) < BASELINE_MACHINE_TEXTUAL:
        problems.append(
            f"有据可查的条数从 {BASELINE_MACHINE_TEXTUAL} **降到 {len(evidenced)}** —— "
            "要么是有人删了引用，要么是条目被改写成了'查不到据'。请核对后同步基线"
        )

    return {
        "ok": not problems,
        "total": len(rows),
        "machine_textual": len(evidenced),
        "uncertain": len(unevidenced),
        "baseline": BASELINE_MACHINE_TEXTUAL,
        "baseline_parsed_rows": BASELINE_PARSED_ROWS,
        "evidenced": evidenced,
        "uncertain_ids": [item["id"] for item in unevidenced],
        "problems": problems,
        # 如实声明边界
        "text_level_only": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="N6 验收判据可查性门禁")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--freeze", action="store_true", help="输出当前实测值（用于更新基线）")
    args = parser.parse_args(argv)
    report = audit()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1
    print("=" * 78)
    print("N6 验收判据可查性（文本级线索，守回归）")
    print("=" * 78)
    if "total" in report:
        print(f"条目 {report['total']}")
        print(f"**有据可查（清单里提到了真实存在的产物 + 写了验证）: {report['machine_textual']}**"
              f"（基线 {report['baseline']}）")
        print(f"未发现机器判据线索: {report['uncertain']} —— **这是「没查到」，不是「没有」**")
    if args.freeze:
        print(f"\nBASELINE_MACHINE_TEXTUAL = {report['machine_textual']}")
    if report["problems"]:
        print("-" * 78)
        for item in report["problems"]:
            print(f"✗ {item}")
    else:
        print("-" * 78)
        print("✓ 有据可查的条数没有倒退")
    print("注意：**文本级**判定 —— 绿 = 有据可查的条数没倒退，**不 = 每条都被验证过**；"
          "精确的可机验性分类需要人工逐条判读。")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
