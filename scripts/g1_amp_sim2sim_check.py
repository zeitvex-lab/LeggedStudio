# -*- coding: utf-8 -*-
"""G1 AMP 策略（parkour 96 维契约）桌面 sim2sim 验证环。"""
import re
import tempfile
from pathlib import Path

import mujoco
import numpy as np
import onnxruntime as ort

PKG = Path(r"C:\Users\31560\Documents\00_open\legged_studio\assets\robots\unitree_g1")
config = __import__("json").loads((PKG / "simulation" / "config.json").read_text(encoding="utf-8"))
pol = config["policies"][0]
contract = pol["contract"]
import numpy as _np
kp = _np.array([config["stiffness"][j] for j in config["stiffness"]])
kd = _np.array([config["damping"][j] for j in config["stiffness"]])
scale_by_joint = contract["action_scale_by_joint"]
joints = list(config['stiffness'].keys())
contract_json = __import__("json").loads((PKG / "contract.json").read_text(encoding="utf-8"))
default_pose = np.array(contract_json["joints"]["default_pose"], dtype=np.float64)

import onnxruntime as ort
sess = ort.InferenceSession(str(PKG / "simulation" / "policies" / pol["path"].split("/")[-1]), providers=["CPUExecutionProvider"])
inp = sess.get_inputs()[0]
obs_dim, action_dim = inp.shape[1], sess.get_outputs()[0].shape[1]
print(f"policy {pol['id']}: obs {obs_dim} -> act {action_dim}")

# 场景布局（meshdir 规范化）
scene = (PKG / "simulation" / "scene.xml").read_text(encoding="utf-8")
model_xml = (PKG / "model" / "robot.xml").read_text(encoding="utf-8")
root = tempfile.mkdtemp()
Path(root + "/model/assets").mkdir(parents=True)
open(root + "/scene.xml", "w", encoding="utf-8").write(scene.replace('include file="../model/robot.xml"', 'include file="model/robot.xml"'))
open(root + "/model/robot.xml", "w", encoding="utf-8").write(model_xml)
for f in (PKG / "model" / "assets").iterdir():
    open(root + "/model/assets/" + f.name, "wb").write(f.read_bytes())
model = mujoco.MjModel.from_xml_path(root + "/scene.xml")
data = mujoco.MjData(model)
print("compile OK nq =", model.nq, "nu =", model.nu)

data.qpos[:] = np.r_[0, 0, 0.78, 1, 0, 0, 0, default_pose]
mujoco.mj_forward(model, data)

act = np.zeros(action_dim, dtype=np.float32)
cmd = np.array([0.5, 0.0, 0.0])

STEPS = 800
for t in range(STEPS):
    if t % 4 == 0:
        quat = data.qpos[3:7]
        g_body = np.zeros(3)
        mujoco.mju_rotVecQuat(g_body, np.array([0, 0, -1.0]), quat)
        lin_b = np.zeros(3)
        mujoco.mju_rotVecQuat(lin_b, data.qvel[0:3], quat)
        ang_b = data.qvel[3:6].copy()
        jpos = data.qpos[7:] - default_pose
        jvel = data.qvel[6:]
        obs = np.concatenate([ang_b, g_body, cmd, jpos, jvel, act]).astype(np.float32)[None, :]
        act = sess.run(None, {inp.name: obs})[0][0]
    for i, j in enumerate(joints):
        target = default_pose[i] + float(act[i]) * scale_by_joint[j]
        q, dq = data.qpos[7 + i], data.qvel[6 + i]
        limit = config["torque_limits"].get(j, 88)
        data.ctrl[i] = max(-limit, min(limit, kp[i] * (target - q) - kd[i] * dq))
    mujoco.mj_step(model, data)
    if t % 100 == 0:
        print(f"t={t*0.005:5.2f}s z={data.qpos[2]:.3f} x={data.qpos[0]:+.3f}")
print(f"FINAL z={data.qpos[2]:.3f} x={data.qpos[0]:+.3f} (z>=0.6 且 x 前进 = 通过)")
