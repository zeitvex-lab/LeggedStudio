# -*- coding: utf-8 -*-
"""形态 Kit 归属表**数据化**门禁（`00_know/06` §17 Phase 3b 余项的收口锁）。

背景（§11.4 实测）：Kit→包归属原先写在 `adapters/mjlab/kits/__init__.py` 的 **docstring**
里（"非数据，机器不可查"），于是积出了「+ 待迁 `unitree_go1`」这类**陈旧字样**——那些包
早就在族里了。本测试把归属表变成**数据 + 静态核对**：

1. 每个族 JSON 必须有完整 `kit` 块（`kit_module` / `binding_from_contract` / 非空 `provides`）；
2. `kit_module` / `binding_from_contract` / `provides` 的模块与属性**静态可解析**
   （查文件 + AST，**不 import** —— 本套件在无 mjlab 的控制面环境也要跑）；
3. `adapters/mjlab/kits/` 下的族 Kit 子包与声明**一一对应**（新族 Kit = 登记族 JSON）；
4. 每个 Kit 都有 `skills/__init__.py` 且它导出 `from_contract`（通用装配器的绑定入口）；
5. 文件头 docstring 的归属表**由数据生成**（与生成器输出一致，且不含陈旧字样）。

判据之外的"反例注入"：`kit_block_problems` 是**纯函数**，坏声明必须被抓出来。
"""

from __future__ import annotations

import ast
import json
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import adapters.mjlab.kits as kits  # noqa: E402

KITS_DIR = ROOT / "adapters" / "mjlab" / "kits"
FAMILIES_DIR = ROOT / "registry" / "families"

#: 陈旧字样：旧手写表把已迁入的包写成"待迁"。归属表里出现即判红。
STALE_MARKERS = ("待迁",)


# ---------------------------------------------------------------------------
# 纯函数：声明校验 + 静态解析（可对合成样本注入反例）
# ---------------------------------------------------------------------------
def kit_block_problems(doc: dict[str, Any], *, family: str) -> list[str]:
    """校验一个族文档的 `kit` 块；返回问题列表（空 = 通过）。"""
    problems: list[str] = []
    kit = doc.get("kit")
    if not isinstance(kit, dict):
        return [f"{family}: 缺 `kit` 块（新族 = 族 JSON 含 kit 块 + 写 Kit）"]
    module = kit.get("kit_module")
    if not isinstance(module, str) or not module:
        problems.append(f"{family}: 缺 `kit.kit_module`")
    binding = kit.get("binding_from_contract")
    if not isinstance(binding, str) or not binding or ":" not in binding:
        problems.append(f"{family}: 缺 `kit.binding_from_contract`（形态 `module:attr`）")
    elif isinstance(module, str):
        bind_module = binding.split(":", 1)[0]
        if bind_module != f"{module}.skills":
            problems.append(
                f"{family}: `binding_from_contract` 的模块 {bind_module!r} "
                f"不是 `<kit_module>.skills`（{module}.skills）"
            )
    provides = kit.get("provides")
    if not isinstance(provides, list) or not provides:
        problems.append(f"{family}: 缺非空 `kit.provides`（归属表「提供什么」列的数据源）")
    else:
        for index, entry in enumerate(provides):
            if not isinstance(entry, str) or not entry:
                problems.append(f"{family}: `kit.provides[{index}]` 不是非空字符串")
    if not (doc.get("members") or []):
        problems.append(f"{family}: 缺非空 `members`（归属表「成员机型」列的数据源）")
    return problems


def module_file(module: str) -> Path | None:
    """`a.b.c` → 源码文件（包 `<...>/__init__.py` 或 `<...>/c.py`）；找不到返回 None。"""
    rel = Path(*module.split("."))
    for candidate in (ROOT / rel / "__init__.py", ROOT / rel.parent / f"{rel.name}.py"):
        if candidate.is_file():
            return candidate
    return None


def defines_symbol(path: Path, symbol: str) -> bool:
    """文件是否**定义/重导出**某符号（AST；不 import）。

    覆盖四种写法：函数/类定义、赋值、`from x import y`（含 `as`）、`import y`。
    """
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == symbol:
                return True
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id == symbol:
                    return True
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if (alias.asname or alias.name) == symbol:
                    return True
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if (alias.asname or alias.name.split(".")[0]) == symbol:
                    return True
    return False


def resolve_entry(entry: str) -> str | None:
    """解析一条 `provides`/绑定声明；可解析返回 None，否则返回问题描述。"""
    if ":" in entry:
        module, symbol = entry.split(":", 1)
        path = module_file(module)
        if path is None:
            return f"模块 {module!r} 找不到源码文件"
        if not defines_symbol(path, symbol):
            return f"{path.relative_to(ROOT).as_posix()} 未定义/重导出 {symbol!r}"
        return None
    return None if module_file(entry) is not None else f"模块 {entry!r} 找不到源码文件"


def family_docs() -> dict[str, dict[str, Any]]:
    docs: dict[str, dict[str, Any]] = {}
    for path in sorted(FAMILIES_DIR.glob("*.json")):
        if path.stem == "index":
            continue
        docs[path.stem] = json.loads(path.read_text(encoding="utf-8-sig"))
    return docs


class KitDeclarationTest(unittest.TestCase):
    def test_every_family_declares_complete_kit_block(self):
        docs = family_docs()
        self.assertTrue(docs, "registry/families/ 不能为空")
        for family, doc in docs.items():
            with self.subTest(family=family):
                self.assertEqual([], kit_block_problems(doc, family=family))

    def test_kit_module_and_binding_resolve_statically(self):
        for family, doc in family_docs().items():
            kit = doc["kit"]
            with self.subTest(family=family):
                module_path = module_file(kit["kit_module"])
                self.assertIsNotNone(module_path, f"kit_module 找不到：{kit['kit_module']}")
                self.assertEqual("__init__.py", module_path.name, "kit_module 必须是包")
                binding = kit["binding_from_contract"]
                binding_module, symbol = binding.split(":", 1)
                self.assertEqual(
                    module_path.parent / "skills" / "__init__.py",
                    module_file(binding_module),
                    "绑定工厂必须来自 `<kit_module>.skills`",
                )
                self.assertTrue(
                    defines_symbol(module_file(binding_module), symbol),
                    f"skills 包未导出绑定符号 {symbol!r}",
                )
                self.assertIsNone(resolve_entry(binding), "binding_from_contract 静态解析失败")

    def test_provides_entries_resolve_statically(self):
        for family, doc in family_docs().items():
            for entry in doc["kit"]["provides"]:
                with self.subTest(family=family, entry=entry):
                    self.assertIsNone(resolve_entry(entry), f"provides 静态解析失败：{entry}")

    def test_each_kit_dir_has_skills_subpackage_exporting_from_contract(self):
        for family, doc in family_docs().items():
            kit_dir = module_file(doc["kit"]["kit_module"]).parent
            with self.subTest(family=family):
                skills_init = kit_dir / "skills" / "__init__.py"
                self.assertTrue(skills_init.is_file(), f"{family}: 缺 skills/__init__.py")
                self.assertTrue(
                    defines_symbol(skills_init, "from_contract"),
                    f"{family}: skills/__init__.py 未导出 from_contract",
                )


class KitsDirParityTest(unittest.TestCase):
    def test_kits_subpackages_match_declared_kits(self):
        on_disk = {
            child.name
            for child in KITS_DIR.iterdir()
            if child.is_dir() and (child / "__init__.py").is_file()
        }
        declared = {doc["kit"]["kit_module"].rsplit(".", 1)[-1] for doc in family_docs().values()}
        self.assertEqual(sorted(declared), sorted(on_disk),
                         "族 Kit 子包与族声明必须一一对应（新增 Kit = 登记族 JSON）")

    def test_ownership_entries_match_declared_kits(self):
        entries = kits.kit_ownership()
        declared = {doc["kit"]["kit_module"] for doc in family_docs().values()}
        self.assertEqual(declared, {item["kit_module"] for item in entries})
        for item in entries:
            for key in ("family_id", "display_name", "morphology", "members",
                        "binding_from_contract", "provides"):
                self.assertIn(key, item)


class DocstringTableTest(unittest.TestCase):
    def test_docstring_table_is_derived_from_data(self):
        table = kits.render_ownership_table(kits.kit_ownership())
        self.assertIn(table, kits.__doc__ or "",
                      "归属表必须由数据生成（不许手写、不许与数据漂移）")

    def test_docstring_has_no_stale_markers(self):
        doc = kits.__doc__ or ""
        for marker in STALE_MARKERS:
            self.assertNotIn(marker, doc, f"归属表含陈旧字样 {marker!r}（旧手写表残留）")


class KitBlockProblemsInjectionTest(unittest.TestCase):
    """反例注入：坏声明必须被抓出来（`kit_block_problems` 是纯函数，可直接喂样本）。"""

    def _good(self) -> dict[str, Any]:
        return {
            "members": ["unitree_go2"],
            "kit": {
                "kit_module": "adapters.mjlab.kits.quadruped_kit",
                "binding_from_contract": "adapters.mjlab.kits.quadruped_kit.skills:from_contract",
                "provides": ["adapters.mjlab.kits.quadruped_kit:package_mjcf"],
            },
        }

    def test_good_sample_passes(self):
        self.assertEqual([], kit_block_problems(self._good(), family="f"))

    def test_missing_kit_block_is_caught(self):
        problems = kit_block_problems({"members": ["x"]}, family="f")
        self.assertTrue(any("kit" in p for p in problems))

    def test_missing_binding_is_caught(self):
        doc = self._good()
        del doc["kit"]["binding_from_contract"]
        self.assertTrue(any("binding_from_contract" in p for p in kit_block_problems(doc, family="f")))

    def test_binding_module_must_be_kit_skills(self):
        doc = self._good()
        doc["kit"]["binding_from_contract"] = "somewhere.else:from_contract"
        self.assertTrue(any("skills" in p for p in kit_block_problems(doc, family="f")))

    def test_empty_provides_is_caught(self):
        doc = self._good()
        doc["kit"]["provides"] = []
        self.assertTrue(any("provides" in p for p in kit_block_problems(doc, family="f")))

    def test_missing_members_is_caught(self):
        doc = self._good()
        doc["members"] = []
        self.assertTrue(any("members" in p for p in kit_block_problems(doc, family="f")))


class StaticResolveInjectionTest(unittest.TestCase):
    def test_unknown_module_is_reported(self):
        self.assertIsNotNone(resolve_entry("no.such.module:thing"))

    def test_unknown_symbol_is_reported(self):
        # 真模块 + 假符号
        self.assertIsNotNone(resolve_entry("adapters.mjlab.kits:definitely_not_defined_xyz"))

    def test_reexported_symbol_resolves(self):
        # from .binding import from_contract 属"重导出"，必须算定义
        self.assertIsNone(resolve_entry("adapters.mjlab.kits.quadruped_kit.skills:from_contract"))


if __name__ == "__main__":
    unittest.main()
