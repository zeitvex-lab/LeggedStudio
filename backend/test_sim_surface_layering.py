"""N5：仿真分层的"声明—消费"契约（把 H26 里那句不存在的实现换成真断言）。

背景：H26 曾声称"面板归属是纯函数 `PANEL_OWNERSHIP` + `panelVisible()`（fail-closed），
断言扩到 13 组进 CI"。审计核实**该函数不存在**（全仓无此符号，`sensor_panels.js` 也没有，
测试零引用，CI 不跑前端）。真实机制是 `index.html` 的 `data-surface="advanced"` + `app.js` 的选择器消费。

这组测试守**真实机制的两端都在**：声明被删 → 判红；消费被删 → 判红；并如实声明"不渲染浏览器"。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import audit_sim_surface as gate  # noqa: E402


class RealRepoLayeringTest(unittest.TestCase):
    def test_layering_declaration_and_consumption_both_present(self):
        report = gate.audit()
        self.assertTrue(report["ok"], report["problems"])
        self.assertIn("advanced", report["declarations"])

    def test_gate_states_it_does_not_render_a_browser(self):
        """**静态扫描 ≠ 页面显示正确**：这个边界必须写在报告里。"""

        self.assertFalse(gate.audit()["renders_browser"])


class InjectedCounterExampleTest(unittest.TestCase):
    """反例注入：门禁必须抓得住，否则它就是摆设。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.real_html = (ROOT / "web/sim2sim/index.html").read_text(encoding="utf-8")
        self.real_js = (ROOT / "web/sim2sim/app.js").read_text(encoding="utf-8")

    def _audit(self, html: str, js: str) -> dict:
        html_path = self.tmp / "index.html"
        js_path = self.tmp / "app.js"
        html_path.write_text(html, encoding="utf-8")
        js_path.write_text(js, encoding="utf-8")
        return gate.audit(html_path, js_path)

    def test_missing_declaration_is_caught(self):
        """声明被删（分层静默失效）⇒ 判红。"""

        report = self._audit('<div id="sensorDock"></div>', self.real_js)
        self.assertFalse(report["ok"])
        self.assertTrue(any("data-surface" in item for item in report["problems"]), report["problems"])

    def test_sensor_dock_losing_its_declaration_is_caught(self):
        """传感器坞丢掉 advanced 声明（基础仿真里会冒出外部传感器面板）⇒ 判红。"""

        html = self.real_html.replace('id="sensorDock" data-surface="advanced"', 'id="sensorDock"')
        report = self._audit(html, self.real_js)
        self.assertFalse(report["ok"])
        self.assertTrue(any("sensorDock" in item for item in report["problems"]), report["problems"])

    def test_missing_consumer_is_caught(self):
        """消费端被删（声明成了死属性）⇒ 判红。"""

        js = self.real_js.replace("querySelectorAll('[data-surface=\"advanced\"]')", "querySelectorAll('.nothing')")
        report = self._audit(self.real_html, js)
        self.assertFalse(report["ok"])
        self.assertTrue(any("消费" in item for item in report["problems"]), report["problems"])

    def test_missing_switch_is_caught(self):
        """开关未定义 ⇒ 判红（消费端引用了不存在的开关）。"""

        js = self.real_js.replace("SHOW_ADVANCED_PANELS =", "SOMETHING_ELSE =", 1)
        report = self._audit(self.real_html, js)
        self.assertFalse(report["ok"])
        self.assertTrue(any("SHOW_ADVANCED_PANELS" in item for item in report["problems"]), report["problems"])


if __name__ == "__main__":
    unittest.main()
