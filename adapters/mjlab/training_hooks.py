"""训练钩子位（Phase 3 插件化，2026-10-03）——训练循环的**事件切点**。

## 为什么存在

横切能力（训练期趋势探针/奖励熔断/实时评测）此前无处安放：只能改 native_worker
主循环或训后手工跑。钩子位把它们变成**数据可挂载的插件消费者**——档案声明
``hooks``，worker 在切点位调用，业务实现在各工具里（内核不 import 它们）。

## 声明（profile JSON / 训练 config）

```json
"hooks": {
  "on_checkpoint": [{"call": "tools.trend_probe_hook:run", "config": {"trend_ratio": 0.2}}]
}
```

## 切点与语义

* ``on_checkpoint``：每次 save checkpoint 后（同步；异常只打印不中断训练——
  探针失败不该弄死一个 4 小时的训练）。接收 ``(ctx: dict)``，ctx 含
  ``{run_dir, checkpoint_path, iteration, effective_config, report}``。
* 内置守卫：同一钩子单次触发最长 30 分钟（挂死探针不许吃掉 GPU 时长预算）。
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

HOOK_TIMEOUT_S = 1800.0
VALID_POINTS = ("on_checkpoint",)


def load_hooks(config: Mapping[str, Any], point: str) -> list[dict[str, Any]]:
    """config/profile 的 ``hooks[point]`` → 钩子清单（形状不对 = 空 + 原因，不炸训练）。"""
    if point not in VALID_POINTS:
        return []
    raw = config.get("hooks")
    if not isinstance(raw, Mapping):
        return []
    entries = raw.get(point)
    if entries is None:
        return []
    if not isinstance(entries, list):
        print(f"[hooks] {point} 形状不对（须数组），忽略: {type(entries).__name__}")
        return []
    out = []
    for item in entries:
        if isinstance(item, Mapping) and str(item.get("call") or ""):
            out.append({"call": str(item["call"]), "config": item.get("config") or {}})
        else:
            print(f"[hooks] {point} 条目缺 call，忽略: {item!r}"[:200])
    return out


def _resolve(call: str):
    import importlib

    module_name, _, attr = call.partition(":")
    if not module_name or not attr:
        raise ValueError(f"hook.call 须 `module:attr`，得到 {call!r}")
    return getattr(importlib.import_module(module_name), attr)


def run_hooks(point: str, hooks: list[dict[str, Any]], ctx: Mapping[str, Any]) -> None:
    """在切点位同步执行钩子（fail-soft：单钩异常/超时只打印，训练继续）。"""
    for hook in hooks:
        t0 = time.monotonic()
        try:
            fn = _resolve(hook["call"])
            fn(dict(ctx), **(hook.get("config") or {}))
            print(f"[hooks] {point} {hook['call']} ok ({time.monotonic() - t0:.1f}s)")
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - t0
            print(f"[hooks] {point} {hook['call']} FAILED ({elapsed:.1f}s): "
                  f"{type(exc).__name__}: {str(exc)[:200]}")
