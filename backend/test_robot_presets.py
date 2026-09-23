import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.robot_presets import list_robot_presets
from backend.package_records import validate_training_profile


class RobotPresetTests(unittest.TestCase):
    def test_go2_and_zex_w_are_versioned_training_presets(self):
        presets = {item["robot_id"]: item for item in list_robot_presets()}
        self.assertTrue({"unitree_go2", "zex-w"}.issubset(presets))
        self.assertEqual(presets["unitree_go2"]["dof"], 12)
        self.assertEqual(presets["zex-w"]["dof"], 16)
        self.assertEqual(presets["unitree_go2"]["contract"]["locomotion_type"], "P")
        self.assertEqual(presets["zex-w"]["contract"]["locomotion_type"], "W")

    def test_every_preset_package_is_complete_not_a_placeholder(self):
        """通用机制重锚（原 microduck 专项用例已随该包出库删除）：preset 的
        robot_package 必须指向真实在盘的 model/robot.xml，占位包不算完整包。"""
        presets = list_robot_presets()
        self.assertEqual(
            [
                "deeprobotics_lite3",
                "deeprobotics_m20",
                "unitree_b2",
                "unitree_b2w",
                "unitree_go1",
                "unitree_go2",
                "unitree_go2w",
                "zex-w",
            ],
            sorted(item["robot_id"] for item in presets),
        )
        for item in presets:
            root = Path(item["robot_package"]["package_root"])
            self.assertTrue(
                root.joinpath("model", "robot.xml").exists(),
                f"{item['robot_id']} 的 robot_package 未指向真实 model/robot.xml",
            )

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
        self.assertEqual(package.get("extension_entrypoint"), "local_tasks.mjlab_extension:register")
        self.assertEqual(package.get("extension_root"), "training/source")
        profile_ids = {item["profile_id"] for item in go2["training_profiles"]}
        self.assertIn("go2-velocity-flat", profile_ids)
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
            (package / "contract_legacy_v2.json").write_text(json.dumps({"robot_id": "acme_quadruped", "family": "Acme", "joints": {"actuated_joints": []}, "urdf": {"path": str(package / "model" / "robot.xml")}}), encoding="utf-8")
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
                (package / "contract_legacy_v2.json").write_text(json.dumps({"robot_id": "acme", "family": family, "joints": {"actuated_joints": []}}), encoding="utf-8")
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

    def test_package_views_share_a_contract_snapshot_during_an_edit(self):
        from backend import robot_packages

        truth = json.loads((Path(__file__).resolve().parents[1] / "assets/robots/unitree_go2/contract.json").read_text(encoding="utf-8-sig"))
        truth["action"]["action_scale"] = 0.125
        truth["morphology"]["version_marker"] = "first"
        changed = json.loads(json.dumps(truth))
        changed["action"]["action_scale"] = 0.875
        changed["morphology"]["version_marker"] = "second"
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / "packages" / "acme"
            package.mkdir(parents=True)
            contract_path = package / "contract.json"
            contract_path.write_text(json.dumps(truth), encoding="utf-8")
            (package / "contract_legacy_v2.json").write_text(json.dumps({"robot_id": "acme", "joints": {"actuated_joints": []}}), encoding="utf-8")
            (package / "robot_package.json").write_text(json.dumps({"package_id": "acme"}), encoding="utf-8")
            original_read = Path.read_text

            def read_then_edit(path, *args, **kwargs):
                text = original_read(path, *args, **kwargs)
                if path == contract_path:
                    contract_path.write_text(json.dumps(changed), encoding="utf-8")
                return text

            with mock.patch.dict(os.environ, {"LEGGED_STUDIO_WORKSPACE": tmp}):
                try:
                    with mock.patch.object(Path, "read_text", new=read_then_edit):
                        robot_packages.upsert_package(package)
                    record = robot_packages.list_robot_packages()[0]
                finally:
                    robot_packages.invalidate_package_cache()
            self.assertEqual(0.125, record["action_scale"]["action_scale"])
            self.assertEqual("first", record["morphology"]["version_marker"])

    def test_profile_validation_is_robot_neutral(self):
        profile = {"schema_version": "training-profile-1.0", "profile_id": "custom-task", "backend": "future_backend", "entrypoints": {"env": "custom.env:create", "runner": "custom.runner:create"}}
        self.assertEqual(validate_training_profile(profile), [])


if __name__ == "__main__":
    unittest.main()
