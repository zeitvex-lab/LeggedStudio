"""原生执行链端到端：真实 go2 包 + rlsar ONNX 跑 NativeRunLoop。

对照意义：浏览器对 go2_rl_sdk_45 闭环发散（步态异常），桌面验收 pass；本测试验证
**原生链**（proprio 适配器 + OnnxPolicyRuntime + PD 力矩执行器 + 调度循环）在零指令下
能保持站立——若原生也失稳，则问题在观测/契约而非浏览器。
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import mujoco
import numpy as np

from . import policy_acceptance as pa
from contracts import simulation_run_contract as rc
from contracts.physics_binding import physics_scalars

from .obs_adapters import ProprioFrameBuilder
from .policy_runtime import OnnxPolicyRuntime
from .run_loop import NativeRunLoop

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "assets" / "robots" / "unitree_go2"
POLICY_ID = "go2-rlsar-robotlab"


class _MemoryRecorder:
    def __init__(self) -> None:
        self.samples = []

    def accept_sample(self, envelope, payload) -> bool:
        self.samples.append((envelope, payload))
        return True

    def accept_status(self, snapshot) -> None:
        pass


class NativeEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cfg = json.loads((PKG / "simulation" / "config.json").read_text(encoding="utf-8-sig"))
        cls.entry = next(p for p in cfg["policies"] if p["id"] == POLICY_ID)
        cls.contract = cls.entry["contract"]
        cls.initial_height = float(cfg.get("initial_base_height") or 0.4)

    def test_native_closed_loop_stands_under_zero_command(self) -> None:
        contract = self.contract
        # 模型用桌面参考的 load_package_model（施加契约 armature/frictionloss/timestep 增量）；
        # 裸 robot.xml 缺这些物理常量增量→动力学不一致→软增益失稳。
        cfg = json.loads((PKG / "simulation" / "config.json").read_text(encoding="utf-8-sig"))
        pa_contract = pa.PackageContract(PKG, self.entry)
        model = pa.load_package_model(PKG, cfg)
        scalars = physics_scalars(PKG)
        decimation = int(scalars["decimation"])
        data = mujoco.MjData(model)

        runtime = OnnxPolicyRuntime([
            rc.PolicyInputBinding(
                name="input", kind="proprio", tensor_shape=(1, 45), dtype="f4",
                source="state", verified=True, verified_by="onnx_metadata", evidence="e2e",
            )
        ])
        runtime.load(model_bytes=(PKG / "simulation" / "policies" / "go2_rlsar_robotlab.onnx").read_bytes())

        scales = contract.get("scales") or {}
        builder = ProprioFrameBuilder(
            joint_order=contract["action_joint_order"],
            default_angles=contract["default_joint_angles"],
            ang_vel_scale=float(scales.get("ang_vel", 0.25)),
            dof_pos_scale=float(scales.get("dof_pos", 1.0)),
            dof_vel_scale=float(scales.get("dof_vel", 0.05)),
            command_scale=tuple(scales.get("command", (1.0, 1.0, 1.0))),
            action_dim=int(contract["action_dim"]),
        )
        builder.bind(model)

        # 出生姿态 = 契约默认角 + 初始高度（与桌面 spawn_default 同口径）
        mujoco.mj_resetData(model, data)
        data.qpos[0:3] = 0.0
        data.qpos[2] = self.initial_height
        data.qpos[3:7] = np.array([1.0, 0.0, 0.0, 0.0])
        for name, angle in contract["default_joint_angles"].items():
            jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
            if jid >= 0:
                data.qpos[model.jnt_qposadr[jid]] = float(angle)
        mujoco.mj_forward(model, data)

        stiffness = (contract.get("control") or {}).get("stiffness") or contract.get("stiffness") or {}
        damping = (contract.get("control") or {}).get("damping") or contract.get("damping") or {}
        limits = contract.get("torque_limits") or {}
        scale_by_joint = contract.get("action_scale_by_joint") or {}
        default_scale = float(contract.get("action_scale", 0.25))

        addresses = []
        for i, name in enumerate(contract["action_joint_order"]):
            jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
            aid = -1
            for cand in range(model.nu):
                if int(model.actuator_trntype[cand]) == int(mujoco.mjtTrn.mjTRN_JOINT) and int(model.actuator_trnid[cand, 0]) == jid:
                    aid = cand
                    break
            addresses.append((
                aid,
                int(model.jnt_qposadr[jid]),
                int(model.jnt_dofadr[jid]),
                float(scale_by_joint.get(name, default_scale)),
                float(stiffness.get(name, 20.0)),
                float(damping.get(name, 0.5)),
                float(limits.get(name, 0.0) or 0.0),
            ))

        def pd_torque_actuator(action, _model, _data) -> None:
            for i, (aid, qadr, vadr, scale, kp, kd, limit) in enumerate(addresses):
                if aid < 0 or i >= len(action):
                    continue
                target = float(action[i]) * scale + float(contract["default_joint_angles"][contract["action_joint_order"][i]])
                torque = kp * (target - _data.qpos[qadr]) - kd * _data.qvel[vadr]
                if limit > 0:
                    torque = float(np.clip(torque, -limit, limit))
                _data.ctrl[aid] = torque

        recorder = _MemoryRecorder()
        loop = NativeRunLoop(
            model=model, data=data, runtime=runtime, recorder=recorder,
            obs_builder=lambda m, d, last: builder.build(d, last, None),
            make_sample=lambda tick, t, arr: (
                rc.SampleEnvelope(
                    run_id="e2e", epoch=0, seq=tick, instance_id="state0", plugin_id="imu",
                    plugin_version="1.0.0", output="base_state", sample_tick=tick,
                    available_tick=tick, sim_time=t, shape=tuple(np.asarray(arr).shape),
                    dtype="f4", unit="m", payload_kind="tensor",
                    payload_bytes=np.asarray(arr, dtype=np.float32).nbytes,
                    checksum="0" * 64,
                ),
                np.ascontiguousarray(arr, dtype=np.float32).tobytes(),
            ),
            decimation=decimation, control_steps=50, actuator=pd_torque_actuator,
        )

        result = loop.run(seed=0)

        self.assertEqual(result["steps"], 50)
        self.assertEqual(len(recorder.samples), 50)
        self.assertTrue(np.all(np.isfinite(data.qpos)), "原生闭环出现 NaN（观测/执行口径错）")
        # 零指令 1s 后仍站立（未跌倒）：与浏览器发散的对照点
        self.assertGreater(float(data.qpos[2]), 0.25, f"原生闭环跌倒 z={float(data.qpos[2]):.3f}")


if __name__ == "__main__":
    unittest.main()
