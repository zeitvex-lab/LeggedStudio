import unittest

from backend.robot_presets import list_robot_presets


class RobotPresetTests(unittest.TestCase):
    def test_go2_and_go2w_are_versioned_training_presets(self):
        presets = {item["robot_id"]: item for item in list_robot_presets()}
        self.assertEqual(set(presets), {"unitree_go2", "unitree_go2w"})
        self.assertEqual(presets["unitree_go2"]["dof"], 12)
        self.assertEqual(presets["unitree_go2w"]["dof"], 16)
        self.assertEqual(presets["unitree_go2"]["contract"]["locomotion_type"], "P")
        self.assertEqual(presets["unitree_go2w"]["contract"]["locomotion_type"], "W")


if __name__ == "__main__":
    unittest.main()
