#!/usr/bin/env python
"""B10 收尾门禁：策略声明是否已从"裸路径"切到"引用 + hash"。

判据（对齐 B10 原文后半句「契约只留引用 + hash」）：

1. 每条声明都带 ``artifact_id``（而非只写 ``path`` / ``url``）；
2. 该 ``artifact_id`` 能在 ``policies/index.json`` 里找到；
3. 声明/索引里的 hash 与**文件实测** hash 一致。

用法::

    python tools/migrate_policy_refs.py            # 人读报告
    python tools/migrate_policy_refs.py --json     # 机读（CI 用）
    python tools/migrate_policy_refs.py --quiet    # 只给退出码

退出码：0 = 已全部迁移且一致；1 = 仍有裸路径声明或 hash 不一致（**门禁语义：未迁移即不过**）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import policy_artifacts as pa  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="策略声明「引用 + hash」迁移门禁")
    parser.add_argument("--json", action="store_true", help="输出 JSON（供 CI/工具消费）")
    parser.add_argument("--quiet", action="store_true", help="只输出结论与退出码")
    parser.add_argument("--allow-legacy", action="store_true",
                        help="迁移过渡期：裸路径只警告不判失败（hash 不一致仍判失败）")
    parser.add_argument("--write", action="store_true",
                        help="**删除**声明里指向 onnx 的裸 path/url（改动 14 份包配置；默认只报告）")
    args = parser.parse_args(argv)

    if args.write:
        stripped = pa.strip_raw_paths(write=True)
        print(f"删除裸路径：{stripped['removed_count']} 处 / {len(stripped['files'])} 份包配置")
        for problem in stripped["problems"]:
            print(f"  ✗ {problem}")
        if not stripped["ok"]:
            return 1

    report = pa.reference_gaps()
    legacy = report["legacy_path_declarations"]
    failing = bool(report["problems"] or (legacy and not args.allow_legacy))

    if args.json:
        print(json.dumps({**report, "ok": not failing, "allow_legacy": args.allow_legacy},
                         ensure_ascii=False, indent=2))
        return 1 if failing else 0

    if not args.quiet:
        print(f"策略声明 {report['declared']} 条 / 仍写裸 path·url 的 {len(legacy)} 条")
        if legacy:
            preview = "、".join(legacy[:6]) + ("…" if len(legacy) > 6 else "")
            print(f"  待迁移：{preview}")
        for problem in report["problems"]:
            print(f"  ✗ {problem}")

    if report["problems"]:
        print(f"✗ 引用/hash 对账失败 {len(report['problems'])} 处")
    elif legacy and not args.allow_legacy:
        print(f"✗ {len(legacy)} 条声明仍是裸路径（未切到 artifact_id + hash）")
    elif legacy:
        # 过渡期：形式未切但 hash 已核对一致 —— 结论必须如实，不能打印"已全部是引用"
        print(f"⚠ {len(legacy)} 条声明仍是裸路径（--allow-legacy：过渡期不判失败，hash 对账已通过）")
    else:
        print("✓ 策略声明已全部是「引用 + hash」")
    return 1 if failing else 0


if __name__ == "__main__":
    raise SystemExit(main())
