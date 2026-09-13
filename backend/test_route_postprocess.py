"""H13 规划后处理单元测试：净空四级 + 路径简化 + 转角混合。"""

from __future__ import annotations

import math
import unittest
from unittest import mock

from backend.motion_commands import route_postprocess_spec
from backend.route_postprocess import (
    CLEARANCE_LEVELS,
    PARAMS_SOURCE,
    PostprocessParams,
    _point_rect_signed_distance,
    blend_corners,
    classify_segments,
    postprocess_route,
    review_route,
    segment_rect_distance,
    segment_rect_intersects,
    segments_intersect,
    simplify_path,
)

#: 单位障碍：x∈[-0.5,0.5]、y∈[-0.5,0.5]
OBSTACLE = [[0.0, 0.0, 0.5, 0.5]]
#: 参数固定下来，判据边界才好断言（required = 0.21 + 0.05 = 0.26）
PARAMS = PostprocessParams(
    footprint_radius_m=0.21,
    avoid_margin_m=0.05,
    warn_margin_m=0.05,
    simplify_tolerance_m=0.1,
    corner_blend_m=0.2,
    corner_blend_samples=4,
    relax_iterations=240,
    relax_step_scale=0.45,
    relax_max_move_per_iter_m=0.08,
    relax_max_total_move_m=0.55,
    relax_smooth_weight=0.12,
    relax_buffer_m=0.05,
    relax_lock_ends=True,
    max_segment_length_m=0.65,
    min_speed_mps=0.22,
)


class ParamsTest(unittest.TestCase):
    def test_matches_registry_field_by_field(self) -> None:
        params = PostprocessParams.from_registry()
        spec = route_postprocess_spec()
        for name in PostprocessParams.__dataclass_fields__:
            self.assertIn(name, spec, f"注册表缺字段 {name}")
            self.assertEqual(getattr(params, name), spec[name], f"字段 {name} 不一致")

    def test_missing_field_raises(self) -> None:
        with mock.patch(
            "backend.motion_commands.route_postprocess_spec", return_value={"avoid_margin_m": 0.05}
        ):
            with self.assertRaises(ValueError):
                PostprocessParams.from_registry()

    def test_required_clearance_is_footprint_plus_margin(self) -> None:
        self.assertAlmostEqual(PARAMS.required_clearance_m, 0.26, places=9)

    def test_clearance_levels_order_is_severity(self) -> None:
        self.assertEqual(CLEARANCE_LEVELS, ("OK", "TIGHT", "VIOLATION", "INTERSECT"))


class GeometryTest(unittest.TestCase):
    def test_signed_distance_matches_nav_avoidance(self) -> None:
        from adapters.mjlab.nav_avoidance import _point_rect_signed_distance as reference

        for obstacle in (OBSTACLE[0], [1.0, -1.0, 0.2, 0.8]):
            for px, py in ((0.0, 0.0), (1.0, 1.0), (5.0, 5.0), (0.6, 0.0)):
                self.assertAlmostEqual(
                    _point_rect_signed_distance(px, py, obstacle),
                    reference(px, py, obstacle),
                    places=9,
                )

    def test_segments_intersect_basic(self) -> None:
        self.assertTrue(segments_intersect((0, 0), (2, 2), (0, 2), (2, 0)))
        self.assertFalse(segments_intersect((0, 0), (1, 0), (0, 1), (1, 1)))

    def test_segment_rect_intersects(self) -> None:
        self.assertTrue(segment_rect_intersects((-2, 0), (2, 0), OBSTACLE[0]))
        self.assertTrue(segment_rect_intersects((0, 0), (0.1, 0.1), OBSTACLE[0]))  # 端点在内部
        self.assertFalse(segment_rect_intersects((-2, 1), (2, 1), OBSTACLE[0]))

    def test_segment_rect_distance(self) -> None:
        self.assertAlmostEqual(segment_rect_distance((-2, 1), (2, 1), OBSTACLE[0]), 0.5, places=9)
        self.assertAlmostEqual(segment_rect_distance((-2, 0), (2, 0), OBSTACLE[0]), 0.0, places=9)


class ClassifyTest(unittest.TestCase):
    """四级判据的边界（required = 0.26，warn = 0.05）。"""

    def status_of(self, y: float) -> str:
        path = [[-2.0, y], [2.0, y]]
        return classify_segments(path, OBSTACLE, PARAMS)[0].status_with(PARAMS.warn_margin_m)

    def test_intersect_when_centerline_crosses(self) -> None:
        self.assertEqual(self.status_of(0.0), "INTERSECT")

    def test_violation_when_margin_negative(self) -> None:
        # 净空 0.10 < 0.26 ⇒ margin −0.16
        self.assertEqual(self.status_of(0.6), "VIOLATION")

    def test_tight_when_margin_below_warn(self) -> None:
        # 净空 0.30 ⇒ margin 0.04 ∈ [0, 0.05)
        self.assertEqual(self.status_of(0.8), "TIGHT")

    def test_ok_when_margin_comfortable(self) -> None:
        # 净空 0.35 ⇒ margin 0.09
        self.assertEqual(self.status_of(0.85), "OK")

    def test_no_obstacles_is_ok_with_infinite_clearance(self) -> None:
        risk = classify_segments([[-2.0, 0.0], [2.0, 0.0]], [], PARAMS)[0]
        self.assertEqual(risk.status_with(PARAMS.warn_margin_m), "OK")
        self.assertTrue(math.isinf(risk.clearance_m))

    def test_worst_obstacle_wins(self) -> None:
        # 两个障碍：一个被穿过、一个在远处 ⇒ 取更严重的（INTERSECT）
        near = [[0.0, 0.6, 0.5, 0.1]]
        risks = classify_segments([[-2.0, 0.0], [2.0, 0.0]], near + OBSTACLE, PARAMS)
        self.assertEqual(risks[0].status_with(PARAMS.warn_margin_m), "INTERSECT")

    def test_segment_count_is_points_minus_one(self) -> None:
        path = [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]]
        self.assertEqual(len(classify_segments(path, [], PARAMS)), 2)


class SimplifyTest(unittest.TestCase):
    def test_removes_collinear_points(self) -> None:
        path = [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0], [2.0, 1.0]]
        self.assertEqual(
            simplify_path(path, 0.1, params=PARAMS), [[0.0, 0.0], [2.0, 0.0], [2.0, 1.0]]
        )

    def test_keeps_endpoints(self) -> None:
        path = [[0.0, 0.0], [0.05, 0.0], [1.0, 0.0]]
        simplified = simplify_path(path, 0.1, params=PARAMS)
        self.assertEqual(simplified[0], [0.0, 0.0])
        self.assertEqual(simplified[-1], [1.0, 0.0])

    def test_zero_tolerance_keeps_everything(self) -> None:
        path = [[0.0, 0.0], [0.5, 0.0], [1.0, 0.0]]
        self.assertEqual(simplify_path(path, 0.0, params=PARAMS), path)

    def test_keeps_corner_beyond_tolerance(self) -> None:
        path = [[0.0, 0.0], [1.0, 0.3], [2.0, 0.0]]
        self.assertEqual(len(simplify_path(path, 0.1, params=PARAMS)), 3)


class BlendTest(unittest.TestCase):
    def test_corner_is_blended_and_endpoints_kept(self) -> None:
        path = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]
        blended = blend_corners(path, 0.2, 2, params=PARAMS)
        self.assertGreater(len(blended), len(path), "圆角应增加点数")
        self.assertEqual(blended[0], [0.0, 0.0])
        self.assertEqual(blended[-1], [1.0, 1.0])

    def test_short_segments_are_not_consumed(self) -> None:
        # 段长 0.05 < blend 0.2 ⇒ cut 被夹到段长一半，坐标仍在原范围内
        path = [[0.0, 0.0], [0.05, 0.0], [0.05, 0.05]]
        blended = blend_corners(path, 0.2, 2, params=PARAMS)
        self.assertTrue(all(-1e-9 <= pt[0] <= 0.05 + 1e-9 for pt in blended))
        self.assertTrue(all(-1e-9 <= pt[1] <= 0.05 + 1e-9 for pt in blended))

    def test_two_points_unchanged(self) -> None:
        path = [[0.0, 0.0], [1.0, 0.0]]
        self.assertEqual(blend_corners(path, 0.2, 2, params=PARAMS), path)


class ReviewTest(unittest.TestCase):
    def test_summary_counts_and_blocked_flag(self) -> None:
        review = review_route([[-2.0, 0.0], [0.0, 0.0], [2.0, 0.0]], OBSTACLE, PARAMS)
        self.assertGreater(review["summary"]["INTERSECT"], 0)
        self.assertTrue(review["summary"]["blocked"])
        self.assertEqual(review["summary"]["worst_status"], "INTERSECT")

    def test_clear_route_not_blocked(self) -> None:
        review = review_route([[-2.0, 2.0], [2.0, 2.0]], OBSTACLE, PARAMS)
        self.assertFalse(review["summary"]["blocked"])
        self.assertEqual(review["summary"]["worst_status"], "OK")

    def test_segments_carry_status_and_indices(self) -> None:
        review = review_route([[-2.0, 1.0], [2.0, 1.0]], OBSTACLE, PARAMS)
        self.assertEqual(len(review["segments"]), 1)
        seg = review["segments"][0]
        for key in (
            "index",
            "start_index",
            "end_index",
            "clearance_m",
            "required_m",
            "margin_m",
            "status",
        ):
            self.assertIn(key, seg)
        self.assertEqual(seg["index"], 0)

    def test_total_length_matches_path(self) -> None:
        review = review_route([[-2.0, 2.0], [0.0, 2.0], [0.0, 3.0]], OBSTACLE, PARAMS)
        self.assertAlmostEqual(review["summary"]["total_length_m"], 3.0, places=6)

    def test_params_source_and_required_clearance_reported(self) -> None:
        review = review_route([[-2.0, 2.0], [2.0, 2.0]], OBSTACLE, PARAMS)
        self.assertEqual(review["params_source"], PARAMS_SOURCE)
        self.assertAlmostEqual(review["required_clearance_m"], 0.26, places=9)

    def test_postprocess_route_blends_and_classifies(self) -> None:
        result = postprocess_route([[-2.0, 2.0], [0.0, 2.0], [0.0, 3.0]], OBSTACLE, PARAMS)
        self.assertTrue(result["simplified"])
        self.assertTrue(result["corner_blended"])
        self.assertEqual(len(result["segments"]), len(result["path"]) - 1)


if __name__ == "__main__":
    unittest.main()
