#!/usr/bin/env python3
"""校验 `packs/` 下全部 Capability Pack（B1 剩余项：CI 与本地同一条命令）。

Pack 是纯引用组合（`morphology_ref × skill_ref [× scenario_ref] [× policy_ref]` + 四阶段
`bindings`），它的失效方式几乎都是「引用的文件被改过、哈希对不上」——2026-09-12 首次运行
本命令时就抓到 **14 份 Pack 全部过期**（D3/D4 保存链改写了 `contract.json`）。因此这条
命令的价值在于把这种漂移在 CI 里暴露出来，而不是等到加载策略时才炸。

用法：
    python tools/validate_packs.py            # 表格 + 失败时非零退出码
    python tools/validate_packs.py --json     # 机器可读（供 CI 归档）
    python tools/validate_packs.py --quiet    # 只回一行汇总
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.pack_catalog import pack_catalog  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 capability Pack（capability-pack-1.0）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出完整目录")
    parser.add_argument("--quiet", action="store_true", help="只输出一行汇总")
    args = parser.parse_args()

    catalog = pack_catalog()
    if args.json:
        print(json.dumps(catalog, ensure_ascii=False, indent=2))
    elif not args.quiet:
        print(f"packs 目录：{catalog['packs_dir']}")
        for entry in catalog["packs"]:
            mark = "OK  " if entry["valid"] else "FAIL"
            ref = (entry.get("morphology_ref") or {}).get("id")
            print(f"  [{mark}] {entry['pack_id']:<24} morphology={ref} file={entry['file']}")
            for error in entry["errors"]:
                print(f"          - {error}")
            for warning in entry["warnings"]:
                print(f"          ~ {warning}")

    print(
        f"Pack 校验：{catalog['valid_count']}/{catalog['count']} 通过"
        + (f"，重复 pack_id：{catalog['duplicates']}" if catalog["duplicates"] else "")
    )
    if catalog["invalid_count"] or catalog["duplicates"]:
        print("提示：改过契约后请重跑 `python tools/generate_packs.py` 刷新引用哈希。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
