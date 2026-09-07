"""ONNX 策略验收评估器（contract-driven 版）。

参考 unitree_rl_mjlab 的 scripts/evaluate_go2w_*.py 三件套思想，面向
Legged Studio 机器人包：给定 package（model/robot.xml + simulation/config.json）
和已导出的 policy.onnx，在无头 MuJoCo 里跑定种子、固定指令的滚出，
输出逐指令模式的 JSON 指标（存活、摔倒、速度跟踪误差、姿态包络）。

观测构建与 web/sim2sim/app.js 的构建器逐项对齐（重力同号、轮位 wrap、相位钟）；
新增观测布局时两处需同步。仅依赖 mujoco + onnxruntime + numpy，跑在适配器 venv。

用法：
  python policy_acceptance.py --package <pkg_dir> --policy <policy.onnx> \
      [--modes 0,0,0 0.3,0,0] [--seconds 6] [--seed 0] [--output metrics.json]
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


# ---------- 四元数/向量工具（约定与 app.js 一致：quat = [w, x, y, z]） ----------

def quat_rotate_inverse(q: np.ndarray, v: np.ndarray) -> np.ndarray:
    """R^T · v"""
    w, x, y, z = q
    u = np.array([x, y, z])
    return v - 2.0 * w * np.cross(u, v) + 2.0 * np.cross(u, np.cross(u, v))


def projected_gravity(q: np.ndarray) -> np.ndarray:
    """R^T · [0, 0, -1]：直立时 (0, 0, -1)，与 app.getGravityOrientation 同约定。"""
    return quat_rotate_inverse(q, np.array([0.0, 0.0, -1.0]))


def wrap_pi(a: float) -> float:
    return math.atan2(math.sin(a), math.cos(a))


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ---------- 包契约读取 ----------

class PackageContract:
    def __init__(self, package_dir: Path, policy_entry: dict[str, Any]):
        self.root = package_dir
        self.sim = json.loads((package_dir / "simulation" / "config.json").read_text(encoding="utf-8"))
        self.entry = policy_entry
        self.contract = dict(policy_entry.get("contract") or {})
        # 策略未声明动作序时回退到机器人级 contract.json 的 action.joint_order
        robot_contract_path = package_dir / "contract.json"
        robot_order: list[str] = []
        if robot_contract_path.is_file():
            rc = json.loads(robot_contract_path.read_text(encoding="utf-8"))
            action = rc.get("action") or {}
            robot_order = [str(n) for n in (action.get("joint_order") or rc.get("joints", {}).get("actuated_joints") or [])]
        self.action_joint_order = [str(n) for n in (self.contract.get("action_joint_order") or [])] or robot_order
        self.physics_hz = float(self.sim.get("physics_hz") or 200)
        self.decimation = int(self.sim.get("decimation") or 4)
        self.step_dt = 1.0 / self.physics_hz * self.decimation
        self.actuator_interface = str(self.sim.get("actuator_interface") or "torque").lower()
        self.initial_height = float(self.sim.get("initial_base_height") or 0.4)
        self.torque_limits = {k.lower(): float(v) for k, v in (self.sim.get("torque_limits") or {}).items()}

        scales = self.contract.get("scales") or {}
        self.ang_vel_scale = float(scales.get("ang_vel", 1.0))
        self.dof_pos_scale = float(scales.get("dof_pos", 1.0))
        self.dof_vel_scale = float(scales.get("dof_vel", 1.0))
        self.cmd_scale = [float(x) for x in (scales.get("command") or [1.0, 1.0, 1.0])]

        self.observation_kind = str(self.contract.get("observation_kind") or "")
        self.obs_dim = int(self.contract.get("obs_dim") or 0)
        self.action_dim = int(self.contract.get("action_dim") or 0)
        self.clip_actions = self.contract.get("clip_actions") or None

        self.default_joint_angles = {k.lower(): float(v) for k, v in (self.contract.get("default_joint_angles") or {}).items()}
        scale_by_joint = {k.lower(): float(v) for k, v in (self.contract.get("action_scale_by_joint") or {}).items()}
        default_scale = float(self.contract.get("action_scale") or 0.5)
        self.action_scales = [
            scale_by_joint.get(name.lower(), default_scale) for name in self.action_joint_order
        ]
        self.gait_period = float(self.contract.get("gait_period_s") or 0.6)

        control = self.sim.get("control") or {}
        self.stiffness = control.get("stiffness") or self.sim.get("stiffness") or {}
        self.damping = control.get("damping") or self.sim.get("damping") or {}

        ranges = (self.contract.get("command_ranges") or {})
        self.cmd_ranges = (
            ranges.get("lin_vel_x") or [-0.5, 1.0],
            ranges.get("lin_vel_y") or [-0.5, 0.5],
            ranges.get("ang_vel_z") or [-1.0, 1.0],
        )

    def default_for(self, joint: str) -> float:
        return self.default_joint_angles.get(joint.lower(), 0.0)

    def gain_for(self, table: dict, joint: str) -> float:
        v = table.get(joint.lower())
        if v is not None:
            return float(v)
        lowered = joint.lower()
        for key, val in table.items():
            if key.lower() in lowered:
                return float(val)
        return 0.0


# ---------- 观测构建（与 app.js 构建器逐项对齐） ----------

class ObsBuilder:
    def __init__(self, contract: PackageContract, model, data):
        import mujoco

        self.mj = mujoco
        self.model = model
        self.data = data
        self.contract = contract
        self.phase_s = 0.0
        self.last_action = np.zeros(contract.action_dim, dtype=np.float32)

        self.base_qadr = 0
        self.base_dadr = 0
        self.jadr: dict[str, tuple[int, int]] = {}
        for name in contract.action_joint_order:
            jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
            if jid < 0:
                raise ValueError(f"模型缺少关节 {name}")
            self.jadr[name] = (int(model.jnt_qposadr[jid]), int(model.jnt_dofadr[jid]))
        # 观测里出现但不在动作序里的关节（如 legs-only 的轮子）也按名解析
        extra = ["FR_wheel_joint", "FL_wheel_joint", "RL_wheel_joint", "RR_wheel_joint"]
        for name in extra:
            if name not in self.jadr:
                jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
                if jid >= 0:
                    self.jadr[name] = (int(model.jnt_qposadr[jid]), int(model.jnt_dofadr[jid]))

    def base_state(self):
        q = self.data.qpos[3:7].copy()
        ang_b = self.data.qvel[3:6].copy()
        # 线速度取 root body 的世界系速度再投到机体系（对齐 app 的 qvel 回退路径）
        lin_w = self.data.qvel[0:3].copy()
        lin_b = quat_rotate_inverse(q, lin_w)
        return q, ang_b, lin_b

    def contact_count(self) -> int:
        return int(self.data.ncon)


def spawn_default(contract: PackageContract, model, data, obs: "ObsBuilder") -> None:
    """重置到契约默认姿态 + 初始高度（与浏览器 resetSimulation 一致）。"""
    import mujoco

    mujoco.mj_resetData(model, data)
    data.qpos[0:3] = 0.0
    data.qpos[2] = contract.initial_height
    data.qpos[3:7] = (1.0, 0.0, 0.0, 0.0)
    for name, (qa, _da) in obs.jadr.items():
        if name in contract.action_joint_order or name.endswith("wheel_joint"):
            data.qpos[qa] = contract.default_for(name)
    mujoco.mj_forward(model, data)

    def build(self, cmd: np.ndarray) -> np.ndarray:
        kind = self.contract.observation_kind
        q, ang_b, lin_b = self.base_state()
        c = self.contract
        obs: list[float] = []
        if kind == "go2w_mjlab_legs_53":
            obs += list(ang_b * 1.0)
            obs += list(projected_gravity(q))
            obs += list(cmd * np.asarray(c.cmd_scale))
            legs = c.action_joint_order[:12]
            obs += [self.data.qpos[self.jadr[n][0]] - c.default_for(n) for n in legs]
            obs += [self.data.qvel[self.jadr[n][1]] * c.dof_vel_scale for n in legs]
            for n in ("FR_wheel_joint", "FL_wheel_joint", "RR_wheel_joint", "RL_wheel_joint"):
                a = self.jadr.get(n)
                obs.append(wrap_pi(self.data.qpos[a[0]]) if a else 0.0)
            for n in ("FR_wheel_joint", "FL_wheel_joint", "RR_wheel_joint", "RL_wheel_joint"):
                a = self.jadr.get(n)
                obs.append(self.data.qvel[a[1]] * c.dof_vel_scale if a else 0.0)
            obs += list(self.last_action)
        elif kind == "g1_mjlab_velocity_98":
            self.phase_s += c.step_dt
            phase = (self.phase_s % c.gait_period) / c.gait_period
            moving = float(np.linalg.norm(cmd)) >= 0.1
            obs += list(ang_b * c.ang_vel_scale)
            obs += list(projected_gravity(q))
            obs += list(cmd * np.asarray(c.cmd_scale))
            obs += [math.sin(phase * 2 * math.pi) if moving else 0.0]
            obs += [math.cos(phase * 2 * math.pi) if moving else 0.0]
            obs += [(self.data.qpos[self.jadr[n][0]] - c.default_for(n)) * c.dof_pos_scale for n in c.action_joint_order]
            obs += [self.data.qvel[self.jadr[n][1]] * c.dof_vel_scale for n in c.action_joint_order]
            obs += list(self.last_action)
        elif kind == "g1_mjswan_locomotion":
            obs += list(lin_b)
            obs += list(ang_b * c.ang_vel_scale)
            obs += list(projected_gravity(q))
            obs += [(self.data.qpos[self.jadr[n][0]] - c.default_for(n)) * c.dof_pos_scale for n in c.action_joint_order]
            obs += [self.data.qvel[self.jadr[n][1]] * c.dof_vel_scale for n in c.action_joint_order]
            obs += list(self.last_action)
            obs += list(cmd * np.asarray(c.cmd_scale))
        else:
            raise ValueError(f"验收器暂不支持观测布局: {kind!r}")
        arr = np.asarray(obs, dtype=np.float32)
        if c.obs_dim and arr.shape[0] != c.obs_dim:
            raise ValueError(f"观测维度不符: 构建 {arr.shape[0]} vs 契约 {c.obs_dim}")
        return arr[None, :]


# ---------- 单模式滚出 ----------

def run_mode(sess, contract: PackageContract, model, data, obs: ObsBuilder,
             cmd: list[float], seconds: float, seed: int) -> dict[str, Any]:
    import mujoco

    rng = np.random.default_rng(seed)
    spawn_default(contract, model, data, obs)

    obs_builder = obs
    obs_builder.phase_s = 0.0
    obs_builder.last_action[:] = 0
    cmd_arr = np.asarray(cmd, dtype=np.float32)

    total = int(seconds / contract.step_dt)
    fell_at = None
    height_min = float("inf")
    roll_max = pitch_max = 0.0
    vel_errs: list[float] = []
    tracked = 0

    for step in range(total):
        if step % contract.decimation == 0:
            o = obs_builder.build(cmd_arr)
            raw = sess.run(None, {sess.get_inputs()[0].name: o})[0][0]
            raw = np.asarray(raw, dtype=np.float32)[: contract.action_dim]
            if contract.clip_actions is not None:
                clip = np.asarray(contract.clip_actions, dtype=np.float32)
                raw = np.clip(raw, -clip, clip)
            obs_builder.last_action = raw.copy()
        # PD/位置目标按物理步频重算（与浏览器端一致：ctrl 每步刷新，动作按 decimation 保持）
        actuate(contract, model, data, obs, raw)
        mujoco.mj_step(model, data)

        q = data.qpos[3:7]
        g = projected_gravity(q)
        roll = math.degrees(math.atan2(g[1], -g[2])) if -g[2] > 1e-6 else math.copysign(90.0, g[1])
        pitch = math.degrees(math.asin(clamp(g[0], -1.0, 1.0)))
        roll_max = max(roll_max, abs(roll))
        pitch_max = max(pitch_max, abs(pitch))
        height_min = min(height_min, float(data.qpos[2]))
        tilted = abs(roll) > 60.0 or abs(pitch) > 60.0
        if fell_at is None and (data.qpos[2] < 0.45 * contract.initial_height or tilted):
            fell_at = step * contract.step_dt
            break
        # 速度跟踪：只统计后半段（前段含起摆/收敛）
        if step > total * 0.7:
            q4, ang_b, lin_b = obs_builder.base_state()
            w_err = ang_b[2] - cmd_arr[2]
            vel_errs.append(float(np.linalg.norm(lin_b[:2] - cmd_arr[:2]) + 0.3 * abs(w_err)))
            tracked += 1

    survived_steps = (fell_at / contract.step_dt) if fell_at is not None else total
    metrics = {
        "command": [float(x) for x in cmd],
        "fell": fell_at is not None,
        "fell_at_s": round(fell_at, 3) if fell_at is not None else None,
        "survival_ratio": round(survived_steps / total, 3),
        "vel_track_err": round(float(np.mean(vel_errs)), 3) if vel_errs else None,
        "height_min": round(height_min, 3),
        "roll_max_deg": round(roll_max, 1),
        "pitch_max_deg": round(pitch_max, 1),
    }
    metrics["pass"] = (not metrics["fell"]) and metrics["survival_ratio"] >= 0.999
    return metrics


def actuate(contract: PackageContract, model, data, obs: ObsBuilder, raw: np.ndarray) -> None:
    import mujoco

    c = contract
    if c.actuator_interface == "position_target":
        for i, name in enumerate(c.action_joint_order):
            aid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, name)
            if aid < 0:
                continue
            target = raw[i] * c.action_scales[i] + c.default_for(name)
            data.ctrl[aid] = target
        # legs-only 契约里轮子无动作槽：ctrl 保持 0（速度执行器 = 阻尼被动）
        return
    # torque 接口：JS/训练端同款 PD（增益按关节名查表），再按 torque_limits 限幅
    for i, name in enumerate(c.action_joint_order):
        qa, da = obs.jadr[name]
        q = data.qpos[qa]
        dq = data.qvel[da]
        target = raw[i] * c.action_scales[i] + c.default_for(name)
        kp = c.gain_for(c.stiffness, name)
        kd = c.gain_for(c.damping, name)
        torque = (target - q) * kp - dq * kd
        limit = c.torque_limits.get(name.lower())
        if limit:
            torque = clamp(torque, -limit, limit)
        aid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, name)
        if aid >= 0:
            data.ctrl[aid] = torque


# ---------- 主入口 ----------

def default_modes(ranges) -> list[list[float]]:
    (vx_lo, vx_hi), (_vy_lo, vy_hi), (_wz_lo, wz_hi) = ranges
    modes = [[0.0, 0.0, 0.0], [float(vx_hi) * 0.5, 0.0, 0.0], [float(vx_hi), 0.0, 0.0]]
    if abs(vy_hi) > 0.01:
        modes.append([0.0, float(vy_hi), 0.0])
    if abs(wz_hi) > 0.01:
        modes.append([0.0, 0.0, float(wz_hi)])
    return modes


def load_package_model(package_dir: Path, sim_cfg: dict[str, Any]):
    """直接编译 model/robot.xml（meshdir 相对自身目录可解析），并补一块验收平地。

    编译前应用契约的 armature/frictionloss（增量真值，覆盖 XML default）——
    训练/验收/浏览器三方消费同一份物理常量。
    """
    import mujoco

    model_xml = package_dir / "model" / "robot.xml"
    if not model_xml.is_file():
        raise SystemExit(f"包内缺少模型: {model_xml}")
    spec = mujoco.MjSpec.from_file(str(model_xml))

    armature = sim_cfg.get("armature") or {}
    frictionloss = sim_cfg.get("frictionloss") or {}
    default_arm = armature.get("__default__")
    default_fric = frictionloss.get("__default__")
    for joint in spec.joints:
        name = joint.name
        if not name:
            continue
        lowered = name.lower()
        if lowered in armature:
            joint.armature = float(armature[lowered])
        elif default_arm is not None:
            joint.armature = float(default_arm)
        if lowered in frictionloss:
            joint.frictionloss = float(frictionloss[lowered])
        elif default_fric is not None:
            joint.frictionloss = float(default_fric)

    spec.worldbody.add_geom(
        type=mujoco.mjtGeom.mjGEOM_PLANE,
        name="acceptance_floor",
        size=[10.0, 10.0, 0.05],
    )
    return spec.compile()


def run_probe(contract: PackageContract, model, data, obs: ObsBuilder,
              seconds: float = 3.0) -> dict[str, Any]:
    """预检（清单 ⑧）：开环恒定动作扫物理包络，训练前确认动作空间可达且不即刻发散。

    无策略参与：raw 恒定为 ±magnitude（逐关节按 action_scale/default 生效），
    记录每种幅值下的存活、最低高度、最大倾角与峰值关节速度。
    """
    import mujoco

    results = []
    envelope_reach = 0.0
    for magnitude in (0.0, 0.25, -0.25, 0.5, -0.5, 0.75, -0.75, 1.0, -1.0):
        spawn_default(contract, model, data, obs)
        raw = np.full(contract.action_dim, magnitude, dtype=np.float32)
        total = int(seconds / contract.step_dt)
        height_min = float("inf")
        tilt_max = 0.0
        qvel_max = 0.0
        finite = True
        for _ in range(total):
            actuate(contract, model, data, obs, raw)
            mujoco.mj_step(model, data)
            if not (np.all(np.isfinite(data.qpos)) and np.all(np.isfinite(data.qvel))):
                finite = False
                break
            q = data.qpos[3:7]
            g = projected_gravity(q)
            tilt = math.degrees(math.acos(clamp(-g[2], -1.0, 1.0)))
            tilt_max = max(tilt_max, tilt)
            height_min = min(height_min, float(data.qpos[2]))
            qvel_max = max(qvel_max, float(np.max(np.abs(data.qvel))))
        survived = finite and height_min > 0.45 * contract.initial_height and tilt_max < 60.0
        if survived:
            envelope_reach = max(envelope_reach, abs(magnitude))
        results.append({
            "raw_action": magnitude,
            "survived": bool(survived),
            "finite": bool(finite),
            "height_min": round(height_min, 3) if math.isfinite(height_min) else None,
            "tilt_max_deg": round(tilt_max, 1),
            "qvel_max": round(qvel_max, 2),
        })
        print(f"[probe] |a|={abs(magnitude):.2f} sign={'-' if magnitude < 0 else '+'} "
              f"survived={survived} h_min={results[-1]['height_min']} tilt={results[-1]['tilt_max_deg']}°")
    return {
        "schema": "policy-probe-1.0",
        "seconds": seconds,
        "results": results,
        "envelope_reach": envelope_reach,
        "verdict": "pass" if envelope_reach >= 0.5 else "warn",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="ONNX 策略验收评估器")
    parser.add_argument("--package", required=True, help="机器人包目录")
    parser.add_argument("--policy", default="", help="policy.onnx 路径（--probe 模式可省略）")
    parser.add_argument("--modes", nargs="*", default=None, help="指令模式列表，如 0,0,0 0.3,0,0")
    parser.add_argument("--seconds", type=float, default=6.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--probe", action="store_true", help="预检模式：无策略，开环恒定动作扫物理包络")
    parser.add_argument("--output", default=None, help="指标 JSON 输出路径（默认打印 stdout）")
    args = parser.parse_args()

    import mujoco
    import onnxruntime as ort

    package_dir = Path(args.package).resolve()
    policy_path = Path(args.policy)
    if not policy_path.is_absolute():
        policy_path = package_dir / policy_path

    sim_cfg = json.loads((package_dir / "simulation" / "config.json").read_text(encoding="utf-8"))
    policies = sim_cfg.get("policies") or []
    policy_entry = next(
        (p for p in policies if str(p.get("path", "")).endswith(policy_path.name) or p.get("id") == policy_path.stem),
        policies[0] if policies else {},
    )
    contract = PackageContract(package_dir, policy_entry)

    model = load_package_model(package_dir, sim_cfg)
    model.opt.timestep = 1.0 / contract.physics_hz
    data = mujoco.MjData(model)

    if args.probe:
        obs = ObsBuilder(contract, model, data)
        report = run_probe(contract, model, data, obs, seconds=args.seconds)
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
            print(f"[probe] metrics -> {args.output}")
        print(text)
        return

    sess = ort.InferenceSession(str(policy_path), providers=["CPUExecutionProvider"])
    in_shape = sess.get_inputs()[0].shape
    if contract.obs_dim and in_shape[-1] != contract.obs_dim:
        raise SystemExit(f"ONNX 输入维度 {in_shape} 与契约 obs_dim={contract.obs_dim} 不符")

    modes = [[float(x) for x in m.split(",")] for m in args.modes] if args.modes else default_modes(contract.cmd_ranges)

    model_results = []
    for idx, cmd in enumerate(modes):
        obs = ObsBuilder(contract, model, data)
        metrics = run_mode(sess, contract, model, data, obs, cmd, args.seconds, args.seed + idx)
        model_results.append(metrics)
        print(f"[acceptance] cmd={cmd} pass={metrics['pass']} "
              f"survival={metrics['survival_ratio']} vel_err={metrics['vel_track_err']}")

    passed = sum(1 for m in model_results if m["pass"])
    report = {
        "schema": "policy-acceptance-1.0",
        "policy": policy_path.name,
        "robot_package": package_dir.name,
        "seconds_per_mode": args.seconds,
        "seed": args.seed,
        "modes": model_results,
        "passed": passed,
        "total": len(model_results),
        "verdict": "pass" if passed == len(model_results) else "fail",
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"[acceptance] metrics -> {args.output}")
    print(text)


if __name__ == "__main__":
    main()
