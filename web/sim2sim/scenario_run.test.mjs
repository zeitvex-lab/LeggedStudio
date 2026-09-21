// Scenario 运行侧纯逻辑单测（`node web/sim2sim/scenario_run.test.mjs`）。
//
// 钉的是 A1 的四件事：
//   1. **交运消息**：完整场景走 postMessage（不再是 7 个有损 URL 参数），且形状不对就拒收；
//   2. **判据不求默认通过**：没有服务端 arrival 判据时如实报"没有判据"，而不是放行；
//   3. **度量如实**：距离/时长/最大姿态/是否摔倒都是算出来的，没有拍脑袋阈值；
//   4. **记录器按声明产出**：未声明的不造文件。
import assert from "node:assert/strict";
import {
  EXECUTOR_COMMAND_SOURCES,
  SCENARIO_MESSAGE_TYPE,
  SCENARIO_MESSAGE_VERSION,
  buildRunSummary,
  evaluateArrival,
  evaluateChecks,
  parseScenarioMessage,
  recorderArtifacts,
  summarizeRun,
  toScenarioMessage,
  tracePoint,
  unsupportedCommandSourceProblems,
} from "./scenario_run.js";

const SCENARIO = {
  schema_version: "scenario-contract-1.1",
  scenario_id: "adv_probe",
  map_id: "warehouse",
  mode: "navigation",
  seed: 3,
  episode_length_s: 20,
  waypoints: [{ x: 0, y: 0 }, { x: 2, y: 0 }, { x: 4, y: 0 }],
  command_limits: { vx: 0.6, vy: 0.4, wz: 0.8 },
  terrain: { kind: "flat" },
  command_source: "planner",
  checks: ["arrival", "route_completion"],
  recorders: ["trajectory", "metrics"],
};

const ARRIVAL = { source: "registry/arrival_criteria.json", tolerance_m: 0.2, stable_ticks: 3 };

// 1) 交运消息：完整场景（含 checks/recorders/perception/command_source）原样带走
{
  const message = toScenarioMessage(SCENARIO, { robot: "unitree_go2", policy: "go2-loco-45" });
  assert.equal(message.type, SCENARIO_MESSAGE_TYPE);
  assert.equal(message.version, SCENARIO_MESSAGE_VERSION);
  assert.equal(message.robot, "unitree_go2");
  assert.equal(message.policy, "go2-loco-45");
  assert.deepEqual(message.scenario.checks, ["arrival", "route_completion"], "判据必须随消息走");
  assert.deepEqual(message.scenario.recorders, ["trajectory", "metrics"], "记录器必须随消息走");
  assert.equal(message.scenario.command_source, "planner", "指令源必须随消息走");
  assert.equal(message.scenario.episode_length_s, 20, "时长必须随消息走");
  assert.equal(message.scenario.map_id, "warehouse", "地图必须随消息走");
  // 深拷贝：改消息不改原对象（编辑器随后还要用原场景渲染报告）
  message.scenario.checks.push("mutated");
  assert.deepEqual(SCENARIO.checks, ["arrival", "route_completion"], "消息必须是深拷贝");
  // 无场景 ⇒ 无消息（不造空壳）
  assert.equal(toScenarioMessage(null), null);
}

// 2) 接收方 fail-closed：形状不对一律拒收并说清原因
{
  assert.equal(parseScenarioMessage({ data: null }).ok, false);
  assert.equal(parseScenarioMessage({ data: { type: "other" } }).ok, false);
  assert.equal(parseScenarioMessage({ data: { type: SCENARIO_MESSAGE_TYPE, version: 99, scenario: {} } }).ok, false);
  assert.equal(parseScenarioMessage({ data: { type: SCENARIO_MESSAGE_TYPE, version: 1 } }).ok, false, "缺 scenario 要拒");
  assert.equal(
    parseScenarioMessage({ data: { type: SCENARIO_MESSAGE_TYPE, version: 1, scenario: { scenario_id: "x" } } }).ok,
    false,
    "waypoints 不是数组要拒",
  );
  const good = parseScenarioMessage({ data: toScenarioMessage(SCENARIO) });
  assert.equal(good.ok, true, good.reason);
  assert.equal(good.payload.scenario.scenario_id, "adv_probe");
}

// 3) 到达判据：**没有服务端判据就不默认通过**
{
  const trace = [tracePoint({ t: 0, x: 0, y: 0 }), tracePoint({ t: 1, x: 3.9, y: 0 })];
  const verdict = evaluateArrival(SCENARIO, trace, null);
  assert.equal(verdict.ok, false, "缺 arrival 判据时不许放行");
  assert.match(verdict.reason, /没有服务端到达判据/);
  const okVerdict = evaluateArrival(SCENARIO, [
    tracePoint({ t: 0, x: 0, y: 0 }),
    tracePoint({ t: 1, x: 3.95, y: 0 }),
    tracePoint({ t: 2, x: 3.98, y: 0 }),
    tracePoint({ t: 3, x: 4.0, y: 0.01 }),
  ], ARRIVAL);
  assert.equal(okVerdict.ok, true, okVerdict.reason);
  assert.equal(okVerdict.stableTicks, 3);
  // 到了但摔了 ⇒ 不算到达（摔倒时贴脸末点是趴过去的）
  const fallen = evaluateArrival(SCENARIO, [
    tracePoint({ t: 2, x: 4.0, y: 0 }),
    tracePoint({ t: 3, x: 4.0, y: 0, fallen: true }),
    tracePoint({ t: 4, x: 4.0, y: 0, fallen: true }),
    tracePoint({ t: 5, x: 4.0, y: 0, fallen: true }),
  ], ARRIVAL);
  assert.equal(fallen.ok, false, "摔倒了不算到达");
}

// 4) 航线完成度 + 度量如实
{
  // 轨迹从 0 直奔 3.95：0 号与 2 号航点在容差内，中间的 2 号航点没经过 ⇒ 2/3
  const trace = [
    tracePoint({ t: 0, x: 0, y: 0 }),
    tracePoint({ t: 1, x: 3.95, y: 0, rollDeg: 3, pitchDeg: -2, vx: 0.5 }),
  ];
  const completion = evaluateChecks(SCENARIO, trace, ARRIVAL).find((c) => c.name === "route_completion");
  assert.equal(completion.reached, 2, "只有 0 与 2 号航点在容差内");
  assert.equal(completion.ratio, 0.667);
  assert.equal(completion.ok, false);
  const metrics = summarizeRun(SCENARIO, trace);
  assert.equal(metrics.distanceM, 3.95);
  assert.equal(metrics.durationS, 1);
  assert.equal(metrics.maxRollDeg, 3);
  assert.equal(metrics.maxPitchDeg, 2);
  assert.equal(metrics.fell, false);
  assert.equal(metrics.samples, 2);
  assert.ok(Math.abs(metrics.meanSpeed - 0.25) < 1e-3);
  // 空轨迹不抛错
  assert.equal(summarizeRun(SCENARIO, []).samples, 0);
}

// 5) 摘要与记录器：声明了才产出；未声明的一项都不造
{
  // 走完全部航点并在末点稳定 3 拍 ⇒ 两项判据都过
  const trace = [
    tracePoint({ t: 0, x: 0, y: 0 }),
    tracePoint({ t: 1, x: 2.0, y: 0 }),
    tracePoint({ t: 2, x: 3.9, y: 0 }),
    tracePoint({ t: 3, x: 4.0, y: 0 }),
    tracePoint({ t: 4, x: 4.0, y: 0 }),
  ];
  const summary = buildRunSummary(SCENARIO, trace, ARRIVAL);
  assert.equal(summary.scenarioId, "adv_probe");
  assert.equal(summary.passed, true, summary.checks.map((c) => c.detail).join(" | "));
  assert.deepEqual(summary.artifacts, ["trajectory.json", "metrics.json"]);
  const artifacts = recorderArtifacts(SCENARIO, trace, ARRIVAL);
  assert.deepEqual(Object.keys(artifacts).sort(), ["metrics.json", "trajectory.json"]);
  assert.equal(artifacts["trajectory.json"].length, 5);
  assert.equal(artifacts["metrics.json"].metrics.samples, 5);
  const none = recorderArtifacts({ ...SCENARIO, recorders: [] }, trace, ARRIVAL);
  assert.deepEqual(Object.keys(none), [], "未声明记录器时不造任何文件");
  // 未知检查项：声明了但不认识 ⇒ 报 false + 原因（不静默跳过）
  const unknown = evaluateChecks({ ...SCENARIO, checks: ["nope"] }, trace, ARRIVAL);
  assert.equal(unknown[0].ok, false);
  assert.match(unknown[0].detail, /未知检查项/);
  // 中途没走完 ⇒ passed=false（摘要不许粉饰）
  const partial = buildRunSummary(SCENARIO, [tracePoint({ t: 0, x: 0, y: 0 }), tracePoint({ t: 1, x: 1.0, y: 0 })], ARRIVAL);
  assert.equal(partial.passed, false);
}

// 6) 执行器能力镜像与 executors.py 同口径（防两头漂移；Python 侧有跨语言核对测试）
{
  assert.deepEqual(EXECUTOR_COMMAND_SOURCES.browser_wasm, ["policy", "teleop", "planner"]);
  assert.deepEqual(EXECUTOR_COMMAND_SOURCES.server_mujoco, ["planner", "script"]);
  // 浏览器跑不了 script（服务端才行）与 perception（两端都没有）
  assert.deepEqual(unsupportedCommandSourceProblems("script"), ["command_source=script 在执行器 browser_wasm不可用：脚本化指令序列只有服务端执行器能跑"]);
  assert.ok(unsupportedCommandSourceProblems("perception")[0].includes("感知进观测链路"));
  assert.deepEqual(unsupportedCommandSourceProblems("planner"), []);
  // 直接传支持数组（页面从 /api/simulation/executors 拿真值时走这条）
  assert.deepEqual(unsupportedCommandSourceProblems("script", ["planner", "script"]), []);
  assert.deepEqual(unsupportedCommandSourceProblems("policy", ["planner"]).length, 1);
}

console.log("scenario_run.test.mjs: 6 组断言全部通过 ✔");
