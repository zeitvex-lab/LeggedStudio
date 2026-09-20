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
  bindingGate,
  composeScenario,
  defaultState,
  describeScenario,
  stepHint,
  toQuery,
  toSimParams,
} from "./scenario_editor.js";

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

async function jsonFetch(url, options) {
  const response = await fetch(url, { cache: "no-store", ...options });
  if (!response.ok) throw new Error(`${url} → HTTP ${response.status}`);
  return response.json();
}

// ── 取数：一律用服务端真值 ────────────────────────────────────────────────
async function loadMaps() {
  const select = $("scMap");
  try {
    const payload = await jsonFetch("/api/simulation/maps");
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
    const payload = await jsonFetch("/api/robots/presets");
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
    const preset = await jsonFetch(`/api/robots/presets/${encodeURIComponent(robotId)}`);
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
    const payload = await jsonFetch("/api/perception/items");
    const items = (payload.items || []).filter((item) => item && item.id);
    host.textContent = `观测项目录 ${items.length} 项：${items.map((item) => item.id).join(" / ")}`;
  } catch (error) {
    host.textContent = `观测项目录不可用：${error.message}`;
  }
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
      const payload = await jsonFetch("/api/scenarios/validate", {
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
        binding = await jsonFetch("/api/perception/binding", {
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
function start() {
  const composed = composeScenario(state);
  if (!composed.ok) return;
  const params = toSimParams(composed.scenario, { robot: state.robot, policy: state.policy });
  params.autoplay = "1";
  const frame = $("advSimFrame");
  frame.src = `sim2sim/index.html?${toQuery(params)}`;
  $("scLastLaunch").textContent = `已启动：${toQuery(params)}`;
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
  await loadPolicies($("scRobot").value);
  bindEvents();
  refresh();
}

init().catch((error) => {
  renderReport(`<div class="sc-bad">编辑器初始化失败：${escapeHtml(error.message)}</div>`);
});
