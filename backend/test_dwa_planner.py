"""H11 局部采样规划器（DWA）单元测试。

覆盖四类：① 参数只从注册表来（逐字段对拍 + 缺字段报错）；② 几何与 nav_avoidance 同口径；
③ 采样/评分/硬约束/恢复的行为；④ 候选扇形与 plan_local 同源（页面画的和跑的是同一份）。
"""

from __future__ import annotations

import dataclasses
import math
import unittest
from unittest import mock

from backend import dwa_planner as dwa
from backend.dwa_planner import (
    DwaParams,
    candidate_fan,
    min_clearance,
    path_direction,
    path_distance,
    plan_local,
    point_rect_signed_distance,
)
from backend.motion_commands import local_planner_spec

#: 空旷直路：起点 → +x 2 m
OPEN_PATH = [[0.0, 0.0], [2.0, 0.0]]
#: 3 m 直路（恢复/目标较远的场景）
LONG_PATH = [[0.0, 0.0], [3.0, 0.0]]


class ParamsFromRegistryTest(unittest.TestCase):
    def test_matches_registry_field_by_field(self) -> None:
        params = DwaParams.from_registry()
        spec = local_planner_spec()
        fields = list(DwaParams.__dataclass_fields__)
        self.assertTrue(fields)
        for name in fields:
            self.assertIn(name, spec, f"注册表缺字段 {name}")
            self.assertEqual(getattr(params, name), spec[name], f"字段 {name} 与注册表不一致")

    def test_missing_field_raises(self) -> None:
        with mock.patch(
            "backend.motion_commands.local_planner_spec", return_value={"sim_time_s": 1.0}
        ):
            with self.assertRaises(ValueError):
                DwaParams.from_registry()

    def test_steps_derived_from_time_and_dt(self) -> None:
        params = DwaParams.from_registry()
        self.assertEqual(params.steps, round(params.sim_time_s / params.sim_dt_s))


class GeometryTest(unittest.TestCase):
    def test_signed_distance_matches_nav_avoidance(self) -> None:
        from adapters.mjlab.nav_avoidance import _point_rect_signed_distance

        obstacles = [(1.0, 1.0, 0.5, 0.5), (2.0, -1.0, 0.2, 0.8)]
        points = [(0.0, 0.0), (1.0, 1.0), (5.0, 5.0), (2.0, 0.0), (0.8, 1.0)]
        for obstacle in obstacles:
            for px, py in points:
                self.assertAlmostEqual(
                    point_rect_signed_distance(px, py, obstacle),
                    _point_rect_signed_distance(px, py, obstacle),
                    places=9,
                    msg=f"{obstacle} @ {px},{py}",
                )

    def test_inside_obstacle_is_negative(self) -> None:
        self.assertLess(point_rect_signed_distance(1.0, 1.0, (1.0, 1.0, 0.5, 0.5)), 0.0)

    def test_min_clearance_without_obstacles_is_infinite(self) -> None:
        self.assertEqual(min_clearance(0.0, 0.0, []), float("inf"))

    def test_path_distance_on_path_is_zero(self) -> None:
        self.assertAlmostEqual(path_distance(1.0, 0.0, OPEN_PATH), 0.0, places=9)

    def test_path_direction_along_segment(self) -> None:
        self.assertAlmostEqual(path_direction(1.0, 0.0, OPEN_PATH), 0.0, places=9)
        up = [[0.0, 0.0], [0.0, 1.0]]
        self.assertAlmostEqual(path_direction(0.0, 0.5, up), math.pi / 2, places=9)

class PlanLocalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.params = DwaParams.from_registry()

    def test_open_path_moves_forward(self) -> None:
        plan = plan_local([0.0, 0.0, 0.0], [0.0, 0.0, 0.0], OPEN_PATH, [], params=self.params)
        self.assertEqual(plan.reason, "ok")
        self.assertGreater(plan.cmd[0], 0.0)
        self.assertFalse(plan.recovery)

    def test_candidate_count_equals_sample_grid(self) -> None:
        plan = plan_local([0.0, 0.0, 0.0], [0.0, 0.0, 0.0], OPEN_PATH, [], params=self.params)
        self.assertEqual(len(plan.candidates), self.params.v_samples * self.params.w_samples)

    def test_obstacle_rejects_some_forward_candidates(self) -> None:
        # 挡在视界内的正前方
        plan = plan_local(
            [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], LONG_PATH,
            [[0.45, 0.0, 0.15, 0.25]], params=self.params,
        )
        rejected = [c for c in plan.candidates if not c.valid]
        self.assertTrue(rejected)
        self.assertTrue(all(c.rejected_reason for c in rejected))

    def test_chosen_trajectory_never_penetrates_robot_radius(self) -> None:
        obstacles = [[0.45, 0.0, 0.15, 0.25]]
        plan = plan_local([0.0, 0.0, 0.0], [0.0, 0.0, 0.0], LONG_PATH, obstacles, params=self.params)
        worst = min(min_clearance(x, y, obstacles) for x, y, _ in plan.trajectory)
        self.assertGreaterEqual(worst, self.params.robot_radius_m - 1e-6)

    def test_allow_backward_false_keeps_speeds_non_negative(self) -> None:
        params = dataclasses.replace(self.params, allow_backward=False)
        plan = plan_local([0.0, 0.0, 0.0], [0.0, 0.0, 0.0], OPEN_PATH, [], params=params)
        self.assertTrue(all(c.v >= 0.0 for c in plan.candidates))

    def test_start_in_collision_triggers_recovery(self) -> None:
        # 起点就在障碍内部 ⇒ 所有候选无效 ⇒ 走恢复
        plan = plan_local(
            [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], LONG_PATH,
            [[0.0, 0.0, 0.5, 0.5]], params=self.params,
        )
        self.assertTrue(plan.recovery)
        self.assertEqual(plan.reason, "rotate_recovery")
        self.assertAlmostEqual(plan.cmd[0], self.params.recovery_vx_mps, places=9)
        self.assertNotEqual(plan.cmd[2], 0.0)

    def test_recovery_disabled_reports_no_feasible(self) -> None:
        params = dataclasses.replace(self.params, rotate_recovery=False)
        plan = plan_local(
            [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], LONG_PATH,
            [[0.0, 0.0, 0.5, 0.5]], params=params,
        )
        self.assertFalse(plan.recovery)
        self.assertEqual(plan.reason, "no_feasible_trajectory")
        self.assertEqual(plan.cmd, [0.0, 0.0, 0.0])

    def test_recovery_direction_follows_path_end(self) -> None:
        # 路径末端在 +x；障碍罩住起点 ⇒ 恢复应朝前（wz 由误差符号定，此处误差≈0 取固定正向）
        plan = plan_local(
            [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], LONG_PATH,
            [[0.0, 0.0, 0.5, 0.5]], params=self.params,
        )
        self.assertGreater(plan.cmd[2], 0.0)

    def test_velocity_feeds_dynamic_window(self) -> None:
        # 当前速度 0.9 ⇒ 窗口上界受 max_vx 限制，且候选不再围绕 0 对称
        plan = plan_local([0.0, 0.0, 0.0], [0.9, 0.0, 0.0], OPEN_PATH, [], params=self.params)
        self.assertTrue(all(c.v <= self.params.max_vx + 1e-9 for c in plan.candidates))
        self.assertTrue(any(c.v < 0.0 for c in plan.candidates) == self.params.allow_backward)

    def test_candidates_cover_turning_range(self) -> None:
        # 候选的角速度应覆盖正负两侧（扇形要能画出左右转向）
        plan = plan_local([0.0, 0.0, 0.0], [0.0, 0.0, 0.0], OPEN_PATH, [], params=self.params)
        speeds = [c.w for c in plan.candidates]
        self.assertLess(min(speeds), 0.0)
        self.assertGreater(max(speeds), 0.0)
        self.assertTrue(any(abs(value) > 0.1 for value in speeds))


class CandidateFanTest(unittest.TestCase):
    def test_fan_shares_plan_local_results(self) -> None:
        fan = candidate_fan([0.0, 0.0, 0.0], [0.0, 0.0, 0.0], OPEN_PATH, [], params=DwaParams.from_registry())
        direct = plan_local([0.0, 0.0, 0.0], [0.0, 0.0, 0.0], OPEN_PATH, [], params=DwaParams.from_registry())
        self.assertEqual(fan["cmd"], direct.cmd)
        self.assertEqual(fan["reason"], direct.reason)
        self.assertEqual(len(fan["candidates"]), len(direct.candidates))

    def test_best_index_points_to_best_valid_candidate(self) -> None:
        fan = candidate_fan([0.0, 0.0, 0.0], [0.0, 0.0, 0.0], OPEN_PATH, [], params=DwaParams.from_registry())
        best_index = fan["best_index"]
        self.assertIsNotNone(best_index)
        valid = [c for c in fan["candidates"] if c["valid"]]
        self.assertTrue(valid)
        best_score = max(c["score"] for c in valid)
        self.assertAlmostEqual(fan["candidates"][best_index]["score"], best_score, places=9)

    def test_fan_carries_params_source(self) -> None:
        fan = candidate_fan([0.0, 0.0, 0.0], [0.0, 0.0, 0.0], OPEN_PATH, [], params=DwaParams.from_registry())
        self.assertEqual(fan["params_source"], dwa.PARAMS_SOURCE)


class SelftestTest(unittest.TestCase):
    def test_dwa_selftest_passes(self) -> None:
        result = dwa.dwa_selftest()
        self.assertEqual(result["verdict"], "pass", result)


if __name__ == "__main__":
    unittest.main()
