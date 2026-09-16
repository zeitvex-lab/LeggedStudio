"""I5 许可与出处：注册表 vs 实测证据的不变量 + SPDX 识别规则 + 取证规则语义。

## 这组测试守的是什么

`registry/licenses.json` 是**声明**，"每个包的每条许可依据"都要能被 `00_resources` 里的
许可文件复核。历史上这里的问题不是"写错了"，而是**字段声明了却没有任何数据、也没有任何
东西会因此报错**（`robot-package-1.1` 的 `license` 字段一直空着）。所以：

1. **对账必须通过**：注册表与实测逐项一致（路径 / sha256 / spdx / 名称 / 证据条数）；
2. **缺口必须可枚举**：取不到证据的上游是**一小串已登记项**，不是一片静默 —— 既不许
   静默新增，也不许悄悄消失；
3. **SPDX 识别保守**：只在文本无歧义时给 id，认不出就 `None` + 原文名（**不猜**）；
4. **取证规则分两级**：祖先链上的许可**可以主张**；同项目子树里的只登记为**线索**
   （vendor 进来的依赖许可挂到主代码头上，比"不知道"错得更远）。

风格：纯 stdlib；仓库数据的断言直接读真实文件，规则类断言用临时树（不依赖仓库状态）。
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

from tools import audit_licenses as al  # noqa: E402


class RegistryMatchesEvidenceTest(unittest.TestCase):
    """注册表与实测证据逐项一致；缺口可枚举。"""

    def test_audit_passes(self):
        report = al.audit()
        self.assertTrue(report["ok"], report["problems"])
        self.assertEqual(14, report["packages"])

    def test_every_builtin_robot_is_recorded(self):
        recorded = json.loads(al.REGISTRY_PATH.read_text(encoding="utf-8"))
        self.assertEqual(al.SCHEMA_VERSION, recorded["schema_version"])
        self.assertEqual(sorted(al.evidence_files_per_robot()), sorted(recorded["packages"]))

    def test_license_evidence_is_reproducible(self):
        """逐条重算 sha256：许可依据被换掉必须能被检出。"""

        recorded = json.loads(al.REGISTRY_PATH.read_text(encoding="utf-8"))
        for robot, item in recorded["packages"].items():
            for entry in item["components"]:
                path = ROOT / entry["path"]
                self.assertTrue(path.is_file(), f"{robot}: 许可依据 {entry['path']} 不存在")
                self.assertEqual(al._sha256(path), entry["sha256"], f"{robot}: {entry['path']} 哈希不符")
                self.assertTrue(entry["name"], f"{robot}: {entry['path']} 缺人类可读名")

    def test_registered_gaps_are_exactly_the_known_ones(self):
        """缺口集合钉死：新增或消失都要显式改（否则它会静默留在索引里）。"""

        derived = al.derive()
        gaps = {
            (robot, gap["upstream"])
            for robot, item in derived.items() for gap in item["unresolved"]
        }
        self.assertEqual(al.EXPECTED_UNRESOLVED, gaps)
        zero = {robot for robot, item in derived.items() if not item["components"]}
        self.assertEqual(al.EXPECTED_ZERO_LICENSE, zero)

    def test_registered_gaps_carry_actionable_leads(self):
        """缺口要带线索：人接手时知道去哪儿找（不要求线索非空，但要求字段在位）。"""

        recorded = json.loads(al.REGISTRY_PATH.read_text(encoding="utf-8"))
        for robot, item in recorded["packages"].items():
            for gap in item["unresolved"]:
                self.assertIn("reason", gap, f"{robot}: 缺口缺原因")
                self.assertIn("leads", gap, f"{robot}: 缺口缺线索字段")
                self.assertGreater(gap["evidence_files"], 0, f"{robot}: 缺口应记录受影响证据条数")


class SpdxIdentificationTest(unittest.TestCase):
    """SPDX 识别：无歧义才给 id；歧义/陌生文本 → None + 原文（不猜）。"""

    def test_identifies_common_licenses(self):
        cases = {
            "Apache-2.0": "                                 Apache License\n                           Version 2.0, January 2004",
            "MIT": "MIT License\n\nCopyright (c) 2024\n",
            "BSD-3-Clause": (
                "BSD 3-Clause License\n\nRedistribution and use in source and binary forms, with or without\n"
                "modification, are permitted provided that the following conditions are met:\n"
                "Neither the name of the copyright holder nor the names of its contributors"
            ),
            "BSD-2-Clause": (
                "Redistribution and use in source and binary forms, with or without modification, "
                "are permitted provided that the following conditions are met:"
            ),
            "GPL-3.0-only": "                    GNU GENERAL PUBLIC LICENSE\n                       Version 3, 29 June 2007",
            "LGPL-2.1-only": "GNU LESSER GENERAL PUBLIC LICENSE\nVersion 2.1, February 1999",
            "CC-BY-NC-4.0": "Attribution-NonCommercial 4.0 International\n\nCreative Commons Corporation",
            "CC-BY-4.0": "Creative Commons Attribution 4.0 International Public License",
            "ISC": "ISC License\n\nPermission to use, copy, modify, and/or distribute this software",
        }
        for expected, text in cases.items():
            with self.subTest(expected=expected):
                spdx, name = al.identify_spdx(text)
                self.assertEqual(expected, spdx, f"{name} 识别错")
                self.assertTrue(name)

    def test_lgpl_is_not_misread_as_gpl(self):
        """判据顺序的守卫：LGPL 正文里也含 'GNU GENERAL PUBLIC LICENSE' 字样。"""

        spdx, _name = al.identify_spdx(
            "GNU LESSER GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007\n\n"
            "Everyone is permitted to copy and distribute verbatim copies of this license document"
        )
        self.assertEqual("LGPL-3.0-only", spdx)

    def test_unknown_text_is_reported_not_guessed(self):
        spdx, name = al.identify_spdx("Proprietary. All rights reserved by Example Corp.\nNo terms given.")
        self.assertIsNone(spdx, "陌生文本不许给 SPDX id")
        self.assertIn("Proprietary", name)


class LicenseLookupRulesTest(unittest.TestCase):
    """取证规则语义：祖先链可主张；同项目子树只作线索。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="license-lookup-")
        self.root = Path(self.tmp.name)
        self._saved = (al.RESOURCES_ROOT, al.PROJECT_ROOT)
        al.RESOURCES_ROOT = self.root / "00_resources"
        al.PROJECT_ROOT = self.root

    def tearDown(self):
        al.RESOURCES_ROOT, al.PROJECT_ROOT = self._saved
        self.tmp.cleanup()

    def _write(self, relative: str, text: str = "Apache License\nVersion 2.0") -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_ancestor_license_is_claimed(self):
        self._write("00_resources/proj/LICENSE")
        self._write("00_resources/proj/src/robot/config/env_cfgs.py", "x = 1\n")
        found = al.nearest_license("proj/src/robot/config/env_cfgs.py")
        self.assertIsNotNone(found)
        self.assertEqual("LICENSE", found.name)

    def test_vendored_license_is_only_a_lead(self):
        """祖先链没有许可 → 不得主张（子树里那份很可能是 vendor 进来的依赖许可）。"""

        self._write("00_resources/proj/vendor/other/LICENSE")
        self._write("00_resources/proj/src/robot/env_cfgs.py", "x = 1\n")
        self.assertIsNone(al.nearest_license("proj/src/robot/env_cfgs.py"))
        leads = al.nearby_license_leads("proj/src/robot/env_cfgs.py")
        self.assertEqual(["00_resources/proj/vendor/other/LICENSE"], leads)

    def test_licenses_directory_counts_as_a_lead(self):
        """`<dir>/licenses/` 这种"许可放在目录里"的形态也算线索。"""

        (self.root / "00_resources/proj/rsl_rl/licenses").mkdir(parents=True)
        self._write("00_resources/proj/rsl_rl/src/x.py", "x = 1\n")
        self.assertIn("00_resources/proj/rsl_rl/licenses", al.nearby_license_leads("proj/rsl_rl/src/x.py"))

    def test_no_license_anywhere_yields_no_lead(self):
        self._write("00_resources/proj/src/x.py", "x = 1\n")
        self.assertIsNone(al.nearest_license("proj/src/x.py"))
        self.assertEqual([], al.nearby_license_leads("proj/src/x.py"))


if __name__ == "__main__":
    unittest.main()
