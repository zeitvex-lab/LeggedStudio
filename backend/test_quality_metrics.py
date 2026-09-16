"""B11 八指标评测：口径、复算与边界。

## 这组测试守的是什么

B11 的验收是"**八指标齐、四档判据可复算**、产出报告 JSON"。要做到"可复算"，指标必须是
**纯函数 + 口径写死**，而不是"跑一遍看着像"。所以这里用**合成数据**把每个公式的数值钉死
（完美跟踪 = 1.0、偏差多少 = 扣多少、软限位超多少 = 扣多少、加权几何平均权重起了什么作用），
再用**真跑一条策略**确认整条链路（MuJoCo 信号 → 八指标 → 质量分 → 报告）能通。

同轮实测到的两处"照抄不通"也在这里钉住：

* **足端不能按名字找**：本仓模型几何**全部无名**（zex-w 38 个 geom 的 `mj_id2name` 全 None），
  上游按 `foot_geom_names` 过滤的做法在这里一个也匹配不到 ⇒ 改为**按结构派生**（叶体几何）；
* **重力投影只有一处实现**：用 `policy_acceptance.projected_gravity`（验收/浏览器同口径），
  自写一份曾把 30° 侧倾算成 1.0（变量名与乘积混淆）。
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "adapters" / "mjlab"
for path in (str(ROOT), str(ADAPTER)):
    if path not in sys.path:
        sys.path.insert(0, path)

import quality_metrics as qm  # noqa: E402


class WeightTest(unittest.TestCase):
    def test_weights_match_upstream(self):
        """权重来自上游 `base_gauge_config.py::QUALITY_WEIGHTS`（照抄，不自己调）。"""

        self.assertEqual(
            {
                "lin_vel_err": 2.0, "ang_vel_err": 2.0, "dof_limits": 1.0, "dof_power": 1.0,
                "orientation_stability": 1.0, "torque_smoothness": 1.0,
                "friction_margin": 1.0, "zmp_margin": 1.0,
            },
            qm.QUALITY_WEIGHTS,
        )

    def test_quality_score_is_weighted_geometric_mean(self):
        self.assertAlmostEqual(1.0, qm.quality_score({name: 1.0 for name in qm.QUALITY_WEIGHTS}), places=9)
        self.assertAlmostEqual(0.5, qm.quality_score({name: 0.5 for name in qm.QUALITY_WEIGHTS}), places=9)
        # 权重更高的一项掉下来，总分掉得更多（证明权重真的起作用）
        heavy = qm.quality_score({**{name: 1.0 for name in qm.QUALITY_WEIGHTS}, "lin_vel_err": 0.25})
        light = qm.quality_score({**{name: 1.0 for name in qm.QUALITY_WEIGHTS}, "dof_limits": 0.25})
        self.assertLess(heavy, light)

    def test_quality_score_clips_to_avoid_log_zero(self):
        self.assertGreater(qm.quality_score({name: 0.0 for name in qm.QUALITY_WEIGHTS}), 0.0)


class VelErrTest(unittest.TestCase):
    def test_perfect_tracking_scores_one(self):
        cmd = np.tile([0.4, 0.0, 0.0], (3, 1))
        limits = np.array([1.0, 1.0, 1.0])
        np.testing.assert_allclose(qm.lin_vel_err(cmd, cmd, limits), 1.0)
        np.testing.assert_allclose(qm.ang_vel_err(np.zeros((2, 3)), np.zeros((2, 3)), limits), 1.0)

    def test_error_is_normalized_by_command_norm(self):
        """上游口径：误差除以 ‖max cmd‖ —— 所以同样的偏差，指令范围越大扣得越少。"""

        cmd = np.tile([1.0, 0.0, 0.0], (1, 1))
        offset = np.array([[1.1, 0.0, 0.0]])
        small = qm.lin_vel_err(offset, cmd, np.array([1.0, 0.0, 0.0]))
        large = qm.lin_vel_err(offset, cmd, np.array([10.0, 0.0, 0.0]))
        self.assertAlmostEqual(0.9, float(small[0]), places=6)
        self.assertAlmostEqual(0.99, float(large[0]), places=6)


class DofMetricTest(unittest.TestCase):
    def test_limits_penalize_only_outside_soft_range(self):
        limits = np.array([[-1.0, 1.0]])
        self.assertAlmostEqual(1.0, float(qm.dof_limits(np.array([[0.0]]), limits)[0]), places=9)
        # 软限位 = ±(1 - 0.9)/2 × range = ±0.9；0.95 超出 0.05 ⇒ /range(2) = 0.025 ⇒ 1-0.025
        self.assertAlmostEqual(0.975, float(qm.dof_limits(np.array([[0.95]]), limits)[0]), places=9)

    def test_power_penalizes_rms_times_scaling(self):
        torque = np.full((1, 2), 10.0)
        velocity = np.full((1, 2), 3.0)
        # |τ·v| = 30 ⇒ RMS 30 ⇒ 1 - 30/100
        self.assertAlmostEqual(0.7, float(qm.dof_power(torque, velocity)[0]), places=6)


class StabilityMetricTest(unittest.TestCase):
    def test_orientation_uses_the_shared_gravity_projection(self):
        """直立 1.0；侧倾 30° ⇒ 1 - |sin30| = 0.5（这条钉住"不另写一份重力投影"）。"""

        upright = np.array([[1.0, 0.0, 0.0, 0.0]])
        roll30 = np.array([[np.cos(np.pi / 12), np.sin(np.pi / 12), 0.0, 0.0]])
        self.assertAlmostEqual(1.0, float(qm.orientation_stability(upright)[0]), places=6)
        self.assertAlmostEqual(0.5, float(qm.orientation_stability(roll30)[0]), places=6)

    def test_torque_smoothness(self):
        constant = np.ones((4, 2))
        np.testing.assert_allclose(qm.torque_smoothness(constant), 1.0)
        # 每步 τ 变化 30 ⇒ RMS(Δτ)=30 ⇒ 1 - 30/30 = 0（首步恒为 1.0）
        ramp = np.array([[0.0], [30.0], [60.0]])
        values = qm.torque_smoothness(ramp)
        self.assertEqual(1.0, float(values[0]))
        np.testing.assert_allclose(values[1:], 0.0, atol=1e-9)


class FrictionMarginTest(unittest.TestCase):
    def test_weighted_average_of_foot_margins(self):
        # 两只足：utilization 0.5 ⇒ margin 0.5；utilization 0 ⇒ margin 1.0，按法向力加权
        normal = [np.array([100.0, 100.0])]
        tangent = [np.array([50.0, 0.0])]
        limit = [np.array([100.0, 100.0])]
        scores, computed = qm.friction_margin(normal, tangent, limit)
        self.assertAlmostEqual(0.75, float(scores[0]), places=6)
        self.assertTrue(computed[0])

    def test_no_contact_scores_one_but_is_marked_not_computed(self):
        """上游口径：算不出来就返回 1.0 —— 但必须标注"没算"，不许冒充真实得分。"""

        scores, computed = qm.friction_margin([np.array([0.0])], [np.array([0.0])], [np.array([0.0])])
        self.assertAlmostEqual(1.0, float(scores[0]), places=9)
        self.assertFalse(computed[0])


class ZmpMarginTest(unittest.TestCase):
    """ZMP 的合成复算：合力竖直、com 在支撑中心 ⇒ ZMP=(0,0) ⇒ 1.0；偏移 0.1 ⇒ 1-0.1/d_norm。"""

    def _inputs(self, com_offset_x: float, d_norm: float = 0.5):
        contact_xy = [np.array([[0.0, 0.0, 0.0]])]
        contact_dist = [np.array([0.0])]
        mass = np.array([10.0])
        inertia = [np.zeros((1, 3, 3))]
        zero = [np.zeros((1, 3))]
        return dict(
            contact_xy=contact_xy, contact_dist=contact_dist,
            com_pos=[np.array([[com_offset_x, 0.0, 0.5]])], mass=mass,
            inertia_world=inertia, body_ang_vel=zero, body_ang_acc=zero, body_lin_acc=zero,
            gravity=np.array([0.0, 0.0, -9.81]), d_norm=d_norm,
        )

    def test_zmp_over_support_center_is_perfect(self):
        scores, computed = qm.zmp_margin(**self._inputs(0.0))
        self.assertAlmostEqual(1.0, float(scores[0]), places=6)
        self.assertTrue(computed[0])

    def test_zmp_offset_reduces_margin_proportionally(self):
        scores, _ = qm.zmp_margin(**self._inputs(0.1, d_norm=0.5))
        self.assertAlmostEqual(0.8, float(scores[0]), places=5)

    def test_no_support_contact_scores_one_without_computing(self):
        inputs = self._inputs(0.0)
        inputs["contact_xy"] = [np.zeros((0, 3))]
        inputs["contact_dist"] = [np.zeros(0)]
        scores, computed = qm.zmp_margin(**inputs)
        self.assertAlmostEqual(1.0, float(scores[0]), places=9)
        self.assertFalse(computed[0])

    def test_unmeasurable_foot_distance_scores_zero(self):
        """上游口径：d_norm 过小（量不出足距）显式返回 0.0，不返回"看起来还行"。"""

        scores, computed = qm.zmp_margin(**self._inputs(0.1, d_norm=0.0))
        self.assertAlmostEqual(0.0, float(scores[0]), places=9)
        self.assertTrue(computed[0])


class RealRunTest(unittest.TestCase):
    """真跑：MuJoCo 信号 → 八指标 → 质量分 → 报告（缺适配器 venv 即跳过）。"""

    @classmethod
    def setUpClass(cls):
        cls.venv = Path("/opt/legged-studio/mjlab-cpu/.venv/bin/python")
        if not cls.venv.is_file():
            raise unittest.SkipTest(f"适配器 venv 不在：{cls.venv}")
        probe = subprocess.run([str(cls.venv), "-c", "import mujoco, onnxruntime"], capture_output=True, text=True)
        if probe.returncode != 0:
            raise unittest.SkipTest("适配器 venv 里没有 mujoco/onnxruntime")
        if not (ROOT / "assets" / "robots" / "zex-w" / "simulation" / "config.json").is_file():
            raise unittest.SkipTest("没有 zex-w 包")

    def test_eight_metrics_and_report_schema(self):
        report = qm.evaluate(
            package_dir=ROOT / "assets" / "robots" / "zex-w",
            policy_id="zex-w-rough-9600",
            steps=40,
            thresholds={"quality_score": 0.5},
        )
        self.assertEqual(qm.REPORT_SCHEMA, report["schema"])
        self.assertEqual(sorted(qm.QUALITY_WEIGHTS), sorted(report["metrics"]))
        for name, value in report["metrics"].items():
            self.assertTrue(0.0 <= value <= 1.0, f"{name}={value}")
        self.assertGreater(report["quality_score"], 0.5, report["metrics"])
        self.assertTrue(report["ok"], report["blockers"])
        self.assertGreater(report["d_norm"], 0.0, "足距对角长量不出来 ⇒ 足端几何派生有问题")

    def test_threshold_blocks_below_the_bar(self):
        report = qm.evaluate(
            package_dir=ROOT / "assets" / "robots" / "zex-w",
            policy_id="zex-w-rough-9600",
            steps=10,
            thresholds={"quality_score": 0.999},
        )
        self.assertFalse(report["ok"])
        self.assertTrue(report["blockers"])


if __name__ == "__main__":
    unittest.main()


class TierLogicTest(unittest.TestCase):
    """四档的**判据与汇总**用假 evaluate 复算（真跑另见 RealRunTest）。

    分开测的理由：四档错的地方通常不是指标算错，而是判据/汇总错（阈值方向、停在哪层、
    中位数还是均值）——那部分不需要仿真就能钉死。
    """

    def setUp(self):
        self._real = qm.evaluate
        self.calls: list[tuple] = []

    def tearDown(self):
        qm.evaluate = self._real

    def _fake(self, score_by_cmd):
        def fake(**kwargs):
            command = tuple(kwargs.get("cmd") or (0.4, 0.0, 0.0))
            self.calls.append(command)
            score = score_by_cmd(command, len(self.calls))
            return {
                "schema": "quality-report-1.0", "tier": "single",
                "package": "/tmp/pkg", "policy": {"id": "demo"},
                "cmd": list(command), "steps": kwargs.get("steps", 1),
                "metrics": {name: score for name in qm.QUALITY_WEIGHTS},
                "quality_score": score, "skipped": [], "ok": True, "blockers": [],
            }
        return fake

    def test_level_passes_when_success_mean_reaches_bar(self):
        qm.evaluate = self._fake(lambda cmd, index: 0.9)
        report = qm.run_level(package_dir="/tmp/pkg", policy_id="demo", magnitudes=[0.5, 1.0], steps=1)
        self.assertEqual(2, len(report["levels"]))
        self.assertTrue(report["ok"])
        self.assertFalse(report["stopped_early"])
        self.assertAlmostEqual(1.0, report["levels"][0]["success_mean"])

    def test_level_stops_at_first_failure(self):
        """上游同款：遇到不过的层就停，**后面的层没跑不假装跑过**。"""

        qm.evaluate = self._fake(lambda cmd, index: 0.9 if index <= 2 else 0.1)
        report = qm.run_level(package_dir="/tmp/pkg", policy_id="demo",
                              magnitudes=[0.5, 1.0, 2.0], steps=1, success_threshold=0.5)
        self.assertFalse(report["ok"])
        self.assertTrue(report["stopped_early"])
        self.assertEqual(2, len(report["levels"]), "第二层不过就应该停，不该继续跑第三层")
        self.assertFalse(report["levels"][-1]["passed"])

    def test_stress_uses_median_per_condition_and_mean_as_benchmark(self):
        # 第 1 次调用是探针（只为拿 scale），随后三次是本条件的重跑 ⇒ 中位数 0.8
        values = {1: 0.5, 2: 0.1, 3: 0.9, 4: 0.8}
        qm.evaluate = self._fake(lambda cmd, index: values[index])
        report = qm.run_stress(package_dir="/tmp/pkg", policy_id="demo",
                               conditions={"only": [0.4, 0.0, 0.0]}, steps=1, repeats=3)
        self.assertAlmostEqual(0.8, report["scores"]["only"], places=6)
        self.assertAlmostEqual(0.8, report["benchmark_score"], places=6)
        self.assertIn("only", report["robust_score"])
        self.assertIn("var", report["robust_score"]["only"]["dof_limits"])

    def test_multi_aggregates_mean_and_min(self):
        values = iter([0.9, 0.3])
        qm.evaluate = self._fake(lambda cmd, index: next(values))
        report = qm.run_multi(package_dir="/tmp/pkg", policies=[{"policy_id": "demo"}],
                              commands=[[0.4, 0.0, 0.0], [0.2, 0.0, 0.0]], steps=1)
        self.assertEqual(2, report["count"])
        self.assertAlmostEqual(0.6, report["aggregate"]["mean"], places=6)
        self.assertAlmostEqual(0.3, report["aggregate"]["min"], places=6)

    def test_unknown_tier_is_rejected(self):
        with self.assertRaises(ValueError):
            qm.run_tier("nope", package_dir="/tmp/pkg")


class QualityGateTest(unittest.TestCase):
    """放行判据：**没有报告不算过**（未评测 ≠ 达标）。"""

    def test_missing_report_blocks(self):
        from backend import quality_matrix

        verdict = quality_matrix.gate(None, min_score=0.5)
        self.assertFalse(verdict["ok"])
        self.assertIn("没有质量报告", verdict["blockers"][0])

    def test_below_threshold_blocks(self):
        from backend import quality_matrix

        verdict = quality_matrix.gate({"tier": "single", "quality_score": 0.31, "ok": False}, min_score=0.5)
        self.assertFalse(verdict["ok"])
        self.assertTrue(any("0.31" in blocker for blocker in verdict["blockers"]))

    def test_stress_and_level_use_their_own_representative_score(self):
        from backend import quality_matrix

        self.assertAlmostEqual(0.88, quality_matrix.score_of({"tier": "stress", "benchmark_score": 0.88}))
        level = {"tier": "level", "levels": [{"passed": True}, {"passed": False}, {"passed": True}, {"passed": True}]}
        self.assertAlmostEqual(0.75, quality_matrix.score_of(level))

    def test_report_roundtrip(self):
        import json
        import tempfile

        from backend import quality_matrix

        with tempfile.TemporaryDirectory() as tmp:
            path = quality_matrix.save_report(
                {"tier": "single", "package": "/tmp/assets/robots/demo", "policy": {"id": "p"},
                 "quality_score": 0.9, "ok": True},
                directory=Path(tmp),
            )
            self.assertTrue(path.is_file())
            self.assertEqual("demo", json.loads(path.read_text(encoding="utf-8"))["package"].split("/")[-1])
            listed = quality_matrix.list_reports(directory=Path(tmp))
            self.assertEqual(1, len(listed))
            self.assertAlmostEqual(0.9, listed[0]["quality_score"])
