"""高度判据的**尺子**：声明优先，内置例外降级为带标注的兜底。

背景（2026-09-14）：`lite3-velocity-benchmark` / `lite3-velocity-sdk45` 稳定站立、不摔、
跟踪误差 0.028，唯一不过的是**高度比 0.692**。我当时误判为"增益错"，去改了物理常量
（MJCF kp 30→60），被三处测试挡下并回滚 —— 真问题是**尺子**：判据拿"默认关节角的运动学
高度"当参考，而那不是策略的自然站姿。

教训落成机制：**尺子必须随结论一起给出**，且例外必须是**声明**（数据），不是代码里的名单。
"""

import unittest

from tools.sweep_policy_availability import resolve_height_ruler


class RulerResolutionTest(unittest.TestCase):
    """``resolve_height_ruler`` 的优先级：声明 > 内置例外 > 引擎现算。"""

    @staticmethod
    def _declaration(policy_id: str, **contract) -> dict:
        return {"policy_id": policy_id, "robot": "unitree_go2", "contract": dict(contract)}

    def test_default_is_engine_computed_static_default_pose(self):
        ruler = resolve_height_ruler(self._declaration("go2-velocity"), family="velocity")
        self.assertEqual("static_default_pose", ruler["ruler"])
        self.assertEqual("engine", ruler["source"])
        self.assertIsNone(ruler["ref_height_m"])

    def test_declared_expected_height_wins_and_carries_the_value(self):
        """显式声明期望稳态高度 —— 数据即真值，且**数值随结论一起给出**。"""
        ruler = resolve_height_ruler(
            self._declaration("lite3-velocity", expected_steady_height_m=0.20), family="velocity",
        )
        self.assertEqual("declared", ruler["ruler"])
        self.assertEqual("declaration", ruler["source"])
        self.assertAlmostEqual(0.20, ruler["ref_height_m"], places=6)

    def test_declared_self_stability_disables_height_gate(self):
        ruler = resolve_height_ruler(
            self._declaration("go2w-himloco-handstand", steady_height_policy="self_stability"),
            family="balance",
        )
        self.assertEqual("self_stability", ruler["ruler"])
        self.assertEqual("declaration", ruler["source"])
        self.assertIsNone(ruler["ref_height_m"])

    def test_there_is_no_code_level_exception_list(self):
        """代码里已无例外名单：**没有声明就回落引擎**（不再按 policy_id 偷偷放行）。

        2026-09-14 收尾：原 `SELF_STABILITY_ONLY` 已删除，非标准站姿一律由声明表达。
        """
        ruler = resolve_height_ruler(self._declaration("go2w-himloco-leggedstand"), family="balance")
        self.assertEqual("static_default_pose", ruler["ruler"])
        self.assertEqual("engine", ruler["source"])

    def test_real_repo_expresses_nonstandard_stance_by_declaration(self):
        """**真实仓不变量**：非标准站姿（前/后腿站立、低站姿）一律由**声明**表达。

        这条一旦红，说明例外又被写回了代码，或某条策略漏了声明。
        """
        from backend import policy_artifacts as pa

        rulers = {
            d["policy_id"]: resolve_height_ruler(d, family="balance")
            for d in pa.scan_declarations()
        }
        expected = (
            "go2w-himloco-stand-front", "go2w-himloco-leggedstand",
            "lite3-velocity-benchmark", "lite3-velocity-sdk45",
        )
        for policy_id in expected:
            with self.subTest(policy=policy_id):
                self.assertEqual("self_stability", rulers[policy_id]["ruler"])
                self.assertEqual("declaration", rulers[policy_id]["source"])

    def test_zero_or_invalid_declared_height_falls_through(self):
        """声明值非法（0 / 负数 / 字符串）→ 回落，不得当成"参考高度 0"（那会让高度比爆表）。"""
        for value in (0, -1.0, "0.2"):
            with self.subTest(declared=value):
                ruler = resolve_height_ruler(
                    self._declaration("go2-velocity", expected_steady_height_m=value),
                    family="velocity",
                )
                self.assertEqual("static_default_pose", ruler["ruler"])
                self.assertEqual("engine", ruler["source"])


class HeadlessCriteriaTest(unittest.TestCase):
    """判据侧：声明的参考高度进 `criteria` 后必须**优先于**引擎现算值，且结论带 `ruler`。"""

    def test_declared_ref_beats_engine_ref_and_labels_ruler(self):
        from tools.sim2sim_headless import evaluate_mode

        class _Contract:
            initial_height = 0.30

        metrics = {"survival_ratio": 1.0, "height_steady": 0.20, "roll_steady_max_deg": 3.0,
                   "pitch_steady_max_deg": 4.0, "vel_track_err": 0.02, "command": [0.0, 0.0, 0.0]}
        criteria = {"survival_min": 0.999, "height_ratio_min": 0.85, "tilt_max_deg": 20.0,
                    "vel_err_max": 0.2, "height_ref_m": 0.20, "height_ruler": "declared"}

        result = evaluate_mode(metrics, "stand", _Contract(), criteria, ref_height=0.289)
        check = next(c for c in result["checks"] if c["name"] == "height_ratio_steady")
        self.assertEqual("declared", check["ruler"])      # 声明的尺子赢了引擎的 0.289
        self.assertAlmostEqual(0.20, check["ref_height"], places=3)
        self.assertAlmostEqual(1.0, check["value"], places=3)
        self.assertTrue(check["ok"])

    def test_engine_ref_is_labelled_when_nothing_declared(self):
        """没声明时用引擎尺子 —— 但**标注出来**，不再是无名的隐式基准。"""
        from tools.sim2sim_headless import evaluate_mode

        class _Contract:
            initial_height = 0.30

        metrics = {"survival_ratio": 1.0, "height_steady": 0.20, "roll_steady_max_deg": 3.0,
                   "pitch_steady_max_deg": 4.0, "vel_track_err": 0.02, "command": [0.0, 0.0, 0.0]}
        criteria = {"survival_min": 0.999, "height_ratio_min": 0.85, "tilt_max_deg": 20.0,
                    "vel_err_max": 0.2}

        result = evaluate_mode(metrics, "stand", _Contract(), criteria, ref_height=0.289)
        check = next(c for c in result["checks"] if c["name"] == "height_ratio_steady")
        self.assertEqual("static_default_pose", check["ruler"])
        self.assertFalse(check["ok"])                     # 0.692 < 0.85 —— 且现在知道跟谁比


if __name__ == "__main__":
    unittest.main()
