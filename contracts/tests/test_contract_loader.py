"""Contract loader (v2/v3 convergence) tests."""

from __future__ import annotations

import unittest
from pathlib import Path

from contracts.contract_loader import (
    ContractLoadError,
    load_contract_v2,
    load_contract_v3,
    load_training_contract,
    merge_v3_over_v2,
)

WORKSPACE = Path(__file__).resolve().parents[2]
ROBOTS = WORKSPACE / "assets" / "robots"


class ContractLoaderTest(unittest.TestCase):
    def test_go2_package_loads_merged(self):
        contract = load_training_contract(ROBOTS / "unitree_go2")
        self.assertEqual(contract["robot_id"], "unitree_go2")
        joints = contract["joints"]
        self.assertEqual(len(joints["actuated_joints"]), 12)
        self.assertEqual(contract["action"]["dimension"], 12)
        # 45 = 标准 6 项 × 12 驱动关节（2026-09-14 基数校正：旧 48 为声明错，见任务清单 E4）
        self.assertEqual(contract["observation"]["dimension"], 45)
        self.assertEqual(contract["control"]["control_hz"], 50)
        # v3 actuator profile expanded per joint.
        self.assertIn("actuator_profile_expanded", contract)
        self.assertEqual(len(contract["actuator_profile_expanded"]), 12)

    def test_v3_authority_over_v2(self):
        v3 = {
            "schema_version": "robot-contract-3.0",
            "robot_id": "test_robot",
            "family": "Test Robot",
            "size_class": "M",
            "locomotion_type": "P",
            "morphology": {
                "id": "quadruped_12dof", "legs": 4,
                "leg_pattern": ["hip", "thigh", "calf"],
                "leg_naming": "{LR}_{role}_joint", "leg_ids": ["FL", "FR", "RL", "RR"],
            },
            "joints": {
                "actuated": [
                    {"name": "FL_hip_joint", "role": "hip"},
                    {"name": "FL_thigh_joint", "role": "thigh"},
                    {"name": "FL_calf_joint", "role": "calf"},
                ],
                "passive": [],
                "default_pose": [0.1, 0.8, -1.5],
            },
            "action": {"dimension": 3, "joint_order": ["FL_hip_joint", "FL_thigh_joint", "FL_calf_joint"], "action_scale": 0.25},
            "observation": {"components": [], "dimension": 24},
            "control": {"control_hz": 50, "physics_hz": 500, "decimation": 10},
            "actuator_profile": {
                "default": {"stiffness": 20.0, "damping": 0.5},
                "by_role": {"hip": {"armature": 0.01}},
            },
            "contract_id": "test_robot_v3",
        }
        v2 = {
            "schema_version": "robot-contract-2.0",
            "robot_id": "test_robot",
            "family": "Test Robot V2",
            "size_class": "L",
            "locomotion_type": "P",
            "contract_id": "test_robot_v2",
            "urdf": {"path": "model/robot.xml", "hash": "abc", "total_mass_kg": 20.0, "mass_source": "manual"},
            "joints": {"actuated_joints": ["FL_hip_joint", "FL_thigh_joint", "FL_calf_joint"], "default_pose": [0.0, 0.0, 0.0]},
            "observation": {"dimension": 48, "components": ["base_lin_vel", "base_ang_vel", "projected_gravity"]},
            "action": {"dimension": 3, "joint_order": ["FL_hip_joint", "FL_thigh_joint", "FL_calf_joint"], "action_scale": 1.0},
            "control": {"control_hz": 100, "physics_hz": 1000, "decimation": 10},
        }

        merged = merge_v3_over_v2(v3, v2)
        # v3 wins for the semantic authority fields.
        self.assertEqual(merged["robot_id"], "test_robot")
        self.assertEqual(merged["size_class"], "M")
        self.assertEqual(merged["action"]["action_scale"], 0.25)
        self.assertEqual(merged["control"]["control_hz"], 50)
        self.assertEqual(merged["observation"]["dimension"], 24)
        self.assertEqual(merged["joints"]["actuated_joints"], ["FL_hip_joint", "FL_thigh_joint", "FL_calf_joint"])
        self.assertEqual(merged["joints"]["default_pose"], [0.1, 0.8, -1.5])
        # v2 supplies the data v3 does not carry (URDF, observation component names).
        self.assertEqual(merged["urdf"]["path"], "model/robot.xml")
        self.assertEqual(len(merged["observation"]["components"]), 3)
        # role-expanded actuator profile.
        profile = merged["actuator_profile_expanded"]
        self.assertEqual(profile["FL_hip_joint"]["armature"], 0.01)
        self.assertEqual(profile["FL_thigh_joint"]["stiffness"], 20.0)
        # contract_id falls back to v3 first.
        self.assertEqual(merged["contract_id"], "test_robot_v3")

    def test_missing_contract_raises(self):
        with self.assertRaises(ContractLoadError):
            load_training_contract(WORKSPACE / "no_such_package")


if __name__ == "__main__":
    unittest.main()


class FieldLevelObservationMergeTest(unittest.TestCase):
    def test_v3_field_level_observation_merged(self):
        """v3 的观测字段级表述（components/history/conditional/recurrent）应 merge 进最终契约。"""
        v3 = {
            "schema_version": "robot-contract-3.0",
            "robot_id": "test_robot",
            "family": "Test Robot",
            "size_class": "M",
            "locomotion_type": "P",
            "morphology": {
                "id": "quadruped_12dof", "legs": 4,
                "leg_pattern": ["hip", "thigh", "calf"],
                "leg_naming": "{LR}_{role}_joint", "leg_ids": ["FL", "FR", "RL", "RR"],
            },
            "joints": {
                "actuated": [{"name": "FL_hip_joint", "role": "hip"}],
                "passive": [],
            },
            "action": {"dimension": 1, "joint_order": ["FL_hip_joint"], "action_scale": 0.25},
            "observation": {
                "components": [
                    {"name": "base_ang_vel", "width": 3, "source": "imu"},
                    {"name": "cmd", "width": 3, "source": "cmd"},
                ],
                "dimension": 6,
                "history_length": 10,
                "history_order": "oldest_to_newest",
                "history_reset": "zero",
                "normalizer": {"mean": [0.0], "std": [1.0]},
                "conditional_fields": [{"name": "motion", "width": 24, "source": "external"}],
            },
            "control": {"control_hz": 50, "physics_hz": 500, "decimation": 10},
            "actuator_profile": {"default": {"stiffness": 20.0}},
            "contract_id": "test_robot_v3",
        }
        v2 = {
            "schema_version": "robot-contract-2.0",
            "robot_id": "test_robot",
            "contract_id": "test_robot_v2",
            "joints": {"actuated_joints": ["FL_hip_joint"], "default_pose": [0.0]},
            "observation": {"dimension": 48, "components": ["base_lin_vel"]},
            "action": {"dimension": 1, "joint_order": ["FL_hip_joint"]},
            "control": {"control_hz": 100},
        }

        merged = merge_v3_over_v2(v3, v2)
        obs = merged["observation"]
        # v3 字段级表述 wins（components 非空）。
        self.assertEqual(obs["dimension"], 6)
        self.assertEqual(len(obs["components"]), 2)
        self.assertEqual(obs["history_length"], 10)
        self.assertEqual(obs["history_order"], "oldest_to_newest")
        self.assertEqual(obs["history_reset"], "zero")
        self.assertEqual(obs["normalizer"], {"mean": [0.0], "std": [1.0]})
        self.assertEqual(len(obs["conditional_fields"]), 1)

    def test_v2_kept_when_v3_components_empty(self):
        """v3 components 为空（宽度待补全）时保留 v2 组件名，但透传 v3 字段级元数据。"""
        v3 = {
            "schema_version": "robot-contract-3.0",
            "robot_id": "test_robot",
            "family": "Test",
            "size_class": "M",
            "locomotion_type": "P",
            "morphology": {
                "id": "quadruped", "legs": 4,
                "leg_pattern": ["hip"], "leg_naming": "{LR}_{role}",
                "leg_ids": ["FL", "FR", "RL", "RR"],
            },
            "joints": {"actuated": [{"name": "FL_hip_joint", "role": "hip"}], "passive": []},
            "action": {"dimension": 1, "joint_order": ["FL_hip_joint"]},
            "observation": {"components": [], "dimension": 48, "history_length": 5},
            "control": {"control_hz": 50},
            "actuator_profile": {"default": {"stiffness": 20.0}},
            "contract_id": "test_robot_v3",
        }
        v2 = {
            "schema_version": "robot-contract-2.0",
            "robot_id": "test_robot",
            "contract_id": "test_robot_v2",
            "joints": {"actuated_joints": ["FL_hip_joint"]},
            "observation": {"dimension": 48, "components": ["base_lin_vel"]},
            "action": {"dimension": 1, "joint_order": ["FL_hip_joint"]},
        }
        merged = merge_v3_over_v2(v3, v2)
        obs = merged["observation"]
        self.assertEqual(len(obs["components"]), 1)  # 保留 v2 组件名
        self.assertEqual(obs["history_length"], 5)   # 透传 v3 历史帧
        self.assertEqual(obs["dimension"], 48)


if __name__ == "__main__":
    unittest.main()
