"""H12 跟随状态机 + 卡死恢复（服务端唯一实现）。

**这次不造轮子**：控制器律、状态划分与判据形状全部对齐参考实现
``00_resources/rc_old/.../sim2sim/nav_route_sim2sim_check.py`` 的 ``WaypointFollower``
（``SimConfig`` 在 81–117 行，跟随逻辑在 395–640 行）：

* 朝前视点走：``wz = clamp(kp_yaw·yaw_err, ±max_wz)``；仅当 ``|yaw_err| ≤ 45°`` 才给
  ``vx = clamp(kp_dist·dist·cos(yaw_err), 0, speed_limit)``（cos 门控，不是线性衰减）。
  **前视点的取法（v0.55.50 改）**：目标 = 弧长游标前方 ``lookahead_m`` 处的**路径点**
  （``_point_at``，纯追踪一族的口径）——不再是从 index 起扫第一个"距机器人 ≥ lookahead
  的航点"。后者在 0.45 边界上**双稳翻转**（机器人距节点 < 0.45 ⇒ 该节点被跳过、目标
  切成远节点；机器人转身漂移后距离 ≥ 0.45 ⇒ 目标翻回**身后**的节点 ⇒ 无限振荡至
  超时，135° 稀疏拐角实测），弧长目标只沿路径向前，翻转从构造上消失。速度口径随之
  从"到远航点的距离"变为"到 lookahead 点的距离"（跟队巡航 ≈ ``kp_dist·lookahead`` =
  0.36 m/s，与浏览器侧密集路径上的既有巡航速度同档）；
* **接近减速（v0.55.48，H12 登记短板「0.2m 容差过冲振荡」的收口）**：只在**最后一段**
  （活跃航点即最终航点）且距最终航点 ``< goal_slowdown_m`` 时，vx 上限按剩余距离比例
  收紧 ``vx_cap = max_vx·clamp(dist/goal_slowdown_m, goal_slowdown_min_scale, 1)``
  （``min_scale`` 是上限地板，保证最后几十厘米走得完；``wz`` 与中途跟随语义不变）。
  标定约束：``goal_slowdown_m`` 必须 > ``max_vx/kp_dist``（1.2/0.8 = 1.5m）上限才会真正
  压住自然律，取 2.4m ⇒ 等效达点时间常数 2.0s（1m→0.5 m/s、0.5m→0.25 m/s）。
* 大误差**原地转**：``|yaw_err| ≥ 70°`` 进入、``≤ 18°`` 退出（滞回）；
* **切角消费（v0.55.50，H12 登记短板「稀疏长段路径 0.45 边界双稳翻转」收口）**：活跃航点
  若已被**走过**（弧长游标 ``progress_s`` 越过它的路径参数 ``cum[index]``）⇒ 视为消费、
  ``index`` 前进（**不**要求 H10 容差/稳定拍数——人已走过，不是"到达"；**最后一个节点
  不消费**，goal 仍须真到达）。判据 = **路径参数边界**（弧长投影），取代 v0.55.49 的
  「投影 > ``node_consume_proj`` **且** 距节点 < lookahead」双条件——那两个条件在
  **垂直拐角**上互斥（投影越过 0.65 要求越过拐点 0.65m，"须曾贴近"要求 < 0.45m；L 形
  1m 段上永远不能同时成立）⇒ 拐点永远无法消费 ⇒ 前视扫描把**身后**的拐点选成目标 ⇒
  目标航向在 ≈±160° 间**双稳翻转** ⇒ ``turn_in_place`` 无限旋转 ⇒ 30s 航点超时
  （00_know/90_归档/08_任务清单_阶段桶与队列_20260928.md §H12 登记的病象：8 档横向偏移全等 timeout）。弧长游标**单调向前**
  （只从游标所在段起投影、不回看）："折返路线起点节点被误消费"由单调性天然挡住
  （起点处游标 = 0，够不到 ``cum[1]``）；机器人绕到拐角另一侧（下一段投影 ≥ 0）游标
  才继续向前，否则钳在拐角节点上（还在拐角外侧 = 没走过拐角）。
  这是对参考实现 ``PathFollower._point_is_behind_segment`` 的**有意偏离**（其同为
  距离/投影口径，同样过不了垂直拐角）——偏离理由 = 该判据在参考场景（密集路径）成立，
  在本仓稀疏手填航点场景不成立；偏离与此登记同在，不回退。
* **卡死恢复**：``stuck_timeout_s`` 内无"目标导向进展" ⇒ 发 2 s 恢复动作
  ``vx = -0.10, wz = 0.45·sign``（符号每轮翻转），至多 ``max_recoveries`` 轮。
  进展有两类口径（v0.55.46 收口裁决，修"拐角急转误触卡死"）：
  **弧长游标推进 ≥ ``stuck_progress_m``**（v0.55.50 起的主口径——前视目标改成随机器人
  前移的路径点后，"到目标距离缩短"被目标前移抵消，失去量尺意义；沿路径真实走了多少
  才是进展。恢复后退不倒扣：游标单调）；或 ``turn_in_place`` 期间航向误差收敛 ≥
  ``stuck_turn_progress_deg``（真机 180° 急转超 4s，不能按位移判卡死；朝向冻住的真
  卡死两项都不成立 ⇒ 照常触发恢复）；
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
class _TrackSegment:
    """路径的一段（退化段除外）：单位方向 + 长度 + 起点累计弧长。

    弧长游标（``FollowController.progress_s``）的几何基础：投影只沿轨道段算，
    两点重合的段没有方向，进不了轨道（它们的航点在 ``_cum`` 里共享同一个弧长）。
    """

    ax: float
    ay: float
    ux: float
    uy: float
    length: float
    cum_start: float


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
        # 弧长表（v0.55.50 路径参数边界的几何基础）：_cum[i] = 第 i 个航点的累计弧长；
        # _track 只收非退化段（两点重合的段没有方向，投影无从谈起——其航点在 _cum 里
        # 与邻居共享同一个弧长，消费判据 progress_s >= cum[index] 不受影响）。
        self._cum: list[float] = [0.0]
        track: list[_TrackSegment] = []
        for i in range(len(self.waypoints) - 1):
            ax, ay = self.waypoints[i]
            bx, by = self.waypoints[i + 1]
            length = math.hypot(bx - ax, by - ay)
            self._cum.append(self._cum[-1] + length)
            if length > 1.0e-9:
                track.append(
                    _TrackSegment(
                        ax=ax,
                        ay=ay,
                        ux=(bx - ax) / length,
                        uy=(by - ay) / length,
                        length=length,
                        cum_start=self._cum[i],
                    )
                )
        self._track = track
        self._total = self._cum[-1]
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
        self.best_heading_err = float("inf")
        # v0.55.50：进展主口径 = 弧长游标推进（best_progress_s = 历史最远游标）；
        # 到前视目标的距离不再是进展量尺（目标随机器人前移，距离被抵消）。
        self.best_progress_s = 0.0
        self.last_progress_time = time_s
        self.recovery_until = -1.0
        self.recovery_count = 0
        self.recovery_sign = 1.0
        self.finished = len(self.waypoints) <= 1
        self.reason: TerminationReason | None = None
        # 弧长游标（v0.55.50）：机器人沿路径走了多少（米）。单调不回退——恢复动作后退
        # 不倒扣，绕到拐角另一侧才继续向前。消费判据 = 路径参数边界（见 _project_onto_path）。
        self.progress_s = 0.0

    @property
    def active(self) -> list[float]:
        return self.waypoints[min(self.index, len(self.waypoints) - 1)]

    def _segment_at(self, s: float) -> _TrackSegment | None:
        """弧长 ``s`` 所在的轨道段（``s`` 恰在节点上时取从该节点出发的那段）。"""
        for seg in reversed(self._track):
            if seg.cum_start <= s + 1.0e-9:
                return seg
        return None

    def _point_at(self, s: float) -> list[float]:
        """弧长 ``s`` 处的路径点（超出范围钳到端点）——前视目标的取法（v0.55.50）。

        前视目标 = ``progress_s + lookahead_m`` 处的路径点，即参考实现 ``PurePursuit``
        一族的「追前方 lookahead 处的点」。取代 v0.55.49 前的「从 index 起扫第一个
        距机器人 ≥ lookahead 的**航点**」——那个扫描在 0.45 边界上**双稳翻转**：机器人
        距节点 < 0.45 时该节点被跳过、目标切成可能需要大转弯的远节点，机器人转身漂移
        后距离又 ≥ 0.45、目标翻回**身后**的节点（135° 稀疏拐角实测：无限振荡至超时）。
        弧长目标只沿路径向前，翻转从构造上消失。
        """
        s = _clamp(s, 0.0, self._total)
        for seg in self._track:
            if s <= seg.cum_start + seg.length + 1.0e-12:
                t = _clamp(s - seg.cum_start, 0.0, seg.length)
                return [seg.ax + seg.ux * t, seg.ay + seg.uy * t]
        return list(self.waypoints[-1])

    def _pursuit_target(self, x: float, y: float) -> list[float]:
        """前视目标点（v0.55.50）：游标前方 ``lookahead_m`` 处的路径点 + 发卡弯护栏。

        **发卡弯护栏（阈值-free，两个条件同时成立才钳）**：
        ① 目标所在的段相对机器人**当前段**掉头（两段方向点积 < 0，即弯角 > 90°）——
           路径在 lookahead 窗口内折返，弧长目标会绕到**返程段**上；
        ② 该拐角**仍是活跃航点**（拐角弧长 ≥ 活跃航点弧长）——还没被到达/消费。
        两条齐了才把目标改取当前段的末端（拐角）：按 H10 真到达拐角后再转身追返程，
        是发卡弯的标准走法。条件②挡的是"已到拐点却还被钳在拐点"的死锁：到达后
        活跃航点前移，护栏自动让位，目标回到返程段上（实测 ``[[0,0]→[2,0]→[0.5,0]]``
        缺它时 stuck@27s——机器人堵在拐点、游标差 1e-5 没跨过节点弧长）。
        ≤90° 的斜切不受影响（点积 ≥ 0，照常切角；密集路径的 45° 折线全部不受影响）。
        """
        lookahead_s = self.progress_s + self.params.lookahead_m
        target = self._point_at(lookahead_s)
        seg = self._segment_at(self.progress_s)
        if seg is not None:
            target_seg = self._segment_at(min(lookahead_s, self._total))
            corner_s = seg.cum_start + seg.length
            if (
                target_seg is not seg
                and (seg.ux * target_seg.ux + seg.uy * target_seg.uy) < 0.0
                and corner_s >= self._cum[self.index] - 1.0e-9
            ):
                return [seg.ax + seg.ux * seg.length, seg.ay + seg.uy * seg.length]
        return target

    def _project_onto_path(self, x: float, y: float) -> float:
        """机器人位姿到路径的**弧长投影**（路径参数边界的基础，v0.55.50）。

        **游标所在段 + 两段窗口**（单调游标）：只把机器人投影到游标当前所在的轨道段
        及其**下一段**上，两条换段规则——

        ① 投影落在当前段内，但机器人**严格更接近下一段**（且已在下一段起点之前）
           ⇒ 换段：宽切角时机器人切到出向段上，游标要能跟上（135° 稀疏拐角实测：
             只按所在段投影会让游标冻在拐点前、目标随之冻住 ⇒ 停在半路）；
        ② 投影越过当前段末（``t ≥ length``）且已绕到拐角另一侧（下一段投影 ≥ 0）
           ⇒ 换段；还在拐角外侧（下一段投影 < 0）⇒ 钳在拐角节点上（没绕过拐角 =
           没走过它，不许拿"贴着拐角外侧"当过）。

        **为什么是两段窗口而不是全路径最近点**（2026-10-12 实测否决）：共线折返
        （180° 发卡弯，入向段与返程段共线）上机器人每一点都到两段等距——全路径
        最近点法无论同距取早取晚都要坏一头（取早：返程段上游标冻住；取晚：入向段
        半途中游标被拉到拐点后、拐点被提前消费）。两段窗口只在"拐角处"看下一段，
        共线折返的等距不触发换段（取早的语义只在拐角生效），返程段则靠机器人真
        绕过拐角后的规则②换段——两头都对。

        游标只单调不回退（恢复后退不倒扣）。
        """
        track = self._track
        if not track:
            return 0.0
        # 游标所在段：cum_start ≤ progress_s 的**最后**一段（progress_s 恰在节点上时
        # 取从该节点出发的那段——机器人一绕到拐角另一侧游标就能前进）。
        index = 0
        for k in range(len(track) - 1, -1, -1):
            if track[k].cum_start <= self.progress_s + 1.0e-9:
                index = k
                break
        while index < len(track):
            seg = track[index]
            t = (x - seg.ax) * seg.ux + (y - seg.ay) * seg.uy
            if index == len(track) - 1 or t < seg.length:
                if index + 1 < len(track):
                    nxt = track[index + 1]
                    t_next = (x - nxt.ax) * nxt.ux + (y - nxt.ay) * nxt.uy
                    t_cur_c = _clamp(t, 0.0, seg.length)
                    t_next_c = _clamp(t_next, 0.0, nxt.length)
                    dist_cur = math.hypot(x - (seg.ax + seg.ux * t_cur_c), y - (seg.ay + seg.uy * t_cur_c))
                    dist_next = math.hypot(x - (nxt.ax + nxt.ux * t_next_c), y - (nxt.ay + nxt.uy * t_next_c))
                    if t_next >= 0.0 and dist_next < dist_cur - 1.0e-9:
                        index += 1  # 规则①：机器人已切到下一段上（严格更近）
                        continue
                return seg.cum_start + _clamp(t, 0.0, seg.length)
            # 规则②：越过段末——绕到拐角另一侧才继续向前
            nxt = track[index + 1]
            t_next = (x - nxt.ax) * nxt.ux + (y - nxt.ay) * nxt.uy
            if t_next < 0.0:
                return nxt.cum_start  # 还在拐角外侧 ⇒ 钳在拐角节点
            index += 1
        return self._total

    # ---------- 一拍 ----------
    def update(self, pose: Sequence[float], time_s: float) -> FollowStep:
        x, y, yaw = float(pose[0]), float(pose[1]), float(pose[2])
        if self.reason is not None:
            return self._step([0.0, 0.0, 0.0], None, "done", time_s, 0.0)

        if time_s > self.params.max_total_time_s:
            # 预算拉停 ≠ 策略失败（LightNav 的 truncated 语义）
            self.reason = "truncated"
            return self._step([0.0, 0.0, 0.0], "truncated", "truncated", time_s, 0.0)

        # 弧长游标推进（v0.55.50）：每拍重算投影，单调不回退。恢复动作后退不倒扣，
        # 位姿冻结时游标不动（卡死判据的输入之一）。必须在到达判定/消费之前算——
        # 1b) 的消费判据读的就是它。
        self.progress_s = max(self.progress_s, self._project_onto_path(x, y))

        active = self.active
        dx, dy = active[0] - x, active[1] - y
        distance = math.hypot(dx, dy)

        # 1) 到达判定：容差内连续 stable_ticks 拍（H10 真值）
        if distance <= self.tolerances[self.index]:
            self.stable_count += 1
            if self.stable_count >= self.stable_ticks:
                self.index += 1
                # 游标 snap 到刚到达的节点（v0.55.50）：容差带内到达时机器人可能还差
                # 最多一个容差没到节点弧长，共线折返时游标会因此冻在入向段上（实测：
                # 1.80m 处到达拐点 ⇒ 转身后游标不动、目标冻住 ⇒ 停在半路）。到达即认可
                # "走过该节点"，游标不许落在节点身后。
                self.progress_s = max(self.progress_s, self._cum[self.index - 1])
                self.turn_in_place = False
                self.stable_count = 0
                self.waypoint_start_time = time_s
                self.best_heading_err = float("inf")
                self.best_progress_s = self.progress_s
                self.last_progress_time = time_s
                if self.index >= len(self.waypoints):
                    self.reason = "complete"
                    return self._step([0.0, 0.0, 0.0], "complete", "done", time_s, distance)
                return self._step([0.0, 0.0, 0.0], "advance", "arrived", time_s, distance)
            return self._step([0.0, 0.0, 0.0], None, "settling", time_s, distance)
        self.stable_count = 0

        # 1b) 切角消费（v0.55.50，路径参数边界）：活跃航点若已被**走过**（弧长游标
        #     ``progress_s`` 越过它的路径参数 ``cum[index]``），它就是被切角绕过的
        #     节点：继续要求"回到容差内"会让 index 永远停住，前视扫描于是反复把
        #     **身后的点**选成目标（目标航向 ≈±160° 双稳翻转 ⇒ turn_in_place 无限
        #     旋转 ⇒ 30 s 航点超时、此后恒发零速）。v0.55.49 的双条件投影判据在
        #     **垂直拐角**上互斥（投影 > 0.65 与"距节点 < lookahead 0.45"不能同时
        #     成立）⇒ 稀疏长段路径的拐点永远无法消费（00_know/90_归档/08_任务清单_阶段桶与队列_20260928.md §H12 登记病象：
        #     L 形 1m 段、拐角被以 0.24~0.35m 掠过 ⇒ 8 档横向偏移全等超时），故改
        #     路径参数边界：弧长游标单调向前，"折返起点误消费"由单调性挡住。
        #     消费语义：**不**要 H10 容差/稳定拍数（人已走过，不是"到达"）；**最后一个
        #     节点不消费**（while 上界 len-1，与参考实现 _advance_path_nodes 同）——
        #     goal 必须按 H10 口径真到达，否则"走过终点"会假装成功。
        bypassed = 0
        while (
            self.index < len(self.waypoints) - 1
            and self.progress_s >= self._cum[self.index] - 1.0e-9
        ):
            self.index += 1
            bypassed += 1
            # 游标 snap（同到达分支）：消费即认可"走过该节点"，游标不许落在节点身后
            # （共线折返时否则转身后游标冻在入向段、目标冻住）。
            self.progress_s = max(self.progress_s, self._cum[self.index - 1])
            self.turn_in_place = False
            self.stable_count = 0
            self.waypoint_start_time = time_s
            self.best_heading_err = float("inf")
            self.best_progress_s = self.progress_s
            self.last_progress_time = time_s
        if bypassed:
            return self._step([0.0, 0.0, 0.0], "bypass", "bypass", time_s, distance)

        # 2) 单航点超时
        if time_s - self.waypoint_start_time > self.params.waypoint_timeout_s:
            self.reason = "timeout"
            return self._step([0.0, 0.0, 0.0], "timeout", "timeout", time_s, distance)

        # 3) 卡死恢复 + 前视目标（v0.55.50：前视点按弧长投影取，见 _pursuit_target）
        target = self._pursuit_target(x, y)
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
        #   * **弧长游标推进 ≥ stuck_progress_m**（v0.55.50 起的主口径）：目标不再是
        #     "抵达即切换"的航点而是随机器人前移的路径点，"到目标距离缩短"失去意义
        #     （目标始终在 lookahead 前方，距离被目标前移抵消）⇒ 改量游标——沿路径
        #     真实走了多少。恢复动作后退不倒扣（游标单调），位姿冻结时游标不动；
        #   * turn_in_place 期间航向误差收敛 ≥ stuck_turn_progress_deg（原地急转是
        #     目标导向运动，真机 180° 急转可超 4s）。被夹住转不动的真卡死两项都不
        #     成立 ⇒ 恢复照常触发，急转豁免不会吞掉真卡死。
        if self.progress_s > self.best_progress_s + self.params.stuck_progress_m:
            self.best_progress_s = self.progress_s
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
