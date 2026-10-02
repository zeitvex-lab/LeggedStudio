"""trend_probe 纯函数回归锁：趋势/平台判据是**测量架构**，判错一次就误导一轮配方决策。"""

from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

tp = importlib.import_module("tools.trend_probe") if (ROOT / "tools" / "__init__.py").is_file() else None
if tp is None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("trend_probe", ROOT / "tools" / "trend_probe.py")
    tp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tp)


class ParseRewardCurveTest(unittest.TestCase):
    def test_pairs_interleave_iter_and_reward(self):
        log = (
            "foo\n"
            "\x1b[1m Learning iteration 100/2500 \x1b[0m\n"
            "                            Mean reward: 66.06\n"
            "\x1b[1m Learning iteration 200/2500 \x1b[0m\n"
            "                            Mean reward: 73.10\n"
        )
        path = Path(self._tmp()) / "training.log"
        path.write_text(log, encoding="utf-8")
        curve = tp.parse_reward_curve(path)
        self.assertEqual([(100, 66.06), (200, 73.1)], curve)

    def _tmp(self) -> str:
        import tempfile

        return tempfile.mkdtemp()

    def test_missing_file_is_empty_not_error(self):
        self.assertEqual([], tp.parse_reward_curve(Path("Z:/nope/training.log")))


class DetectPlateauTest(unittest.TestCase):
    def test_flat_window_detected_at_start(self):
        # 73.2 平台 50+ 轮（4096×2500 实测形态）
        curve = [(i, 66.0 if i < 300 else 73.2 + (i % 3) * 0.05) for i in range(300, 400, 10)]
        # 300-350 内有 6 个点 < window+1；补密到每 2 轮一点
        curve = [(i, 66.0 if i < 300 else 73.2 + (i % 3) * 0.05) for i in range(200, 420, 2)]
        self.assertEqual(300, tp.detect_plateau(curve))

    def test_rising_curve_has_no_plateau(self):
        curve = [(i, 10.0 + i * 0.5) for i in range(0, 400, 2)]
        self.assertIsNone(tp.detect_plateau(curve))

    def test_short_curve_refuses_to_judge(self):
        self.assertIsNone(tp.detect_plateau([(i, 70.0) for i in range(0, 60, 2)]))


class TrendVerdictTest(unittest.TestCase):
    def _ck(self, iter_, vx_mean):
        return {"iter": iter_, "cases": [
            {"command": [0.5, 0, 0], "main_axis": 0, "v_mean": [vx_mean, 0, 0]},
        ]}

    def test_trend_ok_within_budget(self):
        # 预算=观测格点 250（save_interval 下限）：0.11/0.5 = 22% ≥ 20% ⇒ 250 轮格点上出趋势 = 达标
        v = tp.trend_verdict([self._ck(250, 0.11)], trend_iter=250, trend_ratio=0.2)
        self.assertEqual("trend_ok", v["verdict"])

    def test_earliest_checkpoint_cannot_be_late(self):
        v = tp.trend_verdict([self._ck(250, 0.11)], trend_iter=200, trend_ratio=0.2)
        # 预算 200 但首格点 250：严格口径判 late（提醒使用者预算要与保存节奏对齐）
        self.assertEqual("trend_late", v["verdict"])

    def test_trend_late(self):
        v = tp.trend_verdict([self._ck(250, 0.0), self._ck(2500, 0.251)],
                             trend_iter=200, trend_ratio=0.2)
        self.assertEqual("trend_late", v["verdict"])
        self.assertEqual(2500, v["trend_at_iter"])

    def test_no_trend_when_all_zero(self):
        v = tp.trend_verdict([self._ck(250, 0.001), self._ck(2500, 0.0)],
                             trend_iter=200, trend_ratio=0.2)
        self.assertEqual("no_trend", v["verdict"])


if __name__ == "__main__":
    unittest.main()
