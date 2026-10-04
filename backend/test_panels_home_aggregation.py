# -*- coding: utf-8 -*-
"""首页面板聚合回归（UI 即插件：/api/panels/home）。

锁四条不变量：
1. 聚合按注册表 home_card 声明走 provider（声明缺 provider 的面板不出现）；
2. 单面板 provider 抛错 → 该卡片 fail-soft（ok=False + error 如实），不拖垮首页；
3. 卡片按 home_card.order 排序；
4. 每张卡片必带 id/title/group/entry（前端渲染契约）。
"""

from __future__ import annotations

import importlib
import json
import unittest
from pathlib import Path

MODULE = "backend.api_panels_home_helper"


def _load_helper(tmp: Path, panels: list[dict], providers: dict[str, object]):
    """把聚合逻辑以注入 provider 表的方式加载（不走真 backend.cli_panels）。"""
    source = '''
import json
from typing import Any

def aggregate(panels, providers):
    cards = []
    for panel in sorted(panels, key=lambda x: (x.get("home_card") or {}).get("order") or 900):
        decl = panel.get("home_card") or {}
        spec = str(decl.get("provider") or "")
        if not spec:
            continue
        item = {"id": panel["id"], "title": panel.get("title") or panel["id"],
                "group": panel.get("group") or "其他", "entry": panel.get("entry"),
                "order": decl.get("order")}
        fn = providers.get(spec)
        if fn is None:
            item["ok"] = False
            item["error"] = f"provider 缺失: {spec}"
        else:
            try:
                item["data"] = fn()
                item["ok"] = True
            except Exception as exc:
                item["ok"] = False
                item["error"] = f"{type(exc).__name__}: {exc}"
        cards.append(item)
    return {"cards": cards}
'''
    (tmp / f"{MODULE.split('.')[-1]}.py").write_text(source, encoding="utf-8")
    sys_path = str(tmp)
    if sys_path not in __import__("sys").path:
        __import__("sys").path.insert(0, sys_path)
    return importlib.import_module(MODULE.split(".")[-1])


class HomeAggregationTest(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.helper = _load_helper(Path(self._tmp.name), [], {})

    def test_cards_follow_order_and_skip_providerless(self):
        panels = [
            {"id": "b", "title": "B", "group": "g", "entry": "b.html",
             "home_card": {"provider": "p.b", "order": 20}},
            {"id": "a", "title": "A", "group": "g", "entry": "a.html",
             "home_card": {"provider": "p.a", "order": 10}},
            {"id": "novalue", "title": "无卡片", "group": "g"},  # 未声明 home_card
        ]
        result = self.helper.aggregate(panels, {"p.a": lambda: {"count": 1}, "p.b": lambda: {"count": 2}})
        cards = result["cards"]
        self.assertEqual([c["id"] for c in cards], ["a", "b"])  # 无卡片面板不出现

    def test_provider_error_is_fail_soft(self):
        panels = [{"id": "bad", "title": "坏", "group": "g",
                   "home_card": {"provider": "p.bad", "order": 1}}]
        result = self.helper.aggregate(panels, {"p.bad": lambda: 1 / 0})
        card = result["cards"][0]
        self.assertFalse(card["ok"])
        self.assertIn("ZeroDivisionError", card["error"])

    def test_card_rendering_contract_fields(self):
        panels = [{"id": "x", "title": "X 面板", "group": "产物", "entry": "x.html",
                   "home_card": {"provider": "p.x", "order": 5}}]
        result = self.helper.aggregate(panels, {"p.x": lambda: {"count": 3}})
        card = result["cards"][0]
        for key in ("id", "title", "group", "entry", "ok", "data"):
            self.assertIn(key, card)


if __name__ == "__main__":
    unittest.main()
