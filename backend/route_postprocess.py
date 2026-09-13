"""H13 规划后处理：**净空四级 + 路径简化 + 转角混合**（纯 Python，无第三方依赖）。

**为什么要有这一层**：``backend/route_planner.py`` 只给"能走通"的栅格折线——它不管
机器人**本体**离障碍还剩多少余量、拐角机器人拐不拐得过来。把这种路径直接下发给机器人，
就是"看着能走、实际擦碰"。这一层把每段路径打上**净空等级**，并做简化与转角混合。

**这次不造轮子**——三件事各有出处：

* **净空判据逐项抄** ``00_resources/rc_old/.../train/rc_mjlab/tools/nav_tools/route_safety_check.py``
  的 ``SegmentRisk.status``：

  .. code-block:: text

      centerline_intersects → "INTERSECT"   # 中心线穿进障碍
      margin < 0.0          → "VIOLATION"   # margin = clearance − required_clearance
      margin < warn_margin  → "TIGHT"
      否则                   → "OK"

  其中 ``required_clearance = footprint_radius + avoid_margin``，足迹半径照抄它的
  ``default_lateral_footprint_radius()``（``max(PCD 半径, 半宽, 轮子侧向) + padding``）。
* **路径简化**参考 ``00_resources/tdt-nav-kit/src/YAstar/yastar.hpp`` 的
  ``simplifyPath(path, tol)``（本仓用等价的 Douglas–Peucker，迭代式实现）。
* **转角混合**用 ``00_resources/rc_old/.../route_candidate_optimizer.py`` 的
  ``--max-segment-length`` 口径做圆角采样，参数 ``corner_blend`` 取 H13 任务书。

参数唯一真值在 ``registry/motion_commands.json#route_postprocess``（与 H9/H11/H12 同文件）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

PARAMS_SOURCE = "registry/motion_commands.json#route_postprocess"

#: 净空等级（**顺序即严重度**，index 越大越严重）
CLEARANCE_LEVELS: tuple[str, ...] = ("OK", "TIGHT", "VIOLATION", "INTERSECT")

Point = Sequence[float]
#: 轴对齐障碍：[cx, cy, half_w, half_h]（与 scenario_maps / nav_avoidance 同口径）
Obstacle = Sequence[float]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class PostprocessParams:
    """后处理参数（唯一真值在注册表）。"""

    footprint_radius_m: float
    avoid_margin_m: float
    warn_margin_m: float
    simplify_tolerance_m: float
    corner_blend_m: float
    corner_blend_samples: int
    relax_iterations: int
    relax_step_scale: float
    relax_max_move_per_iter_m: float
    relax_max_total_move_m: float
    relax_smooth_weight: float
    relax_buffer_m: float
    relax_lock_ends: bool
    max_segment_length_m: float
    min_speed_mps: float

    @classmethod
    def from_registry(cls) -> "PostprocessParams":
        from backend.motion_commands import route_postprocess_spec

        spec = route_postprocess_spec()
        names = list(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        missing = [name for name in names if spec.get(name) is None]
        if missing:
            raise ValueError(
                f"registry/motion_commands.json 的 route_postprocess 缺字段 {missing}；"
                "后处理参数只有这一处真值，缺了就报错"
            )
        values: dict[str, Any] = {}
        for name in names:
            raw = spec[name]
            if name in ("corner_blend_samples", "relax_iterations"):
                values[name] = int(raw)
            elif name == "relax_lock_ends":
                values[name] = bool(raw)
            else:
                values[name] = float(raw)
        return cls(**values)

    @property
    def required_clearance_m(self) -> float:
        """段净空的下限 = 足迹半径 + 额外余量（route_safety_check 的 required_clearance）。"""
        return self.footprint_radius_m + self.avoid_margin_m


@dataclass(frozen=True)
class SegmentRisk:
    """一段路径的净空评估（字段与 ``route_safety_check.SegmentRisk`` 对齐）。"""

    index: int
    start_index: int
    end_index: int
    obstacle_index: int | None
    clearance_m: float
    required_m: float
    margin_m: float
    length_m: float
    centerline_intersects: bool

    @property
    def status(self) -> str:
        """默认判级（``warn_margin = 0.05``，与参考实现的默认一致）。"""
        return self.status_with(0.05)

    def status_with(self, warn_margin: float) -> str:
        """按给定 warn_margin 判级（判据同 route_safety_check.SegmentRisk.status）。"""
        if self.centerline_intersects:
            return "INTERSECT"
        if self.margin_m < 0.0:
            return "VIOLATION"
        if self.margin_m < warn_margin:
            return "TIGHT"
        return "OK"

    def as_dict(self, warn_margin: float) -> dict[str, Any]:
        return {
            "index": self.index,
            "start_index": self.start_index,
            "end_index": self.end_index,
            "obstacle_index": self.obstacle_index,
            "length_m": round(self.length_m, 4),
            "clearance_m": round(self.clearance_m, 4),
            "required_m": round(self.required_m, 4),
            "margin_m": round(self.margin_m, 4),
            "centerline_intersects": self.centerline_intersects,
            "status": self.status_with(warn_margin),
        }


# ---------------------------------------------------------------------------
# 几何：点到矩形 / 线段-矩形
# ---------------------------------------------------------------------------
def _point_rect_signed_distance(px: float, py: float, obstacle: Obstacle) -> float:
    """点到轴对齐矩形的有符号距离（内部为负）。与 ``nav_avoidance`` 同口径。"""
    cx, cy, half_w, half_h = (
        float(obstacle[0]),
        float(obstacle[1]),
        abs(float(obstacle[2])),
        abs(float(obstacle[3])),
    )
    left, right = cx - half_w, cx + half_w
    bottom, top = cy - half_h, cy + half_h
    if left < px < right and bottom < py < top:
        return -min(px - left, right - px, py - bottom, top - py)
    dx = max(left - px, 0.0, px - right)
    dy = max(bottom - py, 0.0, py - top)
    return math.hypot(dx, dy)


def _point_in_rect(px: float, py: float, obstacle: Obstacle) -> bool:
    return _point_rect_signed_distance(px, py, obstacle) < 0.0


def _corners(obstacle: Obstacle) -> list[tuple[float, float]]:
    cx, cy, half_w, half_h = (
        float(obstacle[0]),
        float(obstacle[1]),
        abs(float(obstacle[2])),
        abs(float(obstacle[3])),
    )
    return [
        (cx - half_w, cy - half_h),
        (cx + half_w, cy - half_h),
        (cx + half_w, cy + half_h),
        (cx - half_w, cy + half_h),
    ]


def _orientation(ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> float:
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


def _on_segment(
    ax: float, ay: float, bx: float, by: float, px: float, py: float
) -> bool:
    return (
        min(ax, bx) <= px <= max(ax, bx)
        and min(ay, by) <= py <= max(ay, by)
        and abs(_orientation(ax, ay, bx, by, px, py)) < 1e-12
    )


def segments_intersect(
    a: tuple[float, float], b: tuple[float, float], c: tuple[float, float], d: tuple[float, float]
) -> bool:
    """两线段是否相交（含共线重叠），与 ``route_safety_check.segments_intersect`` 同法。"""
    o1 = _orientation(a[0], a[1], b[0], b[1], c[0], c[1])
    o2 = _orientation(a[0], a[1], b[0], b[1], d[0], d[1])
    o3 = _orientation(c[0], c[1], d[0], d[1], a[0], a[1])
    o4 = _orientation(c[0], c[1], d[0], d[1], b[0], b[1])
    if (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0):
        return True
    return (
        _on_segment(a[0], a[1], b[0], b[1], c[0], c[1])
        or _on_segment(a[0], a[1], b[0], b[1], d[0], d[1])
        or _on_segment(c[0], c[1], d[0], d[1], a[0], a[1])
        or _on_segment(c[0], c[1], d[0], d[1], b[0], b[1])
    )


def segment_rect_intersects(a: Point, b: Point, obstacle: Obstacle) -> bool:
    """线段是否与矩形相交（端点在内也算）。"""
    ax, ay, bx, by = float(a[0]), float(a[1]), float(b[0]), float(b[1])
    if _point_in_rect(ax, ay, obstacle) or _point_in_rect(bx, by, obstacle):
        return True
    corners = _corners(obstacle)
    for index in range(4):
        if segments_intersect((ax, ay), (bx, by), corners[index], corners[(index + 1) % 4]):
            return True
    return False


def point_segment_distance(
    px: float, py: float, ax: float, ay: float, bx: float, by: float
) -> float:
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = _clamp(((px - ax) * dx + (py - ay) * dy) / length_sq, 0.0, 1.0)
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def segment_rect_distance(a: Point, b: Point, obstacle: Obstacle) -> float:
    """线段到矩形的最短距离（相交时 0）。等价 ``route_safety_check.segment_polygon_distance``。"""
    if segment_rect_intersects(a, b, obstacle):
        return 0.0
    ax, ay, bx, by = float(a[0]), float(a[1]), float(b[0]), float(b[1])
    distances = [
        _point_rect_signed_distance(ax, ay, obstacle),
        _point_rect_signed_distance(bx, by, obstacle),
    ]
    distances += [point_segment_distance(cx, cy, ax, ay, bx, by) for cx, cy in _corners(obstacle)]
    return min(distances)


# ---------------------------------------------------------------------------
# 净空分级
# ---------------------------------------------------------------------------
def classify_segments(
    path: Sequence[Point],
    obstacles: Sequence[Obstacle] | None,
    params: PostprocessParams | None = None,
) -> list[SegmentRisk]:
    """逐段评估净空：每个路径段取**最严重**的那个障碍（同严重度取 margin 更小者）。"""
    p = params or PostprocessParams.from_registry()
    obs = list(obstacles or [])
    required = p.required_clearance_m
    risks: list[SegmentRisk] = []
    for index, (a, b) in enumerate(zip(path, path[1:])):
        ax, ay, bx, by = float(a[0]), float(a[1]), float(b[0]), float(b[1])
        length = math.hypot(bx - ax, by - ay)
        if not obs:
            risks.append(
                SegmentRisk(index, index, index + 1, None, float("inf"), required,
                            float("inf"), length, False)
            )
            continue
        worst: SegmentRisk | None = None
        for obstacle_index, obstacle in enumerate(obs):
            intersects = segment_rect_intersects((ax, ay), (bx, by), obstacle)
            clearance = 0.0 if intersects else segment_rect_distance((ax, ay), (bx, by), obstacle)
            candidate = SegmentRisk(
                index=index,
                start_index=index,
                end_index=index + 1,
                obstacle_index=obstacle_index,
                clearance_m=clearance,
                required_m=required,
                margin_m=clearance - required,
                length_m=length,
                centerline_intersects=intersects,
            )
            if worst is None or _severity(candidate, p.warn_margin_m) > _severity(
                worst, p.warn_margin_m
            ) or (
                _severity(candidate, p.warn_margin_m) == _severity(worst, p.warn_margin_m)
                and candidate.margin_m < worst.margin_m
            ):
                worst = candidate
        assert worst is not None
        risks.append(worst)
    return risks


def _severity(risk: SegmentRisk, warn_margin: float) -> int:
    return CLEARANCE_LEVELS.index(risk.status_with(warn_margin))


# ---------------------------------------------------------------------------
# 路径简化（参考 tdt-nav-kit YAstar::simplifyPath）
# ---------------------------------------------------------------------------
def simplify_path(
    path: Sequence[Point], tolerance_m: float | None = None, *, params: PostprocessParams | None = None
) -> list[list[float]]:
    """Douglas–Peucker 简化（迭代式，避免深递归）。

    与 tdt-nav-kit ``simplifyPath(path, tol)`` 同目的：去掉"直线上多余的点"，
    减少下发点数与拐角数量；``tolerance_m`` 缺省取注册表 ``simplify_tolerance_m``。
    """
    p = params or PostprocessParams.from_registry()
    tol = float(tolerance_m if tolerance_m is not None else p.simplify_tolerance_m)
    points = [[float(pt[0]), float(pt[1])] for pt in path]
    if len(points) <= 2 or tol <= 0.0:
        return points

    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack: list[tuple[int, int]] = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        if end <= start + 1:
            continue
        ax, ay = points[start]
        bx, by = points[end]
        worst_index, worst_distance = -1, -1.0
        for index in range(start + 1, end):
            distance = point_segment_distance(points[index][0], points[index][1], ax, ay, bx, by)
            if distance > worst_distance:
                worst_index, worst_distance = index, distance
        if worst_distance > tol:
            keep[worst_index] = True
            stack.append((start, worst_index))
            stack.append((worst_index, end))
    return [point for point, flag in zip(points, keep) if flag]


# ---------------------------------------------------------------------------
# 转角混合（H13 任务书的 corner_blend）
# ---------------------------------------------------------------------------
def blend_corners(
    path: Sequence[Point],
    blend_m: float | None = None,
    samples: int | None = None,
    *,
    params: PostprocessParams | None = None,
) -> list[list[float]]:
    """在每个拐点两侧 ``blend_m`` 处切角，用二次贝塞尔采样替代尖角。

    端点不动；``blend_m`` 会自动被"相邻段长的一半"夹住，避免短段被吃穿。
    """
    p = params or PostprocessParams.from_registry()
    blend = float(blend_m if blend_m is not None else p.corner_blend_m)
    count = int(samples if samples is not None else p.corner_blend_samples)
    points = [[float(pt[0]), float(pt[1])] for pt in path]
    if len(points) < 3 or blend <= 0.0 or count < 1:
        return points

    out: list[list[float]] = [points[0]]
    for index in range(1, len(points) - 1):
        prev, corner, nxt = points[index - 1], points[index], points[index + 1]
        d_prev = math.hypot(corner[0] - prev[0], corner[1] - prev[1])
        d_next = math.hypot(nxt[0] - corner[0], nxt[1] - corner[1])
        if d_prev <= 1e-9 or d_next <= 1e-9:
            out.append(list(corner))
            continue
        cut = min(blend, d_prev * 0.5, d_next * 0.5)
        if cut <= 1e-9:
            out.append(list(corner))
            continue
        entry = [
            corner[0] + (prev[0] - corner[0]) * cut / d_prev,
            corner[1] + (prev[1] - corner[1]) * cut / d_prev,
        ]
        exit_ = [
            corner[0] + (nxt[0] - corner[0]) * cut / d_next,
            corner[1] + (nxt[1] - corner[1]) * cut / d_next,
        ]
        out.append(entry)
        for step in range(1, count + 1):
            t = step / (count + 1)
            one_minus = 1.0 - t
            out.append(
                [
                    one_minus * one_minus * entry[0] + 2 * one_minus * t * corner[0] + t * t * exit_[0],
                    one_minus * one_minus * entry[1] + 2 * one_minus * t * corner[1] + t * t * exit_[1],
                ]
            )
        out.append(exit_)
    out.append(points[-1])
    return out


# ---------------------------------------------------------------------------
# 航点外推微调（参考 rc_old nav_tools/route_candidate_optimizer.py）
# ---------------------------------------------------------------------------
def _rect_closest_point(px: float, py: float, obstacle: Obstacle) -> tuple[float, float]:
    cx, cy = float(obstacle[0]), float(obstacle[1])
    half_w, half_h = abs(float(obstacle[2])), abs(float(obstacle[3]))
    return (_clamp(px, cx - half_w, cx + half_w), _clamp(py, cy - half_h, cy + half_h))


def clearance_gradient(
    px: float, py: float, obstacles: Sequence[Obstacle]
) -> tuple[float, tuple[float, float] | None]:
    """返回 ``(到最近障碍的有符号距离, 推离方向单位向量)``；点在障碍内部时朝最近边推。"""
    best_distance = float("inf")
    best_direction: tuple[float, float] | None = None
    for obstacle in obstacles:
        distance = _point_rect_signed_distance(px, py, obstacle)
        if distance >= best_distance:
            continue
        qx, qy = _rect_closest_point(px, py, obstacle)
        dx, dy = px - qx, py - qy
        norm = math.hypot(dx, dy)
        if norm > 1e-9:
            best_direction = (dx / norm, dy / norm)
        else:  # 点在矩形内部：朝最近的那条边推
            cx, cy = float(obstacle[0]), float(obstacle[1])
            half_w, half_h = abs(float(obstacle[2])), abs(float(obstacle[3]))
            gaps = (
                (px - (cx - half_w), -1.0, 0.0),
                ((cx + half_w) - px, 1.0, 0.0),
                (py - (cy - half_h), 0.0, -1.0),
                ((cy + half_h) - py, 0.0, 1.0),
            )
            _, dir_x, dir_y = min(gaps, key=lambda item: item[0])
            best_direction = (dir_x, dir_y)
        best_distance = distance
    return best_distance, best_direction


def relax_waypoints(
    path: Sequence[Point],
    obstacles: Sequence[Obstacle] | None = None,
    params: PostprocessParams | None = None,
) -> list[list[float]]:
    """逐点推离 + 平滑迭代，把净空不足的航点推到 ``required_clearance`` 之外。

    与 ``route_candidate_optimizer.optimize_points`` 同结构：每轮算 delta（推离 + 平滑，
    平滑项是"朝相邻两点中点靠"乘 ``smooth_weight``），再按 ``max_move_per_iter`` 与
    ``max_total_move`` **双重限幅**；``relax_lock_ends`` 时首末点锁死（起终点不能被挪）。
    """
    p = params or PostprocessParams.from_registry()
    pts = [[float(pt[0]), float(pt[1])] for pt in path]
    obs = list(obstacles or [])
    if len(pts) < 3 or not obs or p.relax_iterations <= 0:
        return pts

    # 推离目标 = required + buffer：段的净空还取决于"角点到线段"距离（段可能从障碍角点旁
    # 掠过、比两端点都更贴），只推到 required 会恰好卡在边界、段仍判 VIOLATION（实测踩过）。
    required = p.required_clearance_m + p.relax_buffer_m
    moved = [0.0] * len(pts)
    locked = {0, len(pts) - 1} if p.relax_lock_ends else set()

    def try_move(index: int, dx: float, dy: float) -> None:
        """限幅 + **净空单调不减**校验后应用位移（不合格就整步丢弃）。"""
        norm = math.hypot(dx, dy)
        if norm <= 1e-12:
            return
        limit = min(p.relax_max_move_per_iter_m, p.relax_max_total_move_m - moved[index])
        if limit <= 0.0:
            return
        if norm > limit:
            dx *= limit / norm
            dy *= limit / norm
            norm = limit
        before, _ = clearance_gradient(pts[index][0], pts[index][1], obs)
        after, _ = clearance_gradient(pts[index][0] + dx, pts[index][1] + dy, obs)
        if after < before:
            return
        pts[index][0] += dx
        pts[index][1] += dy
        moved[index] += norm

    for _ in range(int(p.relax_iterations)):
        # ① 推离：把净空不足的点沿"远离最近障碍"方向推出 required_clearance。
        #    **必须与平滑分开做**：若两者加权平均，绕障碍拐角处平滑会把净位移拉向障碍一侧，
        #    单调校验于是拒绝整步、点永远推不动（本模块实测踩过：净空卡在 0.255 < 0.26）。
        for index in range(1, len(pts) - 1):
            if index in locked:
                continue
            distance, direction = clearance_gradient(pts[index][0], pts[index][1], obs)
            if direction is None:
                continue
            shortfall = required - distance
            if shortfall <= 0.0:
                continue
            step = min(p.relax_max_move_per_iter_m, shortfall * p.relax_step_scale)
            try_move(index, direction[0] * step, direction[1] * step)
        # ② 平滑：朝相邻两点中点靠（只在"不减少净空"时才生效）
        if p.relax_smooth_weight > 0.0:
            for index in range(1, len(pts) - 1):
                if index in locked:
                    continue
                avg_x = 0.5 * (pts[index - 1][0] + pts[index + 1][0])
                avg_y = 0.5 * (pts[index - 1][1] + pts[index + 1][1])
                try_move(
                    index,
                    (avg_x - pts[index][0]) * p.relax_smooth_weight,
                    (avg_y - pts[index][1]) * p.relax_smooth_weight,
                )
    return pts


# ---------------------------------------------------------------------------
# 一体化评审
# ---------------------------------------------------------------------------
def review_route(
    path: Sequence[Point],
    obstacles: Sequence[Obstacle] | None,
    params: PostprocessParams | None = None,
    *,
    simplify: bool = False,
    relax: bool = False,
    blend: bool = False,
) -> dict[str, Any]:
    """对一条路径做（可选）简化 / 推离微调 / 转角混合 + 净空分级。

    ``summary.blocked`` 为真表示存在 ``INTERSECT``/``VIOLATION`` ⇒ **拒绝下发**
    （H13 验收："TIGHT 标黄、VIOLATION 拒绝下发"）。
    """
    p = params or PostprocessParams.from_registry()
    processed = [[float(pt[0]), float(pt[1])] for pt in path]
    if simplify:
        processed = simplify_path(processed, params=p)
    if blend:
        processed = blend_corners(processed, params=p)
    if relax:
        # **relax 必须最后**：blend 会在拐角插入新点，这些点同样要过净空推离
        # （顺序反了的话插进去的圆角点没人管，照样 VIOLATION——本模块实测踩过）。
        processed = relax_waypoints(processed, obstacles, p)

    risks = classify_segments(processed, obstacles, p)
    counts = {level: 0 for level in CLEARANCE_LEVELS}
    for risk in risks:
        counts[risk.status_with(p.warn_margin_m)] += 1
    total_length = sum(risk.length_m for risk in risks)
    blocked = counts["INTERSECT"] > 0 or counts["VIOLATION"] > 0
    return {
        "path": processed,
        "segments": [risk.as_dict(p.warn_margin_m) for risk in risks],
        "summary": {
            **counts,
            "segment_count": len(risks),
            "total_length_m": round(total_length, 4),
            "blocked": blocked,
            "worst_status": _worst_status(counts),
        },
        "footprint_radius_m": p.footprint_radius_m,
        "required_clearance_m": round(p.required_clearance_m, 4),
        "simplified": simplify,
        "relaxed": relax,
        "corner_blended": blend,
        "params_source": PARAMS_SOURCE,
    }


def _worst_status(counts: dict[str, int]) -> str:
    for level in reversed(CLEARANCE_LEVELS):
        if counts.get(level):
            return level
    return "OK"


def postprocess_route(
    path: Sequence[Point],
    obstacles: Sequence[Obstacle] | None,
    params: PostprocessParams | None = None,
) -> dict[str, Any]:
    """完整后处理链：简化 → **推离微调** → 转角混合 → 净空分级（H13 的默认管线）。"""
    return review_route(path, obstacles, params, simplify=True, relax=True, blend=True)
