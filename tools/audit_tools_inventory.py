#!/usr/bin/env python3
"""N7：`tools/` 工具**登记表**门禁（工具名 → 有没有人用）。

## 为什么要有它

`tools/` 下 50+ 个脚本，很多只在正文里被**顺口提过**、或被测试间接用到，
没有任何地方说清"哪个工具是**在维护的**、谁在消费它"。后果：

* 出问题时不知道该信哪个工具；
* 孤儿工具会一直躺着（有的连自己都跑不起来），没人敢删也没人敢用。

本门禁**不要求**每个工具都被 CI 调用（很多是一次性探查脚本，合理），
它要求的是：**孤儿必须显式登记**。两条双向规则（与 N2 同一套）：

1. 出现**新的**孤儿工具 ⇒ 判红（要么接进某个消费者，要么登记 + 说明用途）；
2. 登记的孤儿**被用上了** ⇒ 也判红（名单过期就是谎言）。

## 边界

**引用检测是文本级的**：某工具被 `package.json` / `.cnb.yml` / 文档 / 测试 / 其他工具提到即算"有人用"，
**不判断那次引用是否真的在跑**（例如文档里提一句也算）。所以绿 = "没有未登记的孤儿"，不 = "每个工具都被验证过"。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"

#: 消费面：这些地方提到工具名即算"有人用"
#:
#: 注意本清单只管 **tools/** 下的孤儿检测；`adapters/*` 里的可执行入口
#: （如 `adapters/github/mirror.py`）不在这套判据内 —— 它们由 `.cnb.yml` 的
#: github-mirror pipeline 直接调用，属于"随适配器走"的成员，与
#: `adapters/backend_adapter.py` 同惯例。
CONSUMERS = (
    "package.json",
    ".cnb.yml",
    "README.md",
    "00_know/05_任务清单.md",
    "00_know/01_项目定位.md",
    "00_know/04_参数真值标准.md",
    "00_know/03_参考项目与资源.md",
    "00_know/02_项目规划.md",
    "00_know/06_统一架构方案.md",
    "00_know/README.md",
    # 2026-09-28 结构性重排：任务清单历史行整体归档，工具引用随行搬家——语料面跟着扩
    "00_know/90_归档/08_任务清单_阶段桶与队列_20260928.md",
    "00_know/90_归档/09_任务清单_进度流水_20260928.md",
    "docs/cloud-dev.md",
    "docs/desktop-app.md",
    "docs/web-app.md",
)

#: **已登记的孤儿工具**（2026-09-16 冻结）。新孤儿判红；名单里的被用上，也判红。
EXPECTED_UNREFERENCED: frozenset[str] = frozenset({
    # `convert_policy.py` 不在此列：门禁复核发现它在清单别处**确实被引用**（抓对了，从名单移出）
    "dedup_training_config.py",
    "fix_policy_families.py",
    # `fix_policy_gains.py` **已移出**（2026-09-22）：它被 `05_任务清单.md` 的第十二笔轮次
    # 日志（第十二笔用它补包级增益）与 `06_统一架构方案.md` 点到名 —— 按本文件的判据
    # （"文档里提一句也算"、且流水排 §N 之后 ⇒ 算真引用）它已不是孤儿了。如实记：这
    # 只说明**有人提到它**，不说明**有人验证过它**（见文件头"绿 ≠ 每个工具都被验证过"）。
    "generate_asset_inventory.py",
    "migrate_contract.py",
    "stl_volume.py",
    "urdf_validator.py",
})


def _tool_files() -> list[Path]:
    files = [path for path in TOOLS_DIR.glob("*.py") if path.is_file()]
    for sub in ("mcp", "baselines"):
        directory = TOOLS_DIR / sub
        if directory.is_dir():
            files.extend(path for path in directory.glob("*.py") if path.is_file())
    return sorted(files, key=lambda item: str(item))


#: 任务清单 §N 段的标题（**只此一份**）。
#:
#: 2026-09-22 修：原先这里写死 `"## N. 2026-09-16 全面审计"`，而那一节后来改名成了
#: `"## N. 审计登记（…）"` ⇒ `find` 恒为 -1 ⇒ **守卫静默失效**（没有测试守它，谁也没发现）。
#: 代价是自反馈又回来了：§N 表里写到的名字会把自己算成"有人用"。两处配套改动：
#:   ① 只切**这一节**（标题 → 下一个 `## `），不再"从此切到文末"——轮次日志（进度流水）
#:      排在 §N 之后，那里的引用是**真引用**（`quality_exp_resampling.py` 就只被它提到）；
#:   ② 标题找不到 ⇒ **直接抛**（fail-closed）。宁可门禁炸掉报出来，也不要静默地什么都没切。
N_SECTION_HEADING = "## N. 审计登记"

#: 任务清单家族：活清单 + 归档 08（2026-09-28 结构性重排后 §N 随历史行住进归档）。
#: §N 段可能出现在其中**任一**文件；**全部都没有** ⇒ fail-closed（见 `_corpus` 末尾）。
N_SECTION_FILES = (
    "00_know/05_任务清单.md",
    "00_know/90_归档/08_任务清单_阶段桶与队列_20260928.md",
)


def _without_n_section(text: str) -> str:
    """去掉任务清单的 §N 段（审计自己的登记表，不算"消费者"）。找不到标题即抛。"""
    start = text.find(N_SECTION_HEADING)
    if start < 0:
        raise ValueError(
            f"任务清单里找不到 §N 标题 {N_SECTION_HEADING!r}——切除点又过期了。"
            "请同步 N_SECTION_HEADING：否则 §N 里的名字会把自己算成'有人用'，门禁静默放水。"
        )
    end = text.find("\n## ", start + len(N_SECTION_HEADING))
    return text[:start] if end < 0 else text[:start] + text[end:]


def _corpus() -> dict[str, str]:
    texts: dict[str, str] = {}
    found_n_section = False
    for relative in CONSUMERS:
        path = ROOT / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        # 任务清单家族的 §N 段是**审计自己写的登记**（里面就列着孤儿名单），不是"消费者"。
        # 不切掉它就会自反馈：名单一写进去，9 个孤儿立刻"有人用了"（第一版就这么错的）。
        # 2026-09-28 重排：§N 随历史行住进归档 08——切除跟着走；单个文件没有 §N 不算错
        # （活清单已不含），但**家族里一个都没有** ⇒ fail-closed 抛错。
        if relative in N_SECTION_FILES and N_SECTION_HEADING in text:
            found_n_section = True
            text = _without_n_section(text)
        texts[relative] = text
    if not found_n_section:
        raise ValueError(
            f"任务清单家族（{N_SECTION_FILES}）里都找不到 §N 标题 {N_SECTION_HEADING!r}"
            "——切除点过期了。否则 §N 里的名字会把自己算成'有人用'，门禁静默放水。"
        )
    # 工具之间互相引用也算"有人用"。
    # **但本文件要排除**：它自己存着孤儿冻结名单，名单里的名字会"自己引用自己"，
    # 把 9 个孤儿全变成"有人用"（第一版就这么错了，跑出来"孤儿 0"）。
    for path in _tool_files():
        if path.name == "audit_tools_inventory.py":
            continue
        texts[path.relative_to(ROOT).as_posix()] = path.read_text(encoding="utf-8", errors="replace")
    # 测试引用也算
    for path in (ROOT / "backend").glob("test_*.py"):
        texts[path.relative_to(ROOT).as_posix()] = path.read_text(encoding="utf-8", errors="replace")
    return texts


def audit(tools_dir: Path | None = None, corpus: dict[str, str] | None = None) -> dict:
    global TOOLS_DIR
    previous = TOOLS_DIR
    if tools_dir is not None:
        TOOLS_DIR = tools_dir
    try:
        files = _tool_files()
    finally:
        TOOLS_DIR = previous

    texts = corpus if corpus is not None else _corpus()
    orphans: list[str] = []
    inventory: list[dict] = []
    for path in files:
        name = path.name
        stem = path.stem
        referenced_by: list[str] = []
        for source, text in texts.items():
            if source.endswith(f"tools/{name}") or source.endswith(f"tools/mcp/{name}") or source.endswith(f"tools/baselines/{name}"):
                continue  # 自己不算
            if name in text or re.search(rf"\b{re.escape(stem)}\b", text):
                referenced_by.append(source)
        entry = {"tool": name, "referenced_by": sorted(referenced_by)[:4], "references": len(referenced_by)}
        inventory.append(entry)
        if not referenced_by:
            orphans.append(name)

    orphan_set = set(orphans)
    problems: list[str] = []
    for name in sorted(orphan_set - set(EXPECTED_UNREFERENCED)):
        problems.append(
            f"{name}: **孤儿工具**（没有任何消费者提到它）—— 要么接进某个消费者，"
            "要么登记进 EXPECTED_UNREFERENCED 并说明它的用途（一次性探查脚本也算合理）"
        )
    for name in sorted(set(EXPECTED_UNREFERENCED) - orphan_set):
        problems.append(f"{name}: 已登记的孤儿**现在有人用了** —— 请把它从 EXPECTED_UNREFERENCED 移出")

    return {
        "ok": not problems,
        "tools": len(files),
        "referenced": len(files) - len(orphans),
        "orphans": sorted(orphans),
        "inventory": inventory,
        "problems": problems,
        # 如实声明边界
        "text_level_only": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="N7 工具登记表门禁")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = audit()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1
    print("=" * 78)
    print("N7 tools/ 工具登记表（谁在用）")
    print("=" * 78)
    print(f"工具 {report['tools']} 个｜有人引用 {report['referenced']}｜**孤儿 {len(report['orphans'])}**")
    if report["orphans"]:
        print(f"孤儿清单：{', '.join(report['orphans'])}")
    if report["problems"]:
        print("-" * 78)
        for item in report["problems"]:
            print(f"✗ {item}")
    else:
        print("-" * 78)
        print("✓ 没有未登记的孤儿工具")
    print("注意：引用检测是**文本级**的（提一句也算），**不判断那次引用是否在跑**。")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
