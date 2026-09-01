import unittest

from fastapi.testclient import TestClient

from backend.api_complete import app
from backend.robot_presets import list_robot_presets


class CompleteApiContractTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
