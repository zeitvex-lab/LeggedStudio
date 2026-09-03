import unittest

from fastapi.testclient import TestClient

from backend.api_complete import app
from backend.robot_presets import list_robot_presets
from backend.training_api import CreateTrainingRequest


class CompleteApiContractTests(unittest.TestCase):
    def test_health_identifies_compatible_backend(self):
        payload = TestClient(app).get("/health").json()
        self.assertEqual(payload["app_id"], "legged-studio")
        self.assertEqual(payload["api_schema"], "legged-studio-api-1")

    def test_training_defaults_to_native_mjlab(self):
        request = CreateTrainingRequest(contract=list_robot_presets()[0]["contract"])
        self.assertEqual(request.backend, "native_mjlab")

    def test_local_mujoco_is_not_a_training_backend(self):
        with self.assertRaises(ValueError):
            CreateTrainingRequest(contract=list_robot_presets()[0]["contract"], backend="local_mujoco")

    def test_environment_exposes_only_mjlab(self):
        payload = TestClient(app).get("/api/system/environment").json()
        self.assertEqual(set(payload["adapters"]), {"mjlab"})

    def test_v2_contract_validation_endpoint(self):
        client = TestClient(app)
        contract = list_robot_presets()[0]["contract"]
        response = client.post("/api/contracts/validate", json=contract)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["schema_version"], "robot-contract-2.0")
        self.assertGreater(payload["actuated_joints"], 0)

    def test_invalid_contract_returns_structured_errors(self):
        client = TestClient(app)
        response = client.post("/api/contracts/validate", json={"contract_id": "bad"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["valid"])
        self.assertTrue(payload["errors"])

    def test_scenario_validation_and_recipe_resolution(self):
        client = TestClient(app)
        scenario = {"scenario_id": "warehouse_demo", "map_id": "warehouse", "mode": "navigation", "waypoints": [{"x": 0, "y": 0}, {"x": 2, "y": 1}]}
        response = client.post("/api/scenarios/validate", json=scenario)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["valid"])

        response = client.post("/api/training/resolve-recipe", json={"task_name": "rough_terrain", "algorithm": "sac", "reward_scales": {"torques": 0}})
        self.assertEqual(response.status_code, 200)
        recipe = response.json()["recipe"]
        self.assertEqual(recipe["algorithm"], "SAC")
        self.assertEqual(recipe["reward_scales"]["torques"], 0)

    def test_missing_training_logs_returns_not_found(self):
        client = TestClient(app)
        response = client.get("/api/training/does-not-exist/logs")
        self.assertEqual(response.status_code, 404)

    def test_browser_simulation_manifest_serves_package_assets(self):
        client = TestClient(app)
        response = client.get("/api/simulation/browser-config/zex-w")
        self.assertEqual(response.status_code, 200)
        manifest = response.json()["sim"]["asset_package"]
        self.assertIn("scene.xml", manifest["files"])
        asset = client.get("/api/simulation/browser-package/zex-w/scene.xml")
        self.assertEqual(asset.status_code, 200)
        self.assertIn("model/robot.xml", asset.text)


if __name__ == "__main__":
    unittest.main()
