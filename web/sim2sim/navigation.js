// 感知导航的浏览器执行器（H3 `command_source=planner` 的「跟随 + 到达判定」）。
//
// 分工是刻意的，避免又变成"同一件事两套实现"：
//   * **规划**（障碍栅格 + 分段 A*/Dijkstra）只在服务端：`backend/navigation_plan.py`
//     —— 浏览器通过 `POST /api/navigation/plan` 拿到「路径折线 + 到达判据」；
//   * 浏览器只做**只有它才能做**的两件事：把折线变成每拍的 cmd_vel（纯追踪），
//     以及按**服务端给的同一份判据**判定"到了没"（容差与稳定拍数来自载荷，
//     浏览器不自己定阈值——H10 的单一真值不能在客户端长出第三个家）。
//
// 因此本模块的两个不变量：
//   1. 缺 `arrival` 判据 ⇒ 构造时直接抛错（不许静默用默认值）；
//   2. 指令上限取 `min(浏览器 CONFIG.maxCmd, 场景 command_limits)`（场景口径更严时以场景为准）。

export const NAVIGATION_VERSION = "nav-follow-1.0";

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

function distance(a, b) {
  return Math.hypot(Number(a.x) - Number(b[0]), Number(a.y) - Number(b[1]));
}

function clampValue(value, limit) {
  const bound = Math.abs(Number(limit));
  if (!Number.isFinite(bound) || bound === 0) return 0;
  return Math.max(-bound, Math.min(bound, value));
}

/**
 * 导航跟随器。
 *
 * @param {object} payload 服务端 `navigation` 载荷（`/api/navigation/plan` 或会话响应）
 * @param {object} [options]
 * @param {number[]} [options.maxCmd]   浏览器侧指令上限 `[vx, vy, wz]`
 * @param {number}   [options.lookahead] 前视距离（米）
 */
export function createNavigationRunner(payload, options = {}) {
  const waypoints = Array.isArray(payload?.waypoints) ? payload.waypoints : [];
  const path = Array.isArray(payload?.plan?.combined_path) ? payload.plan.combined_path : [];
  const arrival = payload?.arrival;
  if (!waypoints.length || path.length < 2) {
    throw new Error("navigation payload 缺少航点或路径（planner 载荷不完整）");
  }
  if (!arrival || !Number.isFinite(Number(arrival.tolerance_m)) || !Number.isFinite(Number(arrival.stable_ticks))) {
    throw new Error("navigation payload 缺少 arrival 判据（容差/稳定拍数必须由服务端给出，浏览器不自造阈值）");
  }

  const toleranceDefault = Number(arrival.tolerance_m);
  const stableTicks = Math.max(1, Math.round(Number(arrival.stable_ticks)));
  const maxCmd = Array.isArray(options.maxCmd) && options.maxCmd.length >= 3
    ? options.maxCmd.map(Number)
    : [Number.POSITIVE_INFINITY, Number.POSITIVE_INFINITY, Number.POSITIVE_INFINITY];
  const commandLimits = payload?.command_limits || {};
  const limits = [
    Math.min(maxCmd[0], Number.isFinite(Number(commandLimits.vx)) ? Number(commandLimits.vx) : maxCmd[0]),
    Math.min(maxCmd[1], Number.isFinite(Number(commandLimits.vy)) ? Number(commandLimits.vy) : maxCmd[1]),
    Math.min(maxCmd[2], Number.isFinite(Number(commandLimits.wz)) ? Number(commandLimits.wz) : maxCmd[2]),
  ];
  const lookahead = Number.isFinite(Number(options.lookahead)) ? Number(options.lookahead) : 0.6;
  const speedGain = Number.isFinite(Number(options.speedGain)) ? Number(options.speedGain) : 1.2;
  const yawGain = Number.isFinite(Number(options.yawGain)) ? Number(options.yawGain) : 1.5;
  const headingGate = Number.isFinite(Number(options.headingGate)) ? Number(options.headingGate) : 0.9;

  // 起点算已到达（否则 completion 永远差一格）
  let waypointIndex = 1;
  let cursor = 1;
  let stableCount = Math.min(stableTicks, 1) === 1 && false ? 0 : 0;
  let reached = 1;
  let finished = waypoints.length <= 1;
  let elapsedSteps = 0;

  function toleranceFor(index) {
    const value = Number(waypoints[index]?.tolerance_m);
    return Number.isFinite(value) ? value : toleranceDefault;
  }

  function targetPoint(pose) {
    // 先把"已经过去"的路径点消费掉（含半径内的），再取前视点
    while (cursor < path.length - 1 && distance(pose, path[cursor]) < lookahead * 0.5) cursor += 1;
    for (let i = cursor; i < path.length; i += 1) {
      if (distance(pose, path[i]) >= lookahead) return path[i];
    }
    return path[path.length - 1];
  }

  function command(pose) {
    if (finished) return [0, 0, 0];
    const target = targetPoint(pose);
    const dx = Number(target[0]) - pose.x;
    const dy = Number(target[1]) - pose.y;
    const targetYaw = Math.atan2(dy, dx);
    const headingError = wrapAngle(targetYaw - pose.yaw);
    const distanceToTarget = Math.hypot(dx, dy);
    const alignFactor = Math.max(0, 1 - Math.abs(headingError) / headingGate);
    return [
      clampValue(speedGain * distanceToTarget * alignFactor, limits[0]),
      0,
      clampValue(yawGain * headingError, limits[2]),
    ];
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
      target: target ? [Number(target.x), Number(target.y)] : null,
      limits,
    };
  }

  function reset() {
    waypointIndex = 1;
    cursor = 1;
    stableCount = 0;
    reached = 1;
    finished = waypoints.length <= 1;
    elapsedSteps = 0;
  }

  return { command, tick, status, reset, waypoints, path, arrival: { ...arrival } };
}
