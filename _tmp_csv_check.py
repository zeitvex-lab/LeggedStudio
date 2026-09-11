# -*- coding: utf-8 -*-
"""对比 backflip/jump motion csv 行数与 time 裁剪窗口。"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GO2 = ROOT / "assets/robots/unitree_go2"
cfg = json.loads((GO2 / "simulation/config.json").read_text(encoding="utf-8-sig"))
for p in cfg.get("policies", []):
    if p.get("id") in ("go2-backflip-69", "go2-jump-69"):
        mp = (p.get("contract") or {}).get("motion_params") or {}
        csv = GO2 / str(mp.get("motion_csv"))
        text = csv.read_text(encoding="utf-8-sig", errors="ignore").strip()
        lines = [l for l in text.splitlines() if l.strip()]
        fps = float(mp.get("fps", 50))
        ts = float(mp.get("time_start", 0))
        te = float(mp.get("time_end", 0))
        rows = len(lines)
        start = round(ts * fps)
        end = min(rows, round(te * fps) or rows)
        clipped = max(0, end - start)
        print(f"{p['id']}: rows={rows} fps={fps} t=[{ts},{te}] -> slice[{start}:{end}] = {clipped} 帧")
        if lines:
            print(f"  首行前 8 列: {lines[0].split(',')[:8]}")
            print(f"  列数: {len(lines[0].split(','))}")
