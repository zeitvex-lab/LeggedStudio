"""渲染 → 检测 → 位姿 闭环的测试。

**分两层**，这是刻意的：
* **几何层**（内参推导 / 坐标换算 / 阈值分割 / PNG 编码）**不需要 GL**，任何环境都跑；
* **渲染层**（真渲染一帧并与投影对齐）需要离屏 GL，不可用时 **skip**（不是 fail）。

这样即使 CI 容器没有 libOSMesa，链路里最容易错的那部分——坐标换算与相机模型——仍然被覆盖；
渲染只是"用同一台相机把同一件事画出来"。
"""

from __future__ import annotations

import math
import unittest

from backend.perception_pipeline import (
    SELFTEST_SCENE,
    bright_bbox,
    camera_intrinsics,
    perception_pipeline_selftest,
    png_bytes,
    render_and_detect,
    tag_corners_world,
    world_to_optical,
)


def compile_scene():
    import mujoco

    model = mujoco.MjModel.from_xml_string(SELFTEST_SCENE)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    camera_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, "front")
    tag_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "tag")
    return mujoco, model, data, camera_id, tag_id


def render_available() -> bool:
    from backend.gl_env import offscreen_render_status

    return offscreen_render_status()[0]


class IntrinsicsTest(unittest.TestCase):
    def test_fovy_becomes_vertical_focal(self) -> None:
        _, model, _, camera_id, _ = compile_scene()
        lens = camera_intrinsics(model, camera_id, 320, 240)
        expected = (240 / 2) / math.tan(math.radians(float(model.cam_fovy[camera_id])) / 2)
        self.assertAlmostEqual(lens["fy"], expected, places=9)
        self.assertAlmostEqual(lens["fx"], lens["fy"], places=9, msg="方形像素 ⇒ fx=fy")
        self.assertEqual((lens["cx"], lens["cy"]), (160.0, 120.0))

    def test_rejects_illegal_fovy(self) -> None:
        class FakeModel:
            cam_fovy = [0.0]

        with self.assertRaises(ValueError):
            camera_intrinsics(FakeModel(), 0, 320, 240)


class GeometryTest(unittest.TestCase):
    def test_mujoco_camera_frame_maps_to_optical(self) -> None:
        """MuJoCo 相机看 **−z**，而光学系看 **+z**：所以相机的"前方"点应在 optical +z。

        单位旋转时：世界 (0,0,-1)（相机正前方）→ optical (0,0,+1)；
        而世界 (0,0,+1)（相机背后）→ optical (0,0,−1)。
        """
        forward = world_to_optical([[0, 0, -1]], [0, 0, 0], [[1, 0, 0], [0, 1, 0], [0, 0, 1]])
        self.assertAlmostEqual(forward[0][2], 1.0, places=9, msg="前方点 optical z 应为正")
        backward = world_to_optical([[0, 0, 1]], [0, 0, 0], [[1, 0, 0], [0, 1, 0], [0, 0, 1]])
        self.assertAlmostEqual(backward[0][2], -1.0, places=9, msg="背后点 optical z 应为负")

    def test_y_axis_is_flipped(self) -> None:
        """相机系 y 向上 → 光学系 y 向下，符号必须相反。"""
        points = world_to_optical([[0, 0, -1]], [0, 0, 0], [[1, 0, 0], [0, 1, 0], [0, 0, 1]])
        self.assertAlmostEqual(points[0][1], -0.0, places=9)
        up = world_to_optical([[0, 0, 0]], [0, 1, 0], [[1, 0, 0], [0, 1, 0], [0, 0, 1]])
        self.assertAlmostEqual(up[0][1], 1.0, places=9, msg="相机上方的点光学系 y 应为正(向下为正)")

    def test_translation_is_subtracted(self) -> None:
        points = world_to_optical([[1, 2, 3]], [1, 2, 4], [[1, 0, 0], [0, 1, 0], [0, 0, 1]])
        self.assertAlmostEqual(points[0][0], 0.0, places=9)
        self.assertAlmostEqual(points[0][1], -0.0, places=9)
        self.assertAlmostEqual(points[0][2], 1.0, places=9)

    def test_tag_corners_follow_body_rotation(self) -> None:
        """自检场景里标签绕 x 轴转了 90° ⇒ 标签的 local y 跨度应转到**世界 z** 上。

        这条同时验证了"body 旋转被正确计入"——如果实现忽略了 ``xmat``，
        y 跨度会留在世界 y 上，这条就会红。
        """
        _, _, data, _, tag_id = compile_scene()
        corners = tag_corners_world(data, tag_id, 0.16)
        self.assertEqual(len(corners), 4)
        xs = [c[0] for c in corners]
        ys = [c[1] for c in corners]
        zs = [c[2] for c in corners]
        self.assertAlmostEqual(max(xs) - min(xs), 0.16, places=9, msg="local x 仍是世界 x")
        self.assertAlmostEqual(max(zs) - min(zs), 0.16, places=9, msg="local y 转到世界 z")
        self.assertAlmostEqual(max(ys) - min(ys), 0.0, places=9, msg="法向朝 −y，世界 y 无跨度")
        self.assertAlmostEqual(sum(xs) / 4, 0.0, places=9)
        self.assertAlmostEqual(sum(ys) / 4, 0.0, places=9)
        self.assertAlmostEqual(sum(zs) / 4, 0.6, places=9, msg="标签中心仍在 z=0.6")

    def test_tag_corners_reject_bad_input(self) -> None:
        _, _, data, _, tag_id = compile_scene()
        with self.assertRaises(ValueError):
            tag_corners_world(data, tag_id, 0.0)
        with self.assertRaises(ValueError):
            tag_corners_world(data, -1, 0.16)


class BrightBboxTest(unittest.TestCase):
    """阈值必须**自适应**：写死高阈值会把"光照下的白几何体"漏掉。"""

    def _frame(self, bright_value: int):
        import numpy as np

        frame = np.full((20, 30, 3), 8, dtype=np.uint8)
        frame[5:10, 10:15] = bright_value
        return frame

    def test_finds_block_at_typical_rendered_brightness(self) -> None:
        # MuJoCo 渲染的白色实测只有 ~190，而不是 255
        bbox = bright_bbox(self._frame(190))
        self.assertEqual(bbox, [10, 5, 14, 9])

    def test_flat_frame_has_no_block(self) -> None:
        import numpy as np

        self.assertIsNone(bright_bbox(np.full((10, 10, 3), 7, dtype=np.uint8)), "全平图不能把整幅当亮块")

    def test_explicit_threshold_still_supported(self) -> None:
        self.assertIsNone(bright_bbox(self._frame(190), threshold=250))
        self.assertEqual(bright_bbox(self._frame(190), threshold=100), [10, 5, 14, 9])


class PngTest(unittest.TestCase):
    def test_png_signature_and_size(self) -> None:
        import numpy as np

        frame = np.zeros((6, 8, 3), dtype=np.uint8)
        blob = png_bytes(frame)
        self.assertTrue(blob.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertIn(b"IHDR", blob[:32])
        self.assertGreater(len(blob), 40)


class RenderLoopTest(unittest.TestCase):
    """需要离屏 GL 的一层；没有 GL 就 skip（不是 fail——环境问题不该报成代码失败）。"""

    @classmethod
    def setUpClass(cls) -> None:
        if not render_available():
            raise unittest.SkipTest("离屏 GL 不可用（MUJOCO_GL 未启用 / 缺 libOSMesa）")

    def test_selftest_passes(self) -> None:
        report = perception_pipeline_selftest()
        self.assertEqual(report["verdict"], "pass", report)

    def test_rendered_block_matches_projection(self) -> None:
        """**核心断言**：渲染图里的标签亮块与几何投影出的四角必须对齐（同相机）。

        这是"检测框能不能画在图上的东西上面"的判据——不一致就说明渲染与投影用的不是同一台相机。
        """
        _, model, data, camera_id, tag_id = compile_scene()
        result = render_and_detect(
            model, data, camera_id=camera_id, tag_body_id=tag_id,
            tag_size_m=0.16, width=320, height=240,
        )
        self.assertNotIn("render_error", result, result.get("render_error"))
        bbox = result["bbox_px"]
        self.assertIsNotNone(bbox, "渲染图里应能找到标签亮块")
        us = [c[0] for c in result["truth_corners_px"]]
        vs = [c[1] for c in result["truth_corners_px"]]
        truth = (min(us), min(vs), max(us), max(vs))
        for index, (got, want) in enumerate(zip(bbox, truth)):
            self.assertLess(abs(got - want), 4.0, f"第 {index} 边偏差 {got} vs {want} 像素")

    def test_detection_noise_degrades_pose_not_geometry(self) -> None:
        """加噪后：检测角点会偏，但**真值角点**（几何）不变。"""
        import random

        from backend.synthetic_detector import DetectionNoise

        _, model, data, camera_id, tag_id = compile_scene()
        clean = render_and_detect(
            model, data, camera_id=camera_id, tag_body_id=tag_id,
            tag_size_m=0.16, width=320, height=240,
        )
        noisy = render_and_detect(
            model, data, camera_id=camera_id, tag_body_id=tag_id,
            tag_size_m=0.16, width=320, height=240,
            noise=DetectionNoise(sigma_px=2.0), rng=random.Random(3),
        )
        self.assertEqual(clean["truth_corners_px"], noisy["truth_corners_px"], "真值不受检测噪声影响")
        self.assertNotEqual(clean["detected_corners_px"], noisy["detected_corners_px"], "带噪检测应偏离")
        self.assertGreater(
            noisy["pose_optical"]["reprojection_error_px"],
            clean["pose_optical"]["reprojection_error_px"],
            "噪声应让重投影误差变大",
        )

    def test_reports_not_image_based(self) -> None:
        _, model, data, camera_id, tag_id = compile_scene()
        result = render_and_detect(
            model, data, camera_id=camera_id, tag_body_id=tag_id,
            tag_size_m=0.16, width=320, height=240,
        )
        self.assertFalse(result["image_based"], "必须自报：这是几何检测，不是图像识别")
        self.assertEqual(result["source"], "render+synthetic_detector")


class EndpointTest(unittest.TestCase):
    """HTTP 面：**几何结果永远给**，渲染失败只是"没图"，不是接口故障。"""

    @classmethod
    def setUpClass(cls) -> None:
        from fastapi.testclient import TestClient

        from backend.api_complete import app

        cls.client = TestClient(app)

    def post(self, **overrides):
        return self.client.post(
            "/api/perception/render/detect", json={"width": 160, "height": 120, **overrides}
        )

    def test_geometry_is_always_returned(self) -> None:
        response = self.post(include_image=False)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertFalse(body["image_based"], "必须自报：这是几何检测，不是图像识别")
        self.assertEqual(len(body["truth_corners_px"]), 4)
        self.assertNotIn("image_png_base64", body, "include_image=False 时不该带图")

    def test_render_failure_is_not_http_error(self) -> None:
        body = self.post().json()
        self.assertTrue(body["success"])
        has_image = "image_png_base64" in body
        has_reason = "render_error" in body
        self.assertTrue(has_image or has_reason, "要么给图，要么给出不可渲染的原因")
        if has_reason:
            self.assertIsInstance(body["render_error"], str)
            self.assertTrue(body["render_error"], "原因不能是空串")

    def test_unknown_camera_is_400(self) -> None:
        self.assertEqual(self.post(camera="no-such-camera").status_code, 400)

    def test_unknown_tag_body_is_400(self) -> None:
        self.assertEqual(self.post(tag_body="no-such-body").status_code, 400)

    def test_bad_mjcf_is_400(self) -> None:
        self.assertEqual(self.post(scene_xml="<not-mujoco/>").status_code, 400)

    def test_same_seed_reproduces(self) -> None:
        first = self.post(seed=5, sigma_px=1.5, include_image=False).json()["detected_corners_px"]
        second = self.post(seed=5, sigma_px=1.5, include_image=False).json()["detected_corners_px"]
        self.assertEqual(first, second, "同 seed 必须复现（否则回归没法当门禁）")


if __name__ == "__main__":
    unittest.main()
