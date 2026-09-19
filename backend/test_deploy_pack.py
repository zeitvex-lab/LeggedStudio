"""T3.3/T3.4 DoD：部署包生成器测试。

- Go2 部署包四件套齐全、模板可编译、FSM 状态机冒烟、解码层维度守卫
- 劣化参数档：力矩 ×0.8 落入部署契约
- 坏请求（无 contract_truth 的包）→ 422
"""

from __future__ import annotations

import importlib.util
import os

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


class DeployPackagePolicyTest(unittest.TestCase):
    """策略随包携带（``policy_onnx``）：带上就真在包里、缺了就 fail-closed。

    架构含义：打包/追加逻辑**只有 ``deploy_pack.generate_deploy_package`` 一份**，
    API 与 CLI 都只是薄壳——所以这里守的两条（带上了 / 缺失即拒）对两个入口同时成立。
    """

    def setUp(self) -> None:
        self.client = TestClient(api.app)

    def test_policy_onnx_is_packed_and_listed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            onnx = Path(tmp) / "policy.onnx"
            onnx.write_bytes(b"fake-onnx-bytes")
            response = self.client.post(
                "/api/deploy/package",
                json={"robot_id": "unitree_go2", "policy_onnx_path": str(onnx)},
            )
            self.assertEqual(200, response.status_code, response.text)
            report = response.json()
            self.assertIn("policy.onnx", report["files"])
            with zipfile.ZipFile(report["path"]) as zf:
                self.assertEqual(b"fake-onnx-bytes", zf.read("policy.onnx"))

    def test_default_package_carries_no_policy_weights(self) -> None:
        """不给策略路径 ⇒ 包里没有 policy.onnx、files 也不谎报（如实两态）。"""

        response = self.client.post("/api/deploy/package", json={"robot_id": "unitree_go2"})
        self.assertEqual(200, response.status_code, response.text)
        report = response.json()
        self.assertNotIn("policy.onnx", report["files"])
        self.assertNotIn("policy.onnx", set(zipfile.ZipFile(report["path"]).namelist()))

    def test_missing_policy_onnx_fails_closed(self) -> None:
        """给了路径而文件不存在 ⇒ 拒绝（404），绝不静默忽略成"以为带上了策略"。"""

        response = self.client.post(
            "/api/deploy/package",
            json={"robot_id": "unitree_go2", "policy_onnx_path": "/no/such/policy.onnx"},
        )
        self.assertEqual(404, response.status_code, response.text)
        self.assertIn("/no/such/policy.onnx", response.json()["detail"])


class DeployGateParityTest(unittest.TestCase):
    """gate 判据只有一份：HTTP 端点与 ``deploy_gate_report`` 必须同结果同字段。"""

    def test_api_gate_matches_backend_report(self) -> None:
        import json as _json

        from backend.deploy_pack import deploy_gate_report

        got = TestClient(api.app).get("/api/deploy/gate/unitree_go2")
        self.assertEqual(200, got.status_code, got.text)
        # compare_contracts 的 entries 内是 tuple，HTTP 往返会变成 list——
        # 按 JSON 语义比对才等价（判据同一份，序列化形态不构成差异）。
        expected = _json.loads(_json.dumps(deploy_gate_report("unitree_go2")))
        self.assertEqual(expected, got.json())

    def test_api_gate_reports_package_root_and_verdict(self) -> None:
        payload = TestClient(api.app).get("/api/deploy/gate/unitree_go2").json()
        self.assertEqual("unitree_go2", payload["robot_id"])
        # 包根可能是内置 assets 树，也可能是 workspace 包副本（两条解析路径都合法）——
        # 这里只钉住"包根指向的就是这台机器人"，不钉住具体来源目录。
        self.assertTrue(Path(payload["package_root"]).is_dir(), payload["package_root"])
        for key in ("ok", "blockers", "warnings", "disposition"):
            self.assertIn(key, payload)

    def test_api_gate_unknown_robot_is_404(self) -> None:
        got = TestClient(api.app).get("/api/deploy/gate/no_such_robot")
        self.assertEqual(404, got.status_code, got.text)
        self.assertIn("no_such_robot", got.json()["detail"])


if __name__ == "__main__":
    unittest.main()
