// Scenario 编辑器的**纯逻辑**（S5）：表单状态 → 场景契约 → 仿真参数 → 启动闸门。
//
// 为什么单独成模块（而不是写进 advanced_sim.html 的 `<script>` 里）：
//   * 这些规则**必须可测**——`node web/sim2sim/scenario_editor.test.mjs` 直接跑，不需要浏览器；
//   * 场景合法性有**两处**权威：服务端 `contracts/scenario_contract.py`（真正的 fail-closed）
//     与本模块（**提前**在页面上拦住，省一次往返、并把原因说清）。两边规则必须一致，
//     本模块只做"镜像"，**不做加码**：判据抄自 ScenarioContract.validate_perception_routing
//     与 PerceptionSpec 的字段面，允许集合也逐字对齐。
//
// 浏览器不做的事：**不自己算阈值、不自己规划路径**（那些是服务端唯一真值，见 navigation.js
// 与 backend/navigation_plan.py 的分工注释）。

/** 场景 id 的允许形式（与 `contracts/scenario_contract.py` 的 Field(pattern=...) 逐字一致）。 */
export const SCENARIO_ID_RE = /^[a-z0-9_-]+$/;

/** `command_source` 允许值（抄自契约的 Literal）。 */
export const COMMAND_SOURCES = ["policy", "planner", "perception", "script", "teleop"];

/** 地形种类（抄自 TerrainSpec.kind 的 Literal）。 */
export const TERRAIN_KINDS = ["flat", "slope", "stairs", "noise", "obstacle_mix"];

/** 感知字段 → 契约字段名（与 `backend/perception_binding.FIELD_TO_ITEM` 的键同源）。 */
export const PERCEPTION_FIELDS = ["heightfield", "depth_camera", "foot_contact"];

/** `checks` / `recorders` 的候选（契约里是自由字符串数组，这里给常用项做勾选）。 */
export const CHECK_OPTIONS = ["arrival", "route_completion"];
export const RECORDER_OPTIONS = ["trajectory", "metrics"];

/** 需要航点的命令来源（B 类外部决策）——契约里"没目标就不算导航"。 */
export const WAYPOINT_SOURCES = ["planner", "perception"];

/**
 * 编辑器的**步骤表**（声明式，交互范式抄 `00_resources/references_1000framesai/shared_nav.js`
 * 的 `STEPS`：**加一段 = 加一条**，其余代码不动）。
 *
 * 为什么是数据而不是写死的四段 HTML：步骤既决定"渲染哪几段"，也决定"标题栏怎么显示"、
 * "测试该核哪些段"。写死就会三处各说一套；声明成表则**唯一真值**在这里，页面与测试都读它。
 * 步骤 `id` 同时是 HTML 里各段的 `data-step` 值（DOM 接线测试会核这条一致性）。
 */
export const SCENARIO_STEPS = [
  { id: "identity", label: "场景", hint: "场景 id / 机器人 / 策略 / 种子与时长" },
  { id: "map", label: "地图", hint: "地图库 + 地形种类 + 指令上限" },
  { id: "sensors", label: "传感器", hint: "感知分层 route + 观测项 + 挂载点" },
  { id: "task", label: "任务", hint: "命令来源 + 航点（外部决策必需）" },
  { id: "checks", label: "判据", hint: "检查项与记录器" },
];

/** 表单默认状态：一台 go2 的平地速度追踪，最保守、必然可跑。 */
export function defaultState() {
  return {
    scenarioId: "advanced_probe",
    robot: "unitree_go2",
    policy: "",
    mapId: "flat",
    mode: "basic",
    seed: 0,
    episodeLengthS: 60,
    terrainKind: "flat",
    perception: { route: "external", heightfield: false, depthCamera: false, footContact: false },
    depthCamera: { width: 106, height: 60, cutoffM: 3.0 },
    commandSource: "policy",
    waypoints: [],
    commandLimits: { vx: 1.0, vy: 1.0, wz: 1.0 },
    checks: ["arrival", "route_completion"],
    recorders: ["trajectory", "metrics"],
  };
}

function _perceptionPayload(state) {
  const source = state.perception || {};
  const enabled = {};
  if (source.heightfield) enabled.heightfield = true;
  if (source.footContact) enabled.foot_contact = true;
  if (source.depthCamera) {
    const camera = state.depthCamera || {};
    enabled.depth_camera = {
      width: Number(camera.width) || 106,
      height: Number(camera.height) || 60,
      cutoff_m: Number(camera.cutoffM) || 3.0,
    };
  }
  // 一个观测项都没勾时**不写 perception**（而不是写个空壳）：契约里 perception=null 表示
  // "本场景不声明感知"，与"声明了但什么都没开"是两件事，前者不参与绑定校验、后者会被判
  // not_applicable —— 少一种中间态就少一处歧义。
  if (!Object.keys(enabled).length) return null;
  return { ...enabled, route: source.route === "obs" ? "obs" : "external", mount: source.mount || "base" };
}

/** 场景感知项的启用数（供 UI 提示"勾了但没有策略吃它"）。 */
export function enabledPerceptionItems(perception) {
  if (!perception) return [];
  return PERCEPTION_FIELDS.filter((field) => {
    const value = perception[field];
    return value === true || (value && typeof value === "object");
  });
}

/**
 * 表单状态 → 场景契约载荷（**失败即 `ok:false` 并列出全部问题**，不静默丢弃字段）。
 *
 * 三条判据抄自服务端契约（**同一套规则**，页面上提前拦是为了把原因解释给人看）：
 *   1. `scenario_id` 必须匹配 `^[a-z0-9_-]+$`；
 *   2. `route=obs`（A 类）⇒ `command_source` 必须为 `policy`；
 *   3. `command_source ∈ {planner, perception}` ⇒ 必须有航点。
 */
export function composeScenario(state) {
  const input = state || {};
  const problems = [];

  const scenarioId = String(input.scenarioId || "").trim();
  if (!scenarioId) problems.push("场景 id 不能为空");
  else if (!SCENARIO_ID_RE.test(scenarioId)) {
    problems.push(`场景 id ${JSON.stringify(scenarioId)} 只能用小写字母/数字/下划线/连字符`);
  }

  const commandSource = COMMAND_SOURCES.includes(input.commandSource) ? input.commandSource : "policy";
  const waypoints = (Array.isArray(input.waypoints) ? input.waypoints : [])
    .map((point) => ({ x: Number(point?.x) || 0, y: Number(point?.y) || 0 }))
    .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));

  const perception = _perceptionPayload(input);
  // **意图与载荷分开**：一个观测项都没勾时载荷为 null（见 `_perceptionPayload`），但"用户声明的
  // route"仍要单独留着 —— 否则 `route=obs` 会被静默降级成外部感知，下面那条"没有可绑定的东西"
  // 的判据**永远不会触发**（本模块第一版就这么错的，被 scenario_editor.test.mjs 第 6 组抓住）。
  const routeIntent = input.perception?.route === "obs" ? "obs" : "external";
  const route = perception?.route || routeIntent;
  if (routeIntent === "obs" && commandSource !== "policy") {
    problems.push("感知 route=obs（A 类：感知进策略观测）要求 command_source=policy；感知在策略外请用 route=external");
  }
  if (WAYPOINT_SOURCES.includes(commandSource) && !waypoints.length) {
    problems.push(`command_source=${commandSource} 需要至少一个航点（没有目标就判不出到达）`);
  }
  if (routeIntent === "obs" && enabledPerceptionItems(perception).length === 0) {
    problems.push("感知 route=obs 但一个观测项都没启用 —— 没有可绑定的东西，绑定校验也无从谈起");
  }

  const scenario = {
    schema_version: "scenario-contract-1.1",
    scenario_id: scenarioId,
    map_id: String(input.mapId || "flat"),
    mode: input.mode === "navigation" ? "navigation" : "basic",
    seed: Number(input.seed) || 0,
    episode_length_s: Number(input.episodeLengthS) || 60,
    waypoints,
    command_limits: {
      vx: Number(input.commandLimits?.vx) || 1.0,
      vy: Number(input.commandLimits?.vy) || 1.0,
      wz: Number(input.commandLimits?.wz) || 1.0,
    },
    terrain: { kind: TERRAIN_KINDS.includes(input.terrainKind) ? input.terrainKind : "flat" },
    command_source: commandSource,
    checks: (Array.isArray(input.checks) ? input.checks : []).slice(),
    recorders: (Array.isArray(input.recorders) ? input.recorders : []).slice(),
  };
  if (perception) scenario.perception = perception;

  return { ok: problems.length === 0, scenario, problems, route: routeIntent };
}

/**
 * 场景 → 仿真页 URL 参数。
 *
 * 参数名**逐个对齐** `web/sim2sim/app.js` 真实消费的那些（`terrain` / `nav` / `nav_waypoints` /
 * `seed` / `robot` / `policy` / `surface` / `view` / `embedded`）；本模块**不发明新参数**——
 * 造一个仿真页不认的参数等于静默失效。
 */
export function toSimParams(scenario, { robot = "", policy = "", embedded = true, surface = "advanced" } = {}) {
  const params = {};
  if (embedded) params.embedded = "1";
  if (surface) params.surface = surface;
  params.view = "advanced";
  if (robot) params.robot = robot;
  if (policy) params.policy = policy;
  if (scenario) {
    if (scenario.map_id) params.terrain = String(scenario.map_id);
    if (Number.isFinite(Number(scenario.seed))) params.seed = String(Number(scenario.seed));
    // 航点只在"外部决策驱动"时才下发：policy 驱动时导航跟随不应接管（优先级见 app.js：
    // 确定性回放 > planner > 手动）。
    if (WAYPOINT_SOURCES.includes(scenario.command_source) && Array.isArray(scenario.waypoints) && scenario.waypoints.length) {
      params.nav = String(scenario.map_id || "");
      params.nav_waypoints = scenario.waypoints.map((point) => `${point.x},${point.y}`).join(";");
    }
  }
  return params;
}

/** 参数对象 → 查询串（保持稳定顺序，便于比对与测试）。 */
export function toQuery(params) {
  const search = new URLSearchParams();
  for (const key of Object.keys(params || {})) {
    const value = params[key];
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  return search.toString();
}

/**
 * **启动闸门**（S2② 的前端半边）：把"场景校验"与"A 类绑定校验"两个结论合成一个可否启动。
 *
 * 服务端已经 fail-closed（`POST /api/simulation/sessions` 会拒），这里再做一遍的意义是
 * **把原因说在人点按钮之前**，而不是让他点完收到一个 400。两侧判据同源，不做加码：
 *   * 场景自身不合法 ⇒ 不许启动；
 *   * 场景要求 A 类感知、而绑定校验说缺项 ⇒ 不许启动（**这才是 S2② 要的效果**）；
 *   * B 类（route=external）⇒ 绑定校验返回 not_applicable，不拦。
 */
export function bindingGate({ scenarioVerdict, binding } = {}) {
  if (scenarioVerdict && scenarioVerdict.ok === false) {
    return {
      canStart: false,
      reason: "场景本身不合法",
      problems: scenarioVerdict.problems || [],
      missing: [],
      fixes: [],
    };
  }
  const verdict = binding || null;
  if (!verdict || verdict.verdict === "not_applicable") {
    return { canStart: true, reason: "", problems: [], missing: [], fixes: [] };
  }
  if (verdict.ok) {
    return { canStart: true, reason: "", problems: [], missing: [], fixes: [] };
  }
  return {
    canStart: false,
    reason: verdict.reason || "A 类感知与所选策略不匹配",
    problems: [],
    missing: verdict.missing || [],
    fixes: verdict.fix || [],
  };
}

/** 步骤表里某个 id 对应的一句话说明（找不到时回退空串，不抛 —— 少一步就少一句话，不该崩）。 */
export function stepHint(stepId) {
  const step = SCENARIO_STEPS.find((item) => item.id === stepId);
  return step ? step.hint || "" : "";
}

/** 一行中文摘要（编辑器标题栏显示"现在这份场景是什么"）。 */
export function describeScenario(scenario) {
  if (!scenario) return "（尚未生成场景）";
  const parts = [
    `场景 ${scenario.scenario_id}`,
    `地图 ${scenario.map_id}`,
    `地形 ${scenario.terrain?.kind || "flat"}`,
    `命令 ${scenario.command_source}`,
  ];
  const items = enabledPerceptionItems(scenario.perception);
  parts.push(items.length ? `感知 ${scenario.perception.route}（${items.join(" / ")}）` : "无感知");
  return parts.join(" · ");
}
