#!/usr/bin/env python3
"""拉取外置参考资源：把 LeggedStudio-Resources 的项目快照同步到 00_resources/。

主仓只保留 `00_resources/README.md`、`_index.json`、`_LICENSES.md`、`_SPEC.md`；
项目实体在独立仓，按需拉取，避免主仓随资源膨胀。

用法：
    python tools/fetch_resources.py --dry-run
    python tools/fetch_resources.py
    python tools/fetch_resources.py --project legbot_lab_PPO,GO2_backflip
    python tools/fetch_resources.py --force
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPO = "https://github.com/zeitvex-lab/LeggedStudio-Resources.git"
DEFAULT_DEST = ROOT / "00_resources"
CACHE = ROOT / ".cache" / "resources-repo"
META = {"_SPEC.md", "README.md", "_index.json", "_LICENSES.md"}


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def _update_cache(repo: str, cache: Path, dry: bool) -> None:
    if dry:
        print(f"[dry-run] cache: {cache} (repo {repo})")
        return
    if (cache / ".git").is_dir():
        _run(["git", "-C", str(cache), "fetch", "--depth", "1", "origin"])
        _run(["git", "-C", str(cache), "reset", "--hard", "origin/main"])
    else:
        cache.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", "--depth", "1", repo, str(cache)])


def _project_names(cache: Path) -> list[str]:
    return sorted(
        path.name
        for path in cache.iterdir()
        if path.is_dir() and path.name != ".git"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="拉取外置参考资源到 00_resources/")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="资源仓 URL")
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST, help="目标 00_resources 目录")
    parser.add_argument("--project", default="", help="只拉取指定项目（逗号分隔）")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的项目目录")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不落盘")
    args = parser.parse_args(argv)

    requested = [p.strip() for p in args.project.split(",") if p.strip()]
    _update_cache(args.repo, CACHE, args.dry_run)

    if args.dry_run:
        print(f"[dry-run] dest: {args.dest}")
        print(f"[dry-run] projects: {requested or '<all>'}")
        return 0

    available = set(_project_names(CACHE))
    if requested:
        missing = [p for p in requested if p not in available]
        if missing:
            print(f"[FAIL] 资源仓中不存在：{missing}", file=sys.stderr)
            return 1
        names = requested
    else:
        names = sorted(available)

    args.dest.mkdir(parents=True, exist_ok=True)
    copied = 0
    for name in names:
        src = CACHE / name
        dst = args.dest / name
        if dst.exists() and not args.force:
            print(f"[skip] {name}（已存在；用 --force 覆盖）")
            continue
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        copied += 1

    for meta in META:
        src = CACHE / meta
        dst = args.dest / meta
        if src.is_file() and not dst.exists():
            shutil.copy2(src, dst)

    print(f"[OK] 拉取 {copied} 个项目 → {args.dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
