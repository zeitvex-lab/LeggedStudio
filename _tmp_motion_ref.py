# -*- coding: utf-8 -*-
"""打印参考运动 CSV 的根高度/四元数/关节角度包络——判断参考动作是否为真翻转/真跳跃。"""
from __future__ import annotations

import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
POL = ROOT / "assets/robots/unitree_go2/simulation/policies"

for name, (ts, te) in (("backflip_motion.csv", (0.0, 1.6)), ("jump_motion.csv", (0.5, 2.6))):
    rows = [[float(v) for v in ln.split(",")] for ln in (POL / name).read_text().splitlines() if ln.strip()]
    fps = 50.0
    s, e = round(ts * fps), min(len(rows), round(te * fps))
    clip = rows[s:e]
    zs = [r[2] for r in clip]
    print(f"== {name}  rows={len(rows)} clip={len(clip)} ==")
    print(f"  root z: min={min(zs):.3f} max={max(zs):.3f} first={zs[0]:.3f} last={zs[-1]:.3f}")
    # 累计旋转角（quat xyzw -> 相对 identity 的旋转角）
    angles = []
    for r in clip:
        x, y, z, w = r[3], r[4], r[5], r[6]
        n = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
        w = max(-1.0, min(1.0, w / n))
        angles.append(math.degrees(2 * math.acos(w)))
    print(f"  |rotation| vs identity: max={max(angles):.1f}deg  at frame {angles.index(max(angles))}")
    print("  frame     :  z      rot(deg)   joint0     joint1     joint2")
    for i in range(0, len(clip), max(1, len(clip) // 8)):
        r = clip[i]
        print(f"  {i:5d}     : {r[2]:6.3f}  {angles[i]:7.1f}   {r[7]:8.3f}  {r[8]:8.3f}  {r[9]:8.3f}")
    print()
