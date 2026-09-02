import unittest

from fastapi.testclient import TestClient

from backend.api_complete import app
from backend.robot_presets import list_robot_presets


class ModelInspectionTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_mjcf_report_contains_structure_and_actuator_mapping(self):
        preset = next(item for item in list_robot_presets() if item["robot_id"] == "unitree_go2")
        response = self.client.post(
            "/api/models/validate",
            json={"path": preset["asset_path"], "format": "mjcf", "contract": preset["contract"]},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["valid"])
        self.assertGreater(payload["stats"]["links"], 0)
        self.assertGreater(payload["stats"]["actuators"], 0)
        self.assertIn("topology", payload["inspection"])
        self.assertIn("actuators", payload["inspection"])

    def test_uploaded_urdf_returns_diagnostics(self):
        urdf = """<robot name='fixture'><link name='base'/><link name='foot'/><joint name='bad' type='revolute'><parent link='base'/><child link='foot'/></joint></robot>"""
        response = self.client.post(
            "/api/models/validate",
            json={"content": urdf, "filename": "fixture.urdf", "format": "auto"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["format"], "urdf")
        self.assertFalse(payload["valid"])
        self.assertTrue(any("missing limit" in item for item in payload["errors"]))
        self.assertIn("inertial", payload["inspection"])


if __name__ == "__main__":
    unittest.main()
