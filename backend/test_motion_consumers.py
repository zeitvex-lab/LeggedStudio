"""M2：Motion 消费统一 —— 三侧引用与注册表对账。

## 这组测试守的是什么

M2 的判据不是"同一个文件"（两侧格式本就不同：训练侧 pkl/npz、浏览器侧 CSV），而是
**同一条 motion 的多个格式版本由注册表统一索引，且不许各处各写一份路径**。于是要钉住：

1. **浏览器格式变体在册**：`simulation/policies/*_motion.csv` 也是 motion 数据（M1 的扫描口径
   只认路径里含 `motions/` 的，于是这一侧的数据在索引之外 —— 2026-09-16 补上）；
2. **CSV 的 fps 是"缺省"不是"实测"**：文件里没有 fps，登记的是浏览器 loader 的缺省 50
   （出处 `web/sim2sim/motion_loader.js:95`）—— 必须带说明，不能假装是读出来的；
3. **消费的必须在册 / 声明的必须存在**：三侧实际存在的文件都要在注册表里；包内契约声明的
   `motion_csv` 必须真的存在（否则浏览器侧启动即 404，而页面只 `console.warn` 一句，静默失败）；
4. **对账本身要能红**：注入一份"手册外"的文件或一条"指向不存在文件"的声明，必须报出问题。

## 2026-09-23 族架构收敛（只留 8 机型）之后的实况

`unitree_g1` 整包删除 ⇒ 训练侧 tracking / amp 两侧的数据在仓内一份不剩，浏览器侧只剩
`unitree_go2` 自带的三条 CSV。第 3 条的计数因此**如实钉成 0 / 0 / 3**：两侧数据重新入库时
对应断言会红，逼着人把口径与注册表一起改 —— 留着 `> 0` 只会制造假绿。
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import motion_registry as mr  # noqa: E402


class BrowserVariantTest(unittest.TestCase):
    def test_browser_csvs_are_indexed(self):
        indexed = mr.load_index()
        csv_files = {
            str(item["path"])
            for entry in indexed.values()
            for item in (entry.get("files") or {}).values()
            if str(item.get("path") or "").endswith(".csv")
        }
        self.assertTrue(csv_files, "浏览器格式变体没进注册表")
        for path in csv_files:
            self.assertTrue((ROOT / path).is_file(), path)
            self.assertIn("simulation/policies", path)

    def test_csv_fps_is_a_cited_default_not_a_measurement(self):
        """CSV 无 fps 元信息 ⇒ 记的是 loader 缺省，且必须写明出处。

        列数按**实测**：现存唯一一份来源（unitree_go2）的 CSV 布局是
        `root_pos3,quat_xyzw4,dof_pos12` = 19 列 / 12 dof（此前这条断言写着 g1 的 36 列 / 29 dof，
        在 g1 删除前就已是既有失败 —— 2026-09-23 一并按实测校正）。
        """

        sample = next(path for path in mr.iter_motion_files() if path.suffix == ".csv")
        meta = mr._read_motion_meta(sample)
        self.assertEqual(50.0, meta["fps"])
        self.assertIn("motion_loader.js", meta["fps_note"])
        self.assertEqual(19, meta["columns"], "浏览器 CSV 布局 = root_pos(3)+quat(4)+dof(12)")
        self.assertEqual(12, meta["dof_dim"])

    def test_layout_classification(self):
        path = ROOT / "assets" / "robots" / "unitree_go2" / "simulation" / "policies" / "backflip_motion.csv"
        layout, variant, clip = mr._layout_of(path)
        self.assertEqual(("browser-csv", "browser", "backflip"), (layout, variant, clip))

    def test_scan_rule_documents_the_browser_location(self):
        """`load_index()` 只返回条目字典，所以这条读**原始文档**：scan 规则必须写明浏览器位置，
        否则下一个人重新派生时又会把这一侧漏掉。"""

        document = json.loads(mr.INDEX_PATH.read_text(encoding="utf-8"))
        self.assertIn("simulation/policies", json.dumps(document.get("rules") or {}, ensure_ascii=False))


class ConsumerAuditTest(unittest.TestCase):
    def test_three_sides_are_accounted_for(self):
        """三侧都在对账口径里，计数按实况钉死：训练侧两侧已随 g1 包删除 ⇒ 0 / 0 / 3。"""

        report = mr.consumer_audit()
        self.assertTrue(report["ok"], report["problems"])
        self.assertEqual(0, report["counts"]["tracking"], "仓内已无 tracking 侧 pkl（随 unitree_g1 删除）")
        self.assertEqual(0, report["counts"]["amp"], "仓内已无 amp 侧 npz（随 unitree_g1 删除）")
        self.assertEqual(3, report["counts"]["browser"])

    def test_declared_browser_motions_exist(self):
        """包内契约声明的 `motion_csv` 必须真的存在（否则浏览器侧静默 404）。"""

        declared = mr.declared_browser_motions()
        self.assertTrue(declared, "没有一条策略声明浏览器运动？口径可能变了")
        for item in declared:
            self.assertTrue(item["exists"], f"{item['package']}/{item['policy_id']} 声明的 {item['motion_csv']} 不存在")

    def test_audit_is_part_of_the_motion_gate(self):
        """对账并进同一个 `audit()`（CI 与 `verify motions` 都读它，不另开门禁入口）。"""

        report = mr.audit()
        self.assertIn("consumers", report)
        self.assertEqual(set(report["consumers"]["counts"]), {"tracking", "amp", "browser"})

    def test_unregistered_file_on_disk_is_reported(self):
        """注入一份"手册外"的文件 ⇒ 必须报"不在注册表里"（对账不能只会说 ok）。"""

        original = mr.iter_motion_files
        ghost = ROOT / "assets" / "robots" / "unitree_go2" / "training" / "source" / "ghost_motions" / "ghost.npz"
        try:
            mr.iter_motion_files = lambda: [*original(), ghost]
            report = mr.consumer_audit()
            self.assertFalse(report["ok"])
            self.assertTrue(any("ghost.npz" in item for item in report["problems"]), report["problems"])
        finally:
            mr.iter_motion_files = original

    def test_missing_declared_browser_motion_is_reported(self):
        original = mr.declared_browser_motions
        try:
            mr.declared_browser_motions = lambda: [
                {"package": "unitree_go2", "policy_id": "demo", "motion_csv": "simulation/policies/missing_motion.csv", "exists": False}
            ]
            report = mr.consumer_audit()
            self.assertFalse(report["ok"])
            self.assertTrue(any("404" in item for item in report["problems"]), report["problems"])
        finally:
            mr.declared_browser_motions = original


if __name__ == "__main__":
    unittest.main()
