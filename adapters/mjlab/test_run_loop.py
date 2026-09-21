"""NativeRunLoop（运行期调度循环）的单元测试。

编排口径与 runtime_interfaces 生命周期一致：每个控制步做 ``decimation`` 次物理子步，
再取观测 → 策略一步 → 施加动作 → 记录样本。记录器/观测构造以注入件参与，
本测试只钉**编排**（子步数、策略步数、样本数、仿真时间），不钉观测语义。
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import mujoco
import numpy as np
import onnx
from onnx import TensorProto, helper

from contracts import simulation_run_contract as rc

from .policy_runtime import OnnxPolicyRuntime
from .run_loop import NativeRunLoop

_MJCF = (
    "<mujoco>"
    "<worldbody><body name='b' pos='0 0 1'>"
    "<joint name='j' type='hinge' axis='0 1 0'/><geom type='sphere' size='0.1'/>"
    "</body></worldbody>"
    "<actuator><motor joint='j' gear='1'/></actuator>"
    "</mujoco>"
)


def _policy_blob(obs_dim: int = 4, act_dim: int = 1) -> bytes:
    x = helper.make_tensor_value_info("obs", TensorProto.FLOAT, [1, obs_dim])
    y = helper.make_tensor_value_info("actions", TensorProto.FLOAT, [1, act_dim])
    w = helper.make_tensor("W", TensorProto.FLOAT, [obs_dim, act_dim], [0.5] * (obs_dim * act_dim))
    node = helper.make_node("MatMul", ["obs", "W"], ["actions"])
    graph = helper.make_graph([node], "p", [x], [y], [w])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 9
    onnx.checker.check_model(model)
    return model.SerializeToString()


def _binding(obs_dim: int = 4) -> rc.PolicyInputBinding:
    return rc.PolicyInputBinding(
        name="obs", kind="proprio", tensor_shape=(1, obs_dim), dtype="f4",
        source="state", verified=True, verified_by="onnx_metadata", evidence="fixture",
    )


class _MemoryRecorder:
    def __init__(self) -> None:
        self.samples = []
        self.statuses = []

    def accept_sample(self, envelope, payload) -> bool:
        self.samples.append((envelope, payload))
        return True

    def accept_status(self, snapshot) -> None:
        self.statuses.append(dict(snapshot))


class NativeRunLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = mujoco.MjModel.from_xml_string(_MJCF)
        self.data = mujoco.MjData(self.model)
        self.runtime = OnnxPolicyRuntime([_binding()])
        self.runtime.load(model_bytes=_policy_blob())
        self.recorder = _MemoryRecorder()
        self.obs_calls: list = []

    def _obs_builder(self, model, data, last_action):
        self.obs_calls.append(None if last_action is None else list(last_action))
        return np.ones(4, dtype=np.float32)

    def _make_sample(self, tick, sim_time, array):
        payload = np.ascontiguousarray(array, dtype=np.float32).tobytes()
        envelope = rc.SampleEnvelope(
            run_id="run1", epoch=0, seq=tick, instance_id="state0", plugin_id="imu",
            plugin_version="1.0.0", output="base_state", sample_tick=tick,
            available_tick=tick, sim_time=sim_time, shape=tuple(np.asarray(array).shape),
            dtype="f4", unit="m", payload_kind="tensor", payload_bytes=len(payload),
            checksum="0" * 64,
        )
        return envelope, payload

    def test_loop_runs_decimation_substeps_per_control_step_and_records(self) -> None:
        loop = NativeRunLoop(
            model=self.model, data=self.data, runtime=self.runtime,
            recorder=self.recorder, obs_builder=self._obs_builder,
            make_sample=self._make_sample, decimation=2, control_steps=5,
        )

        result = loop.run(seed=0)

        self.assertEqual(result["steps"], 5)
        self.assertEqual(len(self.recorder.samples), 5)
        # 5 控制步 × 2 子步 × timestep
        self.assertAlmostEqual(float(self.data.time), 5 * 2 * self.model.opt.timestep, places=6)
        # 首步无前动作，其后每步都拿到上一步动作反馈
        self.assertIsNone(self.obs_calls[0])
        self.assertIsNotNone(self.obs_calls[1])

    def test_loop_applies_policy_action_to_ctrl(self) -> None:
        loop = NativeRunLoop(
            model=self.model, data=self.data, runtime=self.runtime,
            recorder=self.recorder, obs_builder=self._obs_builder,
            make_sample=self._make_sample, decimation=1, control_steps=3,
        )

        loop.run(seed=0)

        # obs 全 1 × W(0.5×4) → action=2.0 → ctrl 被写入非零
        self.assertNotEqual(float(self.data.ctrl[0]), 0.0)

    def test_loop_emits_periodic_status(self) -> None:
        loop = NativeRunLoop(
            model=self.model, data=self.data, runtime=self.runtime,
            recorder=self.recorder, obs_builder=self._obs_builder,
            make_sample=self._make_sample, decimation=1, control_steps=4,
            status_period=2,
        )

        loop.run(seed=0)

        self.assertEqual(len(self.recorder.statuses), 2)


if __name__ == "__main__":
    unittest.main()
