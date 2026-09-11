# -*- coding: utf-8 -*-
"""三条 go2 策略的 observation_kind / 维度 / 文件指纹对比。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GO2 = ROOT / "assets/robots/unitree_go2"
cfg = json.loads((GO2 / "simulation/config.json").read_text(encoding="utf-8-sig"))
for p in cfg.get("policies", []):
    c = p.get("contract") or {}
    path = GO2 / str(p.get("path") or "")
    digest = hashlib.md5(path.read_bytes()).hexdigest()[:12] if path.exists() else "MISSING"
    print(f"{p.get('id'):22s} kind={c.get('observation_kind')!s:20s} obs={c.get('obs_dim')} act={c.get('action_dim')} "
          f"hist={c.get('history_len')} motion={bool((c.get('motion_params') or {}).get('motion_csv'))} "
          f"size={path.stat().st_size if path.exists() else 0} md5={digest}")
