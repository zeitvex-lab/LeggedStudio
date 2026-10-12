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
   **仍必须触发**恢复直至 stuck——急转豁免不许吞掉真卡死；
6. **接近减速（v0.55.48，修登记短板「0.2m 容差过冲振荡」）**：仅最后一段且距最终航点
   < goal_slowdown_m 时 vx 上限按剩余距离比例收紧（浏览器 navigation.js 同分支同参数）；
   中途航点**不受影响**；极近距离上限不低于 max_vx×goal_slowdown_min_scale（能走完最后
   几十厘米）；**到达判定仍由 arrival_criteria（H10）口径**，减速分支不碰判据。
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
        self.assertEqual(params.goal_slowdown_m, 2.4)
        self.assertEqual(params.goal_slowdown_min_scale, 0.2)
        self.assertEqual(params.turn_in_place_enter_deg, 70.0)
        self.assertEqual(params.turn_in_place_exit_deg, 18.0)
        self.assertEqual(params.stuck_timeout_s, 4.0)
        self.assertEqual(params.stuck_turn_progress_deg, 15.0)
        self.assertEqual(params.max_recoveries, 4)
        self.assertEqual(params.recovery_vx_factor, -0.10)
        self.assertEqual(params.recovery_wz_factor, 0.45)
        # 注册表与数据类不得漂移：逐字段对拍
        # （v0.55.50 起 node_consume_proj 不再是服务端参数——切角消费改路径参数边界，
        #  该字段只剩浏览器侧 pursuit 游标一个消费者；见 BypassConsumeTests 的说明）
        for field, key in (
            ("lookahead_m", "lookahead_m"),
            ("max_vx", "max_vx"), ("kp_dist", "kp_dist"),
            ("kp_yaw", "kp_yaw"), ("max_wz", "max_wz"), ("stuck_timeout_s", "stuck_timeout_s"),
            ("stuck_turn_progress_deg", "stuck_turn_progress_deg"),
            ("goal_slowdown_m", "goal_slowdown_m"),
            ("goal_slowdown_min_scale", "goal_slowdown_min_scale"),
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

    def test_missing_slowdown_field_raises_and_names_it(self):
        """接近减速两参数同走 fail-closed（registry 唯一真值，缺了不许静默兜底）。"""
        for key in ("goal_slowdown_m", "goal_slowdown_min_scale"):
            with self.subTest(field=key):
                spec = dict(follow_controller_spec())
                spec.pop(key)
                with mock.patch("backend.motion_commands.follow_controller_spec", return_value=spec):
                    with self.assertRaises(ValueError) as ctx:
                        FollowParams.from_registry()
                self.assertIn(key, str(ctx.exception))

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


class NearGoalSlowdownTests(unittest.TestCase):
    """v0.55.48 接近减速：最后一段按剩余距离比例收紧 vx 上限（浏览器 navigation.js 同分支）。

    修的是 H12 登记短板「0.2m 容差过冲振荡成为到达率瓶颈」（e2e 基线 arrived 1/7）：
    末段匀速冲线 → 过冲 → stable_ticks=2 在容差内攒不上。守四件事：
    减速生效、中途不变、极近不离地（min_scale 地板）、到达判定仍是 H10 口径。
    """

    def test_slowdown_caps_vx_half_meter_from_final_waypoint(self):
        """距终点 0.5m：vx = max_vx·(0.5/2.4) = 0.25 < max_vx（减速生效）。"""
        controller = FollowController([[0.0, 0.0], [2.0, 0.0]])
        step = controller.update([1.5, 0.0, 0.0], 0.0)
        expected_cap = controller.params.max_vx * (0.5 / controller.params.goal_slowdown_m)
        self.assertAlmostEqual(step.cmd[0], expected_cap, places=9)
        self.assertLess(step.cmd[0], controller.params.max_vx)
        self.assertEqual(step.state, "following")

    def test_slowdown_does_not_touch_wz(self):
        """wz 只由 kp_yaw·yaw_err 决定，减速分支不碰它（同位姿、同 yaw_err 对拍）。"""
        controller = FollowController([[0.0, 0.0], [2.0, 0.0]])
        slowed = controller.update([1.5, 0.0, 0.2], 0.0)
        # 同一 yaw_err 放到减速窗口外（把减速距离改小到不生效）取 wz 基准
        wide = replace(controller.params, goal_slowdown_m=0.01)
        baseline = FollowController([[0.0, 0.0], [2.0, 0.0]], params=wide).update([1.5, 0.0, 0.2], 0.0)
        self.assertEqual(slowed.cmd[2], baseline.cmd[2])
        self.assertLess(slowed.cmd[0], baseline.cmd[0], "vx 收紧而 wz 不动 ⇒ 分支只作用在 vx 上限")

    def test_mid_route_following_unchanged(self):
        """中途航点：即使距最终航点已 < goal_slowdown_m 也不减速（门控在活跃航点==最终航点）。

        **v0.55.50 起前视目标 = 弧长点**（游标前方 lookahead 处）⇒ 跟队巡航速度 =
        ``kp_dist·lookahead``（默认 0.36，与浏览器侧密集路径巡航同档），不再是"到远
        航点的距离"。为让"减速门是否误生效"仍可判，用大 kp_dist 让自然律顶到
        max_vx：门控若失效（按距最终航点减速）cap 会把它压到 0.875，一测现形。
        """
        aggressive = replace(FollowParams.from_registry(), kp_dist=5.0)
        # 活跃航点 (0.5,0) 不是最终航点 ⇒ 无减速：自然律 5.0·0.45=2.25 顶满 max_vx。
        controller = FollowController([[0.0, 0.0], [0.5, 0.0], [2.0, 0.0]], params=aggressive)
        step = controller.update([0.25, 0.0, 0.0], 0.0)
        self.assertAlmostEqual(step.cmd[0], controller.params.max_vx, places=9)
        # 默认参数下中途就是巡航速度（不被任何上限压低）
        plain = FollowController([[0.0, 0.0], [0.5, 0.0], [2.0, 0.0]])
        plain_step = plain.update([0.25, 0.0, 0.0], 0.0)
        self.assertAlmostEqual(
            plain_step.cmd[0], plain.params.kp_dist * plain.params.lookahead_m, places=9
        )
        # 最终一段但距终点 ≥ goal_slowdown_m：同样不减速（自然律照发）
        far = FollowController([[0.0, 0.0], [5.0, 0.0]], params=aggressive)
        step_far = far.update([1.0, 0.0, 0.0], 0.0)
        self.assertAlmostEqual(step_far.cmd[0], far.params.max_vx, places=9)

    def test_very_near_goal_cap_floors_at_min_scale(self):
        """极近距离：上限不低于 max_vx·goal_slowdown_min_scale（最后几十厘米走得完）。"""
        controller = FollowController([[0.0, 0.0], [2.0, 0.0]])
        # 距终点 0.4m：0.4/2.4=0.167 < min_scale 0.2 ⇒ 地板生效，cap=0.24；
        # 自然律 0.8·0.4=0.32 > cap ⇒ 观察到的 vx 恰为地板值（无地板会是 0.2）。
        step = controller.update([1.6, 0.0, 0.0], 0.0)
        expected_floor = controller.params.max_vx * controller.params.goal_slowdown_min_scale
        self.assertAlmostEqual(step.cmd[0], expected_floor, places=9)
        self.assertGreater(step.cmd[0], 0.0, "地板保证末段仍有前进指令，不熄火")
        # 更极端：kp_dist 调大让自然律远超地板（d=0.3m ⇒ 自然 1.5 vs 地板 0.24；
        # 取 0.3m 是为了留在 H10 容差 0.2m 之外——容差内是 settling 零指令分支）
        aggressive = replace(controller.params, kp_dist=5.0)
        near = FollowController([[0.0, 0.0], [2.0, 0.0]], params=aggressive)
        step_near = near.update([1.7, 0.0, 0.0], 0.0)
        self.assertAlmostEqual(step_near.cmd[0], expected_floor, places=9)

    def test_arrival_criteria_unchanged_by_slowdown(self):
        """到达判定仍由 arrival_criteria（H10）口径：容差内零指令 settling、判据链路照旧。"""
        from backend.arrival_criteria import waypoint_spec

        controller = FollowController([[0.0, 0.0], [2.0, 0.0]])
        tolerance = float(waypoint_spec()["tolerance_m"])
        # 容差内（1.95m 处，容差 0.2）⇒ 到达判定分支先于减速/跟随律：零指令 settling
        step = controller.update([1.95, 0.0, 0.0], 0.0)
        self.assertEqual(step.cmd, [0.0, 0.0, 0.0])
        self.assertEqual(step.state, "settling")
        # 减速整段仿真：仍按容差带完成（减速不改变"到了没"的判据）
        steps, x, _, _, _ = _simulate(controller)
        self.assertEqual(controller.verdict()["termination_reason"], "complete")
        self.assertGreaterEqual(x, 2.0 - tolerance - 1e-6, f"应停在容差带内（x={x:.3f}）")
        self.assertLess(x, 2.0 + tolerance + 0.05, "减速后不应深冲过终点")


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
        # v0.55.50 前：稀疏长段（2m/2.83m）的 135° 拐点无法消费（双条件判据互斥）⇒
        #     index 停在拐点 ⇒ 前视反复选身后的点 ⇒ 双稳翻转至航点超时（登记病象）。
        # v0.55.50 起：弧长目标贴路径跟踪，135° 拐角**真到达**（advance）⇒ 航线走完。
        self.assertEqual(verdict["termination_reason"], "complete")
        self.assertEqual(verdict["verdict"], "pass")
        self.assertTrue(verdict["details"]["is_strategy_verdict"])
        self.assertIn("advance", {s.event for s in steps}, "135° 拐角须按 H10 真到达")

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


class BypassConsumeTests(unittest.TestCase):
    """v0.55.50 切角消费改**路径参数边界**（H12 登记短板「稀疏长段路径 0.45 边界双稳翻转」收口）。

    **口径变迁**（v0.55.49 → v0.55.50）：消费判据从「投影 > node_consume_proj **且**
    距节点 < lookahead」的双条件，改为**弧长游标越过节点的路径参数**（``progress_s >=
    cum[index]``，最近点 + 单调游标）。换判据的理由 = 双条件在**垂直拐角**上互斥：
    投影越过 0.65 要求越过拐点 0.65m，"须曾贴近"要求 < 0.45m——L 形 1m 段上永远不能
    同时成立 ⇒ 拐点永远无法消费 ⇒ 前视扫描把**身后**的拐点选成目标 ⇒ 目标航向 ≈±160°
    双稳翻转 ⇒ 无限原地转至 30s 航点超时（00_know/05 §2.3 登记：8 档横向偏移全等）。

    **新判据的护栏由单调性提供**（不再需要"须曾贴近"那道距离护栏）：弧长游标只从
    游标所在段起向后找最近段、且只单调不回退 ⇒ 折返路线起点处游标 = 0，够不到
    ``cum[1]``，「必须先去 (2,0)」的节点不会被吞。

    两条纪律不变：**最后一个节点不消费**（goal 按 H10 真到达）；消费**不**要容差/
    稳定拍数（人已走过，不是"到达"）。
    """

    #: 收口复现器：warehouse ``leg_2_3`` 的 A\\* 参考路径（27 节点）+ 起点（静态抄录，
    #: 便于 backend 包内自带复现、不反向依赖 ``tools/``）。
    #: 收口前：拐角节点在 0.45m 处被切角绕过 ⇒ ``index`` 停在 2 ⇒ 前视扫描反复把**身后**
    #: 那个候点选成目标 ⇒ 航向在 ≈±160° 间双稳翻转 ⇒ ``turn_in_place`` 无限旋转 ⇒ 30s
    #: 航点超时、此后恒发零速（``route_regression`` 60s 判"未到达"）。
    #: 收口后：dt=0.02 实测 14.98s 走到终点；dt=0.05（回归节拍）16.50s。
    LEG_2_3_PATH = [
        [3.2, 2.2], [3.31, 2.42], [3.31, 2.63], [3.52, 2.84], [3.73, 3.05], [3.94, 3.05],
        [4.15, 3.05], [4.35, 3.05], [4.56, 3.05], [4.77, 3.05], [4.98, 3.05], [5.19, 3.05],
        [5.4, 3.05], [5.6, 2.84], [5.6, 2.63], [5.6, 2.42], [5.6, 2.21], [5.6, 2.0],
        [5.6, 1.79], [5.6, 1.58], [5.6, 1.37], [5.6, 1.16], [5.6, 0.95], [5.6, 0.74],
        [5.6, 0.53], [5.81, 0.32], [6.0, 0.0],
    ]

    def test_corner_cut_node_is_consumed_and_route_completes(self):
        """leg_2_3 复现器：27 节点密集路径必须走完（收口前 30s 超时）。

        v0.55.50 起前视目标 = 弧长点，机器人贴路径跟踪 ⇒ 密集拐角改为**真到达**
        （advance）而非切角（bypass）——对巡检语义更好；切角消费分支由
        ``test_beside_corner_with_projection_past_it_is_consumed`` 等宽切用例守。
        """
        controller = FollowController(self.LEG_2_3_PATH)
        steps, x, y, yaw, t = _simulate(controller, start=(3.2, 2.2, 0.0))
        verdict = controller.verdict()
        self.assertEqual(verdict["termination_reason"], "complete")
        self.assertEqual(verdict["verdict"], "pass")
        self.assertIn("advance", {s.event for s in steps},
                      "密集路径的节点须按 H10 真到达（弧长目标跟队跟踪的应有形态）")
        self.assertLess(t, 30.0, "必须在航点超时（30s）之前走完——超时正是收口前的病象")
        self.assertLess(math.hypot(6.0 - x, 0.0 - y), 0.2, "终点在 H10 容差内")

    def test_sparse_l_corner_route_completes(self):
        """v0.55.50 主用例：稀疏长段 L 形航线（1m 段）——登记病象的直接复现器。

        收口前（2026-10-08 实测）：8 档横向偏移全等 timeout 31.4~32.5s、终点距
        0.54~0.61m、状态切换 18~28 次（双稳翻转）。收口后：全部 complete。
        弧长目标下机器人贴路径跟踪：贴线起步的档**真到达**拐角（advance），大偏移
        起步的档宽切绕过（bypass）——两种都是"节点已过"的合法机制（真到达/切角消费
        各有专门用例守），这里只锁**走完**。
        """
        for offset in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7):
            with self.subTest(offset=offset):
                controller = FollowController([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]])
                steps, x, y, _, t = _simulate(controller, start=(0.0, offset, 0.0))
                verdict = controller.verdict()
                self.assertEqual(verdict["termination_reason"], "complete",
                                 f"offset={offset} 必须走完（登记病象：此档曾超时）")
                self.assertEqual(verdict["verdict"], "pass")
                self.assertTrue(
                    {"advance", "bypass"} & {s.event for s in steps},
                    "拐角必须被走过（真到达或切角消费，二者任一即节点已过）",
                )
                self.assertLess(t, 30.0, "走完须远早于航点超时")
                self.assertLess(math.hypot(1.0 - x, 1.0 - y), 0.2 + 1e-6, "终点在 H10 容差内")

    def test_sparse_long_segment_route_completes(self):
        """米级长段（2m）L 形：收口前 timeout/终点距 1.58m；收口后 complete。"""
        controller = FollowController([[0.0, 0.0], [2.0, 0.0], [2.0, 2.0]])
        steps, x, y, _, t = _simulate(controller)
        verdict = controller.verdict()
        self.assertEqual(verdict["termination_reason"], "complete")
        self.assertEqual(verdict["verdict"], "pass")
        self.assertIn("advance", {s.event for s in steps})
        self.assertLess(math.hypot(2.0 - x, 2.0 - y), 0.2 + 1e-6)

    def test_guard_rejects_never_approached_node_in_foldback_route(self):
        """护栏（由单调性提供）：折返路线起点节点的投影一开始就"越过"，但游标在 0 处
        （机器人从未沿路径走过它）⇒ 不消费。否则会把"必须先去 (2,0)"的巡检点吞掉。
        """
        controller = FollowController([[0.0, 0.0], [2.0, 0.0], [0.5, 0.0]])
        steps, *_ = _simulate(controller, max_steps=400)
        early = steps[:5]
        self.assertEqual([s.event for s in early if s.event == "bypass"], [],
                         "起点处游标 = 0 < cum[1]=2.0：单调护栏必须拦住消费")

    def test_foldback_route_still_completes(self):
        """折返航线本身要能走完：到 (2,0) 真到达（advance）⇒ 回头去 (0.5,0) 真到达。"""
        controller = FollowController([[0.0, 0.0], [2.0, 0.0], [0.5, 0.0]])
        steps, *_ = _simulate(controller)
        verdict = controller.verdict()
        self.assertEqual(verdict["termination_reason"], "complete")
        self.assertIn("advance", {s.event for s in steps}, "折返点须按 H10 真到达（不是被消费）")

    def test_last_node_is_never_consumed(self):
        """终点节点不参与消费：goal 必须按 H10 真到达（否则"走过终点"会假装成功）。"""
        controller = FollowController([[0.0, 0.0], [1.0, 0.0]])
        steps, *_ = _simulate(controller, start=(1.2, 0.0, 0.0), max_steps=200)
        self.assertEqual([s.event for s in steps if s.event == "bypass"], [])
        self.assertEqual(controller.verdict()["termination_reason"], "complete")

    def test_beside_corner_with_projection_past_it_is_consumed(self):
        """语义变更登记（v0.55.49 → v0.55.50）：机器人贴在拐角旁、但**最近点已落在
        出向段上**（路径参数越过拐点）⇒ 消费。v0.55.49 的"投影没过 65% 就不算走过"
        口径退役——那条判据正是稀疏拐角卡死的根因（投影 65% 与"距节点 < 0.45"互斥）。
        """
        controller = FollowController([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]])
        steps, *_ = _simulate(controller, start=(0.9, 0.3, 0.0), max_steps=60)
        self.assertIn("bypass", {s.event for s in steps[:10]},
                      "最近点在出向段上（路径参数已越过拐点）⇒ 消费")

    def test_robot_still_on_incoming_segment_is_not_consumed(self):
        """对照护栏：机器人还在入向段侧（最近点在入向段上）⇒ 游标够不到拐点，不消费。"""
        controller = FollowController([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]])
        steps, *_ = _simulate(controller, start=(0.4, 0.1, 0.0), max_steps=40)
        self.assertEqual([s.event for s in steps[:20] if s.event == "bypass"], [],
                         "最近点在入向段上 ⇒ 路径参数未越过拐点 ⇒ 不消费")

    def test_degenerate_duplicate_waypoint_is_consumable(self):
        """重复航点（零长段）：v0.55.49 的投影判据对退化段恒 False ⇒ 永远卡死；路径参数
        边界下与邻居共享弧长 ⇒ 游标一到即消费（弧长目标跟队跟踪时多经真到达）。"""
        controller = FollowController([[0.0, 0.0], [1.0, 0.0], [1.0, 0.0], [1.0, 1.0]])
        steps, *_ = _simulate(controller, max_steps=1500)
        verdict = controller.verdict()
        self.assertEqual(verdict["termination_reason"], "complete")
        self.assertEqual(verdict["verdict"], "pass")


class ProjectionTests(unittest.TestCase):
    """v0.55.50 弧长投影（``_project_onto_path``）单元锁：最近点 + 单调游标。"""

    def test_projection_advances_along_straight_path(self):
        controller = FollowController([[0.0, 0.0], [2.0, 0.0]])
        self.assertAlmostEqual(controller._project_onto_path(0.5, 0.1), 0.5, places=9)
        self.assertAlmostEqual(controller._project_onto_path(1.7, -0.2), 1.7, places=9)

    def test_projection_clamps_before_start_and_past_end(self):
        controller = FollowController([[0.0, 0.0], [2.0, 0.0]])
        self.assertAlmostEqual(controller._project_onto_path(-1.0, 0.5), 0.0, places=9)
        self.assertAlmostEqual(controller._project_onto_path(3.0, 0.0), 2.0, places=9)

    def test_projection_takes_nearest_segment_at_corner(self):
        """宽切角：离出向段更近 ⇒ 路径参数取段上的投影（不是入向段的投影）。"""
        controller = FollowController([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]])
        # (0.9, 0.75)：入向段投影 0.9（垂距 0.75）vs 出向段投影 1.75（垂距 0.1）⇒ 取近的
        self.assertAlmostEqual(controller._project_onto_path(0.9, 0.75), 1.75, places=9)

    def test_projection_does_not_look_behind_the_cursor(self):
        """单调：游标已过的段不回看（折返路线入向段平行相邻，回看会把游标拉回起点）。"""
        controller = FollowController([[0.0, 0.0], [2.0, 0.0], [0.5, 0.0]])
        controller.progress_s = 2.0  # 已到折返点
        # 机器人在回程段上 (1.0, 0.0)：入向段 (0,0)→(2,0) 投影 1.0 更近，但不许回看
        self.assertAlmostEqual(controller._project_onto_path(1.0, 0.0), 3.0, places=9)

    def test_cursor_never_regresses(self):
        """update 里游标取 max：恢复动作后退不倒扣。"""
        controller = FollowController([[0.0, 0.0], [2.0, 0.0]])
        controller.update([1.0, 0.0, 0.0], 0.0)
        advanced = controller.progress_s
        controller.update([0.5, 0.0, 0.0], 0.02)  # 后退
        self.assertEqual(controller.progress_s, advanced, "游标单调不回退")


if __name__ == "__main__":
    unittest.main()
