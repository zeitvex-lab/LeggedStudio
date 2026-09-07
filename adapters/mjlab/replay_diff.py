"""G1 浏览器回放 vs 桌面验收 obs 逐维 diff（OPEN_QUESTIONS #5 定位工具）。

用法：
  1. 浏览器打开 ?robot=unitree_g1&policy=unitree-velocity&replay=0.4,0,0&seed=7&debug=1
  2. 控制台执行 __sim2simDebug.startFrameLog()，跑 2-3 秒后 stopFrameLog() 复制 JSON
  3. 存为 framelog.json，运行本脚本：
     python replay_diff.py --package assets/robots/unitree_g1 --framelog framelog.json

输出：逐帧逐维 obs 差异的第一个发散维度、所在观测段（ang_vel/gravity/cmd/pos/vel/action/phase），
以及两侧 obs 头部样例——直接指认根因段。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from policy_acceptance import ObsBuilder, PackageContract, load_package_model  # noqa: E402

# g1_mjlab_velocity_98 的观测段布局（与 app.js buildG1MjlabVelocityObservation 对齐）
SEGMENTS_98 = [
    ("base_ang_vel", 3), ("projected_gravity", 3), ("command", 3), ("gait_phase", 2),
    ("joint_pos_rel", 29), ("joint_vel_rel", 29), ("last_action", 29),
]


def segment_of(index: int) -> str:
    offset = 0
    for name, size in SEGMENTS_98:
        if index < offset + size:
            return f"{name}[{index - offset}]"
        offset += size
    return f"dim{index}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True)
    parser.add_argument("--policy", default="simulation/policies/unitree_velocity.onnx")
    parser.add_argument("--framelog", required=True, help="浏览器 frameLog JSON（obs 数组列表）")
    parser.add_argument("--cmd", default="0.4,0,0")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    import mujoco
    import onnxruntime as ort

    package_dir = Path(args.package).resolve()
    log = json.loads(Path(args.framelog).read_text(encoding="utf-8-sig"))
    frames = log if isinstance(log, list) else log.get("frames", [])
    if not frames:
        raise SystemExit("framelog 为空")
    browser_obs = np.asarray([f["obs"] for f in frames], dtype=np.float32)
    print(f"浏览器帧数: {len(frames)}，obs 维度: {browser_obs.shape[1]}")

    sim_cfg = json.loads((package_dir / "simulation" / "config.json").read_text(encoding="utf-8-sig"))
    contract = PackageContract(package_dir, next(
        (p for p in sim_cfg.get("policies", []) if p.get("id") == "unitree-velocity"), sim_cfg["policies"][0]))
    model = load_package_model(package_dir, sim_cfg)
    model.opt.timestep = 1.0 / contract.physics_hz
    data = mujoco.MjData(model)
    sess = ort.InferenceSession(str(package_dir / args.policy), providers=["CPUExecutionProvider"])

    # 桌面端同指令跑同样帧数，收集每步 obs
    cmd = [float(x) for x in args.cmd.split(",")]
    obs_builder = ObsBuilder(contract, model, data)
    desktop_obs: list[list[float]] = []
    steps = len(frames) * contract.decimation
    from policy_acceptance import actuate, spawn_default  # noqa: E402
    spawn_default(contract, model, data, obs_builder)
    cmd_arr = np.asarray(cmd, dtype=np.float32)
    # 浏览器 frameLog 首帧的相位秒（反推自 gait_phase sin/cos），桌面先空转到同一相位
    # 再开始采集——两侧时钟起点对齐（浏览器 reset 与采集之间总有墙钟间隔）。
    def _phase_seconds(obs_row):
        s, c = float(obs_row[9]), float(obs_row[10])
        if s == 0.0 and c == 0.0:
            return 0.0
        phase = math.atan2(s, c) / (2 * math.pi)
        return phase * contract.gait_period if phase >= 0 else (phase + 1) * contract.gait_period
    import math
    target_phase_s = _phase_seconds(frames[0]["obs"])
    skip_steps = int(round(target_phase_s / contract.step_dt))
    for step in range(steps + skip_steps):
        if step % contract.decimation == 0:
            o = obs_builder.build(cmd_arr)
            if step >= skip_steps:
                desktop_obs.append(o[0].tolist())
            raw = sess.run(None, {sess.get_inputs()[0].name: o})[0][0]
            obs_builder.last_action = np.asarray(raw, dtype=np.float32)[: contract.action_dim]
        actuate(contract, model, data, obs_builder, obs_builder.last_action)
        mujoco.mj_step(model, data)

    desktop = np.asarray(desktop_obs[: len(frames)], dtype=np.float32)
    # 口径对齐：浏览器 frames[0] 是 reset 后的初始 obs（速度/动作恒 0），
    # 从 frames[1] 起才是与桌面第一控制步可对齐的序列。
    browser_aligned = browser_obs[1:len(desktop) + 1]
    n = min(len(desktop), len(browser_aligned))
    diff = np.abs(desktop[:n] - browser_aligned[:n])

    print(f"\n逐帧最大差异（前 10 帧控制步）:")
    for i in range(min(10, n)):
        worst = int(np.argmax(diff[i]))
        print(f"  frame {i}: max={diff[i].max():.4g} @ {segment_of(worst)}")

    first_bad = None
    for i in range(n):
        bad = np.where(diff[i] > 0.05)[0]
        if len(bad):
            first_bad = (i, bad)
            break
    if first_bad is None:
        print("\n全部帧全部维度差异 ≤0.05 —— 观测链路一致，发散源在更后段（数值累积/长时域）")
        return
    frame_idx, dims = first_bad
    print(f"\n第一个发散帧: {frame_idx}（控制步），发散维度 {len(dims)} 个")
    top = sorted(dims, key=lambda d: -diff[frame_idx][d])[:8]
    for d in top:
        seg = segment_of(int(d))
        print(f"  {seg}: browser={browser_obs[frame_idx][d]:+.4f} desktop={desktop[frame_idx][d]:+.4f} diff={diff[frame_idx][d]:.4g}")
    print("\n头部样例（frame 0）:")
    print("  browser:", np.round(browser_obs[0][:12], 4).tolist())
    print("  desktop:", np.round(desktop[0][:12], 4).tolist())


if __name__ == "__main__":
    main()
