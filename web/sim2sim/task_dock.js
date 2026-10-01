// 任务坞：**任务档（registry/tasks）的可运行选装**——选任务 → 应用到仿真 → 出判据。
//
// 与传感器坞同一模式（悬浮坞 + 下拉 + 诚实回显）；与 task_plugins 的关系是
// **两层组合**：插件=感知/命令声明（instantiate 补场景字段），任务档=可运行装配
// （地图/航点/控制器/判据）。这里消费的是任务档；插件声明由任务档的 plugin_id
// 引用，在 /api/scenario/validate 侧生效，本坞不重复实例化。
//
// 纯函数可 Node 断言（sensor_dock 同风格）；DOM 层只负责填充与展示。

/**
 * 任务档下拉选项（纯函数）：**只列基础仿真端口可跑的**——
 * availability 含 headless/cli 的档位都能构造场景 postMessage 应用；
 * 浏览器专属（follow）与越障（判据走 traversal 工具）不进这个坞。
 */
export function taskOptions(indexPayload, profilesPayload) {
  const declared = new Map(
    ((indexPayload && Array.isArray(indexPayload.profiles)) ? indexPayload.profiles : [])
      .map((p) => [p.task_id, p]),
  );
  const profiles = (profilesPayload && Array.isArray(profilesPayload.profiles)) ? profilesPayload.profiles : [];
  return profiles
    .filter((p) => p && p.task_id && declared.has(p.task_id))
    .filter((p) => {
      const av = Array.isArray(p.availability) ? p.availability : [];
      return av.includes("headless") || av.includes("cli");
    })
    .map((p) => ({
      id: p.task_id,
      label: p.display_name || p.task_id,
      cls: p.class || "",
      pluginId: p.plugin_id || null,
      criteria: p.criteria || {},
      assembly: p.assembly || {},
    }));
}

/**
 * 任务档 → 场景载荷（可 postMessage 的形状；sim2sim 接收侧要求
 * scenario_id + waypoints 数组）。由 assembly 派生：
 *   * goal/patrol → 地图默认航点（planner 自主导航）；
 *   * traversal → 空航点（terrain_profile=obstacle_release 地形即障碍）。
 */
export function taskToScenario(task, defaultWaypoints) {
  // registry/tasks 的 profile 用 task_id/class（无 id/cls）——兼容两种键。
  const taskId = task.id || task.task_id;
  const cls = task.class || task.cls || "";
  const mode = task.assembly.waypoints_mode;
  let waypoints = [];
  if (mode === "default_full") waypoints = defaultWaypoints;
  else if (mode === "goal") waypoints = defaultWaypoints.slice(0, 1).concat(defaultWaypoints.slice(-1));
  const scenario = {
    schema_version: "scenario-contract-1.1",
    scenario_id: taskId,
    map_id: task.assembly.map_id || "flat",
    mode: cls === "navigation" ? "navigation" : "basic",
    command_source: task.assembly.command_source || "policy",
    waypoints,
  };
  if (task.assembly.terrain_profile) {
    scenario.terrain = { kind: task.assembly.terrain_profile };
  }
  return scenario;
}

/** 场景消息封装（sim2sim postMessage 协议；version 与 scenario_run.js 的
 *  SCENARIO_MESSAGE_VERSION 同步——接收端对不一致版本拒收）。 */
export function scenarioMessage(scenario) {
  return {
    type: "legged-studio:scenario",
    version: 1,
    scenario,
  };
}

/** readiness 一行摘要（沿用诚实纪律：声明可实例化 ≠ 能跑）。 */
export function readinessLine(readiness) {
  const r = readiness || {};
  const parts = [`ok=${!!r.ok}`, `verified=${!!r.verified}`];
  const blockers = Array.isArray(r.blockers) ? r.blockers : [];
  for (const b of blockers) parts.push(`阻断: ${typeof b === "string" ? b : JSON.stringify(b)}`);
  return parts.join(" ｜ ");
}

/** 选中项变化后的 UI 状态。 */
export function selectionState(pluginId, readiness, error) {
  if (error) return { showNote: true, text: `实例化失败: ${error.message}` };
  if (!pluginId) return { showNote: false, text: "" };
  return { showNote: true, text: readinessLine(readiness) };
}
