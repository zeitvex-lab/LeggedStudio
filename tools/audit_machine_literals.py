#!/usr/bin/env python3
"""Phase 5 余项（`00_know/06` §17）：**web / kits 的机型字面量**进零特判扫描面（豁免 = 测试 + 基线）。

**为什么只有这两处**：§11.4 实测的硬编码分布里，`backend/policy_artifacts.py` 的机型硬表已迁
`registry/observation_kinds.json`（Phase 5 首项）；剩下的密集点就是**前端**（`web/sim2sim/app.js`）
与 **Kit 层**（`adapters/mjlab/kits/`）——后者按族设计**本不该出现机型名**。本工具把这两处扫起来，
"新加一个机型分支"从此有机器判据，而不是靠纪律。

**扫描口径（两套，各取最精确的那套）**：

* **Python（kits）走 AST**：只数**代码里的字符串常量**，**模块/类/函数 docstring 一律不计**——
  kits 里绝大多数机型名出现在「来源：`assets/robots/unitree_go2/...`」这类**溯源注释/docstring**里，
  那是证据不是特判（grep 会把它们全算上，AST 不会）。
* **JS（web）走注释剥离后的文本扫描**：注释（`//` 与 `/* */`）不算，字符串与代码都算（前端机型分支
  常常是对象键或字符串键，不是字符串字面量）。vendored 库与 `*.test.mjs` 不在扫描面。

**词表**：从 `assets/robots/` 的**包名派生**（新增机型自动进词表），加 `_`/`-` 互换的变体
（`zex-w` ↔ `zex_w`）。**刻意不含短键**（`go2` / `m20` / `b2` 之类）：它们在文本里到处都是，
收进来只会制造噪声；代价是「短键新增特判」抓不到 —— 这是本门禁**登记在案的边界**。

**门禁语义（同 `audit_plugin_unification.py`）**：只守"不许涨"——任一文件命中数**高于**基线、
或**出现新文件** ⇒ exit 1。基线的收紧用 `--write-baseline`（**显式动作**，与判红分开）。

用法::

    python tools/audit_machine_literals.py                # 对比基线（CI：涨了即红）
    python tools/audit_machine_literals.py --json         # 机器可读
    python tools/audit_machine_literals.py --write-baseline   # 刷新基线（显式）
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ROBOTS_DIR = ROOT / "assets" / "robots"
KITS_DIR = ROOT / "adapters" / "mjlab" / "kits"
WEB_DIR = ROOT / "web"
BASELINE_PATH = ROOT / "tools" / "baselines" / "machine_literals.json"

#: 扫描面：Python = kits（AST）；JS = web 下非 vendored、非测试的脚本。
JS_SKIP_PARTS = {"vendor", "assets", "models", "node_modules"}
JS_TARGET_SUFFIXES = (".js", ".mjs")


# ---------------------------------------------------------------------------
# 词表（从包名派生）
# ---------------------------------------------------------------------------
def machine_vocabulary() -> list[str]:
    """机型词表：`assets/robots/` 的包名 + `_`/`-` 互换变体，**长的在前**（避免前缀误吞）。"""
    ids: set[str] = set()
    if ROBOTS_DIR.is_dir():
        ids |= {path.name for path in ROBOTS_DIR.iterdir() if path.is_dir()}
    ids |= {value.replace("_", "-") for value in ids}
    ids |= {value.replace("-", "_") for value in ids}
    return sorted(ids, key=lambda value: (-len(value), value))


def _pattern(vocabulary: list[str]) -> re.Pattern:
    # 词表已按长度降序：交替分支天然优先匹配更长的 id（unitree_go2w 先于 unitree_go2）。
    return re.compile("|".join(re.escape(value) for value in vocabulary))


# ---------------------------------------------------------------------------
# Python：AST 数"代码里的字符串常量"（docstring 不计）
# ---------------------------------------------------------------------------
def _docstring_nodes(tree: ast.AST) -> set[int]:
    """收集 docstring 常量节点的 id（模块/类/函数的首语句）。"""
    found: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            found.add(id(first.value))
    return found


def count_python_source(text: str, pattern: re.Pattern) -> int:
    """Python 源码里的机型字面量命中数（字符串常量，docstring 排除）。"""
    tree = ast.parse(text)
    docstrings = _docstring_nodes(tree)
    hits = 0
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in docstrings):
            hits += len(pattern.findall(node.value))
    return hits


# ---------------------------------------------------------------------------
# JavaScript：先剥注释（保字符串），再数
# ---------------------------------------------------------------------------
def strip_js_comments(text: str) -> str:
    """剥掉 JS 注释（`//` 与 `/* */`），**保留字符串内容**与换行（长度不变，便于报行）。

    小状态机：normal / line / block / string('…'、"…"、`…` 带反斜杠转义）。
    """
    out: list[str] = []
    index, length = 0, len(text)
    state = "normal"
    quote = ""
    while index < length:
        char = text[index]
        nxt = text[index + 1] if index + 1 < length else ""
        if state == "normal":
            if char == "/" and nxt == "/":
                state = "line"
                out.append("  ")
                index += 2
                continue
            if char == "/" and nxt == "*":
                state = "block"
                out.append("  ")
                index += 2
                continue
            if char in ("'", '"', "`"):
                state = "string"
                quote = char
                out.append(char)
                index += 1
                continue
            out.append(char)
            index += 1
            continue
        if state == "line":
            if char == "\n":
                state = "normal"
                out.append(char)
            else:
                out.append(" ")
            index += 1
            continue
        if state == "block":
            if char == "*" and nxt == "/":
                state = "normal"
                out.append("  ")
                index += 2
                continue
            out.append("\n" if char == "\n" else " ")
            index += 1
            continue
        # string
        out.append(char)
        if char == "\\" and index + 1 < length:
            out.append(text[index + 1])
            index += 2
            continue
        if char == quote:
            state = "normal"
        index += 1
    return "".join(out)


def count_js_source(text: str, pattern: re.Pattern) -> int:
    return len(pattern.findall(strip_js_comments(text)))


# ---------------------------------------------------------------------------
# 扫描面
# ---------------------------------------------------------------------------
def py_targets() -> list[Path]:
    if not KITS_DIR.is_dir():
        return []
    return sorted(path for path in KITS_DIR.rglob("*.py") if "__pycache__" not in path.parts)


def js_targets() -> list[Path]:
    if not WEB_DIR.is_dir():
        return []
    out: list[Path] = []
    for path in sorted(WEB_DIR.rglob("*")):
        if not path.is_file() or path.suffix not in JS_TARGET_SUFFIXES:
            continue
        if set(path.parts) & JS_SKIP_PARTS:
            continue
        if path.name.endswith((".test.mjs", ".test.js")):
            continue
        out.append(path)
    return out


def scan() -> dict[str, int]:
    """返回 `{相对路径: 命中数}`（只收 > 0 的文件）。"""
    pattern = _pattern(machine_vocabulary())
    counts: dict[str, int] = {}
    for path in py_targets():
        hits = count_python_source(path.read_text(encoding="utf-8-sig"), pattern)
        if hits:
            counts[path.relative_to(ROOT).as_posix()] = hits
    for path in js_targets():
        hits = count_js_source(path.read_text(encoding="utf-8-sig"), pattern)
        if hits:
            counts[path.relative_to(ROOT).as_posix()] = hits
    return counts


# ---------------------------------------------------------------------------
# 门禁
# ---------------------------------------------------------------------------
def compare_to_baseline(counts: dict[str, int], baseline: dict[str, int]) -> list[str]:
    """只守"不许涨"：新文件 或 命中数高于基线 ⇒ 判红。"""
    problems: list[str] = []
    for path, value in sorted(counts.items()):
        base = baseline.get(path)
        if base is None:
            problems.append(f"{path}: 新出现机型字面量 {value} 处（基线里没有这个文件）")
        elif value > base:
            problems.append(f"{path}: 机型字面量 {base} → {value}（只许减少）")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="web/kits 机型字面量门禁（只减不涨）")
    parser.add_argument("--write-baseline", action="store_true", help="刷新基线（显式动作）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    vocabulary = machine_vocabulary()
    counts = scan()
    if args.write_baseline:
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(json.dumps({
            "schema": "machine-literals-baseline-1.0",
            "note": "web/kits 机型字面量基线（只减不涨）。刷新 = 显式动作（--write-baseline），"
                    "与「判红」分开；词表从 assets/robots 包名派生，不含短键（见工具 docstring 的边界）。",
            "vocabulary": vocabulary,
            "counts": counts,
        }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"基线已刷新：{BASELINE_PATH}")
        print(json.dumps(counts, ensure_ascii=False, indent=1))
        return 0

    baseline_doc = (json.loads(BASELINE_PATH.read_text(encoding="utf-8-sig"))
                    if BASELINE_PATH.is_file() else {})
    baseline = dict(baseline_doc.get("counts") or {})
    problems = compare_to_baseline(counts, baseline)

    if args.json:
        print(json.dumps({"counts": counts, "baseline": baseline,
                          "problems": problems}, ensure_ascii=False, indent=2))
    else:
        print("web/kits 机型字面量（词表：包名 + 变体，不含短键）：")
        for path, value in sorted(counts.items()):
            base = baseline.get(path)
            mark = "" if base is None else ("" if value <= base else "  ← 高于基线")
            print(f"  {path:60s} {value:3d}（基线 {base if base is not None else '—'}）{mark}")
        if not baseline:
            print(f"  [SKIP] 无基线（{BASELINE_PATH}）：只报告不判红，刷新用 --write-baseline")
        elif problems:
            print("\n判红：")
            for problem in problems:
                print(f"  - {problem}")
        else:
            print("\n✓ 无新增机型字面量（无新文件、无文件高于基线）")
    if not baseline:
        return 0  # 无基线 = 只报告（判红要有基线才成立）
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
