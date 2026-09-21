"""OnnxPolicyRuntime（PolicyRuntimeProtocol 的 onnxruntime 实现）的单元测试。

夹具是**真产物**：onnx 现造、onnxruntime 真加载真推理。运行时对声明绑定与产物
逐项对账（名称+形状+dtype），不符即抛 PolicyRuntimeError——不广播、不近似、不静默转换。
"""

from __future__ import annotations

import unittest

import numpy as np
import onnx
import onnxruntime as ort  # noqa: F401  (确保环境可用；实际加载在运行时内部)
from onnx import TensorProto, helper

from contracts import simulation_run_contract as rc
from contracts.runtime_interfaces import PolicyRuntimeError, PolicyRuntimeProtocol

from .policy_runtime import OnnxPolicyRuntime

_OBS_DIM = 45
_ACT_DIM = 12


def _policy_blob(*, obs_dim: int = _OBS_DIM, act_dim: int = _ACT_DIM) -> bytes:
    """造真实策略图：obs[1,obs_dim] (float32) -> actions[1,act_dim]。"""

    x = helper.make_tensor_value_info("obs", TensorProto.FLOAT, [1, obs_dim])
    y = helper.make_tensor_value_info("actions", TensorProto.FLOAT, [1, act_dim])
    w = helper.make_tensor("W", TensorProto.FLOAT, [obs_dim, act_dim], [0.1] * (obs_dim * act_dim))
    node = helper.make_node("MatMul", ["obs", "W"], ["actions"])
    graph = helper.make_graph([node], "policy", [x], [y], [w])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 9
    onnx.checker.check_model(model)
    return model.SerializeToString()


def _binding(
    *, name: str = "obs", shape: tuple[int, ...] = (1, _OBS_DIM), dtype: str = "f4"
) -> rc.PolicyInputBinding:
    return rc.PolicyInputBinding(
        name=name,
        kind="proprio",
        tensor_shape=shape,
        dtype=dtype,
        source="state",
        verified=True,
        verified_by="onnx_metadata",
        evidence="fixture",
    )


def _loaded(*bindings: rc.PolicyInputBinding) -> OnnxPolicyRuntime:
    runtime = OnnxPolicyRuntime(list(bindings) or [_binding()])
    runtime.load(model_bytes=_policy_blob())
    return runtime


class PolicyRuntimeLoadTests(unittest.TestCase):
    def test_load_echoes_declared_inputs_and_reads_output_names_from_product(self) -> None:
        runtime = _loaded()

        self.assertIsInstance(runtime, PolicyRuntimeProtocol)
        self.assertEqual(runtime.declared_inputs, (_binding(),))
        self.assertEqual(runtime.output_names, ("actions",))

    def test_load_rejects_binding_absent_from_product(self) -> None:
        runtime = OnnxPolicyRuntime([_binding(name="ghost")])

        with self.assertRaises(PolicyRuntimeError) as ctx:
            runtime.load(model_bytes=_policy_blob())
        self.assertEqual(ctx.exception.code, "input_missing")

    def test_load_rejects_shape_mismatch(self) -> None:
        runtime = OnnxPolicyRuntime([_binding(shape=(1, _OBS_DIM - 1))])

        with self.assertRaises(PolicyRuntimeError) as ctx:
            runtime.load(model_bytes=_policy_blob())
        self.assertEqual(ctx.exception.code, "shape_mismatch")

    def test_load_rejects_dtype_mismatch(self) -> None:
        runtime = OnnxPolicyRuntime([_binding(dtype="f8")])

        with self.assertRaises(PolicyRuntimeError) as ctx:
            runtime.load(model_bytes=_policy_blob())
        self.assertEqual(ctx.exception.code, "dtype_mismatch")

    def test_load_rejects_unreadable_bytes(self) -> None:
        runtime = OnnxPolicyRuntime([_binding()])

        with self.assertRaises(PolicyRuntimeError) as ctx:
            runtime.load(model_bytes=b"not-an-onnx")
        self.assertEqual(ctx.exception.code, "load_failed")


class PolicyRuntimeStepTests(unittest.TestCase):
    def test_step_runs_real_inference_and_returns_named_outputs(self) -> None:
        runtime = _loaded()

        outputs = runtime.step({"obs": np.zeros((1, _OBS_DIM), dtype=np.float32)})

        self.assertIn("actions", outputs)
        self.assertEqual(tuple(outputs["actions"].shape), (1, _ACT_DIM))
        self.assertTrue(np.all(np.isfinite(outputs["actions"])))

    def test_step_rejects_wrong_shape_without_broadcast(self) -> None:
        runtime = _loaded()

        with self.assertRaises(PolicyRuntimeError) as ctx:
            runtime.step({"obs": np.zeros((1, _OBS_DIM - 1), dtype=np.float32)})
        self.assertEqual(ctx.exception.code, "shape_mismatch")

    def test_step_rejects_wrong_dtype_without_silent_cast(self) -> None:
        runtime = _loaded()

        with self.assertRaises(PolicyRuntimeError) as ctx:
            runtime.step({"obs": np.zeros((1, _OBS_DIM), dtype=np.float64)})
        self.assertEqual(ctx.exception.code, "dtype_mismatch")

    def test_step_rejects_missing_input(self) -> None:
        runtime = _loaded()

        with self.assertRaises(PolicyRuntimeError) as ctx:
            runtime.step({})
        self.assertEqual(ctx.exception.code, "input_missing")

    def test_step_before_load_raises(self) -> None:
        runtime = OnnxPolicyRuntime([_binding()])

        with self.assertRaises(PolicyRuntimeError) as ctx:
            runtime.step({"obs": np.zeros((1, _OBS_DIM), dtype=np.float32)})
        self.assertEqual(ctx.exception.code, "not_loaded")


class PolicyRuntimeLifecycleTests(unittest.TestCase):
    def test_reset_keeps_runtime_usable_for_the_next_epoch(self) -> None:
        runtime = _loaded()
        runtime.step({"obs": np.zeros((1, _OBS_DIM), dtype=np.float32)})

        runtime.reset(seed=7)
        outputs = runtime.step({"obs": np.zeros((1, _OBS_DIM), dtype=np.float32)})

        self.assertEqual(tuple(outputs["actions"].shape), (1, _ACT_DIM))

    def test_dispose_is_idempotent_and_blocks_further_steps(self) -> None:
        runtime = _loaded()

        runtime.dispose()
        runtime.dispose()  # 幂等，不抛

        with self.assertRaises(PolicyRuntimeError) as ctx:
            runtime.step({"obs": np.zeros((1, _OBS_DIM), dtype=np.float32)})
        self.assertEqual(ctx.exception.code, "not_loaded")


if __name__ == "__main__":
    unittest.main()
