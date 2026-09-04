"""Headless ZEX-W sim2sim using the reference rc_mjlab code path verbatim."""
import sys, math
from pathlib import Path
import numpy as np

SIM2SIM = Path(r"C:\Users\31560\Documents\00_open\rc_old\RC_WheelLeg\05_software\train\rc_mjlab\sim2sim")
sys.path.insert(0, str(SIM2SIM))
import mujoco, onnxruntime as ort
from interface.mujoco_io import MuJoCoIO, LowPassFilter
from tools.math_utils import get_gravity_orientation

RC = SIM2SIM.parent
ONNX = RC / "model_6800.onnx"
if not ONNX.exists():
    ONNX = Path(r"C:\Users\31560\Documents\00_open\rc_old\RC_WheelLeg\05_software\real\sim2real_ros2_v3\policies\model_6800.onnx")

session = ort.InferenceSession(str(ONNX), providers=["CPUExecutionProvider"])
in_name = session.get_inputs()[0].name

def run(label, default_pose, steps=300):
    io = MuJoCoIO(RC / "sim2sim" / "terrain" / "scene_terrain.xml", RC / "mjcf" / "wheelleg.xml", RC / "sim2sim" / "terrain")
    m, d = io.m, io.d
    print(f"\n=== {label}: default={list(np.round(default_pose,3))} timestep={m.opt.timestep} nu={m.nu}")
    io.reset_robot(default_pose)
    print(f"after settle: z={d.qpos[2]:.3f} quat={np.round(d.qpos[3:7],3)}")
    lpf_legs = LowPassFilter(cutoff_freq=5.0, dt=io.control_dt, dim=12)
    lpf_wheels = LowPassFilter(cutoff_freq=15.0, dt=io.control_dt, dim=4)
    action_scale = np.array([0.125, 0.25, 0.25]*4 + [5.0]*4, dtype=np.float32)
    last_raw = np.zeros(16, dtype=np.float32)
    command = np.zeros(3, dtype=np.float32)
    decim = int(round(io.control_dt / m.opt.timestep))
    for k in range(steps):
        obs = io.get_obs_53d(command, default_pose, last_raw)
        raw = session.run(None, {in_name: obs[None].astype(np.float32)})[0][0]
        raw = np.clip(raw, -100.0, 100.0)
        last_raw = raw.astype(np.float32)
        scaled = raw * action_scale
        act = scaled + default_pose
        act = np.clip(act, -100, 100)
        act[:12] = lpf_legs.filter(act[:12])
        act[12:] = lpf_wheels.filter(act[12:])
        for i in range(16):
            d.ctrl[io.ctrl_ids[i]] = act[i]
        for _ in range(decim):
            mujoco.mj_step(m, d)
        if k % 50 == 0 or k == steps - 1:
            q = d.qpos
            roll = math.degrees(math.atan2(2*(q[3]*q[4]+q[5]*q[6]), 1-2*(q[4]**2+q[5]**2)))
            pitch = math.degrees(math.asin(max(-1, min(1, 2*(q[3]*q[5]-q[6]*q[4])))))
            print(f"t={d.time:5.1f}s z={q[2]:.3f} roll={roll:7.1f} pitch={pitch:7.1f} maxAbsRaw={np.abs(raw).max():6.2f}")
    ok = d.qpos[2] > 0.3 and abs(roll) < 25 and abs(pitch) < 25
    print(f"{label} => {'STABLE' if ok else 'FALLEN'}")
    return ok

run("ref-default [0,0.9,-1.8]", np.array([0.0, 0.9, -1.8]*4 + [0.0]*4, dtype=np.float32))
run("real-default [0,0.55,-1.125]", np.array([0.0, 0.550, -1.125]*4 + [0.0]*4, dtype=np.float32))
