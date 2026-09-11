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
import sys
from pathlib import Path
from typing import Any

import numpy as np

_ROOT = Path(__file__).resolve().parents[2]  # repo root
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


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


def _q_normalize(q):
    n = float(np.linalg.norm(q)) or 1.0
    return np.asarray(q, dtype=np.float64) / n


def _q_conjugate(q):
    return np.array([q[0], -q[1], -q[2], -q[3]], dtype=np.float64)


def _q_multiply(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return np.array([
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    ], dtype=np.float64)


def _q_yaw_only(q):
    yaw = math.atan2(2 * (q[0] * q[3] + q[1] * q[2]), 1 - 2 * (q[2] * q[2] + q[3] * q[3]))
    return np.array([math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)], dtype=np.float64)


def _q_slerp(a, b, t):
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    dot = float(np.dot(a, b))
    if dot < 0:
        b = -b
        dot = -dot
    if dot > 0.9995:
        return _q_normalize(a + t * (b - a))
    theta0 = math.acos(max(-1.0, min(1.0, dot)))
    theta = theta0 * t
    s0 = math.sin((1 - t) * theta0) / math.sin(theta0)
    s1 = math.sin(t * theta0) / math.sin(theta0)
    return _q_normalize(a * s0 + b * s1)


def _q_to_matrix(q):
    w, x, y, z = _q_normalize(q)
    return np.array([
        1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y),
        2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x),
        2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y),
    ], dtype=np.float64)


def _q_from_axis_angle(axis, angle):
    n = float(np.linalg.norm(axis)) or 1.0
    s = math.sin(angle / 2)
    return np.array([math.cos(angle / 2), axis[0] / n * s, axis[1] / n * s, axis[2] / n * s], dtype=np.float64)


class MotionLoader:
    """参考动作 CSV 加载器（对照 web/sim2sim/motion_loader.js 移植）。

    CSV 列 = [root_pos(3), root_quat_xyzw(4), dof_pos(N)]；按 [time_start,time_end]
    裁剪，提供时间插值的关节位置/速度/根四元数与 anchor/torso 辅助。
    """

    def __init__(self, csv_text: str, motion_params: dict):
        self.fps = float(motion_params.get("fps", 50.0) or 50.0)
        self.dt = 1.0 / self.fps
        self.time_start = float(motion_params.get("time_start", 0.0) or 0.0)
        self.time_end = float(motion_params.get("time_end", 0.0) or 0.0)
        lines = [ln for ln in csv_text.strip().replace("\r", "").split("\n") if ln]
        if not lines:
            raise ValueError("motion csv empty")
        rows = [[float(v) if v not in ("", "nan") else 0.0 for v in ln.split(",")] for ln in lines]
        self.num_joints = len(rows[0]) - 7
        start = round(self.time_start * self.fps)
        end = min(len(rows), round(self.time_end * self.fps) or len(rows))
        clipped = rows[start:max(end, start + 1)]
        if not clipped:
            raise ValueError("motion csv has no frames in window")
        self.root_positions = [[r[0], r[1], r[2]] for r in clipped]
        self.root_quaternions = [[r[6], r[3], r[4], r[5]] for r in clipped]  # -> wxyz
        self.dof_positions = [r[7:] for r in clipped]
        self.dof_velocities = []
        for f in range(len(self.dof_positions)):
            nxt = self.dof_positions[min(f + 1, len(self.dof_positions) - 1)]
            cur = self.dof_positions[f]
            self.dof_velocities.append([(nxt[i] - cur[i]) / self.dt for i in range(len(cur))])
        self.num_frames = len(self.dof_positions)
        self.duration = self.num_frames * self.dt
        self.index0 = self.index1 = 0
        self.blend = 0.0
        self.init_quat = np.array([1.0, 0, 0, 0])
        self.time = 0.0

    def update(self, time_s: float) -> None:
        phase = min(max(time_s / max(self.duration, 1e-8), 0.0), 1.0)
        frame_float = phase * max(self.num_frames - 1, 0)
        self.index0 = int(math.floor(frame_float))
        self.index1 = min(self.index0 + 1, self.num_frames - 1)
        self.blend = frame_float - self.index0

    def reset(self, robot_quat, time_s: float = 0.0) -> None:
        self.update(time_s)
        self.init_quat = _q_multiply(_q_yaw_only(robot_quat), _q_conjugate(_q_yaw_only(self.root_quaternion())))

    def _lerp(self, arr, idx0, idx1):
        a, b = arr[idx0], arr[idx1]
        return [a[i] * (1 - self.blend) + b[i] * self.blend for i in range(len(a))]

    def joint_pos(self):
        return self._lerp(self.dof_positions, self.index0, self.index1)

    def joint_vel(self):
        return self._lerp(self.dof_velocities, self.index0, self.index1)

    def root_quaternion(self):
        return _q_slerp(self.root_quaternions[self.index0], self.root_quaternions[self.index1], self.blend)

    def motion_anchor_ori_b(self, real_quat, ref_quat):
        rot_quat = _q_multiply(_q_conjugate(_q_multiply(self.init_quat, ref_quat)), real_quat)
        rot = _q_to_matrix(rot_quat)
        return [rot[0], rot[3], rot[1], rot[4], rot[2], rot[5]]

    def torso_quat_w(self, root_quat, waist_angles):
        yaw, roll, pitch = waist_angles
        q = _q_multiply(root_quat, _q_from_axis_angle([0, 0, 1], yaw))
        q = _q_multiply(q, _q_from_axis_angle([1, 0, 0], roll))
        q = _q_multiply(q, _q_from_axis_angle([0, 1, 0], pitch))
        return _q_normalize(q)

    def anchor_quat_w(self):
        jp = self.joint_pos()
        return self.torso_quat_w(self.root_quaternion(), [jp[12], jp[13], jp[14]])


def deep_merge(base: dict, overlay: dict) -> dict:
    """递归合并：dict 逐键合并，标量/列表由 overlay 覆盖（与后端契约合并同语义）。"""
    out = dict(base)
    for key, value in (overlay or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


# ---------- 包契约读取 ----------

class PackageContract:
    def __init__(self, package_dir: Path, policy_entry: dict[str, Any]):
        self.root = package_dir
        self.sim = json.loads((package_dir / "simulation" / "config.json").read_text(encoding="utf-8-sig"))
        self.entry = policy_entry
        # 包级 policy_contract 是每个策略契约的默认值（后端 browser-config 会深合并，
        # 验收器必须同语义，否则 microduck/zex-w/go2w 这类包级默认 kind 会丢失）。
        package_default = self.sim.get("policy_contract") or self.sim.get("default_policy_contract") or {}
        self.contract = deep_merge(package_default, policy_entry.get("contract") or {})
        # 策略未声明动作序时回退到机器人级 contract.json 的 action.joint_order
        robot_contract_path = package_dir / "contract.json"
        robot_order: list[str] = []
        if robot_contract_path.is_file():
            rc = json.loads(robot_contract_path.read_text(encoding="utf-8-sig"))
            action = rc.get("action") or {}
            robot_order = [str(n) for n in (action.get("joint_order") or rc.get("joints", {}).get("actuated_joints") or [])]
        self.action_joint_order = [str(n) for n in (self.contract.get("action_joint_order") or [])] or robot_order
        self.physics_hz = float(self.sim.get("physics_hz") or 200)
        self.decimation = int(self.sim.get("decimation") or 4)
        self.step_dt = 1.0 / self.physics_hz * self.decimation
        self.actuator_interface = str(self.sim.get("actuator_interface") or "torque").lower()
        self.initial_height = float(self.sim.get("initial_base_height") or 0.4)
        # 力矩限幅：策略契约可覆盖包级（不同训练工程限幅不同，如 ArenaX 用 45）。
        torque_limits = self.contract.get("torque_limits") or self.sim.get("torque_limits") or {}
        self.torque_limits = {k.lower(): float(v) for k, v in torque_limits.items()}

        scales = self.contract.get("scales") or {}
        self.ang_vel_scale = float(scales.get("ang_vel", 1.0))
        self.dof_pos_scale = float(scales.get("dof_pos", 1.0))
        self.dof_vel_scale = float(scales.get("dof_vel", 1.0))
        self.cmd_scale = [float(x) for x in (scales.get("command") or [1.0, 1.0, 1.0])]

        self.observation_kind = str(self.contract.get("observation_kind") or "")
        # 回退策略条目顶层：部分包的策略 contract 为空，维度只在条目顶层声明。
        self.obs_dim = int(self.contract.get("obs_dim") or policy_entry.get("obs_dim") or 0)
        self.action_dim = int(self.contract.get("action_dim") or policy_entry.get("action_dim") or 0)
        self.clip_actions = self.contract.get("clip_actions") or None

        self.default_joint_angles = {k.lower(): float(v) for k, v in (self.contract.get("default_joint_angles") or {}).items()}
        scale_by_joint = {k.lower(): float(v) for k, v in (self.contract.get("action_scale_by_joint") or {}).items()}
        default_scale = float(self.contract.get("action_scale") or 0.5)
        self.action_scales = [
            scale_by_joint.get(name.lower(), default_scale) for name in self.action_joint_order
        ]
        self.gait_period = float(self.contract.get("gait_period_s") or 0.6)

        self.velocity_scale = float(self.contract.get("velocity_scale") or self.sim.get("velocity_scale") or 1.0)
        # 双模型（encoder + policy）部署，如 LimX TRON1：encoder(proprio history) → latent
        # → policy([latent, obs, cmd])。字段在当前策略契约里声明。
        self.encoder_rel = str(policy_entry.get("encoder") or self.contract.get("encoder") or "")
        self.tron1 = self.contract.get("tron1") or {}
        raw_modes = self.contract.get("control_modes") or self.sim.get("control_modes") or {}
        if isinstance(raw_modes, dict):
            self.control_modes = {str(k).lower(): str(v).lower() for k, v in raw_modes.items()}
        else:
            self.control_modes = {}
        self.history_len = max(1, int(self.contract.get("history_len") or policy_entry.get("history_len") or 1))
        self.total_obs_dim = self.obs_dim * self.history_len
        self.history_layout = str(self.contract.get("history_layout") or "")
        # 显式 history 分段（Wuji reorient 这类非标准布局）：[[offset,len], ...]，
        # 每段按 旧→新 逐帧拼接（对齐 mjlab concatenate_terms 的逐 term history）。
        self.history_terms = self.contract.get("history_terms") or None
        # 绝对位置 + EMA + warmup 控制（Wuji Hand）：target = default + clamp(a,-1,1)*scale
        self.action_clamp = self.contract.get("action_clamp")
        self.action_ema_alpha = self.contract.get("action_ema_alpha")
        self.action_warmup_s = float(self.contract.get("action_warmup_s") or 0.0)
        mask = self.contract.get("observation_mask") or {}
        self.wrap_pi_joints = [str(n) for n in (mask.get("wrap_pi") or [])]
        self.command_dims = int(self.contract.get("command_dims") or 3)
        self.task_type = str(self.contract.get("task_type") or "")
        self.default_command = [float(x) for x in (self.contract.get("default_command") or [])]
        # 动作模仿/跟踪：参考动作 CSV 与映射
        self.motion_params = self.contract.get("motion_params") or {}
        self.motion_joint_mapping = self.contract.get("motion_joint_mapping")
        self.waist_joint_indices = self.contract.get("waist_joint_indices") or [2, 5, 8]
        self.clip_obs = self.contract.get("clip_obs")
        self.motion_loop = bool(self.motion_params.get("loop") or self.motion_params.get("motion_loop"))
        self.motion_loader = None

        control = self.sim.get("control") or {}
        ctrl = self.contract.get("control") or {}
        self.stiffness = (ctrl.get("stiffness") or self.contract.get("stiffness")
                          or control.get("stiffness") or self.sim.get("stiffness") or {})
        self.damping = (ctrl.get("damping") or self.contract.get("damping")
                        or control.get("damping") or self.sim.get("damping") or {})

        ranges = (self.contract.get("command_ranges") or {})
        self.cmd_ranges = (
            ranges.get("lin_vel_x") or [-0.5, 1.0],
            ranges.get("lin_vel_y") or [-0.5, 0.5],
            ranges.get("ang_vel_z") or [-1.0, 1.0],
        )

    def default_for(self, joint: str) -> float:
        return self.default_joint_angles.get(joint.lower(), 0.0)

    def is_velocity_joint(self, name: str) -> bool:
        """control_modes 为 {关节名: position|velocity} 映射（含 role 级 'wheel'）。"""
        lowered = name.lower()
        if self.control_modes.get(lowered) == "velocity":
            return True
        return "wheel" in lowered and self.control_modes.get("wheel") == "velocity"

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
        self.history: list[np.ndarray] = []
        self.motion_loader = contract.motion_loader
        self.motion_time = 0.0
        # Wuji reorient（固定基座灵巧手）：归一化动作目标 + tag 系目标朝向
        self.wuji_target = np.zeros(contract.action_dim, dtype=np.float64)
        self.wuji_goal_quat = np.array((1.0, 0.0, 0.0, 0.0), dtype=np.float64)

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


# ---------- 单帧观测规格（与 web/sim2sim/obs/observation_builders.js 逐项对齐） ----------
#
# 每个 observation_kind 的单帧由 _frame_* 函数产出；history（history_len>1）由
# pack_history 统一按 app.js packObsHistoryByTerm 同布局打包。新增布局 = 加一个
# _frame_* + 注册进 FRAME_BUILDERS，不再散落 if-else。

# 浏览器端 IMU 采样与 mjlab/契约同号（直立 projected_gravity=(0,0,-1)），
# 故 Python 侧直接用 qpos/qvel 推导，不再做符号翻转。

_STANDARD_KINDS = {"go2_rl_sdk_45", "lite3_rl_sdk_hist6", "s07_amp_cts"}


def _std_frame(obs: "ObsBuilder", cmd: np.ndarray) -> list[float]:
    """ang_vel·s, gravity, cmd·s, (q-default)·s, dq·s, action（四足/人形通用 45/98 基座）。"""
    c = obs.contract
    _, ang_b, _ = obs.base_state()
    q = obs.data.qpos[3:7]
    order = c.action_joint_order
    out = list(ang_b * c.ang_vel_scale)
    out += list(projected_gravity(q))
    out += list(cmd * np.asarray(c.cmd_scale))
    out += [(obs.data.qpos[obs.jadr[n][0]] - c.default_for(n)) * c.dof_pos_scale for n in order]
    out += [obs.data.qvel[obs.jadr[n][1]] * c.dof_vel_scale for n in order]
    out += list(obs.last_action)
    return out


def _frame_g1_mjlab_velocity_98(obs: "ObsBuilder", cmd: np.ndarray) -> list[float]:
    c = obs.contract
    _, ang_b, _ = obs.base_state()
    q = obs.data.qpos[3:7]
    order = c.action_joint_order
    phase = (obs.phase_s % c.gait_period) / c.gait_period
    moving = float(np.linalg.norm(cmd)) >= 0.1
    out = list(ang_b * c.ang_vel_scale) + list(projected_gravity(q)) + list(cmd * np.asarray(c.cmd_scale))
    out += [math.sin(phase * 2 * math.pi) if moving else 0.0]
    out += [math.cos(phase * 2 * math.pi) if moving else 0.0]
    obs.phase_s += c.step_dt
    out += [(obs.data.qpos[obs.jadr[n][0]] - c.default_for(n)) * c.dof_pos_scale for n in order]
    out += [obs.data.qvel[obs.jadr[n][1]] * c.dof_vel_scale for n in order]
    out += list(obs.last_action)
    return out


def _frame_g1_amp_96(obs: "ObsBuilder", cmd: np.ndarray) -> list[float]:
    return _std_frame(obs, cmd)


def _frame_g1_mjswan_balance(obs: "ObsBuilder", cmd: np.ndarray) -> list[float]:
    c = obs.contract
    _, ang_b, _ = obs.base_state()
    q = obs.data.qpos[3:7]
    order = c.action_joint_order
    out = list(ang_b * c.ang_vel_scale) + list(projected_gravity(q))
    out += [(obs.data.qpos[obs.jadr[n][0]] - c.default_for(n)) * c.dof_pos_scale for n in order]
    out += [obs.data.qvel[obs.jadr[n][1]] * c.dof_vel_scale for n in order]
    out += list(obs.last_action)
    return out


def _frame_g1_mjswan_locomotion(obs: "ObsBuilder", cmd: np.ndarray) -> list[float]:
    c = obs.contract
    _, ang_b, lin_b = obs.base_state()
    q = obs.data.qpos[3:7]
    order = c.action_joint_order
    out = list(lin_b) + list(ang_b * c.ang_vel_scale) + list(projected_gravity(q))
    out += [(obs.data.qpos[obs.jadr[n][0]] - c.default_for(n)) * c.dof_pos_scale for n in order]
    out += [obs.data.qvel[obs.jadr[n][1]] * c.dof_vel_scale for n in order]
    out += list(obs.last_action)
    out += list(cmd * np.asarray(c.cmd_scale))
    return out


def _frame_go1_playground_48(obs: "ObsBuilder", cmd: np.ndarray) -> list[float]:
    c = obs.contract
    _, ang_b, lin_b = obs.base_state()
    q = obs.data.qpos[3:7]
    order = c.action_joint_order
    out = list(lin_b) + list(ang_b) + list(projected_gravity(q))  # 裸值无缩放
    out += [obs.data.qpos[obs.jadr[n][0]] - c.default_for(n) for n in order]
    out += [obs.data.qvel[obs.jadr[n][1]] for n in order]
    out += list(obs.last_action)
    out += list(cmd)
    return out


def _frame_go2_motion_69(obs: "ObsBuilder", cmd: np.ndarray) -> list[float]:
    """Go2 模仿/特技 69：motion_command(24)+anchor_ori_b(6)+ang_vel(3)+q(12)+dq(12)+action(12)。"""
    c = obs.contract
    loader = obs.motion_loader
    if loader is None:
        raise ValueError("go2_motion_69 需要 motion_loader（motion_csv）")
    obs.motion_time += 0.02  # 与 JS 一致：每控制步 +0.02s
    if obs.motion_time > loader.duration:
        obs.motion_time = (obs.motion_time % loader.duration) if c.motion_loop else loader.duration
    loader.update(obs.motion_time)
    ref_pos = loader.joint_pos()
    ref_vel = loader.joint_vel()
    mapping = c.motion_joint_mapping or list(range(len(ref_pos)))
    out = [ref_pos[mapping[i]] for i in range(len(mapping))]
    out += [ref_vel[mapping[i]] for i in range(len(mapping))]
    out += list(loader.motion_anchor_ori_b(list(obs.data.qpos[3:7]), loader.root_quaternion()))
    _, ang_b, _ = obs.base_state()
    out += list(ang_b * c.ang_vel_scale)
    order = c.action_joint_order
    out += [obs.data.qpos[obs.jadr[n][0]] - c.default_for(n) for n in order]
    out += [obs.data.qvel[obs.jadr[n][1]] for n in order]
    out += list(obs.last_action)
    return out


def _frame_g1_motion_154(obs: "ObsBuilder", cmd: np.ndarray) -> list[float]:
    """G1 动作跟踪 154：motion_command(58)+anchor(6)+ang_vel(3)+q(29)+dq(29)+action(29)，含腰补偿。"""
    c = obs.contract
    loader = obs.motion_loader
    if loader is None:
        raise ValueError("g1_motion_154 需要 motion_loader（motion_csv）")
    obs.motion_time += c.step_dt
    if obs.motion_time > loader.duration:
        obs.motion_time = obs.motion_time % loader.duration
    loader.update(obs.motion_time)
    ref_pos = loader.joint_pos()
    ref_vel = loader.joint_vel()
    mapping = c.motion_joint_mapping or list(range(len(ref_pos)))
    out = [ref_pos[mapping[i]] for i in range(len(mapping))]
    out += [ref_vel[mapping[i]] for i in range(len(mapping))]
    order = c.action_joint_order
    base_quat = list(obs.data.qpos[3:7])
    # ``action_joint_order`` 已是策略槽位序（interleaved）；waist_joint_indices 为策略槽。
    waist_real = [obs.data.qpos[obs.jadr[order[slot]][0]] for slot in c.waist_joint_indices]
    real_quat = loader.torso_quat_w(base_quat, waist_real)
    out += list(loader.motion_anchor_ori_b(real_quat, loader.anchor_quat_w()))
    _, ang_b, _ = obs.base_state()
    out += list(ang_b * c.ang_vel_scale)
    out += [(obs.data.qpos[obs.jadr[order[i]][0]] - c.default_for(order[i])) * c.dof_pos_scale
            for i in range(c.action_dim)]
    out += [obs.data.qvel[obs.jadr[order[i]][1]] * c.dof_vel_scale for i in range(c.action_dim)]
    out += list(obs.last_action)
    if c.clip_obs is not None:
        out = [max(-c.clip_obs, min(c.clip_obs, v)) for v in out]
    return out


def _frame_microduck_61(obs: "ObsBuilder", cmd: np.ndarray) -> list[float]:
    """microduck_61：ang_vel, gravity, q_rel(14), dq(14), action(14), cmd(13)。"""
    c = obs.contract
    _, ang_b, _ = obs.base_state()
    q = obs.data.qpos[3:7]
    order = c.action_joint_order
    out = list(ang_b * c.ang_vel_scale)
    out += list(projected_gravity(q))
    out += [(obs.data.qpos[obs.jadr[n][0]] - c.default_for(n)) * c.dof_pos_scale for n in order]
    out += [obs.data.qvel[obs.jadr[n][1]] * c.dof_vel_scale for n in order]
    out += list(obs.last_action)
    # 13 维复合命令：默认取自契约，前 3 维用速度指令覆盖（raw，与 JS 一致）。
    cmd13 = list(c.default_command[:13]) + [0.0] * max(0, 13 - len(c.default_command))
    for i in range(min(3, len(cmd))):
        cmd13[i] = float(cmd[i])
    out += cmd13[:13]
    return out


def _frame_dreamwaq_57(obs: "ObsBuilder", cmd: np.ndarray) -> list[float]:
    """DreamWaQ 轮足单帧 57：cmd, ang_vel, gravity, dof_pos_rel(轮清零), dof_vel, action。

    参考 `00_resources/Dreamwaq/deploy/deploy_mujoco/deploy_mujoco.py:compute_observation`
    （m20）：`obs[0:3]=cmd*[2,2,0.25]`、`obs[3:6]=ang_vel*0.25`、`obs[6:9]=gravity`、
    dof_error 的轮子索引清零、dof_vel*0.05、action。
    """
    c = obs.contract
    _, ang_b, _ = obs.base_state()
    q = obs.data.qpos[3:7]
    order = c.action_joint_order
    out = list(cmd * np.asarray(c.cmd_scale))
    out += list(ang_b * c.ang_vel_scale)
    out += list(projected_gravity(q))
    out += [0.0 if c.is_velocity_joint(n) else (obs.data.qpos[obs.jadr[n][0]] - c.default_for(n)) * c.dof_pos_scale
            for n in order]
    out += [obs.data.qvel[obs.jadr[n][1]] * c.dof_vel_scale for n in order]
    out += list(obs.last_action)
    return out


def _frame_himloco_45(obs: "ObsBuilder", cmd: np.ndarray) -> list[float]:
    """HIMLoco 单帧 45：commands, ang_vel, gravity, dof_pos_rel, dof_vel, actions。

    参考 `00_resources/rl_sar/policy/lite3/himloco/config.yaml` 的 observations 列表序
    （commands 在最前）+ `rl_sdk.cpp:ComputeObservation` 的逐项缩放；history 由
    observations_history_priority="time" 决定为 frame_major 最新帧在前。
    """
    c = obs.contract
    _, ang_b, _ = obs.base_state()
    q = obs.data.qpos[3:7]
    order = c.action_joint_order
    out = list(cmd * np.asarray(c.cmd_scale))
    out += list(ang_b * c.ang_vel_scale)
    out += list(projected_gravity(q))
    out += [(obs.data.qpos[obs.jadr[n][0]] - c.default_for(n)) * c.dof_pos_scale for n in order]
    out += [obs.data.qvel[obs.jadr[n][1]] * c.dof_vel_scale for n in order]
    out += list(obs.last_action)
    return out


def _frame_go2w_mjlab_legs_53(obs: "ObsBuilder", cmd: np.ndarray) -> list[float]:
    c = obs.contract
    _, ang_b, _ = obs.base_state()
    q = obs.data.qpos[3:7]
    legs = c.action_joint_order[:12]
    wheels = c.wrap_pi_joints or ["FR_wheel_joint", "FL_wheel_joint", "RR_wheel_joint", "RL_wheel_joint"]
    out = list(ang_b * c.ang_vel_scale) + list(projected_gravity(q)) + list(cmd * np.asarray(c.cmd_scale))
    out += [obs.data.qpos[obs.jadr[n][0]] - c.default_for(n) for n in legs]
    out += [obs.data.qvel[obs.jadr[n][1]] * c.dof_vel_scale for n in legs]
    for n in wheels:
        a = obs.jadr.get(n)
        out.append(wrap_pi(obs.data.qpos[a[0]]) if a else 0.0)
    for n in wheels:
        a = obs.jadr.get(n)
        out.append(obs.data.qvel[a[1]] * c.dof_vel_scale if a else 0.0)
    out += list(obs.last_action)
    return out


def _frame_go2w_53(obs: "ObsBuilder", cmd: np.ndarray) -> list[float]:
    """go2w_sim2sim 混合：ang·0.25, gravity, cmd, 12 腿 pos_rel, 12 腿 dq·0.05, 4 轮 dq·0.05, 16 action。"""
    c = obs.contract
    _, ang_b, _ = obs.base_state()
    q = obs.data.qpos[3:7]
    legs = c.action_joint_order[:12]
    out = list(ang_b * 0.25) + list(projected_gravity(q)) + list(cmd * np.asarray(c.cmd_scale))
    out += [obs.data.qpos[obs.jadr[n][0]] - c.default_for(n) for n in legs]
    out += [obs.data.qvel[obs.jadr[n][1]] * 0.05 for n in legs]
    # 轮速段序 = 参考 joint_names 的轮顺序（FR,FL,RR,RL）
    for n in ("FR_wheel_joint", "FL_wheel_joint", "RR_wheel_joint", "RL_wheel_joint"):
        a = obs.jadr.get(n)
        out.append(obs.data.qvel[a[1]] * 0.05 if a else 0.0)
    out += list(obs.last_action)
    return out


def _frame_go2w_rl_sdk_57(obs: "ObsBuilder", cmd: np.ndarray) -> list[float]:
    """rl_sar/robot_lab 57：ang·s, gravity, cmd, (轮位置清零), dq·s(16), action(16)。"""
    c = obs.contract
    _, ang_b, _ = obs.base_state()
    q = obs.data.qpos[3:7]
    order = c.action_joint_order
    out = list(ang_b * c.ang_vel_scale) + list(projected_gravity(q)) + list(cmd * np.asarray(c.cmd_scale))
    for n in order:
        rel = (obs.data.qpos[obs.jadr[n][0]] - c.default_for(n)) * c.dof_pos_scale
        out.append(0.0 if c.is_velocity_joint(n) else rel)
    out += [obs.data.qvel[obs.jadr[n][1]] * c.dof_vel_scale for n in order]
    out += list(obs.last_action)
    return out


def _frame_go2w_himloco_57(obs: "ObsBuilder", cmd: np.ndarray) -> list[float]:
    """go2w HIMLoco 57：cmd·s, ang·s, gravity, (轮位清零)dof_pos, dq·s, action(16)。

    参考 `00_resources/LeggedSkillDeploy/.../go2w_himloco/config.yaml` 的
    `observations` 列表序（commands 在最前）+ 逐项缩放；wheel_indices=[3,7,11,15]
    的 dof_pos_rel 清零，轮为速度控制（action_scale 5.0）。
    """
    c = obs.contract
    _, ang_b, _ = obs.base_state()
    q = obs.data.qpos[3:7]
    order = c.action_joint_order
    out = list(cmd * np.asarray(c.cmd_scale))
    out += list(ang_b * c.ang_vel_scale)
    out += list(projected_gravity(q))
    for n in order:
        rel = (obs.data.qpos[obs.jadr[n][0]] - c.default_for(n)) * c.dof_pos_scale
        out.append(0.0 if c.is_velocity_joint(n) else rel)
    out += [obs.data.qvel[obs.jadr[n][1]] * c.dof_vel_scale for n in order]
    out += list(obs.last_action)
    return out


def _frame_zexw_53(obs: "ObsBuilder", cmd: np.ndarray) -> list[float]:
    """zex-w 53：ang·s, gravity, cmd·s, 非轮 pos_rel, 非轮 dq·s, 轮 dq·s, action(16)。"""
    c = obs.contract
    _, ang_b, _ = obs.base_state()
    q = obs.data.qpos[3:7]
    order = c.action_joint_order
    out = list(ang_b * c.ang_vel_scale) + list(projected_gravity(q)) + list(cmd * np.asarray(c.cmd_scale))
    out += [(obs.data.qpos[obs.jadr[n][0]] - c.default_for(n)) * c.dof_pos_scale
            for n in order if not c.is_velocity_joint(n)]
    out += [obs.data.qvel[obs.jadr[n][1]] * c.dof_vel_scale
            for n in order if not c.is_velocity_joint(n)]
    out += [obs.data.qvel[obs.jadr[n][1]] * c.dof_vel_scale
            for n in order if c.is_velocity_joint(n)]
    out += list(obs.last_action)
    return out


# ---------- Wuji Hand in-hand reorientation ----------
#
# 固定基座灵巧手 + 自由立方体；策略 69 维单帧 / history 3 → 207。观测 = 归一化关节角(20)
# + 关节目标误差(20) + 立方体 tag 系位置(3) + 目标 6D 朝向误差(6) + 上一动作(20)。
# 参考 00_resources/wuji-mjlab tasks/reorient（observations.py / reorient_terms.py）。

_WUJI_TAG_IN_PALM_POS = np.array((0.0262, 0.0, -0.0563), dtype=np.float64)
_WUJI_TAG_IN_PALM_QUAT = np.array((math.cos(math.radians(45.0)), 0.0, math.sin(math.radians(45.0)), 0.0), dtype=np.float64)


def _wuji_body_id(model, name: str) -> int:
    import mujoco

    return int(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name))


def _wuji_quat_apply(q: np.ndarray, v: np.ndarray) -> np.ndarray:
    return _q_to_matrix(q).reshape(3, 3) @ np.asarray(v, dtype=np.float64)


def _wuji_normalized_joints(obs: "ObsBuilder") -> np.ndarray:
    """按软限位把当前 20 关节角归一化到 [-1, 1]（mjlab soft_joint_pos_limits）。"""
    import mujoco

    model = obs.model
    out = np.zeros(len(obs.contract.action_joint_order), dtype=np.float64)
    for i, name in enumerate(obs.contract.action_joint_order):
        jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        lo, hi = float(model.jnt_range[jid, 0]), float(model.jnt_range[jid, 1])
        center, half = 0.5 * (lo + hi), 0.5 * (hi - lo) * 0.9
        q = obs.data.qpos[obs.jadr[name][0]]
        out[i] = clamp((q - center) / (half + 1e-6), -1.0, 1.0)
    return out


def _frame_wuji_reorient_69(obs: "ObsBuilder", cmd: np.ndarray) -> list[float]:
    """单帧 69：joint(20) + qpos_error(20) + cube_pos_tag(3) + ori_err6d(6) + action(20)。"""
    c = obs.contract
    model, data = obs.model, obs.data

    norm_joint = _wuji_normalized_joints(obs)
    target = np.asarray(obs.wuji_target, dtype=np.float64)
    qpos_error = norm_joint - target

    palm_id = _wuji_body_id(model, "right_palm_link")
    cube_id = _wuji_body_id(model, "cube")
    palm_pos_w = np.asarray(data.xpos[palm_id], dtype=np.float64)
    palm_quat_w = _q_normalize(np.asarray(data.xquat[palm_id], dtype=np.float64))
    tag_pos_w = palm_pos_w + _wuji_quat_apply(palm_quat_w, _WUJI_TAG_IN_PALM_POS)
    tag_quat_w = _q_normalize(_q_multiply(palm_quat_w, _WUJI_TAG_IN_PALM_QUAT))

    cube_pos_w = np.asarray(data.xpos[cube_id], dtype=np.float64)
    cube_quat_w = _q_normalize(np.asarray(data.xquat[cube_id], dtype=np.float64))
    cube_pos_tag = _wuji_quat_apply(_q_conjugate(tag_quat_w), cube_pos_w - tag_pos_w)

    tag_inv = _q_conjugate(tag_quat_w)
    cube_in_tag = _q_multiply(tag_inv, cube_quat_w)
    goal_in_tag = _q_multiply(tag_inv, np.asarray(obs.wuji_goal_quat, dtype=np.float64))
    q_err = _q_multiply(cube_in_tag, _q_conjugate(goal_in_tag))
    rot = _q_to_matrix(q_err).reshape(-1)[3:9]

    out = list(norm_joint) + list(qpos_error) + list(cube_pos_tag) + list(rot) + list(obs.last_action)
    return [float(x) for x in out]


FRAME_BUILDERS = {
    "go2_rl_sdk_45": _std_frame,
    "lite3_rl_sdk_hist6": _std_frame,
    "s07_amp_cts": _std_frame,
    "g1_amp_96": _frame_g1_amp_96,
    "g1_mjlab_velocity_98": _frame_g1_mjlab_velocity_98,
    "g1_mjswan_locomotion": _frame_g1_mjswan_locomotion,
    "g1_mjswan_balance": _frame_g1_mjswan_balance,
    "go1_playground_48": _frame_go1_playground_48,
    "go2w_53": _frame_go2w_53,
    "go2w_mjlab_legs_53": _frame_go2w_mjlab_legs_53,
    "go2w_rl_sdk_57": _frame_go2w_rl_sdk_57,
    "go2w_himloco_57": _frame_go2w_himloco_57,
    "zexw_53": _frame_zexw_53,
    "himloco_45_hist6": _frame_himloco_45,
    "microduck_61": _frame_microduck_61,
    "go2_motion_69": _frame_go2_motion_69,
    "g1_motion_154": _frame_g1_motion_154,
    "dreamwaq_57": _frame_dreamwaq_57,
    "wuji_reorient_69": _frame_wuji_reorient_69,
    # lite3 的 rl_sar HIMLoco 部署与 go1 同源（observations 列表 commands 在前）；
    # 包内 kind 标注曾误用通用 locomotion 序，这里按同一布局处理。
    "lite3_rl_sdk_hist6": _frame_himloco_45,
}

# 需要 MotionLoader（参考动作 CSV）/13 维复合命令的布局：本轮交由 Node 桥（复用
# web 侧同一真值）覆盖，Python 侧显式报错而不是给出错误观测。
_DEFERRED_KINDS = {"quadrupedal_agility_ll", "wheel_leg_gait_moe_cts", "wheel_leg_jump_moe_cts"}


def pack_history(obs: "ObsBuilder", frames: list[np.ndarray]) -> np.ndarray:
    """按 app.js packObsHistoryByTerm 同布局打包 history（frames 为 oldest→newest）。"""
    c = obs.contract
    if c.history_layout == "frame_major_v1":
        return np.concatenate(list(reversed(frames)))  # 最新帧在前
    if c.history_layout == "frame_major":
        return np.concatenate(frames)  # 整帧依时序拼接，最老帧在前（DreamWaQ 系）
    if c.history_layout == "wuji_term_major" and c.history_terms:
        # 每个显式分段按 旧→新 逐帧拼接（term-major / 段内 history 连续）
        return np.concatenate([
            f[int(off):int(off) + int(length)]
            for off, length in c.history_terms
            for f in frames
        ])
    if c.observation_kind == "zexw_53":
        terms = [(0, 3), (3, 3), (6, 3), (9, 12), (21, 12), (33, 4), (37, 16)]
        return np.concatenate([f[o:o + l] for o, l in terms for f in frames])
    n = len(c.action_joint_order)
    joint_offset, vel_offset, act_offset = 9, 9 + n, 9 + 2 * n
    extra_offset = act_offset + n
    extra_len = max(0, (c.obs_dim or extra_offset) - extra_offset)
    base = [(0, 3), (3, 3), (6, c.command_dims)]
    action_terms = [(joint_offset, n), (vel_offset, n), (act_offset, n)]
    if c.history_layout == "term_major_suffix_extra_v1":
        terms = base + action_terms + ([(extra_offset, extra_len)] if extra_len > 0 else [])
    else:
        terms = base + ([(extra_offset, extra_len)] if extra_len > 0 else []) + action_terms
    return np.concatenate([f[o:o + l] for o, l in terms for f in frames])


def _obs_build(self: "ObsBuilder", cmd: np.ndarray) -> np.ndarray:
    c = self.contract
    kind = c.observation_kind
    if kind in _DEFERRED_KINDS:
        raise ValueError(f"观测布局 {kind!r} 需 MotionLoader/复合命令，请用 Node 桥验收（obs_bridge.mjs）")
    builder = FRAME_BUILDERS.get(kind)
    if builder is None:
        raise ValueError(f"验收器暂不支持观测布局: {kind!r}")
    frame = np.asarray(builder(self, cmd), dtype=np.float32)
    if c.obs_dim and frame.shape[0] != c.obs_dim:
        raise ValueError(f"单帧观测维度不符: 构建 {frame.shape[0]} vs 契约 obs_dim={c.obs_dim}")
    if c.history_len <= 1:
        return frame[None, :].astype(np.float32)  # 单帧不做 term-major 重排
    self.history.append(frame)
    if len(self.history) > c.history_len:
        self.history = self.history[-c.history_len:]
    frames = list(self.history)
    while len(frames) < c.history_len:
        frames.insert(0, frames[0])
    packed = pack_history(self, frames)
    if c.total_obs_dim and packed.shape[0] != c.total_obs_dim:
        raise ValueError(
            f"观测维度不符: 打包 {packed.shape[0]} vs 契约 {c.total_obs_dim}"
            f"（obs_dim {c.obs_dim} × history {c.history_len}）"
        )
    return packed[None, :].astype(np.float32)


ObsBuilder.build = _obs_build


# ---------- 单模式滚出 ----------

def run_mode(sess, contract: PackageContract, model, data, obs: ObsBuilder,
             cmd: list[float], seconds: float, seed: int) -> dict[str, Any]:
    import mujoco

    rng = np.random.default_rng(seed)
    spawn_default(contract, model, data, obs)

    obs_builder = obs
    obs_builder.phase_s = 0.0
    obs_builder.last_action[:] = 0
    obs_builder.history = []
    if contract.motion_loader is not None and contract.observation_kind in ("go2_motion_69", "g1_motion_154"):
        contract.motion_loader.reset(list(data.qpos[3:7]))
        obs_builder.motion_loader = contract.motion_loader
        obs_builder.motion_time = 0.0
    cmd_arr = np.asarray(cmd, dtype=np.float32)

    total = int(seconds / contract.step_dt)
    fell_at = None
    height_min = float("inf")
    roll_max = pitch_max = 0.0
    vel_errs: list[float] = []
    tracked = 0
    steady_height: list[float] = []
    steady_roll: list[float] = []
    steady_pitch: list[float] = []

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
            # 稳态度量：末 30% 窗口，避免启动瞬态（起摆/落地）主导判据。
            steady_height.append(float(data.qpos[2]))
            steady_roll.append(abs(roll))
            steady_pitch.append(abs(pitch))

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
        # 稳态（末 30%）：站立/平衡判据应以稳态为准，全局极值仅作诊断。
        "height_steady": round(float(np.mean(steady_height)), 3) if steady_height else None,
        "height_steady_ratio": round(float(np.mean(steady_height)) / max(contract.initial_height, 1e-6), 3) if steady_height else None,
        "roll_steady_max_deg": round(max(steady_roll), 1) if steady_roll else None,
        "pitch_steady_max_deg": round(max(steady_pitch), 1) if steady_pitch else None,
    }
    metrics["pass"] = (not metrics["fell"]) and metrics["survival_ratio"] >= 0.999
    return metrics


def _wuji_normalize_positions(model, order, values: np.ndarray) -> np.ndarray:
    """按软限位把给定关节角归一化到 [-1, 1]（center ± 0.9·half）。"""
    import mujoco

    out = np.zeros(len(order), dtype=np.float64)
    for i, name in enumerate(order):
        jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        lo, hi = float(model.jnt_range[jid, 0]), float(model.jnt_range[jid, 1])
        center, half = 0.5 * (lo + hi), 0.5 * (hi - lo) * 0.9
        out[i] = clamp((values[i] - center) / (half + 1e-6), -1.0, 1.0)
    return out


def _wuji_clamp_to_limits(model, order, values: np.ndarray) -> np.ndarray:
    """把关节目标夹到软限位内。"""
    import mujoco

    out = np.array(values, dtype=np.float64)
    for i, name in enumerate(order):
        jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        lo, hi = float(model.jnt_range[jid, 0]), float(model.jnt_range[jid, 1])
        center, half = 0.5 * (lo + hi), 0.5 * (hi - lo) * 0.9
        out[i] = clamp(out[i], center - half, center + half)
    return out


def _wuji_random_quats(rng: np.random.Generator, n: int) -> np.ndarray:
    """均匀采样 SO(3)，wxyz（Shoemake / mjlab random_quat_uniform 等价）。"""
    u1, u2, u3 = rng.random(n), rng.random(n), rng.random(n)
    return np.stack((
        np.sqrt(1 - u1) * np.sin(2 * np.pi * u2),
        np.sqrt(1 - u1) * np.cos(2 * np.pi * u2),
        np.sqrt(u1) * np.sin(2 * np.pi * u3),
        np.sqrt(u1) * np.cos(2 * np.pi * u3),
    ), axis=-1)


def _wuji_ori_error(q_a: np.ndarray, q_b: np.ndarray) -> float:
    dot = abs(float(np.dot(_q_normalize(q_a), _q_normalize(q_b))))
    return 2.0 * math.acos(clamp(dot, -1.0, 1.0))


def run_wuji_reorient(sess, contract: PackageContract, model, data, obs: "ObsBuilder",
                      seconds: float, seed: int, success_threshold: float = 0.2,
                      hold_steps: int = 5, warmup_s: float = 0.4,
                      action_clamp: float = 1.0, ema_alpha: float = 0.5) -> dict[str, Any]:
    """Wuji Hand in-hand 立方体重定向验收：固定基座手 + 自由立方体。

    成功判据（上游 manifest/sim2sim）：朝向误差 < success_threshold 连续 hold_steps 步。
    动作：target = default + clamp(a,-1,1)*scale，EMA(alpha)，warmup 期保持 default。
    掉落判据：立方体相对掌心下落超过 15 cm。
    """
    import mujoco

    rng = np.random.default_rng(seed)
    mujoco.mj_resetDataKeyframe(model, data, 0)
    mujoco.mj_forward(model, data)

    # default 关节角 = 场景 keyframe 的 20 个手关节角
    default = np.zeros(contract.action_dim, dtype=np.float64)
    for i, name in enumerate(contract.action_joint_order):
        default[i] = data.qpos[obs.jadr[name][0]]
    obs.wuji_target = np.zeros(contract.action_dim, dtype=np.float64)
    obs.last_action[:] = 0
    obs.history = []

    palm_id = _wuji_body_id(model, "right_palm_link")
    cube_id = _wuji_body_id(model, "cube")
    palm_quat_w = _q_normalize(np.asarray(data.xquat[palm_id], dtype=np.float64))
    tag_quat_w = _q_normalize(_q_multiply(palm_quat_w, _WUJI_TAG_IN_PALM_QUAT))
    goal_quat_w = _q_normalize(_q_multiply(tag_quat_w, _wuji_random_quats(rng, 1)[0]))
    obs.wuji_goal_quat = goal_quat_w

    cube_h0 = float(data.xpos[cube_id][2])
    palm_h0 = float(data.xpos[palm_id][2])

    total = int(seconds / contract.step_dt)
    prev_target = default.copy()
    hold = 0
    min_err = float("inf")
    success_at = None
    dropped_at = None
    cube_min_h = cube_h0

    for step in range(total):
        if step % contract.decimation == 0:
            o = obs.build(np.zeros(3, dtype=np.float32))
            raw = sess.run(None, {sess.get_inputs()[0].name: o})[0][0]
            raw = np.asarray(raw, dtype=np.float32)[: contract.action_dim]
            obs.last_action = raw.copy()
            # 绝对位置目标 + clamp + EMA + warmup
            scaled = default + np.clip(raw, -action_clamp, action_clamp) * contract.action_scales
            scaled = _wuji_clamp_to_limits(model, contract.action_joint_order, scaled)
            smoothed = ema_alpha * scaled + (1.0 - ema_alpha) * prev_target
            if step * contract.step_dt < warmup_s:
                processed = default.copy()
            else:
                processed = smoothed
            prev_target = processed.copy()
            obs.wuji_target = _wuji_normalize_positions(
                model, contract.action_joint_order, processed
            )
            for i, name in enumerate(contract.action_joint_order):
                aid = actuator_for_joint(model, name)
                if aid >= 0:
                    data.ctrl[aid] = processed[i]

        mujoco.mj_step(model, data)

        cube_pos_w = np.asarray(data.xpos[cube_id], dtype=np.float64)
        cube_quat_w = _q_normalize(np.asarray(data.xquat[cube_id], dtype=np.float64))
        err = _wuji_ori_error(cube_quat_w, goal_quat_w)
        min_err = min(min_err, err)
        cube_min_h = min(cube_min_h, float(cube_pos_w[2]))
        hold = hold + 1 if err < success_threshold else 0
        if success_at is None and hold >= hold_steps:
            success_at = step * contract.step_dt
        if dropped_at is None and (cube_min_h < palm_h0 - 0.15):
            dropped_at = step * contract.step_dt

    return {
        "trial": "wuji_reorient",
        "success": success_at is not None,
        "time_to_success_s": round(success_at, 3) if success_at is not None else None,
        "min_ori_error_rad": round(min_err, 4),
        "final_ori_error_rad": round(_wuji_ori_error(
            _q_normalize(np.asarray(data.xquat[cube_id], dtype=np.float64)), goal_quat_w), 4),
        "dropped": dropped_at is not None,
        "dropped_at_s": round(dropped_at, 3) if dropped_at is not None else None,
        "cube_min_height": round(cube_min_h, 3),
    }


def actuator_for_joint(model, joint_name: str) -> int:
    """按 transmission 关节解析执行器 id。

    机器人包的执行器名常与关节名不同（如 b2 `FR_hip` ↔ 关节 `FR_hip_joint`，
    lite3 `FL_HipX_joint_ctrl` ↔ `FL_HipX_joint`），按名字查会漏配 → ctrl 从不
    写入 → 机器人自由落体。按 `actuator_trnid` 反查与浏览器重建逻辑同源。
    """
    import mujoco

    jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint_name)
    if jid < 0:
        return -1
    for aid in range(model.nu):
        if int(model.actuator_trntype[aid]) == int(mujoco.mjtTrn.mjTRN_JOINT) and int(model.actuator_trnid[aid, 0]) == jid:
            return aid
    return -1


def actuate(contract: PackageContract, model, data, obs: ObsBuilder, raw: np.ndarray) -> None:
    import mujoco

    c = contract
    if c.actuator_interface == "position_target":
        for i, name in enumerate(c.action_joint_order):
            aid = actuator_for_joint(model, name)
            if aid < 0:
                continue
            if c.is_velocity_joint(name):
                # 轮子速度控制（DreamWaQ/rc_mjlab 等）：ctrl = 期望速度 = action × velocity_scale
                data.ctrl[aid] = raw[i] * c.velocity_scale
            else:
                data.ctrl[aid] = raw[i] * c.action_scales[i] + c.default_for(name)
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
        limit = c.gain_for(c.torque_limits, name)
        if limit:
            torque = clamp(torque, -limit, limit)
        aid = actuator_for_joint(model, name)
        if aid >= 0:
            data.ctrl[aid] = torque


# ---------- 主入口 ----------

def default_modes(ranges) -> list[list[float]]:
    """中速验收扫描：站立 + 前进（0.5/0.8×上限）+ 侧移/转向（0.5×上限）。

    用范围上限（如 go1 joystick wz=2π）属边缘工况，不能代表"完成任务"的常态；
    中速扫描更贴合部署指令范围，上限工况作为诊断保留在报告里。
    """
    (vx_lo, vx_hi), (_vy_lo, vy_hi), (_wz_lo, wz_hi) = ranges
    modes = [[0.0, 0.0, 0.0], [float(vx_hi) * 0.5, 0.0, 0.0], [float(vx_hi) * 0.8, 0.0, 0.0]]
    if abs(vy_hi) > 0.01:
        modes.append([0.0, float(vy_hi) * 0.5, 0.0])
    if abs(wz_hi) > 0.01:
        modes.append([0.0, 0.0, float(wz_hi) * 0.5])
    return modes


def apply_actuator_rebuild(spec, package_dir: Path, sim_cfg: dict[str, Any],
                           effort_override: dict[str, float] | None = None) -> bool:
    """镜像后端的浏览器执行器重建（`configure_browser_actuators`），在 MjSpec 上原地改。

    包 XML 常是 `motor`（力矩）执行器，而契约 `actuator_interface=position_target`
    或含 velocity 轮：浏览器按 contract_v3 的 actuator_profile 重建为
    position/velocity/motor 才能动。用 MjSpec 原生 API（保留 meshdir），
    自包含不 import backend/fastapi。无 `browser_actuator_rebuild` 时不动。
    """
    if not sim_cfg.get("browser_actuator_rebuild"):
        return False
    v3_path = package_dir / "contract_v3.json"
    robot_contract_path = package_dir / "contract.json"
    if not v3_path.is_file() or not robot_contract_path.is_file():
        return False
    robot_contract = json.loads(robot_contract_path.read_text(encoding="utf-8-sig"))
    action = robot_contract.get("action") or {}
    order = list(action.get("joint_order") or (robot_contract.get("joints") or {}).get("actuated_joints") or [])
    if not order:
        return False
    try:
        from contracts.role_resolver import RoleResolver

        expanded = RoleResolver(json.loads(v3_path.read_text(encoding="utf-8-sig"))).expand_actuator_profile()
    except Exception:
        return False

    import mujoco

    raw_modes = sim_cfg.get("control_modes") or {}
    control_modes = {str(k).lower(): str(v).lower() for k, v in raw_modes.items()} if isinstance(raw_modes, dict) else {}

    def _is_velocity_joint(name: str) -> bool:
        lowered = name.lower()
        if control_modes.get(lowered) == "velocity":
            return True
        return "wheel" in lowered and control_modes.get("wheel") == "velocity"

    for act in list(spec.actuators):
        spec.delete(act)
    for joint_name in order:
        name = str(joint_name)
        params = expanded.get(name) or {}
        # 逐策略 effort 覆盖：不同训练工程的力矩限幅不同（如 ArenaX 用 45）。
        override = (effort_override or {}).get(name.lower())
        effort = float(override) if override else float(params.get("effort") or 40.0)
        # control_modes 优先：轮子应建成 velocity 执行器，否则位置执行器会吃掉速度目标。
        mode = "velocity" if _is_velocity_joint(name) else str(params.get("mode") or "position")
        act = spec.add_actuator()
        act.name = name if mode != "torque" else name.removesuffix("_joint")
        act.trntype = mujoco.mjtTrn.mjTRN_JOINT
        act.target = name
        act.gear[0] = 1.0
        act.forcelimited = True
        act.forcerange[0], act.forcerange[1] = -effort, effort
        act.gaintype = mujoco.mjtGain.mjGAIN_FIXED
        if mode == "torque":
            act.biastype = mujoco.mjtBias.mjBIAS_NONE
            act.gainprm[0] = 1.0
        elif mode == "velocity":
            kv = float(params.get("damping") or 1.0)
            act.biastype = mujoco.mjtBias.mjBIAS_AFFINE
            act.gainprm[0] = kv
            act.biasprm[2] = -kv
        else:
            kp = float(params.get("stiffness") or 20.0)
            kv = float(params.get("damping") or 1.0)
            act.biastype = mujoco.mjtBias.mjBIAS_AFFINE
            act.gainprm[0] = kp
            act.biasprm[1] = -kp
            act.biasprm[2] = -kv
    return True


def load_package_model(package_dir: Path, sim_cfg: dict[str, Any],
                       effort_override: dict[str, float] | None = None,
                       scene_rel: str | None = None):
    """直接编译 model/robot.xml（meshdir 相对自身目录可解析），并补一块验收平地。

    编译前应用契约的 armature/frictionloss（增量真值，覆盖 XML default），并按需重建
    执行器——训练/验收/浏览器三方消费同一份物理常量。

    ``scene_rel``：改为编译包内某个自包含场景（如 Wuji 的
    simulation/scene_reorient.xml：手 + 立方体 + 地面），不再补验收平地。
    """
    import mujoco

    if scene_rel:
        scene = package_dir / scene_rel
        if not scene.is_file():
            raise SystemExit(f"包内缺少场景: {scene}")
        return mujoco.MjSpec.from_file(str(scene)).compile()

    model_xml = package_dir / "model" / "robot.xml"
    if not model_xml.is_file():
        raise SystemExit(f"包内缺少模型: {model_xml}")
    spec = mujoco.MjSpec.from_file(str(model_xml))
    apply_actuator_rebuild(spec, package_dir, sim_cfg, effort_override)

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


def _swap(arr: np.ndarray, mapping: list[int], reverse: bool = False) -> np.ndarray:
    out = np.zeros_like(arr)
    for i, src in enumerate(mapping):
        if reverse:
            out[src] = arr[i]
        else:
            out[i] = arr[src]
    return out


def _tron1_obs(obs: "ObsBuilder", cmd: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """TRON1 单帧观测 + 缩放命令（参考 tron1-rl-deploy-python controllers）。

    obs = ang_vel*0.25, projected_gravity, joint_pos_rel(isaaclab 序), joint_vel*0.05,
          last_action；点足/足底再拼 gait_clock(2) + gait(4)；轮足 joint_pos 排除轮。
    policy_in = [encoder_out(3), obs, scaled_cmd]。
    """
    c = obs.contract
    spec = c.tron1
    names = c.action_joint_order
    n = len(names)
    _, ang_b, _ = obs.base_state()
    q = obs.data.qpos[3:7]
    q_all = np.array([obs.data.qpos[obs.jadr[x][0]] for x in names], dtype=np.float64)
    dq_all = np.array([obs.data.qvel[obs.jadr[x][1]] for x in names], dtype=np.float64)
    default = np.array([c.default_for(x) for x in names], dtype=np.float64)
    mapping = [int(i) for i in (spec.get("swap") or list(range(n)))]

    jp = (q_all - default) * 1.0
    pos_idx = spec.get("joint_pos_idx")
    if pos_idx:
        jp = jp[[int(i) for i in pos_idx]]
        jp = _swap(jp, [int(i) for i in (spec.get("swap_pos") or mapping)])
    else:
        jp = _swap(jp, mapping)
    dq = _swap(dq_all, mapping) * 0.05
    act = _swap(obs.last_action.astype(np.float64), mapping)
    parts = [ang_b * 0.25, projected_gravity(q), jp, dq, act]
    if spec.get("gait"):
        freq = float(spec.get("gait_freq") or 1.3)
        swing = float(spec.get("gait_swing") or 0.12)
        obs.phase_s = (obs.phase_s + 0.02 * freq) % 1.0
        parts.append(np.array([math.sin(obs.phase_s * 2 * math.pi), math.cos(obs.phase_s * 2 * math.pi)]))
        parts.append(np.array([freq, 0.5, 0.5, swing]))
    frame = np.concatenate(parts).astype(np.float32)
    cmd_scale = np.asarray(spec.get("cmd_scale") or [1.0, 1.0, 1.0], dtype=np.float32)
    scaled_cmd = (np.asarray(cmd, dtype=np.float32) * cmd_scale)[: int(spec.get("cmd_size") or 3)]
    return frame, scaled_cmd


def load_motion_loader(contract: PackageContract, package_dir: Path):
    """按契约的 motion_params.motion_csv 加载参考动作（相对包目录）。"""
    rel = str(contract.motion_params.get("motion_csv") or "")
    if not rel:
        return None
    path = Path(rel)
    if not path.is_absolute():
        path = package_dir / path
    if not path.is_file():
        return None
    try:
        return MotionLoader(path.read_text(encoding="utf-8"), contract.motion_params)
    except Exception:
        return None


def static_stand_height(contract: PackageContract, model, data, obs: ObsBuilder, seconds: float = 1.5) -> float:
    """零动作下用策略默认姿静立得到的参考高度。

    多个策略共享一个包级 `initial_base_height`，但各自默认站姿不同（深蹲/直腿），
    拿包级初高当基准会误杀。以「默认姿静立高度」为基准更稳健。
    """
    import mujoco

    spawn_default(contract, model, data, obs)
    total = int(seconds / contract.step_dt)
    zero = np.zeros(contract.action_dim, dtype=np.float32)
    heights: list[float] = []
    for step in range(total):
        actuate(contract, model, data, obs, zero)
        mujoco.mj_step(model, data)
        if step > total * 0.6:
            heights.append(float(data.qpos[2]))
    return float(np.mean(heights)) if heights else contract.initial_height


def run_encoder_mode(sess_enc, sess_pol, contract: PackageContract, model, data,
                     obs: ObsBuilder, cmd: list[float], seconds: float, seed: int) -> dict[str, Any]:
    """encoder+policy 双会话滚出（TRON1 等）。"""
    import mujoco

    spawn_default(contract, model, data, obs)
    obs.phase_s = 0.0
    obs.last_action[:] = 0
    spec = contract.tron1
    hist = max(1, int(spec.get("history") or 1))
    mapping = [int(i) for i in (spec.get("swap") or list(range(len(contract.action_joint_order))))]
    frame, scaled_cmd = _tron1_obs(obs, cmd)
    buf = np.tile(frame, hist).astype(np.float32)
    enc_in = sess_enc.get_inputs()[0].name
    pol_in = sess_pol.get_inputs()[0].name
    cmd_arr = np.asarray(cmd, dtype=np.float32)

    total = int(seconds / contract.step_dt)
    fell_at = None
    height_min = float("inf")
    roll_max = pitch_max = 0.0
    vel_errs: list[float] = []
    steady_height: list[float] = []
    steady_roll: list[float] = []
    steady_pitch: list[float] = []
    raw = np.zeros(contract.action_dim, dtype=np.float32)

    for step in range(total):
        if step % contract.decimation == 0:
            frame, scaled_cmd = _tron1_obs(obs, cmd)
            buf = np.concatenate([buf[frame.shape[0]:], frame])
            # tron1 的 onnx 输入是 1D [N]（非 [1,N]）
            enc_out = np.asarray(sess_enc.run(None, {enc_in: buf.astype(np.float32)})[0]).reshape(-1)
            pol_input = np.concatenate([enc_out, frame, scaled_cmd]).astype(np.float32)
            raw_lab = np.asarray(sess_pol.run(None, {pol_in: pol_input})[0]).reshape(-1)[: contract.action_dim]
            raw = _swap(raw_lab, mapping, reverse=True).astype(np.float32)  # lab → SDK 序
            obs.last_action = raw.copy()
        actuate(contract, model, data, obs, raw)
        mujoco.mj_step(model, data)

        q = data.qpos[3:7]
        g = projected_gravity(q)
        roll = math.degrees(math.atan2(g[1], -g[2])) if -g[2] > 1e-6 else math.copysign(90.0, g[1])
        pitch = math.degrees(math.asin(clamp(g[0], -1.0, 1.0)))
        roll_max = max(roll_max, abs(roll))
        pitch_max = max(pitch_max, abs(pitch))
        height_min = min(height_min, float(data.qpos[2]))
        if fell_at is None and (data.qpos[2] < 0.45 * contract.initial_height or abs(roll) > 60.0 or abs(pitch) > 60.0):
            fell_at = step * contract.step_dt
            break
        if step > total * 0.7:
            _, ang_b, lin_b = obs.base_state()
            vel_errs.append(float(np.linalg.norm(lin_b[:2] - cmd_arr[:2]) + 0.3 * abs(ang_b[2] - cmd_arr[2])))
            steady_height.append(float(data.qpos[2]))
            steady_roll.append(abs(roll))
            steady_pitch.append(abs(pitch))

    survived = (fell_at / contract.step_dt) if fell_at is not None else total
    metrics = {
        "command": [float(x) for x in cmd],
        "fell": fell_at is not None,
        "fell_at_s": round(fell_at, 3) if fell_at is not None else None,
        "survival_ratio": round(survived / total, 3),
        "vel_track_err": round(float(np.mean(vel_errs)), 3) if vel_errs else None,
        "height_min": round(height_min, 3),
        "height_steady": round(float(np.mean(steady_height)), 3) if steady_height else None,
        "height_steady_ratio": round(float(np.mean(steady_height)) / max(contract.initial_height, 1e-6), 3) if steady_height else None,
        "roll_max_deg": round(roll_max, 1),
        "pitch_max_deg": round(pitch_max, 1),
        "roll_steady_max_deg": round(max(steady_roll), 1) if steady_roll else None,
        "pitch_steady_max_deg": round(max(steady_pitch), 1) if steady_pitch else None,
    }
    metrics["pass"] = (not metrics["fell"]) and metrics["survival_ratio"] >= 0.999
    return metrics


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

    sim_cfg = json.loads((package_dir / "simulation" / "config.json").read_text(encoding="utf-8-sig"))
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
    sess_enc = None
    if contract.encoder_rel:
        enc_path = Path(contract.encoder_rel)
        if not enc_path.is_absolute():
            enc_path = package_dir / enc_path
        sess_enc = ort.InferenceSession(str(enc_path), providers=["CPUExecutionProvider"])
    else:
        in_shape = sess.get_inputs()[0].shape
        if contract.total_obs_dim and in_shape[-1] != contract.total_obs_dim:
            raise SystemExit(
                f"ONNX 输入维度 {in_shape} 与契约 {contract.total_obs_dim}"
                f"（obs_dim {contract.obs_dim} × history {contract.history_len}）不符"
            )

    modes = [[float(x) for x in m.split(",")] for m in args.modes] if args.modes else default_modes(contract.cmd_ranges)

    model_results = []
    for idx, cmd in enumerate(modes):
        obs = ObsBuilder(contract, model, data)
        if sess_enc is not None:
            metrics = run_encoder_mode(sess_enc, sess, contract, model, data, obs, cmd, args.seconds, args.seed + idx)
        else:
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
