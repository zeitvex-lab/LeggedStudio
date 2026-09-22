// Scenario 编辑器纯逻辑单测（`node web/sim2sim/scenario_editor.test.mjs` 直接跑）。
//
// 钉的是 S5 的三件事：
//   · **场景组合**：表单 → 契约载荷，三条 fail-closed 判据与服务端 ScenarioContract 一致
//     （route=obs⇒policy、外部决策⇒有航点、route=obs⇒至少一项观测）；
//   · **URL 映射**：只产出仿真页真正认的参数（不发明新参数，否则静默失效），
//     且航点只在外部决策驱动时下发；
//   · **启动闸门**（S2② 前端半边）：场景不合法或 A 类绑定缺项 ⇒ 不许启动，并给出缺什么/怎么修；
//   · **执行器能力**（A2）：当前执行器跑不了的指令来源在组合期就拦（与 backend/executors.py
//     的 UNSUPPORTED_CONTRACT_OPTIONS 同口径），且 URL 参数仍只发仿真页真正认的那些
//     （完整场景走 postMessage —— 见 scenario_run.test.mjs）。
//
// 另加一条**防漂移**核对：组合出的每个字段都必须存在于 `contracts/schema/scenario-contract-1.1.schema.json`
// —— 契约改字段而这里没跟，本测试就红（与 terrain_groups.test.mjs 核对 _index.json 同一手法）。
import assert from "node:assert/strict";

import { readFileSync } from "node:fs";
import {
  applyTaskPluginResult,
  bindingGate,
  composeScenario,
  defaultState,
  describeScenario,
  enabledPerceptionItems,
  taskPluginOptions,
  toQuery,
  toSimParams,
  unsupportedCommandSourceProblems,
  SCENARIO_ID_RE,
  SCENARIO_STEPS,
  stepHint,
} from "./scenario_editor.js";

const SCHEMA = JSON.parse(
  readFileSync(new URL("../../contracts/schema/scenario-contract-1.1.schema.json", import.meta.url), "utf-8"),
);

// 1) 默认状态：可组合、无问题，且**没勾感知时不写 perception**（null ≠ 空壳）
{
  const result = composeScenario(defaultState());
  assert.equal(result.ok, true, `默认状态应可直接组合，问题：${result.problems}`);
  assert.equal(result.scenario.perception, undefined, "未勾任何观测项时不应写 perception");
  assert.equal(result.route, "external");
  assert.equal(result.scenario.schema_version, "scenario-contract-1.1");
  assert.deepEqual(result.scenario.terrain, { kind: "flat" });
}

// 2) 与 schema 防漂移：组合出的字段必须都在契约里，且契约的 required 一个不缺
{
  const scenario = composeScenario(defaultState()).scenario;
  const properties = SCHEMA.properties || {};
  for (const key of Object.keys(scenario)) {
    assert.ok(key in properties, `组合出的字段 ${key} 不在 scenario-contract-1.1.schema.json 里（契约已改？）`);
  }
  for (const key of SCHEMA.required || []) {
    assert.ok(key in scenario, `契约 required 字段 ${key} 未出现在组合结果里`);
  }
}

// 3) scenario_id 判据与服务端同形式
{
  assert.equal(SCENARIO_ID_RE.test("advanced_probe"), true);
  for (const bad of ["", "Advanced Probe", "场景", "has space", "UPPER"]) {
    const result = composeScenario({ ...defaultState(), scenarioId: bad });
    assert.equal(result.ok, false, `场景 id ${JSON.stringify(bad)} 应被判不合法`);
  }
}

// 4) A 类（route=obs）⇒ command_source 必须是 policy（契约硬约束，页面提前拦）
{
  const obs = {
    ...defaultState(),
    perception: { route: "obs", heightfield: true, depthCamera: false, footContact: false },
    commandSource: "planner",
    waypoints: [{ x: 1, y: 0 }],
  };
  const bad = composeScenario(obs);
  assert.equal(bad.ok, false);
  assert.ok(bad.problems.some((text) => text.includes("command_source=policy")), "应指出 route=obs 要求 policy");

  const good = composeScenario({ ...obs, commandSource: "policy" });
  assert.equal(good.ok, true, `route=obs + policy 应通过：${good.problems}`);
  assert.equal(good.scenario.perception.route, "obs");
}

// 5) 外部决策驱动 ⇒ 必须有航点（"没有目标就判不出到达"）
{
  const planner = composeScenario({ ...defaultState(), commandSource: "planner" });
  assert.equal(planner.ok, false);
  assert.ok(planner.problems.some((text) => text.includes("航点")), "应指出缺航点");

  const withWaypoints = composeScenario({
    ...defaultState(),
    commandSource: "planner",
    mode: "navigation",
    waypoints: [{ x: 0, y: 0 }, { x: 2, y: 1 }],
  });
  assert.equal(withWaypoints.ok, true, `planner + 航点应通过：${withWaypoints.problems}`);
  assert.equal(withWaypoints.scenario.waypoints.length, 2);
}

// 6) route=obs 但一个观测项都没勾 ⇒ 拦（没有可绑定的东西）
{
  const result = composeScenario({
    ...defaultState(),
    perception: { route: "obs", heightfield: false, depthCamera: false, footContact: false },
  });
  assert.equal(result.ok, false);
  assert.ok(result.problems.some((text) => text.includes("观测项")), "应指出没有启用任何观测项");
}

// 7) 感知载荷：字段名/默认值与契约一致；勾多项时带全；mount 可改
{
  const result = composeScenario({
    ...defaultState(),
    perception: { route: "external", heightfield: true, depthCamera: true, footContact: true, mount: "head" },
  });
  assert.equal(result.ok, true, `B 类可带多项：${result.problems}`);
  const perception = result.scenario.perception;
  assert.equal(perception.route, "external");
  assert.equal(perception.heightfield, true);
  assert.equal(perception.foot_contact, true);
  assert.deepEqual(perception.depth_camera, { width: 106, height: 60, cutoff_m: 3 });
  assert.equal(perception.mount, "head");
  assert.deepEqual(enabledPerceptionItems(perception).sort(), ["depth_camera", "foot_contact", "heightfield"]);
}

// 8) URL 映射：只产出仿真页认的参数；航点只在外部决策时下发
{
  const policyScenario = composeScenario(defaultState()).scenario;
  const policyParams = toSimParams(policyScenario, { robot: "unitree_go2", policy: "go2-rlsar-robotlab" });
  assert.equal(policyParams.embedded, "1");
  assert.equal(policyParams.surface, "advanced");
  assert.equal(policyParams.robot, "unitree_go2");
  assert.equal(policyParams.policy, "go2-rlsar-robotlab");
  assert.equal(policyParams.terrain, "flat");
  assert.equal(policyParams.nav, undefined, "policy 驱动时不应下发 nav（否则导航接管）");
  assert.equal(policyParams.nav_waypoints, undefined);

  const navScenario = composeScenario({
    ...defaultState(),
    mapId: "warehouse",
    mode: "navigation",
    commandSource: "planner",
    waypoints: [{ x: 0, y: 0 }, { x: 2.5, y: -1 }],
  }).scenario;
  const navParams = toSimParams(navScenario, { robot: "unitree_go2" });
  assert.equal(navParams.terrain, "warehouse");
  assert.equal(navParams.nav, "warehouse");
  assert.equal(navParams.nav_waypoints, "0,0;2.5,-1", "航点格式必须是 x,y;x,y（app.js 按此解析）");
  assert.equal(toQuery({ b: 1, a: 2, skip: "" }), "b=1&a=2", "空值不落进查询串，顺序稳定");
}

// 9) 启动闸门（S2② 前端半边）
{
  const okScenario = composeScenario(defaultState());
  // B 类：绑定校验 not_applicable ⇒ 不拦
  assert.equal(bindingGate({ scenarioVerdict: okScenario, binding: { verdict: "not_applicable", ok: true } }).canStart, true);
  // A 类且绑定通过 ⇒ 放行
  assert.equal(bindingGate({ scenarioVerdict: okScenario, binding: { verdict: "ok", ok: true } }).canStart, true);
  // 场景不合法 ⇒ 拦，并带出问题清单
  const badScenario = composeScenario({ ...defaultState(), commandSource: "planner" });
  const blockedByScenario = bindingGate({ scenarioVerdict: badScenario, binding: null });
  assert.equal(blockedByScenario.canStart, false);
  assert.ok(blockedByScenario.problems.length > 0);
  // A 类绑定缺项 ⇒ 拦，缺什么 + 怎么修都要在
  const blocked = bindingGate({
    scenarioVerdict: okScenario,
    binding: { verdict: "missing", ok: false, missing: ["heightfield"], reason: "A 类感知要求策略声明 ['heightfield']", fix: ["补 profile 声明", "改 route=external"] },
  });
  assert.equal(blocked.canStart, false);
  assert.deepEqual(blocked.missing, ["heightfield"]);
  assert.equal(blocked.fixes.length, 2);
  assert.ok(blocked.reason.includes("heightfield"));
  // 没有绑定结论（未选策略）⇒ 不拦（服务端在给 policy_id 时才校验）
  assert.equal(bindingGate({ scenarioVerdict: okScenario, binding: null }).canStart, true);
}

// 10) 摘要可读：带上场景/地图/地形/命令/感知分层
{
  const scenario = composeScenario({
    ...defaultState(),
    scenarioId: "stairs_probe",
    mapId: "stairs",
    terrainKind: "stairs",
    perception: { route: "obs", heightfield: true, depthCamera: false, footContact: false },
  }).scenario;
  const text = describeScenario(scenario);
  assert.ok(text.includes("stairs_probe"), text);
  assert.ok(text.includes("stairs"), text);
  assert.ok(text.includes("obs"), text);
  assert.ok(text.includes("heightfield"), text);
}

// 11) 步骤表（declare 一次，页面与测试都读它）：S5 点名的四段必须在，id 唯一、标签中文
{
  const ids = SCENARIO_STEPS.map((step) => step.id);
  assert.equal(new Set(ids).size, ids.length, "步骤 id 必须唯一（重复会让步骤条串台）");
  for (const required of ["map", "sensors", "task", "checks"]) {
    assert.ok(ids.includes(required), `S5 要求的「${required}」段必须在步骤表里`);
  }
  for (const step of SCENARIO_STEPS) {
    assert.ok(step.label && /[\u4e00-\u9fff]/.test(step.label), `步骤 ${step.id} 的标签应是中文可读的`);
    assert.ok(step.hint && step.hint.length > 0, `步骤 ${step.id} 应有一句话说明`);
  }
  assert.equal(stepHint("sensors"), SCENARIO_STEPS.find((step) => step.id === "sensors").hint);
  assert.equal(stepHint("no_such_step"), "", "未知步骤回退空串而不是抛错");
}

// 12) A2 执行器能力：浏览器跑不了的指令来源在组合期就拦（与 executors.py 同口径）
{
  assert.deepEqual(unsupportedCommandSourceProblems("policy"), [], "policy 到处能跑");
  assert.deepEqual(unsupportedCommandSourceProblems("planner"), []);
  assert.deepEqual(unsupportedCommandSourceProblems("teleop"), []);
  const script = unsupportedCommandSourceProblems("script");
  assert.equal(script.length, 1);
  assert.match(script[0], /command_source=script/);
  assert.match(script[0], /服务端执行器/);
  const perception = unsupportedCommandSourceProblems("perception");
  assert.match(perception[0], /感知进观测链路/);
  // 换了执行器（服务端）就不再是浏览器这一套限制
  assert.deepEqual(unsupportedCommandSourceProblems("script", "server_mujoco"), []);
  // 组合期也要拦住：选了 script 的场景不许 ok（页面上提前拦，理由是同一套）
  const state = defaultState();
  state.commandSource = "script";
  const composed = composeScenario(state);
  assert.equal(composed.ok, false, "script 场景不许组合通过");
  assert.ok(composed.problems.some((text) => text.includes("command_source=script")), composed.problems.join(" | "));
  // 换回 planner + 给航点 ⇒ 恢复可组合（证明拦的是指令来源，不是别的）
  state.commandSource = "planner";
  state.waypoints = [{ x: 1, y: 1 }, { x: 2, y: 2 }];
  assert.equal(composeScenario(state).ok, true);
}

// 13) A1：URL 参数仍然只发仿真页真正认的那些（完整场景走 postMessage，见 scenario_run.test.mjs）
{
  const state = defaultState();
  state.commandSource = "planner";
  state.waypoints = [{ x: 1, y: 1 }, { x: 2, y: 2 }];
  const { scenario } = composeScenario(state);
  const params = toSimParams(scenario, { robot: "unitree_go2", policy: "go2-loco-45" });
  // URL 里没有的字段不是"忘了发"——它们在 postMessage 的完整场景里（防回归：别把它们塞回 URL）
  for (const key of ["perception", "checks", "recorders", "command_source", "episode_length_s", "mode"]) {
    assert.ok(!(key in params), `${key} 不该出现在 URL 参数里（走 postMessage）`);
  }
  assert.deepEqual(Object.keys(params).sort(), ["autoplay_absent", "embedded", "nav", "nav_waypoints", "policy", "robot", "seed", "surface", "terrain", "view"].filter((k) => k !== "autoplay_absent").sort());
  assert.equal(params.nav_waypoints, "1,1;2,2");
  assert.equal(params.terrain, "flat");
}

// 14) 任务插件：下拉项取自服务端载荷（页面不编清单）
{
  const options = taskPluginOptions({
    plugins: [
      { plugin_id: "wheel-leg-terrain", label: "轮足地形穿越", task_type: "velocity",
        description: "高度扫描 + 足端接触进观测", sensors: [{ plugin_id: "foot_contact" }, { plugin_id: "imu" }] },
      { plugin_id: "no_label" },
      { label: "缺 id ⇒ 丢掉" },
    ],
  });
  assert.deepEqual(options.map((item) => item.id), ["wheel-leg-terrain", "no_label"]);
  assert.equal(options[0].sensorCount, 2);
  assert.equal(options[1].label, "no_label", "缺 label 时回退 plugin_id");
  assert.deepEqual(taskPluginOptions(null), [], "取不到载荷就得空表，不许编");
}

// 15) 一键填入：改的是服务端回的那几项（route / 感知开关 / 命令来源 / 判据 / 记录器）
{
  const before = defaultState();
  const response = {
    plugin_id: "wheel-leg-terrain",
    task_type: "velocity",
    applied: { "perception.heightfield": true, "perception.foot_contact": true, "perception.route": "obs" },
    scenario: {
      command_source: "policy",
      perception: { route: "obs", heightfield: true, foot_contact: true, mount: "base" },
      checks: [],
      recorders: ["metrics"],
    },
    obs_items: { verdict: "generated", items: [{ term: "foot_contact" }, { term: "heightmap" }] },
    readiness: { verified: false, reason: "传感器插件当前止步 registered", blockers: [], unconsumed_checks: [],
                 unconsumed_recorders: [] },
  };
  const result = applyTaskPluginResult(before, response);
  assert.equal(result.ok, true, result.problems.join(" | "));
  assert.equal(result.state.perception.route, "obs");
  assert.equal(result.state.perception.heightfield, true);
  assert.equal(result.state.perception.footContact, true);
  assert.equal(result.state.perception.depthCamera, false, "插件没声明深度 ⇒ 不许顺手打开");
  assert.deepEqual(result.state.recorders, ["metrics"]);
  assert.deepEqual(result.summary.obsTerms, ["foot_contact", "heightmap"]);
  assert.equal(result.summary.applied.length, 3);
  // **诚实面**：verified=false 原样带出，页面照着显示，不许在前端翻成"可用"
  assert.equal(result.summary.verified, false);
  assert.ok(result.summary.readinessReason.includes("registered"), result.summary.readinessReason);
}

// 16) 一键填入：缺场景载荷 ⇒ 整次拒绝（不做"部分应用"）
{
  const before = defaultState();
  before.perception.heightfield = true;
  const result = applyTaskPluginResult(before, { plugin_id: "x" });
  assert.equal(result.ok, false);
  assert.equal(result.state.perception.heightfield, true, "被拒时状态必须原样不动（半份状态更坏）");
  assert.ok(result.problems.join(" ").includes("场景载荷"), result.problems.join(" | "));
}

// 17) 一键填入：勾选框装不下的 checks/recorders 必须被列出来（不许静默丢）
{
  const response = {
    plugin_id: "custom-task",
    scenario: { command_source: "policy", perception: null, checks: ["arrival", "custom_metric"],
                recorders: ["metrics", "rosbag"] },
    readiness: { verified: false },
    obs_items: {},
  };
  const result = applyTaskPluginResult(defaultState(), response);
  assert.deepEqual(result.state.checks, ["arrival", "custom_metric"], "服务端声明的项要原样进场景");
  assert.deepEqual(result.summary.unmappedChecks, ["custom_metric"]);
  assert.deepEqual(result.summary.unmappedRecorders, ["rosbag"]);
}

console.log("scenario_editor.test.mjs: 17 组断言全部通过 ✔");
