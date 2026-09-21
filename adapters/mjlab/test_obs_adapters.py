"""ProprioFrameBuilder（本体观测适配器）的单元测试。

钉住 45D 帧的**段序与缩放**，与浏览器 ``fillRlSdkActorFrame`` / 桌面 ``ObsBuilder`` 同源：
[ang_vel×ang_scale(3), projected_gravity(3), cmd×cmd_scale(3),
 (qpos−default)×pos_scale(12), qvel×vel_scale(12), last_action(12)]。
关节槽按契约 ``joint_order`` 名字解析到模型地址（不按模型物理序）。
"""

from __future__ import annotations

import unittest

import mujoco
import numpy as np

from .obs_adapters import ProprioFrameBuilder

_JOINTS_MODEL_ORDER = [
    "FL_hip_joint", "FL_thigh_joint", "FL_calf_joint",
    "FR_hip_joint", "FR_thigh_joint", "FR_calf_joint",
    "RL_hip_joint", "RL_thigh_joint", "RL_calf_joint",
    "RR_hip_joint", "RR_thigh_joint", "RR_calf_joint",
]
_JOINT_ORDER = [
    "FR_hip_joint", "FR_thigh_joint", "FR_calf_joint",
    "FL_hip_joint", "FL_thigh_joint", "FL_calf_joint",
    "RR_hip_joint", "RR_thigh_joint", "RR_calf_joint",
    "RL_hip_joint", "RL_thigh_joint", "RL_calf_joint",
]


def _mjcf() -> str:
    bodies = "".join(
        f"<body name='b{i}'><joint name='{name}' type='hinge' axis='0 1 0'/>"
        f"<geom type='sphere' size='0.02'/></body>"
        for i, name in enumerate(_JOINTS_MODEL_ORDER)
    )
    # 浮动基座 free joint：qpos[0:7]=根位姿、qvel[3:6]=基座角速度（与真实 go2 同构）
    return (
        "<mujoco><worldbody>"
        "<body name='base'><joint type='free'/><geom type='box' size='0.1 0.1 0.05'/>"
        + bodies
        + "</body></worldbody></mujoco>"
    )


class ProprioFrameBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = mujoco.MjModel.from_xml_string(_mjcf())
        self.data = mujoco.MjData(self.model)
        self.defaults = {name: 0.1 * i for i, name in enumerate(_JOINT_ORDER)}
        self.builder = ProprioFrameBuilder(
            joint_order=_JOINT_ORDER,
            default_angles=self.defaults,
            ang_vel_scale=0.25,
            dof_pos_scale=1.0,
            dof_vel_scale=0.05,
            command_scale=(1.0, 1.0, 1.0),
            action_dim=12,
        )
        self.builder.bind(self.model)

    def test_frame_layout_and_scales(self) -> None:
        mujoco.mj_forward(self.model, self.data)
        # 直立四元数 (w=1) → projected gravity = [0,0,-1]
        self.data.qpos[3:7] = np.array([1.0, 0.0, 0.0, 0.0])
        # 角速度原始 [0.4, -0.8, 1.2] → ×0.25
        self.data.qvel[3:6] = np.array([0.4, -0.8, 1.2])
        # 关节位置 = default + 0.5（FR_hip 槽 0）→ pos_rel = 0.5
        for slot, name in enumerate(_JOINT_ORDER):
            jid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, name)
            self.data.qpos[self.model.jnt_qposadr[jid]] = self.defaults[name] + 0.5
            self.data.qvel[self.model.jnt_dofadr[jid]] = 2.0  # ×0.05 = 0.1
        last_action = np.full(12, 0.25, dtype=np.float32)
        command = np.array([0.6, -0.2, 0.4], dtype=np.float32)

        frame = self.builder.build(self.data, last_action, command)

        self.assertEqual(frame.shape, (45,))
        np.testing.assert_allclose(frame[0:3], [0.1, -0.2, 0.3], atol=1e-5)
        np.testing.assert_allclose(frame[3:6], [0.0, 0.0, -1.0], atol=1e-5)
        np.testing.assert_allclose(frame[6:9], [0.6, -0.2, 0.4], atol=1e-5)
        np.testing.assert_allclose(frame[9:21], np.full(12, 0.5), atol=1e-5)
        np.testing.assert_allclose(frame[21:33], np.full(12, 0.1), atol=1e-5)
        np.testing.assert_allclose(frame[33:45], np.full(12, 0.25), atol=1e-5)

    def test_slot_order_follows_contract_not_model_order(self) -> None:
        mujoco.mj_forward(self.model, self.data)
        self.data.qpos[3:7] = np.array([1.0, 0.0, 0.0, 0.0])
        # 先把全部关节置到契约默认角，再只抬高 FR_hip（契约槽 0，模型序第 3）
        for name in _JOINT_ORDER:
            jid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, name)
            self.data.qpos[self.model.jnt_qposadr[jid]] = self.defaults[name]
        jid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, "FR_hip_joint")
        self.data.qpos[self.model.jnt_qposadr[jid]] = self.defaults["FR_hip_joint"] + 1.0

        frame = self.builder.build(self.data, np.zeros(12, dtype=np.float32), None)

        self.assertAlmostEqual(float(frame[9]), 1.0, places=5)  # 契约槽 0
        self.assertAlmostEqual(float(frame[12]), 0.0, places=5)  # FL_hip 槽 3 未动

    def test_last_action_defaults_to_zero(self) -> None:
        mujoco.mj_forward(self.model, self.data)
        self.data.qpos[3:7] = np.array([1.0, 0.0, 0.0, 0.0])

        frame = self.builder.build(self.data, None, None)

        np.testing.assert_allclose(frame[33:45], np.zeros(12), atol=1e-6)
        np.testing.assert_allclose(frame[6:9], np.zeros(3), atol=1e-6)


if __name__ == "__main__":
    unittest.main()
