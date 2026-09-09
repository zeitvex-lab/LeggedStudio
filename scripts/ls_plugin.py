"""ls_plugin CLI（T6.1/T6.3，批次 6 / M7）：插件包 校验 / 脚手架 / 目录。

用法：
  uv run python scripts/ls_plugin.py validate <package_root> [ ...]
  uv run python scripts/ls_plugin.py scaffold  <target_dir> <package_id>
  uv run python scripts/ls_plugin.py catalog   <packages_dir> [--out catalog.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 统一自举：见 contracts/path_bootstrap.py。
if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from contracts.path_bootstrap import bootstrap_root

ROOT = bootstrap_root()

from backend.plugin_protocol import generate_catalog, match_profiles, scaffold_package, validate_package  # noqa: E402


def cmd_validate(args: argparse.Namespace) -> int:
    failed = 0
    for package_root in args.package_root:
        report = validate_package(Path(package_root))
        mark = "OK " if report["ok"] else "!! "
        print(f"[{mark}] {report.get('package_id') or package_root}")
        for error in report["errors"]:
            print(f"    ✗ {error}")
        for warning in report["warnings"]:
            print(f"    ⚠ {warning}")
        failed += 0 if report["ok"] else 1
    print(f"\n{len(args.package_root) - failed} passed, {failed} failed")
    return 1 if failed else 0


def cmd_scaffold(args: argparse.Namespace) -> int:
    path = scaffold_package(Path(args.target_dir), args.package_id)
    report = validate_package(path)
    print(f"scaffold created: {path} (validate: {'ok' if report['ok'] else report['errors']})")
    return 0 if report["ok"] else 1


def cmd_catalog(args: argparse.Namespace) -> int:
    packages_dir = Path(args.packages_dir)
    roots = [item for item in sorted(packages_dir.iterdir()) if item.is_dir()] if packages_dir.exists() else []
    catalog = generate_catalog(roots)
    out = Path(args.out) if args.out else packages_dir / "catalog.json"
    out.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    valid = sum(1 for item in catalog["packages"] if item["valid"])
    print(f"catalog: {out} ({valid}/{len(catalog['packages'])} valid)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="校验插件包（可多个）")
    p_validate.add_argument("package_root", nargs="+")

    p_scaffold = sub.add_parser("scaffold", help="生成最小插件包骨架")
    p_scaffold.add_argument("target_dir")
    p_scaffold.add_argument("package_id")

    p_catalog = sub.add_parser("catalog", help="生成 catalog.json")
    p_catalog.add_argument("packages_dir")
    p_catalog.add_argument("--out", default=None)

    args = parser.parse_args()
    if args.command == "validate":
        return cmd_validate(args)
    if args.command == "scaffold":
        return cmd_scaffold(args)
    return cmd_catalog(args)


if __name__ == "__main__":
    sys.exit(main())
