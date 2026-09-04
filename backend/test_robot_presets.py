import json
import os
import tempfile
import unittest
from pathlib import Path

from backend.robot_presets import list_robot_presets
from backend.robot_packages import validate_training_profile


class RobotPresetTests(unittest.TestCase):
    def test_go2_and_zex_w_are_versioned_training_presets(self):
        presets = {item["robot_id"]: item for item in list_robot_presets()}
        self.assertTrue({"unitree_go2", "zex-w"}.issubset(presets))
        self.assertEqual(presets["unitree_go2"]["dof"], 12)
        self.assertEqual(presets["zex-w"]["dof"], 16)
        self.assertEqual(presets["unitree_go2"]["contract"]["locomotion_type"], "P")
        self.assertEqual(presets["zex-w"]["contract"]["locomotion_type"], "W")

    def test_microduck_is_a_complete_package_not_a_placeholder(self):
        microduck = next(item for item in list_robot_presets() if item["robot_id"] == "microduck")
        self.assertEqual(microduck["dof"], 14)
        self.assertEqual(len(microduck["training_profiles"]), 18)
        self.assertEqual(microduck["runtime_requirements"]["mjlab"], ">=1.6,<2.0")
        self.assertTrue(microduck["robot_package"].get("extension_entrypoint"))
        self.assertTrue(Path(microduck["robot_package"]["package_root"]).joinpath("model", "robot.xml").exists())

    def test_all_robot_packages_share_layout(self):
        for item in list_robot_presets():
            if item["robot_id"] not in {"unitree_go2", "zex-w"}:
                continue
            package = item["robot_package"]
            self.assertEqual(package["schema_version"], "robot-package-1.0")
            self.assertEqual(package["model"]["path"], "model/robot.xml")
            self.assertEqual(package["contract_path"], "contract.json")
            self.assertEqual(package["training_config_path"], "training/config.json")
            self.assertEqual(package["simulation_config_path"], "simulation/config.json")

    def test_zex_w_exposes_mature_training_profiles(self):
        zex = next(item for item in list_robot_presets() if item["robot_id"] == "zex-w")
        self.assertEqual({item["profile_id"] for item in zex["training_profiles"]}, {"zex-w-flat", "zex-w-rough", "zex-w-crawl"})

    def test_go2_exposes_package_owned_mjlab_profiles(self):
        go2 = next(item for item in list_robot_presets() if item["robot_id"] == "unitree_go2")
        package = go2["robot_package"]
        self.assertEqual(package.get("extension_entrypoint"), "lainloco.mjlab_extension:register")
        self.assertEqual(package.get("extension_root"), "training/source")
        self.assertEqual(len(go2["training_profiles"]), 8)
        self.assertTrue(all(item["backend"] == "native_mjlab" for item in go2["training_profiles"]))
        self.assertTrue(all(item["entrypoints"].get("runner_class") for item in go2["training_profiles"]))

    def test_external_non_go2_package_uses_same_profile_contract(self):
        with tempfile.TemporaryDirectory(prefix="legged-studio-packages-") as value:
            root = Path(value)
            package = root / "packages" / "acme_quadruped"
            (package / "model").mkdir(parents=True)
            (package / "training" / "profiles").mkdir(parents=True)
            (package / "training" / "source" / "acme").mkdir(parents=True)
            (package / "model" / "robot.xml").write_text('<mujoco model="acme"/>', encoding="utf-8")
            (package / "contract.json").write_text(json.dumps({"robot_id": "acme_quadruped", "family": "Acme", "joints": {"actuated_joints": []}, "urdf": {"path": str(package / "model" / "robot.xml")}}), encoding="utf-8")
            (package / "robot_package.json").write_text(json.dumps({"schema_version": "robot-package-1.0", "package_id": "acme_quadruped", "model": {"format": "mjcf", "path": "model/robot.xml"}, "extension_root": "training/source", "extension_entrypoint": "acme.extension:register"}), encoding="utf-8")
            profile = {"schema_version": "training-profile-1.0", "profile_id": "acme-flat", "backend": "native_mjlab", "source_root": "training/source", "entrypoints": {"env": "acme.profile:env_cfg", "runner": "acme.profile:runner_cfg"}}
            (package / "training" / "profiles" / "flat.json").write_text(json.dumps(profile), encoding="utf-8")
            previous = os.environ.get("LEGGED_STUDIO_WORKSPACE")
            os.environ["LEGGED_STUDIO_WORKSPACE"] = str(root)
            try:
                found = next(item for item in list_robot_presets() if item["robot_id"] == "acme_quadruped")
            finally:
                if previous is None:
                    os.environ.pop("LEGGED_STUDIO_WORKSPACE", None)
                else:
                    os.environ["LEGGED_STUDIO_WORKSPACE"] = previous
            self.assertEqual(found["training_profiles"][0]["profile_id"], "acme-flat")
            self.assertTrue(found["training_profiles"][0]["valid"])
            self.assertTrue(Path(found["training_profiles"][0]["path"]).is_absolute())

    def test_duplicate_imports_collapse_to_one_robot_id(self):
        with tempfile.TemporaryDirectory(prefix="legged-studio-packages-") as value:
            workspace = Path(value)
            packages = workspace / "packages"
            for directory, family in (("acme", "Canonical Acme"), ("imported_robot_deadbeef", "Duplicate Acme")):
                package = packages / directory
                (package / "model").mkdir(parents=True)
                (package / "model" / "robot.xml").write_text('<mujoco model="acme"/>', encoding="utf-8")
                (package / "contract.json").write_text(json.dumps({"robot_id": "acme", "family": family, "joints": {"actuated_joints": []}}), encoding="utf-8")
                (package / "robot_package.json").write_text(json.dumps({"schema_version": "robot-package-1.0", "package_id": "acme", "model": {"format": "mjcf", "path": "model/robot.xml"}}), encoding="utf-8")
            previous = os.environ.get("LEGGED_STUDIO_WORKSPACE")
            os.environ["LEGGED_STUDIO_WORKSPACE"] = str(workspace)
            try:
                matches = [item for item in list_robot_presets() if item["robot_id"] == "acme"]
            finally:
                if previous is None:
                    os.environ.pop("LEGGED_STUDIO_WORKSPACE", None)
                else:
                    os.environ["LEGGED_STUDIO_WORKSPACE"] = previous
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0]["family"], "Canonical Acme")
            self.assertEqual(Path(matches[0]["asset_path"]), packages / "acme" / "model" / "robot.xml")

    def test_profile_validation_is_robot_neutral(self):
        profile = {"schema_version": "training-profile-1.0", "profile_id": "custom-task", "backend": "future_backend", "entrypoints": {"env": "custom.env:create", "runner": "custom.runner:create"}}
        self.assertEqual(validate_training_profile(profile), [])


if __name__ == "__main__":
    unittest.main()
