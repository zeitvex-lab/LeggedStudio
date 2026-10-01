import test from "node:test";
import assert from "node:assert/strict";

import { taskOptions, taskToScenario, scenarioMessage, readinessLine, selectionState } from "./task_dock.js";

const INDEX = { profiles: [{ task_id: "goal_nav_warehouse" }, { task_id: "follow_line" }] };
// 注意：availability 在 profiles.json（两表交集 = 登记且可跑）。
const PROFILES = [
  {
    task_id: "goal_nav_warehouse",
    display_name: "仓库定点导航",
    class: "navigation",
    plugin_id: "odom-waypoint-nav",
    availability: ["headless", "cli", "browser"],
    criteria: { arrival_rate_min: 1.0 },
    assembly: { map_id: "warehouse", command_source: "planner", waypoints_mode: "goal" },
  },
  {
    task_id: "follow_line",
    display_name: "目标跟随",
    class: "follow",
    availability: ["browser"],
    criteria: { hold_ratio_min: 0.8 },
    assembly: { map_id: "flat", command_source: "script", waypoints_mode: "moving_target" },
  },
];

test("taskOptions：只列注册表∩可跑（headless/cli）端口——follow(browser) 被剔除", () => {
  const options = taskOptions(INDEX, PROFILES);
  assert.deepEqual(options.map((o) => o.id), ["goal_nav_warehouse"]);
  assert.equal(options[0].pluginId, "odom-waypoint-nav");
});

test("taskOptions：注册表缺登记的任务档不出现（fail-closed）", () => {
  const options = taskOptions({ profiles: [] }, PROFILES);
  assert.deepEqual(options, []);
});

test("taskToScenario：goal 模式 → 首末航点；planner 命令源；map_id 透传", () => {
  const task = PROFILES[0];
  task.assembly.waypoints_mode = "goal";
  const s = taskToScenario(task, [[0, 0], [1.5, 2.2], [6, 0]]);
  assert.equal(s.scenario_id, "goal_nav_warehouse");
  assert.equal(s.command_source, "planner");
  assert.deepEqual(s.waypoints, [[0, 0], [6, 0]]);
});

test("taskToScenario：default_full → 全部航点", () => {
  const task = { ...PROFILES[0], assembly: { ...PROFILES[0].assembly, waypoints_mode: "default_full" } };
  const s = taskToScenario(task, [[0, 0], [1.5, 2.2], [6, 0]]);
  assert.equal(s.waypoints.length, 3);
});

test("scenarioMessage：postMessage 协议封装（type/version/scenario）", () => {
  const s = taskToScenario(PROFILES[0], [[0, 0], [6, 0]]);
  const msg = scenarioMessage(s);
  assert.equal(msg.type, "legged-studio:scenario");
  assert.equal(msg.version, 2);
  assert.equal(msg.scenario.scenario_id, s.scenario_id);
});

test("readinessLine / selectionState：诚实三态", () => {
  assert.equal(readinessLine({ ok: true, verified: false }), "ok=true ｜ verified=false");
  assert.deepEqual(selectionState("x", null, new Error("boom")), { showNote: true, text: "实例化失败: boom" });
  assert.deepEqual(selectionState("", null, null), { showNote: false, text: "" });
});
