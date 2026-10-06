"""运行时档位注册表的统一读取入口（v3.0 Phase 3a：清单来自总表，不再硬编码）。

H8/H9/H10 三条任务共享同一个模式：**数字是数据，不是代码**。相机档位
（``registry/cameras.json``）、运动指令档位（``registry/motion_commands.json``）、
到达判据（``registry/arrival_criteria.json``）都放在 ``registry/`` 下，由本模块统一
读取、缓存与校验，调用方（后端路由 / 自检 / 工具）只认这一个入口。

v3.0 起，"哪些文件构成运行时档位"的唯一真值是 ``registry/plugin-registry.json``
总表里 ``runtime: true`` 的条目——本模块**不再维护自己的文件字典**（Phase 0 前
``REGISTRY_FILES`` 硬编码 3 文件，加一份注册表要改两处）。

约定：

* 每份注册表必须带 ``schema`` 字段（形如 ``xxx-1.0``），缺字段即视为损坏；
* 注册表缺失时**明确报错**（带期望路径），不静默回退到硬编码默认值——
  「悄悄用旧数字」正是 H10 里两套到达阈值并存的原因；
* 读取结果按 mtime 失效（总表与注册表各自缓存），开发期改 JSON 立即生效。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_DIR = ROOT / "registry"
MASTER_TABLE_PATH = REGISTRY_DIR / "plugin-registry.json"
MASTER_TABLE_SCHEMA = "plugin-registry-1.0"

_master_cache: tuple[float, dict[str, Any]] | None = None
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


class RegistryError(RuntimeError):
    """注册表缺失或损坏（不静默回退）。"""


def _load_master_table() -> dict[str, Any]:
    """读总表（按 mtime 缓存）；缺失/损坏/schema 不符 = fail-loud。"""
    global _master_cache
    try:
        mtime = MASTER_TABLE_PATH.stat().st_mtime
    except OSError as exc:
        raise RegistryError(f"插件总表缺失：{MASTER_TABLE_PATH}") from exc
    if _master_cache and _master_cache[0] == mtime:
        return _master_cache[1]
    try:
        payload = json.loads(MASTER_TABLE_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryError(f"插件总表无法解析：{MASTER_TABLE_PATH}（{exc}）") from exc
    if not isinstance(payload, dict) or payload.get("schema") != MASTER_TABLE_SCHEMA:
        raise RegistryError(
            f"插件总表 schema 必须是 {MASTER_TABLE_SCHEMA!r}，得到 "
            f"{payload.get('schema') if isinstance(payload, dict) else type(payload).__name__!r}"
        )
    registries = payload.get("registries")
    if not isinstance(registries, dict) or not registries:
        raise RegistryError(f"插件总表缺少非空 registries 对象：{MASTER_TABLE_PATH}")
    _master_cache = (mtime, payload)
    return payload


def runtime_registry_files() -> dict[str, tuple[str, str]]:
    """``name → (相对路径, 期望 schema)``——总表里 ``runtime: true`` 的条目（唯一真值）。"""
    master = _load_master_table()
    files: dict[str, tuple[str, str]] = {}
    for name, spec in master["registries"].items():
        if isinstance(spec, dict) and spec.get("runtime"):
            files[str(name)] = (str(spec["path"]), str(spec["schema"]))
    if not files:
        raise RegistryError("总表里没有任何 runtime: true 的注册表（运行时档位清单为空）")
    return files


def registry_path(name: str) -> Path:
    """注册表文件路径（不检查存在性，供报错信息与工具打印使用）。"""
    files = runtime_registry_files()
    if name not in files:
        raise RegistryError(f"未知注册表 {name!r}；已登记：{', '.join(sorted(files))}")
    return REGISTRY_DIR / files[name][0]


def load_registry(name: str) -> dict[str, Any]:
    """读取注册表（按 mtime 缓存）。缺失/损坏抛 :class:`RegistryError`。"""
    files = runtime_registry_files()
    if name not in files:
        raise RegistryError(f"未知注册表 {name!r}；已登记：{', '.join(sorted(files))}")
    path = REGISTRY_DIR / files[name][0]
    expected = files[name][1]
    try:
        mtime = path.stat().st_mtime
    except OSError as exc:
        raise RegistryError(
            f"注册表缺失：{path}（期望 schema={expected}）。"
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
    actual = payload.get("schema")
    if actual != expected:
        raise RegistryError(f"注册表 schema 不匹配：{path} 声明 {actual!r}，期望 {expected!r}")

    _CACHE[name] = (mtime, payload)
    return payload


def registry_snapshot() -> dict[str, Any]:
    """把运行时注册表的 schema / 路径 / 关键档位 ID 汇总成一份可打印的快照。"""
    snapshot: dict[str, Any] = {"registry_dir": str(REGISTRY_DIR), "registries": {}}
    for name in runtime_registry_files():
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
