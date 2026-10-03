"""面板注册表回归锁（Phase 5，v2.1）：产品面插件协议——导航是投影，不是手写清单。"""

from __future__ import annotations

import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.panel_registry import PanelRegistryError, load_panels, render_navigation


class PanelRegistryTest(unittest.TestCase):
    def test_real_registry_loads_eight_panels_sorted(self):
        panels = load_panels()
        self.assertEqual(8, len(panels))
        orders = [p["order"] for p in panels]
        self.assertEqual(orders, sorted(orders))
        ids = [p["id"] for p in panels]
        self.assertEqual(["home", "robot", "config", "training",
                          "simulation", "navmap", "deploy", "artifacts"], ids)

    def test_duplicate_id_fails_loud(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "index.json"
            p.write_text(json.dumps({"panels": [
                {"id": "a", "entry": "a.html"}, {"id": "a", "entry": "b.html"}]}), encoding="utf-8")
            with self.assertRaisesRegex(PanelRegistryError, "id 重复"):
                load_panels(p)

    def test_missing_entry_fails_loud(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "index.json"
            p.write_text(json.dumps({"panels": [{"id": "a"}]}), encoding="utf-8")
            with self.assertRaisesRegex(PanelRegistryError, "缺 entry"):
                load_panels(p)

    def test_render_projects_with_desktop_filter_and_disabled(self):
        panels = [
            {"id": "web-only", "title": "仅 Web", "entry": "w.html", "desktop": False, "group": "g"},
            {"id": "broken", "title": "坏了", "entry": "b.html", "desktop": True, "group": "g"},
        ]
        nav = render_navigation(panels, current="broken",
                                unavailable={"broken": "控制面不可达"})
        self.assertEqual(1, len(nav), "desktop=False 不投影")
        self.assertTrue(nav[0]["disabled"])
        self.assertEqual("控制面不可达", nav[0]["disabled_reason"])
        self.assertTrue(nav[0]["current"])


if __name__ == "__main__":
    unittest.main()
