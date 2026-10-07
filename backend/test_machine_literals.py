# -*- coding: utf-8 -*-
"""Phase 5 余项门禁的回归锁（`tools/audit_machine_literals.py`）。

守四件事：

1. **词表从包名派生**（`assets/robots/` 的 8 个机型 + `_`/`-` 变体；长的在前避免前缀误吞）；
2. **仓库当前扫描结果 == 基线**（基线不许虚高：真降下来了就必须显式收紧，见 `--write-baseline`）；
3. **两套口径的语义**：Python 只数**代码里的字符串常量**（docstring 不算）、JS **剥注释**后连
   标识符/对象键一起算——各自用反例注入钉住；
4. 基线的词表与派生词表一致（词表漂移可见）。
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import audit_machine_literals as aml  # noqa: E402

PACKAGE_IDS = {
    "unitree_go2", "unitree_go1", "unitree_b2", "deeprobotics_lite3",
    "deeprobotics_m20", "unitree_b2w", "unitree_go2w", "zex-w",
}


def _baseline() -> dict:
    return json.loads(aml.BASELINE_PATH.read_text(encoding="utf-8-sig"))


class VocabularyTest(unittest.TestCase):
    def test_derived_from_robot_packages(self):
        vocabulary = set(aml.machine_vocabulary())
        for package in PACKAGE_IDS:
            with self.subTest(package=package):
                self.assertIn(package, vocabulary)
        self.assertIn("zex_w", vocabulary, "`_`/`-` 互换变体必须覆盖")

    def test_longest_first(self):
        vocabulary = aml.machine_vocabulary()
        lengths = [-len(value) for value in vocabulary]
        self.assertEqual(sorted(lengths), lengths, "词表必须按长度降序（避免前缀误吞）")

    def test_baseline_vocabulary_matches_derived(self):
        self.assertEqual(aml.machine_vocabulary(), _baseline()["vocabulary"],
                         "基线里冻结的词表与派生词表不一致（词表变了要显式刷新基线）")


class RealRepoTest(unittest.TestCase):
    def test_current_scan_equals_baseline(self):
        counts = aml.scan()
        self.assertEqual(_baseline()["counts"], counts,
                         "机型字面量分布与基线不一致：涨了=判红；降了=请 --write-baseline 收紧")

    def test_no_regression_against_baseline(self):
        self.assertEqual([], aml.compare_to_baseline(aml.scan(), _baseline()["counts"]))

    def test_kits_hits_are_code_literals_not_docstrings(self):
        # kits 侧的命中必须很少：溯源说明都在注释/docstring 里，AST 口径不计
        counts = aml.scan()
        kit_hits = {path: value for path, value in counts.items() if path.startswith("adapters/")}
        self.assertLessEqual(sum(kit_hits.values()), 3,
                             f"kits 层出现较多机型字面量（应为个位数，多半是新特判）：{kit_hits}")


class PythonAstSemanticsTest(unittest.TestCase):
    def _pattern(self):
        return aml._pattern(aml.machine_vocabulary())

    def test_docstring_mentions_are_ignored(self):
        source = '"""来源：assets/robots/unitree_go2/training/source。"""\n\nX = 1\n'
        self.assertEqual(0, aml.count_python_source(source, self._pattern()))

    def test_code_string_literal_is_counted(self):
        source = 'ROOT = "assets/robots/unitree_go2/training/source"\n'
        self.assertEqual(1, aml.count_python_source(source, self._pattern()))

    def test_function_docstring_is_ignored_but_body_literal_is_counted(self):
        source = (
            "def f():\n"
            '    """提到 unitree_go2 一次。"""\n'
            '    return "unitree_go2"\n'
        )
        self.assertEqual(1, aml.count_python_source(source, self._pattern()))

    def test_comment_mentions_are_ignored(self):
        source = "# 原 zex-w 包逐字上移\nX = 1\n"
        self.assertEqual(0, aml.count_python_source(source, self._pattern()))


class JavaScriptSemanticsTest(unittest.TestCase):
    def _pattern(self):
        return aml._pattern(aml.machine_vocabulary())

    def test_line_and_block_comments_are_ignored(self):
        source = (
            "// 归一化到 unitree_go2\n"
            "/* unitree_b2 是包名 */\n"
            "const x = 1;\n"
        )
        self.assertEqual(0, aml.count_js_source(source, self._pattern()))

    def test_string_and_object_key_are_counted(self):
        source = 'const a = "unitree_go2";\nconst m = { unitree_b2: 1 };\n'
        self.assertEqual(2, aml.count_js_source(source, self._pattern()))

    def test_strip_preserves_length_and_strings(self):
        source = 'const url = "http://x//unitree_go2"; // 注释 unitree_b2\n'
        stripped = aml.strip_js_comments(source)
        self.assertEqual(len(source), len(stripped), "剥注释必须保长度（便于报行）")
        self.assertIn("unitree_go2", stripped, "字符串内容必须保留")
        self.assertNotIn("unitree_b2", stripped, "注释里的必须剥掉")

    def test_template_literal_is_string_state(self):
        source = "const a = `unitree_go2`; // unitree_b2\n"
        self.assertEqual(1, aml.count_js_source(source, self._pattern()))


class BaselineGateInjectionTest(unittest.TestCase):
    def test_new_file_is_flagged(self):
        problems = aml.compare_to_baseline({"web/新文件.js": 1}, {})
        self.assertTrue(any("新出现" in p for p in problems))

    def test_increase_is_flagged(self):
        problems = aml.compare_to_baseline({"a.js": 3}, {"a.js": 2})
        self.assertTrue(any("只许减少" in p for p in problems))

    def test_decrease_passes(self):
        self.assertEqual([], aml.compare_to_baseline({"a.js": 1}, {"a.js": 2}))

    def test_equal_passes(self):
        self.assertEqual([], aml.compare_to_baseline({"a.js": 2}, {"a.js": 2}))

    def test_scan_targets_exclude_tests_and_vendored(self):
        for path in aml.js_targets():
            self.assertFalse(path.name.endswith(".test.mjs"), path)
            self.assertNotIn("vendor", path.parts, path)


if __name__ == "__main__":
    unittest.main()
