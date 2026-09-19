"""JSON 读取的**单一来源**守卫（2026-09-19 收口）。

## 守什么

仓内曾有 20 多份 JSON 读取小实现，**编码口径真的不一样**：

* ``utf-8-sig``（吃 BOM）：``resource_packs`` / ``robot_packages`` / ``skill_pack`` …
* ``utf-8``（**吃不了 BOM**）：``policy_artifacts`` / ``training.runs`` / ``project_api`` 的导入路径 …

BOM 不是理论问题：Windows 的编辑器、PowerShell 重定向、部分导出工具默认写 BOM。
带 BOM 的 ``robot_package.json``（用户导入的包）或 ``policies/index.json`` 会让
``json.loads`` 在**第一个字节**就抛，报错只说 ``Expecting value: line 1 column 1``，
完全不指向"编码" —— 排查成本极高。

所以三条性质（漂移即失败）：

1. **BOM 可读**：任意模块的 JSON 读取入口都能吃 BOM；
2. **实现唯一**：``load_json`` / ``read_json`` 之外不许再出现
   ``json.loads(<...>.read_text(encoding="utf-8"))``（非 sig 形式）；
3. **语义各留**：各模块的薄封装（缺失 → ``{}`` / ``None`` / 抛域错误）行为不变。
"""

from __future__ import annotations

import ast
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.jsonio import JSON_ENCODING, load_json, read_json, write_json  # noqa: E402

#: 实现的家：放在最底层（``contracts``），因为 ``backend/`` / ``tools/`` / ``contracts/``
#: 三处都要用它 —— 放控制面会出现"底层反向依赖控制面"。``backend/jsonio.py`` 只做 re-export。
JSONIO = ROOT / "contracts" / "jsonio.py"
ALLOWED_DIRECT = {JSONIO}

BOM = b"\xef\xbb\xbf"


def _python_files() -> list[Path]:
    files: list[Path] = []
    for base in ("backend", "contracts", "tools", "adapters", "scripts"):
        root = ROOT / base
        if root.is_dir():
            files.extend(sorted(root.rglob("*.py")))
    return [p for p in files if "__pycache__" not in p.parts and not p.name.startswith("test_")]


class BomToleranceTest(unittest.TestCase):
    """行为面：带 BOM 的 JSON 必须处处可读（这正是收口的收益）。"""

    def _write_bom_json(self, tmp: str, payload: bytes = b'{"robot_id": "go2"}') -> Path:
        path = Path(tmp) / "with_bom.json"
        path.write_bytes(BOM + payload)
        return path

    def test_jsonio_entry_points_accept_bom(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_bom_json(tmp)
            self.assertEqual({"robot_id": "go2"}, read_json(path))
            self.assertEqual({"robot_id": "go2"}, load_json(path))

    def test_module_wrappers_accept_bom(self) -> None:
        """各模块的薄封装也要吃 BOM —— 它们是本轮实际改动最多的入口。"""

        from backend.asset_inspection import _load_json as inspect_load
        from backend.deploy_pack import _load_json as deploy_load
        from backend.policy_artifacts import _load_json as artifacts_load
        from backend.robot_packages import _read_json as packages_read
        from backend.training.runs import _read_json as runs_read

        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_bom_json(tmp)
            for loader in (inspect_load, deploy_load, artifacts_load, packages_read, runs_read):
                with self.subTest(loader=loader.__module__):
                    self.assertEqual({"robot_id": "go2"}, loader(path))

    def test_failure_semantics_are_preserved(self) -> None:
        """收口只统一编码，不改语义：缺失/坏内容各回各自的默认值。"""

        from backend.deploy_pack import _load_json as deploy_load
        from backend.robot_packages import _read_json as packages_read
        from backend.skill_registry import _load_json as registry_load, SkillRegistryError

        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope.json"
            self.assertIsNone(deploy_load(missing), "缺失 → None")
            self.assertEqual({}, packages_read(missing), "缺失 → 空对象")

            broken = Path(tmp) / "broken.json"
            broken.write_bytes(b"{ not json")
            self.assertIsNone(deploy_load(broken))
            self.assertEqual({}, packages_read(broken))

            # 严格入口要把异常留给调用方包成域错误（skill_registry 是既有先例）
            with self.assertRaises(SkillRegistryError):
                registry_load(broken)

            # 非对象：`require=dict` 的语义是"当空对象"，不是抛
            scalar = Path(tmp) / "scalar.json"
            scalar.write_text("[1, 2]", encoding="utf-8")
            self.assertEqual({}, packages_read(scalar))
            self.assertEqual([1, 2], read_json(scalar))

    def test_encoding_constant_is_bom_tolerant(self) -> None:
        self.assertEqual("utf-8-sig", JSON_ENCODING)

    def test_write_json_has_no_bom_and_trailing_newline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out" / "payload.json"
            write_json(path, {"a": 1})
            raw = path.read_bytes()
            self.assertFalse(raw.startswith(BOM), "仓库内写出的 JSON 不带 BOM")
            self.assertTrue(raw.endswith(b"\n"))
            self.assertEqual({"a": 1}, read_json(path))


class SingleSourceScanTest(unittest.TestCase):
    """源码面：读 JSON 的实现只许在 ``backend/jsonio.py``。"""

    def test_no_bom_unsafe_inline_reads(self) -> None:
        """``json.loads(x.read_text(encoding="utf-8"))`` 是新旧口径分叉的唯一形式。

        允许 ``utf-8-sig``（吃 BOM）或走 ``read_json``/``load_json``；
        对**非 JSON** 的文本改写仍可用 ``utf-8``（那是另一件事，不在本守卫范围）。
        """

        offenders: list[str] = []
        for path in _python_files():
            for number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if "json.loads(" in line and 'encoding="utf-8"' in line:
                    offenders.append(f"{path.relative_to(ROOT)}:{number}")
        self.assertEqual([], offenders, f"JSON 读取需吃 BOM（改用 utf-8-sig 或 backend.jsonio）：{offenders}")

    def test_json_helpers_delegate_instead_of_reimplementing(self) -> None:
        """``_load_json`` / ``_read_json`` 的函数体必须**委托**，不许自己 ``json.loads``。

        封装可以有很多个（语义各不相同），实现只能有一个。
        """

        offenders: list[str] = []
        for path in _python_files():
            if path in ALLOWED_DIRECT:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef) or node.name not in {"_load_json", "_read_json"}:
                    continue
                for call in (item for item in ast.walk(node) if isinstance(item, ast.Call)):
                    target = call.func
                    if isinstance(target, ast.Attribute) and target.attr in {"loads", "load"}:
                        offenders.append(f"{path.relative_to(ROOT)}::{node.name}")
                    if isinstance(target, ast.Name) and target.id == "loads":
                        offenders.append(f"{path.relative_to(ROOT)}::{node.name}")
        self.assertEqual([], offenders, f"JSON 读取实现只许在 backend/jsonio.py：{offenders}")


if __name__ == "__main__":
    unittest.main()
