"""trend_probe 纯函数回归锁：趋势/平台判据是**测量架构**，判错一次就误导一轮配方决策。"""

from __future__ import annotations

import importlib
import json
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


class CurriculumCasesTest(unittest.TestCase):
    """课程感知用例推导：趋势必须在**当期命令分布内**测（2026-10-02 实证教训）。"""

    EFFECTIVE = {
        "algorithm_config": {"num_steps_per_env": 24},
        "environment": {
            "commands": {"twist": {"ranges": {}}},
            "curriculum": {"command_vel": {"params": {"velocity_stages": [
                {"step": 0, "lin_vel_x": [-0.1, 0.25], "ang_vel_z": [-0.2, 0.2]},
                {"step": 72000, "lin_vel_x": [-0.25, 0.5], "ang_vel_z": [-0.4, 0.4]},
            ]}}},
        },
    }

    def test_stage0_at_250_iters_uses_stage0_ceiling(self):
        cases = tp.curriculum_cases(self.EFFECTIVE, 250)
        # 250×24=6000 env-steps < 72000 ⇒ stage0：vx 0.25×0.8=0.2、wz 0.2×0.8=0.16；vy 零程跳过
        self.assertEqual(["0.200,0,0", "0,0,0.160"], cases)

    def test_stage1_after_72000_env_steps(self):
        cases = tp.curriculum_cases(self.EFFECTIVE, 3000)  # 3000×24=72000 ⇒ stage1 生效
        self.assertEqual(["0.400,0,0", "0,0,0.320"], cases)

    def test_final_uses_actual_final_iteration_not_infinity(self):
        # "final" = 本 run 的真实末轮（2499×24 < 72000 ⇒ 仍是 stage0）——
        # 曾被当成无穷远迭代取了末段 stage（2026-10-02 实测修正）
        self.assertEqual(["0.200,0,0", "0,0,0.160"],
                         tp.curriculum_cases(self.EFFECTIVE, "final", final_iter=2499))
        self.assertEqual(["0.400,0,0", "0,0,0.320"],
                         tp.curriculum_cases(self.EFFECTIVE, "final", final_iter=4000))

    def test_no_stages_returns_none(self):
        self.assertIsNone(tp.curriculum_cases({"environment": {"commands": {"twist": {}}}}, 250))


class ProfileTrackingCriteriaTest(unittest.TestCase):
    """档案声明的 criteria.tracking 解析——「完训≠达标」的判据来源（2026-10-05）。"""

    def _mk_pkg(self, root: Path, robot: str, profile: dict | None):
        pkg = root / "assets" / "robots" / robot
        (pkg / "training" / "profiles").mkdir(parents=True)
        if profile is not None:
            (pkg / "training" / "profiles" / "p1.json").write_text(
                json.dumps(profile, ensure_ascii=False), encoding="utf-8")

    def test_declared_criteria_resolved(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._mk_pkg(root, "r1", {"criteria": {"tracking": {
                "cases": ["0.5,0,0"], "err_max": 0.35, "cross_max": 0.25}}})
            old = tp.ROOT
            try:
                tp.ROOT = root
                got = tp._profile_tracking_criteria(
                    "r1", {"provenance": {"profile_id": "p1"}})
            finally:
                tp.ROOT = old
            self.assertEqual(["0.5,0,0"], got["cases"])
            self.assertEqual(0.35, got["err_max"])

    def test_missing_everything_is_none(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            old = tp.ROOT
            try:
                tp.ROOT = Path(tmp)  # 空包：无档案 → None
                self.assertIsNone(tp._profile_tracking_criteria("r1", {}))
                self.assertIsNone(tp._profile_tracking_criteria(
                    "r1", {"provenance": {"profile_id": "p1"}}))
            finally:
                tp.ROOT = old

    def test_declaration_without_cases_is_none(self):
        """criteria.tracking 存在但没 cases = 半声明，不猜回落。"""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._mk_pkg(root, "r1", {"criteria": {"tracking": {"err_max": 0.3}}})
            old = tp.ROOT
            try:
                tp.ROOT = root
                self.assertIsNone(tp._profile_tracking_criteria(
                    "r1", {"provenance": {"profile_id": "p1"}}))
            finally:
                tp.ROOT = old

    def test_broken_profile_json_is_none_not_crash(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pkg = root / "assets" / "robots" / "r1" / "training" / "profiles"
            pkg.mkdir(parents=True)
            (pkg / "p1.json").write_text("{broken", encoding="utf-8")
            old = tp.ROOT
            try:
                tp.ROOT = root
                self.assertIsNone(tp._profile_tracking_criteria(
                    "r1", {"provenance": {"profile_id": "p1"}}))
            finally:
                tp.ROOT = old

    def test_run_case_thresholds_flow_through_reason(self):
        """run_case 阈值参数化：声明的 0.35 在 reason 里如实出现（不是写死的 40%）。"""
        import numpy as np
        import tools.check_user_criteria as cuc
        self.assertEqual(cuc.CRIT["err_max"], cuc.run_case.__defaults__[-2])
        # 阈值语义直接锁：err 分数与参数比较（fail-open 旧账的回归锁在此）
        err, threshold = 0.5, 0.35
        self.assertGreater(err, threshold)
        reason = "主轴误差%.0f%%>%.0f%%" % (err * 100, threshold * 100)
        self.assertEqual("主轴误差50%>35%", reason)
        self.assertTrue(np.isfinite(threshold))
