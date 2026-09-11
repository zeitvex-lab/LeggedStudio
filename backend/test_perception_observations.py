"""Tests for the generic perception observation catalog (Feature 6).

Also covers the MATRiX v1.0.13 derived external sensor suite
(:mod:`backend.sensor_suite`) and the sensor-corpus container probe
(:mod:`tools.matrix_sensor_corpus`), which are the two pieces the advanced
simulation surface consumes from that release.
"""

from __future__ import annotations

import math
import struct
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api_complete import app
from backend.perception_observations import PERCEPTION_ITEMS, list_perception_items

try:  # 语料工具是脚本模块（无 __init__.py），导入失败时跳过对应用例
    from tools.matrix_sensor_corpus import probe_container, probe_corpus
except ImportError:  # pragma: no cover
    probe_container = None  # type: ignore[assignment]
    probe_corpus = None  # type: ignore[assignment]

try:  # MuJoCo 交叉校验用例需要引擎；缺失时跳过（CI 侧 requirements 已含 mujoco==3.11.0）
    import mujoco  # noqa: F401

    _MUJOCO_OK = True
except ImportError:  # pragma: no cover
    _MUJOCO_OK = False


class PerceptionCatalogTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_catalog_contains_perception_pipeline(self):
        ids = [item["id"] for item in list_perception_items()]
        # The three perception stages must be present as generic items.
        for required in ("foot_contact", "heightfield", "depth_camera"):
            self.assertIn(required, ids)

    def test_items_endpoint(self):
        payload = self.client.get("/api/perception/items").json()
        self.assertTrue(payload["success"])
        items = payload["items"]
        self.assertGreaterEqual(payload["count"], 6)
        by_id = {item["id"]: item for item in items}
        self.assertEqual(by_id["depth_camera"]["width"], 6360)
        self.assertEqual(by_id["depth_camera"]["sensor"], "depth_camera")
        self.assertEqual(by_id["foot_contact"]["width"], 4)
        self.assertIn("106", str(by_id["depth_camera"].get("meta")))

    def test_single_item_endpoint(self):
        payload = self.client.get("/api/perception/items/depth_camera").json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["item"]["id"], "depth_camera")
        self.assertEqual(payload["item"]["sample_dot_path"], "environment.observations.actor.terms.depth_scan")

    def test_unknown_item_404(self):
        response = self.client.get("/api/perception/items/nope")
        self.assertEqual(response.status_code, 404)

    def test_required_items_have_width_and_scale(self):
        for item in PERCEPTION_ITEMS.values():
            self.assertGreater(item.width, 0)
            self.assertGreater(item.scale, 0)
            self.assertTrue(item.sample_dot_path)


if __name__ == "__main__":
    unittest.main()


class ObsSourceChoicesTest(unittest.TestCase):
    """Feature 11：观测来源三选一向导的编目与端点测试。"""

    def setUp(self):
        self.client = TestClient(app)

    def test_base_lin_vel_declares_obs_source(self):
        items = {item["id"]: item for item in list_perception_items()}
        blv = items["base_lin_vel"]
        self.assertEqual(blv["obs_source"], "estimator")
        self.assertIn("proxy", blv["meta"].get("observable", ""))

    def test_obs_sources_endpoint(self):
        payload = self.client.get("/api/perception/obs-sources").json()
        self.assertTrue(payload["success"])
        values = [c["value"] for c in payload["choices"]]
        self.assertEqual(values, ["estimator", "proxy", "history"])

    def test_items_endpoint_carries_obs_source(self):
        payload = self.client.get("/api/perception/items").json()
        blv = [i for i in payload["items"] if i["id"] == "base_lin_vel"][0]
        self.assertIn("obs_source", blv)


class MatrixSensorSuiteTests(unittest.TestCase):
    """MATRiX v1.0.13 外部传感器套件抽取（高级仿真的传感器契约）。"""

    def setUp(self):
        self.client = TestClient(app)

    def test_default_suite_matches_release_declarations(self):
        from backend.sensor_suite import default_sensor_suite

        suite = {sensor["kind"]: sensor for sensor in default_sensor_suite()}
        self.assertEqual(set(suite), {"imu", "odom", "rgb", "depth", "lidar"})
        self.assertEqual(suite["imu"]["frequency_hz"], 500)
        self.assertEqual(suite["odom"]["frequency_hz"], 100)
        self.assertEqual(suite["lidar"]["frequency_hz"], 10)
        self.assertEqual(suite["lidar"]["sensor_type"], "airy")
        self.assertEqual(suite["rgb"]["intrinsics"]["width"], 1920)
        self.assertEqual(suite["depth"]["intrinsics"]["fov_deg"], 120)
        self.assertFalse(suite["depth"]["meta"]["cloudmode"])

    def test_presets_endpoint_lists_matriX_presets(self):
        payload = self.client.get("/api/sensors/presets").json()
        self.assertTrue(payload["success"])
        names = [preset["name"] for preset in payload["presets"]]
        for required in ("default", "lidar_dual", "mid360_slam", "zg"):
            self.assertIn(required, names)
        # 平台成像变体已按 RL 口径剔除，不再出现在契约里
        for dropped in ("fisheye", "infrared", "panorama", "ptzrgb"):
            self.assertNotIn(dropped, names)
        default = [p for p in payload["presets"] if p["name"] == "default"][0]
        self.assertEqual(default["sensor_count"], 5)  # imu + odom + rgb + depth + lidar
        self.assertEqual(default["exteroceptive_count"], 3)  # rgb + depth + lidar
        self.assertEqual(len(names), 4)

    def test_single_preset_endpoint_and_unknown_404(self):
        payload = self.client.get("/api/sensors/presets/mid360_slam").json()
        self.assertTrue(payload["success"])
        kinds = {sensor["kind"] for sensor in payload["sensors"]}
        self.assertEqual(kinds, {"lidar", "odom", "imu"})
        self.assertEqual(self.client.get("/api/sensors/presets/nope").status_code, 404)

    def test_kinds_endpoint_classifies_proprio_and_extero(self):
        payload = self.client.get("/api/sensors/kinds").json()
        classes = {entry["kind"]: entry["class"] for entry in payload["kinds"]}
        self.assertEqual(classes["imu"], "proprioceptive")
        self.assertEqual(classes["odom"], "proprioceptive")
        self.assertEqual(classes["lidar"], "exteroceptive")
        self.assertEqual(classes["depth"], "exteroceptive")
        # RL 口径的 5 类：imu / odom / rgb / depth / lidar（gps 已按同一口径剔除）
        self.assertEqual(set(classes), {"imu", "odom", "rgb", "depth", "lidar"})
        self.assertNotIn("gps", classes)

    def test_lidar_height_scan_reuses_heightfield_grid(self):
        items = {item["id"]: item for item in list_perception_items()}
        lidar_scan = items["lidar_height_scan"]
        self.assertEqual(lidar_scan["sensor"], "lidar")
        self.assertEqual(lidar_scan["width"], items["heightfield"]["width"])
        self.assertEqual(lidar_scan["meta"]["align_with"], "heightfield")
        self.assertTrue(lidar_scan["sample_dot_path"])


@unittest.skipIf(probe_container is None, "tools.matrix_sensor_corpus 不可导入")
class MatrixSensorCorpusTests(unittest.TestCase):
    """MATRiX 传感器语料的容器探测（合成容器，不需要发行包）。"""

    def _synthetic(self, directory: Path, suffix: str, frames: int = 5, frame_size: int = 1024) -> Path:
        header_size = 348 if suffix == ".mid360bin" else 352
        header = bytearray(header_size)
        header[:4] = b"M3D1" if suffix == ".mid360bin" else b"ARY1"
        struct.pack_into("<I", header, 4, 2 if suffix == ".mid360bin" else 1)
        struct.pack_into("<I", header, 12, frame_size)
        path = directory / f"sample{suffix}"
        path.write_bytes(bytes(header) + bytes(frames * frame_size))
        return path

    def test_probe_recovers_framing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._synthetic(Path(tmp), ".airybin")
            record = probe_container(path)
            self.assertTrue(record["consistent"])
            self.assertEqual(record["magic"], "ARY1")
            self.assertEqual(record["frames"], 5)
            self.assertEqual(record["body_offset"], 352)
            self.assertEqual(record["frame_size"], 1024)

    def test_probe_rejects_unknown_magic(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.airybin"
            path.write_bytes(b"XXXX" + bytes(1024))
            record = probe_container(path)
            self.assertFalse(record["consistent"])
            self.assertIsNone(record["lidar_type"])

    def test_missing_file_degrades_instead_of_raising(self):
        record = probe_container(Path("/nonexistent/definitely-not-here.airybin"))
        self.assertFalse(record["exists"])
        self.assertFalse(record["consistent"])

    def test_shipped_corpus_is_consistent_when_present(self):
        records = probe_corpus(Path("matrix-v1.0.13/extracted/MATRiX_v1.0.13"))
        self.assertEqual(len(records), 2)
        if any(record["exists"] for record in records):
            self.assertTrue(all(record["consistent"] for record in records))


class SensorKindCoverageTests(unittest.TestCase):
    """感知目录的 sensor 名要么是已登记硬件 kind，要么是明确的派生观测源。"""

    # 派生观测源：由 MJCF 接触、内置高度场与渲染深度派生，不是硬件 kind。
    DERIVED_SOURCES = ("proprio", "foot_contact", "heightfield", "depth_camera")

    def test_perception_sensors_are_derived_or_registered_hardware(self):
        from backend.sensor_suite import SENSOR_KIND_CLASSES

        for item in PERCEPTION_ITEMS.values():
            self.assertTrue(
                item.sensor in SENSOR_KIND_CLASSES or item.sensor in self.DERIVED_SOURCES,
                f"{item.id} 的 sensor={item.sensor} 既不是已登记硬件 kind，也不在派生源清单中",
            )

    def test_derived_sources_do_not_collide_with_hardware_kinds(self):
        from backend.sensor_suite import SENSOR_KIND_CLASSES

        self.assertFalse(set(self.DERIVED_SOURCES) & set(SENSOR_KIND_CLASSES))


class ActuatorObservationsTests(unittest.TestCase):
    """补齐训练侧高频但原先缺项的三个观测：joint_torque / contact_force / wheel_vel。"""

    def test_joint_torque_mirrors_joint_width(self):
        items = {item["id"]: item for item in list_perception_items()}
        torque = items["joint_torque"]
        self.assertEqual(torque["sensor"], "proprio")
        self.assertEqual(torque["width"], items["joint_pos"]["width"])
        self.assertEqual(torque["meta"]["engine_sensor"], "jointactuatorfrc")
        self.assertTrue(torque["sample_dot_path"])

    def test_contact_force_pairs_with_foot_contact(self):
        items = {item["id"]: item for item in list_perception_items()}
        force = items["contact_force"]
        self.assertEqual(force["sensor"], "foot_contact")
        self.assertEqual(force["width"], items["foot_contact"]["width"])
        self.assertEqual(force["meta"]["reduce"], "netforce")
        self.assertIn("force", force["meta"]["fields"])

    def test_wheel_vel_is_wheeled_only(self):
        items = {item["id"]: item for item in list_perception_items()}
        wheel = items["wheel_vel"]
        self.assertEqual(wheel["width"], 4)
        self.assertEqual(wheel["meta"]["joint_pattern"], ".*_wheel_joint")
        for robot in ("unitree_go2w", "unitree_b2w", "deeprobotics_m20", "limx_tron1_wf", "zex-w"):
            self.assertIn(robot, wheel["meta"]["applies_to"])


@unittest.skipUnless(_MUJOCO_OK, "mujoco 不可导入")
class CameraProjectionMujocoTests(unittest.TestCase):
    """用 MuJoCo 原生 <camprojection> 交叉校验针孔投影（引擎独立实现，非自洽性测试）。"""

    def setUp(self):
        self.client = TestClient(app)

    def test_default_mount_matches_mujoco(self):
        from backend.camera_projection import mujoco_camprojection_check

        report = mujoco_camprojection_check()
        self.assertTrue(report["available"])
        self.assertEqual(report["verdict"], "pass", report["rows"])
        self.assertGreaterEqual(report["compared"], 6)
        self.assertLessEqual(report["max_abs_du"], report["tolerance_px"])
        self.assertLessEqual(report["max_abs_dv"], report["tolerance_px"])
        # 被剔除的「相机后方」点必须显式记录
        self.assertTrue(any(row.get("skipped") for row in report["rows"]))

    def test_rotated_mount_matches_mujoco(self):
        from backend.camera_projection import mujoco_camprojection_check

        sensor = {"position": {"x": 0.1, "y": 0.0, "z": 0.2}, "rotation": {"yaw": 90.0}, "mount": "base_link"}
        points = ((2.0, 0.0, 0.2), (0.0, 2.0, 0.2), (0.0, 2.0, 0.6), (1.5, 0.2, 0.2))
        report = mujoco_camprojection_check(sensor=sensor, points=points)
        self.assertEqual(report["verdict"], "pass", report["rows"])
        # yaw=90 时相机朝机身 +y 看：(2,0,0.2) 与视线垂直 → 落在相机后方/侧面被剔除
        self.assertEqual(report["compared"], 3)
        self.assertEqual(sum(1 for row in report["rows"] if row.get("skipped")), 1)

    def test_camera_pose_mapping_is_documented_transform(self):
        from backend.camera_projection import mujoco_camera_pose

        pose = mujoco_camera_pose({"position": {}, "rotation": {}, "mount": "base_link"})
        # 单位安装：相机三轴在安装系下 X=(0,-1,0) Y=(0,0,1) Z=(-1,0,0)
        self.assertEqual(
            [[round(value, 9) for value in row] for row in pose["axis_matrix"]],
            [[0.0, 0.0, -1.0], [-1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        )
        norm = sum(value * value for value in pose["quat"]) ** 0.5
        self.assertAlmostEqual(norm, 1.0, places=12)

    def test_mujoco_check_endpoint(self):
        payload = self.client.get("/api/perception/projection/mujoco-check").json()
        if payload.get("available") is False:
            self.skipTest(payload.get("reason"))
        self.assertEqual(payload["verdict"], "pass")


class HeightScanAlignmentTests(unittest.TestCase):
    """机身高度扫描网格契约（187 点）与「点云 vs 射线」逐格对齐回归。"""

    def setUp(self):
        self.client = TestClient(app)

    def test_grid_matches_upstream_measured_points(self):
        from backend.height_scan import GRID_POINTS, MEASURED_POINTS_X, MEASURED_POINTS_Y, grid_spec

        spec = grid_spec()
        self.assertEqual(spec["points"], 187)
        self.assertEqual(spec["points"], GRID_POINTS)
        self.assertEqual(spec["shape"], [17, 11])
        self.assertEqual(spec["order"], "x_major")
        self.assertEqual(spec["spacing_m"], 0.1)
        self.assertEqual(len(MEASURED_POINTS_X), 17)
        self.assertEqual(len(MEASURED_POINTS_Y), 11)
        self.assertAlmostEqual(MEASURED_POINTS_X[0], -0.8)
        self.assertAlmostEqual(MEASURED_POINTS_X[-1], 0.8)
        self.assertAlmostEqual(MEASURED_POINTS_Y[0], -0.5)
        self.assertAlmostEqual(MEASURED_POINTS_Y[-1], 0.5)

    def test_catalog_items_share_one_grid(self):
        from backend.height_scan import GRID_POINTS

        items = {item["id"]: item for item in list_perception_items()}
        self.assertEqual(items["heightfield"]["width"], GRID_POINTS)
        self.assertEqual(items["lidar_height_scan"]["width"], GRID_POINTS)
        self.assertEqual(items["heightfield"]["meta"]["shape"], [17, 11])
        self.assertEqual(items["lidar_height_scan"]["meta"]["grid_shape"], [17, 11])

    def test_lattice_cloud_reproduces_raycast_exactly(self):
        """点云恰好落在 187 个测量点上时，两条链路必须逐格完全一致（同网格保证）。"""
        from backend.height_scan import (
            align_height_scans,
            build_height_scan_from_points,
            build_height_scan_from_terrain,
            world_grid_points,
        )

        def terrain(x: float, y: float) -> float:
            return 0.05 * x - 0.2 * y + 0.01 * x * y

        base_xy, base_z, yaw = (0.4, -0.3), 0.5, 0.3
        reference = build_height_scan_from_terrain(terrain, base_xy, base_z, yaw)
        cloud = [(wx, wy, terrain(wx, wy)) for wx, wy in world_grid_points(base_xy, yaw)]
        candidate = build_height_scan_from_points(cloud, base_xy, base_z, yaw)
        report = align_height_scans(reference, candidate, tolerance=0.0)
        self.assertEqual(len(reference), 187)
        self.assertEqual(report["max_abs_diff"], 0.0)
        self.assertTrue(report["within_tolerance"])

    def test_selftest_reports_expected_bounds(self):
        from backend.height_scan import alignment_selftest

        report = alignment_selftest()
        self.assertEqual(report["verdict"], "pass")
        self.assertEqual(report["failures"], [])
        cases = {case["name"]: case for case in report["cases"]}
        self.assertEqual(set(cases), {"flat", "slope_10pct", "step_0.2", "yaw_45deg"})
        self.assertEqual(cases["flat"]["max_abs_diff"], 0.0)
        self.assertEqual(cases["yaw_45deg"]["max_abs_diff"], 0.0)
        # 台阶边界切在单元内部 → 恰好暴露一个台阶高的离散化差异
        self.assertAlmostEqual(cases["step_0.2"]["max_abs_diff"], 0.2, places=6)
        slope = cases["slope_10pct"]
        self.assertLessEqual(slope["max_abs_diff"], slope["bound"] + 1e-12)

    def test_height_scan_endpoints(self):
        grid = self.client.get("/api/perception/height-scan/grid").json()
        self.assertTrue(grid["success"])
        self.assertEqual(grid["grid"]["points"], 187)
        selftest = self.client.get("/api/perception/height-scan/selftest?step=0.02").json()
        self.assertEqual(selftest["verdict"], "pass")
        self.assertEqual(len(selftest["cases"]), 4)
        self.assertEqual(
            self.client.get("/api/perception/height-scan/selftest?step=1").status_code, 400
        )

    def test_project_terrain_alignment(self):
        """用项目自己的地形生成器（5 种地形）跑对齐，全部落在坡度推导的上界内。"""
        from backend.height_scan import map_alignment_selftest

        for kind in ("flat", "slope", "stairs", "noise", "obstacle_mix"):
            report = map_alignment_selftest(kind=kind, seed=3)
            self.assertEqual(report["verdict"], "pass", f"{kind}: {report['case']}")
            case = report["case"]
            self.assertLessEqual(case["max_abs_diff"], case["bound"] + 1e-12, kind)
        flat = map_alignment_selftest(kind="flat")["case"]
        self.assertEqual(flat["max_abs_diff"], 0.0)

    def test_selftest_map_endpoint(self):
        payload = self.client.get("/api/perception/height-scan/selftest-map?kind=noise").json()
        self.assertEqual(payload["verdict"], "pass")
        self.assertEqual(payload["case"]["terrain"]["kind"], "noise")
        self.assertEqual(
            self.client.get("/api/perception/height-scan/selftest-map?kind=nope").status_code, 400
        )

    def test_point_cloud_aggregation_and_fill(self):
        from backend.height_scan import build_height_scan_from_points

        # 三个点都落在中心单元（x=0.0, y=0.0 → index = 8 * 11 + 5 = 93）
        cloud = [(0.0, 0.0, 1.0), (0.0, 0.0, 0.5), (0.02, 0.01, 0.8)]
        base_xy, base_z = (0.0, 0.0), 1.0
        minimum = build_height_scan_from_points(cloud, base_xy, base_z, aggregate="min")
        maximum = build_height_scan_from_points(cloud, base_xy, base_z, aggregate="max")
        mean = build_height_scan_from_points(cloud, base_xy, base_z, aggregate="mean")
        self.assertEqual(minimum[0], 0.0)  # 空单元 → fill
        self.assertAlmostEqual(minimum[93], 0.5)  # base_z - min z
        self.assertAlmostEqual(maximum[93], 0.0)  # base_z - max z
        self.assertAlmostEqual(mean[93], 1.0 - (1.0 + 0.5 + 0.8) / 3.0)
        emptied = build_height_scan_from_points([], base_xy, base_z, fill=-1.0)
        self.assertTrue(all(value == -1.0 for value in emptied))


class CameraProjectionTests(unittest.TestCase):
    """相机几何：内参解析、点/框投影、深度反投影、目标判定（高级仿真感知链路）。"""

    def setUp(self):
        self.client = TestClient(app)

    def test_intrinsics_from_fov_and_calibration(self):
        from backend.camera_projection import resolve_intrinsics

        derived = resolve_intrinsics(640, 480, fov_deg=120.0)
        self.assertEqual(derived["source"], "derived_from_fov")
        self.assertAlmostEqual(derived["hfov_deg"], 120.0, places=6)
        self.assertAlmostEqual(derived["cx"], (640 - 1) / 2)
        self.assertAlmostEqual(derived["cy"], (480 - 1) / 2)
        calibrated = resolve_intrinsics(640, 480, fx=500.0, fy=480.0, cx=320.0, cy=240.0)
        self.assertEqual(calibrated["source"], "calibrated")
        self.assertEqual(calibrated["fx"], 500.0)
        self.assertEqual(calibrated["cy"], 240.0)

    def test_optical_axis_projects_to_principal_point(self):
        from backend.camera_projection import mount_rotation, project_base_points, resolve_intrinsics

        intrinsics = resolve_intrinsics(1920, 1080, fov_deg=90.0)
        for yaw in (0.0, 90.0, -45.0):
            sensor = {"position": {"x": 0.1, "y": 0.2, "z": 0.3}, "rotation": {"yaw": yaw}}
            rotation = mount_rotation(0.0, 0.0, yaw)
            distance = 4.0
            point = (
                0.1 + rotation[0][0] * distance,
                0.2 + rotation[1][0] * distance,
                0.3 + rotation[2][0] * distance,
            )
            projected = project_base_points([point], sensor, intrinsics)[0]
            self.assertTrue(projected["valid"], yaw)
            self.assertAlmostEqual(projected["u"], intrinsics["cx"], places=6)
            self.assertAlmostEqual(projected["v"], intrinsics["cy"], places=6)
            self.assertAlmostEqual(projected["depth"], distance, places=6)

    def test_behind_camera_rejected_and_hfov_edges(self):
        from backend.camera_projection import project_base_points, resolve_intrinsics

        intrinsics = resolve_intrinsics(640, 480, fov_deg=120.0)
        sensor = {"position": {"x": 0.0, "y": 0.0, "z": 0.0}, "rotation": {}}
        behind = project_base_points([(-2.0, 0.0, 0.0)], sensor, intrinsics)[0]
        self.assertFalse(behind["valid"])
        self.assertIsNone(behind["u"])
        half = 3.0 * math.tan(math.radians(intrinsics["hfov_deg"]) / 2.0)
        left_edge = project_base_points([(3.0, half, 0.0)], sensor, intrinsics)[0]
        right_edge = project_base_points([(3.0, -half, 0.0)], sensor, intrinsics)[0]
        self.assertAlmostEqual(left_edge["u"], 0.0, places=6)
        self.assertAlmostEqual(right_edge["u"], intrinsics["width"] - 1, places=6)

    def test_box_projection_and_depth_roundtrip(self):
        from backend.camera_projection import (
            depth_image_to_points,
            project_box,
            project_optical_points,
            resolve_intrinsics,
        )

        intrinsics = resolve_intrinsics(640, 480, fov_deg=90.0)
        sensor = {"position": {"x": 0.0, "y": 0.0, "z": 0.0}, "rotation": {}}
        box = project_box((2.0, 0.0, 0.0), (0.3, 0.3, 0.3), sensor, intrinsics)
        self.assertTrue(box["any_visible"])
        self.assertEqual(box["corners_visible"], 8)
        u0, v0, u1, v1 = box["bbox"]
        self.assertLess(u0, u1)
        self.assertLess(v0, v1)
        self.assertAlmostEqual((u0 + u1) / 2, intrinsics["cx"], delta=2.0)

        depth = [[2.5] * 8 for _ in range(6)]
        cloud = depth_image_to_points(depth, intrinsics)
        self.assertEqual(cloud["total"], 48)
        self.assertEqual(cloud["valid"], 48)
        back = project_optical_points(cloud["points"], intrinsics)
        self.assertTrue(all(item["valid"] for item in back))
        self.assertTrue(all(abs(item["depth"] - 2.5) < 1e-9 for item in back))

    def test_target_arrival_and_visibility(self):
        from backend.camera_projection import arrival_verdict, resolve_intrinsics, target_visibility

        self.assertTrue(arrival_verdict((0.0, 0.0), (0.1, 0.1), tolerance_m=0.3)["arrived"])
        self.assertFalse(arrival_verdict((0.0, 0.0), (0.5, 0.0), tolerance_m=0.3)["arrived"])
        intrinsics = resolve_intrinsics(640, 480, fov_deg=120.0)
        sensor = {"position": {"x": 0.0, "y": 0.0, "z": 0.0}, "rotation": {}}
        zone = [(2.0 + dx, dy, 0.0) for dx in (-0.4, 0.0, 0.4) for dy in (-0.3, 0.0, 0.3)]
        visible = target_visibility(zone, sensor, intrinsics)
        self.assertEqual(visible["verdict"], "visible")
        self.assertGreater(visible["visible_ratio"], 0.9)
        self.assertAlmostEqual(visible["nearest_depth_m"], 1.6, places=6)
        behind = target_visibility([(-2.0, 0.0, 0.0)], sensor, intrinsics)
        self.assertEqual(behind["verdict"], "not_visible")

    def test_projection_endpoints(self):
        sensors = self.client.get("/api/perception/projection/sensors").json()
        ids = [item["id"] for item in sensors["sensors"]]
        self.assertIn("camera", ids)
        self.assertIn("depth_sensor", ids)
        selftest = self.client.get("/api/perception/projection/selftest").json()
        self.assertEqual(selftest["verdict"], "pass")
        self.assertEqual(selftest["failures"], [])
        self.assertGreaterEqual(len(selftest["cases"]), 6)

        ok = self.client.post(
            "/api/perception/projection/project",
            json={"sensor_id": "camera", "points": [[3.0, 0.0, 0.0]]},
        ).json()
        self.assertEqual(ok["count"], 1)
        self.assertEqual(ok["sensor_id"], "camera")
        self.assertEqual(
            self.client.post(
                "/api/perception/projection/project", json={"sensor_id": "nope", "points": [[1.0, 0.0, 0.0]]}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                "/api/perception/projection/project", json={"sensor_id": "IMU", "points": [[1.0, 0.0, 0.0]]}
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/api/perception/projection/project", json={"sensor_id": "camera", "points": []}
            ).status_code,
            400,
        )

    def test_odom_observation_item(self):
        items = {item["id"]: item for item in list_perception_items()}
        self.assertEqual(items["base_pos_odom"]["sensor"], "odom")
        self.assertEqual(items["base_pos_odom"]["width"], 3)
        self.assertEqual(items["base_pos_odom"]["meta"]["topic"], "/odom")
        self.assertEqual(items["base_pos_odom"]["meta"]["frequency_hz"], 100)
        # gps 已剔除：既不在观测目录，也不在硬件 kind 登记里
        self.assertNotIn("gps_position", items)
        from backend.sensor_suite import SENSOR_KIND_CLASSES

        self.assertNotIn("gps", SENSOR_KIND_CLASSES)
