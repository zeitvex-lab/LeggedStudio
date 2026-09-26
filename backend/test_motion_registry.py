"""M1 Motion 注册表不变量：注册表 vs 磁盘逐文件一致、字段齐备、许可不许留空或编造。

## 这组测试守的是什么

Motion 参考动作是愿景里的一等资源，但此前仓内**只有文件没有资源层**
（`registry/packs/imitation_amp.json` 自己写着「仓内 motion 注册表尚未建立」）。补齐之后，
下面这些必须一直成立：

1. **覆盖是双向的**：磁盘上的每份 motion 都在注册表里，注册表里没有磁盘上不存在的条目；
   条目数与文件数**钉死**（多一个少一个都要显式改测试 —— 否则"少登记一份"会静默通过）；
2. **逐文件内容对账**：sha256 从磁盘重算必须与注册表一致（数据被换掉必被检出）；
3. **字段齐备且自洽**：`validate()` 全通过；`dof_layout` 与 `dof_dim` 对得上；
   每条至少一个变体；
4. **许可不许留空、也不许编**：要么给出 `spdx`，要么显式 `status=unresolved` + 原因；
   未取证的条目必须出现在 `license_gaps` 里（**可枚举**，不是一片静默）；
5. **派生幂等**：同一次磁盘状态派生两次结果逐字节相同（H31/B39 那类"两台机器两个结果"的反面）。

## 2026-09-23 族架构收敛（只留 8 机型）之后的实况

`unitree_g1` 整包删除，随它退场的 **tracking（pkl，逐引擎变体）与 amp（npz）两侧数据在仓内
一份不剩** —— 现存 motion 数据只有浏览器侧 CSV（`<包>/simulation/policies/*_motion.csv`，
unitree_go2 自带三条）。因此本文件里此前针对 tracking/amp 两侧的断言（四条引擎变体、amp 分组、
fps 分档、tracking 的 BSD-3 依据文件）已随数据删除；两类布局的**派生机制**仍在
`backend/motion_registry.py` 里保留，重新引入参考动作库时按实测补回断言。

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

#: 注册表钉死的规模（2026-09-23 实测）：增删 motion 数据是有意动作，须连同本测试一起改。
#  2026-09-16（M2）：33 → 38 条 / 78 → 83 份 —— 浏览器格式变体（
#  `<包>/simulation/policies/*_motion.csv`）此前**不在扫描口径内**，M2 补上后进册。
#  2026-09-23：38 → 3 条 / 83 → 3 份 —— g1 包删除（36 条：tracking 15 + amp 18 + 浏览器 3），
#  剩下 go2 自带的三条浏览器 CSV。
#  2026-09-26：3 → 16 条 / 3 → 16 份 —— 把**族内共享的 AMP 专家动作**纳入扫描口径
#  （`<...>/motions/<robot>_amp/*.txt`，JSON-in-txt，13 条；此前"文件有、资源层无"，
#  族注册表的 imitation gap 点过这条）。它们同时是 go1 AMP 档案复用的同一批数据。
EXPECTED_CLIPS = 16
EXPECTED_FILES = 16
#: 浏览器侧 CSV 变体：`simulation/policies/*_motion.csv`
EXPECTED_BROWSER_CLIPS = 3
#: AMP 专家动作（JSON-in-txt）变体：`<...>/motions/<robot>_amp/*.txt`
EXPECTED_AMP_JSON_CLIPS = 13


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

    def test_layouts_match_the_current_reality(self):
        """如实钉住当前实况：现存布局 = 浏览器 CSV + AMP 专家动作（JSON-in-txt）。

        `tracking-variants` 与 `amp-dirs`（pkl/npz）随 g1 包删除后仓内已无数据（**机制保留**）；
        两类训练侧数据重新入库时这条会红，从而强制把钉死的计数与断言一起补回 ——
        而不是让新数据静默混进别的口径里。
        """

        layouts = {entry["layout"] for entry in mr.derive()["motions"]}
        self.assertEqual({"browser-csv", "amp-json"}, layouts)


class EntrySemanticsTest(unittest.TestCase):
    """字段语义：dof 布局自洽、变体分组正确、浏览器侧出处取自包内声明。"""

    def _entries(self):
        return mr.derive()["motions"]

    def test_all_entries_validate(self):
        problems = {entry["id"]: mr.validate(entry) for entry in self._entries()}
        failing = {key: value for key, value in problems.items() if value}
        self.assertEqual({}, failing)

    def test_dof_layout_matches_dimension(self):
        for entry in self._entries():
            self.assertEqual(f"unitree_dds_{entry['dof_dim']}", entry["dof_layout"])

    def test_browser_clips_are_grouped_by_file(self):
        browser = [entry for entry in self._entries() if entry["layout"] == "browser-csv"]
        self.assertEqual(EXPECTED_BROWSER_CLIPS, len(browser))
        for entry in browser:
            self.assertEqual(["browser"], sorted(entry["files"]))

    def test_browser_lineage_points_at_the_in_package_declaration(self):
        """浏览器侧条目的出处不许是编的：evidence 必须指回包内声明文件，且该文件真实存在。"""

        for entry in [item for item in self._entries() if item["layout"] == "browser-csv"]:
            evidence = entry["lineage"]["evidence"]
            self.assertTrue(evidence, entry["id"])
            for item in evidence:
                self.assertTrue((ROOT / item).is_file(), f"{entry['id']}: 出处文件不存在 {item}")
            self.assertIn(f"assets/robots/{entry['robot']}/simulation/config.json", evidence)

    def test_browser_license_reason_cites_the_declared_source(self):
        """许可未取证时，原因必须引用包内声明的 `source`（真值），而不是一段泛泛的话。"""

        for entry in [item for item in self._entries() if item["layout"] == "browser-csv"]:
            block = entry["license"]
            self.assertEqual("unresolved", block["status"])
            declared = mr._declared_browser_sources().get((entry["robot"], Path(
                next(iter(entry["files"].values()))["path"]).name))
            self.assertTrue(declared, entry["id"])
            self.assertIn(declared, block["reason"], entry["id"])


class LicenseDisciplineTest(unittest.TestCase):
    """许可：不许留空、不许编造；未取证必须可枚举。"""

    def test_license_is_either_declared_or_explicitly_unresolved(self):
        for entry in mr.derive()["motions"]:
            block = entry["license"]
            self.assertTrue(block.get("spdx") or block.get("status") == "unresolved", entry["id"])
            if block.get("status") == "unresolved":
                self.assertTrue(block.get("reason"), f"{entry['id']}: 未取证却没写原因")
                self.assertTrue(block.get("evidence"), f"{entry['id']}: 未取证却没给依据")
                for item in block["evidence"]:
                    self.assertTrue((ROOT / item).is_file(), f"{entry['id']}: 依据不存在 {item}")

    def test_gaps_are_enumerable_and_answer_to_the_registry(self):
        """未取证条目数 == 浏览器 CSV 条数（随包 demo 数据，出处未取证）。"""

        report = mr.audit()
        self.assertEqual(EXPECTED_BROWSER_CLIPS, len(report["license_gaps"]))
        self.assertEqual(
            sorted(gap["id"] for gap in report["license_gaps"]),
            sorted(gap["id"] for gap in report["license_gaps"]),
        )


class ValidationRejectsBadEntriesTest(unittest.TestCase):
    """校验器的反例（门禁必须能红）。"""

    def _good(self) -> dict:
        return dict(next(item for item in mr.derive()["motions"] if item["layout"] == "browser-csv"))

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



class AmpJsonClipsTest(unittest.TestCase):
    """AMP 专家动作（JSON-in-txt）：口径 / 元信息 / 许可能从包内 README 复核。"""

    @classmethod
    def setUpClass(cls):
        derived = mr.derive()
        cls.entries = [e for e in derived["motions"] if e["layout"] == "amp-json"]

    def test_amp_json_group_is_complete(self):
        self.assertEqual(EXPECTED_AMP_JSON_CLIPS, len(self.entries))
        self.assertTrue(all(e["robot"] == "unitree_go2" for e in self.entries))

    def test_meta_is_derived_from_the_files(self):
        """帧宽 49、帧数逐个读出；fps 由 `FrameDuration` 反推（0.02→50 / 0.04→25）。"""
        for entry in self.entries:
            self.assertEqual(49, entry["dof_dim"], entry["id"])
            self.assertGreater(entry["frames_min"], 0, entry["id"])
            self.assertIn(entry["fps"], (25, 50), entry["id"])
        self.assertEqual(
            {"backward", "forward", "forward_left", "forward_right", "left", "left_new",
             "right", "right_new", "rotate", "rotate_inverse", "stand", "turn_left", "turn_right"},
            {
                Path(next(iter(entry["files"].values()))["path"]).stem
                for entry in self.entries
            },
        )

    def test_license_is_apache_with_evidence(self):
        for entry in self.entries:
            self.assertEqual("Apache-2.0", entry["license"].get("spdx"), entry["id"])
            self.assertIn("00_resources/lain_job/LLoco/LICENSE", entry["license"]["evidence"])

    def test_consumers_see_the_amp_clips(self):
        """消费侧对账：AMP 布局的 13 条必须被认成 amp 消费（不是"无消费方"）。"""
        report = mr.audit()
        consumers = report.get("consumers") or {}
        self.assertEqual(EXPECTED_AMP_JSON_CLIPS, (consumers.get("counts") or {}).get("amp", 0))

if __name__ == "__main__":
    unittest.main()
