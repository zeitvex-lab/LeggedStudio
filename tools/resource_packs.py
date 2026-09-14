#!/usr/bin/env python
"""E5 CLI：资源包列出 / 校验 / 挂载 / 卸载（离线可用，不依赖 GPU）。

用法：

    python tools/resource_packs.py list
    python tools/resource_packs.py check                      # 全部包自检（引用/宽度）
    python tools/resource_packs.py check dreamwaq_blind
    python tools/resource_packs.py mount dreamwaq_blind --config c.json -o out.json
    python tools/resource_packs.py mount dreamwaq_blind --obs-dim 57      # 顺带校验宽度
    python tools/resource_packs.py unmount dreamwaq_blind --config out.json --provenance p.json

退出码：0 通过 / 1 有问题。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import resource_packs as rp  # noqa: E402


def _cmd_list(_: argparse.Namespace) -> int:
    summaries = rp.list_packs()
    print(f"已注册资源包 {len(summaries)} 个：")
    for item in summaries:
        if item.get("error"):
            print(f"  ✗ {item['pack_id']}：{item['error']}")
            continue
        counts = item["counts"]
        print(f"  · {item['pack_id']:<18} {item.get('label') or ''}")
        print(f"      用途：{item.get('purpose') or '—'}")
        print(f"      挂载：观测项 {counts['observations']} / 奖励项 {counts['reward_terms']} / "
              f"provider {counts['providers']}"
              f"；观测宽度影响 {item.get('obs_dim_delta') or 0}")
        if item.get("requires"):
            print(f"      依赖：{'、'.join(item['requires'])}")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    ids = [args.pack_id] if args.pack_id else [item["pack_id"] for item in rp.list_packs()
                                              if not item.get("error")]
    failures = 0
    for pack_id in ids:
        try:
            pack = rp.load_pack(pack_id)
        except rp.ResourcePackError as exc:
            print(f"✗ {pack_id}：{exc}")
            failures += 1
            continue
        report = rp.validate_pack(pack)
        if report["ok"]:
            print(f"✓ {pack_id}")
        else:
            failures += 1
            print(f"✗ {pack_id}：")
            for problem in report["problems"]:
                print(f"    - {problem}")
    print(f"\n共 {len(ids)} 个包，{failures} 个有问题")
    return 1 if failures else 0


def _read_config(path: str | None) -> dict:
    if not path:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _cmd_mount(args: argparse.Namespace) -> int:
    result = rp.mount(
        _read_config(args.config), args.pack_ids, obs_dim=args.obs_dim,
    )
    if not result["ok"]:
        print(f"✗ 挂载被拒（{len(result['problems'])} 处问题，**一个都没挂**）：")
        for problem in result["problems"]:
            print(f"   - {problem}")
        return 1
    print(f"✓ 已挂载：{'、'.join(result['mounted']) or '（无变化）'}")
    if result["obs_dim_total"] is not None:
        print(f"  观测宽度：{args.obs_dim} → {result['obs_dim_total']}"
              f"（+{result['obs_dim_total'] - args.obs_dim}；与包声明的一致性已在 check 里校验）")
    if args.output:
        Path(args.output).write_text(
            json.dumps(result["config"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        Path(str(args.output) + ".provenance.json").write_text(
            json.dumps(result["provenance"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        print(f"  已写 {args.output}（附 .provenance.json，卸载要用）")
    return 0


def _cmd_unmount(args: argparse.Namespace) -> int:
    provenance = _read_config(args.provenance) if args.provenance else {}
    result = rp.unmount(_read_config(args.config), args.pack_id, provenance=provenance)
    if not result["ok"]:
        print(f"✗ 卸载被拒：{result['problems']}")
        return 1
    print(f"✓ 已卸载 {args.pack_id}，回退：{'、'.join(result['removed']) or '（无）'}")
    if args.output:
        Path(args.output).write_text(
            json.dumps(result["config"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="资源包（可挂载/可卸载）")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="列出已注册资源包").set_defaults(func=_cmd_list)

    check = sub.add_parser("check", help="校验包（引用存在性 / 观测宽度 / 依赖）")
    check.add_argument("pack_id", nargs="?")
    check.set_defaults(func=_cmd_check)

    mount = sub.add_parser("mount", help="挂载包到配置")
    mount.add_argument("pack_ids", nargs="+")
    mount.add_argument("--config", help="起始配置 JSON（缺省为空配置）")
    mount.add_argument("--obs-dim", type=int, help="契约声明的观测宽度（用于校验）")
    mount.add_argument("-o", "--output", help="写出挂载后的配置（同时写 .provenance.json）")
    mount.set_defaults(func=_cmd_mount)

    unmount = sub.add_parser("unmount", help="卸载包（需 provenance）")
    unmount.add_argument("pack_id")
    unmount.add_argument("--config", required=True)
    unmount.add_argument("--provenance", help="挂载时写出的 provenance JSON")
    unmount.add_argument("-o", "--output")
    unmount.set_defaults(func=_cmd_unmount)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
