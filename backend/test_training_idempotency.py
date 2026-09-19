"""Feature 13：训练创建幂等（Idempotency-Key）+ resume_from 配置传递测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from contracts.contract_legacy_v2 import ContractLegacyV2


def _manager(workspace_dir: str):
    # Import lazily to avoid any torch chain at module import.
    from backend.training_manager import TrainingManager
    return TrainingManager(workspace_dir=workspace_dir)


def _sample_contract() -> ContractLegacyV2:
    """Load a real, schema-valid ContractLegacyV2 fixture from contracts/fixtures."""
    fixtures = Path(__file__).resolve().parents[1] / "contracts" / "fixtures" / "unitree_go2.v2.json"
    return ContractLegacyV2.from_json_file(str(fixtures))


class TrainingIdempotencyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name) / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.contract = _sample_contract()
        self.base_config = {
            "backend": "native_mjlab",
            "algorithm": "PPO",
            "max_iterations": 100,
        }

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _stub_manager(self, root: str):
        manager = _manager(root)
        manager.launcher.launch_training = mock.Mock(return_value="x")  # type: ignore[assignment]
        return manager

    def test_create_task_returns_task_id(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            manager = self._stub_manager(str(Path(d) / "w"))
            tid = manager.create_task(contract=self.contract, config=self.base_config)
            self.assertTrue(tid)

    def test_idempotent_replay_returns_same_task(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            manager = self._stub_manager(str(Path(d) / "w"))
            tid1 = manager.create_task(contract=self.contract, config=self.base_config, idempotency_key="key-abc")
            tid2 = manager.create_task(contract=self.contract, config=self.base_config, idempotency_key="key-abc")
            self.assertEqual(tid1, tid2)
            self.assertEqual(len(manager.list_tasks()), 1)
            self.assertEqual(manager.launcher.launch_training.call_count, 1)

    def test_distinct_keys_create_distinct_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            manager = self._stub_manager(str(Path(d) / "w"))
            tid1 = manager.create_task(contract=self.contract, config=self.base_config, idempotency_key="key-1")
            tid2 = manager.create_task(contract=self.contract, config=self.base_config, idempotency_key="key-2")
            self.assertNotEqual(tid1, tid2)

    def test_resolve_idempotency_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            w = str(Path(d) / "w")
            manager = self._stub_manager(w)
            tid = manager.create_task(contract=self.contract, config=self.base_config, idempotency_key="persist-key")
            # Simulate a control-plane restart: new manager re-reads the map.
            manager2 = self._stub_manager(w)
            replayed = manager2.resolve_idempotency("persist-key")
            self.assertEqual(replayed, tid)

    def test_resume_from_flows_into_config(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = str(Path(d) / "w")
            manager = self._stub_manager(root)
            config = dict(self.base_config)
            config["resume_from"] = "/tmp/model_500.pt"
            # Capture what the launcher hands to the worker process.
            captured = {}
            def fake_launch(contract_path, config, task_id=None):
                captured["config"] = config
                captured["task_id"] = task_id
                return task_id
            manager.launcher.launch_training = fake_launch  # type: ignore[assignment]
            tid = manager.create_task(contract=self.contract, config=config)
            self.assertIsNotNone(tid)
            self.assertEqual(captured["config"].get("resume_from"), "/tmp/model_500.pt")


if __name__ == "__main__":
    unittest.main()
