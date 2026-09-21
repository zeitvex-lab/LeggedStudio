// Scenario **运行侧**纯逻辑（A1）：场景交运、判据求值、运行摘要。
//
// 为什么单独成模块：这些判据必须在 Node 里可测（`node web/sim2sim/scenario_run.test.mjs`），
// 且**阈值不许自己发明** —— 到达判据的数值真值在服务端 `registry/arrival_criteria.json`
// （经 `/api/navigation/plan` 的 `arrival` 段随载荷下发），本模块只做"拿真值去比"的纯函数。
//
// 分工（与 scenario_editor.js 的分工注释一致）：
//   * 编辑器（scenario_editor.js）：表单 → 场景契约（合法性与门禁）；
//   * 本模块：场景契约 → **交给仿真的消息** + 跑完之后的判据/摘要；
//   * 浏览器不算路径、不算阈值（那些是服务端唯一真值）。

/** 交运消息的类型（iframe postMessage 用；编辑器与仿真页两端必须同一个字面量）。 */
export const SCENARIO_MESSAGE_TYPE = "legged-studio:scenario";

/** 消息协议版本（两端不一致时接收方要拒收，而不是半懂地跑）。 */
export const SCENARIO_MESSAGE_VERSION = 1;

/** 浏览器执行器**不支持**的命令来源（与 `backend/executors.py` 的能力矩阵同口径）。
 *
 * 这是**镜像数据**：真值在 `backend/executors.py` 的 `EXECUTORS[*].supports.command_sources`，
 * 页面运行时经 `GET /api/simulation/executors` 拿真值（B1）；这里留一份是为了纯函数可测、
 * 可离线。防漂移靠 `backend/test_executors.py` 的跨语言核对（JS 常量 ↔ Python 矩阵）。
 */
export const EXECUTOR_COMMAND_SOURCES = {
  browser_wasm: ["policy", "teleop", "planner"],
  server_mujoco: ["planner", "script"],
};

/** 某执行器下不可用的指令来源问题列表（空 = 可用）。启动闸门读它。
 *
 * @param {string} commandSource 场景声明的指令来源
 * @param {string|string[]} executor 执行器 id，或**直接给**该执行器支持的来源数组
 *        （页面从 `/api/simulation/executors` 拿到真值时传数组，避免两侧数据漂移）
 */
export function unsupportedCommandSourceProblems(commandSource, executor = "browser_wasm") {
  const supported = Array.isArray(executor)
    ? executor
    : (EXECUTOR_COMMAND_SOURCES[executor] || EXECUTOR_COMMAND_SOURCES.browser_wasm);
  if (supported.includes(commandSource)) return [];
  const why = commandSource === "script"
    ? "脚本化指令序列只有服务端执行器能跑"
    : commandSource === "perception"
      ? "感知驱动需要感知进观测链路，当前执行器未接"
      : `当前执行器可执行的来源只有：${supported.join(" / ")}`;
  const label = Array.isArray(executor) ? "当前执行器" : `执行器 ${executor}`;
  return [`command_source=${commandSource} 在${label}不可用：${why}`];
}

/**
 * 场景 → 交运消息载荷（完整场景，不再是有损的 7 个 URL 参数）。
 *
 * URL 参数仍然发（深链接/刷新要能用），但**完整场景走 postMessage**：判据、记录器、
 * 感知、指令源、时长这些字段塞进 URL 要么塞不下要么静默失效。
 */
export function toScenarioMessage(scenario, { robot = "", policy = "", source = "scenario-editor" } = {}) {
  if (!scenario || typeof scenario !== "object") return null;
  return {
    type: SCENARIO_MESSAGE_TYPE,
    version: SCENARIO_MESSAGE_VERSION,
    source,
    robot: String(robot || ""),
    policy: String(policy || ""),
    scenario: JSON.parse(JSON.stringify(scenario)),
  };
}

/**
 * 接收方校验：消息形状不对就**拒收并说清原因**（不猜、不半懂地跑）。
 * 返回 `{ ok, reason, payload }`。
 */
export function parseScenarioMessage(event) {
  const data = event?.data;
  if (!data || typeof data !== "object") return { ok: false, reason: "消息不是对象" };
  if (data.type !== SCENARIO_MESSAGE_TYPE) return { ok: false, reason: `不是场景消息（type=${String(data.type)}）` };
  if (Number(data.version) !== SCENARIO_MESSAGE_VERSION) {
    return { ok: false, reason: `消息协议版本不符（收到 ${String(data.version)}，期望 ${SCENARIO_MESSAGE_VERSION}）` };
  }
  const scenario = data.scenario;
  if (!scenario || typeof scenario !== "object") return { ok: false, reason: "消息缺 scenario 载荷" };
  if (!scenario.scenario_id) return { ok: false, reason: "scenario 缺 scenario_id" };
  if (!Array.isArray(scenario.waypoints)) return { ok: false, reason: "scenario.waypoints 必须是数组" };
  return { ok: true, payload: data, reason: "" };
}

/** 一条轨迹采样点（控制步粒度；`pose` 用 `{x,y,yawDeg}` 这种粗口径，够判据用）。 */
export function tracePoint({ t, x, y, yawDeg = 0, rollDeg = 0, pitchDeg = 0, vx = 0, vy = 0, wz = 0, fallen = false }) {
  return {
    t: Number(t) || 0,
    x: Number(x) || 0,
    y: Number(y) || 0,
    yawDeg: Number(yawDeg) || 0,
    rollDeg: Number(rollDeg) || 0,
    pitchDeg: Number(pitchDeg) || 0,
    vx: Number(vx) || 0,
    vy: Number(vy) || 0,
    wz: Number(wz) || 0,
    fallen: Boolean(fallen),
  };
}

/**
 * 到达判据：**末个航点**在容差内稳定停留（判据数值由服务端 `arrival` 段给出，
 * 本函数不写死任何阈值 —— 没有 arrival 就明说"没有判据"而不是默认通过）。
 */
export function evaluateArrival(scenario, trace, arrival) {
  const waypoints = Array.isArray(scenario?.waypoints) ? scenario.waypoints : [];
  if (!waypoints.length) return { ok: false, reason: "场景没有航点，判不出到达" };
  if (!arrival || !Number.isFinite(Number(arrival.tolerance_m))) {
    return { ok: false, reason: "没有服务端到达判据（arrival.tolerance_m 缺失），不默认通过" };
  }
  const tolerance = Number(arrival.tolerance_m);
  const stable = Number.isFinite(Number(arrival.stable_ticks)) ? Number(arrival.stable_ticks) : 1;
  const goal = waypoints[waypoints.length - 1];
  const near = trace.filter((point) => Math.hypot(point.x - goal.x, point.y - goal.y) <= tolerance);
  // 连续稳定拍数（末尾起算，与 H12 的 stable_count 同口径）
  let streak = 0;
  for (let i = trace.length - 1; i >= 0; i -= 1) {
    if (Math.hypot(trace[i].x - goal.x, trace[i].y - goal.y) <= tolerance) streak += 1;
    else break;
  }
  const last = trace.length ? trace[trace.length - 1] : null;
  const distance = last ? Math.hypot(last.x - goal.x, last.y - goal.y) : Infinity;
  return {
    ok: streak >= stable && !(last && last.fallen),
    reason: streak >= stable ? `已在末点 ${distance.toFixed(2)}m 内稳定 ${streak} 拍` : `距末点 ${distance.toFixed(2)}m（容差 ${tolerance}m），稳定 ${streak}/${stable} 拍`,
    distanceM: Number.isFinite(distance) ? Number(distance.toFixed(3)) : null,
    stableTicks: streak,
    requiredTicks: stable,
  };
}

/** 航线完成度：到达过的航点数 / 总航点数（顺序不要求，报告用）。 */
export function evaluateRouteCompletion(scenario, trace, arrival) {
  const waypoints = Array.isArray(scenario?.waypoints) ? scenario.waypoints : [];
  if (!waypoints.length) return { ok: false, reason: "场景没有航点", ratio: 0, reached: 0, total: 0 };
  const tolerance = arrival && Number.isFinite(Number(arrival.tolerance_m)) ? Number(arrival.tolerance_m) : 0.5;
  const reached = waypoints.filter((goal) =>
    trace.some((point) => Math.hypot(point.x - goal.x, point.y - goal.y) <= tolerance)).length;
  const ratio = reached / waypoints.length;
  return {
    ok: ratio >= 1,
    reason: `到达 ${reached}/${waypoints.length} 个航点（容差 ${tolerance}m）`,
    ratio: Number(ratio.toFixed(3)),
    reached,
    total: waypoints.length,
  };
}

/** 一趟运行的度量（不设门槛，只如实报告；门槛归评测矩阵）。 */
export function summarizeRun(scenario, trace) {
  if (!trace.length) {
    return { durationS: 0, distanceM: 0, maxRollDeg: 0, maxPitchDeg: 0, fell: false, meanSpeed: 0, samples: 0 };
  }
  let distance = 0;
  let maxRoll = 0;
  let maxPitch = 0;
  let speed = 0;
  let fell = false;
  for (let i = 0; i < trace.length; i += 1) {
    const point = trace[i];
    if (i > 0) distance += Math.hypot(point.x - trace[i - 1].x, point.y - trace[i - 1].y);
    maxRoll = Math.max(maxRoll, Math.abs(point.rollDeg));
    maxPitch = Math.max(maxPitch, Math.abs(point.pitchDeg));
    speed += Math.hypot(point.vx, point.vy);
    fell = fell || point.fallen;
  }
  return {
    durationS: Number((trace[trace.length - 1].t - trace[0].t).toFixed(2)),
    distanceM: Number(distance.toFixed(2)),
    maxRollDeg: Number(maxRoll.toFixed(1)),
    maxPitchDeg: Number(maxPitch.toFixed(1)),
    fell,
    meanSpeed: Number((speed / trace.length).toFixed(3)),
    samples: trace.length,
  };
}

/**
 * 按场景声明的 `checks` 逐项求值。**未声明的项不跑**（场景说了算），
 * 声明了但求不出结果的项如实报 `ok:false` + 原因（不许默认通过）。
 */
export function evaluateChecks(scenario, trace, arrival) {
  const checks = Array.isArray(scenario?.checks) ? scenario.checks : [];
  const results = [];
  for (const name of checks) {
    if (name === "arrival") {
      const verdict = evaluateArrival(scenario, trace, arrival);
      results.push({ name, ok: verdict.ok, detail: verdict.reason, ...verdict });
    } else if (name === "route_completion") {
      const verdict = evaluateRouteCompletion(scenario, trace, arrival);
      results.push({ name, ok: verdict.ok, detail: verdict.reason, ...verdict });
    } else {
      results.push({ name, ok: false, detail: `未知检查项 ${JSON.stringify(name)}（场景声明了但运行侧不认识）` });
    }
  }
  return results;
}

/** 运行摘要（判据 + 度量 + 记录器产物清单）——UI 与测试都读这一个形状。 */
export function buildRunSummary(scenario, trace, arrival) {
  const checks = evaluateChecks(scenario, trace, arrival);
  const metrics = summarizeRun(scenario, trace);
  const recorders = Array.isArray(scenario?.recorders) ? scenario.recorders : [];
  return {
    scenarioId: scenario?.scenario_id || "",
    commandSource: scenario?.commandSource || scenario?.command_source || "",
    checks,
    metrics,
    passed: checks.length > 0 && checks.every((check) => check.ok),
    recorders,
    // 记录器产物：声明的才产出（未声明的不造文件，场景说了算）
    artifacts: recorders.map((name) => (name === "trajectory" ? "trajectory.json" : name === "metrics" ? "metrics.json" : `${name}.json`)),
  };
}

/** 记录器产物内容（trajectory = 全量采样；metrics = 摘要 + 判据）。 */
export function recorderArtifacts(scenario, trace, arrival) {
  const summary = buildRunSummary(scenario, trace, arrival);
  const out = {};
  if (summary.recorders.includes("trajectory")) out["trajectory.json"] = trace;
  if (summary.recorders.includes("metrics")) out["metrics.json"] = { metrics: summary.metrics, checks: summary.checks };
  return out;
}
