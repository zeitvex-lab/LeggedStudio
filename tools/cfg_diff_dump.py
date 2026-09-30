#!/usr/bin/env python3
"""装配机制对拍的**序列化端**：把一份 ManagerBasedRlEnvCfg 走成 JSON 可比树。

背景（2026-09-30，legs-only 学步五组对照后）：数值层逐项对齐、五组参数杠杆全判
"pass-但-零位移"，而上游同任务产物真在走 ⇒ 差异只剩**装配机制层**。逐行读代码
易漏，构建后对象**逐属性 diff** 更可靠——本脚本产出可比的那一半（另一半是 diff）。

用法（两个进程各跑一次，import 隔离——上游捆绑 mjlab 与本仓 venv 的 mjlab 不能同进程）：
    <venv> python tools/cfg_diff_dump.py --mode ours --variant flat_legs_only --out a.json
    <venv> python tools/cfg_diff_dump.py --mode upstream --variant flat_legs_only --out b.json
    diff a.json b.json

序列化规则：dataclass → {"__type__": 类名, 字段...}；dict/list/tuple → 容器；
可调用/类 → 限定名；其余（torch/np/对象）→ repr 截断。**只比结构与数值，不比身份**。
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _walk(obj, depth=0):
    if depth > 14:
        return "<depth-limit>"
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        out = {"__type__": type(obj).__name__}
        for f in dataclasses.fields(obj):
            if f.name.startswith("_"):
                continue
            out[f.name] = _walk(getattr(obj, f.name), depth + 1)
        return out
    if isinstance(obj, dict):
        return {"__dict__": {str(k): _walk(v, depth + 1) for k, v in obj.items()}}
    if isinstance(obj, (list, tuple)):
        return {"__list__": [_walk(v, depth + 1) for v in obj]}
    if isinstance(obj, type):
        return f"<class {obj.__module__}.{obj.__qualname__}>"
    if callable(obj):
        return f"<func {getattr(obj, '__module__', '?')}.{getattr(obj, '__qualname__', repr(obj))}>"
    return repr(obj)[:200]


def _dump_ours(variant: str) -> dict:
    sys.path.insert(0, str(ROOT / "assets" / "robots" / "unitree_go2w" / "training" / "source"))
    import go2w_velocity as g

    fn = {
        "rough": g.unitree_go2w_rough_env_cfg,
        "flat": g.unitree_go2w_flat_env_cfg,
        "flat_legs_only": g.unitree_go2w_flat_legs_only_env_cfg,
        "flat_legs_only_omni": g.unitree_go2w_flat_legs_only_omni_env_cfg,
    }[variant]
    return _walk(fn(play=False))


def _dump_upstream(variant: str) -> dict:
    sys.path.insert(0, str(ROOT / "00_resources" / "unitree_rl_mjlab_go2w"))
    from mjlab.tasks.robots.unitree_go2w.velocity import env_cfgs

    fn = {
        "rough": env_cfgs.unitree_go2w_rough_env_cfg,
        "flat": env_cfgs.unitree_go2w_flat_env_cfg,
        "flat_legs_only": env_cfgs.unitree_go2w_flat_legs_only_env_cfg,
        "flat_legs_only_omni": env_cfgs.unitree_go2w_flat_legs_only_omni_env_cfg,
    }[variant]
    return _walk(fn(play=False))


def main() -> int:
    parser = argparse.ArgumentParser(description="cfg 装配对拍·序列化端")
    parser.add_argument("--mode", choices=("ours", "upstream"), required=True)
    parser.add_argument("--variant", default="flat_legs_only")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    import os
    os.environ.setdefault("MUJOCO_GL", "disabled")

    tree = _dump_ours(args.variant) if args.mode == "ours" else _dump_upstream(args.variant)
    Path(args.out).write_text(
        json.dumps(tree, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"[dump] {args.mode}/{args.variant} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
