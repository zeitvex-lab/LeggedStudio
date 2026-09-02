import unittest

from fastapi.testclient import TestClient

from backend.api_complete import app
from backend.robot_presets import list_robot_presets
from backend.robot_packages import package_for_contract


class ModelInspectionTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_builtin_robot_is_described_as_a_package(self):
        package = package_for_contract(list_robot_presets()[0]["contract"])
        self.assertEqual(package["schema_version"], "robot-package-1.0")
        self.assertEqual(package["task_kind"], "generic")
        self.assertTrue(package["package_root"])


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

    def test_import_persists_model_and_generates_contract_draft(self):
        urdf = """<robot name='imported'><link name='base'><inertial><mass value='2'/></inertial></link></robot>"""
        response = self.client.post(
            "/api/models/import",
            json={"files": [{"path": "demo/model.urdf", "content": urdf, "encoding": "utf-8"}], "model_filename": "demo/model.urdf", "format": "auto"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["imported"])
        self.assertTrue(payload["model_path"].startswith("workspace/imports/"))
        self.assertEqual(payload["contract_draft"]["source"], "legged_studio_asset_import")

    def test_project_package_round_trip_contains_training_and_scenario(self):
        import base64
        response = self.client.post("/api/project/export", json={"training_config": {"algorithm": "PPO", "reward_scales": {"track_linear_velocity": 2.0}}, "scenario": {"map_id": "warehouse", "mode": "navigation"}})
        self.assertEqual(response.status_code, 200)
        encoded = base64.b64encode(response.content).decode("ascii")
        imported = self.client.post("/api/project/import", json={"archive_base64": encoded})
        self.assertEqual(imported.status_code, 200)
        payload = imported.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["training_config"]["algorithm"], "PPO")
        self.assertEqual(payload["scenario"]["map_id"], "warehouse")


if __name__ == "__main__":
    unittest.main()
