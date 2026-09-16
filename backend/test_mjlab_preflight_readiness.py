"""A5 收口：mjlab preflight 的**就绪判据**（源码树可选、运行时为硬证据）。

## 这组测试守的是什么

`/api/training/create` 在起 worker 之前先问 `adapters.mjlab.native_adapter.preflight`：
"训练运行时到底能不能用？"。旧判据是

    exists ∧ manager_env_available ∧ runtime.available

其中后两项都描述**源码 checkout**，于是把"必须有 mjlab 源码树"当成了产品前提。
但 mjlab 早已是 `adapters/mjlab/pyproject.toml` 钉住的依赖（`mjlab==1.6.0`，从 PyPI 装进
隔离 venv），源码树只是**可选遮蔽层**（开发 checkout 覆盖已安装版本）。后果：没有
`vendor/mjlab` 的环境（云开发容器、服务端）里 `scripts/cpu_training_smoke_gate.sh`
能真练，而产品内点"开始训练"恒 **501**——"冒烟门禁能跑 ≠ 产品内训练能跑"（A5）。

本文件钉死新判据的三条语义：

1. **源码树不存在 + 运行时可用 → 就绪**（`source_mode="installed_package"`）；
2. **源码树完整 → 就绪**（`source_mode="checkout"`，与旧行为一致）；
3. **运行时不可用 → 未就绪**（fail-closed 不变：缺 torch/mjlab 必须拦住）；
4. **源码树存在但不完整 → 未就绪**（"半份源码"会遮蔽已安装版本，比没有更危险——宁可报错）；
5. **调用方只读报告的裁决**（`execution_ready`），不许自己再拼一遍条件：本文件用结构断言
   守住 `backend/training/create.py` 不再出现旧的三元表达式（两份判据并存必然分叉）。

风格：只 import 适配器模块（零 torch 依赖），探测函数用 monkeypatch 打桩 —— 真探测要起
子进程 import torch，留给"真实训练链"证据（见任务清单 B39/A5 的验收栏）。
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from unittest import mock  # noqa: E402

from adapters.mjlab import native_adapter  # noqa: E402

CREATE_PY = ROOT / "backend" / "training" / "create.py"

#: 源码 checkout 的"完整"标志文件（与 native_adapter 的判据同源，不另立清单）
_CHECKOUT_FILES = (
    Path("src") / "mjlab" / "envs" / "manager_based_rl_env.py",
    Path("src") / "mjlab" / "rl" / "runner.py",
)

_RUNTIME_OK = {"available": True, "interpreters": [{"python": "/venv/bin/python", "available": True}]}
_RUNTIME_BAD = {"available": False, "interpreters": [{"python": "/venv/bin/python", "available": False}]}


def _fake_source(tmp: str, *, complete: bool | None) -> Path:
    """造源码树：``complete=None`` → 目录不存在；``True`` → 标志文件齐全；``False`` → 半份。"""

    source = Path(tmp) / "mjlab"
    if complete is None:
        return source
    source.mkdir(parents=True)
    for relative in _CHECKOUT_FILES if complete else _CHECKOUT_FILES[:1]:
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    return source


def _preflight(source: Path, runtime: dict) -> dict:
    with mock.patch.object(native_adapter, "_probe_runtime", return_value=runtime):
        return native_adapter._preflight_uncached(source)


class SourceTreeIsOptionalTest(unittest.TestCase):
    """源码树是可选的遮蔽层：没有它也能就绪（A5 的核心）。"""

    def test_absent_source_with_working_runtime_is_ready(self):
        """没有源码树（云开发容器/服务端的常态）→ 走已安装发行版，就绪。"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            report = _preflight(_fake_source(tmp, complete=None), _RUNTIME_OK)
        self.assertFalse(report["exists"])
        self.assertEqual("installed_package", report["source_mode"])
        for key in ("smoke_ready", "execution_ready", "training_ready"):
            self.assertTrue(report[key], f"{key} 应为 True：运行时可用即就绪")
        self.assertIsNone(report["not_ready_reason"])
        self.assertIn("installed_package", report["execution_note"])

    def test_complete_source_is_ready_and_reported_as_checkout(self):
        """源码树完整 → 就绪，且如实报告走的是 checkout（与旧行为一致）。"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            report = _preflight(_fake_source(tmp, complete=True), _RUNTIME_OK)
        self.assertTrue(report["exists"])
        self.assertTrue(report["manager_env_available"] and report["runner_available"])
        self.assertEqual("checkout", report["source_mode"])
        self.assertTrue(report["execution_ready"])


class FailClosedStaysTest(unittest.TestCase):
    """fail-closed 的两侧都不能松：运行时不可用、或源码树是"半份"。"""

    def test_runtime_unavailable_is_not_ready_even_without_source(self):
        """缺 torch/mjlab → 必拦（这是真依赖，不是布局问题）。"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            report = _preflight(_fake_source(tmp, complete=None), _RUNTIME_BAD)
        self.assertFalse(report["execution_ready"])
        self.assertEqual("unavailable", report["source_mode"])
        self.assertIn("provision the training venv", str(report["not_ready_reason"]))

    def test_incomplete_checkout_is_not_ready(self):
        """存在但残缺的 checkout 会遮蔽已安装版本 ⇒ 仍判未就绪（比"没有"更危险）。"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            report = _preflight(_fake_source(tmp, complete=False), _RUNTIME_OK)
        self.assertTrue(report["exists"])
        self.assertFalse(report["manager_env_available"] and report["runner_available"])
        self.assertFalse(report["execution_ready"])
        self.assertEqual("checkout_incomplete", report["source_mode"])
        self.assertIn("incomplete", str(report["not_ready_reason"]))

    def test_not_probed_snapshot_is_not_ready_and_has_same_shape(self):
        """廉价快照（未探测）不得自称就绪，且字段形状与探测后一致。"""
        report = native_adapter._filesystem_preflight(Path("/nonexistent/mjlab"))
        self.assertFalse(report["execution_ready"])
        self.assertIsNone(report["source_mode"])
        self.assertIn("not_ready_reason", report)


class RouterReadsTheVerdictTest(unittest.TestCase):
    """调用方只读报告的裁决 —— 两份判据并存必然分叉（A5 的成因）。"""

    def test_create_router_does_not_rebuild_the_condition(self):
        """`create.py` 不再自己拼 `exists ∧ manager_env_available ∧ runtime.available`。"""
        source = CREATE_PY.read_text(encoding="utf-8")
        self.assertNotRegex(
            source,
            re.compile(r'native\["exists"\]\s*or\s*not\s*native\["manager_env_available"\]'),
            "create.py 又自己拼了一遍就绪条件：就绪判据必须只有一处（preflight 报告）",
        )
        self.assertIn('native.get("execution_ready")', source, "create.py 应读报告的执行就绪裁决")
        self.assertIn('native.get("not_ready_reason")', source, "501 应带上机器可读的未就绪原因")


if __name__ == "__main__":
    unittest.main()
