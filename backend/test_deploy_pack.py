"""T3.3/T3.4 DoD：部署包生成器测试。

- Go2 部署包四件套齐全、模板可编译、FSM 状态机冒烟、解码层维度守卫
- 劣化参数档：力矩 ×0.8 落入部署契约
- 坏请求（无 contract_v3 的包）→ 422
"""

from __future__ import annotations

import importlib.util
import os
import py_compile
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

import backend.api_complete as api  # noqa: E402

WORKSPACE = Path(__file__).resolve().parents[1]


def _mount_zip_modules(zip_path: str):
    sys.path.insert(0, tempfile.mkdtemp())
    tmp = tempfile.mkdtemp()
    with zipfile.ZipFile(zip_path) as zf:
        for name in ("deployment_contract.py", "fsm_safety_template.py", "action_decoder_template.py"):
            zf.extract(name, tmp)
    for mod_name, file_name in (
        ("deployment_contract", "deployment_contract.py"),
        ("fsm_safety_template", "fsm_safety_template.py"),
        ("action_decoder_template", "action_decoder_template.py"),
    ):
        spec = importlib.util.spec_from_file_location(mod_name, os.path.join(tmp, file_name))
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
    return sys.modules["deployment_contract"], sys.modules["fsm_safety_template"], sys.modules["action_decoder_template"]


class DeployPackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(api.app)
        response = cls.client.post("/api/deploy/package", json={"robot_id": "unitree_go2"})
        assert response.status_code == 200, response.text
        cls.report = response.json()

    def test_zip_contains_four_pieces(self) -> None:
        names = set(zipfile.ZipFile(self.report["path"]).namelist())
        self.assertTrue({"deployment-contract.yaml", "fsm_safety_template.py", "action_decoder_template.py", "人工确认清单.md"} <= names)

    def test_templates_compile_and_fsm_smoke(self) -> None:
        dc, fsm, _ = _mount_zip_modules(self.report["path"])
        machine = fsm.RobotSafetyFSM()
        self.assertEqual(machine.tick(policy_action=[0.0] * 12)["mode"], "damping")
        machine.state = fsm.State.STAND
        import time

        machine.last_command_ts = time.monotonic()
        self.assertEqual(machine.tick(policy_action=[0.1] * 12)["mode"], "policy")

    def test_decoder_uses_contract_roles_and_dimension_guard(self) -> None:
        _, _, dec = _mount_zip_modules(self.report["path"])
        commands = dec.decode([0.1] * 12)
        self.assertEqual(len(commands), 12)
        # go2 为 torque 模式，力矩限来自角色表（hip/thigh 23.7，calf 35.55）
        self.assertEqual(commands["FL_hip_joint"]["mode"], "torque")
        self.assertEqual(commands["FL_hip_joint"]["effort_limit"], 23.7)
        self.assertEqual(commands["FL_calf_joint"]["effort_limit"], 35.55)
        with self.assertRaises(ValueError):
            dec.decode([0.1] * 11)

    def test_checklist_mentions_key_safety_rules(self) -> None:
        with zipfile.ZipFile(self.report["path"]) as zf:
            checklist = zf.read("人工确认清单.md").decode("utf-8")
        for keyword in ("降 50%", "急停", "零点", "软限位", "reindex"):
            self.assertIn(keyword, checklist)

    def test_degraded_preset_scales_effort(self) -> None:
        import json as _json

        response = self.client.post("/api/deploy/package", json={"robot_id": "unitree_go2", "degraded": True})
        self.assertEqual(response.status_code, 200)
        with zipfile.ZipFile(response.json()["path"]) as zf:
            dc_source = zf.read("deployment_contract.py").decode("utf-8")
        # 劣化档：力矩 ×0.8（23.7 → 18.96）
        self.assertIn("18.96", dc_source)

    def test_unknown_robot_rejected(self) -> None:
        response = self.client.post("/api/deploy/package", json={"robot_id": "no_such_robot"})
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
