"""E 组：评测配置页把 B11 质量矩阵接出来了（页面 ↔ 端点 ↔ 判据）。

## 这组测试守的是什么

"界面接出来了"最容易变成一句空话（页面能打开、按钮点了没反应、传的字段被后端静默忽略）。
这里用三条可自动化的判据钉住它：

1. **页面上真有那块东西**：质量矩阵区块存在、四个档位可选、两个端点都被调用；
2. **脚本语法真的过**（`node --check`）—— 页面是单文件内联脚本，语法错就是白屏；
3. **前端传的字段不会被静默忽略**：`magnitudes`/`repeats` 必须一路传到跑评测的函数
   —— 否则 level 档会"看起来跑了"实际用默认幅值；
4. **环境没准备好时如实报 501**（缺适配器 venv），不是 500 也不是"评测失败"这种查不出原因的话。
5. **B11-GAP-2**：单策略请求 multi 档不再冗余跑 1×1 矩阵——后端跳过并说明
   （`skipped-single-policy` + reason），gate 不放行；页面转述原因，不渲染假矩阵。
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import HTTPException  # noqa: E402

from backend import evaluation_api as ea  # noqa: E402


class EvaluationPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "web" / "evaluation.html").read_text(encoding="utf-8")

    def test_quality_section_exists_with_all_four_tiers(self):
        self.assertIn('id="quality"', self.html)
        for tier in ("single", "multi", "level", "stress"):
            self.assertIn(f'value="{tier}"', self.html, f"页面缺档位 {tier}")
        for element in ("q-robot", "q-policy", "q-tier", "q-min", "q-steps", "q-magnitudes", "q-run", "q-list"):
            self.assertIn(f'id="{element}"', self.html, f"页面缺 {element}")

    def test_page_calls_both_quality_endpoints(self):
        self.assertIn("/api/evaluation/quality/run", self.html)
        self.assertIn("/api/evaluation/quality/list", self.html)

    def test_missing_report_is_stated_on_the_page(self):
        """放行判据的对外口径要一致：没有报告 = 未评测 ≠ 达标。"""

        self.assertIn("未评测 ≠ 达标", self.html)

    def test_inline_scripts_pass_node_syntax_check(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("没有 node，跳过脚本语法门禁")
        blocks = re.findall(r"<script>(.*?)</script>", self.html, re.S)
        self.assertTrue(blocks, "页面里没有内联脚本？")
        with tempfile.TemporaryDirectory() as tmp:
            for index, block in enumerate(blocks):
                path = Path(tmp) / f"block-{index}.js"
                path.write_text(block, encoding="utf-8")
                completed = subprocess.run([node, "--check", str(path)], capture_output=True, text=True)
                self.assertEqual(0, completed.returncode, f"script 块 {index} 语法错误：{completed.stderr}")


class QualityEndpointTest(unittest.TestCase):
    def test_request_carries_the_page_fields(self):
        request = ea.QualityRequest(package_dir="assets/robots/demo", policy_id="p",
                                    magnitudes="0.3,0.6", repeats=3)
        self.assertEqual("0.3,0.6", request.magnitudes)
        self.assertEqual(3, request.repeats)

    def test_page_fields_reach_the_runner(self):
        """`magnitudes`/`repeats` 必须一路传到跑评测的函数，不能被静默忽略。"""

        from backend import quality_matrix

        captured: dict = {}
        original = quality_matrix.run_quality

        def fake(**kwargs):
            captured.update(kwargs)
            return {"tier": "level", "package": kwargs["package_dir"], "policy": {"id": "p"},
                    "levels": [], "quality_score": 0.9, "ok": True, "generated_at": "now"}

        quality_matrix.run_quality = fake
        try:
            result = asyncio.run(ea.run_quality_report(ea.QualityRequest(
                package_dir="assets/robots/demo", policy_id="p", tier="level",
                magnitudes="0.3,0.6", repeats=2, save=False,
            )))
        finally:
            quality_matrix.run_quality = original
        self.assertEqual("0.3,0.6", captured.get("magnitudes"))
        self.assertEqual(2, captured.get("repeats"))
        self.assertEqual("level", captured.get("tier"))
        self.assertIsNone(result["report_path"])

    def test_unavailable_adapter_is_reported_as_501(self):
        """缺适配器 venv ⇒ 501 并带上可执行修法（不是 500、也不是"评测失败"）。"""

        from backend import quality_matrix
        from backend.adapter_runtime import AdapterUnavailable

        original = quality_matrix.run_quality

        def fake(**_kwargs):
            raise AdapterUnavailable("找不到可用的适配器解释器；修法：设 LEGGED_STUDIO_MJLAB_VENV=...")

        quality_matrix.run_quality = fake
        try:
            with self.assertRaises(HTTPException) as context:
                asyncio.run(ea.run_quality_report(ea.QualityRequest(package_dir="assets/robots/demo", save=False)))
        finally:
            quality_matrix.run_quality = original
        self.assertEqual(501, context.exception.status_code)
        self.assertIn("LEGGED_STUDIO_MJLAB_VENV", str(context.exception.detail))

    def test_quality_routes_are_registered(self):
        paths = {route.path for route in ea.router.routes}
        self.assertIn("/api/evaluation/quality/run", paths)
        self.assertIn("/api/evaluation/quality/list", paths)


class MultiTierSinglePolicySkipTest(unittest.TestCase):
    """B11-GAP-2：单策略请求 multi 档 = 1×1 冗余矩阵（与 single 同分）。

    语义钉死为「跳过并说明」（`multi="skipped-single-policy"` + reason）：
    不真跑适配器（省一次冗余 MuJoCo），也不复用 single 分数冒充矩阵报告；
    报告 ok=False 且带 blocker，`gate` 不放行（未评测 ≠ 达标）。
    """

    def test_multi_with_single_policy_is_skipped_without_running(self):
        from backend import adapter_runtime
        from backend import quality_matrix

        def boom(*_args, **_kwargs):
            raise AssertionError("单策略 multi 档不应启动适配器脚本（应跳过并说明）")

        original = adapter_runtime.run_json_script
        adapter_runtime.run_json_script = boom
        try:
            report = quality_matrix.run_quality(
                package_dir="assets/robots/demo", tier="multi", policy_id="p")
        finally:
            adapter_runtime.run_json_script = original
        self.assertEqual("skipped-single-policy", report.get("multi"))
        self.assertIn("single", str(report.get("reason")))
        self.assertFalse(report.get("ok"))

    def test_gate_rejects_skipped_multi_report(self):
        from backend import quality_matrix

        report = quality_matrix.run_quality(
            package_dir="assets/robots/demo", tier="multi", policy_id="p")
        verdict = quality_matrix.gate(report, min_score=0.5)
        # gate 只认分数：跳过报告没有分数 ⇒ 不放行（未评测 ≠ 达标）；
        # 跳过原因由报告自带（blockers/reason），页面据此转述，不靠 gate 复述。
        self.assertFalse(verdict["ok"])
        self.assertIsNone(verdict["score"])
        self.assertIn("skipped-single-policy", str(report.get("multi")))
        self.assertTrue(
            any("multi" in str(blocker) for blocker in report["blockers"]),
            f"报告自身应带 multi 跳过说明：{report['blockers']}",
        )


class EvaluationPageMultiSkipCopyTest(unittest.TestCase):
    """B11-GAP-2 前端半边：页面转述 skipped 原因，不渲染假矩阵（NaN 聚合）。"""

    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "web" / "evaluation.html").read_text(encoding="utf-8")

    def test_multi_skip_is_explained_not_faked(self):
        self.assertIn("skipped-single-policy", self.html)
        self.assertIn("multi 档未运行", self.html)


if __name__ == "__main__":
    unittest.main()
