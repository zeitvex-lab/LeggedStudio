# -*- coding: utf-8 -*-
"""面板插件清单回归锁（v3.0 Phase 2a）：产品面插件协议——导航是投影，不是手写清单。

形态已从"单文件 panels 数组"（v2.1）迁为 ``registry/plugins/panel/<id>.json``
清单目录（schema ``legged-plugin-1.0``）——一个面板一个 manifest 文件。
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.panel_registry import PanelRegistryError, load_panels, render_navigation


def _manifest(pid: str, **extra) -> dict:
    m = {"schema": "legged-plugin-1.0", "id": pid, "seam": "panel",
         "provides": [f"panel/{pid}"], "entry": f"{pid}.html"}
    m.update(extra)
    return m


def _write_manifests(directory: Path, manifests: list[dict]) -> Path:
    for m in manifests:
        (directory / f"{m['id']}.json").write_text(
            json.dumps(m, ensure_ascii=False), encoding="utf-8")
    return directory


class PanelRegistryTest(unittest.TestCase):
    def test_real_registry_loads_twelve_panels_sorted(self):
        """12 面板（2026-10-05 +controllers；2026-10-12 +onboarding；2026-10-13
        +navigation-editor/exports 两个跳页/新标签页收编进壳）——加面板 = 一个 manifest 文件。
        注：onboarding 落地时本测试停在 9 未同步（存量红，2026-10-13 随收编一并订正）。"""
        panels = load_panels()
        self.assertEqual(12, len(panels))
        orders = [p["order"] for p in panels]
        self.assertEqual(orders, sorted(orders))
        ids = [p["id"] for p in panels]
        self.assertEqual(["home", "onboarding", "robot", "controllers", "config", "training",
                          "simulation", "navmap", "navigation-editor", "deploy", "exports",
                          "artifacts"], ids)
        for p in panels:
            self.assertEqual("panel", p["seam"])
            self.assertIn(f"panel/{p['id']}", p["provides"])

    def test_manifest_filename_must_match_id(self):
        """清单目录形态的不变式：一个面板一个文件，id 即文件名——重名不可能，
        错名当场红（这是对 v2.1"数组内重复 id"检查的强替代）。"""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.json").write_text(
                json.dumps(_manifest("b"), ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(PanelRegistryError, "不一致"):
                load_panels(Path(tmp))

    def test_empty_directory_fails_loud(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(PanelRegistryError, "为空"):
                load_panels(Path(tmp))

    def test_missing_entry_fails_loud(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _write_manifests(Path(tmp), [{"schema": "legged-plugin-1.0", "id": "a",
                                              "seam": "panel", "provides": ["panel/a"]}])
            with self.assertRaisesRegex(PanelRegistryError, "缺 entry"):
                load_panels(d)

    def test_wrong_schema_or_seam_fails_loud(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _write_manifests(Path(tmp), [_manifest("a", schema="panel-registry-1.0")])
            with self.assertRaisesRegex(PanelRegistryError, "schema"):
                load_panels(d)
        with tempfile.TemporaryDirectory() as tmp:
            d = _write_manifests(Path(tmp), [_manifest("a", seam="surface")])
            with self.assertRaisesRegex(PanelRegistryError, "seam"):
                load_panels(d)

    def test_manifest_must_provide_its_own_panel_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _write_manifests(Path(tmp), [_manifest("a", provides=["panel/other"])])
            with self.assertRaisesRegex(PanelRegistryError, "provides"):
                load_panels(d)

    def test_every_declared_provider_is_real_module_attr(self):
        """四投影契约：清单里的每个 provider 声明（cli + home_card）必须是真 ``module:attr``。"""
        from backend.cli_panels import resolve_provider

        for panel in load_panels():
            specs = {d.get("provider") for d in (panel.get("cli"), panel.get("home_card"))
                     if isinstance(d, dict) and d.get("provider")}
            for spec in specs:
                fn = resolve_provider(str(spec))
                self.assertTrue(callable(fn), f"{panel['id']}: {spec}")

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
