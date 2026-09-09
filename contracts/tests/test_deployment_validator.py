"""deployment_validator / deployment-contract schema 测试。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from contracts.deployment_validator import (
    DEPLOY_CONTRACT_VERSION,
    DeploymentContractError,
    load_schema,
    validate_deployment_contract,
)

ROOT = Path(__file__).resolve().parents[2]


class ValidatorTest(unittest.TestCase):
    def _valid(self) -> dict:
        return {
            "schema_version": "deployment-contract-1.0",
            "generated_by": "test",
            "robot_id": "unitree_go2",
            "control": {"control_hz": 50, "physics_hz": 500, "decimation": 10},
            "action": {
                "joint_order": [f"FL_{r}_joint" for r in ("hip", "thigh", "calf")],
                "reindex_from_model": [0, 1, 2],
                "action_scale": 0.25,
                "dimension": 3,
            },
            "actuator_profile": {},
            "default_pose": [0.0, 0.0, 0.0],
        }

    def test_valid(self) -> None:
        self.assertEqual(validate_deployment_contract(self._valid()), [])

    def test_bad_version(self) -> None:
        c = self._valid()
        c["schema_version"] = "deployment-contract-0.9"
        self.assertTrue(any("schema_version" in e for e in validate_deployment_contract(c)))

    def test_missing_robot_id(self) -> None:
        c = self._valid()
        c["robot_id"] = ""
        self.assertTrue(any("robot_id" in e for e in validate_deployment_contract(c)))

    def test_reindex_len_mismatch(self) -> None:
        c = self._valid()
        c["action"]["reindex_from_model"] = [0, 1]
        self.assertTrue(
            any("reindex_from_model 长度" in e for e in validate_deployment_contract(c))
        )

    def test_dimension_mismatch(self) -> None:
        c = self._valid()
        c["action"]["dimension"] = 5
        self.assertTrue(any("dimension" in e for e in validate_deployment_contract(c)))

    def test_frequency_out_of_range(self) -> None:
        c = self._valid()
        c["control"]["control_hz"] = 5
        self.assertTrue(any("control_hz" in e for e in validate_deployment_contract(c)))

    def test_action_scale_non_positive(self) -> None:
        c = self._valid()
        c["action"]["action_scale"] = 0
        self.assertTrue(any("action_scale" in e for e in validate_deployment_contract(c)))


class SchemaTest(unittest.TestCase):
    def test_schema_loads(self) -> None:
        schema = load_schema()
        self.assertEqual(schema["title"], "DeploymentContractV1")
        self.assertIn("properties", schema)

    def test_schema_version_const(self) -> None:
        schema = load_schema()
        self.assertEqual(schema["properties"]["schema_version"]["const"], DEPLOY_CONTRACT_VERSION)


if __name__ == "__main__":
    unittest.main()
