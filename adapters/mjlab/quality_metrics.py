"""B11 评测矩阵之一：RoboGauge **八指标** + 加权几何平均质量分（可复算）。

## 八指标（口径照抄上游，不自己发明）

上游：`00_resources/kaiwu_rl/RoboGauge/robogauge/tasks/gauge/metrics/` 与
`gauge/base_gauge_config.py::QUALITY_WEIGHTS`、`gauge/goals/base_goal.py::update_metrics`。

| 指标 | 上游文件 | 公式（本模块逐行对照实现） |
|---|---|---|
| `lin_vel_err` | `vel_metrics.py::LinVelErrMetric` | `1 - ‖v_lin - v_cmd‖ / ‖max cmd‖` |
| `ang_vel_err` | `vel_metrics.py::AngVelErrMetric` | `1 - ‖ω - ω_cmd‖ / ‖max ω_cmd‖` |
| `dof_limits` | `dof_metrics.py::DofLimitsMetric` | 软限位（±(1-0.9)/2·range）内为 0，超出量 /range 后取 RMS，`1 - RMS` |
| `dof_power` | `dof_metrics.py::DofPowerMetric` | 逐关节 `|τ·v|` 的 RMS，`1 - RMS/100` |
| `orientation_stability` | `stable_metric.py::OrientationStabilityMetric` | `1 - |projected_gravity_y|`（只看 roll） |
| `torque_smoothness` | `stable_metric.py::TorqueSmoothnessMetric` | `1 - RMS(Δτ)/30`（首步记 1.0） |
| `friction_margin` | `stable_metric.py::FrictionMarginMetric` | 逐足 `utilization = ‖f_tan‖/(μ·f_n)`，`margin = max(0, 1-util)`，按法向力加权平均 |
| `zmp_margin` | `stable_metric.py::ZmpMarginMetric` | `1 - ‖ZMP_xy‖ / d_norm`（d_norm = 默认足距对角长） |

**质量分**（`base_goal.update_metrics`）：`Π clip(v, 1e-9, 1)^{w} ** (1/Σw)`，权重
`lin/ang_vel_err = 2`，其余 `= 1`。

## 与"谁能跑"的分工

本模块**只做指标**（纯函数 + 一个采集器）；"四档矩阵（single/multi/level/stress）+ 报告 JSON
+ 达标才放行打包"在 `backend/evaluation_api.py` 与导出闸门里（B11 后半）。
采集器与 B12 的 frame log 同源：同一套 `policy_acceptance` 原语、同一套策略解析
（`frame_log.resolve_policy`）—— 不另立第二套"怎么跑一条策略"。

## 诚实边界（写死在报告里）

* 需要**接触力/摩擦系数**的指标（`friction_margin`）在包内没有足端几何声明时**记 1.0 并标注
  `skipped`**（上游同款行为：找不到足端就返回 1.0）；不假装"和平足一样好"，但也不把它当成
  真实得分 —— 报告里带 `skipped` 名单。
* `zmp_margin` 需要 `d_norm`（默认足距对角长）：本模块在 reset 姿态实测两足足心距离，
  实测不出（单足/无足端）则记 0.0 并标注（与上游"d_norm 过小返回 0"同口径）。
* 角加速度用 MuJoCo 的 `mj_objectAcceleration(..., local=0)`（世界系）**直接取**，不做差分近似。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from frame_log import resolve_policy, resolve_policy_entry  # noqa: E402
from policy_acceptance import (  # noqa: E402
    ObsBuilder,
    PackageContract,
    actuate,
    load_package_model,
    projected_gravity,   # 重力投影**只有一处实现**（验收/浏览器同一口径），不在这里再写一份
    spawn_default,
)

ROOT = Path(__file__).resolve().parents[2]
REPORT_SCHEMA = "quality-report-1.0"

#: 上游 `base_gauge_config.py::QUALITY_WEIGHTS`
QUALITY_WEIGHTS: dict[str, float] = {
    "lin_vel_err": 2.0,
    "ang_vel_err": 2.0,
    "dof_limits": 1.0,
    "dof_power": 1.0,
    "orientation_stability": 1.0,
    "torque_smoothness": 1.0,
    "friction_margin": 1.0,
    "zmp_margin": 1.0,
}

#: 上游阈值项（`base_gauge_config.py` 的 `class metrics`）
SOFT_DOF_LIMIT_RATIO = 0.9
DOF_POWER_SCALING = 100.0
TORQUE_SMOOTHNESS_SCALING = 30.0
FRICTION_FORCE_THRESHOLD = 1.0
ZMP_CONTACT_THRESHOLD = 0.05
ZMP_FORCE_THRESHOLD = 1.0


def quality_score(values: dict[str, float]) -> float:
    """上游 `base_goal.update_metrics` 的加权几何平均（含 1e-9 下限，避免 log(0)）。"""

    score = 1.0
    weight_sum = 0.0
    for name, weight in QUALITY_WEIGHTS.items():
        if name not in values:
            continue
        score *= min(max(1e-9, float(values[name])), 1.0) ** weight
        weight_sum += weight
    return float(score ** (1.0 / weight_sum)) if weight_sum > 0 else 0.0


# --------------------------------------------------------------------------------------
# 八指标（纯函数：输入逐步数组，输出逐步得分；便于用合成数据复算）
# --------------------------------------------------------------------------------------
def lin_vel_err(lin_vel: np.ndarray, cmd: np.ndarray, cmd_limits: np.ndarray) -> np.ndarray:
    """`1 - ‖v_lin - v_cmd‖ / ‖cmd_limits‖`（上游 LinVelErrMetric）。"""

    error = np.linalg.norm(np.asarray(lin_vel) - np.asarray(cmd), axis=-1) / float(np.linalg.norm(cmd_limits))
    return 1.0 - error


def ang_vel_err(ang_vel: np.ndarray, cmd: np.ndarray, ang_cmd_limits: np.ndarray) -> np.ndarray:
    error = np.linalg.norm(np.asarray(ang_vel) - np.asarray(cmd), axis=-1) / float(np.linalg.norm(ang_cmd_limits))
    return 1.0 - error


def _motion_err(values: np.ndarray, cmd: np.ndarray, *, weight: float = 1.0) -> np.ndarray:
    """**运动档**并列口径：`1 − ‖差‖/‖cmd‖`（与 headless 验收器 tracking_ratio 同一数学）。

    与上游原口径（`lin_vel_err`/`ang_vel_err`，按 cmd_limits 归一）的区别只在**归一基准**：
    cmd_limits 含隐含上限（norm ≥1.732），小命令下"完全没动"也有 ~0.77 的本底分
    （go2w 重训复验实证）；本口径按实际命令幅值归一，没动就是 0。cmd≈0（站立）时
    没有运动语义 ⇒ 记 NaN，聚合时剔除（不冒充满分）。
    """
    values = np.asarray(values, dtype=np.float64)
    cmd = np.asarray(cmd, dtype=np.float64)
    speed = np.linalg.norm(cmd, axis=-1)
    scale = np.where(speed > 1e-6, speed * weight, np.nan)
    return 1.0 - np.linalg.norm(values - cmd, axis=-1) / scale


def dof_limits(joint_pos: np.ndarray, joint_limits: np.ndarray, *, ratio: float = SOFT_DOF_LIMIT_RATIO) -> np.ndarray:
    """上游 DofLimitsMetric：软限位内为 0，超出量 /range，逐关节 RMS 后 `1 - RMS`。"""

    pos = np.asarray(joint_pos, dtype=np.float64)
    limits = np.asarray(joint_limits, dtype=np.float64)
    ranges = limits[:, 1] - limits[:, 0]
    usable = ranges > 1e-6
    soft_low = limits[:, 0] + (1 - ratio) * ranges / 2
    soft_high = limits[:, 1] - (1 - ratio) * ranges / 2
    violation = np.zeros_like(pos)
    if usable.any():
        low_missing = np.where(usable, np.maximum(soft_low - pos, 0.0), 0.0)
        high_missing = np.where(usable, np.maximum(pos - soft_high, 0.0), 0.0)
        violation = np.where(usable, (low_missing + high_missing) / np.where(usable, ranges, 1.0), 0.0)
    rms = np.sqrt(np.mean(np.square(violation), axis=-1)) if pos.size else np.zeros(len(pos))
    return 1.0 - rms


def dof_power(joint_torque: np.ndarray, joint_vel: np.ndarray, *, scaling: float = DOF_POWER_SCALING) -> np.ndarray:
    """上游 DofPowerMetric：逐关节 `|τ·v|` 的 RMS，`1 - RMS/scaling`。"""

    power = np.abs(np.asarray(joint_torque) * np.asarray(joint_vel))
    rms = np.sqrt(np.mean(np.square(power), axis=-1))
    return 1.0 - rms / scaling


def orientation_stability(quat: np.ndarray) -> np.ndarray:
    """上游 OrientationStabilityMetric：`1 - |projected_gravity_y|`（只看 roll）。"""

    quat_arr = np.asarray(quat, dtype=np.float64)
    if quat_arr.ndim == 1:
        quat_arr = quat_arr[None, :]
    # 逐帧调验收模块的实现（同口径、同一处代码）；直立应为 (0,0,-1)
    projected = np.asarray([projected_gravity(frame) for frame in quat_arr], dtype=np.float64)
    return 1.0 - np.abs(projected[:, 1])


def torque_smoothness(joint_torque: np.ndarray, *, scaling: float = TORQUE_SMOOTHNESS_SCALING) -> np.ndarray:
    """上游 TorqueSmoothnessMetric：`1 - RMS(Δτ)/scaling`，首步记 1.0。"""

    torque = np.asarray(joint_torque, dtype=np.float64)
    if torque.shape[0] == 0:
        return np.zeros(0)
    diffs = np.diff(torque, axis=0)
    rms = np.sqrt(np.mean(np.square(diffs), axis=-1)) if diffs.size else np.zeros(0)
    return np.concatenate(([1.0], 1.0 - rms / scaling))


def friction_margin(
    foot_normal: list[np.ndarray],
    foot_tangent: list[np.ndarray],
    foot_limit: list[np.ndarray],
    *,
    force_threshold: float = FRICTION_FORCE_THRESHOLD,
) -> tuple[np.ndarray, list[bool]]:
    """上游 FrictionMarginMetric：逐足 `1 - utilization` 按法向力加权平均。

    返回 ``(逐步得分, 逐步是否"算了")`` —— 没有足端接触声明时按上游口径记 1.0，但**标注 skipped**，
    报告里能看出"这一项其实没算"。
    """

    scores: list[float] = []
    computed: list[bool] = []
    for normal, tangent, limit in zip(foot_normal, foot_tangent, foot_limit):
        normal_arr = np.asarray(normal, dtype=np.float64)
        tangent_arr = np.asarray(tangent, dtype=np.float64)
        limit_arr = np.asarray(limit, dtype=np.float64)
        mask = normal_arr > force_threshold
        if not mask.any():
            scores.append(1.0)
            computed.append(False)
            continue
        margins: list[float] = []
        weights: list[float] = []
        for value_n, value_t, value_l in zip(normal_arr[mask], tangent_arr[mask], limit_arr[mask]):
            if value_l <= force_threshold:
                margins.append(0.0)
                weights.append(float(value_n))
                continue
            utilization = float(value_t) / float(value_l)
            margins.append(max(0.0, 1.0 - utilization))
            weights.append(float(value_n))
        scores.append(float(np.average(margins, weights=np.asarray(weights))) if margins else 1.0)
        computed.append(bool(margins))
    return np.asarray(scores, dtype=np.float64), computed


def zmp_margin(
    contact_xy: list[np.ndarray],
    contact_dist: list[np.ndarray],
    com_pos: list[np.ndarray],
    mass: np.ndarray,
    inertia_world: list[np.ndarray],
    body_ang_vel: list[np.ndarray],
    body_ang_acc: list[np.ndarray],
    body_lin_acc: list[np.ndarray],
    gravity: np.ndarray,
    d_norm: float,
    *,
    contact_threshold: float = ZMP_CONTACT_THRESHOLD,
    force_threshold: float = ZMP_FORCE_THRESHOLD,
) -> tuple[np.ndarray, list[bool]]:
    """上游 ZmpMarginMetric：`1 - ‖ZMP_xy‖/d_norm`（ZMP 由全身惯性/重力力矩求和得到）。

    与上游同口径的边界：无支撑接触 / 竖向合力过小 ⇒ 记 1.0（并标注未计算）；
    ``d_norm`` 过小 ⇒ 记 0.0（上游显式返回 0）。
    """

    scores: list[float] = []
    computed: list[bool] = []
    for step, (xy, dist) in enumerate(zip(contact_xy, contact_dist)):
        xy_arr = np.asarray(xy, dtype=np.float64)
        dist_arr = np.asarray(dist, dtype=np.float64)
        contact_mask = dist_arr <= contact_threshold
        support = xy_arr[contact_mask] if xy_arr.size else np.zeros((0, 3))
        if support.shape[0] == 0:
            scores.append(1.0)
            computed.append(False)
            continue
        support_center = support.mean(axis=0)
        rel = np.asarray(com_pos[step], dtype=np.float64) - support_center[None, :]
        forces = np.asarray(mass, dtype=np.float64)[:, None] * (
            np.asarray(gravity, dtype=np.float64)[None, :] - np.asarray(body_lin_acc[step], dtype=np.float64)
        )
        total_force = forces.sum(axis=0)
        total_force_z = float(total_force[2])
        if abs(total_force_z) < force_threshold:
            scores.append(1.0)
            computed.append(False)
            continue
        inertia = np.asarray(inertia_world[step], dtype=np.float64)
        ang_vel = np.asarray(body_ang_vel[step], dtype=np.float64)
        ang_acc = np.asarray(body_ang_acc[step], dtype=np.float64)
        inertia_alpha = np.einsum("nij,nj->ni", inertia, ang_acc)
        inertia_omega = np.einsum("nij,nj->ni", inertia, ang_vel)
        gyro = np.cross(ang_vel, inertia_omega)
        moments = np.cross(rel, forces) - (inertia_alpha + gyro)
        total_moment = moments.sum(axis=0)
        zmp_xy = np.array([-total_moment[1] / total_force_z, total_moment[0] / total_force_z], dtype=np.float64)
        if d_norm < 1e-8:
            scores.append(0.0)
            computed.append(True)
            continue
        scores.append(max(0.0, 1.0 - float(np.linalg.norm(zmp_xy)) / float(d_norm)))
        computed.append(True)
    return np.asarray(scores, dtype=np.float64), computed


# --------------------------------------------------------------------------------------
# 采集：跑一条策略，把指标需要的信号逐控制步记下来
# --------------------------------------------------------------------------------------
def collect_trace(
    *,
    package_dir: Path | str,
    policy: str | None = None,
    policy_id: str | None = None,
    cmd: tuple[float, ...] | list[float] = (0.4, 0.0, 0.0),
    steps: int = 200,
) -> dict[str, Any]:
    """与 frame log 同源地跑策略（同一套原语与策略解析），收集**指标所需**的信号。

    记的是"指标要用的量"而不是全部状态：基础位姿/速度、关节 pos/vel/扭矩、指令、
    足端接触（法向/切向/摩擦上限）、刚体动力学量（com 位置/质量/世界系惯量/角速度/角加速度）。
    """

    import mujoco

    package_dir = Path(package_dir).expanduser().resolve()
    sim_config = json.loads((package_dir / "simulation" / "config.json").read_text(encoding="utf-8-sig"))
    entry = resolve_policy_entry(sim_config, policy_id)
    policy_path, _, _ = resolve_policy(package_dir, entry, policy)
    contract = PackageContract(package_dir, entry)

    model = load_package_model(package_dir, sim_config)
    model.opt.timestep = 1.0 / contract.physics_hz
    data = mujoco.MjData(model)
    obs_builder = ObsBuilder(contract, model, data)

    import onnxruntime

    session = onnxruntime.InferenceSession(str(policy_path), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name

    spawn_default(contract, model, data, obs_builder)
    obs_builder.phase_s = 0.0
    obs_builder.last_action[:] = 0
    obs_builder.history = []

    # 足端几何：上游按**名字**过滤接触，本仓行不通 —— 实测 zex-w 的 38 个几何**全部无名**
    # （`mj_id2name` 全 None），按名匹配一个也找不到。改为**按结构派生**：足端＝叶体
    # （没有子节点的刚体）上的几何。对四足/轮足/人形都成立，且不依赖命名习惯。
    parent_ids = {int(model.body_parentid[i]) for i in range(1, model.nbody)}
    leaf_bodies = [i for i in range(1, model.nbody) if i not in parent_ids]
    foot_geom_ids = {i for i in range(model.ngeom) if int(model.geom_bodyid[i]) in set(leaf_bodies)}
    joint_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        for name in contract.action_joint_order
    ]
    joint_qpos = [int(model.jnt_qposadr[jid]) for jid in joint_ids if jid >= 0]
    joint_dof = [int(model.jnt_dofadr[jid]) for jid in joint_ids if jid >= 0]
    joint_limits = np.asarray(
        [model.jnt_range[jid] for jid in joint_ids if jid >= 0], dtype=np.float64
    ) if joint_ids else np.zeros((0, 2))

    # d_norm：默认姿态下**足端几何中心的最大两两距离** —— 对应上游 `default_diagonal_foot_distance`
    # （"默认足距对角长"）。口径写死在这里：它会进报告（`d_norm` 字段），换个口径结论会变，
    # 所以必须是可复核的一行，而不是散在代码里的一句话。
    foot_centers = [np.asarray(data.geom_xpos[geom_id], dtype=np.float64) for geom_id in sorted(foot_geom_ids)]
    d_norm = 0.0
    for i in range(len(foot_centers)):
        for j in range(i + 1, len(foot_centers)):
            d_norm = max(d_norm, float(np.linalg.norm(foot_centers[i] - foot_centers[j])))

    trace: dict[str, list[Any]] = {
        "lin_vel": [], "ang_vel": [], "base_quat": [], "cmd": [],
        "joint_pos": [], "joint_vel": [], "joint_torque": [],
        "contact_xy": [], "contact_dist": [], "foot_normal": [], "foot_tangent": [], "foot_limit": [],
        "com_pos": [], "body_ang_vel": [], "body_ang_acc": [], "body_lin_acc": [], "inertia_world": [],
    }
    cmd_limits = np.asarray([abs(contract.cmd_scale[i]) * max(1.0, abs(float(cmd[i]))) for i in range(3)])
    wrench = np.zeros(6, dtype=np.float64)

    def _foot_force(contact_index: int) -> tuple[float, float, float]:
        mujoco.mj_contactForce(model, data, contact_index, wrench)
        normal = abs(float(wrench[0]))
        tangent = float(np.linalg.norm(wrench[1:3]))
        geom1 = int(data.contact[contact_index].geom1)
        geom2 = int(data.contact[contact_index].geom2)
        friction = max(float(model.geom_friction[geom1, 0]), float(model.geom_friction[geom2, 0]))
        return normal, tangent, friction * normal

    for _ in range(int(steps)):
        observation = obs_builder.build(np.asarray(cmd, dtype=np.float32))
        raw = session.run(None, {input_name: observation})[0][0]
        action = np.asarray(raw, dtype=np.float32)[: contract.action_dim]
        obs_builder.last_action = action.astype(np.float32)
        actuate(contract, model, data, obs_builder, obs_builder.last_action)
        for _ in range(contract.decimation):
            mujoco.mj_step(model, data)

        trace["lin_vel"].append(np.asarray(data.qvel[0:3], dtype=np.float64).copy())
        trace["ang_vel"].append(np.asarray(data.qvel[3:6], dtype=np.float64).copy())
        trace["base_quat"].append(np.asarray(data.qpos[3:7], dtype=np.float64).copy())
        trace["cmd"].append(np.asarray(cmd, dtype=np.float64).copy())
        trace["joint_pos"].append(np.asarray(data.qpos[joint_qpos], dtype=np.float64).copy())
        trace["joint_vel"].append(np.asarray(data.qvel[joint_dof], dtype=np.float64).copy())
        trace["joint_torque"].append(np.asarray(data.actuator_force, dtype=np.float64).copy())

        normals: list[float] = []
        tangents: list[float] = []
        limits: list[float] = []
        contact_xy: list[list[float]] = []
        contact_dist: list[float] = []
        for contact_index in range(data.ncon):
            contact = data.contact[contact_index]
            contact_xy.append(list(np.asarray(contact.pos, dtype=np.float64)))
            contact_dist.append(float(contact.dist))
            if int(contact.geom1) in foot_geom_ids or int(contact.geom2) in foot_geom_ids:
                normal, tangent, limit = _foot_force(contact_index)
                normals.append(normal)
                tangents.append(tangent)
                limits.append(limit)
        trace["contact_xy"].append(np.asarray(contact_xy, dtype=np.float64).reshape(-1, 3))
        trace["contact_dist"].append(np.asarray(contact_dist, dtype=np.float64))
        trace["foot_normal"].append(np.asarray(normals, dtype=np.float64))
        trace["foot_tangent"].append(np.asarray(tangents, dtype=np.float64))
        trace["foot_limit"].append(np.asarray(limits, dtype=np.float64))

        com_pos, mass, inertia, ang_vel, ang_acc, lin_acc = [], [], [], [], [], []
        for body_id in range(1, model.nbody):
            com_pos.append(np.asarray(data.xipos[body_id], dtype=np.float64).copy())
            mass.append(float(model.body_mass[body_id]))
            rotation = np.asarray(data.ximat[body_id], dtype=np.float64).reshape(3, 3)
            inertia.append(rotation @ np.diag(np.asarray(model.body_inertia[body_id], dtype=np.float64)) @ rotation.T)
            velocity = np.zeros(6, dtype=np.float64)
            mujoco.mj_objectVelocity(model, data, mujoco.mjtObj.mjOBJ_BODY, body_id, velocity, 0)
            acceleration = np.zeros(6, dtype=np.float64)
            mujoco.mj_objectAcceleration(model, data, mujoco.mjtObj.mjOBJ_BODY, body_id, acceleration, 0)
            ang_vel.append(velocity[0:3].copy())
            ang_acc.append(acceleration[0:3].copy())
            lin_acc.append(acceleration[3:6].copy())
        trace["com_pos"].append(np.asarray(com_pos, dtype=np.float64))
        trace["body_ang_vel"].append(np.asarray(ang_vel, dtype=np.float64))
        trace["body_ang_acc"].append(np.asarray(ang_acc, dtype=np.float64))
        trace["body_lin_acc"].append(np.asarray(lin_acc, dtype=np.float64))
        trace["inertia_world"].append(np.asarray(inertia, dtype=np.float64))

    return {
        "trace": trace,
        "mass": np.asarray([float(model.body_mass[i]) for i in range(1, model.nbody)], dtype=np.float64),
        "gravity": np.asarray(model.opt.gravity, dtype=np.float64),
        "joint_limits": joint_limits,
        "cmd": np.asarray(cmd, dtype=np.float64),
        "cmd_limits": cmd_limits,
        "d_norm": d_norm,
        "package": package_dir,
        "policy": {"id": entry.get("id"), "path": str(policy_path)},
        "steps": int(steps),
        "has_foot_geoms": bool(foot_geom_ids),
        "foot_geoms": {
            "count": len(foot_geom_ids),
            "leaf_bodies": len(leaf_bodies),
            "derivation": "叶体（无子节点刚体）上的几何 —— 本仓模型几何未命名，按结构派生",
        },
    }


def metrics_from_trace(source: dict[str, Any]) -> dict[str, Any]:
    """把 trace 变成八指标（逐步 → 均值）+ 质量分。纯计算，可对合成数据复算。"""

    trace = source["trace"]
    per_step: dict[str, np.ndarray] = {}
    per_step["lin_vel_err"] = lin_vel_err(trace["lin_vel"], trace["cmd"], source["cmd_limits"])
    per_step["ang_vel_err"] = ang_vel_err(trace["ang_vel"], np.zeros_like(trace["cmd"]), source["cmd_limits"])
    # **运动档并列口径**（2026-09-28）：按 ‖cmd‖ 归一（headless tracking_ratio 同数学），回答
    # "到底动没动/跟了多少"——go2w 重训复验实证原口径在小命令下有 ~0.77 的没动本底。
    # **不进质量分加权**（八指标与放行门语义不变），只并列输出供跨口径对读；
    # ang_vel 运动档的对照命令是零（上游口径如此），无旋转命令时同样记 NaN 剔除。
    per_step["lin_vel_err_motion"] = _motion_err(trace["lin_vel"], trace["cmd"])
    per_step["ang_vel_err_motion"] = _motion_err(trace["ang_vel"], np.zeros_like(trace["cmd"]))
    per_step["dof_limits"] = dof_limits(trace["joint_pos"], source["joint_limits"])
    per_step["dof_power"] = dof_power(trace["joint_torque"], trace["joint_vel"])
    per_step["orientation_stability"] = orientation_stability(trace["base_quat"])
    per_step["torque_smoothness"] = torque_smoothness(trace["joint_torque"])
    friction, friction_computed = friction_margin(trace["foot_normal"], trace["foot_tangent"], trace["foot_limit"])
    per_step["friction_margin"] = friction
    zmp, zmp_computed = zmp_margin(
        trace["contact_xy"], trace["contact_dist"], trace["com_pos"], source["mass"],
        trace["inertia_world"], trace["body_ang_vel"], trace["body_ang_acc"], trace["body_lin_acc"],
        source["gravity"], source["d_norm"],
    )
    per_step["zmp_margin"] = zmp

    means = {
        # 运动档含 NaN（cmd≈0 的站立步无运动语义）⇒ 用 nanmean 剔除；全 NaN ⇒ 0.0 如实（无运动语义可评）。
        name: float(np.nanmean(np.clip(np.asarray(values, dtype=np.float64), 0.0, 1.0)))
        if len(values) and not np.all(np.isnan(np.asarray(values, dtype=np.float64))) else 0.0
        for name, values in per_step.items()
    }
    skipped = []
    if not source.get("has_foot_geoms"):
        skipped.append("friction_margin（包内没有足端几何声明，按上游口径记 1.0）")
    if not any(friction_computed):
        skipped.append("friction_margin（全程没有足端法向力超阈值，未真正计算）")
    if not any(zmp_computed):
        skipped.append("zmp_margin（全程无有效支撑接触或竖向合力过小，未真正计算）")
    if source.get("d_norm", 0.0) < 1e-8:
        skipped.append("zmp_margin（实测不出默认足距对角长 d_norm ⇒ 按上游口径记 0）")
    return {
        "metrics": means,
        "quality_score": quality_score(means),
        "per_step": {name: values.tolist() for name, values in per_step.items()},
        "skipped": skipped,
    }


def evaluate(
    *,
    package_dir: Path | str,
    policy: str | None = None,
    policy_id: str | None = None,
    cmd: tuple[float, ...] | list[float] = (0.4, 0.0, 0.0),
    steps: int = 200,
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """跑一条策略 → 八指标 + 质量分 + 结论（`ok` 与 `blockers`，与 export_gate 同报告形状）。"""

    source = collect_trace(package_dir=package_dir, policy=policy, policy_id=policy_id, cmd=cmd, steps=steps)
    result = metrics_from_trace(source)
    thresholds = thresholds or {"quality_score": 0.5}
    blockers = [
        f"{name} = {result['metrics'].get(name):.4f} < 阈值 {value}"
        for name, value in thresholds.items()
        if name in result["metrics"] and result["metrics"][name] < value
    ]
    if "quality_score" in thresholds and result["quality_score"] < thresholds["quality_score"]:
        blockers = [item for item in blockers if not item.startswith("quality_score")] + [
            f"quality_score = {result['quality_score']:.4f} < 阈值 {thresholds['quality_score']}"
        ]
    return {
        "schema": REPORT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "package": str(source["package"]),
        "policy": source["policy"],
        "cmd": list(source["cmd"]),
        "steps": source["steps"],
        "d_norm": source["d_norm"],
        "weights": QUALITY_WEIGHTS,
        "metrics": result["metrics"],
        "quality_score": result["quality_score"],
        "thresholds": thresholds,
        "skipped": result["skipped"],
        "ok": not blockers,
        "blockers": blockers,
    }


# --------------------------------------------------------------------------------------
# 四档矩阵（B11 后半）：single / multi / level / stress
#
# 口径来自上游 `00_resources/kaiwu_rl/RoboGauge/robogauge/tasks/pipeline/`：
#   * single —— 单策略单指令：八指标 + 质量分（就是上面 :func:`evaluate`）；
#   * multi  —— 多策略 × 多指令矩阵：每格一条质量分，汇总均值/最差值；
#   * level  —— 难度递增的分层：每层"成功"= 质量分 ≥ 阈值，`success_mean >= 0.8` 该层过，
#               **遇到第一个不过的层就停**（上游 level_pipeline 同款）；
#   * stress —— 多条件（本仓是**指令条件**）：逐条件取中位数 ⇒ `benchmark_score = mean(scores)`，
#               并给 `robust_score[条件][指标] = mean ± var`（上游 stress_pipeline 同款）。
#
# **地形维度未启用（如实登记）**：上游 stress 按地形分层，而本仓 14 个包只有 `wuji_hand` 声明了
# 两种地形（`flat` / `reorient`），其余都只有 `flat` —— 多地形 stress 等包声明出多种地形后再扩，
# 现在硬造地形只会产出"看着像压力测试、其实是同一场景跑五遍"的结果。
# --------------------------------------------------------------------------------------
TIERS = ("single", "multi", "level", "stress")
MATRIX_SCHEMA = "quality-matrix-1.0"
#: 上游 `level_pipeline.py::test_level` 的判据
LEVEL_SUCCESS_MEAN_BAR = 0.8


def _commands_from_scale(scale: list[float], magnitudes: list[float]) -> list[list[float]]:
    return [[float(scale[0]) * m, 0.0, 0.0] for m in magnitudes]


def run_single(
    *, package_dir: Path | str, policy: str | None = None, policy_id: str | None = None,
    cmd: tuple[float, ...] | list[float] = (0.4, 0.0, 0.0), steps: int = 200,
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    report = evaluate(package_dir=package_dir, policy=policy, policy_id=policy_id,
                      cmd=cmd, steps=steps, thresholds=thresholds)
    report["tier"] = "single"
    return report


def run_multi(
    *, package_dir: Path | str, policies: list[dict[str, Any]], commands: list[list[float]],
    steps: int = 150, thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """多策略 × 多指令矩阵。`policies` 形如 ``[{"policy_id": "..."}, {"policy": "..."}]``。"""

    cells: list[dict[str, Any]] = []
    for spec in policies:
        for command in commands:
            report = evaluate(package_dir=package_dir, steps=steps, thresholds=thresholds or {},
                              cmd=command, **spec)
            cells.append({
                "policy": report["policy"],
                "cmd": command,
                "quality_score": report["quality_score"],
                "metrics": report["metrics"],
                "skipped": report["skipped"],
            })
    scores = [cell["quality_score"] for cell in cells if cell["policy"]]
    return {
        "schema": MATRIX_SCHEMA,
        "tier": "multi",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "package": str(Path(package_dir)),
        "count": len(cells),
        "cells": cells,
        "aggregate": {
            "mean": float(np.mean(scores)) if scores else 0.0,
            "min": float(np.min(scores)) if scores else 0.0,
            "worst": min(cells, key=lambda cell: cell["quality_score"])["cmd"] if cells else None,
        },
        "thresholds": thresholds or {},
        "ok": bool(scores) and (thresholds or {}).get("quality_score", 0.0) <= float(np.min(scores)),
        "blockers": [],
    }


def run_level(
    *, package_dir: Path | str, policy: str | None = None, policy_id: str | None = None,
    magnitudes: list[float] | None = None, steps: int = 150,
    success_threshold: float = 0.5, success_mean_bar: float = LEVEL_SUCCESS_MEAN_BAR,
) -> dict[str, Any]:
    """难度递增分层：每层一组指令，成功 = 质量分 ≥ `success_threshold`；`success_mean ≥ 0.8` 该层过。

    遇到第一个不过的层就停（上游同款）—— 后面的层没跑不假装跑过，报告里 `stopped_early=true`。
    """

    magnitudes = magnitudes or [0.5, 0.75, 1.0]
    probe = evaluate(package_dir=package_dir, policy=policy, policy_id=policy_id, steps=4, thresholds={})
    scale = [abs(float(probe["cmd"][0])) or 1.0, 1.0, 1.0]
    levels: list[dict[str, Any]] = []
    stopped_early = False
    for index, magnitude in enumerate(magnitudes, start=1):
        commands = _commands_from_scale(scale, [magnitude])
        results = [
            evaluate(package_dir=package_dir, policy=policy, policy_id=policy_id,
                     cmd=command, steps=steps, thresholds={})
            for command in commands
        ]
        successes = [report["quality_score"] >= success_threshold for report in results]
        success_mean = float(np.mean(successes)) if successes else 0.0
        passed = success_mean >= success_mean_bar
        levels.append({
            "level": index,
            "magnitude": magnitude,
            "commands": commands,
            "quality_scores": [report["quality_score"] for report in results],
            "success_mean": success_mean,
            "passed": passed,
        })
        if not passed:
            stopped_early = index < len(magnitudes)
            break
    return {
        "schema": MATRIX_SCHEMA,
        "tier": "level",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "package": str(Path(package_dir)),
        "policy": {"policy": policy, "policy_id": policy_id},
        "success_threshold": success_threshold,
        "success_mean_bar": success_mean_bar,
        "levels": levels,
        "stopped_early": stopped_early,
        "passed_levels": sum(1 for level in levels if level["passed"]),
        "ok": all(level["passed"] for level in levels) and not stopped_early,
        "blockers": [f"level {level['level']}（幅值 {level['magnitude']}）success_mean="
                     f"{level['success_mean']:.2f} < {success_mean_bar}" for level in levels if not level["passed"]],
    }


def run_stress(
    *, package_dir: Path | str, policy: str | None = None, policy_id: str | None = None,
    conditions: dict[str, list[float]] | None = None, steps: int = 150, repeats: int = 1,
) -> dict[str, Any]:
    """多条件压力档：逐条件取质量分**中位数** ⇒ `benchmark_score = mean(scores)`。

    `repeats > 1` 时逐次重跑：本仓**没有域随机化**（L3 缺口）⇒ 同 seed 重复跑必然同值，
    `robust_score` 的方差会是 0 —— 这是如实结果，不是"稳如老狗"。DR 接入后这一栏才有信息量。
    """

    probe = evaluate(package_dir=package_dir, policy=policy, policy_id=policy_id, steps=4, thresholds={})
    scale = abs(float(probe["cmd"][0])) or 1.0
    conditions = conditions or {
        "forward": [scale, 0.0, 0.0],
        "backward": [-scale, 0.0, 0.0],
        "lateral": [0.0, scale, 0.0],
        "yaw": [0.0, 0.0, scale],
        "diagonal": [scale, 0.0, scale],
    }
    scores: dict[str, float] = {}
    robust: dict[str, dict[str, Any]] = {}
    details: dict[str, Any] = {}
    for name, command in conditions.items():
        runs = [
            evaluate(package_dir=package_dir, policy=policy, policy_id=policy_id,
                     cmd=command, steps=steps, thresholds={})
            for _ in range(max(1, repeats))
        ]
        quality = [report["quality_score"] for report in runs]
        scores[name] = float(np.median(quality))
        metric_names = sorted(runs[0]["metrics"])
        robust[name] = {
            metric: {
                "mean": float(np.mean([report["metrics"][metric] for report in runs])),
                "var": float(np.var([report["metrics"][metric] for report in runs])),
            }
            for metric in metric_names
        }
        details[name] = {"cmd": command, "quality_scores": quality}
    benchmark = float(np.mean(list(scores.values()))) if scores else 0.0
    scores_with_benchmark = {**scores, "benchmark": benchmark}
    return {
        "schema": MATRIX_SCHEMA,
        "tier": "stress",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "package": str(Path(package_dir)),
        "policy": {"policy": policy, "policy_id": policy_id},
        "repeats": repeats,
        "dimension": "command",
        "dimension_note": "上游按地形分层；本仓包内只声明了一种地形（除 wuji_hand），故按指令条件分层",
        "scores": scores_with_benchmark,
        "robust_score": robust,
        "details": details,
        "benchmark_score": benchmark,
        "ok": True,
        "blockers": [],
    }


def run_tier(tier: str, **kwargs: Any) -> dict[str, Any]:
    """四档统一入口（CLI 与后端都走它）。"""

    if tier == "single":
        return run_single(**kwargs)
    if tier == "multi":
        return run_multi(**kwargs)
    if tier == "level":
        return run_level(**kwargs)
    if tier == "stress":
        return run_stress(**kwargs)
    raise ValueError(f"未知档位 {tier!r}（可选：{TIERS}）")


def main() -> int:
    parser = argparse.ArgumentParser(description="B11 八指标评测（可复算的计算部分）")
    parser.add_argument("--package", required=True)
    parser.add_argument("--policy", default=None, help="包内相对路径或绝对路径")
    parser.add_argument("--policy-id", default=None, help="策略 id（走统一解析器）")
    parser.add_argument("--cmd", default="0.4,0,0")
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--quality-min", type=float, default=0.5, help="质量分下限（默认 0.5）")
    parser.add_argument("--tier", default="single", choices=list(TIERS), help="评测档位（B11 后半）")
    parser.add_argument("--magnitudes", default="0.5,0.75,1.0", help="level 档的幅值序列")
    parser.add_argument("--repeats", type=int, default=1, help="stress 档每条件重跑次数")
    parser.add_argument("--json", action="store_true", help="只输出 JSON（机器可读）")
    parser.add_argument("--out", type=Path, default=None, help="把报告写到该路径")
    args = parser.parse_args()

    if args.tier == "single":
        report = run_single(
            package_dir=args.package,
            policy=args.policy,
            policy_id=args.policy_id,
            cmd=tuple(float(x) for x in args.cmd.split(",")),
            steps=args.steps,
            thresholds={"quality_score": args.quality_min},
        )
    elif args.tier == "level":
        report = run_tier("level", package_dir=args.package, policy=args.policy,
                          policy_id=args.policy_id, steps=args.steps,
                          magnitudes=[float(x) for x in args.magnitudes.split(",")],
                          success_threshold=args.quality_min)
    elif args.tier == "stress":
        report = run_tier("stress", package_dir=args.package, policy=args.policy,
                          policy_id=args.policy_id, steps=args.steps, repeats=args.repeats)
    else:
        report = run_tier("multi", package_dir=args.package,
                          policies=[{"policy": args.policy, "policy_id": args.policy_id}],
                          commands=[tuple(float(x) for x in args.cmd.split(","))],
                          steps=args.steps, thresholds={"quality_score": args.quality_min})
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif report.get("tier") == "level":
        print(f"分层评测（{report['schema']}）：每层 success_mean ≥ {report['success_mean_bar']}")
        for level in report["levels"]:
            mark = "✓" if level["passed"] else "✗"
            print(f"  {mark} level {level['level']} 幅值 {level['magnitude']}："
                  f"success_mean={level['success_mean']:.2f} 质量分 {[round(x, 3) for x in level['quality_scores']]}")
        if report["stopped_early"]:
            print("  ~ 遇到不过的层即停（后面的层没跑）")
        print("✓ 通过" if report["ok"] else "✗ 未通过")
    elif report.get("tier") == "stress":
        print(f"压力档（{report['dimension']} 维度 / 每条件 {report['repeats']} 次）")
        for name, value in report["scores"].items():
            print(f"  {name:>10}: {value:.4f}")
        print(f"  benchmark_score = {report['benchmark_score']:.4f}")
    elif report.get("tier") == "multi":
        print(f"矩阵评测：{report['count']} 格，mean={report['aggregate']['mean']:.4f} "
              f"min={report['aggregate']['min']:.4f}")
    else:
        print(f"八指标评测：{report['policy'].get('id') or report['policy']['path']}（{report['steps']} 控制步）")
        for name in QUALITY_WEIGHTS:
            print(f"  {name:>22}: {report['metrics'][name]:.4f}  (w={QUALITY_WEIGHTS[name]:g})")
        print(f"  {'quality_score':>22}: {report['quality_score']:.4f}")
        for item in report["skipped"]:
            print(f"  ~ 未真正计算：{item}")
        for item in report["blockers"]:
            print(f"  ✗ {item}")
        print("✓ 达标" if report["ok"] else "✗ 未达标")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
