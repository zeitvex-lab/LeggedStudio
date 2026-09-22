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
import re
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


def quat_to_euler_xyz(q) -> list[float]:
    """四元数 (w,x,y,z) → XYZ Tait-Bryan 欧拉 [roll, pitch, yaw]。

    与 web/sim2sim/utils.js::quatToRpy 逐式一致（LainLab gait 帧的 euler_xyz 段
    = mjlab root_link_quat_w 的 xyz euler，即浏览器 IMU rpy），约定/符号不得漂移。
    """
    w, x, y, z = (float(v) for v in q)
    roll = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    sinp = 2 * (w * y - z * x)
    pitch = math.copysign(math.pi / 2, sinp) if abs(sinp) >= 1 else math.asin(sinp)
    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return [roll, pitch, yaw]


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
        # B3 收尾（2026-09-13 续五）：这两个键**已从 simulation/config.json 移除**，
        # 继续读 ``self.sim`` 会静默回落 200 / 4，而模型 timestep 已按契约设成 1/500 →
        #   ① 探针 ``total = seconds * physics_hz`` 少跑 60%（声明 3 s 实跑 1.2 s）；
        #   ② 策略刷新 ``step % decimation`` 变成每 4 步 = 125 Hz（契约是每 10 步 = 50 Hz）。
        # 两者都会**静默改变验收结论**，与 armature 那次是同一类问题：改走契约真值 单一真值。
        from contracts.physics_binding import physics_scalars

        scalars = physics_scalars(package_dir)
        self.physics_hz = float(scalars.get("physics_hz") or self.sim.get("physics_hz") or 200)
        self.decimation = int(scalars.get("decimation") or self.sim.get("decimation") or 4)
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
        # B25（2026-09-16）：worker 训练链从不携带策略条目（``config["policy"]`` 恒缺位），
        # 而包级 policy_contract 只在 g1/go2w/zex-w/tron1 声明了维度——microduck/go1/go2
        # 的维度只在 ``policies[]`` 各条目顶层。条目缺位时 action_dim 落 0，但动作关节序
        # 已从机器人级 contract.json 回退到位，``run_probe`` 拿空动作数组按关节序取
        # ``raw[0]`` → 裸 IndexError。动作槽与关节序语义同源（逐关节一个动作槽），未声明
        # 时按关节序派生；已声明的值仍是唯一真值，不做静默改写。
        if not self.action_dim:
            self.action_dim = len(self.action_joint_order)
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
        # 历史**初值**约定 —— 两种上游语义确有差异，必须由契约声明，不能默认：
        #   repeat_first（默认）= 用首帧重复预热（LeggedSkillDeploy / HIMLoco 的
        #     `ObservationBuffer.reset` 语义，见 web/sim2sim/app.js::buildPolicyObs）；
        #   zero = 历史缓冲清零（robot_lab `source/rsl_rl/rsl_rl/utils/exporter_cts.py`
        #     的 `reset()` 里 `obs_history.zero_()`）。
        # 用错会让历史型策略开局就拿到一段"假历史"。
        self.history_init = str(self.contract.get("history_init") or "repeat_first")
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

    def effective_command(self, cmd) -> np.ndarray:
        """策略**实际收到**的速度指令（obs 构建器内部会乘的那一层缩放）。

        观测构建器把 ``cmd`` 乘上命令缩放后再喂给网络：TRON1 走
        ``tron1.cmd_scale``（部署 user_cmd_scales），其余机型走 ``scales.command``。
        跟踪误差必须与这个值比较，否则指令缩放 ≠ 1 的机型会被判成「跟踪不合格」，
        且缺口恰好等于缩放倍率（TRON1 的 1.5 倍就是这么来的）。
        """
        spec = self.tron1 or {}
        if not spec:
            # 其余机型 scales.command 是「观测归一化」而非单位换算，用户指令即 m/s。
            return np.asarray(cmd, dtype=np.float32)
        scale = spec.get("cmd_scale") or [1.0, 1.0, 1.0]
        dims = int(spec.get("cmd_size") or 3)
        arr = np.asarray(cmd, dtype=np.float32) * np.asarray(scale, dtype=np.float32)
        return arr[:dims]

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


def _frame_go2_mjlab_actor_48(obs: "ObsBuilder", cmd: np.ndarray) -> list[float]:
    """mjlab velocity actor 组单帧 48：lin_vel, ang_vel, gravity, q_rel(12), dq(12), action(12), cmd。

    2026-09-18 B11 规模档质量评测新增：L7 产品自产策略（go2-velocity-flat profile）按
    mjlab `make_velocity_env_cfg` 的 actor 组训练 —— training.log ObservationManager 表
    逐项序 = base_lin_vel, base_ang_vel, projected_gravity, joint_pos, joint_vel, actions,
    command（48 维），且各 term 无 scale（mjlab ObservationTermCfg 默认 1.0）；命令 term 在
    **帧尾**。ONNX metadata_props 的 default_joint_pos / action_scale（逐关节）与
    clip_actions=100 是部署侧真值（由 onnx_exporter.attach_metadata_to_onnx 盖章）。
    """
    c = obs.contract
    _, ang_b, lin_b = obs.base_state()
    q = obs.data.qpos[3:7]
    order = c.action_joint_order
    out = list(lin_b)
    out += list(ang_b * c.ang_vel_scale)
    out += list(projected_gravity(q))
    out += [(obs.data.qpos[obs.jadr[n][0]] - c.default_for(n)) * c.dof_pos_scale for n in order]
    out += [obs.data.qvel[obs.jadr[n][1]] * c.dof_vel_scale for n in order]
    out += list(obs.last_action)
    out += list(cmd * np.asarray(c.cmd_scale))
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


# LainLab playground 技能族（2026-09-20 入库）——trot/jump 共用的 47 维单帧。
# 逐字对齐 web/sim2sim/obs/observation_builders.js::buildLainlabGaitObservation。
# **缩放用字面量**（训练源即真值，与 JS 同）：该契约未声明 scales，若走
# c.ang_vel_scale/c.dof_pos_scale/c.cmd_scale 会全部回落 1.0，与训练时不一致。
# 布局（47）：[sin(2π·phase), cos(2π·phase), cmd_x·2, cmd_y·2, cmd_w·0.25]（5）
#   + ang_vel(body)·0.25（3）+ euler_xyz（3）+ (q−default)（12）+ dq·0.05（12）+ action（12）。
# 相位 = (真实 sim.data.time mod gait_period_s) / gait_period_s；data.time 每物理步
# 推进、mj_resetData 归零 ⇒ 复位即清相位来源，无需额外累积器。sin/cos 用 2π·归一化
# 相位（不是把 0..1 周期当弧度）。gravity 段该帧不含（用 euler 表姿态）。
def _frame_lainlab_gait_47(obs: "ObsBuilder", cmd: np.ndarray) -> list[float]:
    c = obs.contract
    _, ang_b, _ = obs.base_state()
    quat = obs.data.qpos[3:7]
    period = c.gait_period if c.gait_period > 0 else 0.5
    phase = (float(obs.data.time) % period) / period
    order = c.action_joint_order
    angle = 2.0 * math.pi * phase
    out = [math.sin(angle), math.cos(angle)]
    out += [float(cmd[0]) * 2.0, float(cmd[1]) * 2.0, float(cmd[2]) * 0.25]
    out += [float(ang_b[i]) * 0.25 for i in range(3)]
    out += quat_to_euler_xyz(quat)
    out += [obs.data.qpos[obs.jadr[n][0]] - c.default_for(n) for n in order]
    out += [obs.data.qvel[obs.jadr[n][1]] * 0.05 for n in order]
    out += [float(a) for a in obs.last_action]
    return out


FRAME_BUILDERS = {
    "go2_rl_sdk_45": _std_frame,
    "go2_mjlab_actor_48": _frame_go2_mjlab_actor_48,
    "lainlab_gait_47_hist10": _frame_lainlab_gait_47,
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
    if c.history_layout in ("frame_major", "frame_major_oldest_first"):
        # 整帧依时序拼接、最老帧在前、当前帧在最后。`frame_major_oldest_first` 是
        # LainLab 技能族（trot/jump 470 等）在契约里显式声明的同语义别名（ONNX 图首
        # 个 Slice 为 [0:-obs_dim]，encoder 吃前段历史、actor MLP 吃末帧），与
        # web/sim2sim/app.js::packObsHistoryByTerm 完全一致。
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
        # 预热填充按契约的 `history_init` 约定：`zero` 用零帧，默认用首帧重复。
        frames.insert(0, np.zeros_like(frames[0]) if c.history_init == "zero" else frames[0])
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

    total = int(seconds * contract.physics_hz)
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
        # 迭代 = 一个物理步；策略每 decimation 步刷新一次（与浏览器/训练同频）。
        actuate(contract, model, data, obs, raw)
        mujoco.mj_step(model, data)

        q = data.qpos[3:7]
        g = projected_gravity(q)
        roll = math.degrees(math.atan2(g[1], -g[2])) if -g[2] > 1e-6 else math.copysign(90.0, g[1])
        pitch = math.degrees(math.asin(clamp(g[0], -1.0, 1.0)))
        roll_max = max(roll_max, abs(roll))
        pitch_max = max(pitch_max, abs(pitch))
        height_min = min(height_min, float(data.qpos[2]))
        # 倾角闸门放到 90°：**前腿/后腿站立**这类非标准站姿本来就会把躯干立起来
        # （实测 go2w 后腿站立 pitch 80.5° 是正常姿态，60° 会把它误判成摔倒并中止回合）。
        # 阈值只用于"回合是否该中止"，姿态是否合格仍由 verdict 的 tilt 判据决定。
        tilted = abs(roll) > 90.0 or abs(pitch) > 90.0
        # **起摆窗口**：从出生高度落到站立高度是**正常过程**（go2 出生 0.445、站高约 0.28），
        # 单帧穿过 `0.45 × initial_height` 就判"摔倒"，会把还没机会发动作的策略直接掐掉
        # （实测 go2-moe-cts 0.248 s、g1-velocity 0.35 s 都是这么被中止的）。
        settle_steps = int(0.5 * contract.physics_hz)
        if fell_at is None and step >= settle_steps and (
            data.qpos[2] < 0.45 * contract.initial_height or tilted
        ):
            fell_at = step / contract.physics_hz
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

    survived_steps = (fell_at * contract.physics_hz) if fell_at is not None else total
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

    total = int(seconds * contract.physics_hz)
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
            if step / contract.physics_hz < warmup_s:
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
        # hold_steps 以控制步计（与策略频率一致），迭代本身是物理步。
        if step % contract.decimation == 0:
            hold = hold + 1 if err < success_threshold else 0
        if success_at is None and hold >= hold_steps:
            success_at = step / contract.physics_hz
        if dropped_at is None and (cube_min_h < palm_h0 - 0.15):
            dropped_at = step / contract.physics_hz

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


# ---------- PIE 深度跑酷（多输入 + GRU memory + 深度相机） ----------
#
# 上游 00_resources/parkour_mjlab deploy/pie/sim2sim（Unitree-Go2-PIE）：
#   proprio(45) + proprio_history(10×45, term-major 旧→新) + depth_history(2×60×86)
#   + memory_h(1×128 GRU 状态) → actions(12) + memory_h_out。
# 深度：60×106 相机（fovy 由 HFOV 87° 反解），光学 Z → 裁剪 10px/侧 → 3×3 高斯 →
# 裁剪[0.05,3]→/3。本机无 GL，改用 raycast 合成光学 Z（与 renderer 口径一致）。

_PIE_DEFAULT_JOINT_POS = np.array([-0.1, 0.9, -1.8] * 4, dtype=np.float64)
_PIE_ACTION_SCALE = 0.25
_PIE_TERM_DIMS = (3, 3, 3, 12, 12, 12)
_PIE_PROPRIO_DIM = 45
_PIE_HISTORY_LEN = 10
_PIE_DEPTH_RAW_W = 106
_PIE_DEPTH_H = 60
_PIE_DEPTH_CROP = 10
_PIE_DEPTH_W = _PIE_DEPTH_RAW_W - 2 * _PIE_DEPTH_CROP
_PIE_DEPTH_HISTORY = 2
_PIE_DEPTH_MIN = 0.05
_PIE_DEPTH_MAX = 3.0
_PIE_DEPTH_UPDATE_STEPS = 5
_PIE_CONTROL_DT = 0.02
_PIE_PHYSICS_STEPS = 4
_PIE_CAM_POS = np.array((0.345, 0.0, 0.07), dtype=np.float64)
_PIE_CAM_QUAT = np.array((0.5792280, 0.4055798, -0.4055798, -0.5792280), dtype=np.float64)
_PIE_DEPTH_FOVY_DEG = math.degrees(2.0 * math.atan(
    math.tan(math.radians(87.0) * 0.5) * _PIE_DEPTH_H / _PIE_DEPTH_RAW_W))
_PIE_GAUSSIAN = np.array((
    (0.07511361, 0.12384140, 0.07511361),
    (0.12384140, 0.20417996, 0.12384140),
    (0.07511361, 0.12384140, 0.07511361),
), dtype=np.float32)
_PIE_GAUSSIAN /= _PIE_GAUSSIAN.sum()


def _pie_ray_dirs():
    """相机坐标系下的逐像素射线方向（单位向量）与 z→ray 缩放。

    相机系口径：**−z 是光轴、+x 朝图像右、+y 朝图像上**；帧数组行优先、行 0 = 图像顶部。
    依据（实证，见 web/sim2sim/sensors/screen_frame.js 头部）：mujoco.Renderer.render 对
    EGL/OSMesa 后端显式 ``np.flipud``（行 0 = 顶）＋ 右手系定理（"+x 右 + y 下"是左手系，
    任何旋转都造不出来）＋ 上游 PIE 相机四元数只有在这个口径下才是正立图像。
    于是行 0 在上 ⇒ y 分量取 −py；列 0 在左 ⇒ x 分量取 **+px**。

    2026-09-22 修：x 分量此前是 −px ⇒ 策略（以及本引擎的验收结论）吃到的是**左右镜像**
    的深度图。浏览器侧同一实现 ``web/sim2sim/pie_depth.js`` 同步修正——两处必须逐值同口径，
    否则"浏览器里跑得动、验收里跑不动"这类分裂无从判断。
    """
    focal = 0.5 * _PIE_DEPTH_H / math.tan(0.5 * math.radians(_PIE_DEPTH_FOVY_DEG))
    px = (np.arange(_PIE_DEPTH_RAW_W, dtype=np.float64) + 0.5 - 0.5 * _PIE_DEPTH_RAW_W) / focal
    py = (np.arange(_PIE_DEPTH_H, dtype=np.float64) + 0.5 - 0.5 * _PIE_DEPTH_H) / focal
    scale = np.sqrt(1.0 + py[:, None] ** 2 + px[None, :] ** 2)
    dirs = np.stack((px[None, :].repeat(_PIE_DEPTH_H, 0),
                     -py[:, None].repeat(_PIE_DEPTH_RAW_W, 1),
                     -np.ones((_PIE_DEPTH_H, _PIE_DEPTH_RAW_W))), axis=-1)
    dirs /= np.linalg.norm(dirs, axis=-1, keepdims=True)
    return dirs, scale


_PIE_RAY_DIRS, _PIE_Z_TO_RAY = _pie_ray_dirs()


def _pie_preprocess_depth_z(depth_z: np.ndarray) -> np.ndarray:
    """原生光学-Z 图像 → 单帧 PIE 深度（裁剪/高斯/裁剪/归一化）。"""
    depth = np.asarray(depth_z, dtype=np.float32)
    invalid = ~np.isfinite(depth) | (depth <= 0.0)
    ray_depth = depth * _PIE_Z_TO_RAY
    ray_depth[invalid] = _PIE_DEPTH_MAX
    ray_depth = ray_depth[:, _PIE_DEPTH_CROP:_PIE_DEPTH_RAW_W - _PIE_DEPTH_CROP]
    padded = np.pad(ray_depth, ((1, 1), (1, 1)), mode="reflect")
    windows = np.lib.stride_tricks.sliding_window_view(padded, (3, 3))
    blurred = np.einsum("ijxy,xy->ij", windows, _PIE_GAUSSIAN, optimize=True)
    normalized = np.clip(blurred, _PIE_DEPTH_MIN, _PIE_DEPTH_MAX) / _PIE_DEPTH_MAX
    return np.ascontiguousarray(normalized[None, :, :], dtype=np.float32)


def _pie_capture_depth_z(model, data, base_id: int) -> np.ndarray:
    """raycast 合成相机光学-Z（60×106）。无 GL 环境下替代 mujoco.Renderer 深度。"""
    import mujoco

    base_pos = np.asarray(data.xpos[base_id], dtype=np.float64)
    base_quat = _q_normalize(np.asarray(data.xquat[base_id], dtype=np.float64))
    rot = _q_to_matrix(base_quat).reshape(3, 3)
    cam_pos = base_pos + rot @ _PIE_CAM_POS
    cam_rot = rot @ _q_to_matrix(_q_normalize(_q_multiply(base_quat, _PIE_CAM_QUAT))).reshape(3, 3)
    world_dirs = _PIE_RAY_DIRS @ cam_rot.T  # (H,W,3) 行向量右乘 R^T
    depth = np.full((_PIE_DEPTH_H, _PIE_DEPTH_RAW_W), _PIE_DEPTH_MAX, dtype=np.float64)
    gid = np.array([-1], dtype=np.int32)
    ray = mujoco.mj_ray
    for v in range(_PIE_DEPTH_H):
        for u in range(_PIE_DEPTH_RAW_W):
            gid[0] = -1
            dist = ray(model, data, cam_pos, world_dirs[v, u], None, 1, -1, gid)
            if dist > 0.0 and dist <= _PIE_DEPTH_MAX * 1.5:
                depth[v, u] = dist / _PIE_Z_TO_RAY[v, u]
    return depth


def _pie_proprio(obs: "ObsBuilder", cmd: np.ndarray) -> np.ndarray:
    _, ang_b, _ = obs.base_state()
    q = obs.data.qpos[3:7]
    order = obs.contract.action_joint_order
    out = list(ang_b) + list(projected_gravity(q)) + list(np.asarray(cmd, dtype=np.float64)[:3])
    out += [obs.data.qpos[obs.jadr[n][0]] - _PIE_DEFAULT_JOINT_POS[i] for i, n in enumerate(order)]
    out += [obs.data.qvel[obs.jadr[n][1]] for n in order]
    out += list(obs.last_action)
    return np.asarray(out, dtype=np.float32)


class _PieProprioHistory:
    """term-major、旧→新的 10 帧 45 维本体历史（对齐 mjlab CircularBuffer 拼接）。"""

    def __init__(self) -> None:
        self.frames: list[np.ndarray] = []

    def reset(self) -> None:
        self.frames = []

    def append(self, frame: np.ndarray) -> None:
        f = np.asarray(frame, dtype=np.float32).reshape(_PIE_PROPRIO_DIM)
        if not self.frames:
            self.frames = [f.copy() for _ in range(_PIE_HISTORY_LEN)]
        else:
            self.frames.append(f.copy())
            if len(self.frames) > _PIE_HISTORY_LEN:
                self.frames = self.frames[-_PIE_HISTORY_LEN:]

    @property
    def array(self) -> np.ndarray:
        stack = np.stack(self.frames, axis=0)
        chunks, start = [], 0
        for dim in _PIE_TERM_DIMS:
            chunks.append(stack[:, start:start + dim].reshape(-1))
            start += dim
        return np.ascontiguousarray(np.concatenate(chunks).astype(np.float32))


class _PieDepthHistory:
    def __init__(self) -> None:
        self.frames: list[np.ndarray] = []

    def reset(self) -> None:
        self.frames = []

    def append(self, frame: np.ndarray) -> None:
        f = np.asarray(frame, dtype=np.float32).reshape(1, _PIE_DEPTH_H, _PIE_DEPTH_W)
        if not self.frames:
            self.frames = [f.copy() for _ in range(_PIE_DEPTH_HISTORY)]
        else:
            self.frames.append(f.copy())
            if len(self.frames) > _PIE_DEPTH_HISTORY:
                self.frames = self.frames[-_PIE_DEPTH_HISTORY:]

    @property
    def array(self) -> np.ndarray:
        return np.ascontiguousarray(np.concatenate(self.frames, axis=0).astype(np.float32))


def _pie_body_id(model, name: str) -> int:
    import mujoco

    bid = int(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name))
    if bid < 0:
        for b in range(model.nbody):
            if mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, b) == name:
                return b
    return bid


def run_pie_policy(sess, contract: PackageContract, model, data, obs: "ObsBuilder",
                   cmd: list[float], seconds: float, seed: int,
                   base_body: str = "base") -> dict[str, Any]:
    """PIE 控制回路：50Hz 控制 / 4 物理步；深度每 5 控制步更新；GRU memory 逐步回灌。"""
    import mujoco

    spawn_default(contract, model, data, obs)
    # 关节初始姿态对齐 PIE 默认角
    for i, name in enumerate(contract.action_joint_order):
        data.qpos[obs.jadr[name][0]] = _PIE_DEFAULT_JOINT_POS[i]
    mujoco.mj_forward(model, data)

    base_id = _pie_body_id(model, base_body)
    cmd_arr = np.asarray(cmd, dtype=np.float32)[:3]
    history = _PieProprioHistory()
    depths = _PieDepthHistory()
    obs.last_action = np.zeros(contract.action_dim, dtype=np.float32)
    memory = np.zeros((1, 1, 128), dtype=np.float32)
    in_names = [i.name for i in sess.get_inputs()]

    control_steps = int(seconds / _PIE_CONTROL_DT)
    start_xy = np.asarray(data.xpos[base_id], dtype=np.float64)[:2].copy()
    fell_at = None
    tilt_max = 0.0
    forward_max = 0.0
    height_min = float("inf")
    depth_frames = 0

    for step in range(control_steps):
        if step % _PIE_DEPTH_UPDATE_STEPS == 0:
            depths.append(_pie_preprocess_depth_z(_pie_capture_depth_z(model, data, base_id)))
            depth_frames += 1
        proprio = _pie_proprio(obs, cmd_arr)
        history.append(proprio)
        feeds = {
            "proprio": proprio.reshape(1, -1),
            "proprio_history": history.array.reshape(1, -1),
            "depth_history": depths.array.reshape(1, _PIE_DEPTH_HISTORY, _PIE_DEPTH_H, _PIE_DEPTH_W),
            "memory_h_in": memory,
        }
        feeds = {k: v for k, v in feeds.items() if k in in_names}
        outs = sess.run(None, feeds)
        action = np.asarray(outs[0], dtype=np.float32).reshape(-1)
        obs.last_action = action.copy()
        memory = np.asarray(outs[1], dtype=np.float32) if len(outs) > 1 else memory
        # 复用通用 actuate：位置目标 = default + action_scale*action；torque 接口按 kp/kd 求力矩
        actuate(contract, model, data, obs, action)
        for _ in range(_PIE_PHYSICS_STEPS):
            mujoco.mj_step(model, data)

        q = data.qpos[3:7]
        g = projected_gravity(q)
        roll = math.degrees(math.atan2(g[1], -g[2])) if -g[2] > 1e-6 else math.copysign(90.0, g[1])
        pitch = math.degrees(math.asin(clamp(g[0], -1.0, 1.0)))
        tilt_max = max(tilt_max, abs(roll), abs(pitch))
        height_min = min(height_min, float(data.qpos[2]))
        forward = float(np.asarray(data.xpos[base_id], dtype=np.float64)[0] - start_xy[0])
        forward_max = max(forward_max, forward)
        if fell_at is None and (data.qpos[2] < 0.5 * contract.initial_height or max(abs(roll), abs(pitch)) > 75.0):
            fell_at = step * _PIE_CONTROL_DT
            break

    survived = (fell_at / _PIE_CONTROL_DT) if fell_at is not None else control_steps
    return {
        "command": [float(x) for x in cmd_arr],
        "fell": fell_at is not None,
        "fell_at_s": round(fell_at, 3) if fell_at is not None else None,
        "survival_ratio": round(survived / control_steps, 3),
        "tilt_max_deg": round(tilt_max, 1),
        "forward_max_m": round(forward_max, 3),
        "height_min": round(height_min, 3),
        "depth_frames": depth_frames,
    }


# ---------- mjswan 多输入 RNN 回路（槽表：actor / is_init / adapt_hx / command_）----------

#: 上游 mjswan demo 的 `control_dt`（50 Hz 控制步）；物理子步数按契约 `physics_hz` 推。
_MJSWAN_CONTROL_DT = 0.02
#: actor 各 term 的 (名, 维度, 是否 element-major 交错)，顺序 = 上游 `go2_velocity_obs["actor"]`；
#: 维度 0 = 随 `action_dim`（关节项）。实测该组**无 command、无 base_ang_vel、各 term scale=1.0**。
_MJSWAN_ACTOR_TERMS: tuple[tuple[str, int, bool], ...] = (
    ("projected_gravity", 3, False),
    ("joint_pos_rel", 0, False),
    ("joint_vel_rel", 0, False),
    ("last_action", 0, True),
)
#: 上游 `history_steps=(0,1,2)`：**新→旧**（dense `history_length` 才是旧→新，别搞混）。
_MJSWAN_HISTORY_STEPS = 3
#: `command_` 槽 = velocity_cmd(3) + 13 个零（oscillator 槽位占位，上游 `velocity_command_padding`）。
_MJSWAN_COMMAND_PAD = 13
#: 循环隐状态宽度（上游 `adapt_hx`）。
_MJSWAN_RECURRENT_DIM = 128
#: 上游 `out_keys` 里这两项的位置，robust/vanilla/facet 三个导出件**实测一致**（15/16 个输出里）。
_MJSWAN_ACTION_OUTPUT = 10  # 见下：部署取均值时改用 7
_MJSWAN_RECURRENT_OUTPUT = 4


def _mjswan_actor_frame(obs: "ObsBuilder") -> np.ndarray:
    """单帧 actor（**无缩放**）：projected_gravity(3) + joint_pos_rel(A) + joint_vel(A) + last_action(A)。"""
    c = obs.contract
    q = obs.data.qpos[3:7]
    out = [float(v) for v in projected_gravity(q)]
    out += [float(obs.data.qpos[obs.jadr[n][0]] - c.default_for(n)) for n in c.action_joint_order]
    out += [float(obs.data.qvel[obs.jadr[n][1]]) for n in c.action_joint_order]
    out += [float(v) for v in obs.last_action]
    return np.asarray(out, dtype=np.float32)


class _MjswanActorHistory:
    """`history_steps=(0,1,2)` 的 actor 历史：逐 term 堆叠、**新→旧**，`last_action` 交错。

    逐值口径（唯一真值 = 上游 `HistoryObservation.ts`，两份实现必须一致——这类"差一步"不抛异常）：
      · 非交错项：按 offset 序整段铺 ⇒ `[g_t(3), g_{t-1}(3), g_{t-2}(3)]`；
      · 交错项（element-major）：**每个元素自己的几帧相邻** ⇒ `[a_t[0],a_{t-1}[0],a_{t-2}[0], a_t[1], …]`；
      · reset 后首帧**填满每一槽**（`needsPrime`：不许把未训练的零当历史）。
    """

    def __init__(self, frame_dim: int, action_dim: int) -> None:
        self._frame_dim = int(frame_dim)
        self._action_dim = int(action_dim)
        self._frames: list[np.ndarray] = []

    def reset(self) -> None:
        self._frames = []

    def append(self, frame: np.ndarray) -> None:
        f = np.asarray(frame, dtype=np.float32).reshape(self._frame_dim)
        if not self._frames:
            self._frames = [f.copy() for _ in range(_MJSWAN_HISTORY_STEPS)]
        else:
            self._frames = [f.copy(), *self._frames[: _MJSWAN_HISTORY_STEPS - 1]]

    @property
    def array(self) -> np.ndarray:
        chunks: list[float] = []
        offset = 0
        for _name, dim, interleaved in _MJSWAN_ACTOR_TERMS:
            width = dim or self._action_dim
            if interleaved:
                for j in range(width):
                    for frame in self._frames:
                        chunks.append(float(frame[offset + j]))
            else:
                for frame in self._frames:
                    chunks.extend(float(v) for v in frame[offset : offset + width])
            offset += width
        return np.asarray(chunks, dtype=np.float32)


def run_mjswan_policy(sess, contract: PackageContract, model, data, obs: "ObsBuilder",
                      cmd: list[float], seconds: float, seed: int,
                      base_body: str = "base",
                      slots: tuple[str, ...] | None = None) -> dict[str, Any]:
    """mjswan 四输入 RNN 回路（50 Hz 控制）：`actor` / `is_init` / `adapt_hx` / `command_`。

    **输入按槽表位置喂**（上游 ADR 0006 §5：onnx 自己的张量名无意义、`l_kwargs_*` 只是导出器
    产物名），槽表顺序来自契约；`adapt_hx` 回灌上一步输出（索引 4 的 `[next,adapt_hx]`），
    `is_init` 只在 episode 首帧为真（**bool** 张量，喂 float 会直接被 onnxruntime 拒），
    `command_` = 命令 3 维 + 13 个零占位。动作不额外 clip（上游 `clip_actions` 取 rsl-rl 包装器
    的默认 100，实际不起作用）。判据口径与 PIE 回路一致（存活/姿态/前进），便于同报告比较。
    """
    import mujoco

    slots = tuple(slots or ("actor", "is_init", "adapt_hx", "command_"))
    in_names = [str(i.name) for i in sess.get_inputs()]
    if len(in_names) != len(slots):
        raise ValueError(
            f"槽表与网络输入数不符：声明 {list(slots)}（{len(slots)} 路）"
            f" vs onnx {in_names}（{len(in_names)} 路）——按位置映射，多一路少一路都是错绑"
        )

    spawn_default(contract, model, data, obs)
    # 关节初始姿态对齐**策略默认角**（上游 `default_joint_pos` = 包内契约的 default_joint_angles）。
    # 与 PIE 回路同一步：不对齐的话策略从一个它没训过的姿态起步，表现为"站得住但不走/偶发摔"。
    for name in contract.action_joint_order:
        data.qpos[obs.jadr[name][0]] = contract.default_for(name)
    mujoco.mj_forward(model, data)
    base_id = _pie_body_id(model, base_body)
    cmd_arr = np.asarray(cmd, dtype=np.float32)[:3]
    cmd_scale = np.asarray(contract.cmd_scale, dtype=np.float32)
    physics_steps = max(1, int(round(_MJSWAN_CONTROL_DT * float(contract.physics_hz))))
    control_steps = max(1, int(float(seconds) / _MJSWAN_CONTROL_DT))

    obs.last_action = np.zeros(contract.action_dim, dtype=np.float32)
    history = _MjswanActorHistory(3 + 3 * contract.action_dim, contract.action_dim)
    hx = np.zeros((1, _MJSWAN_RECURRENT_DIM), dtype=np.float32)
    start_xy = np.asarray(data.xpos[base_id], dtype=np.float64)[:2].copy()
    fell_at: float | None = None
    tilt_max = 0.0
    forward_max = 0.0
    height_min = float("inf")

    for step in range(control_steps):
        history.append(_mjswan_actor_frame(obs))
        values = {
            "actor": history.array.reshape(1, -1),
            # rank 必须与 onnx 一致（`arg1` 是 [1] 一维 bool；喂 [[.]] 会被 onnxruntime 判
            # "Invalid rank for input: arg1 Got: 2 Expected: 1" —— 实测踩过）。
            "is_init": np.asarray([step == 0], dtype=bool),
            "adapt_hx": hx,
            "command_": np.concatenate(
                [cmd_arr * cmd_scale, np.zeros(_MJSWAN_COMMAND_PAD, dtype=np.float32)]
            ).reshape(1, -1),
        }
        outs = sess.run(None, {in_names[i]: values[slot] for i, slot in enumerate(slots)})
        action = np.asarray(outs[_MJSWAN_ACTION_OUTPUT], dtype=np.float32).reshape(-1)[: contract.action_dim]
        hx = np.asarray(outs[_MJSWAN_RECURRENT_OUTPUT], dtype=np.float32).reshape(1, _MJSWAN_RECURRENT_DIM)
        obs.last_action = action.copy()
        # 位置目标 = default + action_scale*action（与 PIE/通用路径同一份 actuate）。
        actuate(contract, model, data, obs, action)
        for _ in range(physics_steps):
            mujoco.mj_step(model, data)

        q = data.qpos[3:7]
        g = projected_gravity(q)
        roll = math.degrees(math.atan2(g[1], -g[2])) if -g[2] > 1e-6 else math.copysign(90.0, g[1])
        pitch = math.degrees(math.asin(clamp(g[0], -1.0, 1.0)))
        tilt_max = max(tilt_max, abs(roll), abs(pitch))
        height_min = min(height_min, float(data.qpos[2]))
        forward = float(np.asarray(data.xpos[base_id], dtype=np.float64)[0] - start_xy[0])
        forward_max = max(forward_max, forward)
        if fell_at is None and (data.qpos[2] < 0.5 * contract.initial_height or max(abs(roll), abs(pitch)) > 75.0):
            fell_at = step * _MJSWAN_CONTROL_DT
            break

    survived = (fell_at / _MJSWAN_CONTROL_DT) if fell_at is not None else control_steps
    return {
        "command": [float(x) for x in cmd_arr],
        "fell": fell_at is not None,
        "fell_at_s": round(fell_at, 3) if fell_at is not None else None,
        "survival_ratio": round(survived / control_steps, 3),
        "tilt_max_deg": round(tilt_max, 1),
        "forward_max_m": round(forward_max, 3),
        "height_min": round(height_min, 3),
        "slots": list(slots),
    }


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


_XML_ATTR_RE = re.compile(r'([A-Za-z_][\w]*)\s*=\s*"([^"]*)"')
_FLOOR_GEOM_RE = re.compile(r'<geom\b([^>]*?)/?>')


def scene_physics_overrides(package_dir: Path, sim_cfg: dict[str, Any]):
    """从包内 ``simulation/scene.xml`` 提取地板摩擦（``<option>`` 搬运已于 2026-09-13 退役）。

    **历史**：浏览器加载 ``simulation/scene.xml``，验收器只编译 ``model/robot.xml`` 再自建
    平地；两边 ``<option>`` 曾不一致（TRON1 实测 Euler/pyramidal/impratio=1/地面 0.6 vs
    implicitfast/elliptic/impratio=100/地面 0.8），于是有了"把 scene 的 option 搬过来"这一步。

    **现状**：物理 ``<option>`` 已固化进 ``model/robot.xml``（tools/bake_mjcf_physics.py），
    scene 不再声明 option——实测 ``<include>`` 里的 option 会被继承，两侧天然同源，故搬运
    逻辑删除。仍未消除的只有"验收平地"与"场景地面"的摩擦差异，因此本函数只返回地板摩擦；
    ``option_attrs`` 保留空字典仅为兼容既有调用形态。
    """
    rel = str(sim_cfg.get("scene_path") or "")
    if not rel:
        return {}, None
    scene = package_dir / rel
    if not scene.is_file():
        return {}, None
    try:
        text = scene.read_text(encoding="utf-8-sig")
    except OSError:
        return {}, None
    option_attrs: dict[str, str] = {}  # 退役：物理 <option> 已固化进 model/robot.xml
    floor_friction = None
    for gm in _FLOOR_GEOM_RE.finditer(text):
        attrs = {k: v for k, v in _XML_ATTR_RE.findall(gm.group(1))}
        if attrs.get("type") == "plane" and attrs.get("friction"):
            try:
                floor_friction = [float(x) for x in attrs["friction"].split()]
            except ValueError:
                floor_friction = None
            break
    return option_attrs, floor_friction


def apply_effort_override(model, effort_override: dict[str, float]) -> None:
    """按调用方给的表覆盖逐关节力矩上限（``sim2sim_headless`` 的"部署口径复现"）。

    这是**显式调用方意图**，不是资产修补：契约 effort 已固化进 MJCF，这里只是把调用方
    声明的另一套限幅写上（该工具用 v2 契约 ``torque_limits`` 复现部署侧口径）。
    认不出的关节名**直接报错**，不静默忽略——忽略过一次，工具就会拿"没有覆盖"的结果
    当"覆盖后"的结论。
    """
    import mujoco

    joint_to_actuator: dict[str, int] = {}
    for i in range(model.nu):
        jid = int(model.actuator_trnid[i][0])
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, jid)
        if name:
            joint_to_actuator.setdefault(name.lower(), i)
    unknown = [name for name in effort_override if name.lower() not in joint_to_actuator]
    if unknown:
        raise SystemExit(f"effort_override 含未知或无执行器的关节：{sorted(unknown)}")
    for name, value in effort_override.items():
        index = joint_to_actuator[name.lower()]
        limit = float(value)
        model.actuator_forcerange[index][:] = (-limit, limit)
        model.actuator_forcelimited[index] = 1


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
        spec = mujoco.MjSpec.from_file(str(scene))
    else:
        model_xml = package_dir / "model" / "robot.xml"
        if not model_xml.is_file():
            raise SystemExit(f"包内缺少模型: {model_xml}")
        spec = mujoco.MjSpec.from_file(str(model_xml))
    # 执行器/关节常量不再由验收器改写：包内 MJCF 已固化契约口径
    # （tools/bake_mjcf_physics.py）。验收 = 编译资产 + 注入契约 timestep，
    # 物理真值与浏览器/训练完全同源；漂移由校验器报，不静默修。

    # 关节常量（armature / frictionloss）已固化进包内 MJCF（tools/bake_mjcf_physics.py），
    # 这里不再注入：同一份数据只允许在资产里存在一次，注入 = "运行时偷偷改写物理"。
    from contracts.physics_binding import physics_scalars

    if not scene_rel:
        spec.worldbody.add_geom(
            type=mujoco.mjtGeom.mjGEOM_PLANE,
            name="acceptance_floor",
            size=[10.0, 10.0, 0.05],
        )
    model = spec.compile()
    if not scene_rel:
        # 自建场景必须复刻包内 scene.xml 的物理设置，否则 wasm 与 server_mujoco
        # 两个执行器会给出不同结论（Pack 声明 require_deterministic_replay）。
        # `<option>` 已固化进 model/robot.xml（场景不再重复声明），此处只对齐"场景自带的
        # 地板摩擦"——那是场景属性，不是机器人物理，不涉及两份真值。
        _option_attrs, floor_friction = scene_physics_overrides(package_dir, sim_cfg)
        if floor_friction is not None:
            gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "acceptance_floor")
            if gid >= 0:
                model.geom_friction[gid] = floor_friction
    # 契约 physics_hz 是步长唯一真值：包内 robot.xml 常自带 timestep="0.001"，
    # 调用方漏改就会以 5 倍速跑（策略按 decimation 计频，频率直接错位）。
    # B3 收尾：取值改走 physics_scalars（契约真值 优先）——此前读 sim config 顶层
    # physics_hz，去掉重复键后若不同步迁移就会静默回落 200（go2 契约是 500）。
    scalars = physics_scalars(package_dir)
    physics_hz = float(scalars.get("physics_hz") or 200)
    model.opt.timestep = 1.0 / physics_hz
    if effort_override:
        apply_effort_override(model, effort_override)
    return model


def run_probe(contract: PackageContract, model, data, obs: ObsBuilder,
              seconds: float = 3.0) -> dict[str, Any]:
    """预检（清单 ⑧）：开环恒定动作扫物理包络，训练前确认动作空间可达且不即刻发散。

    无策略参与：raw 恒定为 ±magnitude（逐关节按 action_scale/default 生效），
    记录每种幅值下的存活、最低高度、最大倾角与峰值关节速度。

    **速度限幅（D9）**：此前这里只在记录 ``qvel_max``，从不与任何阈值比对——而
    浏览器侧的电机模型（``applyVelocityLimits``）一直在用速度限幅限速，"电机参数"
    三端口径不一致（浏览器有、训练/验收没有）。现在把契约真值 的
    ``velocity_limit`` 拉进来，对峰值关节速度逐关节判定并显式报告。
    """
    # V4 fail-closed：动作空间声明缺失/自相矛盾时给明确中文原因，不抛裸 IndexError。
    # 放在 mujoco import 之前：声明校验不需要物理引擎，控制面 venv 也能测这条守卫。
    # （B25：探针报错不阻断训练，但脏字段每台新机型冒烟都会带——错误必须可读。）
    order_len = len(contract.action_joint_order)
    if not contract.action_dim or not order_len:
        raise ValueError(
            f"无法开环探测：{contract.root.name} 契约未声明动作空间"
            f"（action_dim={contract.action_dim}，动作关节序 {order_len} 项）——"
            "请在包 simulation/config.json 的策略声明（obs_dim/action_dim）"
            "或 contract.json 的 action.joint_order 补齐后重试"
        )
    if order_len > contract.action_dim:
        raise ValueError(
            f"无法开环探测：{contract.root.name} 契约自相矛盾——"
            f"动作关节序 {order_len} 项 > 声明 action_dim={contract.action_dim}，"
            "恒定动作数组无法覆盖全部关节，请先修正声明"
        )

    import mujoco

    # D9：速度限幅的唯一真值 = 契约真值（键统一小写，带 __default__ 兜底）。
    from contracts.physics_binding import joint_constant_tables

    speed_limits = joint_constant_tables(contract.root)["velocity_limits"]
    default_limit = speed_limits.get("__default__")
    peak_by_joint: dict[str, float] = {}
    results = []
    envelope_reach = 0.0
    for magnitude in (0.0, 0.25, -0.25, 0.5, -0.5, 0.75, -0.75, 1.0, -1.0):
        spawn_default(contract, model, data, obs)
        raw = np.full(contract.action_dim, magnitude, dtype=np.float32)
        total = int(seconds * contract.physics_hz)
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
            for name in contract.action_joint_order:
                addr = obs.jadr.get(name)
                if addr is None:
                    continue
                peak = abs(float(data.qvel[addr[1]]))
                if peak > peak_by_joint.get(name, 0.0):
                    peak_by_joint[name] = peak
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
        "speed_limit": _speed_limit_report(contract, peak_by_joint, speed_limits, default_limit),
    }


def _speed_limit_report(contract: PackageContract, peak_by_joint: dict[str, float],
                        speed_limits: dict[str, float], default_limit: float | None) -> dict[str, Any]:
    """契约速度限幅 vs 探针峰值关节速度（D9）。

    判定为 ``warn`` 而非 ``fail``：**训练侧物理上并未强制速度上限**（mjlab 的
    ``ActuatorCfg`` 无 velocity_limit 字段，MuJoCo 关节也没有速度上限属性），
    超限只说明"动作空间把关节推到了电机转速之外"，属需要知情的信息，不是
    本次验收失败——把它记为 fail 会让既有基线无预警翻转。
    """
    violations: list[dict[str, Any]] = []
    worst: dict[str, Any] | None = None
    for name, peak in sorted(peak_by_joint.items()):
        limit = speed_limits.get(name.lower())
        if limit is None:
            limit = default_limit
        if limit is None or limit <= 0:
            continue
        ratio = peak / float(limit)
        entry = {"joint": name, "peak": round(peak, 3), "limit": float(limit), "ratio": round(ratio, 3)}
        if ratio > 1.0:
            violations.append(entry)
        if worst is None or ratio > worst["ratio"]:
            worst = entry
    if not speed_limits and default_limit is None:
        return {
            "schema": "policy-speed-limit-1.0",
            "declared": False,
            "verdict": "skip",
            "note": (
                "契约真值 未声明 velocity_limit，本次不做速度判定"
                "（浏览器侧电机模型同样只会用缺省值——要判定请先在包内补速度限幅）"
            ),
            "worst": None,
            "violations": [],
        }
    return {
        "schema": "policy-speed-limit-1.0",
        "declared": True,
        "verdict": "pass" if not violations else "warn",
        "note": (
            "训练/验收侧的 MuJoCo 物理**不强制**速度上限（mjlab 无 velocity_limit 字段），"
            "本项为知情性判据；要真正强制需在控制器层做力矩-速度削顶。"
        ),
        "worst": worst,
        "violations": violations,
        "action_joints": len(contract.action_joint_order),
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
    """默认姿下**足端触地**时 root 的垂直高度 —— 纯运动学量。

    早前版本用"零动作静立 ``seconds`` 秒"取稳态高度。那对 ``actuator_interface="torque"``
    的包（go2 / g1 等）等价于**零力矩**：机器人必然塌下去，参考高度被算成 7~9 cm
    （上游训练真值 0.3 / 0.754 米），于是"稳态高度比"这把尺子把**本来站得住的策略**
    判成不合格，还连带把多条策略的复跑提前中止。改成几何量后与力矩语义无关，
    也不受落地瞬态影响。（``seconds`` 参数保留仅为兼容调用点，现已不参与计算。）

    做法：root 放到 z=0、关节保持默认角，前向算一次，量**非世界体**几何体的最低点；
    该点深度即"足端到 root 的垂直距离"，也就是足端触地时的 root 高度。
    """
    import mujoco

    spawn_default(contract, model, data, obs)
    data.qpos[2] = 0.0
    mujoco.mj_forward(model, data)

    hints = ("foot", "wheel", "toe", "calf", "ankle")
    robot_geoms = [i for i in range(model.ngeom) if model.geom_bodyid[i] != 0]  # 0 = world（地板）
    named_feet = [
        i for i in robot_geoms
        if any(
            hint in (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, i) or "").lower()
            for hint in hints
        )
    ]
    heights = [float(data.geom_xpos[i][2]) for i in (named_feet or robot_geoms)]
    if not heights:
        return contract.initial_height
    return max(abs(min(heights)), 1e-3)


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
    # 跟踪误差比较的是策略真正收到的指令（含命令缩放），不是用户侧旋钮值。
    cmd_eff = contract.effective_command(cmd_arr)

    total = int(seconds * contract.physics_hz)
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
        # 迭代 = 一个物理步；策略每 decimation 步刷新一次（与浏览器/训练同频）。
        actuate(contract, model, data, obs, raw)
        mujoco.mj_step(model, data)

        q = data.qpos[3:7]
        g = projected_gravity(q)
        roll = math.degrees(math.atan2(g[1], -g[2])) if -g[2] > 1e-6 else math.copysign(90.0, g[1])
        pitch = math.degrees(math.asin(clamp(g[0], -1.0, 1.0)))
        roll_max = max(roll_max, abs(roll))
        pitch_max = max(pitch_max, abs(pitch))
        height_min = min(height_min, float(data.qpos[2]))
        # 与 run_mode 同一口径：起摆窗口内不判摔（双图 encoder 链同样受这条保护）。
        if fell_at is None and step >= int(0.5 * contract.physics_hz) and (
            data.qpos[2] < 0.45 * contract.initial_height or abs(roll) > 90.0 or abs(pitch) > 90.0
        ):
            fell_at = step / contract.physics_hz
            break
        if step > total * 0.7:
            _, ang_b, lin_b = obs.base_state()
            vel_errs.append(float(np.linalg.norm(lin_b[:2] - cmd_eff[:2]) + 0.3 * abs(ang_b[2] - cmd_eff[2])))
            steady_height.append(float(data.qpos[2]))
            steady_roll.append(abs(roll))
            steady_pitch.append(abs(pitch))

    survived = (fell_at * contract.physics_hz) if fell_at is not None else total
    metrics = {
        "command": [float(x) for x in cmd],
        "command_effective": [float(x) for x in cmd_eff],
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


def match_policy_entry(
    policies: list, policy_path: Path, package_dir: Path, policy_id: str = "",
) -> dict | None:
    """把 ``--policy``（onnx 路径，或 stem 恰为声明 id 的路径）映射回包内声明条目。

    B10 删掉 46 处裸 ``path``/``url`` 后，旧匹配 ``p.get("path", "")`` 恒为空串；
    而实测 46 条声明中 45 条**文件名 stem ≠ id**，于是几乎每次都静默回落
    ``policies[0]`` —— 拿第一条策略的增益/观测布局去验收别的策略
    （"看起来生效、实际不生效"）。改为与 ``tools/sim2sim_headless.py`` 同一口径，
    优先级：**① 显式 ``--policy-id``**（唯一无歧义的键；lite3 两条声明共用同一
    onnx，文件名原理上分不出谁是谁）→ ② stem 恰为声明 id → ③ 解析出的 blob
    文件名**全等**（``backend.policy_artifacts`` 纯标准库，适配器 venv 亦可导入）。
    解析不到返回 ``None``，由调用方决定是否 fail-closed。

    匹配用**文件名全等**而非 ``endswith``：后者会把 ``mypolicy.onnx`` 误配给
    ``--policy policy.onnx``（wuji_hand 的 blob 恰好就叫 ``policy.onnx``）。
    """
    from backend.policy_artifacts import policy_blob_path

    for p in policies:
        if not isinstance(p, dict):
            continue
        if policy_id:
            if p.get("id") == policy_id:
                return p
        elif p.get("id") == policy_path.stem:
            return p
    if policy_id:
        # 调用方点名了要谁（端点已预检 id 存在）：对不上就是数据漂移，
        # 不得退回文件名匹配 —— 给别人属于答非所问。
        return None
    for p in policies:
        if not isinstance(p, dict):
            continue
        blob = policy_blob_path(p, robot_dir=package_dir)
        if blob is not None and blob.name == policy_path.name:
            return p
    return None


def resolve_probe_policy_entry(sim_cfg: dict, profile_id: str = "") -> dict:
    """为**开环探针**挑选包内策略声明条目（与训练 profile 一致的优先）。

    B25 取证：worker 训练链从不携带策略条目（``config["policy"]`` 恒缺位），
    而探针需要的 obs_dim/action_dim 多数包只在 ``policies[]`` 各条目顶层声明
    （包级 policy_contract 声明维度的仅 g1/go2w/zex-w/tron1）。条目缺位曾让
    action_dim 落 0 → ``run_probe`` 裸 IndexError。

    匹配口径：① ``training_ref.profile`` == 当前训练 profile_id（唯一对应训练
    工程的声明）；② 否则第一条声明（与 CLI ``--probe`` 既有语义一致：契约条目
    只提供物理口径）。无声明返回空 dict，由 ``run_probe`` 的守卫 fail-closed。
    """
    policies = [p for p in (sim_cfg.get("policies") or []) if isinstance(p, dict)]
    if profile_id:
        for p in policies:
            ref = p.get("training_ref") or {}
            if str(ref.get("profile") or "") == profile_id:
                return p
    return policies[0] if policies else {}


def main() -> None:
    parser = argparse.ArgumentParser(description="ONNX 策略验收评估器")
    parser.add_argument("--package", required=True, help="机器人包目录")
    parser.add_argument("--policy", default="", help="policy.onnx 路径（--probe 模式可省略）")
    parser.add_argument("--policy-id", default="",
                        help="声明 id（共用同一 onnx 的多条声明靠它区分；缺省时按 id/文件名匹配）")
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
    if args.policy:
        # 给了 --policy 却对不上任何声明 → fail-closed：静默回落 policies[0] 会拿
        # 别人的契约条目（增益/观测布局）跑验收，报告看似正常实则答非所问。
        policy_entry = match_policy_entry(policies, policy_path, package_dir, args.policy_id)
        if policy_entry is None:
            raise SystemExit(
                f"--policy {policy_path.name} 无法对应包内任何策略声明"
                f"（既非声明 id，也无同名 onnx；包: {package_dir.name}）"
            )
    else:
        # --probe：无策略，契约条目只提供物理口径，取第一条即可。
        policy_entry = resolve_probe_policy_entry(sim_cfg)
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
        # 实际匹配到的声明 id（lite3 两条声明共用同一 onnx，只看文件名分不出用了谁的契约条目）
        "policy_id": policy_entry.get("id") if isinstance(policy_entry, dict) else None,
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
