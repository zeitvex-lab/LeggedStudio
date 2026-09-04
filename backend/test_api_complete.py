import unittest
import xml.etree.ElementTree as ET

from fastapi.testclient import TestClient

from backend.api_complete import app
from backend.robot_presets import list_robot_presets
from backend.training_api import CreateTrainingRequest


class CompleteApiContractTests(unittest.TestCase):
    def test_robot_summary_does_not_eagerly_return_model_contracts(self):
        payload = TestClient(app).get("/api/robots/presets?summary=true").json()
        self.assertEqual(payload["count"], 3)
        self.assertEqual({item["robot_id"] for item in payload["presets"]}, {"unitree_go2", "zex-w", "microduck"})
        self.assertTrue(all("contract" not in item for item in payload["presets"]))
        self.assertTrue(all("training_profiles" not in item for item in payload["presets"]))

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

    def test_missing_training_checkpoints_returns_not_found(self):
        client = TestClient(app)
        response = client.get("/api/training/does-not-exist/checkpoints")
        self.assertEqual(response.status_code, 404)

    def test_browser_simulation_manifest_serves_package_assets(self):
        client = TestClient(app)
        response = client.get("/api/simulation/browser-config/zex-w")
        self.assertEqual(response.status_code, 200)
        manifest = response.json()["sim"]["asset_package"]
        self.assertEqual(
            manifest["scenes"],
            ["simulation/flat.xml", "simulation/rough.xml", "simulation/stairs.xml", "simulation/slope.xml"],
        )
        asset = client.get("/api/simulation/browser-package/zex-w/scene.xml")
        self.assertEqual(asset.status_code, 200)
        self.assertIn("model/robot.xml", asset.text)

    def test_zex_w_ships_full_meshes_and_per_leg_contract(self):
        client = TestClient(app)
        response = client.get("/api/simulation/browser-config/zex_w")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["sim"]["robot"], "zex-w")
        self.assertEqual(payload["policy"]["contract"]["action_dim"], 16)
        self.assertEqual(len(payload["robot"]["default_joint_angles"]), 16)
        # Deployment pose from the real robot contract: 12 legs then 4 wheels.
        self.assertEqual(
            payload["robot"]["joint_order"][:4],
            ["fl_hip_abduction_joint", "fl_hip_pitch_joint", "fl_knee_joint", "fr_hip_abduction_joint"],
        )
        self.assertEqual(payload["robot"]["joint_order"][12], "fl_wheel_joint")
        # All package meshes now fit under the transfer limit and stay visual.
        package = payload["sim"]["asset_package"]
        self.assertFalse(package["lightweight_preview"])
        self.assertEqual(package["preview_mode"], "visual_meshes")
        self.assertEqual(package["omitted_meshes"], [])
        self.assertIn("model/assets/base_link.STL", package["files"])

        model = client.get("/api/simulation/browser-package/zex-w/model/robot.xml")
        self.assertEqual(model.status_code, 200)
        document = ET.fromstring(model.text)
        self.assertIn("base_link", {item.get("name") for item in document.findall(".//mesh")})
        self.assertIn("fl_hip_pitch_Link", {item.get("name") for item in document.findall(".//mesh")})
        self.assertTrue(document.findall(".//geom[@mesh='fl_hip_pitch_Link']"))
        self.assertTrue(document.findall(".//key[@name='__browser_init__']"))
        self.assertGreaterEqual(len(document.findall(".//geom")), 16)
        self.assertEqual(len(document.findall(".//actuator/*")), 16)

    def test_go2_browser_config_exposes_real_terrain_and_policy_choices(self):
        client = TestClient(app)
        payload = client.get("/api/simulation/browser-config/unitree_go2").json()
        package = payload["sim"]["asset_package"]
        self.assertEqual(
            package["scenes"],
            ["flat.xml", "stairs.xml", "cross_stairs.xml", "high_platforms.xml", "cross_slope.xml", "race_track.xml"],
        )
        self.assertFalse(payload["policy"]["disabled"])
        self.assertEqual(payload["policy"]["contract"]["obs_dim"], 45)
        self.assertEqual(payload["policy"]["contract"]["action_dim"], 12)
        # Matches the reference sim2sim spawn height of the Go2 MJCF.
        self.assertEqual(payload["robot"]["control"]["base_height_target"], 0.445)
        self.assertEqual(payload["robot"]["control"]["initial_keyframe"], "__browser_init__")
        self.assertIn("model/assets/hip_0.obj", package["files"])
        # The 7.8 MB base_4.obj stays under the 12 MiB transfer limit.
        self.assertIn("model/assets/base_4.obj", package["files"])

        scene = client.get("/api/simulation/browser-package/unitree_go2/flat.xml")
        self.assertEqual(scene.status_code, 200)
        self.assertIn('file="model/robot.xml"', scene.text)
        self.assertNotIn('file="go2.xml"', scene.text)


if __name__ == "__main__":
    unittest.main()
