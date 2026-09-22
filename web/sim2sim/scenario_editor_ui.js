// Scenario 编辑器的 DOM 接线（S5）。**规则不在这里** —— 组合/校验/闸门全在
// `scenario_editor.js`（纯函数、有 node 单测）；本文件只做三件事：
//   1. 把服务端真值喂进表单（地图 / 机器人 / 策略 / 观测项目录）；
//   2. 每次改动 → 组合 → 本地判据（先拦）→ 服务端校验 + A 类绑定校验（后拦）；
//   3. 「启动仿真」按 `toSimParams` 重写 iframe src（场景 → 仿真页参数）。
//
// 分工的边界：**浏览器不发明参数、不发明阈值**。所有能取真值的东西都从接口拿
// （地图 `/api/simulation/maps`、策略 `/api/robots/presets/<id>`、观测项目录
// `/api/perception/items`），拿不到就如实显示"不可用"，不在前端编一份。

import {
  CHECK_OPTIONS,
  COMMAND_SOURCES,
  RECORDER_OPTIONS,
  SCENARIO_STEPS,
  TERRAIN_KINDS,
  applyTaskPluginResult,
  bindingGate,
  composeScenario,
  defaultState,
  describeScenario,
  stepHint,
  taskPluginOptions,
  toQuery,
  toSimParams,
} from "./scenario_editor.js";
// A1：完整场景的交运（postMessage）与判据/摘要的**纯逻辑**在那边，这里只发/收。
import {
  SCENARIO_MESSAGE_TYPE,
  toScenarioMessage,
} from "./scenario_run.js";

const $ = (id) => document.getElementById(id);

const COMMAND_SOURCE_LABELS = {
  policy: "策略（policy）",
  planner: "外部规划（planner）",
  perception: "感知决策（perception）",
  script: "脚本（script）",
  teleop: "遥操作（teleop）",
};
const TERRAIN_LABELS = {
  flat: "平地",
  slope: "斜坡",
  stairs: "楼梯",
  noise: "噪声地",
  obstacle_mix: "混合障碍",
};

let state = defaultState();
let mapsAvailable = false;
let policiesLoading = false;
/** 服务端任务插件清单（下拉项 + 描述），由 `loadTaskPlugins()` 填。 */
let taskPlugins = new Map();

// ── 取数：一律用服务端真值 ────────────────────────────────────────────────
// HTTP 错误 / 超时 / JSON 解析 / 中文错误消息的**唯一实现**在 `web/shared/api.js`
// （UMD 形态：本页是 ES module，经全局 `LSApi` 取用；`advanced_sim.html` 里以普通脚本
// 先加载它，普通脚本先于模块执行 ⇒ 模块里 `LSApi` 一定有值）。
//
// **2026-09-22 修**：本文件此前自建了第二个 `jsonFetch`——它只查 `response.ok`、不取后端
// `detail`，与共享实现各自演化；被 `web/shared/api.test.mjs` 的源码面守卫判红
// （"JSON fetch 封装应只在 web/shared/api.js"）。删掉，6 处调用全部改走共享实现。
async function loadMaps() {
  const select = $("scMap");
  try {
    const payload = await LSApi.fetchJson("/api/simulation/maps", { cache: "no-store" });
    const maps = (payload.maps || []).filter((item) => item && item.id);
    if (!maps.length) throw new Error("地图库为空");
    select.innerHTML = maps
      .map((item) => `<option value="${item.id}">${item.label || item.id}${item.mode === "navigation" ? "（导航）" : ""}</option>`)
      .join("");
    select.value = maps.some((item) => item.id === state.mapId) ? state.mapId : maps[0].id;
    mapsAvailable = true;
  } catch (error) {
    select.innerHTML = `<option value="${state.mapId}">${state.mapId}（地图库不可用：${error.message}）</option>`;
    mapsAvailable = false;
  }
}

async function loadRobots() {
  const select = $("scRobot");
  try {
    const payload = await LSApi.fetchJson("/api/robots/presets", { cache: "no-store" });
    const presets = (payload.presets || []).filter((item) => item && item.robot_id);
    if (!presets.length) throw new Error("没有可用机器人包");
    select.innerHTML = presets.map((item) => `<option value="${item.robot_id}">${item.robot_id}</option>`).join("");
    select.value = presets.some((item) => item.robot_id === state.robot) ? state.robot : presets[0].robot_id;
  } catch (error) {
    select.innerHTML = `<option value="${state.robot}">${state.robot}（机器人清单不可用：${error.message}）</option>`;
  }
}

async function loadPolicies(robotId) {
  const select = $("scPolicy");
  if (!robotId) {
    select.innerHTML = '<option value="">（先选机器人）</option>';
    return;
  }
  policiesLoading = true;
  select.innerHTML = '<option value="">加载中…</option>';
  try {
    // 与 evaluation.html 同口径：包内 `simulation/config.json` 的 policies 声明就是策略清单
    const preset = await LSApi.fetchJson(
      `/api/robots/presets/${encodeURIComponent(robotId)}`, { cache: "no-store" },
    );
    const policies = ((preset.simulation_config || {}).policies || []).filter((item) => item && item.id);
    select.innerHTML = '<option value="">（不指定策略：跳过 A 类绑定校验）</option>'
      + policies.map((item) => `<option value="${item.id}">${item.label || item.id}</option>`).join("");
    if (policies.some((item) => item.id === state.policy)) select.value = state.policy;
  } catch (error) {
    select.innerHTML = `<option value="">（策略清单不可用：${error.message}）</option>`;
  } finally {
    policiesLoading = false;
  }
}

async function loadPerceptionItems() {
  const host = $("scPerceptionItems");
  try {
    const payload = await LSApi.fetchJson("/api/perception/items", { cache: "no-store" });
    const items = (payload.items || []).filter((item) => item && item.id);
    host.textContent = `观测项目录 ${items.length} 项：${items.map((item) => item.id).join(" / ")}`;
  } catch (error) {
    host.textContent = `观测项目录不可用：${error.message}`;
  }
}

// ── 任务插件（服务端注册表 → 下拉 + 一键填入）──────────────────────────────
// 页面**不编任务清单、不编传感器需求**：`GET /api/task-plugins` 给清单，
// `POST /api/task-plugins/{id}/instantiate` 给"补齐后的场景 + 观测项 + 就绪度"。
async function loadTaskPlugins() {
  const select = $("scTaskPlugin");
  try {
    const payload = await LSApi.fetchJson("/api/task-plugins", { cache: "no-store" });
    const options = taskPluginOptions(payload);
    if (!options.length) throw new Error("注册表里没有任务插件");
    select.innerHTML = options.map((item) => `<option value="${item.id}">${
      escapeHtml(item.label)}（${escapeHtml(item.id)}｜${item.sensorCount} 个传感器）</option>`).join("");
    taskPlugins = new Map(options.map((item) => [item.id, item]));
    renderTaskPluginHint();
  } catch (error) {
    select.innerHTML = '<option value="">（任务插件不可用）</option>';
    $("scTaskPluginResult").textContent = `任务插件清单不可用：${error.message}`;
  }
}

function renderTaskPluginHint() {
  const item = taskPlugins.get($("scTaskPlugin").value);
  $("scTaskPluginResult").textContent = item
    ? `${item.label}${item.taskType ? `（task_type=${item.taskType}）` : ""}：${item.description}`
    : "（未选任务插件）";
}

async function fillFromTaskPlugin() {
  const pluginId = $("scTaskPlugin").value;
  const host = $("scTaskPluginResult");
  if (!pluginId) { host.textContent = "先选一条任务插件。"; return; }
  const composed = composeScenario(readForm());
  if (!composed.ok) {
    host.textContent = "当前表单里的场景还不合法，先修好再一键填入（否则补出来的场景也是坏的）。";
    return;
  }
  host.textContent = `正在向服务端实例化 ${pluginId} …`;
  try {
    const payload = await LSApi.fetchJson(
      `/api/task-plugins/${encodeURIComponent(pluginId)}/instantiate`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario: composed.scenario }),
      },
    );
    const result = applyTaskPluginResult(readForm(), payload);
    if (!result.ok) { host.textContent = `填入被拒：${result.problems.join("；")}`; return; }
    state = result.state;
    applyStateToForm(state);
    await refresh();
    host.innerHTML = renderTaskPluginSummary(result.summary);
  } catch (error) {
    host.textContent = `实例化失败：${error.message}`;
  }
}

/**
 * 就绪度的**诚实显示**：`verified=false` 时必须把服务端给的理由原样摆出来，
 * 不许在页面上把它渲染成"可用"（传感器插件当前止步 `registered`）。
 */
function renderTaskPluginSummary(summary) {
  if (!summary) return "";
  const rows = [
    `<div><strong>已填入 ${escapeHtml(summary.pluginId)}</strong>`
    + `（观测项：${escapeHtml(summary.obsVerdict || "—")}${summary.obsTerms.length ? ` → ${escapeHtml(summary.obsTerms.join(" / "))}` : ""}）</div>`,
    `<div>改动的字段：${escapeHtml(summary.applied.join(" / ") || "（无：插件声明与当前场景一致）")}</div>`,
    summary.verified
      ? '<div class="sc-ok">就绪度：已验证</div>'
      : `<div class="sc-warn">就绪度：<strong>仅“声明可实例化”，不能声称“能跑”</strong>`
        + `${summary.readinessReason ? `—— ${escapeHtml(summary.readinessReason)}` : ""}</div>`,
  ];
  if (summary.blockers.length) {
    rows.push(`<div class="sc-bad">阻断项：${escapeHtml(summary.blockers.join(" / "))}</div>`);
  }
  if (summary.unconsumedChecks.length || summary.unconsumedRecorders.length) {
    rows.push(`<div class="sc-warn">声明了但今天没人执行的：${escapeHtml(
      [...summary.unconsumedChecks, ...summary.unconsumedRecorders].join(" / "))}</div>`);
  }
  if (summary.unmappedChecks.length || summary.unmappedRecorders.length) {
    rows.push(`<div class="sc-warn">表单里没有对应勾选框的项（已按服务端原样记在场景里）：${escapeHtml(
      [...summary.unmappedChecks, ...summary.unmappedRecorders].join(" / "))}</div>`);
  }
  return rows.join("");
}

// ── 表单 ⇄ 状态 ──────────────────────────────────────────────────────────
function parseWaypoints(text) {
  return String(text || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [x, y] = line.split(",").map((part) => Number(part.trim()));
      return { x, y };
    })
    .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
}

function readForm() {
  const checks = CHECK_OPTIONS.filter((key) => $(`scCheck_${key}`)?.checked);
  const recorders = RECORDER_OPTIONS.filter((key) => $(`scRecorder_${key}`)?.checked);
  return {
    ...state,
    scenarioId: $("scScenarioId").value.trim(),
    robot: $("scRobot").value,
    policy: $("scPolicy").value,
    mapId: $("scMap").value,
    mode: $("scCommandSource").value === "policy" ? "basic" : "navigation",
    seed: Number($("scSeed").value) || 0,
    episodeLengthS: Number($("scEpisode").value) || 60,
    terrainKind: $("scTerrain").value,
    perception: {
      route: $("scRoute").value,
      heightfield: $("scHeightfield").checked,
      depthCamera: $("scDepthCamera").checked,
      footContact: $("scFootContact").checked,
      mount: $("scMount").value.trim() || "base",
    },
    depthCamera: {
      width: Number($("scDepthWidth").value) || 106,
      height: Number($("scDepthHeight").value) || 60,
      cutoffM: Number($("scDepthCutoff").value) || 3,
    },
    commandSource: $("scCommandSource").value,
    waypoints: parseWaypoints($("scWaypoints").value),
    checks,
    recorders,
    commandLimits: {
      vx: Number($("scLimitVx").value) || 1,
      vy: Number($("scLimitVy").value) || 1,
      wz: Number($("scLimitWz").value) || 1,
    },
  };
}

function renderReport(html) {
  $("scReport").innerHTML = html;
}

/** 状态 → 表单（一键填入的落点：**只写自己有权威的那几项**，其余字段不动）。 */
function applyStateToForm(next) {
  $("scRoute").value = next.perception?.route === "obs" ? "obs" : "external";
  $("scHeightfield").checked = Boolean(next.perception?.heightfield);
  $("scDepthCamera").checked = Boolean(next.perception?.depthCamera);
  $("scFootContact").checked = Boolean(next.perception?.footContact);
  $("scMount").value = next.perception?.mount || "base";
  if (next.depthCamera) {
    $("scDepthWidth").value = String(next.depthCamera.width);
    $("scDepthHeight").value = String(next.depthCamera.height);
    $("scDepthCutoff").value = String(next.depthCamera.cutoffM);
  }
  if (COMMAND_SOURCES.includes(next.commandSource)) $("scCommandSource").value = next.commandSource;
  for (const key of CHECK_OPTIONS) {
    const box = $(`scCheck_${key}`);
    if (box) box.checked = (next.checks || []).includes(key);
  }
  for (const key of RECORDER_OPTIONS) {
    const box = $(`scRecorder_${key}`);
    if (box) box.checked = (next.recorders || []).includes(key);
  }
  syncWaypointVisibility();
}

function renderScenarioSummary(composed) {
  $("scSummary").textContent = describeScenario(composed.scenario);
}

/** 需要航点的命令来源：显出航点编辑区（其余情况藏起来，避免误填）。 */
function syncWaypointVisibility() {
  const needs = $("scCommandSource").value !== "policy";
  $("scWaypointsRow").hidden = !needs;
}

function localProblemsHtml(problems) {
  if (!problems.length) return "";
  return `<div class="sc-bad"><strong>场景不合法，先修这些：</strong><ul>${
    problems.map((text) => `<li>${escapeHtml(text)}</li>`).join("")
  }</ul></div>`;
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[char]));
}

// ── 三道拦：本地判据 → 服务端场景校验 → A 类绑定校验 ────────────────────────
let refreshSeq = 0;

async function refresh() {
  const seq = ++refreshSeq;
  state = readForm();
  syncWaypointVisibility();
  const composed = composeScenario(state);
  renderScenarioSummary(composed);

  let scenarioVerdict = { ok: composed.ok, problems: composed.problems };
  let binding = null;
  let notes = [localProblemsHtml(composed.problems)];

  if (composed.ok) {
    try {
      const payload = await LSApi.fetchJson("/api/scenarios/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(composed.scenario),
      });
      scenarioVerdict = { ok: Boolean(payload.valid), problems: payload.errors || payload.detail || [] };
      notes.push(payload.valid
        ? '<div class="sc-ok">服务端场景校验：通过</div>'
        : `<div class="sc-bad"><strong>服务端场景校验未通过：</strong><pre>${escapeHtml(JSON.stringify(payload, null, 2))}</pre></div>`);
    } catch (error) {
      scenarioVerdict = { ok: false, problems: [error.message] };
      notes.push(`<div class="sc-bad">服务端场景校验不可用：${escapeHtml(error.message)}</div>`);
    }

    // A 类（route=obs）且选了策略 ⇒ 问服务端"这策略真的吃了这些传感器吗"
    if (composed.route === "obs" && state.policy) {
      try {
        binding = await LSApi.fetchJson("/api/perception/binding", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ robot_id: state.robot, policy_id: state.policy, perception: composed.scenario.perception }),
        });
      } catch (error) {
        // 拿不到结论不能当成"通过"——那是 fail-open；按最严处理。
        binding = { ok: false, verdict: "missing", reason: `绑定校验不可用：${error.message}`, missing: [], fix: [] };
      }
    }
  }

  if (seq !== refreshSeq) return;
  const gate = bindingGate({ scenarioVerdict, binding });
  $("scStart").disabled = !gate.canStart;

  if (binding) {
    if (binding.verdict === "not_applicable") {
      notes.push(`<div class="sc-ok">A 类绑定：不适用（${escapeHtml(binding.reason || "")}）</div>`);
    } else if (binding.ok) {
      notes.push(`<div class="sc-ok">A 类绑定：通过（策略已声明 ${escapeHtml((binding.declared || []).join(" / ") || "无")}）</div>`);
    } else {
      notes.push(
        `<div class="sc-bad"><strong>拒绝启动：${escapeHtml(gate.reason)}</strong>`
        + `<div>缺：${escapeHtml((gate.missing || []).join(" / ") || "—")}</div>`
        + `<div>怎么修：<ul>${(gate.fixes || []).map((text) => `<li>${escapeHtml(text)}</li>`).join("")}</ul></div></div>`,
      );
    }
  } else if (composed.route === "obs" && !state.policy) {
    notes.push('<div class="sc-warn">这是 A 类场景（感知进策略观测）但没选策略 —— 服务端在给了 policy_id 时才会校验绑定；此处按不拦处理。</div>');
  }
  renderReport(notes.join(""));
}

// ── 启动：场景 → 仿真页参数 ────────────────────────────────────────────────
// A1：**两条腿同时走**。URL 参数照旧发（深链接/刷新仍可用，参数仍是仿真页真正认的那几个），
// 但**完整场景**（判据/记录器/感知/指令源/时长/地图）走 postMessage —— 塞进 URL 要么塞不下
// 要么静默失效。握手：发 ready-request → 仿真页就绪后回 ready → **才发场景**（不等就绪就发，
// 仿真页的策略清单还没填，"策略不在清单里"会把一次好场景误判成拒收；仿真页侧也会缓冲，
// 这里等 ready 只是让正常情况下走正路）。
function start() {
  const composed = composeScenario(state);
  if (!composed.ok) return;
  const params = toSimParams(composed.scenario, { robot: state.robot, policy: state.policy });
  params.autoplay = "1";
  const frame = $("advSimFrame");
  frame.src = `sim2sim/index.html?${toQuery(params)}`;
  $("scLastLaunch").textContent = `已启动：${toQuery(params)}`;
  const message = toScenarioMessage(composed.scenario, { robot: state.robot, policy: state.policy });
  const status = (text) => { $("scLastLaunch").textContent = text; };
  const send = () => {
    try {
      frame.contentWindow?.postMessage(message, window.location.origin);
      status(`已启动并交运完整场景（${toQuery(params)}）`);
    } catch (error) {
      status(`已启动，但场景交运失败：${error.message}`);
    }
  };
  let sent = false;
  const sendOnce = () => { if (!sent) { sent = true; send(); } };
  frame.addEventListener("load", () => {
    try {
      frame.contentWindow?.postMessage({ type: "legged-studio:ready-request" }, window.location.origin);
    } catch (error) { /* 下一行兜底 */ }
    // 兜底：ready 回执慢/丢时不要卡住启动（仿真页侧有缓冲，晚到也会被应用）
    window.setTimeout(sendOnce, 8000);
  }, { once: true });
  window.addEventListener("message", (event) => {
    if (event.origin !== window.location.origin) return;
    const data = event.data;
    if (data?.type === "legged-studio:ready") { sendOnce(); return; }
    if (data?.type !== "legged-studio:scenario-applied") return;
    const result = data;
    const skipped = (result.skipped || []).join("；");
    status(result.ok
      ? `场景已在仿真页生效（${(result.applied || []).length} 项）${result.pending ? "（就绪后应用）" : ""}${skipped ? `；未应用：${skipped}` : ""}`
      : `仿真页拒收场景：${result.reason}`);
  });
}

// ── 初始化 ───────────────────────────────────────────────────────────────
// ── 步骤条（范式抄 references_1000framesai/shared_nav.js 的 STEPS）────────────────
// 步骤表在 `scenario_editor.js`（唯一真值），这里只渲染：**加一段 = 步骤表加一条 + HTML 加一段**，
// 其余代码不动。当前步只影响"显示哪一段"，不影响校验（校验永远是整份场景）。
let activeStep = SCENARIO_STEPS[0].id;

function renderSteps() {
  const host = $("scSteps");
  host.innerHTML = SCENARIO_STEPS.map(
    (step) => `<button type="button" class="sc-step" data-step="${step.id}" title="${escapeHtml(step.hint)}">${escapeHtml(step.label)}</button>`,
  ).join("");
}

function selectStep(stepId) {
  const known = SCENARIO_STEPS.some((step) => step.id === stepId);
  activeStep = known ? stepId : SCENARIO_STEPS[0].id;
  for (const button of document.querySelectorAll("#scSteps [data-step]")) {
    button.classList.toggle("active", button.dataset.step === activeStep);
  }
  for (const section of document.querySelectorAll("[data-step]")) {
    if (section.closest("#scSteps")) continue;
    section.hidden = section.dataset.step !== activeStep;
  }
  $("scStepHint").textContent = stepHint(activeStep);
}

function fillStaticSelects() {
  $("scTerrain").innerHTML = TERRAIN_KINDS
    .map((key) => `<option value="${key}">${TERRAIN_LABELS[key] || key}</option>`).join("");
  $("scCommandSource").innerHTML = COMMAND_SOURCES
    .map((key) => `<option value="${key}">${COMMAND_SOURCE_LABELS[key] || key}</option>`).join("");
  $("scChecks").innerHTML = CHECK_OPTIONS
    .map((key) => `<label><input type="checkbox" id="scCheck_${key}" checked> ${key}</label>`).join("");
  $("scRecorders").innerHTML = RECORDER_OPTIONS
    .map((key) => `<label><input type="checkbox" id="scRecorder_${key}" checked> ${key}</label>`).join("");
}

function bindEvents() {
  const watched = [
    "scScenarioId", "scRobot", "scPolicy", "scMap", "scSeed", "scEpisode", "scTerrain",
    "scRoute", "scHeightfield", "scDepthCamera", "scFootContact", "scMount",
    "scDepthWidth", "scDepthHeight", "scDepthCutoff",
    "scCommandSource", "scWaypoints", "scLimitVx", "scLimitVy", "scLimitWz",
    ...CHECK_OPTIONS.map((key) => `scCheck_${key}`),
    ...RECORDER_OPTIONS.map((key) => `scRecorder_${key}`),
  ];
  for (const id of watched) {
    const element = $(id);
    if (!element) continue;
    element.addEventListener("change", () => { refresh(); });
    element.addEventListener("input", () => { refresh(); });
  }
  $("scRobot").addEventListener("change", async () => {
    await loadPolicies($("scRobot").value);
    refresh();
  });
  $("scStart").addEventListener("click", start);
  $("scValidate").addEventListener("click", () => { refresh(); });
  // 任务插件：选一条只更新说明（**不自动改表单** —— 改字段是「一键填入」这个显式动作）；
  // 点「一键填入」才把服务端算好的补丁写进表单并重新校验。
  $("scTaskPlugin").addEventListener("change", renderTaskPluginHint);
  $("scTaskFill").addEventListener("click", () => { fillFromTaskPlugin(); });
  $("scSteps").addEventListener("click", (event) => {
    const button = event.target.closest?.("[data-step]");
    if (button) selectStep(button.dataset.step);
  });
}

async function init() {
  fillStaticSelects();
  renderSteps();
  selectStep(activeStep);
  await Promise.all([loadMaps(), loadRobots(), loadPerceptionItems()]);
  await loadTaskPlugins();
  await loadPolicies($("scRobot").value);
  bindEvents();
  refresh();
}

init().catch((error) => {
  renderReport(`<div class="sc-bad">编辑器初始化失败：${escapeHtml(error.message)}</div>`);
});
