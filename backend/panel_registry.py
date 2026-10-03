"""产品面插件注册表（Phase 5，v2.1）：导航/侧栏/桌面从声明生成，机器人与功能零特判。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PANELS_FILE = ROOT / "registry" / "panels" / "index.json"

SERVICE_PROBES = {
    # 声明的 service → 探测路径（/health 派生；未来可扩）
    "backend": "/health",
}


class PanelRegistryError(RuntimeError):
    """面板注册表不合法（fail-loud）。"""


def load_panels(path: Path | None = None) -> list[dict]:
    source = Path(path) if path is not None else PANELS_FILE
    if not source.is_file():
        raise PanelRegistryError(f"面板注册表不存在：{source}")
    raw = json.loads(source.read_text(encoding="utf-8-sig"))
    panels = raw.get("panels")
    if not isinstance(panels, list) or not panels:
        raise PanelRegistryError("面板注册表缺少非空 panels 数组")
    seen: set[str] = set()
    for item in panels:
        pid = str(item.get("id") or "")
        if not pid:
            raise PanelRegistryError("面板缺 id")
        if pid in seen:
            raise PanelRegistryError(f"面板 id 重复：{pid}")
        if not item.get("entry"):
            raise PanelRegistryError(f"面板 {pid} 缺 entry")
        seen.add(pid)
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
