"""N2：资源库许可覆盖门禁的契约。

守三件事：
1. 真仓的覆盖数字与零许可名单**一致且如实**（84 / 43 顶层 / 23 仅深层 / 18 完全没有）；
2. **新出现的零许可目录判红**（不能悄悄恶化）；
3. **名单过期也判红**（登记的零许可目录拿到许可后不更新名单 ⇒ 名单变成谎言）。

以及一条诚实声明：本门禁只扫文件存在性，**不判断许可内容是否适用于我们的用法**。
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

import audit_resource_licenses as gate  # noqa: E402


class RealRepoCoverageTest(unittest.TestCase):
    def setUp(self):
        self.report = gate.audit()

    def test_audit_passes_and_numbers_add_up(self):
        self.assertTrue(self.report["ok"], self.report["problems"])
        total = self.report["dirs_total"]
        self.assertEqual(
            total,
            self.report["with_top_license"]
            + self.report["with_deep_license_only"]
            + self.report["zero_license"],
            "三类之和必须等于总数（否则统计口径自相矛盾）",
        )

    def test_zero_license_list_is_frozen_and_matches_reality(self):
        self.assertEqual(
            sorted(self.report["zero_license_dirs"]),
            self.report["registered_zero_license"],
            "实测零许可名单与登记名单必须逐项一致",
        )
        self.assertEqual(len(self.report["zero_license_dirs"]), self.report["zero_license"])

    def test_gate_admits_it_does_not_read_license_content(self):
        self.assertFalse(self.report["scans_content"], "本门禁只扫文件存在性，不该声称读过内容")


class InjectedCounterExampleTest(unittest.TestCase):
    """反例注入：两个方向都必须判红。"""

    def test_new_zero_license_directory_is_caught(self):
        """资源库里冒出一个没有任何许可文件的新目录 ⇒ 判红（先评估再登记）。"""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "brand_new_upstream").mkdir()
            (root / "brand_new_upstream" / "README.md").write_text("x", encoding="utf-8")
            (root / "has_license").mkdir()
            (root / "has_license" / "LICENSE").write_text("MIT", encoding="utf-8")
            report = gate.audit(root)
            self.assertFalse(report["ok"])
            self.assertTrue(any("brand_new_upstream" in item for item in report["problems"]), report["problems"])

    def test_resolved_directory_makes_the_frozen_list_stale(self):
        """登记为零许可的目录**拿到了**许可 ⇒ 判红（名单过期就是谎言）。"""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # 造一个已登记名字（AMP_mjlab）——现在它有许可了
            (root / "AMP_mjlab").mkdir()
            (root / "AMP_mjlab" / "LICENSE").write_text("Apache-2.0", encoding="utf-8")
            report = gate.audit(root)
            self.assertFalse(report["ok"])
            self.assertTrue(any("名单过期" in item for item in report["problems"]), report["problems"])

    def test_deep_only_license_is_counted_as_clue_not_as_zero(self):
        """深层才有许可 ⇒ 记"仅深层有"（线索），**不算零许可**、也不算顶层覆盖。"""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "some_upstream" / "vendor"
            nested.mkdir(parents=True)
            (nested / "LICENSE.txt").write_text("BSD-3-Clause", encoding="utf-8")
            report = gate.audit(root)
            self.assertEqual(report["with_top_license"], 0)
            self.assertEqual(report["with_deep_license_only"], 1)
            # some_upstream 是"仅深层"，不该出现在零许可名单里 → 但 registered 里没有它，
            # 所以"名单过期"分支不该被触发（它不在 EXPECTED 里）
            self.assertNotIn("some_upstream", report["zero_license_dirs"])


if __name__ == "__main__":
    unittest.main()
