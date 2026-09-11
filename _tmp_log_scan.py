# -*- coding: utf-8 -*-
"""扫描最近一次 verify 运行：场景编译 / motion csv / 策略加载时序。"""
from __future__ import annotations

import re
from pathlib import Path

LOG = Path(r"C:\Users\31560\Documents\00_open\.playwright-cli\console-2026-09-11T03-03-13-027Z.log")
lines = LOG.read_text(encoding="utf-8", errors="ignore").splitlines()
print(f"total lines: {len(lines)}")

# 只看最后一次 verify（含 8 次 fastForward 的那段）：从最后一个 index 往前找
rx = re.compile(
    r"✔ MuJoCo scene|MuJoCo 错误|loadMjModel|motion csv|browser-package|go2-jump-69|go2-backflip-69"
    r"|ONNX policy|loadMujocoAssets|Error opening|ParseXML|✘|失败|frame error #\d+ TypeError",
    re.I,
)
hits = [(i, ln.strip()) for i, ln in enumerate(lines) if rx.search(ln)]
print(f"matched: {len(hits)}")
start = max(0, len(hits) - 90)
seen = set()
for i, ln in hits[start:]:
    key = re.sub(r"#\d+", "#N", ln)[:250]
    if key in seen:
        continue
    seen.add(key)
    print(f"L{i}: {ln[:250]}")
