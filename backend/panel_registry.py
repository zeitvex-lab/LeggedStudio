"""产品面插件注册表（v3.0 Phase 2a）：面板 = 插件清单，一个文件一个面板。

装载形态从"单文件 index.json 的 panels 数组"（v2.1）迁为
``registry/plugins/panel/<id>.json`` **插件清单目录**（schema ``legged-plugin-1.0``）：

* 每个面板一个 manifest（id/seam/provides + 四投影字段 cli/home_card/desktop/entry）；
* 导航/侧栏/桌面 launcher/CLI 全部由这批声明**投影**生成——机器人与功能零特判；
* provider 声明是**真 ``module:attr``**（importlib 解析，可指向任何模块），
  不再锁死在 ``backend.cli_panels`` 一个文件里。

公开 API（``load_panels`` / ``render_navigation`` / ``service_unavailable``）
与 v2.1 完全一致——消费方（api_complete / cli_panels / CLI / 测试）零改动。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PANELS_DIR = ROOT / "registry" / "plugins" / "panel"

MANIFEST_SCHEMA = "legged-plugin-1.0"
PANEL_SEAM = "panel"

SERVICE_PROBES = {
    # 声明的 service → 探测路径（/health 派生；未来可扩）
    "backend": "/health",
}


class PanelRegistryError(RuntimeError):
    """面板注册表不合法（fail-loud）。"""


def load_panels(source: Path | None = None) -> list[dict]:
    """读取面板插件清单目录（默认 ``registry/plugins/panel/``），返回按 (order, id) 排序的声明列表。

    ``source`` 必须是**目录**（含若干 ``*.json`` manifest）——一个面板一个文件，
    不再是单文件数组（v3.0 Phase 2a 迁移；测试夹具同形态）。
    """
    directory = Path(source) if source is not None else PANELS_DIR
    if not directory.is_dir():
        raise PanelRegistryError(f"面板清单目录不存在：{directory}")
    files = sorted(directory.glob("*.json"))
    if not files:
        raise PanelRegistryError(f"面板清单目录为空：{directory}")
    panels: list[dict] = []
    seen: set[str] = set()
    for manifest_file in files:
        try:
            item = json.loads(manifest_file.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PanelRegistryError(f"面板清单不可解析：{manifest_file.name}（{exc}）") from exc
        if not isinstance(item, dict):
            raise PanelRegistryError(f"面板清单必须是 JSON 对象：{manifest_file.name}")
        if item.get("schema") != MANIFEST_SCHEMA:
            raise PanelRegistryError(
                f"面板清单 schema 必须是 {MANIFEST_SCHEMA!r}，{manifest_file.name} 声明 "
                f"{item.get('schema')!r}"
            )
        if item.get("seam") != PANEL_SEAM:
            raise PanelRegistryError(
                f"面板清单 seam 必须是 {PANEL_SEAM!r}，{manifest_file.name} 声明 {item.get('seam')!r}"
            )
        pid = str(item.get("id") or "")
        if not pid:
            raise PanelRegistryError(f"面板缺 id：{manifest_file.name}")
        if pid != manifest_file.stem:
            raise PanelRegistryError(f"面板 id {pid!r} 与清单文件名 {manifest_file.name} 不一致")
        if pid in seen:
            raise PanelRegistryError(f"面板 id 重复：{pid}")
        if not item.get("entry"):
            raise PanelRegistryError(f"面板 {pid} 缺 entry")
        if f"panel/{pid}" not in (item.get("provides") or []):
            raise PanelRegistryError(f"面板 {pid} 的 provides 必须含 'panel/{pid}'")
        seen.add(pid)
        panels.append(item)
    return sorted(panels, key=lambda p: (int(p.get("order") or 0), p["id"]))


def service_unavailable(service: str, *, probe: bool = False) -> str | None:
    """声明服务的可用性探测：返回原因（不可用）或 None（可用）。"""
    probe_path = SERVICE_PROBES.get(service)
    if not probe_path or not probe:
        return None  # 不探测 = 默认可用（静态生成场景）；运行期探测由 API 层做
    try:
        import urllib.request

        with urllib.request.urlopen(f"http://127.0.0.1:8765{probe_path}", timeout=1.5) as resp:
            return None if resp.status == 200 else f"/health {resp.status}"
    except Exception as exc:  # noqa: BLE001
        return f"控制面不可达：{type(exc).__name__}"


def render_navigation(panels: list[dict], *, current: str = "",
                      unavailable: dict[str, str] | None = None) -> list[dict]:
    """注册表 → 导航结构（纯函数可测；HTML 渲染在前端/shared）。unavailable = 置灰并带原因。"""
    unavailable = unavailable or {}
    nav = []
    for p in panels:
        if p.get("desktop") is False:
            continue
        reason = unavailable.get(p["id"])
        nav.append({
            "id": p["id"],
            "title": p.get("title") or p["id"],
            "href": p["entry"],
            "group": p.get("group") or "其他",
            "disabled": bool(reason),
            "disabled_reason": reason or "",
            "current": p["id"] == current,
        })
    return nav


@lru_cache(maxsize=1)
def _cached_panels() -> list[dict]:
    return load_panels()
