#!/usr/bin/env python3
"""dump_effective_recipe.py — 机型档案的**当前**装配快照（recipe_parity 的我方真值源）。

在 adapter venv 里跑：按档案 JSON 的 `entrypoints.env`（与 native_worker 同一工厂入口）
装配 env cfg，把奖励/命令域/动作缩放/终止 dump 成 effective-config 同形 JSON——
**不实例化 env、不占 GPU**，开训前就能对拍参考真值表。

    adapters/mjlab/.venv/Scripts/python.exe tools/dump_effective_recipe.py \
        --robot unitree_go2w --profile go2w-flat-legs-only \
        --out workspace/parity_snapshot.json
    python tools/recipe_parity.py --recipe <参考真值表id> --effective-config workspace/parity_snapshot.json

退出码：0 = 落盘；2 = 档案/entrypoint 缺失（fail-closed，不猜）。
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _dump(obj):
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _dump(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _dump(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_dump(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return repr(obj)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--robot", required=True)
    ap.add_argument("--profile", required=True, help="档案 id（training/profiles 下的文件名去 .json）")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    pkg = ROOT / "assets" / "robots" / args.robot
    prof_path = pkg / "training" / "profiles" / f"{args.profile}.json"
    if not prof_path.is_file():
        print(f"[env-missing] 档案不存在：{prof_path}", file=sys.stderr)
        return 2
    prof = json.loads(prof_path.read_text(encoding="utf-8-sig"))
    entrypoint = str(((prof.get("entrypoints") or {}).get("env")) or "")
    if ":" not in entrypoint:
        print(f"[env-missing] 档案缺 entrypoints.env：{prof_path}", file=sys.stderr)
        return 2
    module_name, factory_name = entrypoint.split(":", 1)

    source_root = pkg / str(prof.get("source_root") or "training/source")
    for p in (str(source_root), str(pkg), str(ROOT)):
        if p not in sys.path:
            sys.path.insert(0, p)

    module = importlib.import_module(module_name)
    cfg = getattr(module, factory_name)(play=True)

    snap = {"environment": {
        "rewards": {k: {"weight": v.weight, "params": _dump(v.params)} for k, v in cfg.rewards.items()},
        "commands": _dump(cfg.commands),
        "actions": _dump(cfg.actions),
        "terminations": _dump(cfg.terminations),
    }}
    Path(args.out).write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"dumped {args.robot}/{args.profile} ({entrypoint}) -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
