"""H20 指令仲裁纯函数 —— 判据原文：单测覆盖「超时→停 / 非有限值→拒 / 死区→置零」。

另加定义列要求的模式仲裁、急停 latch、STAND/WALK 门控。全部纯函数、无 I/O、
无真机依赖，可离线全绿。
"""

import unittest

from backend import command_arbiter as ca


def _cmd(vx=0.0, vy=0.0, yaw_rate=0.0):
    return {"vx": vx, "vy": vy, "yaw_rate": yaw_rate}


class ParseModeTest(unittest.TestCase):
    def test_case_insensitive_and_unknown_falls_back_to_disabled(self):
        self.assertEqual("REMOTE", ca.parse_mode("remote"))
        self.assertEqual("NAV", ca.parse_mode("Nav"))
        self.assertEqual("DISABLED", ca.parse_mode("garbage"))
        self.assertEqual("DISABLED", ca.parse_mode(None))


class ArbitrateTest(unittest.TestCase):
    def test_fresh_source_is_selected(self):
        result = ca.arbitrate_command(
            mode="REMOTE",
            sources={"remote": {"command": _cmd(0.5, 0.0, 0.0), "age_ms": 100}},
        )
        self.assertTrue(result["accepted"])
        self.assertEqual("remote", result["source"])
        self.assertEqual(0.5, result["command"]["vx"])

    def test_timeout_stops(self):
        """**判据① 超时→停**：remote age 300 > 250 阈值 → 零输出，accepted 仍为 True。"""
        result = ca.arbitrate_command(
            mode="REMOTE",
            sources={"remote": {"command": _cmd(0.5), "age_ms": 300}},
        )
        self.assertTrue(result["accepted"], "超时是安全停，不是拒绝")
        self.assertEqual({"vx": 0.0, "vy": 0.0, "yaw_rate": 0.0}, result["command"])
        self.assertIn("超时", " ".join(result["reasons"]))

    def test_timeout_boundary_is_still_fresh(self):
        """age_ms == 250 恰好等于阈值 → 仍新鲜（与上游 is_fresh 的 ≤ 一致）。"""
        result = ca.arbitrate_command(
            mode="REMOTE",
            sources={"remote": {"command": _cmd(0.5), "age_ms": 250}},
        )
        self.assertEqual("remote", result["source"])

    def test_non_finite_rejected(self):
        """**判据② 非有限值→拒**：NaN 指令 → accepted=False。"""
        result = ca.arbitrate_command(
            mode="REMOTE",
            sources={"remote": {"command": _cmd(float("nan")), "age_ms": 10}},
        )
        self.assertFalse(result["accepted"])
        self.assertIsNone(result["command"])

    def test_deadzone_zeroes(self):
        """**判据③ 死区→置零**：小指令经 H9 死区（teleop min_effective 0.22）置零。"""
        result = ca.arbitrate_command(
            mode="REMOTE",
            sources={"remote": {"command": _cmd(0.1), "age_ms": 10}},
        )
        self.assertTrue(result["accepted"])
        self.assertEqual(0.0, result["command"]["vx"])

    def test_estop_latches_to_disabled(self):
        """急停 latch：即使传 REMOTE，mode_effective 也落到 DISABLED 且零输出。"""
        result = ca.arbitrate_command(
            mode="REMOTE",
            estop=True,
            sources={"remote": {"command": _cmd(0.5), "age_ms": 10}},
        )
        self.assertEqual("DISABLED", result["mode_effective"])
        self.assertEqual("estop", result["source"])
        self.assertEqual({"vx": 0.0, "vy": 0.0, "yaw_rate": 0.0}, result["command"])

    def test_robot_mode_gate(self):
        """STAND/WALK 之外（如 SIT）禁止行走。"""
        result = ca.arbitrate_command(
            mode="REMOTE",
            robot_mode="SIT",
            sources={"remote": {"command": _cmd(0.5), "age_ms": 10}},
        )
        self.assertEqual("stand", result["source"])
        self.assertEqual({"vx": 0.0, "vy": 0.0, "yaw_rate": 0.0}, result["command"])

    def test_mode_priority_ignores_other_sources(self):
        """WEB 模式只选 web 源，忽略新鲜的 remote。"""
        result = ca.arbitrate_command(
            mode="WEB",
            sources={
                "remote": {"command": _cmd(0.9), "age_ms": 10},
                "web": {"command": _cmd(0.3), "age_ms": 10},
            },
        )
        self.assertEqual("web", result["source"])
        self.assertEqual(0.3, result["command"]["vx"])

    def test_disabled_mode_is_zero(self):
        result = ca.arbitrate_command(mode="DISABLED")
        self.assertEqual("disabled", result["source"])
        self.assertEqual({"vx": 0.0, "vy": 0.0, "yaw_rate": 0.0}, result["command"])

    def test_keep_mode_is_zero(self):
        result = ca.arbitrate_command(mode="KEEP")
        self.assertEqual("keep", result["source"])
        self.assertEqual({"vx": 0.0, "vy": 0.0, "yaw_rate": 0.0}, result["command"])

    def test_disabled_source_is_not_selected(self):
        """enabled.remote=False → 即使新鲜也落零。"""
        result = ca.arbitrate_command(
            mode="REMOTE",
            enabled={"remote": False},
            sources={"remote": {"command": _cmd(0.5), "age_ms": 10}},
        )
        self.assertEqual("zero", result["source"])
        self.assertEqual({"vx": 0.0, "vy": 0.0, "yaw_rate": 0.0}, result["command"])
        self.assertIn("未使能", " ".join(result["reasons"]))

    def test_missing_source_is_treated_as_timeout(self):
        result = ca.arbitrate_command(mode="REMOTE", sources={})
        self.assertEqual("zero", result["source"])
        self.assertIn("从未收到数据", " ".join(result["reasons"]))

    def test_nav_uses_500ms_timeout(self):
        result = ca.arbitrate_command(
            mode="NAV",
            sources={"nav": {"command": _cmd(0.4), "age_ms": 400}},
        )
        self.assertEqual("nav", result["source"], "nav 超时 500ms，400ms 应仍新鲜")

    def test_slew_limit_applied_when_previous_and_dt_given(self):
        result = ca.arbitrate_command(
            mode="REMOTE",
            sources={"remote": {"command": _cmd(1.0), "age_ms": 10}},
            previous=_cmd(0.0),
            dt=0.1,
        )
        self.assertTrue(result["accepted"])
        # teleop accel 1.0 → 单步 0.1 最多 +0.1
        self.assertAlmostEqual(0.1, result["command"]["vx"], places=6)


if __name__ == "__main__":
    unittest.main()
