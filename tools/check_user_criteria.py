#!/usr/bin/env python3
"""check_user_criteria.py — 用户验收判据自动检测（2026-09-30 固化）。

判据（用户口径）：
  * 主轴跟踪偏差 <= 40%；
  * 单命令时其他轴 <= 主命令的 20%（串扰）；
  * 持续 5s 及以上的稳定：输入输出不爆（NaN/Inf）、机身不倒地（高度/倾角）；
  * 命令自动钳到该策略契约 command_ranges（部署分布内）。

用法（需 adapters/mjlab/.venv）：
  python tools/check_user_criteria.py --robot unitree_go2w --policy go2w-velocity-robotlab
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CRIT = {"err_max": 0.40, "cross_max": 0.20, "hold_s": 5.0, "total_s": 8.0}


def run_case(sess, contract, model, cmd, total_s=CRIT["total_s"], judge_last=CRIT["hold_s"],
             err_max: float = CRIT["err_max"], cross_max: float = CRIT["cross_max"]):
    """阈值可由档案声明覆盖（``criteria.tracking.err_max/cross_max``）——判据口径
    「配方各自声明」而非写死在本工具（缺省 = CRIT，行业 40%/20% 口径不变）。"""
    import numpy as np
    import mujoco
    from adapters.mjlab import policy_acceptance as pa

    data = mujoco.MjData(model)
    ob = pa.ObsBuilder(contract, model, data)
    pa.spawn_default(contract, model, data, ob)
    ob.phase_s = 0.0
    ob.last_action[:] = 0
    ob.history = []
    cmd = np.asarray(cmd, dtype=np.float32)
    dt = 1.0 / contract.physics_hz * contract.decimation
    steps = int(total_s / dt)
    judge_n = int(judge_last / dt)
    vels = []
    fell = False
    obs_max = act_max = 0.0
    # VAE 宿主多输入（DreamWaQ 系）：第二输入 = k×obs_dim 的**历史帧展平**
    #（不含当前帧；训练里 history 由零初始化逐步填充——零初始化语义对齐）。
    inputs = sess.get_inputs()
    hist_frames = 0
    history: list = []
    if len(inputs) > 1:
        shape = inputs[1].shape
        if len(shape) == 2 and isinstance(shape[1], int) and shape[1] > 0:
            # 注意 build 可能返回 (1, obs_dim)——obs_dim 必须取**展平后**的宽度，
            # 否则 228 // 1 = 228 被当成帧数（2026-10-04 实测 284 之谜）。
            first = np.asarray(ob.build(cmd), dtype=np.float32).reshape(-1)
            obs_dim = int(first.shape[0])
            if obs_dim > 0 and shape[1] % obs_dim == 0 and shape[1] // obs_dim > 1:
                hist_frames = shape[1] // obs_dim
                history = [np.zeros(obs_dim, dtype=np.float32) for _ in range(hist_frames)]
    for _ in range(steps):
        obs = np.asarray(ob.build(cmd), dtype=np.float32).reshape(-1)
        if not np.isfinite(obs).all():
            return {"pass": False, "reason": "输入爆(NaN)"}
        obs_max = max(obs_max, float(np.abs(obs).max()))
        if hist_frames:
            feed = {inputs[0].name: obs.reshape(1, -1)}
        else:
            feed = {inputs[0].name: obs}
        if hist_frames:
            history.append(np.asarray(obs, dtype=np.float32))
            history = history[-hist_frames:]
            cond = np.concatenate(
                [np.zeros(obs_dim, dtype=np.float32)] * (hist_frames - len(history))
                + history
            )
            feed[inputs[1].name] = cond.reshape(1, -1)
        raw = sess.run(None, feed)[0][0]
        a = np.asarray(raw, dtype=np.float32)[: contract.action_dim]
        if not np.isfinite(a).all():
            return {"pass": False, "reason": "输出爆(NaN)"}
        act_max = max(act_max, float(np.abs(a).max()))
        ob.last_action = a
        pa.actuate(contract, model, data, ob, ob.last_action)
        for _ in range(contract.decimation):
            mujoco.mj_step(model, data)
        quat = data.qpos[3:7]
        tilt = abs(2 * (quat[0] * quat[2] + quat[1] * quat[3]))
        if float(data.qpos[2]) < 0.12 or tilt > 0.95:
            fell = True
            break
        vels.append([float(data.qvel[0]), float(data.qvel[1]), float(data.qvel[5])])
    if fell:
        return {"pass": False, "reason": "倒地", "obs_max": round(obs_max, 1), "act_max": round(act_max, 1)}
    if len(vels) < judge_n:
        return {"pass": False, "reason": "不足5s", "obs_max": round(obs_max, 1), "act_max": round(act_max, 1)}
    mean = np.asarray(vels[-judge_n:]).mean(axis=0)
    res = {"pass": True, "v_mean": [round(float(x), 3) for x in mean],
           "obs_max": round(obs_max, 1), "act_max": round(act_max, 1)}
    main = int(np.argmax(np.abs(cmd))) if np.abs(cmd).max() > 0 else -1
    if main >= 0:
        cmag = abs(float(cmd[main]))
        err = abs(abs(mean[main]) - cmag) / cmag
        res["err%"] = round(err * 100, 1)
        # 判据比较一律用**分数**（err ∈ [0,∞)，0.40 = 40%）——这里曾拿分数与
        # `err_max * 100`（=40）比，主轴阈值实际成了 4000%，v_mean=0 也 PASS（fail-open，
        # 2026-10-01 在 40k 产物上抓到：四命令全零速度却全 PASS）。
        if err > err_max:
            res["pass"] = False
            res["reason"] = "主轴误差%.0f%%>%.0f%%" % (err * 100, err_max * 100)
        for ax in range(3):
            if ax == main:
                continue
            cross = abs(mean[ax]) / cmag
            if cross > cross_max:
                res["pass"] = False
                res["reason"] = "串扰轴%d=%.0f%%>%.0f%%" % (ax, cross * 100, cross_max * 100)
    if obs_max > 100 or act_max > 100:
        res["pass"] = False
        res["reason"] = "输入输出爆"
    return res


def clamp_to_ranges(cmd, contract):
    ranges = getattr(contract, "command_ranges", None) or {}
    axes = ("lin_vel_x", "lin_vel_y", "ang_vel_z")
    out = []
    for i, axis in enumerate(axes):
        span = ranges.get(axis) if isinstance(ranges, dict) else None
        if isinstance(span, (list, tuple)) and len(span) >= 2:
            lo, hi = float(span[0]), float(span[1])
            if lo == 0.0 and hi == 0.0:
                out.append(0.0)
                continue
            out.append(min(max(cmd[i], lo), hi))
        else:
            out.append(cmd[i])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="用户验收判据检测（40%%/20%%/5s/不爆/不倒）")
    ap.add_argument("--robot", required=True)
    ap.add_argument("--policy", required=True, help="包内策略 id")
    ap.add_argument("--cases", default="0.5,0,0;0,0.4,0;0,0,0.6;0.4,0.2,0.4")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    import mujoco
    import onnxruntime as ort
    from adapters.mjlab import policy_acceptance as pa
    from backend.policy_artifacts import policy_blob_path, load_index

    pkg = ROOT / "assets" / "robots" / args.robot
    if not pkg.is_dir():
        pkg = ROOT / "workspace" / "packages" / args.robot
    sim_cfg = json.loads((pkg / "simulation/config.json").read_text(encoding="utf-8-sig"))
    entry = next(p for p in sim_cfg["policies"] if p.get("id") == args.policy)
    contract = pa.PackageContract(pkg, entry)
    model = pa.load_package_model(pkg, sim_cfg)
    model.opt.timestep = 1.0 / contract.physics_hz
    blob = policy_blob_path(entry, robot_dir=pkg, index=load_index())
    sess = ort.InferenceSession(str(blob), providers=["CPUExecutionProvider"])

    cases = [tuple(float(x) for x in c.split(",")) for c in args.cases.split(";")]
    report = {"policy": args.policy, "robot": args.robot, "cases": []}
    n_pass = 0
    for cmd in cases:
        cmd = clamp_to_ranges(list(cmd), contract)
        r = run_case(sess, contract, model, cmd)
        r["command"] = list(cmd)
        report["cases"].append(r)
        n_pass += 1 if r["pass"] else 0
        tag = "PASS" if r["pass"] else "FAIL(%s)" % r.get("reason")
        extra = {k: v for k, v in r.items() if k not in ("pass", "reason", "command")}
        print("  cmd%s [%s] %s" % (r["command"], tag, json.dumps(extra, ensure_ascii=False)))
    report["verdict"] = "pass" if n_pass == len(cases) else "fail(%d/%d)" % (n_pass, len(cases))
    print("[%s] %s" % (args.policy, report["verdict"]))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if n_pass == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
