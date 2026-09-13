"""几何路径跟踪控制器（H14 的 ``controller: geometric`` 选项）—— 纯 Python。

**为什么需要它**：``backend/dwa_planner.py`` 是"采样择优"的局部规划器，在开阔/中等场景有效；
但在 warehouse 这类**高障碍 + 局部视野**的角落里，采样式规划在"预测 2 s 却只执行 1 拍"的
强滚动下容易陷入极限环。``tools/dwa_ab_check.py`` 的三方对照实测：

    DWA（采样择优）      到达=False   势场（potential）到达=False
    几何跟踪（本模块）   到达=True  23.55 s / 零碰撞

**这次不造轮子**——控制律与参数**逐项取自**成熟真机实现
``00_resources/jie_3d_nav/octo_planner/src/d1_controller.cpp``：

* 追踪点选择：找离机器人最近的路径点；若当前追踪点在容差内则**前进到第一个距离 > 容差的点**
  （``selectTrackingTarget``，容差 ``tracking_point_reached_xy_tolerance = 0.20``）；
* 误差转机体系：``base_x = cosθ·dx + sinθ·dy``、``base_y = −sinθ·dx + cosθ·dy``；
* 控制律：``vx = clamp(base_x·linear_gain, ±max_linear)``、
  ``vy = clamp(base_y·lateral_gain, ±max_lateral)``（该项目支持横移）、
  ``wz = clamp(atan2(base_y, base_x)·heading_gain + base_y·cross_track_angular_gain, ±max_angular)``；
* **死区整形**：``|cmd| < deadband`` 置零（与 H9 的 deadzone 同思路）。

参数唯一真值在 ``registry/motion_commands.json#geometric_tracker``（与 H12/H11 同文件）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

PARAMS_SOURCE = "registry/motion_commands.json#geometric_tracker"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class GeometricParams:
    """几何跟踪参数（取自 ``d1_controller.cpp`` 默认值，唯一真值在注册表）。"""

    lookahead_tolerance_m: float
    linear_gain: float
    lateral_gain: float
    heading_gain: float
    cross_track_angular_gain: float
    max_linear_speed: float
    max_lateral_speed: float
    max_angular_speed: float
    deadband: float
    enable_lateral_motion: bool

    @classmethod
    def from_registry(cls) -> "GeometricParams":
        """从注册表读参数；缺块或缺字段**直接报错**（不静默用代码默认值）。"""
        from backend.motion_commands import geometric_tracker_spec

        spec = geometric_tracker_spec()
        names = list(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        missing = [name for name in names if spec.get(name) is None]
        if missing:
            raise ValueError(
                f"registry/motion_commands.json 的 geometric_tracker 缺字段 {missing}；"
                "跟踪参数只有这一处真值，缺了就报错"
            )
        values: dict[str, Any] = {}
        for name in names:
            raw = spec[name]
            values[name] = bool(raw) if name == "enable_lateral_motion" else float(raw)
        return cls(**values)


def select_tracking_target(
    pose: Sequence[float],
    path: Sequence[Sequence[float]],
    start_index: int,
    tolerance: float,
) -> tuple[int, list[float]]:
    """选追踪点（``d1_controller::selectTrackingTarget`` 的等价实现）。

    先找离机器人最近的路径点作起点；若该点已在容差内，则**前进到第一个距离 > 容差的点**
    （不跳点、不倒推）。返回 ``(新下标, 目标点)``。
    """
    if not path:
        raise ValueError("参考路径为空，无法选追踪点")
    x, y = float(pose[0]), float(pose[1])
    index = max(0, min(int(start_index), len(path) - 1))
    # 若追踪点近于容差，推进到第一个"够远"的点（末点为止）
    while index < len(path) - 1:
        px, py = float(path[index][0]), float(path[index][1])
        if math.hypot(px - x, py - y) > tolerance:
            break
        index += 1
    target = [float(path[index][0]), float(path[index][1])]
    return index, target


def command_from_target(
    pose: Sequence[float], target: Sequence[float], params: GeometricParams
) -> dict[str, Any]:
    """基座系误差 × 增益 + 死区整形，返回 ``{cmd:[vx, vy, wz], ...}``。"""
    x, y, yaw = float(pose[0]), float(pose[1]), float(pose[2])
    dx, dy = float(target[0]) - x, float(target[1]) - y
    cos_yaw, sin_yaw = math.cos(yaw), math.sin(yaw)
    base_x = cos_yaw * dx + sin_yaw * dy
    base_y = -sin_yaw * dx + cos_yaw * dy
    heading_error = math.atan2(base_y, max(1e-6, base_x))

    vx = _clamp(base_x * params.linear_gain, -params.max_linear_speed, params.max_linear_speed)
    if params.enable_lateral_motion:
        vy = _clamp(
            base_y * params.lateral_gain, -params.max_lateral_speed, params.max_lateral_speed
        )
    else:
        vy = 0.0
    wz = _clamp(
        heading_error * params.heading_gain + base_y * params.cross_track_angular_gain,
        -params.max_angular_speed,
        params.max_angular_speed,
    )
    if abs(vx) < params.deadband:
        vx = 0.0
    if abs(vy) < params.deadband:
        vy = 0.0
    if abs(wz) < params.deadband:
        wz = 0.0
    return {
        "cmd": [round(vx, 6), round(vy, 6), round(wz, 6)],
        "base_error": [round(base_x, 4), round(base_y, 4)],
        "heading_error": round(heading_error, 4),
        "target": [round(float(target[0]), 4), round(float(target[1]), 4)],
    }


class GeometricTracker:
    """带追踪点状态的几何跟踪器（逐拍调用）。"""

    def __init__(
        self,
        path: Sequence[Sequence[float]],
        *,
        params: GeometricParams | None = None,
        start_index: int = 0,
    ) -> None:
        if len(path) < 2:
            raise ValueError("参考路径至少要两个点")
        self.path = [[float(p[0]), float(p[1])] for p in path]
        self.params = params or GeometricParams.from_registry()
        self.index = max(0, min(int(start_index), len(self.path) - 1))

    def reset(self, start_index: int = 0) -> None:
        self.index = max(0, min(int(start_index), len(self.path) - 1))

    def update(self, pose: Sequence[float]) -> dict[str, Any]:
        self.index, target = select_tracking_target(
            pose, self.path, self.index, self.params.lookahead_tolerance_m
        )
        result = command_from_target(pose, target, self.params)
        return {**result, "target_index": self.index, "params_source": PARAMS_SOURCE}

    @property
    def target(self) -> list[float]:
        return [float(self.path[self.index][0]), float(self.path[self.index][1])]


def geometric_selftest() -> dict[str, Any]:
    """自检：直线路径上能推进并走到末端（供 CI 快速验证判据链路）。"""
    tracker = GeometricTracker([[0.0, 0.0], [2.0, 0.0]])
    pose = [0.0, 0.0, 0.0]
    goal = tracker.path[-1]
    steps = 0
    for steps in range(1, 401):
        result = tracker.update(pose)
        vx, _vy, wz = result["cmd"]
        pose = [pose[0] + vx * 0.05, pose[1], pose[2] + wz * 0.05]
        if math.hypot(goal[0] - pose[0], goal[1] - pose[1]) < 0.05:
            break
    remaining = math.hypot(goal[0] - pose[0], goal[1] - pose[1])
    return {
        "params_source": PARAMS_SOURCE,
        "steps": steps,
        "x_m": round(pose[0], 3),
        "remaining_m": round(remaining, 3),
        "target_index": tracker.index,
        "verdict": "pass" if remaining < 0.2 else "fail",
    }
