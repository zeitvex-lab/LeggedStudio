"""H12 跟随状态机 + 卡死恢复（服务端唯一实现）。

**这次不造轮子**：控制器律、状态划分与判据形状全部对齐参考实现
``00_resources/rc_old/.../sim2sim/nav_route_sim2sim_check.py`` 的 ``WaypointFollower``
（``SimConfig`` 在 81–117 行，跟随逻辑在 395–640 行）：

* 朝前视点走：``wz = clamp(kp_yaw·yaw_err, ±max_wz)``；仅当 ``|yaw_err| ≤ 45°`` 才给
  ``vx = clamp(kp_dist·dist·cos(yaw_err), 0, speed_limit)``（cos 门控，不是线性衰减）；
* 大误差**原地转**：``|yaw_err| ≥ 70°`` 进入、``≤ 18°`` 退出（滞回）；
* **卡死恢复**：``stuck_timeout_s`` 内前视距离无 ``stuck_progress_m`` 进展 ⇒ 发 2 s 恢复动作
  ``vx = -0.10, wz = 0.45·sign``（符号每轮翻转），至多 ``max_recoveries`` 轮；
* 判据三类：``complete``（走完全程）/ ``timeout``（单航点超时）/ ``stuck``（恢复用尽）。

**判据/阈值的两个来源（都不在本文件里硬编码）**：

* 跟随与恢复参数 → ``registry/motion_commands.json`` 的 ``follow_controller``（H12）；
* 到达容差与稳定拍数 → ``registry/arrival_criteria.json``（H10，唯一真值）。

**终止原因分层抄 LightNav**（``vlnce.py:488-627``）：``complete / timeout / stuck / truncated
/ undefined``——其中 ``truncated`` 表示"被总时长预算拉停"，**不是策略结论**，必须与
"策略失败"分开记（这正是参考项目里最值得抄的一条约定）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal, Sequence

TerminationReason = Literal["complete", "timeout", "stuck", "truncated", "undefined"]


def normalize_angle(angle: float) -> float:
    while angle > math.pi:
        angle -= 2 * math.pi
    while angle <= -math.pi:
        angle += 2 * math.pi
    return angle


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class FollowParams:
    """跟随参数（全部来自 ``registry/motion_commands.json``）。"""

    lookahead_m: float
    max_vx: float
    max_vy: float
    max_wz: float
    kp_dist: float
    kp_yaw: float
    yaw_stop_threshold_deg: float
    turn_in_place_enter_deg: float
    turn_in_place_exit_deg: float
    turn_in_place_max_wz: float
    waypoint_timeout_s: float
    max_total_time_s: float
    stuck_timeout_s: float
    stuck_progress_m: float
    recovery_duration_s: float
    max_recoveries: int
    recovery_vx_factor: float
    recovery_wz_factor: float

    @classmethod
    def from_registry(cls) -> "FollowParams":
        """从注册表读参数；缺块或缺字段**直接报错**（不静默用默认值）。"""
        from backend.motion_commands import follow_controller_spec

        spec = follow_controller_spec()
        recovery = spec.get("recovery_cmd") or {}
        fields = {
            "lookahead_m": spec.get("lookahead_m"),
            "max_vx": spec.get("max_vx"),
            "max_vy": spec.get("max_vy", 0.0),
            "max_wz": spec.get("max_wz"),
            "kp_dist": spec.get("kp_dist"),
            "kp_yaw": spec.get("kp_yaw"),
            "yaw_stop_threshold_deg": spec.get("yaw_stop_threshold_deg"),
            "turn_in_place_enter_deg": spec.get("turn_in_place_enter_deg"),
            "turn_in_place_exit_deg": spec.get("turn_in_place_exit_deg"),
            "turn_in_place_max_wz": spec.get("turn_in_place_max_wz"),
            "waypoint_timeout_s": spec.get("waypoint_timeout_s"),
            "max_total_time_s": spec.get("max_total_time_s"),
            "stuck_timeout_s": spec.get("stuck_timeout_s"),
            "stuck_progress_m": spec.get("stuck_progress_m"),
            "recovery_duration_s": spec.get("recovery_duration_s"),
            "max_recoveries": spec.get("max_recoveries"),
            "recovery_vx_factor": recovery.get("vx_factor"),
            "recovery_wz_factor": recovery.get("wz_factor"),
        }
        missing = [name for name, value in fields.items() if value is None]
        if missing:
            raise ValueError(
                f"registry/motion_commands.json 的 follow_controller 缺字段 {missing}；"
                "跟随参数只有这一处真值，缺了就报错，不用代码里的旧默认值兜底"
            )
        return cls(**fields)  # type: ignore[arg-type]


@dataclass
class FollowStep:
    """一拍的结果（指令 + 事件 + 状态，便于 episode 里看见状态迁移）。"""

    cmd: list[float]
    event: str | None
    state: str
    waypoint_index: int
    distance_m: float
    termination_reason: TerminationReason | None = None


class FollowController:
    """单航点序列的跟随状态机（纯 Python，无 MuJoCo/NumPy 依赖）。

    用法::

        controller = FollowController(waypoints, tolerances=..., stable_ticks=...)
        while True:
            step = controller.update(pose=(x, y, yaw), time_s=t)
            if step.termination_reason:
                break
    """

    def __init__(
        self,
        waypoints: Sequence[Sequence[float]],
        *,
        params: FollowParams | None = None,
        tolerances: Sequence[float] | None = None,
        stable_ticks: int | None = None,
    ) -> None:
        if len(waypoints) < 2:
            raise ValueError("跟随至少需要两个航点（起点与目标）")
        self.waypoints = [[float(p[0]), float(p[1])] for p in waypoints]
        self.params = params or FollowParams.from_registry()

        if tolerances is None or stable_ticks is None:
            # H10：容差与稳定拍数只有一处真值
            from backend.arrival_criteria import waypoint_spec

            spec = waypoint_spec()
            tolerances = tolerances if tolerances is not None else [float(spec["tolerance_m"])] * len(self.waypoints)
            stable_ticks = stable_ticks if stable_ticks is not None else int(spec["stable_ticks"])
        if len(tolerances) != len(self.waypoints):
            raise ValueError("tolerances 数量必须与航点数一致")
        self.tolerances = [float(t) for t in tolerances]
        self.stable_ticks = max(1, int(stable_ticks))

        self.reset()

    # ---------- 状态 ----------
    def reset(self, time_s: float = 0.0) -> None:
        self.index = 1  # 起点视为已到位
        self.turn_in_place = False
        self.stable_count = 0
        self.waypoint_start_time = time_s
        self.best_distance = float("inf")
        self.last_progress_time = time_s
        self.recovery_until = -1.0
        self.recovery_count = 0
        self.recovery_sign = 1.0
        self.finished = len(self.waypoints) <= 1
        self.reason: TerminationReason | None = None

    @property
    def active(self) -> list[float]:
        return self.waypoints[min(self.index, len(self.waypoints) - 1)]

    def _lookahead_target(self, x: float, y: float) -> list[float]:
        """前视点：跳过近处已消费的点，取第一个 ≥ lookahead 的点（参考实现同法）。"""
        target = self.waypoints[min(self.index, len(self.waypoints) - 1)]
        for i in range(self.index, len(self.waypoints)):
            target = self.waypoints[i]
            if math.hypot(target[0] - x, target[1] - y) >= self.params.lookahead_m:
                break
        return target

    # ---------- 一拍 ----------
    def update(self, pose: Sequence[float], time_s: float) -> FollowStep:
        x, y, yaw = float(pose[0]), float(pose[1]), float(pose[2])
        if self.reason is not None:
            return self._step([0.0, 0.0, 0.0], None, "done", time_s, 0.0)

        if time_s > self.params.max_total_time_s:
            # 预算拉停 ≠ 策略失败（LightNav 的 truncated 语义）
            self.reason = "truncated"
            return self._step([0.0, 0.0, 0.0], "truncated", "truncated", time_s, 0.0)

        active = self.active
        dx, dy = active[0] - x, active[1] - y
        distance = math.hypot(dx, dy)

        # 1) 到达判定：容差内连续 stable_ticks 拍（H10 真值）
        if distance <= self.tolerances[self.index]:
            self.stable_count += 1
            if self.stable_count >= self.stable_ticks:
                self.index += 1
                self.turn_in_place = False
                self.stable_count = 0
                self.waypoint_start_time = time_s
                self.best_distance = float("inf")
                self.last_progress_time = time_s
                if self.index >= len(self.waypoints):
                    self.reason = "complete"
                    return self._step([0.0, 0.0, 0.0], "complete", "done", time_s, distance)
                return self._step([0.0, 0.0, 0.0], "advance", "arrived", time_s, distance)
            return self._step([0.0, 0.0, 0.0], None, "settling", time_s, distance)
        self.stable_count = 0

        # 2) 单航点超时
        if time_s - self.waypoint_start_time > self.params.waypoint_timeout_s:
            self.reason = "timeout"
            return self._step([0.0, 0.0, 0.0], "timeout", "timeout", time_s, distance)

        # 3) 卡死恢复
        if distance + self.params.stuck_progress_m < self.best_distance:
            self.best_distance = distance
            self.last_progress_time = time_s
        if self.recovery_until > time_s:
            cmd = [
                self.params.recovery_vx_factor,
                0.0,
                self.params.recovery_wz_factor * self.recovery_sign,
            ]
            return self._step(cmd, "recovery", "recovery", time_s, distance)
        if time_s - self.last_progress_time > self.params.stuck_timeout_s:
            if self.recovery_count >= self.params.max_recoveries:
                self.reason = "stuck"
                return self._step([0.0, 0.0, 0.0], "stuck", "stuck", time_s, distance)
            self.recovery_count += 1
            self.recovery_sign *= -1.0
            self.recovery_until = time_s + self.params.recovery_duration_s
            self.last_progress_time = time_s  # 恢复期后重新计时，避免立即再判卡死
            cmd = [
                self.params.recovery_vx_factor,
                0.0,
                self.params.recovery_wz_factor * self.recovery_sign,
            ]
            return self._step(cmd, "recovery", "recovery", time_s, distance)

        # 4) 跟随（参考实现形状：滞回原地转 + cos 门控前进）
        target = self._lookahead_target(x, y)
        target_yaw = math.atan2(target[1] - y, target[0] - x)
        yaw_err = normalize_angle(target_yaw - yaw)
        if self.turn_in_place:
            if abs(yaw_err) <= math.radians(self.params.turn_in_place_exit_deg):
                self.turn_in_place = False
        elif abs(yaw_err) >= math.radians(self.params.turn_in_place_enter_deg):
            self.turn_in_place = True

        if self.turn_in_place:
            wz = _clamp(self.params.kp_yaw * yaw_err, -self.params.turn_in_place_max_wz, self.params.turn_in_place_max_wz)
            return self._step([0.0, 0.0, wz], None, "turn_in_place", time_s, distance)

        lookahead_distance = math.hypot(target[0] - x, target[1] - y)
        vx = 0.0
        if abs(yaw_err) <= math.radians(self.params.yaw_stop_threshold_deg):
            vx = _clamp(
                self.params.kp_dist * lookahead_distance * math.cos(yaw_err),
                0.0,
                min(self.params.max_vx, self.params.max_vx),
            )
        wz = _clamp(self.params.kp_yaw * yaw_err, -self.params.max_wz, self.params.max_wz)
        return self._step([vx, 0.0, wz], None, "following", time_s, distance)

    def _step(self, cmd: list[float], event: str | None, state: str, time_s: float, distance: float) -> FollowStep:
        return FollowStep(
            cmd=[round(float(value), 6) for value in cmd],
            event=event,
            state=state,
            waypoint_index=self.index,
            distance_m=round(distance, 4),
            termination_reason=self.reason,
        )

    # ---------- 结论（抄 LightNav 的分层：策略停止 / 预算截断 分开） ----------
    def verdict(self) -> dict[str, Any]:
        reason: TerminationReason = self.reason or "undefined"
        completed = self.index >= len(self.waypoints) - 1 and reason in ("complete", "truncated")
        return {
            "verdict": "pass" if reason == "complete" else ("partial" if reason == "truncated" else "fail"),
            "termination_reason": reason,
            "waypoints_reached": max(0, self.index - 1),
            "waypoints_total": len(self.waypoints) - 1,
            "route_completion": round(max(0.0, (self.index - 1)) / max(1, len(self.waypoints) - 1), 4),
            "recoveries_used": self.recovery_count,
            "details": {
                "completed_route": bool(completed),
                "is_strategy_verdict": reason in ("complete", "timeout", "stuck"),
                "note": "truncated/undefined 不是策略结论（预算拉停 / 判据未定义）",
            },
        }


def follow_controller_selftest() -> dict[str, Any]:
    """自检：注册表可读、参数齐全、一条直线航线能走完（供 CI 快速验证判据链路）。"""
    params = FollowParams.from_registry()
    controller = FollowController([[0.0, 0.0], [2.0, 0.0]], params=params)
    time_s = 0.0
    x = 0.0
    steps = 0
    while controller.reason is None and steps < 2000:
        step = controller.update([x, 0.0, 0.0], time_s)
        x += step.cmd[0] * 0.02
        time_s += 0.02
        steps += 1
    return {
        "params_source": "registry/motion_commands.json#follow_controller",
        "arrival_source": "registry/arrival_criteria.json",
        "lookahead_m": params.lookahead_m,
        "steps": steps,
        "x_m": round(x, 3),
        **controller.verdict(),
    }
