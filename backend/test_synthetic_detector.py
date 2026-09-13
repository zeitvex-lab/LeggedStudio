"""合成检测器的测试：**闭环**（投影 → 检测 → 反解位姿）与噪声语义。

这些测试要证明两件事：
1. **几何闭环是通的**——无噪声时"角点 → 像素 → 位姿"能还原真值（否则链路本身有问题）；
2. **噪声参数真的在起作用**——σ 增大误差必须单调变大，丢帧/缺角必须**返回未检测**
   而不是给一组假角点（后者才是"伪造检测"）。
"""

from __future__ import annotations

import random
import unittest

from backend.camera_projection import camera_profile, camera_profile_intrinsics
from backend.synthetic_detector import (
    CORNER_COUNT,
    DetectionNoise,
    corners_from_tag_pose,
    detect_from_optical,
    synthetic_detector_selftest,
)
from backend.perception_providers.tag_detector import pose_from_corners

PROFILE = "ideal-pinhole-1920x1080"
TAG_SIZE_M = 0.16
TRUTH_OPTICAL = (0.10, -0.04, 1.20)


def intrinsics() -> dict:
    return camera_profile_intrinsics(camera_profile(PROFILE))


def truth_corners() -> list[list[float]]:
    return corners_from_tag_pose(TRUTH_OPTICAL, tag_size_m=TAG_SIZE_M)


def recover(corners_px, lens) -> dict:
    return pose_from_corners(corners_px, lens, TAG_SIZE_M, undistorted=True)


def position_error(pose) -> float:
    return max(abs(float(a) - b) for a, b in zip(pose["position_optical"], TRUTH_OPTICAL))


class ClosedLoopTest(unittest.TestCase):
    def test_ideal_detection_recovers_truth(self) -> None:
        lens = intrinsics()
        detected = detect_from_optical(truth_corners(), lens, noise=DetectionNoise(), z_min=0.1)
        self.assertTrue(detected["detected"], detected.get("detail"))
        self.assertEqual(len(detected["corners_px"]), CORNER_COUNT)
        pose = recover(detected["corners_px"], lens)
        self.assertLess(position_error(pose), 1e-6, "无噪声时必须精确还原真值")

    def test_marks_itself_as_not_image_based(self) -> None:
        """输出必须自报"不是图像识别"，防止下游把合成检测当真实能力。"""
        detected = detect_from_optical(truth_corners(), intrinsics(), noise=DetectionNoise())
        self.assertEqual(detected["source"], "synthetic_detector")
        self.assertFalse(detected["image_based"])

    def test_selftest_passes(self) -> None:
        result = synthetic_detector_selftest()
        self.assertEqual(result["verdict"], "pass", result)


class NoiseTest(unittest.TestCase):
    def test_error_grows_with_sigma(self) -> None:
        lens = intrinsics()
        errors = []
        for sigma in (0.0, 0.5, 2.0):
            detected = detect_from_optical(
                truth_corners(),
                lens,
                noise=DetectionNoise(sigma_px=sigma),
                rng=random.Random(7),
            )
            self.assertTrue(detected["detected"])
            errors.append(position_error(recover(detected["corners_px"], lens)))
        self.assertLess(errors[0], errors[1], "σ 变大误差应变大")
        self.assertLess(errors[1], errors[2], "误差应随 σ 单调增长")

    def test_bias_shifts_pixels(self) -> None:
        lens = intrinsics()
        base = detect_from_optical(
            truth_corners(), lens, noise=DetectionNoise(), rng=random.Random(1)
        )
        biased = detect_from_optical(
            truth_corners(), lens, noise=DetectionNoise(bias_px=3.0), rng=random.Random(1)
        )
        for a, b in zip(base["corners_px"], biased["corners_px"]):
            self.assertAlmostEqual(b[0] - a[0], 3.0, places=9)
            self.assertAlmostEqual(b[1] - a[1], 3.0, places=9)

    def test_same_seed_reproduces(self) -> None:
        corner_sets = [
            detect_from_optical(
                truth_corners(), intrinsics(), noise=DetectionNoise(sigma_px=1.0), rng=random.Random(99)
            )["corners_px"]
            for _ in range(2)
        ]
        self.assertEqual(corner_sets[0], corner_sets[1], "同 seed 必须复现（回归要可复现）")


class MissTest(unittest.TestCase):
    """未检测必须**明确返回 None**，不能返回假角点。"""

    def test_dropped_frame(self) -> None:
        detected = detect_from_optical(
            truth_corners(), intrinsics(), noise=DetectionNoise(drop_frame_rate=1.0)
        )
        self.assertFalse(detected["detected"])
        self.assertEqual(detected["reason"], "dropped_frame")
        self.assertIsNone(detected["corners_px"])

    def test_corner_missing(self) -> None:
        detected = detect_from_optical(
            truth_corners(), intrinsics(), noise=DetectionNoise(drop_corner_rate=1.0)
        )
        self.assertFalse(detected["detected"])
        self.assertEqual(detected["reason"], "corner_missing")
        self.assertIsNone(detected["corners_px"])

    def test_too_close_is_unprojectable(self) -> None:
        # 标签贴在镜头前（z < z_min）：真实检测器也看不到
        near = corners_from_tag_pose((0.0, 0.0, 0.05), tag_size_m=TAG_SIZE_M)
        detected = detect_from_optical(near, intrinsics(), noise=DetectionNoise(), z_min=0.1)
        self.assertFalse(detected["detected"])
        self.assertEqual(detected["reason"], "unprojectable")

    def test_wrong_corner_count_is_reported(self) -> None:
        detected = detect_from_optical(truth_corners()[:3], intrinsics(), noise=DetectionNoise())
        self.assertFalse(detected["detected"])
        self.assertEqual(detected["reason"], "bad_input")


class ParamsTest(unittest.TestCase):
    def test_clamp_keeps_probabilities_in_range(self) -> None:
        clamped = DetectionNoise(sigma_px=-1.0, drop_frame_rate=2.0, drop_corner_rate=-3.0).clamped()
        self.assertEqual(clamped.sigma_px, 1.0)
        self.assertEqual(clamped.drop_frame_rate, 1.0)
        self.assertEqual(clamped.drop_corner_rate, 0.0)

    def test_out_of_range_rate_does_not_become_always_drop(self) -> None:
        # -3.0 夹到 0 之后**不应**恒丢帧；2.0 夹到 1 才恒丢帧
        never = detect_from_optical(
            truth_corners(), intrinsics(), noise=DetectionNoise(drop_corner_rate=-3.0)
        )
        self.assertTrue(never["detected"])
        always = detect_from_optical(
            truth_corners(), intrinsics(), noise=DetectionNoise(drop_corner_rate=2.0)
        )
        self.assertFalse(always["detected"])


class TagPoseCornersTest(unittest.TestCase):
    def test_center_and_span(self) -> None:
        corners = corners_from_tag_pose((0.0, 0.0, 2.0), tag_size_m=0.2)
        self.assertEqual(len(corners), CORNER_COUNT)
        us = [c[0] for c in corners]
        vs = [c[1] for c in corners]
        self.assertAlmostEqual(sum(us) / 4, 0.0, places=9)
        self.assertAlmostEqual(sum(vs) / 4, 0.0, places=9)
        self.assertAlmostEqual(max(us) - min(us), 0.2, places=9)
        self.assertAlmostEqual(max(vs) - min(vs), 0.2, places=9)

    def test_in_plane_rotation_swaps_span(self) -> None:
        rotated = corners_from_tag_pose((0.0, 0.0, 2.0), tag_size_m=0.2, in_plane_rotation_rad=1.5707963267948966)
        us = [c[0] for c in rotated]
        vs = [c[1] for c in rotated]
        self.assertAlmostEqual(max(us) - min(us), 0.2, places=9, msg="90° 旋转后 x 跨度不变")
        self.assertAlmostEqual(max(vs) - min(vs), 0.2, places=9)

    def test_corners_stay_at_tag_depth(self) -> None:
        corners = corners_from_tag_pose((0.0, 0.0, 1.5), tag_size_m=0.16)
        self.assertTrue(all(abs(c[2] - 1.5) < 1e-12 for c in corners))


if __name__ == "__main__":
    unittest.main()
