#!/usr/bin/env python3
"""obs_crosscheck.py — **同状态观测对拍**：验收器（Python）↔ 浏览器观测构建器（Node）。

**为什么需要它**（2026-09-22 一场血案的直接产物）：浏览器与验收器是**两套独立实现**，
"差一步"的缺陷**不抛异常、不改任何读数**，只在特定姿态暴露——用户报的"机器人转到 180°
左右必然抽风"就是浏览器侧 `captureImuSample` 对自由关节 `qvel[3:6]`（**本就是机体系角速度**）
多做了一次 `Rᵀ`（双重旋转）：yaw≈0 处 R≈I 完全看不出来，yaw→180° 时水平两轴翻号 ⇒
姿态反馈变正反馈 ⇒ 乱动失衡。当时把它抓住的唯一手段就是本工具的做法：
**同一份 qpos/qvel 喂给两条实现，逐段比观测**。

口径（刻意的选择，别改）：
  · 状态在**真 MuJoCo** 里造：默认 **yaw=180° + 小滚转/俯仰（4°/3°）**，带非零体速度与关节
    偏移。**为什么要给滚转/俯仰**：差一步的缺陷在 yaw≈0 且姿态直立时几乎不可见（实测同一
    缺陷：yaw=0 直立 Δ≈1e-8 也测不出来；带上 4°/3° 后 yaw=0 就有 Δ≈1.8e-2、到 yaw=180°
    放大到 Δ≈0.98）——所以状态要"站得歪 + 转得大"，任何 yaw 下都能现形；
  · 浏览器侧**不启浏览器**：Node 直接加载 `web/sim2sim/obs/observation_builders.js`，
    IMU 走 `web/sim2sim/utils.js::imuSampleFromQpos`（运行时真路径）——不另写一份仿真品；
  · 判据在 Python 侧算，两边各自只出自己的真值，工具不引入第三份实现。

**门禁资格（已实测）**：把 2026-09-22 那处缺陷临时注入回去 → 本工具 `exit=1` 并指名
`IMU.angular max|Δ|=9.85e-01`；还原后 `exit=0`。即它**真的能抓**，不是"跑完总是绿"。

退出码：`0` 一致 · `1` 不一致（超容差）· `2` 环境缺失或本 kind 不适用（fail-closed）

用法：
    python3 tools/obs_crosscheck.py                      # 默认 go2-rlsar-robotlab @ yaw=180°
    python3 tools/obs_crosscheck.py --yaw-deg 0          # 对照：yaw=0（此处两者本应恒等）
    python3 tools/obs_crosscheck.py --policy go2-loco-45
    python3 tools/obs_crosscheck.py --keep               # 保留中间 JSON 供排查
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: 通例段（**定位提示**，不是判据）：绝大多数 kind 的前 9 维是 ang_vel / gravity / cmd。
#: 判据只有一条 —— 逐维 max|Δ| ≤ tol。段名写在这里只是让人一眼看出"错在哪个语义段"。
COMMON_SEGMENTS = (("ang_vel", 0, 3), ("gravity", 3, 6), ("cmd", 6, 9))


def load_engine():
    """加载验收器引擎（与 tools/sim2sim_headless.py 同一实现，见那里的说明）。"""
    spec = importlib.util.spec_from_file_location(
        "sim2sim_headless", ROOT / "tools" / "sim2sim_headless.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        return module.load_engine()
    except ImportError as exc:  # mujoco / onnxruntime 缺失
        print(f"[crosscheck] 环境缺失：{exc}", file=sys.stderr)
        raise SystemExit(2)


def build_state(engine, package_dir: Path, sim_cfg: dict, entry: dict, yaw_deg: float) -> tuple[dict, dict]:
    """造一个"大角度 + 非零速度 + 关节偏移"的状态，返回 (给 Node 的状态包, 本侧参考观测)。"""
    import mujoco
    import numpy as np

    contract = engine.PackageContract(package_dir, entry)
    contract.motion_loader = None
    if contract.observation_kind in getattr(engine, "_DEFERRED_KINDS", set()):
        print(f"[crosscheck] kind={contract.observation_kind} 需 MotionLoader/复合命令，本工具不适用（不是缺陷）",
              file=sys.stderr)
        raise SystemExit(2)
    model = engine.load_package_model(package_dir, sim_cfg, None, scene_rel=contract.contract.get("scene_path"))
    model.opt.timestep = 1.0 / contract.physics_hz
    data = mujoco.MjData(model)
    obs = engine.ObsBuilder(contract, model, data)
    engine.spawn_default(contract, model, data, obs)

    # ── 状态：按 yaw 造姿态（含小滚转/俯仰，让 R 既不是单位阵也不是纯偏航）──────────
    quat = np.zeros(4, dtype=np.float64)
    mujoco.mju_euler2Quat(quat, np.radians(np.array([4.0, -3.0, float(yaw_deg)])), "xyz")
    data.qpos[3:7] = quat
    rot = np.zeros(9, dtype=np.float64)
    mujoco.mju_quat2Mat(rot, quat)
    rot = rot.reshape(3, 3)
    v_body = np.array([0.6, 0.2, 0.0])          # 机体系线速度 → 世界系写进 qvel[0:3]
    omega_body = np.array([0.3, -0.5, 0.2])     # 机体系角速度 → 直接进 qvel[3:6]
    data.qvel[0:3] = rot @ v_body
    data.qvel[3:6] = omega_body

    order = contract.action_joint_order
    joints = []
    for i, name in enumerate(order):
        qa, da = obs.jadr[name]
        data.qpos[qa] = contract.default_for(name) + 0.05 * ((i % 3) - 1)
        data.qvel[da] = 0.1 * i - 0.4
        joints.append({"name": name, "q": float(data.qpos[qa]), "dq": float(data.qvel[da]),
                       "default": float(contract.default_for(name))})
    mujoco.mj_forward(model, data)

    obs.last_action = np.zeros(contract.action_dim, dtype=np.float32)
    cmd = np.array([0.6, 0.0, 0.0], dtype=np.float32)
    own = np.asarray(obs.build(cmd), dtype=np.float64).reshape(-1)
    # **历史口径（2026-09-22 补）**：验收器的 `build()` 直接给出**叠好历史**的整向量
    # （如 270 = 6×45），而浏览器侧被驱动的是 **builder 单帧**（叠帧在
    # `app.js::packObsHistoryByTerm`，Node 侧没驱动那一层）⇒ 直接比会得到"270 vs 45"的**假红**。
    # 故有历史时只比**当前帧**那一段，基准按契约 `history_layout` 取：
    #   · `frame_major_oldest_first`（旧→新）⇒ 当前帧在**末尾**；
    #   · 其余（`frame_major_v1` 等，新→旧）⇒ 当前帧在**开头**。
    # 叠帧布局本身由验收器自己的 `history_len × obs_dim` 断言守着（这里不重复判它）。
    history_len = int(contract.history_len or 1)
    frame_width = int(contract.obs_dim or own.shape[0])
    layout = str(getattr(contract, "history_layout", "") or "")
    compare_basis = "整向量"
    if history_len > 1 and own.shape[0] == frame_width * history_len:
        own = own[-frame_width:] if layout == "frame_major_oldest_first" else own[:frame_width]
        compare_basis = f"当前帧（{layout or 'frame_major_v1'}，另 {history_len - 1} 帧历史不在此层）"

    state = {
        "contract": {
            "observation_kind": contract.observation_kind,
            "obs_dim": int(contract.obs_dim or own.shape[0]),
            "action_dim": int(contract.action_dim),
            "history_len": int(contract.history_len or 1),
            "command_dims": int(contract.command_dims or 3),
            "decimation": int(contract.decimation or 1),
            "physics_hz": float(contract.physics_hz),
            "gait_period_s": float(getattr(contract, "gait_period", 0.0) or 0.0),
            "default_joint_angles": {},
        },
        "scales": {
            "ang_vel": float(contract.ang_vel_scale),
            "dof_pos": float(contract.dof_pos_scale),
            "dof_vel": float(contract.dof_vel_scale),
            "command": [float(v) for v in contract.cmd_scale],
        },
        "cmd": [float(v) for v in cmd],
        "action": [float(v) for v in obs.last_action],
        # 浏览器侧 `input.imuAxisSigns` 默认 [1,1,1]（契约里没有该字段），两侧同号
        "imu_axis_signs": {"angular": [1, 1, 1], "gravity": [1, 1, 1]},
        "state": {
            "quat_wxyz": [float(v) for v in data.qpos[3:7]],
            "qvel_head": [float(v) for v in data.qvel[0:6]],
            "joints": joints,
        },
    }
    reference = {
        "obs": [float(v) for v in own],
        "compare_basis": compare_basis,
        "imu": {
            "angular": [float(v) for v in data.qvel[3:6]],
            "linear": [float(v) for v in (rot.T @ data.qvel[0:3])],
            "gravity": [float(v) for v in engine.projected_gravity(data.qpos[3:7])],
            "rpy": [float(v) for v in engine.quat_to_euler_xyz(data.qpos[3:7])],
        },
    }
    return state, reference


def run_browser_side(state: dict, keep_path: Path | None) -> dict:
    node = shutil.which("node")
    if not node:
        print("[crosscheck] 环境缺失：找不到 node（浏览器侧观测构建器需要 Node 运行）", file=sys.stderr)
        raise SystemExit(2)
    if keep_path is None:
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        handle.write(json.dumps(state))
        handle.close()
        state_path = Path(handle.name)
    else:
        state_path = keep_path
        state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
    completed = subprocess.run(
        [node, str(ROOT / "tools" / "obs_crosscheck.mjs"), str(state_path)],
        capture_output=True, text=True, encoding="utf-8", timeout=180,
    )
    if completed.returncode != 0 and not completed.stdout.strip():
        print(f"[crosscheck] 浏览器侧执行失败（exit {completed.returncode}）：\n{completed.stderr[-2000:]}",
              file=sys.stderr)
        raise SystemExit(2)
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    if not payload.get("ok"):
        print(f"[crosscheck] 浏览器侧报错：{payload.get('error')}", file=sys.stderr)
        raise SystemExit(2)
    return payload


def compare(tag: str, mine: list[float], theirs: list[float], tol: float) -> tuple[float, str]:
    """逐维比对，返回 (max|Δ|, 最差维描述)。长度不等直接判失败。"""
    if len(mine) != len(theirs):
        return math.inf, f"长度不一致：验收器 {len(mine)} vs 浏览器 {len(theirs)}"
    worst, at = 0.0, -1
    for i, (a, b) in enumerate(zip(mine, theirs)):
        delta = abs(float(a) - float(b))
        if delta > worst:
            worst, at = delta, i
    detail = f"[{at}] 验收器 {mine[at]:+.6f} vs 浏览器 {theirs[at]:+.6f}" if at >= 0 else "—"
    return worst, f"{tag} 最差维 {detail}"


def main() -> int:
    parser = argparse.ArgumentParser(description="同状态观测对拍（验收器 ↔ 浏览器观测构建器）")
    parser.add_argument("--robot", default="unitree_go2")
    parser.add_argument("--policy", default="go2-rlsar-robotlab")
    parser.add_argument("--yaw-deg", type=float, default=180.0, help="机身 yaw（默认 180°：两份实现差异最大的地方）")
    parser.add_argument("--tol", type=float, default=1e-5, help="逐维容差（两侧都是 Float32，~1e-7 量级是表示误差）")
    parser.add_argument("--keep", type=Path, default=None, help="保留中间 JSON 到此路径（排查用）")
    args = parser.parse_args()

    engine = load_engine()
    package_dir = ROOT / "assets" / "robots" / args.robot
    if not (package_dir / "simulation" / "config.json").is_file():
        print(f"[crosscheck] 找不到机型包：{package_dir}", file=sys.stderr)
        return 2
    sim_cfg = json.loads((package_dir / "simulation" / "config.json").read_text(encoding="utf-8-sig"))
    entry = next((e for e in (sim_cfg.get("policies") or []) if e.get("id") == args.policy), None)
    if entry is None:
        print(f"[crosscheck] {args.robot} 里没有策略 id={args.policy}", file=sys.stderr)
        return 2

    state, reference = build_state(engine, package_dir, sim_cfg, entry, args.yaw_deg)
    browser = run_browser_side(state, args.keep)

    kind = state["contract"]["observation_kind"]
    print("=" * 74)
    print(f"同状态观测对拍：{args.robot} / {args.policy}")
    print(f"  kind={kind}  obs={state['contract']['obs_dim']}  history={state['contract']['history_len']}"
          f"  yaw={args.yaw_deg:g}°  容差={args.tol:g}")
    print(f"  对比基准：{reference.get('compare_basis') or '整向量'}")
    print("-" * 74)

    failures: list[str] = []
    print("① IMU 采样（喂进观测的那一组；浏览器 = utils.js::imuSampleFromQpos）")
    for name in ("angular", "linear", "gravity", "rpy"):
        worst, detail = compare(name, reference["imu"][name], browser["imu"][name], args.tol)
        flag = "OK  " if worst <= args.tol else "FAIL"
        print(f"  [{flag}] {name:<8} max|Δ|={worst:.3e}   {detail}")
        if worst > args.tol:
            failures.append(f"IMU.{name}: max|Δ|={worst:.3e}（{detail}）")

    print("② 整条观测（逐维；段名按通例标注，仅作定位提示）")
    obs_worst, obs_detail = compare("obs", reference["obs"], browser["obs"], args.tol)
    for name, lo, hi in COMMON_SEGMENTS:
        if hi > len(reference["obs"]):
            continue
        seg_worst, _ = compare(name, reference["obs"][lo:hi], browser["obs"][lo:hi], args.tol)
        print(f"  [{'OK  ' if seg_worst <= args.tol else 'FAIL'}] {name:<8} max|Δ|={seg_worst:.3e}")
    print(f"  [{'OK  ' if obs_worst <= args.tol else 'FAIL'}] 全向量   max|Δ|={obs_worst:.3e}")
    if obs_worst > args.tol:
        failures.append(f"obs: max|Δ|={obs_worst:.3e}（{obs_detail}）")

    print("-" * 74)
    if failures:
        print(f"✗ 两份实现**不一致** {len(failures)} 处：")
        for item in failures:
            print(f"  - {item}")
        print("  ⇒ 浏览器与验收器差一步（历史上正是这类缺陷造成\"转 180° 抽风\"）")
        return 1
    print("✓ 一致：同一状态、同一条观测，两份实现逐维相同")
    return 0


if __name__ == "__main__":
    sys.exit(main())
