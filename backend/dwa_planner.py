"""H11 局部采样规划器（DWA）——纯 Python，无 numpy/torch 依赖。

**为什么要有这个模块**：``backend/route_planner.py`` 只给**全局**折线（A*/Dijkstra，离线栅格），
``backend/follow_controller.py`` 只做**前视点跟随**（朝下一个点走，不看两侧）。两者之间缺一层
「按当前速度与朝向、在动态窗口里采样、挑一条既不撞又**贴合全局路径**的**局部**指令」。

**这次不造轮子**——算法、评分与参数全部对齐 ``00_resources`` 里的参考实现：

* **评分结构** = **Nav2 DWB 的 critics 体系**：``rc_old/.../sim2real_nav2/config/nav2_params.yaml``
  （``ObstacleFootprint 0.2 / PathAlign 32 / GoalAlign 24 / PathDist 32 / GoalDist 24``）与
  ``unitree-go2-slam-nav2/go2_slam_nav/config/nav2_params.yaml`` 同构。**要点：障碍权重必须远小于
  路径/目标**——障碍由硬碰撞否决 + 膨胀处理，评分里只是软引导；两者同量级会诱导机器人停在障碍前。
* **动态窗口与轨迹采样** = ``Odin-Nav-Stack/.../local_planner/dwa_planner.cpp``（``dwa_planner.h``）：
  ``[v±ax·T] × [w±alpha·T]``、unicycle 积分、footprint 圆碰撞、无解时恢复。
* **参数取值** = ``Odin-Nav-Stack/.../model_planner/config/local_planner.yaml`` 的 ``dwa`` 段
  （本项目自己的配置层，覆盖 ``dwa_planner.h`` 的代码默认）；ROS 官方
  ``navigation_planner/config/dwa_local_planner_params.yaml`` 作量级互校。
* **卡住恢复** = Nav2 ``progress_checker``（0.5 m / 10 s）语义 + ``behavior_server`` 的
  ``spin``/``backup`` 组合（本仓以"最优解速度≈0"近似、以"倒退+转向"实现）。

**参数一律来自注册表**（``registry/motion_commands.json#local_planner``，与 H12 的
``follow_controller`` 同文件）；缺块即报错，代码里不留旧默认值。

**五道实测防线**（都在本模块开发过程中实地踩到，改法见各函数 docstring）：
1. **障碍权重不能与路径同量级**——否则"原地不动 / 停在障碍前"成为局部最优；
2. 碰撞是 ``clearance < robot_radius`` 的**硬约束**（不是"穿透才拒"），否则贴角擦碰；
3. heading 对齐**路径方向**，不能对齐"朝目标"——否则预测越过后朝向背离、被罚到低于原地不动；
4. "原地不动"是合法候选，需要在"最优解速度≈0"时判定卡住并**倒退+转向**恢复；
5. 动态窗口要用**上一拍速度**（闭环），否则窗口恒绕 0 开、近目标采样过粗。

**与势场的关系**：``adapters/mjlab/nav_avoidance.py`` 是"吸引 + 斥力"的反应式控制器（H3 的 A 侧），
本模块是"采样择优"的局部规划器（B 侧）；A/B 对照在 ``tools/dwa_ab_check.py``。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

#: 障碍记录格式（与 ``scenario_maps.MAPS[...]["obstacles"]`` / nav_avoidance 同口径）
Obstacle = Sequence[float]  # [cx, cy, half_w, half_h]（world 米，轴对齐矩形）

PARAMS_SOURCE = "registry/motion_commands.json#local_planner"


def normalize_angle(angle: float) -> float:
    """归一化到 (-π, π]（与 follow_controller 同实现，避免两套角约定）。"""
    while angle > math.pi:
        angle -= 2 * math.pi
    while angle <= -math.pi:
        angle += 2 * math.pi
    return angle


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _linspace(low: float, high: float, count: int) -> list[float]:
    if count <= 1:
        return [(low + high) / 2.0]
    return [low + (high - low) * i / (count - 1) for i in range(count)]


# ---------------------------------------------------------------------------
# 几何：点到矩形 / 点到折线 / 折线方向
# ---------------------------------------------------------------------------
def point_rect_signed_distance(px: float, py: float, obstacle: Obstacle) -> float:
    """点到轴对齐矩形的**有符号**距离：内部为负（穿透深度），表面为 0，外部为正。

    与 ``adapters/mjlab/nav_avoidance._point_rect_signed_distance`` 同口径——两处各写一份
    是因为控制面不 import 训练栈适配层；数值语义必须一致（有测试对拍）。
    """
    cx = float(obstacle[0])
    cy = float(obstacle[1])
    half_w = abs(float(obstacle[2]))
    half_h = abs(float(obstacle[3]))
    left, right = cx - half_w, cx + half_w
    bottom, top = cy - half_h, cy + half_h
    if left < px < right and bottom < py < top:
        return -min(px - left, right - px, py - bottom, top - py)
    dx = max(left - px, 0.0, px - right)
    dy = max(bottom - py, 0.0, py - top)
    return math.hypot(dx, dy)


def min_clearance(x: float, y: float, obstacles: Sequence[Obstacle]) -> float:
    """到最近障碍表面的距离（无障碍时为 ``inf``）。"""
    if not obstacles:
        return float("inf")
    return min(point_rect_signed_distance(x, y, obstacle) for obstacle in obstacles)


def _point_segment_distance(
    px: float, py: float, ax: float, ay: float, bx: float, by: float
) -> float:
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = _clamp(((px - ax) * dx + (py - ay) * dy) / length_sq, 0.0, 1.0)
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _nearest_segment_index(x: float, y: float, path: Sequence[Sequence[float]]) -> int:
    best_index, best_distance = 0, float("inf")
    for index in range(max(0, len(path) - 1)):
        ax, ay = float(path[index][0]), float(path[index][1])
        bx, by = float(path[index + 1][0]), float(path[index + 1][1])
        distance = _point_segment_distance(x, y, ax, ay, bx, by)
        if distance < best_distance:
            best_distance, best_index = distance, index
    return best_index


def path_distance(x: float, y: float, path: Sequence[Sequence[float]]) -> float:
    """点到参考折线的最短距离（折线为空时 0）。"""
    if not path:
        return 0.0
    if len(path) == 1:
        return math.hypot(x - float(path[0][0]), y - float(path[0][1]))
    index = _nearest_segment_index(x, y, path)
    ax, ay = float(path[index][0]), float(path[index][1])
    bx, by = float(path[index + 1][0]), float(path[index + 1][1])
    return _point_segment_distance(x, y, ax, ay, bx, by)


def path_direction(x: float, y: float, path: Sequence[Sequence[float]]) -> float:
    """参考折线在"离 (x,y) 最近的一段"上的走向（弧度）。"""
    if not path or len(path) < 2:
        return 0.0
    index = _nearest_segment_index(x, y, path)
    ax, ay = float(path[index][0]), float(path[index][1])
    bx, by = float(path[index + 1][0]), float(path[index + 1][1])
    return math.atan2(by - ay, bx - ax)


# ---------------------------------------------------------------------------
# 参数
# ---------------------------------------------------------------------------
_INT_FIELDS = {"v_samples", "w_samples"}
_BOOL_FIELDS = {"allow_backward", "rotate_recovery"}


@dataclass(frozen=True)
class DwaParams:
    """DWA 参数（全部来自 ``registry/motion_commands.json#local_planner``）。"""

    sim_time_s: float
    sim_dt_s: float
    v_samples: int
    w_samples: int
    path_weight: float
    goal_weight: float
    align_weight: float
    clearance_weight: float
    speed_weight: float
    robot_radius_m: float
    inflation_m: float
    max_vx: float
    max_wz: float
    ax_max: float
    alpha_max: float
    allow_backward: bool
    rotate_recovery: bool
    rotate_recovery_factor: float
    recovery_vx_mps: float
    min_progress_v_mps: float
    heading_align_threshold_rad: float
    heading_boost: float

    @classmethod
    def from_registry(cls) -> "DwaParams":
        """从注册表读参数；缺块或缺字段**直接报错**（不静默用代码默认值）。"""
        from backend.motion_commands import local_planner_spec

        spec = local_planner_spec()
        names = list(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        missing = [name for name in names if spec.get(name) is None]
        if missing:
            raise ValueError(
                f"registry/motion_commands.json 的 local_planner 缺字段 {missing}；"
                "局部规划参数只有这一处真值，缺了就报错，不用代码里的旧默认值兜底"
            )
        values: dict[str, Any] = {}
        for name in names:
            raw = spec[name]
            if name in _INT_FIELDS:
                values[name] = int(raw)
            elif name in _BOOL_FIELDS:
                values[name] = bool(raw)
            else:
                values[name] = float(raw)
        return cls(**values)

    @property
    def steps(self) -> int:
        return max(1, int(round(self.sim_time_s / self.sim_dt_s)))


# ---------------------------------------------------------------------------
# 结果
# ---------------------------------------------------------------------------
@dataclass
class Candidate:
    """一个采样候选（无论可行与否都留档，扇形图要画"哪些被拒了"）。"""

    v: float
    w: float
    valid: bool
    score: float
    trajectory: list[list[float]]
    min_clearance_m: float | None = None
    rejected_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "v": round(self.v, 4),
            "w": round(self.w, 4),
            "valid": self.valid,
            "score": round(self.score, 6) if math.isfinite(self.score) else None,
            "trajectory": self.trajectory,
            "min_clearance_m": (
                round(self.min_clearance_m, 4) if self.min_clearance_m is not None else None
            ),
            "rejected_reason": self.rejected_reason,
        }


@dataclass
class DwaPlan:
    """一拍的结果：指令 + 最优轨迹 + 全部候选（扇形）+ 是否走了恢复动作。"""

    cmd: list[float]  # [vx, vy(=0), wz]
    trajectory: list[list[float]]
    candidates: list[Candidate]
    recovery: bool
    reason: str
    params_source: str = PARAMS_SOURCE
    metrics: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "cmd": self.cmd,
            "trajectory": self.trajectory,
            "candidates": [c.as_dict() for c in self.candidates],
            "recovery": self.recovery,
            "reason": self.reason,
            "params_source": self.params_source,
            "metrics": self.metrics,
        }


def _simulate(
    x0: float,
    y0: float,
    yaw0: float,
    v: float,
    w: float,
    params: DwaParams,
    obstacles: Sequence[Obstacle],
) -> tuple[list[list[float]] | None, float, str | None]:
    """unicycle 积分一条轨迹；返回 ``(轨迹, 最小净空, 拒绝原因)``。

    **硬约束是 ``clearance < robot_radius``**（机器人本体圆不得与障碍相交），不是"穿透才拒"
    ——首版只拒穿透，结果贴着障碍角擦过去、实际积分后净空 −0.003 m（实测踩过）。
    对应参考实现 ``dwa_planner.cpp::obstacleCost`` 的 footprint 圆检测。

    **被拒时也返回已走过的部分轨迹**（``rejected_reason`` 非 None）——扇形图要能画出
    "这条候选撞在哪"，返回空轨迹就看不到这个信息了。
    """
    x, y, theta = x0, y0, yaw0
    radius = params.robot_radius_m
    tolerance = 1e-9  # 浮点边界容差：0.35-0.15 会算成 0.19999999999999998
    trajectory = [[round(x, 4), round(y, 4), round(theta, 6)]]
    clearance = min_clearance(x, y, obstacles)
    if clearance < radius - tolerance:
        return trajectory, clearance, "start_in_collision"
    for _ in range(params.steps):
        x += v * math.cos(theta) * params.sim_dt_s
        y += v * math.sin(theta) * params.sim_dt_s
        theta = normalize_angle(theta + w * params.sim_dt_s)
        trajectory.append([round(x, 4), round(y, 4), round(theta, 6)])
        clearance = min(clearance, min_clearance(x, y, obstacles))
        if clearance < radius - tolerance:  # 本体圆与障碍相交：硬拒
            return trajectory, clearance, "collision"
    return trajectory, clearance, None


def _score(
    trajectory: list[list[float]],
    reference_path: Sequence[Sequence[float]],
    goal: Sequence[float],
    v: float,
    params: DwaParams,
    obstacles: Sequence[Obstacle],
) -> tuple[float, dict[str, Any]]:
    """**Nav2 DWB 的 critics 结构**（来源见 registry `evidence`）：

    ``path·PathDist + goal·GoalDist + align·PathAlign − clearance·ObstacleFootprint + speed·speed``。

    **障碍权重远小于路径/目标**（0.2 vs 32/24）——障碍已由硬碰撞否决 + 膨胀处理，评分里只是
    软引导；把 clearance 与 path 设成同量级会让机器人宁可停在障碍前（本模块首版实测踩过）。

    * ``PathDist``：末端到参考路径的距离 → ``1/(1+d)``；
    * ``GoalDist``：末端到目标距离 → ``1/(1+d)``；
    * ``PathAlign``：末端朝向对齐参考路径走向 → ``1−|Δyaw|/π``（大偏差乘 boost，同 dwa_planner.h）；
    * ``ObstacleFootprint``：轨迹最小净空的"贴近程度" ∈ [0,1]（越贴越大）。
    """
    end_x, end_y, end_theta = trajectory[-1]

    path_dist = path_distance(end_x, end_y, reference_path)
    goal_dist = math.hypot(float(goal[0]) - end_x, float(goal[1]) - end_y)

    desired_theta = path_direction(end_x, end_y, reference_path)
    align_error = abs(normalize_angle(end_theta - desired_theta)) / math.pi
    align_score = 1.0 - _clamp(align_error, 0.0, 1.0)
    if align_error * math.pi > params.heading_align_threshold_rad:
        # dwa_planner.cpp 的 heading_boost 是**放大分数**（heading_score *= boost）且**不 clamp**。
        # 一旦 clamp 到 1，大偏差区间会全部饱和，转向就失去梯度（本模块实测踩过：机器人在
        # 障碍前只小幅抖动、不肯转向）。不 clamp 时该项仍随偏差单调，梯度保留。
        align_score = align_score * params.heading_boost

    trajectory_clearance = min(min_clearance(x, y, obstacles) for x, y, _ in trajectory)
    # **连续代价场**（参考 tdt-nav-kit ``YAstar::setCostField`` 的 ``0.5/(0.1+x)``）：
    # 原来的 ``(safety−clearance)/safety`` 在 clearance ≥ safety 后**恒为 0、梯度丢失**，
    # 远处"再远一点"没有收益；连续式则始终有梯度（越远离障碍代价越小）。
    obstacle_cost = _clamp(
        params.inflation_m / (params.inflation_m + max(trajectory_clearance, 0.0)), 0.0, 1.0
    )

    speed_score = _clamp(max(0.0, v) / max(params.max_vx, 1e-6), 0.0, 1.0)

    # PathDist / GoalDist 取**负距离**（DWB 口径：越远越小）。**不能用 1/(1+d)**——它在近距离
    # 饱和，单靠"停在参考路径上"就能拿满分，机器人会原地不动（本模块实测踩过）。
    score = (
        -params.path_weight * path_dist
        - params.goal_weight * goal_dist
        + params.align_weight * align_score
        - params.clearance_weight * obstacle_cost
        + params.speed_weight * speed_score
    )
    metrics = {
        "path_distance_m": round(path_dist, 4),
        "goal_distance_m": round(goal_dist, 4),
        "align_score": round(align_score, 4),
        "obstacle_cost": round(obstacle_cost, 4),
        "speed_score": round(speed_score, 4),
        "min_clearance_m": round(trajectory_clearance, 4),
    }
    return score, metrics


def _recovery_trajectory(
    x0: float, y0: float, yaw0: float, v: float, w: float, params: DwaParams
) -> list[list[float]]:
    """恢复轨迹（不做碰撞否决——恢复就是要先脱离卡死）。"""
    x, y, theta = x0, y0, yaw0
    trajectory = [[round(x, 4), round(y, 4), round(theta, 6)]]
    for _ in range(params.steps):
        x += v * math.cos(theta) * params.sim_dt_s
        y += v * math.sin(theta) * params.sim_dt_s
        theta = normalize_angle(theta + w * params.sim_dt_s)
        trajectory.append([round(x, 4), round(y, 4), round(theta, 6)])
    return trajectory


def plan_local(
    pose: Sequence[float],
    velocity: Sequence[float],
    reference_path: Sequence[Sequence[float]],
    obstacles: Sequence[Obstacle] | None = None,
    *,
    params: DwaParams | None = None,
) -> DwaPlan:
    """采一拍局部指令。

    * ``pose``           ``[x, y, yaw]``（world 米 / rad）；
    * ``velocity``       ``[vx, vy, wz]``（当前速度，用于动态窗口）；
    * ``reference_path`` 全局折线（``navigation_plan`` 的 ``combined_path``）；
    * ``obstacles``      ``[[cx, cy, half_w, half_h], ...]``。

    卡住时（全撞，或最优候选速度≈0）走**倒退 + 转向**恢复；否则如实报告 ``reason``。
    """
    p = params or DwaParams.from_registry()
    x0, y0, yaw0 = float(pose[0]), float(pose[1]), float(pose[2])
    v_cur = float(velocity[0]) if len(velocity) > 0 else 0.0
    w_cur = float(velocity[2]) if len(velocity) > 2 else 0.0
    ref = [[float(pt[0]), float(pt[1])] for pt in reference_path]
    obs = [list(o) for o in (obstacles or [])]

    # 目标 = 参考路径末端（GoalDist 的参照点）。
    # **2026-09-13 诊断**：试过 Nav2 prunePlan 式的"截断到局部窗口"（局部目标=截断段末端，
    # 理由是本行原注释就写了"DWB 用截断路径末端"而实现用了全局末端），实测**无收益**：
    # horizon 3.0/5.0 m 与不截断持平（均 3/5），2.0 m 反而退化到 2/5（leg_0_1 超时）。
    # 失败的两条（full / leg_2_3）在**所有** horizon 下都失败 ⇒ 瓶颈不在"目标选远端还是近端"。
    goal = [float(ref[-1][0]), float(ref[-1][1])] if ref else [x0, y0]
    distance_to_goal = math.hypot(goal[0] - x0, goal[1] - y0)

    # 动态窗口（dwa_planner.cpp: plan() 头部）
    v_low = v_cur - p.ax_max * p.sim_time_s
    v_high = v_cur + p.ax_max * p.sim_time_s
    v_floor = -p.max_vx if p.allow_backward else 0.0
    v_low = max(v_floor, v_low)
    v_high = max(v_low, min(p.max_vx, v_high))
    w_low = max(-p.max_wz, w_cur - p.alpha_max * p.sim_time_s)
    w_high = max(w_low, min(p.max_wz, w_cur + p.alpha_max * p.sim_time_s))

    candidates: list[Candidate] = []
    best: Candidate | None = None
    best_metrics: dict[str, Any] = {}
    for v in _linspace(v_low, v_high, max(1, p.v_samples)):
        for w in _linspace(w_low, w_high, max(1, p.w_samples)):
            trajectory, clearance, rejected = _simulate(x0, y0, yaw0, v, w, p, obs)
            if rejected is not None:
                candidates.append(
                    Candidate(v, w, False, float("-inf"), trajectory, clearance, rejected)
                )
                continue
            score, metrics = _score(trajectory, ref, goal, v, p, obs)
            candidate = Candidate(v, w, True, score, trajectory, clearance)
            candidates.append(candidate)
            if best is None or score > best.score:
                best, best_metrics = candidate, metrics

    valid_count = sum(1 for c in candidates if c.valid)
    # 卡住信号：全撞，或"最优候选挪不动"（v≈0）。"原地不动"是合法候选（不撞、clearance 最高），
    # 会永久压过"前进但会撞"的解；参考实现只在"无任何可行轨迹"时恢复，抓不到这种情况（实测踩过）。
    # 卡住 = 既不动**也不转**。单纯原地转向（v≈0、w≠0）是正常对齐，不能算卡
    # ——参考 jie_3d_nav/d1_controller 就有独立的 heading/转向通道；本模块实测踩过：
    # 把"转向候选"误判为卡住会让恢复动作与转向互相打断，机器人原地抖。
    #
    # **2026-09-13 诊断：这里的"粗糙"反而是对的，改精致了更差（故保持原样）**。
    # 本判据确实把角速度阈值错用了 `min_progress_v_mps`（0.05，量纲不对），也确实用
    # "速度阈值×时间"代替了 Nav2 progress_checker 的**位移半径**语义。看起来该修，实测**修了更差**
    # （H19 回归 warehouse 5 条路线）：原样 3/5 →（位移半径 0.3 + 独立角速度阈值 0.15）**1/5**，
    # 还新增 random_1 超时；单独试 Nav2 prunePlan 式"参考路径截断到局部窗口"也无收益
    # （3.0 m 与原样持平，2.0 m 更差）。
    # 根因是**架构性**的，不是参数：warehouse 绕障碍 2 的窄处（机器人 x=3.46、障碍 x≥3.7）里，
    # 采样窗口内所有"前进"方向被硬约束**一并否决**（实测 400 个候选仅 68 个可行、可行者 v ≤ 0.14），
    # 而**单拍无状态**规划器没有"先原地转向对齐、再前进"的序列能力（2 s 预测窗口内转向会累积过冲，
    # 评分于是偏好"不转"）。Nav2 靠**行为树层**的 recovery behaviors（spin/backup，由
    # progress_checker 跨拍触发）解决——那正是本单拍实现缺的一层。
    # 详见任务清单 H11 的"停止盲调"与 tools/route_regression.py 的基线。
    stuck = best is None or (
        abs(best.v) < p.min_progress_v_mps
        and abs(best.w) < p.min_progress_v_mps
        and distance_to_goal > p.min_progress_v_mps * p.sim_time_s
    )
    if stuck and p.rotate_recovery and ref:
        # 卡住判据近似 Nav2 的 progress_checker（required_movement_radius/movement_time_allowance）；
        # 恢复动作 = Nav2 behavior_server 的 spin + backup 组合：倒退 + 转向。
        # 只"原地转"不行：朝向已对准目标时空转振荡（实测踩过）。
        error = normalize_angle(
            math.atan2(float(goal[1]) - y0, float(goal[0]) - x0) - yaw0
        )
        sign = 1.0 if error >= 0 else -1.0
        if abs(error) < 0.05:
            sign = 1.0  # 误差≈0 时符号会逐拍抖动 → 固定方向
        wz = sign * p.rotate_recovery_factor * p.max_wz
        vx = p.recovery_vx_mps
        return DwaPlan(
            cmd=[round(vx, 6), 0.0, round(wz, 6)],
            trajectory=_recovery_trajectory(x0, y0, yaw0, vx, wz, p),
            candidates=candidates,
            recovery=True,
            reason="rotate_recovery",
            metrics={
                "candidates_total": len(candidates),
                "candidates_valid": valid_count,
                "stuck": True,
            },
        )

    if best is None:
        return DwaPlan(
            cmd=[0.0, 0.0, 0.0],
            trajectory=[[round(x0, 4), round(y0, 4), round(yaw0, 6)]],
            candidates=candidates,
            recovery=False,
            reason="no_feasible_trajectory",
            metrics={"candidates_total": len(candidates), "candidates_valid": valid_count},
        )

    return DwaPlan(
        cmd=[round(best.v, 6), 0.0, round(best.w, 6)],
        trajectory=best.trajectory,
        candidates=candidates,
        recovery=False,
        reason="ok",
        metrics={
            **best_metrics,
            "candidates_total": len(candidates),
            "candidates_valid": valid_count,
            "stuck": False,
        },
    )


def candidate_fan(
    pose: Sequence[float],
    velocity: Sequence[float],
    reference_path: Sequence[Sequence[float]],
    obstacles: Sequence[Obstacle] | None = None,
    *,
    params: DwaParams | None = None,
) -> dict[str, Any]:
    """候选轨迹扇形（供页面绘制：可行绿色 / 被拒灰色 / 最优高亮）。

    与 :func:`plan_local` 同一实现——不另算一遍，避免"画出来的"和"跑出来的"不一致。
    """
    plan = plan_local(pose, velocity, reference_path, obstacles, params=params)
    best = max((c for c in plan.candidates if c.valid), key=lambda c: c.score, default=None)
    return {
        "cmd": plan.cmd,
        "reason": plan.reason,
        "recovery": plan.recovery,
        "params_source": plan.params_source,
        "metrics": plan.metrics,
        "best_index": plan.candidates.index(best) if best is not None else None,
        "candidates": [c.as_dict() for c in plan.candidates],
    }


def dwa_selftest() -> dict[str, Any]:
    """自检：注册表可读、空旷直路能前进、正前方障碍使"全速直行"被拒。

    说明：DWA 是**滚动优化**——单拍视界 ``sim_time`` 内只验证"避碰生效"；"绕障走完全程"
    在 ``tools/dwa_ab_check.py`` 的多拍循环里验证。
    """
    params = DwaParams.from_registry()
    straight = plan_local([0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [[0.0, 0.0], [2.0, 0.0]], [])
    blocked = plan_local(
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0],
        [[0.0, 0.0], [3.0, 0.0]],
        [[0.45, 0.0, 0.15, 0.25]],  # 挡在视界内的正前方（左边缘 0.30 > robot_radius 0.2）
    )
    total = blocked.metrics.get("candidates_total") or 0
    valid = blocked.metrics.get("candidates_valid") or 0
    return {
        "params_source": PARAMS_SOURCE,
        "steps_per_call": params.steps,
        "straight": {"cmd": straight.cmd, "reason": straight.reason},
        "blocked": {
            "cmd": blocked.cmd,
            "reason": blocked.reason,
            "valid_candidates": valid,
            "total_candidates": total,
        },
        "verdict": (
            "pass"
            if straight.reason == "ok"
            and straight.cmd[0] > 0.0
            and valid < total          # 有候选因撞被拒
            and blocked.cmd != straight.cmd  # 不再全速直行（减速/转向/恢复都算反应）
            else "fail"
        ),
    }
