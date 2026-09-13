"""tag（视觉基准标签）位姿估计 + 停靠伺服测试。

守什么：

1. **逆解要与正投影自洽（往返校验）**：用本仓既有的 `project_optical_points` 把已知位姿的
   标签投影成角点，再交给 `pose_from_corners` 解回去——位置/朝向必须一致，重投影误差≈0。
   这是"同一套几何、两个方向"的交叉验证，比各算各的可信。
2. **畸变不静默**：档位带畸变系数且角点未去畸变 ⇒ 报错（不按理想针孔悄悄算）。
3. **停靠判据取 H10**：`visual_dock_arrival` 的 3 cm/3 cm/2.5° 与丢帧 0.7/2.5 s 必须生效，
   到位即停（指令归零）、丢失即停并累计丢帧。
4. **图像检测不伪造**：传原始图像 ⇒ 明确报错并点名可选依赖。
5. **伺服律**：远则前进、太近则后退（不超 max_back）、大偏航先原地转。
"""

from __future__ import annotations

import math
import unittest

import numpy as np
from fastapi.testclient import TestClient

from backend.api_complete import app
from backend.arrival_criteria import visual_dock_spec
from backend.camera_projection import camera_profile, camera_profile_intrinsics, project_optical_points
from backend.perception_providers import provider_spec, resolve_provider
from backend.perception_providers.tag_detector import (
    TagDetector,
    distortion_required,
    image_detector_available,
    pose_from_corners,
    visual_servo_command,
)

PINHOLE = "ideal-pinhole-1920x1080"
FISHEYE = "go2-front-fisheye-1920x1080"
TAG_SIZE = 0.16


def intrinsics(profile_id: str = PINHOLE) -> dict:
    return camera_profile_intrinsics(camera_profile(profile_id))


def corners_for(position_optical, *, profile_id: str = PINHOLE, tag_size_m: float = TAG_SIZE,
                rotation=None, intrinsics_override: dict | None = None) -> list[list[float]]:
    """正向投影：已知标签位姿（相机光学系）⇒ 角点像素（顺序 tl,tr,br,bl）。"""
    half = tag_size_m / 2.0
    local = [(-half, -half, 0.0), (half, -half, 0.0), (half, half, 0.0), (-half, half, 0.0)]
    rot = np.eye(3) if rotation is None else np.asarray(rotation, dtype=float)
    points = [tuple(rot @ np.asarray(point, dtype=float) + np.asarray(position_optical, dtype=float))
              for point in local]
    projected = project_optical_points(points, intrinsics_override or intrinsics(profile_id))
    return [[item["u"], item["v"]] for item in projected]


class PoseFromCornersTests(unittest.TestCase):
    def test_round_trip_translation_only(self):
        pose = pose_from_corners(corners_for((0.02, -0.01, 1.2)), intrinsics(), TAG_SIZE)
        np.testing.assert_allclose(pose["position_optical"], [0.02, -0.01, 1.2], atol=1e-6)
        np.testing.assert_allclose(pose["rotation_optical"], np.eye(3), atol=1e-6)
        self.assertLess(pose["reprojection_error_px"], 1e-6)
        self.assertAlmostEqual(pose["in_plane_rotation_rad"], 0.0, places=6)

    def test_round_trip_in_plane_rotation(self):
        angle = math.radians(30.0)
        rot_z = [[math.cos(angle), -math.sin(angle), 0.0],
                 [math.sin(angle), math.cos(angle), 0.0],
                 [0.0, 0.0, 1.0]]
        pose = pose_from_corners(corners_for((0.0, 0.0, 0.9), rotation=rot_z), intrinsics(), TAG_SIZE)
        np.testing.assert_allclose(pose["position_optical"], [0.0, 0.0, 0.9], atol=1e-6)
        self.assertAlmostEqual(pose["in_plane_rotation_rad"], angle, places=6)
        self.assertLess(pose["reprojection_error_px"], 1e-6)

    def test_tilted_tag_reprojects_cleanly(self):
        """倾斜标签存在单应分解的二义性，故断言"重投影干净 + 距离量级对"，不硬比姿态。"""
        tilt = math.radians(15.0)
        rot_y = [[math.cos(tilt), 0.0, math.sin(tilt)],
                 [0.0, 1.0, 0.0],
                 [-math.sin(tilt), 0.0, math.cos(tilt)]]
        pose = pose_from_corners(corners_for((0.0, 0.0, 1.0), rotation=rot_y), intrinsics(), TAG_SIZE)
        self.assertLess(pose["reprojection_error_px"], 0.5)
        self.assertAlmostEqual(pose["position_optical"][2], 1.0, delta=0.05)

    def test_scale_is_tied_to_tag_size(self):
        """同样的角点、标签边长翻倍 ⇒ 距离翻倍（标定输入必须真的参与计算）。"""
        corners = corners_for((0.0, 0.0, 0.8))
        near = pose_from_corners(corners, intrinsics(), 0.16)["position_optical"][2]
        far = pose_from_corners(corners, intrinsics(), 0.32)["position_optical"][2]
        self.assertAlmostEqual(far / near, 2.0, places=5)

    def test_distorted_profile_requires_undistortion(self):
        self.assertTrue(distortion_required(intrinsics(FISHEYE)))
        corners = corners_for((0.0, 0.0, 1.0), profile_id=FISHEYE)
        with self.assertRaises(ValueError) as ctx:
            pose_from_corners(corners, intrinsics(FISHEYE), TAG_SIZE)
        self.assertIn("去畸变", str(ctx.exception))
        # 显式声明已去畸变才放行（仍按理想针孔算）
        pose = pose_from_corners(corners, intrinsics(FISHEYE), TAG_SIZE, undistorted=True)
        self.assertLess(pose["reprojection_error_px"], 5.0)

    def test_bad_input_is_rejected(self):
        with self.assertRaises(ValueError):
            pose_from_corners([[0.0, 0.0], [1.0, 0.0]], intrinsics(), TAG_SIZE)
        with self.assertRaises(ValueError):
            pose_from_corners(corners_for((0, 0, 1.0)), intrinsics(), 0.0)


class VisualServoTests(unittest.TestCase):
    def setUp(self):
        self.params = provider_spec("tag_detector").params

    def test_far_tag_drives_forward(self):
        command = visual_servo_command((2.0, 0.0, 0.1), 0.0, params=self.params)
        self.assertGreater(command[0], 0.0)
        self.assertLessEqual(command[0], float(self.params["max_vx"]))
        self.assertEqual(command[2], 0.0)

    def test_too_close_backs_off_within_limit(self):
        command = visual_servo_command((0.05, 0.0, 0.1), 0.0, params=self.params)
        self.assertLess(command[0], 0.0)
        self.assertGreaterEqual(command[0], -float(self.params["max_back_mps"]))

    def test_large_bearing_turns_in_place(self):
        yaw_error = math.radians(float(self.params["yaw_gate_deg"]) + 10.0)
        command = visual_servo_command((1.0, 0.5, 0.1), yaw_error, params=self.params)
        self.assertEqual(command[0], 0.0, "偏航超门限 ⇒ 先原地转")
        self.assertGreater(command[2], 0.0)
        self.assertLessEqual(abs(command[2]), float(self.params["max_wz"]))


class TagProviderTests(unittest.TestCase):
    def setUp(self):
        self.provider = resolve_provider("tag_detector")

    def test_detects_tag_ahead_in_base_frame(self):
        # 机身前方 1.2 m、与相机同高（相机在 base_link z=0.1）⇒ 机身系 (1.2, 0, 0.1)
        reading = self.provider.update(
            {"tag_id": "dock_a", "corners_px": corners_for((0.0, 0.0, 1.2))}, 0.0
        )
        self.assertTrue(reading["detected"])
        self.assertEqual(reading["tag_id"], "dock_a")
        self.assertAlmostEqual(reading["position_base"]["x"], 1.2, places=5)
        self.assertAlmostEqual(reading["position_base"]["y"], 0.0, places=5)
        self.assertAlmostEqual(reading["position_base"]["z"], 0.1, places=5)
        self.assertAlmostEqual(reading["distance_m"], 1.2, places=5)
        self.assertAlmostEqual(reading["bearing_rad"], 0.0, places=5)
        self.assertFalse(reading["dock"]["docked"])
        self.assertEqual(reading["action"]["kind"], "visual_servo")
        self.assertGreater(reading["servo_cmd"][0], 0.0, "还没到 standoff ⇒ 应给前进指令")

    def test_docked_tag_stops(self):
        standoff = float(provider_spec("tag_detector").params["standoff_m"])
        reading = self.provider.update({"corners_px": corners_for((0.0, 0.0, standoff))}, 0.0)
        self.assertTrue(reading["dock"]["docked"], reading["dock"]["reasons"])
        self.assertEqual(reading["servo_cmd"], [0.0, 0.0, 0.0], "停靠到位必须停")
        self.assertEqual(reading["action"]["kind"], "stop")
        spec = visual_dock_spec()
        self.assertEqual(reading["dock_thresholds"]["lateral_tolerance_m"], spec["lateral_tolerance_m"])
        self.assertEqual(reading["thresholds_source"], "registry/arrival_criteria.json#visual_dock")

    def test_lateral_offset_produces_bearing(self):
        reading = self.provider.update({"corners_px": corners_for((0.2, 0.0, 1.0))}, 0.0)
        # 标签在机身右侧（光学系 +x = 机身 -y）⇒ bearing 为负（需右转）
        self.assertLess(reading["bearing_rad"], 0.0)
        self.assertAlmostEqual(reading["position_base"]["y"], -0.2, places=5)
        self.assertTrue(any("横向偏差" in reason for reason in reading["dock"]["reasons"]))

    def test_lost_frames_accumulate_and_stop(self):
        first = self.provider.update({}, 0.0)
        self.assertFalse(first["detected"])
        self.assertEqual(first["servo_cmd"], [0.0, 0.0, 0.0])
        self.assertFalse(first["dock"]["lost"], "刚开始丢帧不该立刻判失败（H10 有 0.7/2.5 s 阶梯）")
        later = self.provider.update({}, float(visual_dock_spec()["lose_confirm_s"]) + 0.1)
        self.assertTrue(later["dock"]["lost"])
        self.assertFalse(later["dock"]["docked"])
        self.assertEqual(later["action"]["kind"], "stop")

    def test_image_input_is_refused_not_faked(self):
        with self.assertRaises(ValueError) as ctx:
            self.provider.update({"image": [[0, 0], [1, 1]]}, 0.0)
        message = str(ctx.exception)
        self.assertIn("可选依赖", message)
        self.assertIn("corners_px", message)

    def test_registry_entry_is_honest(self):
        spec = provider_spec("tag_detector")
        self.assertEqual(spec.sensor, "rgb")
        self.assertTrue(spec.params["evidence"]["sources"], "参数必须带来源")
        self.assertIn("opencv-contrib-python", [
            package for package in ["opencv-contrib-python", "apriltag"]
        ])
        availability = image_detector_available()
        self.assertFalse(availability["available"], "当前环境未装图像检测依赖，必须如实报告")

    def test_missing_params_rejected(self):
        provider = TagDetector()
        with self.assertRaises(ValueError) as ctx:
            provider.init({"tag_size_m": 0.16})
        self.assertIn("camera_profile_id", str(ctx.exception))


class TagEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_endpoint_returns_pose_and_servo(self):
        response = self.client.post("/api/perception/tag/evaluate", json={
            "tag_id": "dock_a", "corners_px": corners_for((0.0, 0.0, 1.2)),
        })
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["reading"]["tag_id"], "dock_a")
        self.assertGreater(payload["reading"]["servo_cmd"][0], 0.0)
        self.assertIn("检测器输出的角点", payload["note"])

    def test_endpoint_rejects_distorted_profile_without_undistortion(self):
        response = self.client.post("/api/perception/tag/evaluate", json={
            "corners_px": corners_for((0.0, 0.0, 1.0), profile_id=FISHEYE),
            "camera_profile_id": FISHEYE,
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("去畸变", response.json()["detail"])

    def test_endpoint_rejects_wrong_corner_count(self):
        response = self.client.post("/api/perception/tag/evaluate", json={"corners_px": [[0, 0], [1, 1]]})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
