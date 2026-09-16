"""M1 Motion 注册表不变量：注册表 vs 磁盘逐文件一致、字段齐备、许可不许留空或编造。

## 这组测试守的是什么

Motion 参考动作是愿景里的一等资源，但此前仓内**只有文件没有资源层**
（`registry/packs/imitation_amp.json` 自己写着「仓内 motion 注册表尚未建立」）。补齐之后，
下面这些必须一直成立：

1. **覆盖是双向的**：磁盘上的每份 motion 都在注册表里，注册表里没有磁盘上不存在的条目；
   条目数与文件数**钉死**（多一个少一个都要显式改测试 —— 否则"少登记一份"会静默通过）；
2. **逐文件内容对账**：sha256 从磁盘重算必须与注册表一致（数据被换掉必被检出）；
3. **字段齐备且自洽**：`validate()` 全通过；`dof_layout` 与 `dof_dim` 对得上；
   每条至少一个变体（tracking 是 4 个：rawconv/genesis/isaacgym/isaaclab）；
4. **许可不许留空、也不许编**：要么给出 `spdx`，要么显式 `status=unresolved` + 原因；
   未取证的条目必须出现在 `license_gaps` 里（**可枚举**，不是一片静默）；
5. **派生幂等**：同一次磁盘状态派生两次结果逐字节相同（H31/B39 那类"两台机器两个结果"的反面）。

风格：纯 stdlib（读 npz 时按需 import numpy），直接对真实仓库数据断言。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import motion_registry as mr  # noqa: E402

#: 注册表钉死的规模（2026-09-16 实测）：增删 motion 数据是有意动作，须连同本测试一起改。
# 2026-09-16（M2）：33 → 38 条 / 78 → 83 份 —— 浏览器格式变体（
# `<包>/simulation/policies/*_motion.csv`）此前**不在扫描口径内**，M2 补上后进册。
EXPECTED_CLIPS = 38
EXPECTED_FILES = 83
#: tracking 15 条 × 4 个引擎变体 + amp 18 条 × 1 份。
EXPECTED_TRACKING_CLIPS = 15
EXPECTED_AMP_CLIPS = 18
#: 浏览器侧 CSV 变体（M2 进册）：`simulation/policies/*_motion.csv`
EXPECTED_BROWSER_CLIPS = 5


class RegistryMatchesDiskTest(unittest.TestCase):
    """注册表与磁盘逐文件一致；规模钉死。"""

    def test_audit_passes(self):
        report = mr.audit()
        self.assertTrue(report["ok"], report["problems"])

    def test_counts_are_pinned(self):
        derived = mr.derive()
        self.assertEqual(EXPECTED_CLIPS, derived["counts"]["clips"])
        self.assertEqual(EXPECTED_FILES, derived["counts"]["files"])

    def test_every_file_on_disk_is_registered(self):
        on_disk = {path.relative_to(ROOT).as_posix() for path in mr.iter_motion_files()}
        registered = {
            item["path"]
            for entry in mr.derive()["motions"]
            for item in entry["files"].values()
        }
        self.assertEqual(sorted(on_disk - registered), [], "磁盘上有 motion 没进注册表")
        self.assertEqual(sorted(registered - on_disk), [], "注册表里有磁盘上不存在的 motion 文件")

    def test_hashes_are_reproducible(self):
        for entry in mr.derive()["motions"]:
            for variant, item in entry["files"].items():
                actual = mr._sha256(ROOT / item["path"])
                self.assertEqual(item["sha256"], actual, f"{entry['id']}/{variant} 内容与注册表不符")

    def test_derivation_is_idempotent(self):
        self.assertEqual(mr.derive(), mr.derive(), "同一磁盘状态派生两次结果不同（判据不稳）")


class EntrySemanticsTest(unittest.TestCase):
    """字段语义：dof 布局自洽、变体分组正确、fps 来自文件本身。"""

    def _entries(self):
        return mr.derive()["motions"]

    def test_all_entries_validate(self):
        problems = {entry["id"]: mr.validate(entry) for entry in self._entries()}
        failing = {key: value for key, value in problems.items() if value}
        self.assertEqual({}, failing)

    def test_dof_layout_matches_dimension(self):
        for entry in self._entries():
            self.assertEqual(f"unitree_dds_{entry['dof_dim']}", entry["dof_layout"])

    def test_tracking_clips_carry_four_engine_variants(self):
        tracking = [entry for entry in self._entries() if entry["layout"] == "tracking-variants"]
        self.assertEqual(EXPECTED_TRACKING_CLIPS, len(tracking))
        for entry in tracking:
            self.assertEqual(
                ["genesis", "isaacgym", "isaaclab", "rawconv"], sorted(entry["files"]),
                f"{entry['id']} 少了逐引擎重定向产物（血缘就不完整）",
            )

    def test_amp_clips_are_grouped_by_directory(self):
        amp = [entry for entry in self._entries() if entry["layout"] == "amp-dirs"]
        self.assertEqual(EXPECTED_AMP_CLIPS, len(amp))
        for entry in amp:
            self.assertEqual(["WalkandRun", "Recovery"].count(next(iter(entry["files"]))), 1)

    def test_fps_comes_from_the_file(self):
        """fps 不是常量：tracking 多为 60、amp 为 50，且**如实记录文件的真实值**（含换算产物）。"""

        by_layout = {}
        for entry in self._entries():
            by_layout.setdefault(entry["layout"], set()).add(round(float(entry["fps"]), 6))
        self.assertIn(50.0, by_layout["amp-dirs"])
        self.assertTrue(any(abs(value - 60.0) < 1.0 for value in by_layout["tracking-variants"]), by_layout)
        # 有一条 tracking 的 fps 是换算产物（59.875…），不四舍五入成 60 —— 记录真值比好看重要
        self.assertTrue(any(abs(value - 60.0) > 1e-6 for value in by_layout["tracking-variants"]), by_layout)


class LicenseDisciplineTest(unittest.TestCase):
    """许可：不许留空、不许编造；未取证必须可枚举。"""

    def test_license_is_either_declared_or_explicitly_unresolved(self):
        for entry in mr.derive()["motions"]:
            block = entry["license"]
            self.assertTrue(block.get("spdx") or block.get("status") == "unresolved", entry["id"])
            if block.get("status") == "unresolved":
                self.assertTrue(block.get("reason"), f"{entry['id']}: 未取证却没写原因")
                self.assertTrue(block.get("evidence"), f"{entry['id']}: 未取证却没给依据")

    def test_gaps_are_enumerable_and_answer_to_the_registry(self):
        """未取证条目数 == amp 条数（tracking 有 BSD-3-Clause 依据，amp 数据出处未取证）。"""

        report = mr.audit()
        # 许可缺口 = amp（18，出处未取证）+ 浏览器 CSV（5，随包 demo 数据，同样未取证）
        self.assertEqual(EXPECTED_AMP_CLIPS + EXPECTED_BROWSER_CLIPS, len(report["license_gaps"]))
        self.assertEqual(
            sorted(gap["id"] for gap in report["license_gaps"]),
            sorted(gap["id"] for gap in report["license_gaps"]),
        )

    def test_tracking_license_points_at_real_evidence(self):
        entry = next(item for item in mr.derive()["motions"] if item["layout"] == "tracking-variants")
        evidence = entry["license"]["evidence"]
        self.assertTrue((ROOT / evidence).is_file(), f"许可依据不存在：{evidence}")
        self.assertEqual("BSD-3-Clause", entry["license"]["spdx"])


class ValidationRejectsBadEntriesTest(unittest.TestCase):
    """校验器的反例（门禁必须能红）。"""

    def _good(self) -> dict:
        return dict(next(item for item in mr.derive()["motions"] if item["layout"] == "tracking-variants"))

    def test_missing_fps_is_rejected(self):
        entry = self._good()
        entry["fps"] = None
        self.assertTrue(any("fps" in problem for problem in mr.validate(entry)))

    def test_non_positive_fps_is_rejected(self):
        entry = self._good()
        entry["fps"] = 0
        self.assertTrue(any("fps" in problem for problem in mr.validate(entry)))

    def test_missing_license_block_is_rejected(self):
        entry = self._good()
        entry["license"] = {}
        self.assertTrue(any("license" in problem for problem in mr.validate(entry)))

    def test_fabricated_license_without_spdx_or_reason_is_rejected(self):
        entry = self._good()
        entry["license"] = {"status": "unresolved"}
        self.assertTrue(any("原因" in problem for problem in mr.validate(entry)))

    def test_bad_dof_layout_shape_is_rejected(self):
        entry = self._good()
        entry["dof_layout"] = "dds"
        self.assertTrue(any("dof_layout" in problem for problem in mr.validate(entry)))

    def test_entry_without_files_is_rejected(self):
        entry = self._good()
        entry["files"] = {}
        self.assertTrue(any("files" in problem for problem in mr.validate(entry)))

    def test_missing_required_field_is_rejected(self):
        entry = self._good()
        entry.pop("lineage")
        self.assertTrue(any("lineage" in problem for problem in mr.validate(entry)))


if __name__ == "__main__":
    unittest.main()
