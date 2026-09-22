"""**字典字面量里不许有重复的字符串键** —— 静默遮蔽守卫（2026-09-22 实测一次性抓到 4 处）。

## 为什么值得单开一条守卫

Python 对 `{"a": 1, "a": 2}` **不报错、不警告**：后写的赢，先写的**静默变死条目**。
这类缺陷的形态特别坏：

* **不会在任何运行时暴露** —— 跑起来一切正常（赢的那个确实生效）；
* 读代码的人会看到**两个都像意图**的写法，于是按"先写的"理解行为（实测就是这么误读的）；
* 与"两份口径各自成立、其中一个永远不生效"是同一族（本仓反复吃亏的形态）。

2026-09-22 一次全仓 AST 扫描抓到 4 处，全部是"合并/改名时留下的残渣"：

| 位置 | 重复键 | 真相 |
|---|---|---|
| `adapters/mjlab/policy_acceptance.py`（`FRAME_BUILDERS`） | `lite3_rl_sdk_hist6` | 先写的 `_std_frame` 死；后写的 `_frame_himloco_45` 才是注释想要的 |
| `adapters/mjlab/native_worker.py`（reward 别名表） | `feet_air_time` | 先写的是自映射（`→ 自己`）死；后写的 `→ air_time` 生效 |
| `adapters/mjlab/param_catalog.py`（段名标签表） | `clip` / `scale` | 扁平表装不下「观测/动作」两个同名段，后写的（动作）赢 |
| `backend/plugin_protocol.py`（manifest 草稿） | `contract_path` | 先写的 `contract_legacy_v2.json` 死；真值应是 `contract.json` |

## 判据与边界

* 只看**字典字面量**里的**字符串常量键**（`**spread`、变量键、非字符串键都不算——它们本来
  就允许"覆盖"且语义明确）；
* 扫描面 = 仓内 Python（排除 `00_resources` / `.venv` / `site-packages` / `node_modules` /
  `workspace`）——**上游快照与三方库不归我们管**；
* 有意重复的情况（若将来真有）应写成显式赋值（`d["k"] = ...` 两次）或加注释说明，
  而不是在字面量里留两个字面量键。
"""
from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: 扫描根（仓内自己写的 Python）。`tests/` 与 `backend/` 都含测试，一并扫——测试里的
#: 重复键同样会静默遮蔽（"这条断言怎么没生效"）。
SCAN_ROOTS = ("backend", "tools", "adapters", "contracts", "scripts", "tests")

#: 不扫的路径**段**（上游快照 / 三方库 / 运行期产物）。
#:
#: 必须按**路径段**比较、不能拿绝对路径做子串匹配 —— 第一版就是子串匹配，而仓根叫
#: `/workspace` ⇒ `"workspace" in "/workspace/backend/x.py"` 恒真 ⇒ **一个文件都没扫到**
#: （守卫"全绿"地什么都没查，正是它自己要防的那种假绿）。所以本文件自带
#: `test_scanner_covers_...` 与"扫描面 ≥200 个 .py"两条自检。
EXCLUDED_SEGMENTS = frozenset({"00_resources", "node_modules", ".venv", "site-packages", "workspace", "90_归档"})


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        base = ROOT / root
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if EXCLUDED_SEGMENTS.intersection(path.relative_to(ROOT).parts):
                continue
            files.append(path)
    return sorted(files)


def _display(path: Path) -> str:
    """仓内文件显示相对路径；仓外（反例注入用的临时文件）原样显示。"""

    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def find_duplicate_keys(path: Path) -> list[str]:
    """返回 `["相对路径:行号 重复键 ['a', 'b']", ...]`；语法坏的文件记为一条（不静默跳过）。"""

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError) as exc:  # noqa: PERF203
        return [f"{_display(path)}: 无法解析（{exc.__class__.__name__}: {exc}）"]
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = [k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        duplicates = sorted({k for k in keys if keys.count(k) > 1})
        if duplicates:
            found.append(f"{_display(path)}:{node.lineno} 重复键 {duplicates}")
    return found


class NoDuplicateDictKeysTest(unittest.TestCase):
    def test_repo_has_no_duplicate_dict_keys(self):
        files = _iter_python_files()
        problems: list[str] = []
        for path in files:
            problems.extend(find_duplicate_keys(path))
        self.assertGreaterEqual(len(files), 200, f"扫描面太小（{len(files)} 个 .py）——根列表或排除规则可能失效")
        self.assertEqual(
            [], problems,
            "这些字典字面量里有重复字符串键（后写的赢、先写的静默变死条目）：\n  " + "\n  ".join(problems),
        )

    def test_scanner_covers_the_files_that_had_the_defect(self):
        """自检：曾经出问题的文件必须在扫描面里（否则上一条会在"根本没扫到"时假绿）。"""

        scanned = {p.relative_to(ROOT).as_posix() for p in _iter_python_files()}
        for expected in (
            "adapters/mjlab/policy_acceptance.py",
            "adapters/mjlab/native_worker.py",
            "adapters/mjlab/param_catalog.py",
            "backend/plugin_protocol.py",
        ):
            self.assertIn(expected, scanned, f"扫描面漏了 {expected}")

    def test_injected_duplicate_is_caught(self):
        """反例注入：造一个真·重复键，扫描器必须报出来（守卫的守卫）。"""

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dup.py"
            path.write_text('MAP = {"a": 1, "b": 2, "a": 3}\n', encoding="utf-8")
            found = find_duplicate_keys(path)
            self.assertEqual(1, len(found), found)
            self.assertIn("'a'", found[0])

    def test_explicit_reassignment_is_not_flagged(self):
        """**显式赋值不算**：`d["k"] = ...` 两次是明确意图，不该被守卫拦下。"""

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ok.py"
            path.write_text('MAP = {"a": 1}\nMAP["a"] = 2\n', encoding="utf-8")
            self.assertEqual([], find_duplicate_keys(path))


if __name__ == "__main__":
    unittest.main()
