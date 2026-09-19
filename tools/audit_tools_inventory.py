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
    "00_know/07_形态Kit设计草案.md",
    "00_know/README.md",
    "docs/cloud-dev.md",
    "docs/desktop-app.md",
    "docs/web-app.md",
)

#: **已登记的孤儿工具**（2026-09-16 冻结）。新孤儿判红；名单里的被用上，也判红。
EXPECTED_UNREFERENCED: frozenset[str] = frozenset({
    # `convert_policy.py` 不在此列：门禁复核发现它在清单别处**确实被引用**（抓对了，从名单移出）
    "dedup_training_config.py",
    "fix_policy_families.py",
    "fix_policy_gains.py",
    "generate_asset_inventory.py",
    "migrate_contract.py",
    "stl_volume.py",
    "urdf_to_mjcf.py",
    "urdf_validator.py",
})


def _tool_files() -> list[Path]:
    files = [path for path in TOOLS_DIR.glob("*.py") if path.is_file()]
    for sub in ("mcp", "baselines"):
        directory = TOOLS_DIR / sub
        if directory.is_dir():
            files.extend(path for path in directory.glob("*.py") if path.is_file())
    return sorted(files, key=lambda item: str(item))


def _corpus() -> dict[str, str]:
    texts: dict[str, str] = {}
    for relative in CONSUMERS:
        path = ROOT / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        # 任务清单的 §N 段是**审计自己写的登记**（里面就列着孤儿名单），不是"消费者"。
        # 不切掉它就会自反馈：名单一写进去，9 个孤儿立刻"有人用了"（第一版就这么错的）。
        if relative.endswith("05_任务清单.md"):
            cut = text.find("## N. 2026-09-16 全面审计")
            if cut > 0:
                text = text[:cut]
        texts[relative] = text
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
