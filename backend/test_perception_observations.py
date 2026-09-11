"""Tests for the generic perception observation catalog (Feature 6).

Also covers the MATRiX v1.0.13 derived external sensor suite
(:mod:`backend.sensor_suite`) and the sensor-corpus container probe
(:mod:`tools.matrix_sensor_corpus`), which are the two pieces the advanced
simulation surface consumes from that release.
"""

from __future__ import annotations

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
        self.assertEqual(set(suite), {"imu", "odom", "gps", "rgb", "depth", "lidar"})
        self.assertEqual(suite["imu"]["frequency_hz"], 500)
        self.assertEqual(suite["odom"]["frequency_hz"], 100)
        self.assertEqual(suite["gps"]["frequency_hz"], 100)
        self.assertEqual(suite["lidar"]["frequency_hz"], 10)
        self.assertEqual(suite["lidar"]["sensor_type"], "airy")
        self.assertEqual(suite["rgb"]["intrinsics"]["width"], 1920)
        self.assertEqual(suite["depth"]["intrinsics"]["fov_deg"], 120)
        self.assertFalse(suite["depth"]["meta"]["cloudmode"])

    def test_presets_endpoint_lists_matriX_presets(self):
        payload = self.client.get("/api/sensors/presets").json()
        self.assertTrue(payload["success"])
        names = [preset["name"] for preset in payload["presets"]]
        for required in ("default", "lidar_dual", "mid360_slam", "fisheye", "infrared", "panorama", "ptzrgb", "zg"):
            self.assertIn(required, names)
        default = [p for p in payload["presets"] if p["name"] == "default"][0]
        self.assertEqual(default["sensor_count"], 6)
        self.assertEqual(default["exteroceptive_count"], 3)  # rgb + depth + lidar

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
        self.assertEqual(classes["ptzrgb"], "exteroceptive")

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
