"""面板插件 HTTP 投影（v3.0 Phase 2：四投影之 HTTP 面）。

面板清单（``registry/plugins/panel/*.json``）的服务端投影端点——
``/api/panels``（导航/侧栏/桌面的唯一来源）与 ``/api/panels/home``
（home_card 聚合，fail-soft 逐面板）。原先内联在 ``api_complete``，
按「api_complete 只做装配」的拆解纪律移到本模块（路径与行为零变化）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter(tags=["panels"])


@router.get("/api/panels")
async def api_panels(current: str | None = None):
    """产品面插件清单投影：清单（registry/plugins/panel/）→ 服务探测（诚实禁用）→ 导航结构。

    前端 topnav/workbench 侧栏/桌面 launcher 消费同一份；机器人与功能零特判。"""
    from backend.panel_registry import load_panels, render_navigation, service_unavailable

    panels = load_panels()
    unavailable = {
        p["id"]: reason
        for p in panels
        for svc in ((p.get("requires") or {}).get("services") or [])
        if (reason := service_unavailable(svc, probe=True)) is not None
    }
    nav = render_navigation(panels, current=current or "", unavailable=unavailable)
    return {"success": True, "schema": "panel-registry-1.0", "navigation": nav,
            "panels": panels, "unavailable": unavailable}


@router.get("/api/panels/home")
async def api_panels_home():
    """首页面板聚合（UI 即插件：面板通过 home_card 声明贡献首页卡片）。

    每个声明了 `home_card.provider` 的面板：服务端调用与 CLI 投影**同一个**
    数据函数（manifest 声明的真 ``module:attr``），fail-soft 逐面板——
    单面板故障只降级自己的卡片（error 字段如实带原因），不拖垮整个首页。
    新面板 = 一个 manifest 文件，导航/CLI/首页三面自动出现。
    """
    from backend.panel_registry import load_panels
    from backend.cli_panels import resolve_provider

    cards: list[dict[str, Any]] = []
    for panel in sorted(load_panels(), key=lambda x: (x.get("home_card") or {}).get("order") or 900):
        card_decl = panel.get("home_card") or {}
        provider_spec = str(card_decl.get("provider") or "")
        if not provider_spec:
            continue
        item: dict[str, Any] = {
            "id": panel["id"],
            "title": panel.get("title") or panel["id"],
            "group": panel.get("group") or "其他",
            "entry": panel.get("entry"),
            "order": card_decl.get("order"),
        }
        try:
            item["data"] = resolve_provider(provider_spec)()
            item["ok"] = True
        except Exception as exc:  # noqa: BLE001 — fail-soft：单面板故障不拖垮首页
            item["ok"] = False
            item["error"] = f"{type(exc).__name__}: {exc}"
        cards.append(item)
    return {"success": True, "schema": "panel-home-1.0", "cards": cards}
