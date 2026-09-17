// 感知导航的浏览器执行器（H3 `command_source=planner` 的「跟随 + 到达判定」）。
//
// 分工是刻意的，避免"同一件事两套实现"：
//   * **规划**（障碍栅格 + 分段 A*/Dijkstra）只在服务端：`backend/navigation_plan.py`
//     —— 浏览器通过 `POST /api/navigation/plan` 拿到「路径折线 + 跟随参数 + 到达判据」；
//   * 浏览器只做**只有它才能做**的两件事：把折线变成每拍的 cmd_vel（跟随），
//     以及按**服务端给的同一份判据**判定"到了没"。
//
// **数字一律来自服务端载荷，浏览器不自己定阈值**（H10/H12 的单一真值不允许长第三个家）：
//   * `arrival`           → `registry/arrival_criteria.json`（容差 / 稳定拍数）
//   * `follow_controller` → `registry/motion_commands.json#follow_controller`（H12，
//                           取值范围与参考实现 `nav_route_sim2sim_check.py::SimConfig` 对齐）
// 缺任一块 ⇒ 构造时直接抛错。
//
// 控制器律对齐参考实现（H12）：
//   * 前视点跟随：`wz = clamp(kp_yaw·err, ±max_wz)`；仅当 `|err| ≤ yaw_stop_threshold` 才给
//     `vx = clamp(kp_dist·d·cos(err), 0, max_vx)`（cos 门控，不是线性衰减）；
//   * 大误差**原地转**：`|err| ≥ turn_in_place_enter` 进入、`≤ turn_in_place_exit` 退出（滞回）。
//
// H12 卡死/恢复/终止原因（2026-09-17 接入）：与服务端 `backend/follow_controller.py`
// 的 FollowController 状态机**同参数同语义**——参数全部取 `payload.follow_controller`
// （即 registry/motion_commands.json#follow_controller，缺字段 fail-closed 抛错，沿用
// requiredNumber 惯例），判据形状逐分支对齐服务端：
//   * 进展登记：`distance + stuck_progress_m < best_distance` ⇒ 有进展（服务端 220 行）；
//   * 卡死判定：`stuck_timeout_s` 内无进展 ⇒ 发恢复段（服务端 230 行）；
//   * 恢复动作：`vx = recovery_cmd.vx_factor, wz = recovery_cmd.wz_factor × sign`
//     （符号每轮翻转），持续 `recovery_duration_s`，至多 `max_recoveries` 轮
//     （服务端 223–243 行）；恢复用尽 ⇒ 终止原因 `stuck`；
//   * 终止原因分层抄 LightNav：`complete / timeout / stuck / truncated / undefined`
//     ——`truncated` 表示"被总时长预算拉停"，不是策略结论，必须与"策略失败"分开记。
// 时间口径：服务端 update(pose, time_s) 以秒计时；浏览器把每控制拍的增量
// `options.controlDt`（= sim_dt × control_decimation，由 app.js 传入）累计成秒。
export const NAVIGATION_VERSION = "nav-follow-2.1";

/** 把角度归一化到 (-π, π]。 */
export function wrapAngle(angle) {
  let value = Number(angle) || 0;
  while (value > Math.PI) value -= 2 * Math.PI;
  while (value <= -Math.PI) value += 2 * Math.PI;
  return value;
}

/**
 * 从自由关节四元数取偏航角（yaw）。
 * MuJoCo 自由关节：qpos[0..2]=位置，qpos[3..6]=四元数 (w, x, y, z)。
 */
export function yawFromQuat(quat, offset = 0) {
  const w = Number(quat?.[offset] ?? 1);
  const x = Number(quat?.[offset + 1] ?? 0);
  const y = Number(quat?.[offset + 2] ?? 0);
  const z = Number(quat?.[offset + 3] ?? 0);
  const siny = 2 * (w * z + x * y);
  const cosy = 1 - 2 * (y * y + z * z);
  return Math.atan2(siny, cosy);
}

/** 从 qpos 取平面位姿 `{x, y, yaw}`（自由关节布局）。 */
export function poseFromQpos(qpos) {
  return {
    x: Number(qpos?.[0] ?? 0),
    y: Number(qpos?.[1] ?? 0),
    yaw: yawFromQuat(qpos, 3),
  };
}

const DEG = Math.PI / 180;

function distance(a, b) {
  return Math.hypot(Number(a.x) - Number(b[0]), Number(a.y) - Number(b[1]));
}

function clampValue(value, limit) {
  const bound = Math.abs(Number(limit));
  if (!Number.isFinite(bound) || bound === 0) return 0;
  return Math.max(-bound, Math.min(bound, value));
}

function requiredNumber(source, key, where) {
  const value = Number(source?.[key]);
  if (!Number.isFinite(value)) {
    throw new Error(`navigation payload 缺少 ${where}.${key}（数字必须由服务端给出，浏览器不自造）`);
  }
  return value;
}

/** 必需的有限数（浮点允许）；非有限 ⇒ fail-closed（同 requiredNumber 的纪律）。 */
function requiredFinite(source, key, where) {
  const value = Number(source?.[key]);
  if (!Number.isFinite(value)) {
    throw new Error(`navigation payload 缺少 ${where}.${key}（数字必须由服务端给出，浏览器不自造）`);
  }
  return value;
}

/**
 * 导航跟随器（含 H12 卡死恢复状态机，与服务端 backend/follow_controller.py 同语义）。
 *
 * @param {object} payload 服务端 `navigation` 载荷（`/api/navigation/plan` 或会话响应）
 * @param {object} [options]
 * @param {number[]} [options.maxCmd] 浏览器侧指令上限 `[vx, vy, wz]`（与场景/注册表取更严者）
 * @param {number|(() => number)} [options.controlDt] 控制拍时长（秒，= sim_dt ×
 *   control_decimation；可传 getter，每拍求值）。缺失 ⇒ 第一次 tick 即抛错（fail-closed，
 *   卡死/恢复/超时判据全部依赖真实时间，浏览器不许自造拍长）。
 */
export function createNavigationRunner(payload, options = {}) {
  const waypoints = Array.isArray(payload?.waypoints) ? payload.waypoints : [];
  const path = Array.isArray(payload?.plan?.combined_path) ? payload.plan.combined_path : [];
  const arrival = payload?.arrival;
  const follow = payload?.follow_controller;
  if (!waypoints.length || path.length < 2) {
    throw new Error("navigation payload 缺少航点或路径（planner 载荷不完整）");
  }
  if (!arrival || !Number.isFinite(Number(arrival.tolerance_m)) || !Number.isFinite(Number(arrival.stable_ticks))) {
    throw new Error("navigation payload 缺少 arrival 判据（容差/稳定拍数必须由服务端给出，浏览器不自造阈值）");
  }
  if (!follow || typeof follow !== "object") {
    throw new Error("navigation payload 缺少 follow_controller 参数（H12：跟随参数必须来自 registry/motion_commands.json）");
  }

  const params = {
    lookahead_m: requiredNumber(follow, "lookahead_m", "follow_controller"),
    kp_dist: requiredNumber(follow, "kp_dist", "follow_controller"),
    kp_yaw: requiredNumber(follow, "kp_yaw", "follow_controller"),
    max_vx: requiredNumber(follow, "max_vx", "follow_controller"),
    max_wz: requiredNumber(follow, "max_wz", "follow_controller"),
    yaw_stop_threshold_deg: requiredNumber(follow, "yaw_stop_threshold_deg", "follow_controller"),
    turn_in_place_enter_deg: requiredNumber(follow, "turn_in_place_enter_deg", "follow_controller"),
    turn_in_place_exit_deg: requiredNumber(follow, "turn_in_place_exit_deg", "follow_controller"),
    turn_in_place_max_wz: requiredNumber(follow, "turn_in_place_max_wz", "follow_controller"),
  };
  // H12 卡死/恢复/终止参数：与服务端 FollowParams.from_registry 同字段同真值
  // （registry/motion_commands.json#follow_controller；recovery_cmd 在其子块里）。
  // 缺字段直接抛错——服务端 FollowParams.from_registry 的 fail-closed 纪律（74–101 行）。
  const recovery = follow.recovery_cmd && typeof follow.recovery_cmd === "object" ? follow.recovery_cmd : null;
  if (!recovery) {
    throw new Error("navigation payload 缺少 follow_controller.recovery_cmd（H12 卡死恢复参数必须来自 registry/motion_commands.json）");
  }
  const stuckParams = {
    stuck_timeout_s: requiredFinite(follow, "stuck_timeout_s", "follow_controller"),
    stuck_progress_m: requiredFinite(follow, "stuck_progress_m", "follow_controller"),
    recovery_duration_s: requiredFinite(follow, "recovery_duration_s", "follow_controller"),
    max_recoveries: Math.round(requiredFinite(follow, "max_recoveries", "follow_controller")),
    recovery_vx: requiredFinite(recovery, "vx_factor", "follow_controller.recovery_cmd"),
    recovery_wz: requiredFinite(recovery, "wz_factor", "follow_controller.recovery_cmd"),
    waypoint_timeout_s: requiredFinite(follow, "waypoint_timeout_s", "follow_controller"),
    max_total_time_s: requiredFinite(follow, "max_total_time_s", "follow_controller"),
  };
  const arrivalTolerance = Number(arrival.tolerance_m);
  const stableTicks = Math.max(1, Math.round(Number(arrival.stable_ticks)));
  const maxCmd = Array.isArray(options.maxCmd) && options.maxCmd.length >= 3
    ? options.maxCmd.map(Number)
    : [Number.POSITIVE_INFINITY, Number.POSITIVE_INFINITY, Number.POSITIVE_INFINITY];
  const commandLimits = payload?.command_limits || {};
  // 三处取更严：浏览器指令上限 × 场景 command_limits × 注册表 max_vx/max_wz
  const limits = [
    Math.min(maxCmd[0], Number.isFinite(Number(commandLimits.vx)) ? Number(commandLimits.vx) : maxCmd[0], params.max_vx),
    Math.min(maxCmd[1], Number.isFinite(Number(commandLimits.vy)) ? Number(commandLimits.vy) : maxCmd[1]),
    Math.min(maxCmd[2], Number.isFinite(Number(commandLimits.wz)) ? Number(commandLimits.wz) : maxCmd[2], params.max_wz),
  ];
  const turnInPlaceMaxWz = Math.min(limits[2], params.turn_in_place_max_wz);

  let waypointIndex = 1;
  let cursor = 1;
  let stableCount = 0;
  let reached = 1;
  let finished = waypoints.length <= 1;
  let elapsedSteps = 0;
  let turnInPlace = false;
  // --- H12 状态机（与服务端 FollowController.reset 对齐，backend/follow_controller.py 156–167 行）---
  let elapsed_s = 0; // 控制时间线（秒）：每控制拍累加 controlDt，对应服务端 update 的 time_s
  let terminationReason = null; // complete / timeout / stuck / truncated / undefined（LightNav 分层）
  let waypointStart_s = 0; // 当前航点的起始时刻（服务端 waypoint_start_time）
  let bestDistance = Number.POSITIVE_INFINITY; // 本航点历史最近距离（服务端 best_distance）
  let lastProgress_s = 0; // 最近一次有进展的时刻（服务端 last_progress_time）
  let recoveryUntil_s = -1; // 恢复段截止时刻（服务端 recovery_until）
  let recoveryCount = 0; // 已用恢复轮数（服务端 recovery_count）
  let recoverySign = 1; // 恢复转向符号，每轮翻转（服务端 recovery_sign）
  let lastState = finished ? "done" : "following"; // 最近一拍的状态名（对齐服务端 FollowStep.state）

  // 控制拍时长（秒）：调用方传 sim_dt × control_decimation（number 或 getter——
  // getter 用于合约晚于导航初始化到达的场景，每拍取最新值）。缺失/非法 ⇒ fail-closed。
  const controlDtSource = options.controlDt;
  function currentControlDt() {
    const value = typeof controlDtSource === "function" ? Number(controlDtSource()) : Number(controlDtSource);
    if (!Number.isFinite(value) || value <= 0) {
      throw new Error("navigation runner 缺少有效的 options.controlDt（控制拍秒数必须由调用方给出，浏览器不自造）");
    }
    return value;
  }

  /** 终止：状态机不再发指令（服务端 reason 字段的浏览器对应物）。 */
  function finish(reason, state) {
    finished = true;
    terminationReason = reason;
    lastState = state;
    return status();
  }

  function toleranceFor(index) {
    const value = Number(waypoints[index]?.tolerance_m);
    return Number.isFinite(value) ? value : arrivalTolerance;
  }

  function targetPoint(pose) {
    // 先消费掉近处的路径点，再取第一个 ≥ 前视距离的点（参考实现同法）
    while (cursor < path.length - 1 && distance(pose, path[cursor]) < params.lookahead_m * 0.5) cursor += 1;
    for (let i = cursor; i < path.length; i += 1) {
      if (distance(pose, path[i]) >= params.lookahead_m) return path[i];
    }
    return path[path.length - 1];
  }

  function command(pose) {
    if (finished) return [0, 0, 0];
    // 容差内先发**零指令**（settling，服务端 197–211 行同语义：update 的到达判定分支
    // 在卡死恢复/跟随律之前，容差内的拍一律 [0,0,0]）。机器人据此在容差区内减速停驻、
    // 攒够 stable_ticks——若容差内还按跟随律加前提航，机器人会冲过航点形成过冲振荡，
    // 距离长时间无 0.08m 净改善 ⇒ 卡死判据按共享语义如实触发（振荡不是"活着"的证据）。
    const activeWaypoint = waypoints[waypointIndex];
    if (activeWaypoint && distance(pose, [activeWaypoint.x, activeWaypoint.y]) <= toleranceFor(waypointIndex)) {
      return [0, 0, 0];
    }
    // 恢复段在发令侧先于跟随律（服务端 223–229 行同语义——update 的"卡死恢复"分支
    // 先于跟随律返回 recovery cmd）。
    // 恢复动作：vx = recovery_cmd.vx_factor，wz = recovery_cmd.wz_factor × sign
    // （vx 为负 = 后退脱困；转向符号每轮翻转以打破对称卡死）。注释对应
    // backend/follow_controller.py 223–229 行的 recovery cmd 构造。
    if (recoveryUntil_s > elapsed_s) {
      // 恢复指令**原样发**（服务端 224–228 行构造后直接返回，不做限幅）；
      // 若地形切换层要求限速，那是 app.js 的 applyTerrainSwitch 在跟随指令之上施加的
      // 浏览器侧安全层，与本状态机无关。
      return [stuckParams.recovery_vx, 0, stuckParams.recovery_wz * recoverySign];
    }
    const target = targetPoint(pose);
    const dx = Number(target[0]) - pose.x;
    const dy = Number(target[1]) - pose.y;
    const error = wrapAngle(Math.atan2(dy, dx) - pose.yaw);

    if (turnInPlace) {
      if (Math.abs(error) <= params.turn_in_place_exit_deg * DEG) turnInPlace = false;
    } else if (Math.abs(error) >= params.turn_in_place_enter_deg * DEG) {
      turnInPlace = true;
    }
    if (turnInPlace) {
      return [0, 0, clampValue(params.kp_yaw * error, turnInPlaceMaxWz)];
    }

    const lookaheadDistance = Math.hypot(dx, dy);
    let vx = 0;
    if (Math.abs(error) <= params.yaw_stop_threshold_deg * DEG) {
      vx = Math.max(0, Math.min(limits[0], params.kp_dist * lookaheadDistance * Math.cos(error)));
    }
    const wz = clampValue(params.kp_yaw * error, limits[2]);
    return [vx, 0, wz];
  }

  /** 每控制拍调用一次：推进到达判定、卡死恢复与终止原因（状态机主干）。 */
  function tick(pose) {
    elapsedSteps += 1;
    const controlDt = currentControlDt();
    elapsed_s += controlDt;
    if (finished) {
      lastState = "done";
      return status();
    }
    // 0) 总时长预算（服务端 188–191 行同语义，先于到达判定）：预算拉停 ≠ 策略失败，
    //    单独记 truncated，不与 timeout/stuck 混淆（LightNav 约定）。
    if (elapsed_s > stuckParams.max_total_time_s) {
      return finish("truncated", "truncated");
    }
    const target = waypoints[waypointIndex];
    if (!target) {
      return finish("undefined", "done"); // 没有可追随的航点：判据未定义（不假装成功）
    }
    const distanceToTarget = distance(pose, [target.x, target.y]);

    // 1) 到达判定：容差内连续 stable_ticks 拍（H10 真值；服务端 197–211 行同语义）
    if (distanceToTarget <= toleranceFor(waypointIndex)) {
      stableCount += 1;
      if (stableCount >= stableTicks) {
        reached += 1;
        stableCount = 0;
        waypointIndex += 1;
        turnInPlace = false; // 换段重新判定朝向
        // 新航点只重置计时/进展登记（服务端 204–206 行同语义：waypoint_start_time /
        // best_distance / last_progress_time）——**不**清 recovery_until / recovery_count，
        // 残余恢复窗口跨航点有效（服务端 advance 分支同样不清，语义以此为准）。
        waypointStart_s = elapsed_s;
        bestDistance = Number.POSITIVE_INFINITY;
        lastProgress_s = elapsed_s;
        if (waypointIndex >= waypoints.length) return finish("complete", "done");
        lastState = "arrived";
        return status();
      }
      lastState = "settling";
      return status();
    }
    stableCount = 0;

    // 2) 单航点超时（服务端 215–217 行同语义）：策略结论，与预算截断分开记
    if (elapsed_s - waypointStart_s > stuckParams.waypoint_timeout_s) {
      return finish("timeout", "timeout");
    }

    // 3) 卡死恢复（服务端 219–243 行同语义）：
    //    进展登记 ⇒ 恢复段发令 ⇒ 恢复用尽判 stuck。
    //    首拍 best 为 ∞ ⇒ 恒刷新（d + p < ∞ 对有限 d 恒真，与服务端 reset 后形状一致）。
    if (distanceToTarget + stuckParams.stuck_progress_m < bestDistance) {
      bestDistance = distanceToTarget;
      lastProgress_s = elapsed_s;
    }
    if (recoveryUntil_s > elapsed_s) {
      lastState = "recovery"; // 指令在 command() 里发（调用方每拍都问 command）
      return status();
    }
    if (elapsed_s - lastProgress_s > stuckParams.stuck_timeout_s) {
      if (recoveryCount >= stuckParams.max_recoveries) {
        return finish("stuck", "stuck"); // 恢复用尽：策略结论 = 卡死（服务端 231–233 行）
      }
      recoveryCount += 1;
      recoverySign *= -1;
      recoveryUntil_s = elapsed_s + stuckParams.recovery_duration_s;
      lastProgress_s = elapsed_s; // 恢复期后重新计时，避免立即再判卡死（服务端 237 行注释同源）
      lastState = "recovery";
      return status();
    }

    // 4) 跟随中
    lastState = turnInPlace ? "turn_in_place" : "following";
    return status();
  }

  function status() {
    const total = Math.max(1, waypoints.length - 1);
    const target = waypoints[Math.min(waypointIndex, waypoints.length - 1)];
    return {
      version: NAVIGATION_VERSION,
      waypoint_index: waypointIndex,
      waypoint_count: waypoints.length,
      reached,
      route_completion: Math.min(1, (reached - 1) / total),
      tolerance_m: toleranceFor(Math.min(waypointIndex, waypoints.length - 1)),
      stable_ticks: stableTicks,
      stable_count: stableCount,
      steps: elapsedSteps,
      finished,
      // --- H12 状态机字段（与服务端 FollowStep/FollowController.verdict 对齐）---
      state: lastState, // following / turn_in_place / settling / arrived / recovery / timeout / stuck / truncated / done
      termination_reason: terminationReason, // complete / timeout / stuck / truncated / undefined；未结束为 null
      recoveries_used: recoveryCount,
      max_recoveries: stuckParams.max_recoveries,
      stuck: lastState === "recovery" || (recoveryUntil_s > elapsed_s),
      elapsed_s: Math.round(elapsed_s * 1000) / 1000,
      turn_in_place: turnInPlace,
      target: target ? [Number(target.x), Number(target.y)] : null,
      limits,
      // 参数来源写进状态，UI 上可直接显示"数字从哪来"
      sources: {
        arrival: arrival.source || "registry/arrival_criteria.json",
        follow_controller: "registry/motion_commands.json#follow_controller",
      },
      params,
    };
  }

  function reset() {
    waypointIndex = 1;
    cursor = 1;
    stableCount = 0;
    reached = 1;
    finished = waypoints.length <= 1;
    elapsedSteps = 0;
    turnInPlace = false;
    elapsed_s = 0;
    terminationReason = null;
    waypointStart_s = 0;
    bestDistance = Number.POSITIVE_INFINITY;
    lastProgress_s = 0;
    recoveryUntil_s = -1;
    recoveryCount = 0;
    recoverySign = 1;
    lastState = finished ? "done" : "following";
  }

  return { command, tick, status, reset, waypoints, path, arrival: { ...arrival }, params };
}

/**
 * 把服务端给的**切换决定**施加到这一拍的指令上（纯函数，可单测）。
 *
 * * `kind: "stop"` —— 判定不可通行 ⇒ 指令全零；
 * * `kind: "limits"` / `"policy"` —— 按 `new_limits` 逐轴裁剪（**只会更严**）；
 * * 其它（含缺失、未知类型）—— **不施加**并把原因回给调用方（fail-closed：不猜）。
 *
 * 为什么把这段做成纯函数：切换是否生效是"感知闭环"的最后一米，必须能脱离浏览器单测。
 */
export function applyTerrainSwitch(cmd, decision) {
  const original = [Number(cmd?.[0] ?? 0), Number(cmd?.[1] ?? 0), Number(cmd?.[2] ?? 0)];
  if (!decision || typeof decision !== "object") {
    return { cmd: original, applied: false, kind: null, reason: "无切换决定" };
  }
  const kind = String(decision.kind ?? "");
  if (kind === "stop") {
    return { cmd: [0, 0, 0], applied: true, kind, stopped: true, reason: decision.note || "不可通行：停机" };
  }
  if (kind === "limits" || kind === "policy") {
    const limits = decision.new_limits || {};
    const axes = ["vx", "vy", "wz"];
    const next = original.map((value, index) => {
      const bound = Number(limits[axes[index]]);
      return Number.isFinite(bound) ? clampValue(value, bound) : value;
    });
    return { cmd: next, applied: true, kind, reason: decision.note || "" };
  }
  return { cmd: original, applied: false, kind, reason: `未知切换类型 ${kind || "<空>"}（不施加）` };
}
