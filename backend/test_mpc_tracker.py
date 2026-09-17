"""H14 可选对照控制器（mpc）单元测试 —— LightNav-0 vln_mpc 的纯 Python 简化版。

守什么（对齐 test_geometric_tracker / test_follow_controller 的钉法）：

1. **参数只有一个来源**：``registry/motion_commands.json#mpc_tracker``，字段与
   ``vln_mpc/mpc_node.py`` 的 declare_parameter 同名对齐，缺字段即报错（不回退代码默认值）；
2. **控制器行为**：直线收敛、急转不发散、横向误差有界（同一仿真口径下的 mpc vs geometric
   对拍，横向误差以几何中心线为准）；
3. **对比表跑通**：``tools.dwa_ab_check.simulate(mode="mpc")`` 与其他控制器同一积分器、
   同一到达判据，返回同一组指标键；
4. **退化防护**：非有限位姿不产 NaN；卡死输入（reference 在正后方）输出仍有限；
   网格窗口永远非空（上一拍控制越界也不许崩）。
"""

from __future__ import annotations

import dataclasses
import math
import unittest
from unittest import mock

from backend.mpc_tracker import (
    MpcParams,
    MpcTracker,
    PARAMS_SOURCE,
    build_pose_aligned_reference,
    mpc_command,
    mpc_selftest,
    validate_mpc_params,
)
from backend.motion_commands import mpc_tracker_spec

DT = 0.05  # 与 tools/dwa_ab_check.py 的仿真步长一致


def _integrate(tracker: MpcTracker, start: list[float], *, max_steps: int = 1200) -> tuple[list[float], int]:
    """纯运动学积分：cmd → 位姿（差速），与 A/B 评测同一运动学。"""
    x, y, yaw = start
    steps = 0
    for steps in range(1, max_steps + 1):
        result = tracker.update([x, y, yaw])
        vx, _vy, wz = result["cmd"]
        if not all(math.isfinite(value) for value in (vx, wz)):
            raise AssertionError(f"cmd 含非有限值：{result['cmd']}")
        x += vx * math.cos(yaw) * DT
        y += vx * math.sin(yaw) * DT
        yaw += wz * DT
        goal = tracker.path[-1]
        if math.hypot(goal[0] - x, goal[1] - y) <= 0.2:
            break
    return [x, y, yaw], steps


class ParamsFromRegistryTest(unittest.TestCase):
    def test_matches_registry_field_by_field(self) -> None:
        params = MpcParams.from_registry()
        spec = mpc_tracker_spec()
        for name in MpcParams.__dataclass_fields__:
            self.assertIn(name, spec, f"注册表缺字段 {name}")
            self.assertEqual(getattr(params, name), spec[name], f"字段 {name} 不一致")

    def test_missing_field_raises(self) -> None:
        with mock.patch("backend.motion_commands.mpc_tracker_spec", return_value={"horizon": 5}):
            with self.assertRaises(ValueError):
                MpcParams.from_registry()

    def test_registry_values_match_vln_mpc_node_defaults(self) -> None:
        """参数值必须与 vln_mpc/mpc_node.py 的 declare_parameter 默认值对齐（出处可查）。"""
        spec = mpc_tracker_spec()
        self.assertEqual(spec["horizon"], 5)
        self.assertEqual(spec["mpc_dt_s"], 0.1)
        self.assertEqual(spec["max_wz"], 3.0)
        self.assertEqual(spec["a_max_v"], 2.0)
        self.assertEqual(spec["a_max_w"], 5.0)
        self.assertEqual(spec["q_x"], 10.0)
        self.assertEqual(spec["q_y"], 10.0)
        self.assertEqual(spec["q_yaw"], 1.0)
        self.assertEqual(spec["r_v"], 0.1)
        self.assertEqual(spec["r_w"], 0.1)
        # max_vx 收敛到本仓 nav 档（参考 track_v_max 1.5 超出本仓运动指令档位）
        self.assertEqual(spec["max_vx"], 0.9)

    def test_validate_rejects_bad_params(self) -> None:
        params = MpcParams.from_registry()
        self.assertEqual(validate_mpc_params(params), [])
        bad = dataclasses.replace(params, horizon=0)
        self.assertTrue(any("horizon" in p for p in validate_mpc_params(bad)))
        bad = dataclasses.replace(params, w_grid_steps=4)
        self.assertTrue(any("w_grid_steps" in p for p in validate_mpc_params(bad)))
        bad = dataclasses.replace(params, q_x=0.0, q_y=0.0)
        self.assertTrue(any("位置权重" in p for p in validate_mpc_params(bad)))


class ReferenceTest(unittest.TestCase):
    def test_reference_starts_after_nearest_and_has_horizon_points(self) -> None:
        path = [[0.0, 0.0], [0.5, 0.0], [1.0, 0.0], [1.5, 0.0], [2.0, 0.0]]
        ref = build_pose_aligned_reference(path, [0.0, 0.0, 0.0], horizon=3, weights=(10.0, 10.0))
        self.assertEqual(len(ref), 3)
        # 最近点是下标 0 ⇒ 参考段从下标 1 开始
        self.assertEqual(ref[0][0], 0.5)
        self.assertEqual(ref[-1][0], 1.5)

    def test_reference_near_path_end_clamps_to_last_point(self) -> None:
        path = [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]]
        ref = build_pose_aligned_reference(path, [1.9, 0.0, 0.0], horizon=5, weights=(10.0, 10.0))
        self.assertTrue(all(point[0] <= 2.0 for point in ref))
        self.assertEqual(ref[-1][0], 2.0)

    def test_reference_yaw_follows_segment_direction(self) -> None:
        # 参考航向 = **进入该点**的方向：第 2 点（东向段末）yaw≈0，第 3 点（北向段末）yaw≈π/2
        path = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]
        ref = build_pose_aligned_reference(path, [0.0, 0.0, 0.0], horizon=2, weights=(10.0, 10.0))
        # 起点 pose 在 [0,0]，最近点=下标 0 ⇒ 参考段从下标 1 起：先东向点、再北向点
        self.assertAlmostEqual(ref[0][2], 0.0, places=6)
        self.assertAlmostEqual(ref[1][2], math.pi / 2, places=6)

    def test_empty_path_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_pose_aligned_reference([], [0.0, 0.0, 0.0], horizon=3, weights=(1.0, 1.0))


class CommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self.params = MpcParams.from_registry()

    def test_straight_reference_drives_forward(self) -> None:
        ref = [[0.5, 0.0, 0.0], [1.0, 0.0, 0.0], [1.5, 0.0, 0.0], [2.0, 0.0, 0.0], [2.5, 0.0, 0.0]]
        result = mpc_command([0.0, 0.0, 0.0], ref, self.params)
        self.assertGreater(result["cmd"][0], 0.0)
        self.assertEqual(result["cmd"][2], 0.0)

    def test_lateral_offset_reference_turns_toward_it(self) -> None:
        # 参考段在左前方（+y）⇒ 首拍应给正 wz（左转），且不发散（|wz| ≤ max_wz）
        ref = [[0.5, 0.5, 0.7], [1.0, 1.0, 0.7], [1.5, 1.5, 0.7], [2.0, 2.0, 0.7], [2.5, 2.5, 0.7]]
        result = mpc_command([0.0, 0.0, 0.0], ref, self.params)
        self.assertGreater(result["cmd"][2], 0.0)
        self.assertLessEqual(result["cmd"][2], self.params.max_wz)

    def test_sharp_turn_reference_does_not_explode(self) -> None:
        """急转（参考航向突变 ~180°）输出仍限幅、有限——不发散。"""
        ref = [[0.5, 0.0, 0.0], [0.4, 0.1, 2.8], [0.3, 0.2, -2.8], [0.4, 0.3, 2.9], [0.5, 0.4, -2.9]]
        result = mpc_command([0.0, 0.0, 0.0], ref, self.params)
        self.assertTrue(math.isfinite(result["cmd"][0]))
        self.assertTrue(math.isfinite(result["cmd"][2]))
        self.assertLessEqual(abs(result["cmd"][2]), self.params.max_wz + 1e-9)
        self.assertLessEqual(result["cmd"][0], self.params.max_vx + 1e-9)

    def test_first_step_respects_acceleration_window(self) -> None:
        """上一拍 v=0 ⇒ 首拍 v ≤ a_max_v·dt（参考 MPC 首拍约束的离散化）。"""
        ref = [[0.5, 0.0, 0.0], [1.0, 0.0, 0.0], [1.5, 0.0, 0.0], [2.0, 0.0, 0.0], [2.5, 0.0, 0.0]]
        result = mpc_command([0.0, 0.0, 0.0], ref, self.params, previous=(0.0, 0.0))
        self.assertLessEqual(result["cmd"][0], self.params.a_max_v * self.params.mpc_dt_s + 1e-9)

    def test_window_never_empty_when_previous_out_of_bounds(self) -> None:
        """上一拍控制越界（异常输入）也不许崩：窗被裁到界内、恒有解。"""
        ref = [[0.5, 0.0, 0.0], [1.0, 0.0, 0.0], [1.5, 0.0, 0.0], [2.0, 0.0, 0.0], [2.5, 0.0, 0.0]]
        result = mpc_command([0.0, 0.0, 0.0], ref, self.params, previous=(99.0, -99.0))
        self.assertEqual(result["candidates"] > 0, True)
        self.assertTrue(math.isfinite(result["cmd"][0]))

    def test_non_finite_pose_rejected_without_nan(self) -> None:
        ref = [[0.5, 0.0, 0.0], [1.0, 0.0, 0.0], [1.5, 0.0, 0.0], [2.0, 0.0, 0.0], [2.5, 0.0, 0.0]]
        for bad_pose in ([float("nan"), 0.0, 0.0], [0.0, float("inf"), 0.0], [0.0, 0.0, float("nan")]):
            result = mpc_command(bad_pose, ref, self.params)
            self.assertEqual(result["cmd"], [0.0, 0.0, 0.0])
            self.assertIn("reason", result)

    def test_stuck_reference_stays_finite(self) -> None:
        """卡死输入：参考段在正后方 ⇒ MPC 不会给出 NaN/Inf（宁停不崩）。"""
        ref = [[-0.5, 0.0, math.pi], [-1.0, 0.0, math.pi], [-1.5, 0.0, math.pi], [-2.0, 0.0, math.pi], [-2.5, 0.0, math.pi]]
        result = mpc_command([0.0, 0.0, 0.0], ref, self.params)
        for value in result["cmd"]:
            self.assertTrue(math.isfinite(value))


class TrackerConvergenceTest(unittest.TestCase):
    def test_reaches_end_of_straight_path(self) -> None:
        tracker = MpcTracker([[0.0, 0.0], [2.0, 0.0]])
        pose, steps = _integrate(tracker, [0.0, 0.0, 0.0])
        self.assertLess(math.hypot(2.0 - pose[0], pose[1]), 0.2, f"steps={steps}")
        self.assertLess(steps, 300, "直线 2 m 应在 300 拍内走完")

    def test_survives_sharp_corner_route(self) -> None:
        """急转路线（先东后北再西）不发散、能到终点（对照 A/B 的 leg 场景）。"""
        tracker = MpcTracker([[0.0, 0.0], [1.5, 0.0], [1.5, 1.5], [0.0, 1.5]])
        pose, _steps = _integrate(tracker, [0.0, 0.0, 0.0])
        self.assertLess(math.hypot(0.0 - pose[0], 1.5 - pose[1]), 0.3, f"final={pose}")

    def test_lateral_error_stays_bounded_on_straight_run(self) -> None:
        """横向误差有界：直线跟踪中 |y| 不得越过 0.15 m（起步偏 0.1 也能收敛）。"""
        tracker = MpcTracker([[0.0, 0.0], [2.0, 0.0]])
        x, y, yaw = 0.0, 0.1, 0.0
        worst = 0.0
        for _ in range(400):
            result = tracker.update([x, y, yaw])
            vx, _vy, wz = result["cmd"]
            x += vx * math.cos(yaw) * DT
            y += vx * math.sin(yaw) * DT
            yaw += wz * DT
            worst = max(worst, abs(y))
        self.assertLess(worst, 0.15, f"最大横向误差 {worst:.4f} m")

    def test_update_reports_params_source(self) -> None:
        tracker = MpcTracker([[0.0, 0.0], [1.0, 0.0]])
        self.assertEqual(tracker.update([0.0, 0.0, 0.0])["params_source"], PARAMS_SOURCE)

    def test_short_path_raises(self) -> None:
        with self.assertRaises(ValueError):
            MpcTracker([[0.0, 0.0]])


class OvershootTest(unittest.TestCase):
    """H14 验收的「超调」半边：沿路径方向**越过目标点**的最大距离（位置超调）。

    口径：仿真跑到速度归零（MPC 刹停）或走完 max_steps，取 ``max(0, 沿线越过的距离)``。
    MPC 目标函数本身含刹车动机（停在参考末点代价最小），加减速窗限制刹车力度；
    网格分辨率是近似误差来源——这条测试就是给"简化版刹车"钉一个可回归的界。
    """

    def test_positional_overshoot_past_goal_is_bounded(self) -> None:
        tracker = MpcTracker([[0.0, 0.0], [2.0, 0.0]])
        x, y, yaw = 0.0, 0.0, 0.0
        past_max = 0.0
        for _ in range(300):
            result = tracker.update([x, y, yaw])
            vx, _vy, wz = result["cmd"]
            x += vx * math.cos(yaw) * DT
            y += vx * math.sin(yaw) * DT
            yaw += wz * DT
            past_max = max(past_max, x - 2.0)
            if vx == 0.0:
                break
        self.assertLess(past_max, 0.1, f"位置超调 {past_max:.4f} m")

    def test_braking_distance_within_accel_limit(self) -> None:
        """刹停点不得越过目标过远：网格 MPC 应在容差内停住（对齐 H10 容差口径）。"""
        tracker = MpcTracker([[0.0, 0.0], [2.0, 0.0]])
        pose, steps = _integrate(tracker, [0.0, 0.0, 0.0])
        self.assertLess(math.hypot(2.0 - pose[0], pose[1]), 0.2)
        self.assertLess(steps, 300)


class SimulationHarnessTest(unittest.TestCase):
    """对比表跑通：mpc 从 tools.dwa_ab_check.simulate 走同一积分器与判据。"""

    def test_simulate_mpc_runs_warehouse_route(self) -> None:
        from tools.dwa_ab_check import _parse_waypoints, reference_path, simulate
        from backend.dwa_planner import DwaParams
        from backend.motion_commands import follow_controller_spec
        from backend.scenario_maps import MAPS

        map_id = "warehouse"
        waypoints = _parse_waypoints(None, map_id)
        obstacles = [list(o[:4]) for o in (MAPS[map_id].get("obstacles") or [])]
        path = reference_path(map_id, waypoints, obstacles)
        result = simulate(
            "mpc",
            waypoints,
            path,
            obstacles,
            dt=0.05,
            max_steps=1200,
            tolerance=0.2,
            params=DwaParams.from_registry(),
            turn_gain=float(follow_controller_spec()["kp_yaw"]),
        )
        # 同一组指标键（与 potential/dwa/geometric/follow 完全同构）
        for key in ("reached", "steps", "time_s", "min_clearance_m", "collision_steps", "final_distance_m", "final_pose"):
            self.assertIn(key, result)
        self.assertTrue(math.isfinite(result["final_distance_m"]))
        if result["min_clearance_m"] is not None:
            self.assertTrue(math.isfinite(result["min_clearance_m"]))


class SelftestTest(unittest.TestCase):
    def test_mpc_selftest_passes(self) -> None:
        result = mpc_selftest()
        self.assertEqual(result["verdict"], "pass", result)


if __name__ == "__main__":
    unittest.main()
