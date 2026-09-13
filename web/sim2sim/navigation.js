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
// 尚未在浏览器侧实现（**别当已有**）：卡死检测 / 恢复动作 / 终止原因分层（`truncated` 等）
// —— 那些在服务端 `backend/follow_controller.py`（H12 状态机）里；浏览器侧后续接入。

export const NAVIGATION_VERSION = "nav-follow-2.0";

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

/**
 * 导航跟随器。
 *
 * @param {object} payload 服务端 `navigation` 载荷（`/api/navigation/plan` 或会话响应）
 * @param {object} [options]
 * @param {number[]} [options.maxCmd] 浏览器侧指令上限 `[vx, vy, wz]`（与场景/注册表取更严者）
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

  /** 每控制拍调用一次：推进到达判定与完成率。 */
  function tick(pose) {
    elapsedSteps += 1;
    if (finished) return status();
    const target = waypoints[waypointIndex];
    if (!target) {
      finished = true;
      return status();
    }
    if (distance(pose, [target.x, target.y]) <= toleranceFor(waypointIndex)) {
      stableCount += 1;
      if (stableCount >= stableTicks) {
        reached += 1;
        stableCount = 0;
        waypointIndex += 1;
        turnInPlace = false; // 换段重新判定朝向
        if (waypointIndex >= waypoints.length) finished = true;
      }
    } else {
      stableCount = 0;
    }
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
