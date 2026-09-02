import unittest

from backend.robot_presets import list_robot_presets


class RobotPresetTests(unittest.TestCase):
    def test_go2_and_go2w_are_versioned_training_presets(self):
        presets = {item["robot_id"]: item for item in list_robot_presets()}
        self.assertTrue({"unitree_go2", "unitree_go2w", "zex-w"}.issubset(presets))
        self.assertEqual(presets["unitree_go2"]["dof"], 12)
        self.assertEqual(presets["unitree_go2w"]["dof"], 16)
        self.assertEqual(presets["unitree_go2"]["contract"]["locomotion_type"], "P")
        self.assertEqual(presets["unitree_go2w"]["contract"]["locomotion_type"], "W")

    def test_all_robot_packages_share_layout(self):
        for item in list_robot_presets():
            package = item["robot_package"]
            self.assertEqual(package["schema_version"], "robot-package-1.0")
            self.assertEqual(package["model"]["path"], "model/robot.xml")
            self.assertEqual(package["contract_path"], "contract.json")
            self.assertEqual(package["training_config_path"], "training/config.json")
            self.assertEqual(package["simulation_config_path"], "simulation/config.json")


if __name__ == "__main__":
    unittest.main()
