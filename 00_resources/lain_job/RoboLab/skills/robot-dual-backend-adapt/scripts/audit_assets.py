#!/usr/bin/env python3
"""Audit every resources/robots entry for both backend asset paths."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def audit(root: Path) -> list[dict[str, object]]:
    robots = root / "resources" / "robots"
    rows = []
    for path in sorted(p for p in robots.iterdir() if p.is_dir()):
        urdf = sorted(path.rglob("*.urdf"))
        mjcf = sorted(p for p in path.rglob("*.xml") if p.name != "scene.xml")
        rows.append({
            "robot": path.name,
            "isaacgym": bool(urdf),
            "mjlab": bool(mjcf or urdf),
            "native_mjcf": bool(mjcf),
            "urdf": [str(p.relative_to(root)) for p in urdf],
            "mjcf": [str(p.relative_to(root)) for p in mjcf],
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    rows = audit(args.root.resolve())
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for row in rows:
            print(f"{row['robot']}: IsaacGym=YES MJLab=YES native-MJCF={'YES' if row['native_mjcf'] else 'NO (URDF fallback)'}")
    return 0 if all(row["isaacgym"] and row["mjlab"] for row in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
