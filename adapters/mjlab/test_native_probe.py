"""真实原生探测（native_probe）的单元测试。

这里的夹具是**真的**：最小 MJCF 由 mujoco 实际编译，小 ONNX 图由 onnxruntime
实际加载并推理。探测若谎报 supported，这些断言就会咬住——因为版本、特征状态
都来自真实运行时，而不是字典字面量。
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import mujoco
import onnx
import onnxruntime as ort
from onnx import TensorProto, helper

from backend import simulation_resolver as sr
from contracts import simulation_run_contract as rc

from .native_probe import probe_native

_MIN_MJCF = (
    "<mujoco>"
    "<worldbody><body name='base'>"
    "<joint type='free'/><geom type='sphere' size='0.1'/>"
    "</body></worldbody>"
    "</mujoco>"
)


def _write_real_onnx(path: Path, *, obs_dim: int = 4, act_dim: int = 2) -> Path:
    """造一个能被 onnxruntime 真实加载/推理的极小策略图：obs[1,N] -> actions[1,M]。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    x = helper.make_tensor_value_info("obs", TensorProto.FLOAT, [1, obs_dim])
    y = helper.make_tensor_value_info("actions", TensorProto.FLOAT, [1, act_dim])
    w = helper.make_tensor("W", TensorProto.FLOAT, [obs_dim, act_dim], [0.1] * (obs_dim * act_dim))
    node = helper.make_node("MatMul", ["obs", "W"], ["actions"])
    graph = helper.make_graph([node], "policy", [x], [y], [w])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 9
    onnx.checker.check_model(model)
    path.write_bytes(model.SerializeToString())
    return path


def _write_model(path: Path, xml: str = _MIN_MJCF) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(xml, encoding="utf-8")
    return path


def _draft(
    root: Path,
    *,
    model: Path | None,
    onnx_path: Path | None,
    required: tuple[str, ...] = (
        "model_compile",
        "physics_substep",
        "onnx_inference",
        "policy_closed_loop",
        "episode_record",
    ),
) -> dict:
    return {
        "robot_id": "fixture_bot",
        "package_root": str(root),
        "policy_id": "fixture_policy",
        "model_path": str(model) if model is not None else None,
        "policy_onnx_path": str(onnx_path) if onnx_path is not None else None,
        "required_features": list(required),
        "time_base": {"physics_hz": 500.0, "decimation": 10, "control_hz": 50.0},
        "plugin_ids": [],
        "provider_id": None,
        "duration_s": 4.0,
    }


class NativeProbeExecutionTests(unittest.TestCase):
    """探测必须**真的**跑 mujoco + onnxruntime，并如实记录版本与特征状态。"""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_probe_runs_real_runtime_and_reports_supported_execution_features(self) -> None:
        model = _write_model(self.root / "model" / "robot.xml")
        policy = _write_real_onnx(self.root / "simulation" / "policies" / "p.onnx")

        report = probe_native(_draft(self.root, model=model, onnx_path=policy))

        self.assertIsInstance(report, rc.NativeProbeReport)
        self.assertTrue(report.probed)
        self.assertEqual(report.reason, "probed")
        # 版本来自真实运行时，不是硬编码字面量。
        self.assertEqual(report.mujoco_version, mujoco.__version__)
        self.assertEqual(report.onnxruntime_version, ort.__version__)
        self.assertTrue(report.python_version)
        self.assertIsNotNone(report.probed_at_unix)
        for feature in ("model_compile", "physics_substep", "onnx_inference", "policy_closed_loop"):
            self.assertEqual(report.state_of(feature), "supported", feature)

    def test_report_satisfies_contract_identity(self) -> None:
        model = _write_model(self.root / "model" / "robot.xml")
        policy = _write_real_onnx(self.root / "p.onnx")

        report = probe_native(_draft(self.root, model=model, onnx_path=policy))

        self.assertEqual(report.executor_id, rc.NATIVE_EXECUTOR_ID)
        self.assertEqual(report.native_runtime_version, rc.NATIVE_RUNTIME_VERSION)

    def test_missing_model_marks_compile_and_substep_unsupported_but_keeps_onnx(self) -> None:
        policy = _write_real_onnx(self.root / "p.onnx")
        missing = self.root / "model" / "gone.xml"

        report = probe_native(_draft(self.root, model=missing, onnx_path=policy))

        self.assertTrue(report.probed)  # 部分失败仍如实探测，不崩、不谎报
        self.assertEqual(report.state_of("model_compile"), "unsupported")
        self.assertEqual(report.state_of("physics_substep"), "unsupported")
        self.assertEqual(report.state_of("policy_closed_loop"), "unsupported")
        self.assertEqual(report.state_of("onnx_inference"), "supported")

    def test_bad_policy_marks_inference_and_closed_loop_unsupported(self) -> None:
        model = _write_model(self.root / "model" / "robot.xml")
        bad = self.root / "p.onnx"
        bad.write_bytes(b"not-an-onnx-model")

        report = probe_native(_draft(self.root, model=model, onnx_path=bad))

        self.assertTrue(report.probed)
        self.assertEqual(report.state_of("model_compile"), "supported")
        self.assertEqual(report.state_of("physics_substep"), "supported")
        self.assertEqual(report.state_of("onnx_inference"), "unsupported")
        self.assertEqual(report.state_of("policy_closed_loop"), "unsupported")

    def test_absent_policy_path_is_unsupported_not_guessed(self) -> None:
        model = _write_model(self.root / "model" / "robot.xml")

        report = probe_native(_draft(self.root, model=model, onnx_path=None))

        self.assertEqual(report.state_of("onnx_inference"), "unsupported")
        self.assertEqual(report.state_of("policy_closed_loop"), "unsupported")

    def test_unverifiable_required_feature_stays_unknown(self) -> None:
        """探测没实现核验的特征只能是 unknown，绝不能猜成 supported。"""

        model = _write_model(self.root / "model" / "robot.xml")
        policy = _write_real_onnx(self.root / "p.onnx")
        draft = _draft(
            self.root,
            model=model,
            onnx_path=policy,
            required=("model_compile", "raycast", "offscreen_render"),
        )

        report = probe_native(draft)

        self.assertEqual(report.state_of("model_compile"), "supported")
        self.assertEqual(report.state_of("raycast"), "unknown")
        self.assertEqual(report.state_of("offscreen_render"), "unknown")
        self.assertFalse(report.is_supported("raycast"))

    def test_episode_record_is_verified_by_recorder_selftest(self) -> None:
        """记录子系统自检通过 → episode_record 如实标 supported（存储原语真跑过）。"""

        model = _write_model(self.root / "model" / "robot.xml")
        policy = _write_real_onnx(self.root / "p.onnx")

        report = probe_native(_draft(self.root, model=model, onnx_path=policy))

        self.assertEqual(report.state_of("episode_record"), "supported")


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_real_package(
    root: Path, *, robot_id: str = "fixture_go2", obs_dim: int = 45, act_dim: int = 12
) -> Path:
    """造一个**产物是真的**机器人包：真实可编译 MJCF + 真实可推理 ONNX。"""

    pkg = root / "packages" / robot_id
    _write_json(
        pkg / "robot_package.json",
        {"package_id": robot_id, "model": {"path": "model/robot.xml"}},
    )
    _write_json(pkg / "contract.json", {"control": {"physics_hz": 500, "decimation": 10}})
    _write_model(pkg / "model" / "robot.xml")
    rel = "simulation/policies/fixture.onnx"
    _write_json(
        pkg / "simulation" / "config.json",
        {"policies": [{"id": "fixture_trot", "path": rel, "obs_dim": obs_dim, "contract": {}}]},
    )
    _write_real_onnx(pkg / rel, obs_dim=obs_dim, act_dim=act_dim)
    return pkg


class NativeProbeResolveIntegrationTests(unittest.TestCase):
    """把真实探测注入解析器：证明 ``resolve_run`` 消费的是**真跑过**的报告。"""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_resolve_completes_with_real_probe_once_recorder_is_available(self) -> None:
        pkg = _write_real_package(self.root)

        response = sr.resolve_run(
            {
                "schema_version": rc.RUN_CONTRACT_VERSION,
                "scenario": {
                    "schema_version": "scenario-contract-1.2",
                    "scenario_id": "fixture_run",
                    "episode_length_s": 4.0,
                    "advanced": {},
                },
                "options": {
                    "robot_id": "fixture_go2",
                    "policy_id": "fixture_trot",
                    "seed": 3,
                    "duration_s": 4.0,
                },
            },
            package_root=pkg,
            repo_root=self.root,
            probe=probe_native,
        )

        messages = [blocker.as_message() for blocker in response.blockers]
        self.assertTrue(response.ok, messages)
        self.assertIsNotNone(response.spec)
        # 五项必需能力都被真实探测确认为 available。
        capabilities = response.spec.capabilities
        self.assertTrue(capabilities.probed)
        for feature in (
            "model_compile",
            "physics_substep",
            "onnx_inference",
            "policy_closed_loop",
            "episode_record",
        ):
            self.assertEqual(capabilities.level_of(feature), "available", feature)


if __name__ == "__main__":
    unittest.main()
