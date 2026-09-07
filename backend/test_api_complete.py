import unittest
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from fastapi.testclient import TestClient

from backend.api_complete import app
from backend.robot_presets import list_robot_presets
from backend.training_api import CreateTrainingRequest


class CompleteApiContractTests(unittest.TestCase):
    def test_robot_summary_does_not_eagerly_return_model_contracts(self):
        payload = TestClient(app).get("/api/robots/presets?summary=true").json()
        expected_ids = {preset["robot_id"] for preset in list_robot_presets()}
        self.assertEqual(payload["count"], len(expected_ids))
        self.assertEqual({item["robot_id"] for item in payload["presets"]}, expected_ids)
        self.assertTrue(all("contract" not in item for item in payload["presets"]))
        self.assertTrue(all("training_profiles" not in item for item in payload["presets"]))

    def test_health_identifies_compatible_backend(self):
        payload = TestClient(app).get("/health").json()
        self.assertEqual(payload["app_id"], "legged-studio")
        self.assertEqual(payload["api_schema"], "legged-studio-api-1")

    def test_training_defaults_to_native_mjlab(self):
        request = CreateTrainingRequest(contract=list_robot_presets()[0]["contract"])
        self.assertEqual(request.backend, "native_mjlab")

    def test_create_request_accepts_and_stores_overrides(self):
        # Generic dot-path overrides ride through the create request into the
        # stored worker config untouched; the worker applies them per path.
        overrides = {
            "environment.sim.mujoco.timestep": 0.002,
            "runner.max_iterations": 25000,
            "environment.rewards.action_rate.weight": -0.02,
        }
        request = CreateTrainingRequest(
            contract=list_robot_presets()[0]["contract"],
            profile_id="zex-w-rough",
            overrides=overrides,
        )
        self.assertEqual(request.overrides, overrides)
        payload = request.model_dump(mode="json")
        self.assertEqual(payload["overrides"], overrides)
        # Default stays an empty dict so existing callers are unaffected.
        self.assertEqual(CreateTrainingRequest(contract=list_robot_presets()[0]["contract"]).overrides, {})

    def test_config_introspect_dump_and_set_by_path(self):
        from adapters.mjlab import config_introspect

        @dataclass
        class RewardTermCfg:
            weight: float = 1.0
            params: dict = field(default_factory=dict)

        @dataclass
        class SimCfg:
            timestep: float = 0.005
            use_gpu: bool = False

        @dataclass
        class EnvCfg:
            sim: SimCfg = field(default_factory=SimCfg)
            rewards: dict = field(default_factory=lambda: {"action_rate": RewardTermCfg(weight=-0.01)})
            num_envs: int = 2048
            label: str = "rough"
            hidden: tuple = (512, 256)
            nothing: object = None
            _private: int = 7

        cfg = EnvCfg()
        tree = config_introspect.dump_config_tree(cfg)
        self.assertEqual(tree["__type__"], "EnvCfg")
        self.assertEqual(tree["sim"]["__type__"], "SimCfg")
        self.assertEqual(tree["sim"]["timestep"], 0.005)
        self.assertEqual(tree["rewards"]["action_rate"]["weight"], -0.01)
        self.assertNotIn("_private", tree)

        config_introspect.set_by_path(cfg, "sim.timestep", "0.002")
        self.assertEqual(cfg.sim.timestep, 0.002)
        self.assertIsInstance(cfg.sim.timestep, float)
        config_introspect.set_by_path(cfg, "sim.use_gpu", 1)
        self.assertIs(cfg.sim.use_gpu, True)
        config_introspect.set_by_path(cfg, "num_envs", "4096")
        self.assertEqual(cfg.num_envs, 4096)
        self.assertIsInstance(cfg.num_envs, int)
        config_introspect.set_by_path(cfg, "rewards.action_rate.weight", -0.05)
        self.assertEqual(cfg.rewards["action_rate"].weight, -0.05)
        config_introspect.set_by_path(cfg, "hidden", [1, 2])
        self.assertEqual(cfg.hidden, (1, 2))
        config_introspect.set_by_path(cfg, "nothing", "kept")
        self.assertEqual(cfg.nothing, "kept")
        for bad_path in ("missing", "sim.missing", "rewards.missing.weight"):
            with self.assertRaises(KeyError):
                config_introspect.set_by_path(cfg, bad_path, 1)

        leaves = dict(config_introspect.iter_leaves(cfg))
        self.assertEqual(leaves["sim.timestep"], 0.002)
        self.assertEqual(leaves["rewards.action_rate.weight"], -0.05)
        self.assertEqual(leaves["hidden"], [1, 2])
        self.assertEqual(set(leaves) & {"_private"}, set())

    def test_profile_schema_endpoint_validates_ids_without_spawning(self):
        client = TestClient(app)
        missing_robot = client.get("/api/training/profile-schema?robot_id=does-not-exist&profile_id=zex-w-rough")
        self.assertEqual(missing_robot.status_code, 404)
        missing_profile = client.get("/api/training/profile-schema?robot_id=zex-w&profile_id=does-not-exist")
        self.assertEqual(missing_profile.status_code, 404)

    def test_unknown_backend_is_accepted_but_rejected_at_launch(self):
        # The schema accepts any backend string (future frameworks such as
        # unilab); launch-time validation rejects the ones not wired yet.
        request = CreateTrainingRequest(contract=list_robot_presets()[0]["contract"], backend="local_mujoco")
        self.assertEqual(request.backend, "local_mujoco")

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

    def test_training_config_preview_exposes_five_categories(self):
        client = TestClient(app)
        preset = next(item for item in list_robot_presets() if item.get("training_profiles"))
        profile = preset["training_profiles"][0]
        response = client.get(
            f"/api/training/config-preview?robot_id={preset['robot_id']}&profile_id={profile['profile_id']}"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["robot_id"], preset["robot_id"])
        self.assertEqual(payload["profile_id"], profile["profile_id"])
        self.assertEqual(payload["task_name"], profile["task_name"])
        for category in ("simulator", "environment", "embodiment", "learning", "robustness", "editable_vs_readonly"):
            self.assertIn(category, payload)
        self.assertEqual(payload["learning"]["algorithm"], "PPO")
        self.assertEqual(payload["learning"]["runner"], profile.get("runner"))
        expected_decimation = profile.get("decimation") or preset["contract"]["control"]["decimation"]
        self.assertEqual(payload["simulator"]["decimation"], expected_decimation)
        self.assertEqual(payload["embodiment"]["joint_order"], preset["contract"]["action"]["joint_order"])
        editable = payload["editable_vs_readonly"]["editable_keys"]
        for key in ("profile_id", "num_minibatches", "reward_overrides", "command_ranges", "seed"):
            self.assertIn(key, editable)
        self.assertTrue(all(item["reason"] for item in payload["editable_vs_readonly"]["readonly_categories"]))

    def test_training_config_preview_without_profile_and_unknown_ids(self):
        client = TestClient(app)
        preset = list_robot_presets()[0]
        response = client.get(f"/api/training/config-preview?robot_id={preset['robot_id']}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIsNone(payload["profile_id"])
        self.assertIsNone(payload["environment"]["curriculum"])
        self.assertEqual(client.get("/api/training/config-preview?robot_id=does-not-exist").status_code, 404)
        unknown_profile = client.get(
            f"/api/training/config-preview?robot_id={preset['robot_id']}&profile_id=does-not-exist"
        )
        self.assertEqual(unknown_profile.status_code, 404)

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
