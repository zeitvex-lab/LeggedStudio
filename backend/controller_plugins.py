"""控制插件单一真值（MPC 轴，2026-10-05 立项）——**provider + registration**。

「一切皆插件」在控制能力域的落地：MPC 参考的内化与消费都走
``registry/controllers/index.json`` 声明，本模块是它的唯一加载/校验/反查实现
（CLI / HTTP / 首页卡片三面共用；与其他注册表同口径——校验 fail-loud，绝不静默降级）。

校验面（加载即全量校验，任何一条坏声明都让整个表不可用——带坏声明的注册表
比"缺一条"更危险，因为它看起来在提供服务）：

* id 唯一（重复 = 跨条目冲突，fail-loud）；
* ``mechanism_class`` / ``porting.status`` 必须在闭合词汇表内（词汇表随表声明走，
  不在本模块重抄——与 sensor_plugin_contract 同风格）；
* ``source.path`` 指向的快照必须真实存在（悬空声明 = 表不可用）；
* ``snapshot_head`` 必须是 ≥7 位十六进制（溯源锚点；无 .git 快照靠它对上游）；
* ``license`` 缺失 = null 允许，但必须已登记零许可门禁（audit_resource_licenses
  EXPECTED_ZERO_LICENSE）——许可债显式化，不许静默。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_REGISTRY_PATH = _ROOT / "registry" / "controllers" / "index.json"

_HEAD_RE = re.compile(r"^[0-9a-f]{7,40}$")

_cached: dict[str, Any] | None = None


def _fail(message: str) -> None:
    raise ValueError(f"controllers 注册表损坏：{message}")


def load_registry() -> dict[str, Any]:
    """读注册表并全量校验（带缓存；测试用 ``reset_cache`` 强制重读）。"""
    global _cached
    if _cached is not None:
        return _cached
    if not _REGISTRY_PATH.is_file():
        raise FileNotFoundError(f"controllers 注册表不存在：{_REGISTRY_PATH}")
    try:
        data = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        _fail(f"JSON 解析失败：{exc}")
        raise  # 不可达（_fail 必抛）；让类型检查器知道 data 已不可用

    if not str(data.get("schema") or "").startswith("controller-registry-"):
        _fail(f"schema 不认识：{data.get('schema')!r}")

    entries = data.get("controllers")
    if not isinstance(entries, list) or not entries:
        _fail("controllers 必须是非空列表")

    vocabulary = data.get("vocabulary") or {}
    known_class = set(vocabulary.get("mechanism_class") or ())
    known_status = set(vocabulary.get("status") or ())
    if not known_class or not known_status:
        _fail("vocabulary.mechanism_class / vocabulary.status 必须声明（闭合词汇表）")

    seen: set[str] = set()
    for entry in entries:
        cid = str(entry.get("controller_id") or "")
        if not cid:
            _fail("存在无 controller_id 的条目")
        if cid in seen:
            _fail(f"controller_id 重复：{cid!r}（跨条目冲突，fail-loud）")
        seen.add(cid)

        if str(entry.get("mechanism_class") or "") not in known_class:
            _fail(f"{cid}: mechanism_class {entry.get('mechanism_class')!r} 不在词汇表 "
                  f"{sorted(known_class)}")
        status = str((entry.get("porting") or {}).get("status") or "")
        if status not in known_status:
            _fail(f"{cid}: porting.status {status!r} 不在词汇表 {sorted(known_status)}")

        source = entry.get("source") or {}
        rel = str(source.get("path") or "")
        if not rel or not (_ROOT / rel).is_dir():
            _fail(f"{cid}: source.path {rel!r} 指向的快照不存在（悬空声明）")
        head = str(source.get("snapshot_head") or "")
        if not _HEAD_RE.match(head):
            _fail(f"{cid}: snapshot_head {head!r} 必须是 ≥7 位十六进制（上游溯源锚点）")
        if source.get("license") is None:
            zero = _registered_zero_license()
            if rel.rsplit("/", 1)[-1] not in zero:
                _fail(f"{cid}: 无 license 且未登记零许可门禁（先评估再声明，不许静默欠账）")

    _cached = data
    return data


def _registered_zero_license() -> set[str]:
    """零许可门禁的登记名单（存在性守卫用；工具缺失 = 空集 → 无许可声明会被拦）。"""
    try:
        import sys

        tools = str(_ROOT / "tools")
        if tools not in sys.path:
            sys.path.insert(0, tools)
        import audit_resource_licenses  # noqa: PLC0415 — 可选依赖，缺了按空集 fail-closed

        return set(audit_resource_licenses.EXPECTED_ZERO_LICENSE)
    except Exception:  # noqa: BLE001 — 守卫面，不是主路径
        return set()


def reset_cache() -> None:
    global _cached
    _cached = None


def get_controller(controller_id: str) -> dict[str, Any] | None:
    data = load_registry()
    return next((e for e in data["controllers"]
                 if e["controller_id"] == controller_id), None)


def require_controller(controller_id: str) -> dict[str, Any]:
    entry = get_controller(controller_id)
    if entry is None:
        known = sorted(e["controller_id"] for e in load_registry()["controllers"])
        raise KeyError(f"未知控制插件 {controller_id!r}；已注册：{known}")
    return entry


def list_controllers() -> list[dict[str, Any]]:
    return [e for e in load_registry()["controllers"]]


def summary() -> dict[str, Any]:
    """面板投影读数（一处实现三面投影：CLI / HTTP / 首页卡片）。"""
    data = load_registry()
    entries = data["controllers"]

    def _tally(key: str) -> dict[str, int]:
        out: dict[str, int] = {}
        for e in entries:
            value = str(e.get(key) or (e.get("porting") or {}).get("status"))
            out[value] = out.get(value, 0) + 1
        return dict(sorted(out.items()))

    return {
        "registry": "registry/controllers/index.json",
        "count": len(entries),
        "by_mechanism_class": _tally("mechanism_class"),
        "by_porting_status": _tally("porting.status"),
        "controllers": [
            {
                "controller_id": e["controller_id"],
                "label": e.get("label"),
                "mechanism_class": e.get("mechanism_class"),
                "language": e.get("language"),
                "license": (e.get("source") or {}).get("license"),
                "snapshot_head": (e.get("source") or {}).get("snapshot_head"),
                "path": (e.get("source") or {}).get("path"),
                "porting_status": (e.get("porting") or {}).get("status"),
                "mechanism_files": ((e.get("porting") or {}).get("mechanism_files") or []),
            }
            for e in sorted(entries, key=lambda x: x["controller_id"])
        ],
    }
