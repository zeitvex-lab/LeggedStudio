import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from contracts import load_robot_contract


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "go2.v1.json"
WORKSPACE = Path(__file__).resolve().parents[3]


class Go2ContractTest(unittest.TestCase):
    def test_load_go2_contract_fixture(self) -> None:
        contract = load_robot_contract(FIXTURE)

        self.assertEqual(contract.robot_id, "unitree_go2")
        self.assertEqual(contract.model_revision, "go2-joint-map-v1")
        self.assertEqual(len(contract.joints.canonical_order), 12)
        self.assertEqual(contract.joints.training_indices, list(range(12)))
        self.assertEqual(contract.joints.mujoco_indices, list(range(7, 19)))
        self.assertEqual(
            contract.joints.deploy_indices,
            [3, 4, 5, 0, 1, 2, 9, 10, 11, 6, 7, 8],
        )
        self.assertIsNone(contract.joints.direction_multipliers)
        self.assertIsNone(contract.physics_hz)
        self.assertEqual(contract.control_hz, 50)

    def test_go2_evidence_files_match_hashes(self) -> None:
        contract = load_robot_contract(FIXTURE)

        for evidence in contract.evidence:
            source = WORKSPACE / evidence.path
            self.assertTrue(source.is_file(), evidence.path)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), evidence.sha256)

    def test_invalid_go2_contract_fails(self) -> None:
        cases = [
            (lambda data: data["joints"].update(training_indices=[0]), "training_indices"),
            (lambda data: data.update(default_pose=[0.0]), "default_pose length"),
            (lambda data: data["evidence"][0].update(sha256="bad"), "sha256"),
        ]
        for mutate, error in cases:
            with self.subTest(error=error), tempfile.TemporaryDirectory() as directory:
                data = json.loads(FIXTURE.read_text(encoding="utf-8"))
                mutate(data)
                invalid = Path(directory) / "invalid.json"
                invalid.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaisesRegex(ValidationError, error):
                    load_robot_contract(invalid)


if __name__ == "__main__":
    unittest.main()
