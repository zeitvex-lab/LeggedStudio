# -*- coding: utf-8 -*-
"""对比 go2 backflip/jump 的 motion 契约与 csv 存在性。"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
cfg = json.loads((ROOT / "assets/robots/unitree_go2/simulation/config.json").read_text(encoding="utf-8-sig"))
for p in cfg.get("policies", []):
    if p.get("id") in ("go2-backflip-69", "go2-jump-69"):
        c = p.get("contract") or {}
        mp = c.get("motion_params") or {}
        csv_path = ROOT / "assets/robots/unitree_go2" / str(mp.get("motion_csv") or "")
        print(f"== {p['id']} ==")
        print(f"  motion_csv: {mp.get('motion_csv')}  exists={csv_path.exists()}")
        print(f"  motion_joint_mapping: {c.get('motion_joint_mapping')}")
        print(f"  motion keys: {sorted(mp.keys())}")
        print(f"  contract keys: {sorted(c.keys())}")
        print()
