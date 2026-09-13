"""运行时档位注册表（``registry/*.json``）的统一读取入口。

H8/H9/H10 三条任务共享同一个模式：**数字是数据，不是代码**。相机档位
（``registry/cameras.json``）、运动指令档位（``registry/motion_commands.json``）、
到达判据（``registry/arrival_criteria.json``）都放在 ``registry/`` 下，由本模块统一
读取、缓存与校验，调用方（后端路由 / 自检 / 工具）只认这一个入口。

约定：

* 每份注册表必须带 ``schema`` 字段（形如 ``xxx-1.0``），缺字段即视为损坏；
* 注册表缺失时**明确报错**（带期望路径），不静默回退到硬编码默认值——
  「悄悄用旧数字」正是 H10 里两套到达阈值并存的原因；
* 读取结果按 mtime 失效，开发期改 JSON 立即生效，无需重启。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_DIR = ROOT / "registry"

#: name → (文件名, 期望 schema)
REGISTRY_FILES: dict[str, tuple[str, str]] = {
    "cameras": ("cameras.json", "camera-profile-1.0"),
    "motion_commands": ("motion_commands.json", "motion-command-profile-1.0"),
    "arrival_criteria": ("arrival_criteria.json", "arrival-criteria-1.0"),
}

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


class RegistryError(RuntimeError):
    """注册表缺失或损坏（不静默回退）。"""


def registry_path(name: str) -> Path:
    """注册表文件路径（不检查存在性，供报错信息与工具打印使用）。"""
    if name not in REGISTRY_FILES:
        raise RegistryError(f"未知注册表 {name!r}；已登记：{', '.join(sorted(REGISTRY_FILES))}")
    return REGISTRY_DIR / REGISTRY_FILES[name][0]


def load_registry(name: str) -> dict[str, Any]:
    """读取注册表（按 mtime 缓存）。缺失/损坏抛 :class:`RegistryError`。"""
    path = registry_path(name)
    try:
        mtime = path.stat().st_mtime
    except OSError as exc:
        raise RegistryError(
            f"注册表缺失：{path}（期望 schema={REGISTRY_FILES[name][1]}）。"
            "请从仓库取回该文件，不要用代码里的旧默认值兜底。"
        ) from exc

    cached = _CACHE.get(name)
    if cached and cached[0] == mtime:
        return cached[1]

    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryError(f"注册表无法解析：{path}（{exc}）") from exc
    if not isinstance(payload, dict):
        raise RegistryError(f"注册表顶层必须是对象：{path}")
    expected = REGISTRY_FILES[name][1]
    actual = payload.get("schema")
    if actual != expected:
        raise RegistryError(f"注册表 schema 不匹配：{path} 声明 {actual!r}，期望 {expected!r}")

    _CACHE[name] = (mtime, payload)
    return payload


def registry_snapshot() -> dict[str, Any]:
    """把三份注册表的 schema / 路径 / 关键档位 ID 汇总成一份可打印的快照。"""
    snapshot: dict[str, Any] = {"registry_dir": str(REGISTRY_DIR), "registries": {}}
    for name in REGISTRY_FILES:
        try:
            payload = load_registry(name)
        except RegistryError as exc:
            snapshot["registries"][name] = {"ok": False, "error": str(exc)}
            continue
        entry: dict[str, Any] = {
            "ok": True,
            "schema": payload.get("schema"),
            "path": str(registry_path(name)),
        }
        if name == "cameras":
            entry["ids"] = [str(p.get("id")) for p in payload.get("profiles") or []]
        elif name == "motion_commands":
            entry["ids"] = sorted((payload.get("profiles") or {}).keys())
        elif name == "arrival_criteria":
            entry["sections"] = [
                key for key in ("waypoint", "visual_dock") if isinstance(payload.get(key), dict)
            ]
        snapshot["registries"][name] = entry
    return snapshot
