"""N6/N7：登记类门禁（可查性 / 工具孤儿）的契约。

守三件事：
1. 真仓通过，且数字与基线一致（N6 有据可查 39 / 解析 110；N7 孤儿 9）；
2. **反例注入**：N6 的"有据可查"条数下降必须判红、能解析的行数下降必须判红；
   N7 出现新孤儿必须判红、登记孤儿被用上必须判红；
3. 两个门禁都**如实声明自己是文本级**（不声称 CI 真跑过它）。
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

import audit_acceptance_verifiability as n6  # noqa: E402
import audit_tools_inventory as n7  # noqa: E402


class VerifiabilityGateTest(unittest.TestCase):
    def test_real_tasklist_passes(self):
        report = n6.audit()
        self.assertTrue(report["ok"], report["problems"])
        # 只能"不倒退"：上升是改善，不需要批准
        self.assertGreaterEqual(report["machine_textual"], n6.BASELINE_MACHINE_TEXTUAL)
        self.assertGreaterEqual(report["total"], n6.BASELINE_PARSED_ROWS)

    def test_gate_says_it_is_text_level_only(self):
        self.assertTrue(n6.audit()["text_level_only"])

    def _audit_text(self, text: str) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tasklist.md"
            path.write_text(text, encoding="utf-8")
            return n6.audit(path)

    def test_losing_rows_is_caught(self):
        """能解析的任务行数掉下来（条目被删或表形变了）⇒ 判红。"""

        report = self._audit_text("| **Z1** | 某任务 | 已完成 | 无 |\n")
        self.assertFalse(report["ok"])
        self.assertTrue(any("任务行数" in item for item in report["problems"]), report["problems"])

    def test_row_without_evidence_is_reported(self):
        """有产物引用 + 验证词 ⇒ 算有据可查；都没有 ⇒ 不计入（但不判红，除非跌破基线）。"""

        ok, _ = n6.has_evidence({
            "id": "Z1", "status": "已完成（见 tools/audit_motions.py 进 CI）",
            "acceptance": "全绿", "row": "Z1 已完成 tools/audit_motions.py 进 CI 全绿",
        })
        self.assertTrue(ok)
        bad, why = n6.has_evidence({"id": "Z2", "status": "未做", "acceptance": "人工看", "row": "Z2 未做 人工看"})
        self.assertFalse(bad)
        self.assertIn("没写产物", why)


class ToolsInventoryGateTest(unittest.TestCase):
    def test_real_repo_passes_with_frozen_orphans(self):
        report = n7.audit()
        self.assertTrue(report["ok"], report["problems"])
        self.assertEqual(sorted(n7.EXPECTED_UNREFERENCED), report["orphans"])

    def test_gate_says_it_is_text_level_only(self):
        self.assertTrue(n7.audit()["text_level_only"])

    def test_new_orphan_is_caught(self):
        """新增一个没人引用的工具 ⇒ 判红。"""

        with tempfile.TemporaryDirectory() as tmp:
            tools = Path(tmp)
            (tools / "brand_new_tool.py").write_text("x = 1\n", encoding="utf-8")
            report = n7.audit(tools_dir=tools, corpus={})
            self.assertFalse(report["ok"])
            self.assertIn("brand_new_tool.py", report["orphans"])

    def test_frozen_orphan_that_got_used_is_caught(self):
        """登记的孤儿现在有人用了 ⇒ 也判红（名单过期就是谎言）。"""

        with tempfile.TemporaryDirectory() as tmp:
            tools = Path(tmp)
            (tools / "convert_policy.py").write_text("x = 1\n", encoding="utf-8")
            report = n7.audit(tools_dir=tools, corpus={"00_know/01_任务清单.md": "见 tools/convert_policy.py"})
            self.assertFalse(report["ok"])
            self.assertTrue(any("有人用" in item for item in report["problems"]), report["problems"])


if __name__ == "__main__":
    unittest.main()
