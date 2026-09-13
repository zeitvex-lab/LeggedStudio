// 导航跟随器单测（node web/sim2sim/navigation.test.mjs，已进 npm run test:all）。
//
// 守的是什么：
//   1. **阈值不许在客户端自造**：缺 arrival 判据直接抛错（H10 单一真值）；
//   2. **指令上限取更严的一方**：场景 command_limits 比浏览器 maxCmd 小时以场景为准；
//   3. **到达判定按容差 + 稳定拍数**推进航线，完成率随之前进；
//   4. **航向控制方向正确**：目标在左 ⇒ yaw 速率为正；朝目标时前进速度为正。

import assert from "node:assert/strict";
import {
  NAVIGATION_VERSION,
  applyTerrainSwitch,
  createNavigationRunner,
  poseFromQpos,
  wrapAngle,
  yawFromQuat,
} from "./navigation.js";

function payload(overrides = {}) {
  return {
    command_source: "planner",
    map_id: "warehouse",
    waypoints: [
      { x: 0, y: 0, tolerance_m: 0.35, tolerance_source: "registry/arrival_criteria.json" },
      { x: 2, y: 0, tolerance_m: 0.35, tolerance_source: "registry/arrival_criteria.json" },
      { x: 4, y: 0, tolerance_m: 0.2, tolerance_source: "scenario" },
    ],
    plan: { combined_path: [[0, 0], [1, 0], [2, 0], [3, 0], [4, 0]] },
    arrival: { tolerance_m: 0.35, stable_ticks: 3, source: "registry/arrival_criteria.json" },
    // 镜像 registry/motion_commands.json#follow_controller（Python 侧有测试与注册表对拍）
    follow_controller: {
      lookahead_m: 0.45, max_vx: 1.2, max_wz: 0.8,
      kp_dist: 0.8, kp_yaw: 1.8,
      yaw_stop_threshold_deg: 45, turn_in_place_enter_deg: 70,
      turn_in_place_exit_deg: 18, turn_in_place_max_wz: 0.8,
    },
    ...overrides,
  };
}

function pose(x, y, yaw = 0) {
  return { x, y, yaw };
}

// --- 切换施加（感知闭环最后一米）---
const switched = applyTerrainSwitch([1.0, 0.5, 0.8], { kind: "limits", new_limits: { vx: 0.5, vy: 0.25, wz: 0.4 } });
assert.deepEqual(switched.cmd, [0.5, 0.25, 0.4], "限速决定应逐轴裁剪");
assert.equal(switched.applied, true);
const stopped = applyTerrainSwitch([1.0, 0.0, 0.5], { kind: "stop", note: "不可通行" });
assert.deepEqual(stopped.cmd, [0, 0, 0], "停机决定 ⇒ 指令全零");
assert.equal(stopped.stopped, true);
const unknown = applyTerrainSwitch([1.0, 0.0, 0.5], { kind: "teleport" });
assert.deepEqual(unknown.cmd, [1.0, 0.0, 0.5], "未知切换类型不得施加");
assert.equal(unknown.applied, false);
assert.match(unknown.reason, /未知切换类型/);
const none = applyTerrainSwitch([0.3, 0, 0], null);
assert.equal(none.applied, false, "没有决定就不动指令");
assert.deepEqual(none.cmd, [0.3, 0, 0]);

// --- 纯函数 ---
assert.equal(yawFromQuat([1, 0, 0, 0], 0), 0, "单位四元数 ⇒ yaw 0");
assert.ok(Math.abs(yawFromQuat([Math.cos(Math.PI / 4), 0, 0, Math.sin(Math.PI / 4)], 0) - Math.PI / 2) < 1e-9, "绕 z 90° ⇒ yaw π/2");
assert.equal(wrapAngle(3 * Math.PI), Math.PI, "wrapAngle 归一化到 (-π, π]");
const qpos = new Float32Array([1, 2, 0.5, 1, 0, 0, 0]);
const fromQpos = poseFromQpos(qpos);
assert.deepEqual([fromQpos.x, fromQpos.y, fromQpos.yaw], [1, 2, 0], "poseFromQpos 读自由关节布局");

// --- 判据缺失必须抛错（不许自造阈值）---
assert.throws(() => createNavigationRunner({ ...payload(), arrival: null }), /arrival/, "缺 arrival ⇒ 抛错");
assert.throws(() => createNavigationRunner({ ...payload(), follow_controller: null }), /follow_controller/, "缺跟随参数 ⇒ 抛错");
assert.throws(
  () => createNavigationRunner({ ...payload(), follow_controller: { ...payload().follow_controller, kp_yaw: undefined } }),
  /kp_yaw/, "跟随参数缺字段 ⇒ 抛错（不许用代码默认值兜底）",
);
assert.throws(() => createNavigationRunner({ ...payload(), plan: { combined_path: [[0, 0]] } }), /路径|航点/, "路径不足 ⇒ 抛错");

// --- 朝向目标：直行 ---
const runner = createNavigationRunner(payload(), { maxCmd: [8, 1.5, 2.5] });
const straight = runner.command(pose(0, 0, 0));
assert.ok(straight[0] > 0, "目标在前方 ⇒ vx > 0");
assert.ok(straight[0] <= 1.2 + 1e-9, "vx 受注册表 max_vx 约束");
assert.equal(runner.status().sources.follow_controller, "registry/motion_commands.json#follow_controller");
assert.ok(Math.abs(straight[2]) < 1e-9, "已对准 ⇒ wz ≈ 0");
assert.equal(NAVIGATION_VERSION, runner.status().version, "状态带版本号");

// --- 侧向目标：转向方向 ---
// 机器人**朝向左偏**（yaw=+0.9，路径沿 +x）⇒ 需右转回正 ⇒ wz < 0
const overLeft = createNavigationRunner(payload(), { maxCmd: [8, 1.5, 2.5] }).command(pose(0, 0, 0.9));
assert.ok(overLeft[2] < 0, "机器人朝左偏 ⇒ 右转（wz < 0）");
// 机器人朝向正前方、目标在左侧（路径沿 +y）⇒ 需左转 ⇒ wz > 0
const lateral = createNavigationRunner(
  payload({
    waypoints: [{ x: 0, y: 0, tolerance_m: 0.35 }, { x: 0, y: 2, tolerance_m: 0.35 }],
    plan: { combined_path: [[0, 0], [0, 1], [0, 2]] },
  }),
  { maxCmd: [8, 1.5, 2.5] },
).command(pose(0, 0, 0));
assert.ok(lateral[2] > 0, "目标在左侧 ⇒ 左转（wz > 0）");
// 误差（π/2≈1.57）超过对齐门限（默认 0.9）⇒ **先原地转**，不往前冲
assert.equal(lateral[0], 0, "正交误差 ⇒ vx=0（先转再走）");
// 误差在对齐门限内（45°≈0.785 < 0.9）⇒ 给前进速度，并按对齐系数衰减
const partial = createNavigationRunner(
  payload({
    waypoints: [{ x: 0, y: 0, tolerance_m: 0.35 }, { x: 2, y: 2, tolerance_m: 0.35 }],
    plan: { combined_path: [[0, 0], [1, 1], [2, 2]] },
  }),
  { maxCmd: [8, 1.5, 2.5] },
).command(pose(0, 0, 0));
assert.ok(partial[0] > 0, "误差在对齐门限内 ⇒ vx > 0");
assert.ok(partial[0] < 1.2, "vx 被对齐系数衰减（小于纯距离增益）");

// --- 指令上限取更严的一方 ---
const limited = createNavigationRunner(
  payload({ command_limits: { vx: 0.4, vy: 0.4, wz: 0.3 } }),
  { maxCmd: [8, 1.5, 2.5] },
);
const limitedCmd = limited.command(pose(0, 0, 0));
assert.ok(limitedCmd[0] <= 0.4 + 1e-9, `场景限速应生效（得到 ${limitedCmd[0]}）`);
assert.deepEqual(limited.status().limits, [0.4, 0.4, 0.3], "生效上限写进状态，便于 UI 显示");

const browserTighter = createNavigationRunner(payload(), { maxCmd: [0.2, 1.5, 2.5] });
assert.ok(browserTighter.command(pose(0, 0, 0))[0] <= 0.2 + 1e-9, "浏览器上限更严时以浏览器为准");

// --- 到达：容差 + 稳定拍数 ---
const route = createNavigationRunner(payload(), { maxCmd: [8, 1.5, 2.5] });
assert.equal(route.status().route_completion, 0, "起点不算完成率");
for (let i = 0; i < 2; i += 1) route.tick(pose(2, 0, 0)); // 不足稳定拍数
assert.equal(route.status().waypoint_index, 1, "帧数不足不推进航点");
route.tick(pose(2, 0, 0));
assert.equal(route.status().waypoint_index, 2, "连续稳定拍数够 ⇒ 推进到下一航点");
assert.ok(route.status().route_completion > 0, "完成率随推进上升");

// 离开容差区 ⇒ 稳定计数清零（不允许"擦边累积"）
const jitter = createNavigationRunner(payload(), { maxCmd: [8, 1.5, 2.5] });
jitter.tick(pose(2, 0, 0));
jitter.tick(pose(5, 0, 0));
assert.equal(jitter.status().stable_count, 0, "离开容差区应清零稳定计数");
jitter.tick(pose(2, 0, 0));
jitter.tick(pose(2, 0, 0));
jitter.tick(pose(2, 0, 0));
assert.equal(jitter.status().waypoint_index, 2, "重新累积到稳定拍数后仍能推进");

// 逐航点容差：第三个航点的场景容差 0.2（比注册表 0.35 严）
const strict = createNavigationRunner(payload(), { maxCmd: [8, 1.5, 2.5] });
for (let i = 0; i < 3; i += 1) strict.tick(pose(2, 0, 0));
assert.equal(strict.status().tolerance_m, 0.2, "到达第三个航点时用场景声明的更严容差");

// --- 完成：走完全程后停住 ---
const done = createNavigationRunner(payload(), { maxCmd: [8, 1.5, 2.5] });
for (let i = 0; i < 3; i += 1) done.tick(pose(2, 0, 0));
for (let i = 0; i < 3; i += 1) done.tick(pose(4, 0, 0));
const finalStatus = done.status();
assert.equal(finalStatus.finished, true, "走完全程 ⇒ finished");
assert.equal(finalStatus.route_completion, 1, "完成率 100%");
assert.deepEqual(done.command(pose(4, 0, 0)), [0, 0, 0], "完成后不再驱动");

// --- reset 回到初始态 ---
done.reset();
assert.equal(done.status().finished, false, "reset 后可重跑");
assert.equal(done.status().route_completion, 0, "reset 后完成率归零");

console.log("navigation.test.mjs OK");
