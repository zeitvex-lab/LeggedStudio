"""H12：跟随状态机 + 卡死恢复 + 终止原因分层测试。

守什么：

1. **参数只有一个来源**：跟随参数取 `registry/motion_commands.json#follow_controller`
   （与参考实现 `nav_route_sim2sim_check.py::SimConfig` 逐字段对齐），缺块即报错；
   到达容差/稳定拍数取 `registry/arrival_criteria.json`（H10）——两处都不许有代码默认值；
2. **控制器律对齐参考实现**：cos 门控前进（`|yaw_err| ≤ 45°` 才给 vx）、
   大误差原地转（70° 进 / 18° 出，滞回）；
3. **三类判据**：`complete`（走完）/ `timeout`（单航点超时）/ `stuck`（恢复用尽），
   且**恢复动作真的发得出来**（vx<0、wz≠0、符号翻转）；
4. **终止原因分层（抄 LightNav）**：`truncated`（预算拉停）与 `undefined` **不是策略结论**
   （`details.is_strategy_verdict == False`），不许与 `stuck/timeout` 混为一谈；
5. **卡死进展按"目标导向运动"登记（v0.55.46 收口第 2 条裁决）**：拐角航向差 90°+ 的
   原地急转/切角追赶**不得误触恢复动作**（进展 = 到前视目标距离缩短，或 turn_in_place
   期间航向误差收敛 ≥ stuck_turn_progress_deg）；被夹住（位置与朝向全冻结）的真卡死
   **仍必须触发**恢复直至 stuck——急转豁免不许吞掉真卡死。
"""

from __future__ import annotations

import math
import unittest
from dataclasses import replace
from unittest import mock

from backend.follow_controller import FollowController, FollowParams, follow_controller_selftest, normalize_angle
from backend.motion_commands import follow_controller_spec

DT = 0.02


def _simulate(controller: FollowController, *, start=(0.0, 0.0, 0.0), freeze=False, max_steps=4000, yaw_efficiency=1.0):
    """按控制周期推进：默认把 cmd 积分为位姿变化（简单单车积分）；freeze=True 模拟卡住不动。

    yaw_efficiency < 1 模拟真机转向跟踪滞后（指令 wz 只兑现一部分——浏览器实测 180°
    原地急转的无位移时长因此超过 stuck_timeout_s，是误触卡死的现场）。
    """
    x, y, yaw = start
    t = 0.0
    steps = []
    for _ in range(max_steps):
        step = controller.update([x, y, yaw], t)
        steps.append(step)
        if step.termination_reason:
            break
        if not freeze:
            x += step.cmd[0] * math.cos(yaw) * DT
            y += step.cmd[0] * math.sin(yaw) * DT
            yaw = normalize_angle(yaw + step.cmd[2] * yaw_efficiency * DT)
        t += DT
    return steps, x, y, yaw, t


class FollowParamsTests(unittest.TestCase):
    def test_params_come_from_registry_and_match_reference(self):
        params = FollowParams.from_registry()
        spec = follow_controller_spec()
        self.assertEqual(params.lookahead_m, 0.45)
        self.assertEqual(params.kp_dist, 0.8)
        self.assertEqual(params.kp_yaw, 1.8)
        self.assertEqual(params.turn_in_place_enter_deg, 70.0)
        self.assertEqual(params.turn_in_place_exit_deg, 18.0)
        self.assertEqual(params.stuck_timeout_s, 4.0)
        self.assertEqual(params.stuck_turn_progress_deg, 15.0)
        self.assertEqual(params.max_recoveries, 4)
        self.assertEqual(params.recovery_vx_factor, -0.10)
        self.assertEqual(params.recovery_wz_factor, 0.45)
        # 注册表与数据类不得漂移：逐字段对拍
        for field, key in (
            ("lookahead_m", "lookahead_m"), ("max_vx", "max_vx"), ("kp_dist", "kp_dist"),
            ("kp_yaw", "kp_yaw"), ("max_wz", "max_wz"), ("stuck_timeout_s", "stuck_timeout_s"),
            ("stuck_turn_progress_deg", "stuck_turn_progress_deg"),
        ):
            with self.subTest(field=field):
                self.assertEqual(getattr(params, field), spec[key])

    def test_missing_block_raises_instead_of_defaulting(self):
        with mock.patch("backend.motion_commands.follow_controller_spec", return_value={}):
            with self.assertRaises(ValueError) as ctx:
                FollowParams.from_registry()
        self.assertIn("follow_controller", str(ctx.exception))

    def test_missing_field_raises_and_names_it(self):
        spec = dict(follow_controller_spec())
        spec.pop("kp_yaw")
        with mock.patch("backend.motion_commands.follow_controller_spec", return_value=spec):
            with self.assertRaises(ValueError) as ctx:
                FollowParams.from_registry()
        self.assertIn("kp_yaw", str(ctx.exception))

    def test_arrival_spec_still_comes_from_h10(self):
        from backend.arrival_criteria import waypoint_spec

        controller = FollowController([[0.0, 0.0], [1.0, 0.0]])
        self.assertEqual(controller.stable_ticks, int(waypoint_spec()["stable_ticks"]))
        self.assertEqual(controller.tolerances[1], float(waypoint_spec()["tolerance_m"]))


class FollowLawTests(unittest.TestCase):
    def test_straight_line_runs_to_completion(self):
        from backend.arrival_criteria import waypoint_spec

        controller = FollowController([[0.0, 0.0], [2.0, 0.0]])
        steps, x, _, _, _ = _simulate(controller)
        verdict = controller.verdict()
        self.assertEqual(verdict["verdict"], "pass")
        self.assertEqual(verdict["termination_reason"], "complete")
        # 停在 H10 容差带内即算到达（不是"必须压到点上"）
        tolerance = float(waypoint_spec()["tolerance_m"])
        self.assertGreaterEqual(x, 2.0 - tolerance - 1e-6, f"应停在容差带内（x={x:.3f}, 容差={tolerance}）")
        events = [step.event for step in steps]
        # 两个航点的航线没有中间段 ⇒ 直接 complete；有中间航点时必须出现 advance
        self.assertTrue(any(event in ("advance", "complete") for event in events), events[:5])
        self.assertEqual(verdict["recoveries_used"], 0)

    def test_small_yaw_error_still_moves_forward_with_cos_gate(self):
        controller = FollowController([[0.0, 0.0], [2.0, 0.0], [4.0, 0.0]])
        # 目标在正前方、朝向偏 0.3 rad（<45°）⇒ 给前进速度
        step = controller.update([0.0, 0.0, 0.3], 0.0)
        self.assertGreater(step.cmd[0], 0.0)
        self.assertEqual(step.state, "following")
        # 偏到 80°（>70°）⇒ 原地转，不给前进
        step = controller.update([0.0, 0.0, math.radians(80)], 0.02)
        self.assertEqual(step.state, "turn_in_place")
        self.assertEqual(step.cmd[0], 0.0)
        self.assertLess(step.cmd[2], 0.0, "目标在右侧 ⇒ 右转")

    def test_turn_in_place_hysteresis(self):
        controller = FollowController([[0.0, 0.0], [2.0, 0.0], [4.0, 0.0]])
        controller.update([0.0, 0.0, math.radians(80)], 0.0)   # 进入原地转（>70°）
        self.assertTrue(controller.turn_in_place)
        controller.update([0.0, 0.0, math.radians(30)], 0.02)  # 30° 在 18°~70° 之间 ⇒ 保持
        self.assertTrue(controller.turn_in_place, "滞回区间内不应退出")
        controller.update([0.0, 0.0, math.radians(10)], 0.04)  # ≤18° ⇒ 退出
        self.assertFalse(controller.turn_in_place)

    def test_yaw_rate_is_clamped_to_max_wz(self):
        controller = FollowController([[0.0, 0.0], [2.0, 0.0], [4.0, 0.0]])
        params = controller.params
        step = controller.update([0.0, 0.0, math.radians(60)], 0.0)
        self.assertLessEqual(abs(step.cmd[2]), params.max_wz + 1e-9)


class CornerProgressTests(unittest.TestCase):
    """v0.55.46 收口第 2 条：拐角急转不误触卡死恢复；被夹住的真卡死仍触发。

    误触机理（改前实测）：拐角航向差大 ⇒ 前视目标切到下一段 ⇒ 原地转/切角后机器人
    追的是新方向，而**当前航点在身后**——按旧口径（到当前航点的距离）4s 无进展 ⇒
    误发恢复动作（135° 拐角首轮实测 5.88s 触发、180° 折返 30s 内烧光 4 轮判 stuck）。
    """

    def test_sharp_corner_waypoint_registers_pursuit_progress(self):
        """航向差 135° 的拐角航点：切角追赶前视目标算进展，不得误发恢复动作。"""
        controller = FollowController([[0.0, 0.0], [2.0, 0.0], [0.0, 2.0]])
        steps, *_ = _simulate(controller)
        self.assertEqual(
            [s for s in steps if s.event == "recovery"],
            [],
            "拐角切角追赶前视目标是进展，不得误触恢复动作",
        )
        verdict = controller.verdict()
        self.assertEqual(verdict["recoveries_used"], 0)
        # 切角几何上绕过了当前航点（H12 已登记的"lookahead 0.45 拐角切角"短板，
        # 此前被误触卡死的挣扎掩盖）⇒ 终止是**航点超时**（策略结论），不是卡死——
        # 终止原因分层不得因卡死口径修正而混淆。
        self.assertEqual(verdict["termination_reason"], "timeout")
        self.assertEqual(verdict["verdict"], "fail")
        self.assertTrue(verdict["details"]["is_strategy_verdict"])

    def test_fold_back_slow_pivot_beyond_stuck_window_keeps_rotating(self):
        """180° 折返 + 转向跟踪打折（0.5×，真机滞后现场）：原地转远超 4s 不得误触恢复。"""
        controller = FollowController([[0.0, 0.0], [2.0, 0.0], [0.5, 0.0]])
        steps, *_ = _simulate(controller, yaw_efficiency=0.5)
        self.assertEqual(
            [s for s in steps if s.event == "recovery"],
            [],
            "180° 慢速原地转：航向误差持续收敛 ⇒ 进展，不得误触恢复动作",
        )
        self.assertEqual(controller.verdict()["recoveries_used"], 0)
        states = {s.state for s in steps}
        self.assertIn("turn_in_place", states, "用例本身必须经过原地转阶段（否则没测到目标分支）")

    def test_true_stuck_while_turning_still_triggers_recovery(self):
        """航向差 130° ⇒ 持续发原地转指令，但位姿全冻结（被夹住转不动）⇒ 必须恢复。"""
        controller = FollowController([[0.0, 0.0], [2.0, 0.0], [0.0, 2.0]])
        steps, *_ = _simulate(controller, start=(1.7, 0.0, 0.0), freeze=True)
        recoveries = [s for s in steps if s.event == "recovery"]
        self.assertTrue(recoveries, "朝向冻住的真卡死必须触发恢复（急转豁免不许吞掉它）")
        self.assertLess(recoveries[0].cmd[0], 0.0, "恢复动作应后退")
        self.assertNotEqual(recoveries[0].cmd[2], 0.0, "恢复动作应转向以脱困")
        verdict = controller.verdict()
        self.assertEqual(verdict["termination_reason"], "stuck")
        self.assertEqual(verdict["verdict"], "fail")


class VerdictTests(unittest.TestCase):
    def test_stuck_triggers_recovery_then_stuck_verdict(self):
        controller = FollowController([[0.0, 0.0], [5.0, 0.0]])
        steps, *_ = _simulate(controller, freeze=True)
        recoveries = [step for step in steps if step.event == "recovery"]
        self.assertTrue(recoveries, "卡死必须发出恢复动作")
        self.assertLess(recoveries[0].cmd[0], 0.0, "恢复动作应后退")
        self.assertNotEqual(recoveries[0].cmd[2], 0.0, "恢复动作应转向以脱困")
        signs = {step.cmd[2] > 0 for step in recoveries}
        self.assertEqual(len(signs), 2, "恢复转向符号应逐轮翻转")
        verdict = controller.verdict()
        self.assertEqual(verdict["termination_reason"], "stuck")
        self.assertEqual(verdict["verdict"], "fail")
        self.assertLessEqual(verdict["recoveries_used"], controller.params.max_recoveries)

    def test_waypoint_timeout_isolated_from_stuck(self):
        params = replace(FollowParams.from_registry(), stuck_timeout_s=10_000.0, max_total_time_s=10_000.0)
        controller = FollowController([[0.0, 0.0], [3.0, 0.0]], params=params)
        # 不动的机器人 ⇒ 只有航点超时会触发（卡死已被参数隔离）
        steps, *_ = _simulate(controller, freeze=True, max_steps=4000)
        self.assertEqual(controller.verdict()["termination_reason"], "timeout")
        self.assertTrue(any(step.event == "timeout" for step in steps))

    def test_total_time_budget_is_truncation_not_strategy_failure(self):
        params = replace(FollowParams.from_registry(), max_total_time_s=1.0, stuck_timeout_s=10_000.0)
        controller = FollowController([[0.0, 0.0], [9.0, 0.0]], params=params)
        _simulate(controller, max_steps=200)
        verdict = controller.verdict()
        self.assertEqual(verdict["termination_reason"], "truncated")
        self.assertEqual(verdict["verdict"], "partial")
        self.assertFalse(verdict["details"]["is_strategy_verdict"], "预算拉停不是策略结论")

    def test_untouched_controller_is_undefined(self):
        verdict = FollowController([[0.0, 0.0], [1.0, 0.0]]).verdict()
        self.assertEqual(verdict["termination_reason"], "undefined")
        self.assertFalse(verdict["details"]["is_strategy_verdict"])

    def test_route_completion_and_counts_are_reported(self):
        controller = FollowController([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]])
        _simulate(controller)
        verdict = controller.verdict()
        self.assertEqual(verdict["waypoints_total"], 2)
        self.assertEqual(verdict["waypoints_reached"], 2)
        self.assertEqual(verdict["route_completion"], 1.0)

    def test_after_termination_commands_are_zero(self):
        controller = FollowController([[0.0, 0.0], [1.0, 0.0]])
        _simulate(controller)
        step = controller.update([0.0, 0.0, 0.0], 99.0)
        self.assertEqual(step.cmd, [0.0, 0.0, 0.0])
        self.assertEqual(step.state, "done")


class SelftestTests(unittest.TestCase):
    def test_selftest_walks_a_route(self):
        report = follow_controller_selftest()
        self.assertEqual(report["termination_reason"], "complete")
        self.assertEqual(report["verdict"], "pass")
        self.assertEqual(report["params_source"], "registry/motion_commands.json#follow_controller")
        self.assertEqual(report["arrival_source"], "registry/arrival_criteria.json")


if __name__ == "__main__":
    unittest.main()
