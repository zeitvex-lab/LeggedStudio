"""F6：训练指标 NaN / OOM 告警测试。

后端：五大指标序列出现 NaN/±Inf → alerts 出 nan 条目（metric/step 如实）；
全有限序列 → alerts 为空列表（键存在，区分"没检查"与"无告警"）；
training.log 尾部出现显存不足记录 → alerts 出 oom 条目；缺文件/无命中 → 空。
前端：training_monitor.html 有告警渲染入口，且日志行经 escapeHtml 转义。
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.health_cards import build_health_report, scan_nan_alerts, scan_oom_alerts

WEB_DIR = Path(__file__).resolve().parents[1] / "web"


def _write_log(task_dir: Path, lines: list[str]) -> Path:
    log = task_dir / "training.log"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return log


class NanAlertTest(unittest.TestCase):
    """指标序列 NaN/±Inf 扫描。"""

    def test_reward_nan_flags_alert_with_metric_and_step(self) -> None:
        """reward 序列在第 5 步出现 NaN → 一条 nan 告警，metric/step 如实。"""
        rows = [
            {"iteration": i, "reward": 1.0 + i * 0.1, "kl": 0.01, "entropy": 0.9}
            for i in range(8)
        ]
        rows[5]["reward"] = float("nan")
        alerts = build_health_report(rows)["alerts"]
        nan_alerts = [a for a in alerts if a["kind"] == "nan"]
        self.assertEqual(len(nan_alerts), 1)
        self.assertEqual(nan_alerts[0]["metric"], "reward")
        self.assertEqual(nan_alerts[0]["step"], 5)
        self.assertIn("NaN", nan_alerts[0]["text"])

    def test_value_loss_inf_flags_alert(self) -> None:
        """value_loss 出现 +Inf 也算数值发散（kind 同为 nan）。"""
        rows = [{"iteration": i, "value_loss": 0.5} for i in range(4)]
        rows[2]["value_loss"] = float("inf")
        alerts = scan_nan_alerts(rows)
        self.assertEqual([a["metric"] for a in alerts], ["value_loss"])
        self.assertEqual(alerts[0]["step"], 2)
        self.assertIn("Inf", alerts[0]["text"])

    def test_step_falls_back_to_row_index_without_iteration(self) -> None:
        """行内没有 iteration/step 字段时，步号回退到行序号（0 起）。"""
        rows = [{"kl": 0.01}, {"kl": 0.02}, {"kl": float("nan")}]
        alerts = scan_nan_alerts(rows)
        self.assertEqual(alerts[0]["step"], 2)

    def test_finite_series_yields_empty_alerts_key(self) -> None:
        """全有限序列 → alerts 是空列表，但键必须存在（前端区分"没检查"）。"""
        rows = [
            {"iteration": i, "reward": float(i), "kl": 0.01, "entropy": 0.8, "value_loss": 0.5}
            for i in range(20)
        ]
        report = build_health_report(rows)
        self.assertIn("alerts", report)
        self.assertEqual(report["alerts"], [])

    def test_empty_or_single_rows_do_not_flag(self) -> None:
        """空序列/单点不算告警——判据诚实，不伪造结论。"""
        self.assertEqual(scan_nan_alerts([]), [])
        self.assertEqual(scan_nan_alerts([{"reward": 0.0}]), [])
        # 字符串 "NaN" 不是数值，同样不报
        self.assertEqual(scan_nan_alerts([{"reward": "NaN"}]), [])


class OomAlertTest(unittest.TestCase):
    """训练日志尾部 OOM 启发式。"""

    def test_cuda_out_of_memory_line_flags_alert(self) -> None:
        """日志尾部含 "CUDA out of memory" → 一条 oom 告警，带截断日志行。"""
        with tempfile.TemporaryDirectory() as tmp:
            log = _write_log(Path(tmp), [
                "[INFO] iteration 120",
                "torch.cuda.OutOfMemoryError: CUDA out of memory. Tried to allocate 2.00 GiB",
            ])
            alerts = scan_oom_alerts(log)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["kind"], "oom")
        self.assertIn("CUDA out of memory", alerts[0]["line"])
        self.assertIn("OOM", alerts[0]["text"])

    def test_long_line_truncated_to_160_chars(self) -> None:
        """超长日志行截断到 160 字符。"""
        with tempfile.TemporaryDirectory() as tmp:
            log = _write_log(Path(tmp), ["OOM: " + "x" * 300])
            alerts = scan_oom_alerts(log)
        self.assertEqual(len(alerts[0]["line"]), 160)

    def test_clean_or_wordy_log_does_not_flag(self) -> None:
        """无 OOM 记录 → 空；"Room/zoom" 等含 oom 子串的词不误报（词边界）。"""
        with tempfile.TemporaryDirectory() as tmp:
            log = _write_log(Path(tmp), [
                "[INFO] episode done in Room 6, zoomed camera",
                "[INFO] all good",
            ])
            self.assertEqual(scan_oom_alerts(log), [])

    def test_old_oom_beyond_tail_window_ignored(self) -> None:
        """只看最后 400 行：更早的 OOM 记录不报。"""
        with tempfile.TemporaryDirectory() as tmp:
            lines = [f"[INFO] iteration {i}" for i in range(500)]
            lines[10] = "RuntimeError: out of memory"
            log = _write_log(Path(tmp), lines)
            self.assertEqual(scan_oom_alerts(log), [])

    def test_missing_or_unreadable_log_returns_empty(self) -> None:
        """缺文件 → 空列表，不抛异常。"""
        self.assertEqual(scan_oom_alerts(Path(tempfile.gettempdir()) / "no_such_training.log"), [])


class HealthEndpointMergeTest(unittest.TestCase):
    """/health 端点把 NaN 告警与 OOM 告警聚合进同一个 alerts 列表。"""

    def test_endpoint_merges_nan_and_oom_alerts(self) -> None:
        from backend.training import monitor

        class _StubTask:
            def __init__(self, task_dir: Path) -> None:
                self.task_dir = task_dir

        class _StubManager:
            def __init__(self, task: _StubTask) -> None:
                self._task = task

            def get_task(self, task_id: str):
                return self._task

        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            rows = [{"iteration": i, "reward": float(i)} for i in range(6)]
            rows[4]["reward"] = float("nan")
            (task_dir / "metrics.jsonl").write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            _write_log(task_dir, ["CUDA out of memory at iteration 4"])
            stub = _StubManager(_StubTask(task_dir))
            with patch.object(monitor, "get_training_manager", return_value=stub):
                result = asyncio.run(monitor.get_training_health("task-x"))
        self.assertTrue(result["success"])
        kinds = [alert["kind"] for alert in result["alerts"]]
        self.assertIn("nan", kinds)
        self.assertIn("oom", kinds)
        nan_alert = next(a for a in result["alerts"] if a["kind"] == "nan")
        self.assertEqual((nan_alert["metric"], nan_alert["step"]), ("reward", 4))


class FrontendAlertRenderingTest(unittest.TestCase):
    """前端结构断言：告警条渲染入口 + 日志行转义。"""

    def setUp(self) -> None:
        self.html = (WEB_DIR / "training_monitor.html").read_text(encoding="utf-8")

    def test_page_has_alert_container_and_renderer(self) -> None:
        """页面有 healthAlerts 容器与渲染函数，alerts 为空时不渲染任何内容。"""
        self.assertIn('id="healthAlerts"', self.html)
        self.assertIn("function renderHealthAlerts(alerts)", self.html)
        # 空列表 / 旧后端无键 → innerHTML 清空（不渲染）
        self.assertIn("!Array.isArray(alerts) || !alerts.length", self.html)

    def test_alert_lines_pass_through_escape_html(self) -> None:
        """每条告警（含 OOM 日志行）渲染前经 escapeHtml 转义，防日志注入 HTML。"""
        self.assertIn("escapeHtml(healthAlertText(alert))", self.html)
        self.assertIn("alert.line", self.html)


if __name__ == "__main__":
    unittest.main()
