# -*- coding: utf-8 -*-
"""严格审计：每条演示策略 ↔ 包内对应训练任务（token 级取证）。"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ROBOTS = ROOT / "assets" / "robots"

# 政策 id/label → 训练侧 token 的映射线索（多给同义词，命中任一即算对应）
TOKENS = {
    "walking": ["velocity", "velstand", "walk"],
    "stand": ["velstand", "stand"],
    "sitstand": ["sitstand", "sit_stand"],
    "roulade": ["roulade"],
    "roller": ["roller"],
    "roller-crouch": ["roller", "crouch"],
    "ground-pick": ["groundpick", "ground_pick", "pick"],
    "ball-kick-left": ["ballkick", "ball_kick", "kick"],
    "ball-kick-right": ["ballkick", "ball_kick", "kick"],
    "model-6800": ["rough"],
    "model-84": ["wall", "rough", "rc_wall"],
    "model-9600": ["rough"],
    "model-rough": ["rough"],
    "unitree-velocity": ["velocity"],
    "locomotion": ["locomotion", "velocity", "mjswan"],
    "dance-102": ["dance", "tracking", "motion"],
    "dance-gangnam-style": ["dance", "gangnam", "tracking", "motion"],
    "dance-subject2": ["dance", "subject", "tracking", "motion"],
    "unitree-velocity-legs": ["velocity"],
    "velocity": ["velocity"],
    "robotlab-velocity-57": ["velocity", "robot_lab"],
    "go2-backflip-69": ["backflip", "back_flip"],
    "go2-jump-69": ["jump"],
    "go2-baseline-164k": ["moe", "cts"],
    "deeprobotics_lite3-velocity-benchmark": ["velocity"],
    "lite3-official-sdk-45": ["velocity"],
    "m20-velocity-57": ["velocity", "dreamwaq"],
    "unitree_b2-velocity-benchmark": ["velocity"],
}

results: dict[str, list[tuple[str, str]]] = {}
for pkg in sorted(p for p in ROBOTS.iterdir() if p.is_dir()):
    cfg_path = pkg / "simulation" / "config.json"
    if not cfg_path.exists():
        continue
    cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
    policies = [p for p in (cfg.get("policies") or []) if isinstance(p, dict) and p.get("path")]
    if not policies:
        continue
    src = pkg / "training" / "source"
    corpus = ""
    task_ids: set[str] = set()
    for f in src.rglob("*.py") if src.exists() else []:
        text = f.read_text(encoding="utf-8", errors="ignore")
        corpus += text
        for m in re.finditer(r'task_id\s*=\s*"([^"]+)"', text):
            task_ids.add(m.group(1))
    corpus_l = corpus.lower()
    rows = []
    for p in policies:
        pid = str(p.get("id") or Path(str(p["path"])).stem)
        tokens = TOKENS.get(pid, [pid.replace("-", "_").lower()])
        hit = [t for t in tokens if t.lower() in corpus_l]
        rows.append((pid, "✓ " + ",".join(hit[:3]) if hit else "✗ 无对应任务", sorted(task_ids)))
    results[pkg.name] = rows

for robot, rows in results.items():
    print(f"\n=== {robot} ===")
    for pid, verdict, tasks in rows:
        print(f"  {pid:32s} {verdict}   (注册任务: {tasks if tasks else '-'})")
