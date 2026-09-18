"""H12 跟随状态机 + 卡死恢复（服务端唯一实现）。

**这次不造轮子**：控制器律、状态划分与判据形状全部对齐参考实现
``00_resources/rc_old/.../sim2sim/nav_route_sim2sim_check.py`` 的 ``WaypointFollower``
（``SimConfig`` 在 81–117 行，跟随逻辑在 395–640 行）：

* 朝前视点走：``wz = clamp(kp_yaw·yaw_err, ±max_wz)``；仅当 ``|yaw_err| ≤ 45°`` 才给
  ``vx = clamp(kp_dist·dist·cos(yaw_err), 0, speed_limit)``（cos 门控，不是线性衰减）；
* **接近减速（v0.55.48，H12 登记短板「0.2m 容差过冲振荡」的收口）**：只在**最后一段**
  （活跃航点即最终航点）且距最终航点 ``< goal_slowdown_m`` 时，vx 上限按剩余距离比例
  收紧 ``vx_cap = max_vx·clamp(dist/goal_slowdown_m, goal_slowdown_min_scale, 1)``
  （``min_scale`` 是上限地板，保证最后几十厘米走得完；``wz`` 与中途跟随语义不变）。
  标定约束：``goal_slowdown_m`` 必须 > ``max_vx/kp_dist``（1.2/0.8 = 1.5m）上限才会真正
  压住自然律，取 2.4m ⇒ 等效达点时间常数 2.0s（1m→0.5 m/s、0.5m→0.25 m/s）。
* 大误差**原地转**：``|yaw_err| ≥ 70°`` 进入、``≤ 18°`` 退出（滞回）；
* **卡死恢复**：``stuck_timeout_s`` 内无"目标导向进展" ⇒ 发 2 s 恢复动作
  ``vx = -0.10, wz = 0.45·sign``（符号每轮翻转），至多 ``max_recoveries`` 轮。
  进展有两类口径（v0.55.46 收口裁决，修"拐角急转误触卡死"）：
  朝**前视目标**逼近 ≥ ``stuck_progress_m``（不是到当前航点的距离——拐角切角后当前
  航点在身后，距离不缩反涨，按旧口径 135° 拐角必误判）；或 ``turn_in_place`` 期间
  航向误差收敛 ≥ ``stuck_turn_progress_deg``（真机 180° 急转超 4s，不能按位移判卡死；
  朝向冻住的真卡死两项都不成立 ⇒ 照常触发恢复）；
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
    goal_slowdown_m: float
    goal_slowdown_min_scale: float
    yaw_stop_threshold_deg: float
    turn_in_place_enter_deg: float
    turn_in_place_exit_deg: float
    turn_in_place_max_wz: float
    waypoint_timeout_s: float
    max_total_time_s: float
    stuck_timeout_s: float
    stuck_progress_m: float
    stuck_turn_progress_deg: float
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
            # v0.55.48 接近减速：最后一段按剩余距离比例收紧 vx 上限（浏览器镜像同字段）
            "goal_slowdown_m": spec.get("goal_slowdown_m"),
            "goal_slowdown_min_scale": spec.get("goal_slowdown_min_scale"),
            "yaw_stop_threshold_deg": spec.get("yaw_stop_threshold_deg"),
            "turn_in_place_enter_deg": spec.get("turn_in_place_enter_deg"),
            "turn_in_place_exit_deg": spec.get("turn_in_place_exit_deg"),
            "turn_in_place_max_wz": spec.get("turn_in_place_max_wz"),
            "waypoint_timeout_s": spec.get("waypoint_timeout_s"),
            "max_total_time_s": spec.get("max_total_time_s"),
            "stuck_timeout_s": spec.get("stuck_timeout_s"),
            "stuck_progress_m": spec.get("stuck_progress_m"),
            "stuck_turn_progress_deg": spec.get("stuck_turn_progress_deg"),
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
        self.best_heading_err = float("inf")
        self.progress_target_index: int | None = None
        self.last_progress_time = time_s
        self.recovery_until = -1.0
        self.recovery_count = 0
        self.recovery_sign = 1.0
        self.finished = len(self.waypoints) <= 1
        self.reason: TerminationReason | None = None

    @property
    def active(self) -> list[float]:
        return self.waypoints[min(self.index, len(self.waypoints) - 1)]

    def _lookahead_index(self, x: float, y: float) -> int:
        """前视点**下标**：跳过近处已消费的点，取第一个 ≥ lookahead 的点（参考实现同法）。

        返回下标而不是坐标：进展登记要识别"前视目标切换了"（切换 ⇒ 换基准重记，
        见 update 的进展登记段），下标是稳定身份（两个航点可能坐标相同）。
        """
        for i in range(min(self.index, len(self.waypoints) - 1), len(self.waypoints)):
            wp = self.waypoints[i]
            if math.hypot(wp[0] - x, wp[1] - y) >= self.params.lookahead_m:
                return i
        return len(self.waypoints) - 1

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
                self.best_heading_err = float("inf")
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

        # 3) 卡死恢复 —— 进展按"目标导向运动"登记（v0.55.46 收口裁决）
        target_index = self._lookahead_index(x, y)
        target = self.waypoints[target_index]
        if target_index != self.progress_target_index:
            # 前视目标切换 ⇒ 进展基准对新目标重记（切换本身既不算进展也不算倒退）。
            # 浏览器镜像：web/sim2sim/navigation.js tick() 的 progressTargetIndex 同款。
            self.progress_target_index = target_index
            self.best_distance = float("inf")
            self.best_heading_err = float("inf")
        pursuit_dx, pursuit_dy = target[0] - x, target[1] - y
        pursuit_distance = math.hypot(pursuit_dx, pursuit_dy)
        yaw_err = normalize_angle(math.atan2(pursuit_dy, pursuit_dx) - yaw)

        # 原地转滞回（参考实现形状）。提前到进展登记之前：turn_in_place 态决定
        # 进展的第二类口径（航向收敛），跟随律复用同一份状态，不重复判定。
        if self.turn_in_place:
            if abs(yaw_err) <= math.radians(self.params.turn_in_place_exit_deg):
                self.turn_in_place = False
        elif abs(yaw_err) >= math.radians(self.params.turn_in_place_enter_deg):
            self.turn_in_place = True

        # 3a) 进展登记，两类任一成立即刷新 last_progress_time：
        #   * 朝前视目标逼近 ≥ stuck_progress_m（直线/弧线推进；拐角切角后机器人追的
        #     是前视目标，到"身后当前航点"的距离不缩反涨——旧口径因此误判卡死）；
        #   * turn_in_place 期间航向误差收敛 ≥ stuck_turn_progress_deg（原地急转是
        #     目标导向运动，真机 180° 急转可超 4s）。被夹住转不动的真卡死两项都不
        #     成立 ⇒ 恢复照常触发，急转豁免不会吞掉真卡死。
        if pursuit_distance + self.params.stuck_progress_m < self.best_distance:
            self.best_distance = pursuit_distance
            self.last_progress_time = time_s
        if self.turn_in_place:
            heading_err = abs(yaw_err)
            if heading_err + math.radians(self.params.stuck_turn_progress_deg) < self.best_heading_err:
                self.best_heading_err = heading_err
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

        # 4) 跟随（参考实现形状：滞回原地转 + cos 门控前进；target/yaw_err 复用上面）
        if self.turn_in_place:
            wz = _clamp(self.params.kp_yaw * yaw_err, -self.params.turn_in_place_max_wz, self.params.turn_in_place_max_wz)
            return self._step([0.0, 0.0, wz], None, "turn_in_place", time_s, distance)

        # 接近减速（v0.55.48）：仅**最后一段**（活跃航点即最终航点）且距最终航点
        # < goal_slowdown_m 时，vx 上限按剩余距离比例收紧——修 H12 登记短板
        # 「0.2m 容差过冲振荡」（匀速冲线 → 过冲 → stable_ticks=2 攒不上）。
        #   vx_cap = max_vx · clamp(dist/goal_slowdown_m, goal_slowdown_min_scale, 1)
        # min_scale 是上限地板（最后几十厘米仍有 0.24 m/s 前进余量，不熄火）；
        # wz 不受影响；中途航点跟随语义不变（门控在 index==最后航点，折返航线中途
        # 靠近最终航点也不减速）。浏览器镜像：web/sim2sim/navigation.js command()
        # 的 isFinalLeg / vxLimit 同分支同参数（goal_slowdown_* 同源 registry）。
        # 标定：goal_slowdown_m 2.4 > max_vx/kp_dist 1.5，上限才压得住自然律
        # （等效达点时间常数 2.0s）；推导见 registry/motion_commands.json#follow_controller note。
        vx_limit = self.params.max_vx
        if self.index == len(self.waypoints) - 1 and distance < self.params.goal_slowdown_m:
            scale = _clamp(distance / self.params.goal_slowdown_m, self.params.goal_slowdown_min_scale, 1.0)
            vx_limit = min(vx_limit, self.params.max_vx * scale)

        vx = 0.0
        if abs(yaw_err) <= math.radians(self.params.yaw_stop_threshold_deg):
            vx = _clamp(
                self.params.kp_dist * pursuit_distance * math.cos(yaw_err),
                0.0,
                vx_limit,
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
