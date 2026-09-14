#!/usr/bin/env python
"""E7 CLI：Skill 包（纯 JSON）的导出 / 校验 / 导入。

用法：

    python tools/skill_pack.py export velocity_base -o velocity_base.skillpack.json
    python tools/skill_pack.py export zex-w-rough -o zex-w-rough.skillpack.json   # 自动带上基座
    python tools/skill_pack.py verify zex-w-rough.skillpack.json
    python tools/skill_pack.py import zex-w-rough.skillpack.json                  # 预演（不落盘）
    python tools/skill_pack.py import zex-w-rough.skillpack.json --write          # 真写入

退出码：0 通过 / 1 有问题（`verify`、`import` 均如此）——可直接进门禁。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import skill_pack  # noqa: E402
from backend.skill_registry import SKILLS_DIR, SkillRegistryError  # noqa: E402


def _cmd_export(args: argparse.Namespace) -> int:
    try:
        pack = skill_pack.export_pack(args.recipe_id, skills_dir=args.skills_dir)
    except SkillRegistryError as exc:
        print(f"✗ 导出失败：{exc}")
        return 1
    target = Path(args.output) if args.output else Path(f"{args.recipe_id}.skillpack.json")
    target.write_text(
        json.dumps(pack, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    roles = "、".join(f"{r['recipe_id']}({r.get('role') or '—'})" for r in pack["recipes"])
    print(f"✓ 已导出 {target}：{len(pack['recipes'])} 个配方（{roles}） digest={pack['digest'][:12]}…")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    pack = json.loads(Path(args.path).read_text(encoding="utf-8-sig"))
    report = skill_pack.verify_pack(pack)
    if report["ok"]:
        print(f"✓ 包自洽：{', '.join(report['recipes'])}")
        return 0
    print(f"✗ 包有 {len(report['problems'])} 处问题：")
    for problem in report["problems"]:
        print(f"   - {problem}")
    return 1


def _cmd_import(args: argparse.Namespace) -> int:
    pack = json.loads(Path(args.path).read_text(encoding="utf-8-sig"))
    result = skill_pack.import_pack(
        pack, skills_dir=args.skills_dir, overwrite=args.overwrite, write=args.write,
    )
    verb = "已写入" if args.write else "预演（未落盘）"
    if result["ok"]:
        print(f"✓ 导入{verb}：{', '.join(result['planned']) or '（无内容）'}"
              f"{'；清单已更新' if result.get('index_updated') else ''}")
        return 0
    print(f"✗ 导入被拒（{verb}，共 {len(result['problems'])} 处问题）：")
    for problem in result["problems"]:
        print(f"   - {problem}")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Skill 包（纯 JSON）导出 / 校验 / 导入")
    parser.add_argument("--skills-dir", default=str(SKILLS_DIR),
                        help="技能注册表目录（默认 registry/skills）")
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser("export", help="导出技能为自包含 JSON 包")
    export.add_argument("recipe_id")
    export.add_argument("-o", "--output")
    export.set_defaults(func=_cmd_export)

    verify = sub.add_parser("verify", help="校验包（含摘要与闭环）")
    verify.add_argument("path")
    verify.set_defaults(func=_cmd_verify)

    imp = sub.add_parser("import", help="导入包（默认预演）")
    imp.add_argument("path")
    imp.add_argument("--write", action="store_true", help="真写入（默认只预演）")
    imp.add_argument("--overwrite", action="store_true", help="允许覆盖同名但内容不同的技能")
    imp.set_defaults(func=_cmd_import)

    args = parser.parse_args(argv)
    args.skills_dir = Path(args.skills_dir)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
