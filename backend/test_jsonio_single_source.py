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

*> 2026-09-19 追加第 4 条性质*：**读 JSON 不许依赖 locale 默认编码**
（``json.load(open(path))`` 不带 ``encoding`` —— Windows(locale=GBK) 上读含中文的
``status.json`` 会抛，被上层 ``except: pass`` 吞掉，已完成的 Run 被报成 running）。
"""

from __future__ import annotations

import ast
import json
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


#: 跳过**非本仓代码**：本地训练 venv 就落在 ``adapters/mjlab/.venv``，``rglob`` 会把
#: 整个 site-packages 扫进来 —— 既慢（实测一次 4 分钟）又会把第三方实现报成"本仓违规"
#: （本地必红、CI 里 venv 不在该路径下则绿，正是"守卫不可信"的典型）。
_SKIP_PARTS = ("__pycache__", ".venv", "site-packages", "node_modules", "build", "dist", ".git")


def _python_files() -> list[Path]:
    files: list[Path] = []
    for base in ("backend", "contracts", "tools", "adapters", "scripts"):
        root = ROOT / base
        if root.is_dir():
            files.extend(sorted(root.rglob("*.py")))
    return [
        p
        for p in files
        if not any(part in _SKIP_PARTS for part in p.parts) and not p.name.startswith("test_")
    ]


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

    def test_dumps_is_the_only_formatter(self) -> None:
        """格式化规则唯一：中文不转义（可读）+ 尾随换行；**落盘策略不在它里面**。

        原子写（临时文件 + rename）是另一件事 —— ``policy_artifacts._write_json_atomic``
        用 :func:`dumps` 拿文本后自己落盘，两者分层不混。
        """

        from contracts.jsonio import dumps

        text = dumps({"b": 1, "a": "中文"})
        self.assertIn("中文", text, "ensure_ascii=False：中文必须是可读的，不是 \\uXXXX")
        self.assertTrue(text.endswith("\n"), "尾随换行：产物进 git 时不留「\\ No newline」")
        self.assertEqual(text, json.dumps({"b": 1, "a": "中文"}, ensure_ascii=False, indent=2) + "\n")
        self.assertEqual(
            dumps({"b": 1, "a": 2}, sort_keys=True),
            json.dumps({"a": 2, "b": 1}, ensure_ascii=False, indent=2) + "\n",
            "sort_keys 透传（run 档案靠它让 diff 稳定）",
        )

    def test_write_json_has_no_bom_and_trailing_newline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out" / "payload.json"
            write_json(path, {"a": 1})
            raw = path.read_bytes()
            self.assertFalse(raw.startswith(BOM), "仓库内写出的 JSON 不带 BOM")
            self.assertTrue(raw.endswith(b"\n"))
            self.assertEqual({"a": 1}, read_json(path))


class LocaleDependentReadRegressionTest(unittest.TestCase):
    """回归：任务状态的读取不许依赖 **locale 默认编码**（2026-09-19 实缺陷）。

    缺陷形态：``with open(path, 'r') as f: json.load(f)`` —— **不指定编码**，
    于是在 Windows（locale=GBK）上读含中文的 ``status.json`` 抛
    ``UnicodeDecodeError``，又被 ``except Exception: pass`` 吞掉；``to_dict()``
    于是回落到内存里的 ``status``（创建后一直是 "running"）——**已完成的 Run
    被一直报成 running**，E8 冒烟门因此找不到「已完成」证据，长训被 409 拒。

    本用例用 **BOM + 中文**：在 UTF-8 locale 的 CI 上旧实现会因 BOM 抛
    ``JSONDecodeError``（同样被吞），所以**任何平台**都能钉住这两个缺陷。
    """

    def test_status_json_with_bom_and_cjk_is_read(self) -> None:
        from backend.training_manager import TrainingTask

        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            payload = {
                "status": "train_completed",
                "note": "训练完成：中文备注（旧实现按 locale 解码会抛）",
                "exit_code": 0,
            }
            (task_dir / "status.json").write_bytes(
                BOM + json.dumps(payload, ensure_ascii=False).encode("utf-8")
            )
            (task_dir / "progress.json").write_bytes(
                BOM + json.dumps({"iteration": 7, "reward_mean": 1.5}, ensure_ascii=False).encode("utf-8")
            )

            task = TrainingTask("regression-task", None, {}, task_dir)
            self.assertEqual(
                "train_completed",
                task.get_status_info().get("status"),
                "带 BOM + 中文的 status.json 必须可读——否则管理器会把完成的 Run 报成 running",
            )
            self.assertEqual(7, task.get_progress().get("iteration"))

    def test_missing_status_still_reads_as_empty(self) -> None:
        """失败语义不变：文件不存在 → 空对象（由调用方回落）。"""
        from backend.training_manager import TrainingTask

        with tempfile.TemporaryDirectory() as tmp:
            task = TrainingTask("missing-task", None, {}, Path(tmp))
            self.assertEqual({}, task.get_status_info())
            self.assertEqual({}, task.get_progress())


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

    def test_json_reads_never_rely_on_locale_encoding(self) -> None:
        """``json.load(open(path))``（**不给 ``encoding``**）是"locale 依赖读"的唯一形式。

        2026-09-19 的实缺陷正是它：Windows（locale=GBK）下读含中文的 ``status.json``
        抛 ``UnicodeDecodeError``，被上层的 ``except Exception: pass`` 吞掉，于是已完成
        的 Run 被一直报成 ``running``（E8 冒烟门随之失灵）。本规则只看
        "``open(...)`` 没给 ``encoding`` 又喂给 ``json.load``"，因此**不吃**显式
        ``utf-8`` / ``utf-8-sig`` 的既有写法，不需要任何白名单。
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
                if not isinstance(node, ast.With):
                    continue
                for item in node.items:
                    call = item.context_expr
                    if not isinstance(call, ast.Call) or item.optional_vars is None:
                        continue
                    func = call.func
                    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
                    if name != "open":
                        continue
                    if any(keyword.arg == "encoding" for keyword in call.keywords):
                        continue
                    bound = item.optional_vars
                    if not isinstance(bound, ast.Name):
                        continue
                    for inner in ast.walk(node):
                        if not isinstance(inner, ast.Call):
                            continue
                        target = inner.func
                        # **只看 ``json.load(...)``**：``pickle.load`` / ``tomllib.load`` 读的
                        # 是二进制 / TOML，不是 JSON —— 规则过宽会把它们误报成违规
                        # （2026-09-19 实测：首版规则在 motion_registry / preflight /
                        # convert_raw_motion_pkls 上产生 3 处假阳性）。
                        is_json_load = (
                            isinstance(target, ast.Attribute)
                            and target.attr in {"load", "loads"}
                            and isinstance(target.value, ast.Name)
                            and target.value.id == "json"
                        )
                        if not is_json_load:
                            continue
                        if any(isinstance(arg, ast.Name) and arg.id == bound.id for arg in inner.args):
                            offenders.append(f"{path.relative_to(ROOT)}:{inner.lineno}")
        self.assertEqual(
            [],
            offenders,
            f"JSON 读取不许依赖 locale 默认编码（给 encoding 或改用 contracts.jsonio）：{offenders}",
        )


if __name__ == "__main__":
    unittest.main()
