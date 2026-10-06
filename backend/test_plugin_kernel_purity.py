# -*- coding: utf-8 -*-
"""内核纯度门禁（00_know/08 v3.0 §4.2 铁律）——机器守卫，不靠纪律。

三条不变式：
1. **内核 ≤400 行**（能力只在被需要处长出来——dsh 教训）；
2. **零本仓 import**：``plugins/runtime.py`` 只许标准库（控制面/训练面都装得起的依赖）；
3. **零业务词**：机型/族/功能 id 出现在内核 = 特判回潮，判红。
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

KERNEL = ROOT / "plugins" / "runtime.py"
FACADE = ROOT / "plugins" / "core.py"

#: 内核禁词：机型 id（现行 + 已删族）、族词、以及易被特判的功能词
FORBIDDEN_TOKENS = (
    "unitree", "deeprobotics", "zex", "go1", "go2", "go2w", "b2", "b2w", "m20", "lite3",
    "quadruped", "wheel_leg", "humanoid", "g1", "tron1", "microduck", "wuji",
)

ALLOWED_STD_MODULES = {
    "__future__", "importlib", "collections", "typing",
    "functools", "itertools", "operator",
}


class KernelPurityTest(unittest.TestCase):
    source: str = ""

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = KERNEL.read_text(encoding="utf-8")

    def test_kernel_within_line_budget(self):
        lines = self.source.count("\n") + 1
        self.assertLessEqual(lines, 400, f"plugins/runtime.py {lines} 行 > 400 行硬上限")

    def test_kernel_imports_stdlib_only(self):
        tree = ast.parse(self.source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertIn(alias.name.split(".")[0], ALLOWED_STD_MODULES,
                                  f"内核 import 了非白名单模块：{alias.name}")
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                self.assertIn(root, ALLOWED_STD_MODULES,
                              f"内核 from-import 了非白名单模块：{node.module}")

    def test_kernel_has_no_business_tokens(self):
        lowered = self.source.lower()
        hits = [t for t in FORBIDDEN_TOKENS if t in lowered]
        self.assertEqual([], hits, f"内核出现业务词（特判回潮）：{hits}")

    def test_facade_only_reexports_runtime(self):
        """门面不许重新实现——它只能 re-export，否则会出现两个真值。"""
        tree = ast.parse(FACADE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            self.assertNotIsInstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
                                      "plugins/core.py 必须是纯 re-export 门面")

    def test_kernel_exports_stable_surface(self):
        import plugins.runtime as rt
        for name in ("PluginError", "Entry", "Context", "load_entries",
                     "merge_entries", "apply_patch", "mount"):
            self.assertTrue(hasattr(rt, name), f"内核导出面缺 {name}")


if __name__ == "__main__":
    unittest.main()
