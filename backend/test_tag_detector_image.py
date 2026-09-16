"""H31：从**像素**认标签 —— 可选依赖路径的端到端验证。

## 这组测试守的是什么

原清单把"不能从像素认标签"写成诚实边界（`registry/perception_providers/index.json` 里
`inputs.image` 标"**不支持**"）。H31 把它变成**可选依赖路径**：

1. **装了依赖就真认**：`detect_tag_corners(image)` 从图像里检出角点与 id；
2. **没装依赖仍然不认**（不伪造）：`image_detector_available()` 如实说缺哪些包，
   传 `image` 得到明确报错而不是编出来的角点；
3. **去畸变按档位声明的模型**（`pinhole` / `brown_conrady` / `fisheye_equidistant`），不在这里猜。

**怎么验"真认"**（不靠人眼看）：用**本仓自己的投影数学**（`backend/camera_projection.py`）
把已知位姿下标签的四角投到像素 → 生成真实 AprilTag 图案并用透视变换贴到那四个角上 →
再让检测器从这张合成图里找角点 → **与投影得到的角点逐点比对**（Ground truth 来自投影，
不是来自检测器自己）。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.camera_projection import camera_profile, camera_profile_intrinsics, project_optical_points  # noqa: E402
from backend.perception_providers.tag_detector import (  # noqa: E402
    CORNER_ORDER,
    DEFAULT_TAG_FAMILY,
    detect_tag_corners,
    image_detector_available,
    undistort_image,
)

FAMILY = "DICT_APRILTAG_36h11"
TAG_SIZE_M = 0.16


def _cv2():
    cv2 = __import__("cv2")
    if not hasattr(cv2, "aruco"):
        raise unittest.SkipTest("cv2 没有 aruco（需要 opencv-contrib，不是 opencv-python）")
    return cv2


def _render_tag(intrinsics: dict, pose: dict) -> tuple[np.ndarray, list[list[float]]]:
    """按已知位姿把标签渲染进一张合成图，返回 (BGR 图像, 投影得到的角点 —— Ground truth)。"""

    cv2 = _cv2()
    half = TAG_SIZE_M / 2.0
    local = np.array([[-half, -half, 0.0], [half, -half, 0.0], [half, half, 0.0], [-half, half, 0.0]])
    rotation = np.asarray(pose["rotation"], dtype=float)
    translation = np.asarray(pose["translation"], dtype=float)
    optical = [tuple(rotation @ point + translation) for point in local]
    projected = project_optical_points(optical, intrinsics)
    truth = [[float(item["u"]), float(item["v"])] for item in projected]
    if not all(item["valid"] for item in projected):
        raise unittest.SkipTest("这套位姿不落在画幅内")

    width = int(intrinsics.get("width") or 1920)
    height = int(intrinsics.get("height") or 1080)
    image = np.full((height, width, 3), 235, dtype=np.uint8)

    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, FAMILY))
    side = 320
    # **静默区**：生成的标记图只有黑白方格本身，直接贴到浅灰背景上检测不稳定 ——
    # 真实场景里标签周围本来就有白边，这里按同样口径补上（否则是"测试夹具不真实"，不是检测器不行）。
    margin = 80
    marker = cv2.aruco.generateImageMarker(dictionary, 7, side)
    marker = cv2.copyMakeBorder(marker, margin, margin, margin, margin, cv2.BORDER_CONSTANT, value=255)
    marker_bgr = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
    source = np.array([
        [margin, margin], [margin + side - 1, margin],
        [margin + side - 1, margin + side - 1], [margin, margin + side - 1],
    ], dtype=np.float32)
    target = np.asarray(truth, dtype=np.float32)
    transform = cv2.getPerspectiveTransform(source, target)
    warped = cv2.warpPerspective(marker_bgr, transform, (width, height), flags=cv2.INTER_LINEAR)
    mask = cv2.warpPerspective(np.full(marker.shape[:2], 255, dtype=np.uint8), transform, (width, height))
    image[mask > 0] = warped[mask > 0]
    return image, truth


class AvailabilityTest(unittest.TestCase):
    """可用性如实汇报（这条不依赖装没装：两种环境都要过）。"""

    def test_reports_each_optional_package(self):
        state = image_detector_available()
        self.assertEqual({"cv2", "apriltag", "pupil_apriltags"}, set(state["packages"]))
        if not state["available"]:
            self.assertIn("不伪造检测结果", state["hint"])

    def test_missing_dependency_is_an_explicit_error_not_a_fake_corner(self):
        """没装依赖时必须**明确报错**（这是原清单的诚实边界，H31 不拆掉它）。"""

        from backend.perception_providers import tag_detector

        original = tag_detector.image_detector_available
        try:
            tag_detector.image_detector_available = lambda: {
                "available": False, "packages": {"cv2": False, "apriltag": False, "pupil_apriltags": False},
                "hint": "未安装",
            }
            with self.assertRaises(ValueError) as context:
                detect_tag_corners(np.zeros((10, 10), dtype=np.uint8), intrinsics={})
        finally:
            tag_detector.image_detector_available = original
        message = str(context.exception)
        self.assertIn("可选依赖", message)
        self.assertIn("不伪造检测结果", message)

    def test_undistort_dispatches_on_the_declared_model(self):
        """档位声明 `pinhole` 且无系数 ⇒ 原样返回（不无谓地过一遍 cv2）。"""

        intrinsics = camera_profile_intrinsics(camera_profile("ideal-pinhole-1920x1080"))
        image = np.zeros((8, 8, 3), dtype=np.uint8)
        self.assertIs(image, undistort_image(image, intrinsics))


class DetectFromPixelsTest(unittest.TestCase):
    """装了依赖就真认：合成图 → 角点与 id，与**投影得到的**真值逐点比对。"""

    def setUp(self):
        state = image_detector_available()
        if not state["packages"]["cv2"]:
            self.skipTest("没有 cv2（可选依赖未安装）")

    def test_corners_and_id_match_the_projection_ground_truth(self):
        intrinsics = camera_profile_intrinsics(camera_profile("ideal-pinhole-1920x1080"))
        pose = {"rotation": np.eye(3), "translation": np.array([0.02, -0.01, 1.5])}
        image, truth = _render_tag(intrinsics, pose)

        result = detect_tag_corners(image, intrinsics=intrinsics, tag_family=FAMILY)
        self.assertIsNotNone(result["corners_px"], "没能从合成图里检出标签")
        self.assertEqual(7, result["tag_id"])
        self.assertEqual("cv2.aruco", result["backend"])
        for index, (found, expected) in enumerate(zip(result["corners_px"], truth)):
            distance = float(np.hypot(found[0] - expected[0], found[1] - expected[1]))
            self.assertLess(distance, 2.0, f"第 {index} 个角点（{CORNER_ORDER[index]}）差 {distance:.2f}px")

    def test_detected_corners_feed_the_pose_solver(self):
        """检出结果**能直接喂给既有几何**：角点 → `pose_from_corners` 解出的位姿应接近真值。"""

        from backend.perception_providers.tag_detector import pose_from_corners

        intrinsics = camera_profile_intrinsics(camera_profile("ideal-pinhole-1920x1080"))
        pose = {"rotation": np.eye(3), "translation": np.array([0.0, 0.0, 1.2])}
        image, _ = _render_tag(intrinsics, pose)
        detection = detect_tag_corners(image, intrinsics=intrinsics, tag_family=FAMILY)
        solved = pose_from_corners(detection["corners_px"], intrinsics, TAG_SIZE_M)
        self.assertAlmostEqual(1.2, float(solved["position_optical"][2]), delta=0.05)
        self.assertLess(float(solved["reprojection_error_px"]), 1.0)

    def test_empty_scene_reports_no_detection_without_raising(self):
        """画面里没有标签 ⇒ `corners_px=None`（**不是错误**：丢帧判定要靠这个状态）。"""

        intrinsics = camera_profile_intrinsics(camera_profile("ideal-pinhole-1920x1080"))
        blank = np.full((480, 640, 3), 255, dtype=np.uint8)
        result = detect_tag_corners(blank, intrinsics=intrinsics, tag_family=FAMILY)
        self.assertIsNone(result["corners_px"])
        self.assertIsNone(result["tag_id"])
        self.assertEqual([], result["candidates"])


class ProviderImageBranchTest(unittest.TestCase):
    """provider 的 `update({"image": …})` 分支：装了依赖走真检测，读数里写明"这帧怎么来的"。"""

    def setUp(self):
        if not image_detector_available()["packages"]["cv2"]:
            self.skipTest("没有 cv2（可选依赖未安装）")

    def _detector(self):
        from backend.perception_providers.tag_detector import TagDetector

        detector = TagDetector()
        detector.init({
            "camera_profile_id": "ideal-pinhole-1920x1080", "sensor_id": "camera",
            "tag_size_m": TAG_SIZE_M, "standoff_m": 1.0,
            "kp_dist": 0.8, "kp_yaw": 1.2, "max_vx": 0.5, "max_back_mps": 0.3, "max_wz": 0.8,
            "yaw_gate_deg": 8.0, "actions": {"detected": {"kind": "dock"}, "lost": {"kind": "hold"}},
        })
        return detector

    def test_image_reading_is_detected_and_labelled(self):
        intrinsics = camera_profile_intrinsics(camera_profile("ideal-pinhole-1920x1080"))
        image, _ = _render_tag(intrinsics, {"rotation": np.eye(3), "translation": np.array([0.0, 0.0, 1.0])})
        detector = self._detector()
        reading = detector.update({"image": image, "tag_family": FAMILY}, time_s=0.0)
        self.assertTrue(reading["detected"])
        self.assertEqual("image:cv2.aruco", reading["detected_from"])
        self.assertIsNotNone(reading["pose"])
        detector.on_reset()
        self.assertIsNone(detector.last_reading)


if __name__ == "__main__":
    unittest.main()
