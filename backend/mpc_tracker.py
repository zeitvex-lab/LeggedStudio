"""H14 可选对照控制器 ``controller: mpc`` —— 纯 Python 的 LightNav ``vln_mpc`` 简化版。

**出处（参考真实现，本文件是它的什么简化，逐条说清）**：

* 参考实现：``00_resources/LightNav-0/robot_deploy/src/vln_mpc/vln_mpc/mpc.py`` 的
  ``MPCController``（CasADi/IPOPT）+ ``mpc_node.py`` 的 ROS 节点。参考是**单车模型
  （unicycle）非线性最优控制**：把 ``horizon=5`` 步内每拍 ``(v, w)`` 当决策变量，
  目标 = Σ 状态误差ᵀ·Q·状态误差 + 控制量ᵀ·R·控制量，约束 = 运动学递推、
  ``0 ≤ v ≤ v_max``、``|w| ≤ w_max``、相邻拍加减速界（``a_max_v`` / ``a_max_w``）。
* 参数真值：``registry/motion_commands.json#mpc_tracker``（字段名与 ``mpc_node.py``
  的 ``declare_parameter`` 一一对应）。

**本文件搬了什么**：

* 同一套目标函数形状：Q 加权 ``(x, y, yaw)`` 误差 + R 加权控制量；
* 同一套参考点选取思路：``build_pose_aligned_reference``——每拍在**全路径**上找离机器人
  **位姿加权最近**的点，取其后 ``horizon`` 个点当参考轨迹（``weights=(q_x, q_y)`` 同源；
  参考是 3 维位姿加权、本仓路径点是 2 维，故只用位置权重）；
* 同一套约束语义：``0 ≤ v ≤ max_vx``、``|w| ≤ max_wz``、首拍受上一拍的加减速界
  （``a_max_v`` / ``a_max_w``）——首拍决策空间就是**上一拍速度的加减速可达窗**
  （这个窗与 DWA 的"动态窗口"同构，但评分用的是 MPC 目标函数）。

**没搬什么（诚实的简化清单）**：

1. **求解器**：CasADi/IPOPT 非线性连续优化 → **网格近似**：把首拍 ``(v, w)`` 在加减速
   可达窗内离散成 ``v_grid_steps + 1`` × ``w_grid_steps`` 档，对每个候选做**整条 horizon
   的单车前向 rollout**、按同一目标函数打分、取最优。这是"离散决策空间上的同目标 MPC"
   ——**不是** QP，最优性没有保证，网格分辨率即近似误差
   （``w_grid_steps=17`` ⇒ 转向分辨率 ≈ 窗宽/16 rad/s）。
2. **后续 horizon 拍的控制序列**：参考对整条 ``(v[k], w[k])`` 序列做联合优化并受
   **逐拍加减速链**约束；本实现只把首拍当决策变量，horizon 内后续拍用"朝参考点转"
   的启发式（几何跟踪律形状）推进 rollout——所以加减速约束**只对首拍生效**，
   序列级一致性没有搬。
3. **ROS 节点层**（``mpc_node.py``）：体坐标路径投影（``project_odom_to_local``）、
   10 Hz 求解线程池、``v_output_scale``/``w_output_scale`` 输出缩放、odom 断连超时、
   track/objnav 双模式——这些是 ROS 集成件，本仓评测口径
   （``tools/dwa_ab_check.simulate``）里不存在对应概念。

**定位（H14）**：``mpc`` 是**可选对照项**，不是推荐——H14 结论是四个参考项目没有一个
以 DWA 为主线、``geometric`` 应标推荐；vln_mpc 的存在只证明"另一个可选候选长什么样"。
参数缺块即报错（与 follow/geometric 同纪律），不回退代码默认值。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

PARAMS_SOURCE = "registry/motion_commands.json#mpc_tracker"

#: 参考实现路径（头注释与 selftest 里引用）
REFERENCE_SOURCE = (
    "00_resources/LightNav-0/robot_deploy/src/vln_mpc/vln_mpc/mpc.py"
    "（MPCController, build_pose_aligned_reference）+ mpc_node.py"
)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _wrap_angle(angle: float) -> float:
    """角度归一化到 (-π, π]（与参考 mpc.py 的 ``_wrap_angle`` 同式）。"""
    return (float(angle) + math.pi) % (2.0 * math.pi) - math.pi


@dataclass(frozen=True)
class MpcParams:
    """MPC 对照控制器参数（字段名与 vln_mpc ``mpc_node.py`` 的 declare_parameter 对齐）。"""

    horizon: int
    mpc_dt_s: float
    max_vx: float
    max_wz: float
    a_max_v: float
    a_max_w: float
    q_x: float
    q_y: float
    q_yaw: float
    r_v: float
    r_w: float
    w_grid_steps: int
    v_grid_steps: int

    @classmethod
    def from_registry(cls) -> "MpcParams":
        """从注册表读参数；缺块或缺字段**直接报错**（不静默用代码默认值）。"""
        from backend.motion_commands import mpc_tracker_spec

        spec = mpc_tracker_spec()
        names = list(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        missing = [name for name in names if spec.get(name) is None]
        if missing:
            raise ValueError(
                f"registry/motion_commands.json 的 mpc_tracker 缺字段 {missing}；"
                "MPC 参数只有这一处真值，缺了就报错"
            )
        values: dict[str, Any] = {}
        for name in names:
            raw = spec[name]
            values[name] = int(raw) if name in ("horizon", "w_grid_steps", "v_grid_steps") else float(raw)
        params = cls(**values)
        problems = validate_mpc_params(params)
        if problems:
            raise ValueError(f"mpc_tracker 参数非法：{'；'.join(problems)}")
        return params


def validate_mpc_params(params: "MpcParams") -> list[str]:
    """参数合法性（形状对齐参考 ``mpc_node.validate_mpc_config``：限值须正、权重非负）。"""
    problems: list[str] = []
    if params.horizon <= 0:
        problems.append("horizon 必须为正")
    if min(params.mpc_dt_s, params.max_vx, params.max_wz, params.a_max_v, params.a_max_w) <= 0.0:
        problems.append("时间步与限值必须为正")
    if min(params.q_x, params.q_y, params.q_yaw) < 0.0:
        problems.append("状态权重必须非负")
    if not any(w > 0.0 for w in (params.q_x, params.q_y)):
        problems.append("至少一个位置权重必须为正（参考 validate_mpc_config 同判）")
    if min(params.r_v, params.r_w) < 0.0:
        problems.append("控制量权重必须非负")
    if params.w_grid_steps < 3 or params.w_grid_steps % 2 == 0:
        problems.append("w_grid_steps 必须是 ≥3 的奇数（保证 w=0 在网格上）")
    if params.v_grid_steps < 1:
        problems.append("v_grid_steps 必须为正")
    return problems


def build_pose_aligned_reference(
    path: Sequence[Sequence[float]],
    pose: Sequence[float],
    *,
    horizon: int,
    weights: Sequence[float],
) -> list[list[float]]:
    """位姿对齐参考段（``vln_mpc/mpc.py::build_pose_aligned_reference`` 的纯 Python 等价）。

    参考实现吃 Nx3（x, y, **yaw**）轨迹——VLN 模型输出的航点自带朝向，``q_yaw`` 误差项
    才有对齐对象；本仓路径点是 2 维，故**航向取相邻点连线方向**（段方向），末点沿用前一段
    航向，并逐点展开不发生 ±2π 跳变（参考 48–51 行的同款 unwrap）。最近点搜索参考用
    全位姿加权，本仓路径无 yaw，只用位置权重 ``(q_x, q_y)``。

    返回 ``horizon`` 个 ``[x, y, yaw_ref]``。
    """
    points = [[float(p[0]), float(p[1])] for p in path]
    if not points:
        raise ValueError("参考路径为空，无法构建 MPC 参考")
    if len(points) == 1:
        points = [points[0], points[0]]
    x, y = float(pose[0]), float(pose[1])
    wx, wy = float(weights[0]), float(weights[1])
    costs = [((p[0] - x) * wx) ** 2 + ((p[1] - y) * wy) ** 2 for p in points]
    nearest = min(range(len(points)), key=lambda i: costs[i])
    indices = [min(nearest + 1 + k, len(points) - 1) for k in range(horizon)]

    # 段方向：每点的参考航向 = **进入该点**的方向（前一点 → 本点）——"到达该点时应摆出的
    # 朝向"；用出发方向会让机器人提前转弯。首点无前驱，沿用第二点方向（出发点朝向）。
    heading = [0.0] * len(points)
    for i in range(1, len(points)):
        heading[i] = math.atan2(points[i][1] - points[i - 1][1], points[i][0] - points[i - 1][0])
    heading[0] = heading[1] if len(points) > 1 else 0.0

    reference: list[list[float]] = []
    previous_yaw = 0.0
    for k, i in enumerate(indices):
        raw_yaw = heading[i]
        if k == 0:
            previous_yaw = raw_yaw
        else:
            raw_yaw = previous_yaw + _wrap_angle(raw_yaw - previous_yaw)
            previous_yaw = raw_yaw
        reference.append([points[i][0], points[i][1], raw_yaw])
    return reference

    reference: list[list[float]] = []
    previous_yaw = 0.0
    for k, i in enumerate(indices):
        raw_yaw = heading[i]
        if k == 0:
            previous_yaw = raw_yaw
        else:
            raw_yaw = previous_yaw + _wrap_angle(raw_yaw - previous_yaw)
            previous_yaw = raw_yaw
        reference.append([points[i][0], points[i][1], raw_yaw])
    return reference


def _heuristic_w(target: Sequence[float], pose: Sequence[float], w_max: float) -> float:
    """rollout 后续拍的启发式转向：朝参考点转（几何跟踪律形状，见头注释简化 2）。"""
    yaw = float(pose[2])
    desired = math.atan2(float(target[1]) - float(pose[1]), float(target[0]) - float(pose[0]))
    return _clamp(_wrap_angle(desired - yaw) / max(1e-6, 0.1), -w_max, w_max)


def _rollout_cost(
    pose: Sequence[float],
    v: float,
    w: float,
    reference: Sequence[Sequence[float]],
    params: MpcParams,
) -> float:
    """给定首拍控制 (v, w)，rollout 整条 horizon 并按参考同款目标函数打分。

    代价 = Σ [ (x−ref_x, y−ref_y, yaw−ref_yaw)ᵀ·Q·(·) + (v, w)ᵀ·R·(v, w) ]
    （参考 mpc.py 第 142–145 行的同款目标；后续拍转向用启发式 w、速度沿用 v——
    见头注释简化 2：序列级联合优化没搬。）
    """
    q_x, q_y, q_yaw = params.q_x, params.q_y, params.q_yaw
    r_v, r_w = params.r_v, params.r_w
    x, y, yaw = float(pose[0]), float(pose[1]), float(pose[2])
    cost = 0.0
    w_next = w
    for k, target in enumerate(reference):
        x += v * math.cos(yaw) * params.mpc_dt_s
        y += v * math.sin(yaw) * params.mpc_dt_s
        yaw = _wrap_angle(yaw + w_next * params.mpc_dt_s)
        yaw_err = _wrap_angle(yaw - float(target[2]))
        cost += q_x * (target[0] - x) ** 2 + q_y * (target[1] - y) ** 2 + q_yaw * yaw_err * yaw_err
        cost += r_v * v * v + r_w * w_next * w_next
        if k + 1 < len(reference):
            w_next = _heuristic_w(reference[k + 1], (x, y, yaw), params.max_wz)
    return cost


def mpc_command(
    pose: Sequence[float],
    reference: Sequence[Sequence[float]],
    params: MpcParams,
    *,
    previous: Sequence[float] = (0.0, 0.0),
) -> dict[str, Any]:
    """网格近似的 MPC 一步求解：返回 ``{cmd:[vx, 0, wz], cost, ...}``。

    **与参考的对应**：参考用 IPOPT 在连续空间解整条控制序列；这里把首拍 ``(v, w)``
    在**上一拍速度的加减速可达窗**内离散成 ``(v_grid_steps+1) × w_grid_steps`` 档
    （窗为空时退化为窗中心单点——上一拍控制越界也要有解可比），逐候选 rollout 打分取最优。
    位姿含非有限值时拒绝求解、返回定身指令，**不产生 NaN**。
    """
    x, y, yaw = float(pose[0]), float(pose[1]), float(pose[2])
    prev_v = float(previous[0])
    prev_w = float(previous[1])
    if not all(math.isfinite(value) for value in (x, y, yaw, prev_v, prev_w)):
        return {
            "cmd": [0.0, 0.0, 0.0],
            "cost": None,
            "candidates": 0,
            "reason": "pose/previous 含非有限值，MPC 拒绝求解（不产 NaN）",
        }

    # 首拍决策空间 = 上一拍速度 ± (a_max × mpc_dt)，再裁到硬限幅内（参考 MPC 首拍约束的
    # 离散化；与 DWA 的动态窗口同构，评分换成 MPC 目标函数）。
    v_lo = _clamp(prev_v - params.a_max_v * params.mpc_dt_s, 0.0, params.max_vx)
    v_hi = _clamp(prev_v + params.a_max_v * params.mpc_dt_s, 0.0, params.max_vx)
    n_v = max(1, params.v_grid_steps)
    v_grid = [v_lo + (v_hi - v_lo) * (i / n_v) for i in range(n_v + 1)]

    w_lo = _clamp(prev_w - params.a_max_w * params.mpc_dt_s, -params.max_wz, params.max_wz)
    w_hi = _clamp(prev_w + params.a_max_w * params.mpc_dt_s, -params.max_wz, params.max_wz)
    n_w = max(3, params.w_grid_steps if params.w_grid_steps % 2 == 1 else params.w_grid_steps + 1)
    w_grid = [w_lo + (w_hi - w_lo) * (i / (n_w - 1)) for i in range(n_w)]

    best: tuple[float, float] | None = None
    best_cost = float("inf")
    for v in v_grid:
        for w in w_grid:
            cost = _rollout_cost((x, y, yaw), v, w, reference, params)
            if cost < best_cost:
                best_cost = cost
                best = (v, w)

    if best is None:
        # 理论不可达（reference 为空等），防御性定身
        return {
            "cmd": [0.0, 0.0, 0.0],
            "cost": None,
            "candidates": 0,
            "reason": "无候选可评（参考段为空？），MPC 定身",
        }
    vx, wz = best
    if abs(vx) < 1e-6:
        vx = 0.0
    if abs(wz) < 1e-6:
        wz = 0.0
    return {
        "cmd": [round(vx, 6), 0.0, round(wz, 6)],
        "cost": round(best_cost, 6) if math.isfinite(best_cost) else None,
        "candidates": len(v_grid) * len(w_grid),
    }


class MpcTracker:
    """逐拍调用的 MPC 对照控制器（风格对齐 ``GeometricTracker``）。

    状态只有两项：上一拍控制 ``(v, wz)``（喂下一拍加减速可达窗）。
    追踪点**不**维护跨拍状态——参考 ``build_pose_aligned_reference`` 每拍在全路径上
    重找位姿加权最近点（这正是"pose-aligned"的本义），本实现保持同语义。
    """

    def __init__(
        self,
        path: Sequence[Sequence[float]],
        *,
        params: MpcParams | None = None,
    ) -> None:
        if len(path) < 2:
            raise ValueError("参考路径至少要两个点")
        self.path = [[float(p[0]), float(p[1])] for p in path]
        self.params = params or MpcParams.from_registry()
        self.previous: tuple[float, float] = (0.0, 0.0)
        self.nearest_index = 0

    def reset(self) -> None:
        self.previous = (0.0, 0.0)
        self.nearest_index = 0

    def update(self, pose: Sequence[float]) -> dict[str, Any]:
        """一拍：位姿对齐参考段 → 网格 MPC 求解 → 记录本拍控制供下一拍加减速窗。"""
        reference = build_pose_aligned_reference(
            self.path,
            pose,
            horizon=self.params.horizon,
            weights=(self.params.q_x, self.params.q_y),
        )
        result = mpc_command(pose, reference, self.params, previous=self.previous)
        self.previous = (result["cmd"][0], result["cmd"][2])
        return {
            **result,
            "reference": [[round(float(p[0]), 4), round(float(p[1]), 4)] for p in reference],
            "nearest_index": self.nearest_index,
            "params_source": PARAMS_SOURCE,
            "reference_source": REFERENCE_SOURCE,
        }


def mpc_selftest() -> dict[str, Any]:
    """自检：注册表可读、直线路径能走到末端（供 CI 快速验证判据链路）。"""
    params = MpcParams.from_registry()
    tracker = MpcTracker([[0.0, 0.0], [2.0, 0.0]], params=params)
    pose = [0.0, 0.0, 0.0]
    goal = tracker.path[-1]
    steps = 0
    for steps in range(1, 1001):
        result = tracker.update(pose)
        vx, _vy, wz = result["cmd"]
        pose = [pose[0] + vx * 0.05 * math.cos(pose[2]), pose[1] + vx * 0.05 * math.sin(pose[2]), pose[2] + wz * 0.05]
        if math.hypot(goal[0] - pose[0], goal[1] - pose[1]) < 0.15:
            break
    remaining = math.hypot(goal[0] - pose[0], goal[1] - pose[1])
    return {
        "params_source": PARAMS_SOURCE,
        "reference_source": REFERENCE_SOURCE,
        "steps": steps,
        "x_m": round(pose[0], 3),
        "remaining_m": round(remaining, 3),
        "verdict": "pass" if remaining < 0.25 else "fail",
    }
