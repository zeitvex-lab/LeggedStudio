"""H14 几何路径跟踪控制器单元测试（参考 jie_3d_nav d1_controller）。"""

from __future__ import annotations

import dataclasses
import math
import unittest
from unittest import mock

from backend.geometric_tracker import (
    GeometricParams,
    GeometricTracker,
    PARAMS_SOURCE,
    command_from_target,
    geometric_selftest,
    select_tracking_target,
)
from backend.motion_commands import geometric_tracker_spec


class ParamsFromRegistryTest(unittest.TestCase):
    def test_matches_registry_field_by_field(self) -> None:
        params = GeometricParams.from_registry()
        spec = geometric_tracker_spec()
        for name in GeometricParams.__dataclass_fields__:
            self.assertIn(name, spec, f"注册表缺字段 {name}")
            self.assertEqual(getattr(params, name), spec[name], f"字段 {name} 不一致")

    def test_missing_field_raises(self) -> None:
        with mock.patch(
            "backend.motion_commands.geometric_tracker_spec", return_value={"linear_gain": 1.0}
        ):
            with self.assertRaises(ValueError):
                GeometricParams.from_registry()


class SelectTrackingTargetTest(unittest.TestCase):
    def test_advances_past_points_within_tolerance(self) -> None:
        path = [[0.0, 0.0], [0.1, 0.0], [1.0, 0.0]]
        index, target = select_tracking_target([0.0, 0.0], path, 0, 0.2)
        self.assertEqual(index, 2, "容差内的点应被跳过")
        self.assertEqual(target, [1.0, 0.0])

    def test_stops_when_current_point_already_far(self) -> None:
        path = [[0.0, 0.0], [2.0, 0.0]]
        index, target = select_tracking_target([0.0, 0.0], path, 0, 0.2)
        self.assertEqual(index, 1)
        self.assertEqual(target, [2.0, 0.0])

    def test_empty_path_raises(self) -> None:
        with self.assertRaises(ValueError):
            select_tracking_target([0.0, 0.0], [], 0, 0.2)


class CommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self.params = GeometricParams.from_registry()

    def test_straight_ahead_drives_forward_without_turning(self) -> None:
        result = command_from_target([0.0, 0.0, 0.0], [2.0, 0.0], self.params)
        self.assertGreater(result["cmd"][0], 0.0)
        self.assertEqual(result["cmd"][2], 0.0)

    def test_speed_is_clamped(self) -> None:
        result = command_from_target([0.0, 0.0, 0.0], [5.0, 0.0], self.params)
        self.assertAlmostEqual(result["cmd"][0], self.params.max_linear_speed, places=6)

    def test_lateral_offset_produces_angular_command(self) -> None:
        result = command_from_target([0.0, 0.0, 0.0], [2.0, 1.0], self.params)
        self.assertNotEqual(result["cmd"][2], 0.0)
        self.assertAlmostEqual(abs(result["cmd"][2]), self.params.max_angular_speed, places=6)

    def test_deadband_zeroes_small_commands(self) -> None:
        result = command_from_target([0.0, 0.0, 0.0], [0.01, 0.0], self.params)
        self.assertEqual(result["cmd"][0], 0.0)
        self.assertEqual(result["cmd"][2], 0.0)

    def test_lateral_motion_toggle(self) -> None:
        params = dataclasses.replace(self.params, enable_lateral_motion=False)
        result = command_from_target([0.0, 0.0, 0.0], [1.0, 1.0], params)
        self.assertEqual(result["cmd"][1], 0.0)

    def test_base_frame_error_rotates_with_yaw(self) -> None:
        # 机器人朝 +y（yaw=π/2），目标在 +x ⇒ 机体系里目标在右侧
        result = command_from_target([0.0, 0.0, math.pi / 2], [2.0, 0.0], self.params)
        self.assertAlmostEqual(result["base_error"][0], 0.0, places=6)
        self.assertAlmostEqual(result["base_error"][1], -2.0, places=6)


class TrackerTest(unittest.TestCase):
    def test_reaches_end_of_straight_path(self) -> None:
        tracker = GeometricTracker([[0.0, 0.0], [2.0, 0.0]])
        pose = [0.0, 0.0, 0.0]
        for _ in range(400):
            result = tracker.update(pose)
            vx, _vy, wz = result["cmd"]
            pose = [pose[0] + vx * 0.05, pose[1], pose[2] + wz * 0.05]
            if math.hypot(2.0 - pose[0], -pose[1]) < 0.05:
                break
        self.assertLess(math.hypot(2.0 - pose[0], -pose[1]), 0.2)

    def test_update_reports_params_source(self) -> None:
        tracker = GeometricTracker([[0.0, 0.0], [1.0, 0.0]])
        self.assertEqual(tracker.update([0.0, 0.0, 0.0])["params_source"], PARAMS_SOURCE)

    def test_short_path_raises(self) -> None:
        with self.assertRaises(ValueError):
            GeometricTracker([[0.0, 0.0]])

    def test_advances_only_to_first_point_beyond_tolerance(self) -> None:
        # 路径 [[0,0],[0.5,0],[1.0,0]]：起点在容差内 ⇒ 推进到**第一个**超出容差的点（0.5），
        # 不是一步跳到末点（d1_controller::selectTrackingTarget 的语义）
        tracker = GeometricTracker([[0.0, 0.0], [0.5, 0.0], [1.0, 0.0]])
        result = tracker.update([0.0, 0.0, 0.0])
        self.assertEqual(result["target"], [0.5, 0.0])


class SelftestTest(unittest.TestCase):
    def test_geometric_selftest_passes(self) -> None:
        result = geometric_selftest()
        self.assertEqual(result["verdict"], "pass", result)


if __name__ == "__main__":
    unittest.main()
