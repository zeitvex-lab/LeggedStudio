#!/usr/bin/env python3
"""Upload and publish built Microduck bundles through the Miniverse CLI."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]


def miniverse(*args):
    result = subprocess.run(["miniverse", *args, "--json"], check=True, text=True, capture_output=True)
    value = json.loads(result.stdout)
    print(json.dumps(value, indent=2))
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("bundles", nargs="*", type=Path, help="Defaults to every dist/*.dhsim bundle")
    parser.add_argument("--upload-only", action="store_true", help="Create revisions without publishing them")
    args = parser.parse_args()
    bundles = args.bundles or sorted((ROOT / "dist").glob("*.dhsim"))
    if not bundles:
        raise SystemExit("no bundles found; run uv run scripts/build.py first")
    miniverse("auth", "status")
    for bundle in bundles:
        uploaded = miniverse("bundle", "upload", str(bundle.resolve()))
        bundle_id = uploaded.get("bundleId")
        revision_id = uploaded.get("revisionId")
        if not bundle_id or not revision_id:
            raise SystemExit(f"upload response for {bundle} did not contain bundleId and revisionId")
        if not args.upload_only:
            miniverse("bundle", "publish", f"{bundle_id}@{revision_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
