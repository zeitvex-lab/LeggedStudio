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
      // H12 卡死/恢复/终止（服务端 FollowParams 同字段）
      stuck_timeout_s: 4.0, stuck_progress_m: 0.08,
      recovery_duration_s: 2.0, max_recoveries: 4,
      waypoint_timeout_s: 30.0, max_total_time_s: 420.0,
      recovery_cmd: { vx_factor: -0.1, wz_factor: 0.45 },
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
const runner = createNavigationRunner(payload(), { maxCmd: [8, 1.5, 2.5], controlDt: 0.05 });
const straight = runner.command(pose(0, 0, 0));
assert.ok(straight[0] > 0, "目标在前方 ⇒ vx > 0");
assert.ok(straight[0] <= 1.2 + 1e-9, "vx 受注册表 max_vx 约束");
assert.equal(runner.status().sources.follow_controller, "registry/motion_commands.json#follow_controller");
assert.ok(Math.abs(straight[2]) < 1e-9, "已对准 ⇒ wz ≈ 0");
assert.equal(NAVIGATION_VERSION, runner.status().version, "状态带版本号");

// --- 侧向目标：转向方向 ---
// 机器人**朝向左偏**（yaw=+0.9，路径沿 +x）⇒ 需右转回正 ⇒ wz < 0
const overLeft = createNavigationRunner(payload(), { maxCmd: [8, 1.5, 2.5], controlDt: 0.05 }).command(pose(0, 0, 0.9));
assert.ok(overLeft[2] < 0, "机器人朝左偏 ⇒ 右转（wz < 0）");
// 机器人朝向正前方、目标在左侧（路径沿 +y）⇒ 需左转 ⇒ wz > 0
const lateral = createNavigationRunner(
  payload({
    waypoints: [{ x: 0, y: 0, tolerance_m: 0.35 }, { x: 0, y: 2, tolerance_m: 0.35 }],
    plan: { combined_path: [[0, 0], [0, 1], [0, 2]] },
  }),
  { maxCmd: [8, 1.5, 2.5], controlDt: 0.05 },
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
  { maxCmd: [8, 1.5, 2.5], controlDt: 0.05 },
).command(pose(0, 0, 0));
assert.ok(partial[0] > 0, "误差在对齐门限内 ⇒ vx > 0");
assert.ok(partial[0] < 1.2, "vx 被对齐系数衰减（小于纯距离增益）");

// --- 指令上限取更严的一方 ---
const limited = createNavigationRunner(
  payload({ command_limits: { vx: 0.4, vy: 0.4, wz: 0.3 } }),
  { maxCmd: [8, 1.5, 2.5], controlDt: 0.05 },
);
const limitedCmd = limited.command(pose(0, 0, 0));
assert.ok(limitedCmd[0] <= 0.4 + 1e-9, `场景限速应生效（得到 ${limitedCmd[0]}）`);
assert.deepEqual(limited.status().limits, [0.4, 0.4, 0.3], "生效上限写进状态，便于 UI 显示");

const browserTighter = createNavigationRunner(payload(), { maxCmd: [0.2, 1.5, 2.5] });
assert.ok(browserTighter.command(pose(0, 0, 0))[0] <= 0.2 + 1e-9, "浏览器上限更严时以浏览器为准");

// --- 到达：容差 + 稳定拍数 ---
const route = createNavigationRunner(payload(), { maxCmd: [8, 1.5, 2.5], controlDt: 0.05 });
assert.equal(route.status().route_completion, 0, "起点不算完成率");
for (let i = 0; i < 2; i += 1) route.tick(pose(2, 0, 0)); // 不足稳定拍数
assert.equal(route.status().waypoint_index, 1, "帧数不足不推进航点");
route.tick(pose(2, 0, 0));
assert.equal(route.status().waypoint_index, 2, "连续稳定拍数够 ⇒ 推进到下一航点");
assert.ok(route.status().route_completion > 0, "完成率随推进上升");

// 离开容差区 ⇒ 稳定计数清零（不允许"擦边累积"）
const jitter = createNavigationRunner(payload(), { maxCmd: [8, 1.5, 2.5], controlDt: 0.05 });
jitter.tick(pose(2, 0, 0));
jitter.tick(pose(5, 0, 0));
assert.equal(jitter.status().stable_count, 0, "离开容差区应清零稳定计数");
jitter.tick(pose(2, 0, 0));
jitter.tick(pose(2, 0, 0));
jitter.tick(pose(2, 0, 0));
assert.equal(jitter.status().waypoint_index, 2, "重新累积到稳定拍数后仍能推进");

// 逐航点容差：第三个航点的场景容差 0.2（比注册表 0.35 严）
const strict = createNavigationRunner(payload(), { maxCmd: [8, 1.5, 2.5], controlDt: 0.05 });
for (let i = 0; i < 3; i += 1) strict.tick(pose(2, 0, 0));
assert.equal(strict.status().tolerance_m, 0.2, "到达第三个航点时用场景声明的更严容差");

// --- 完成：走完全程后停住 ---
const done = createNavigationRunner(payload(), { maxCmd: [8, 1.5, 2.5], controlDt: 0.05 });
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

// ===========================================================================
// --- H12 卡死恢复状态机（对齐 backend/follow_controller.py 的浏览器侧接入）---
// 参数 = registry/motion_commands.json#follow_controller（stuck_timeout_s 4s /
// stuck_progress_m 0.08 / recovery_duration_s 2s / max_recoveries 4 /
// recovery vx -0.1, wz ±0.45）；时间口径 controlDt=0.05s/拍。
// ===========================================================================

function stuckPayload(overrides = {}) {
  // 短航点 + 空路径折线外的直线：位姿序列由测试直接构造（不动的位姿 ⇒ 卡死）
  return payload(overrides);
}

// --- 卡死检测：位置连续无进展超过 stuck_timeout_s ⇒ 触发恢复段 ---
const stuckRun = createNavigationRunner(stuckPayload(), { maxCmd: [8, 1.5, 2.5], controlDt: 0.05 });
// 79 拍 = 3.95s < stuck_timeout_s 4s：不应触发恢复（服务端同款严格大于比较）
for (let i = 0; i < 79; i += 1) stuckRun.tick(pose(0.5, 0.3, 0));
assert.equal(stuckRun.status().state, "following", "无进展 3.95s（< 4s）⇒ 仍是 following");
assert.equal(stuckRun.status().recoveries_used, 0, "未触发恢复");
// 时间线：首拍计 0.05s ⇒ 第 80 拍 t=4.0s（严格 > 4 不成立）、第 82 拍 t=4.1s ⇒ 触发
stuckRun.tick(pose(0.5, 0.3, 0));
stuckRun.tick(pose(0.5, 0.3, 0));
assert.equal(stuckRun.status().state, "following", "t=4.0s 边界：严格大于不触发（对齐服务端 230 行）");
stuckRun.tick(pose(0.5, 0.3, 0));
assert.equal(stuckRun.status().state, "recovery", "无进展超过 4s ⇒ 进入 recovery");
assert.equal(stuckRun.status().recoveries_used, 1, "恢复计数 1");
assert.equal(stuckRun.status().stuck, true, "status.stuck 如实标记恢复中");

// --- 恢复动作照服务端语义：vx=-0.1（后退）、wz=±0.45（符号每轮翻转） ---
// 第一轮：recovery_sign 初始 1，进入恢复前 ×-1 ⇒ -1 ⇒ wz = 0.45×(-1) = -0.45
const recCmd1 = stuckRun.command(pose(0.5, 0.3, 0));
assert.equal(recCmd1[0], -0.1, "恢复段 vx = recovery_cmd.vx_factor = -0.1（后退脱困）");
assert.equal(recCmd1[1], 0, "恢复段 vy = 0");
assert.ok(Math.abs(recCmd1[2] + 0.45) < 1e-9, `第一轮 wz = 0.45×(-1)（实测 ${recCmd1[2]}）`);
// 恢复段持续 recovery_duration_s=2s（40 拍）：因 0.05 浮点累加，恢复窗口边界
// （recovery_until = 6.0999…9343 > 累计 6.0999…8632）在第 42 拍才关闭——严格比较，
// 与服务端以秒计时的形状一致（服务端浮点误差在 0.02s dt 下同样存在）。
for (let i = 0; i < 40; i += 1) stuckRun.tick(pose(0.5, 0.3, 0));
assert.equal(stuckRun.status().state, "recovery", "恢复段 2s 内保持 recovery");
stuckRun.tick(pose(0.5, 0.3, 0));
stuckRun.tick(pose(0.5, 0.3, 0));
assert.equal(stuckRun.status().state, "following", "恢复段结束 ⇒ 回到 following");
// 恢复期 last_progress 被重置（触发时刻起重新计时）⇒ 需再等 stuck_timeout_s 才再判卡死。
// 0.05s 浮点累加让毫秒级边界对拍数敏感，故用有界轮询等状态迁移（语义断言，不数拍子）。
const waitRecovery = (runner, maxTicks = 100) => {
  for (let i = 0; i < maxTicks; i += 1) {
    if (runner.status().state === "recovery") return true;
    runner.tick(pose(0.5, 0.3, 0));
  }
  return runner.status().state === "recovery";
};
assert.ok(waitRecovery(stuckRun), "恢复期后重新计时 ⇒ 再次卡死进入第二轮恢复");
assert.equal(stuckRun.status().recoveries_used, 2, "再次卡死 ⇒ 第二轮恢复");
// 第二轮符号翻转：wz = 0.45×(+1)
const recCmd2 = stuckRun.command(pose(0.5, 0.3, 0));
assert.ok(Math.abs(recCmd2[2] - 0.45) < 1e-9, `第二轮 wz 翻转为 +0.45（实测 ${recCmd2[2]}）`);

// --- 恢复用尽 ⇒ 终止原因 stuck（服务端 231–233 行同语义）---
const exhausted = createNavigationRunner(stuckPayload(), { maxCmd: [8, 1.5, 2.5], controlDt: 0.05 });
// 每轮按**状态迁移**烧掉恰好一次恢复：无进展 tick 到进入 recovery，再 tick 到退出。
// （固定拍数会因恢复窗口/卡死窗口在时间线上重叠而多烧——按状态断言语义才稳。）
const burnStuck = (runner, maxTicks = 400) => {
  let ticks = 0;
  while (runner.status().state !== "recovery" && ticks < maxTicks) { runner.tick(pose(0.5, 0.3, 0)); ticks += 1; }
  assert.equal(runner.status().state, "recovery", "烧轮：应进入 recovery");
  while (runner.status().state === "recovery" && ticks < maxTicks) { runner.tick(pose(0.5, 0.3, 0)); ticks += 1; }
  assert.equal(runner.status().state, "following", "烧轮：恢复段应结束回 following");
};
burnStuck(exhausted);
burnStuck(exhausted);
burnStuck(exhausted);
assert.equal(exhausted.status().recoveries_used, 3, "已用 3 轮恢复");
assert.equal(exhausted.status().finished, false, "max_recoveries=4 ⇒ 尚未终止");
// 第 4 次卡死触发时 recovery_count 已达 max ⇒ 直接 stuck 终止（不会再进 recovery）
for (let i = 0; i < 200 && !exhausted.status().finished; i += 1) exhausted.tick(pose(0.5, 0.3, 0));
assert.equal(exhausted.status().finished, true, "恢复用尽 ⇒ finished");
assert.equal(exhausted.status().termination_reason, "stuck", "终止原因 = stuck（策略结论）");
assert.equal(exhausted.status().recoveries_used, 4, "第 4 轮计入已用恢复数");
assert.deepEqual(exhausted.command(pose(0.5, 0.3, 0)), [0, 0, 0], "终止后不再驱动");

// --- 位置有进展 ⇒ 不误判卡死 ---
const moving = createNavigationRunner(stuckPayload(), { maxCmd: [8, 1.5, 2.5], controlDt: 0.05 });
// 每拍挪 0.01m ⇒ 每拍都有进展（0.01 > 相对登记 0.08 需要累计，但 best_distance 持续刷新）
// 用慢速进展：每 20 拍挪 0.05m（< stuck_progress_m 的单步，但 best_distance 一直被刷新）
let mx = 0.5;
for (let i = 0; i < 400; i += 1) {
  if (i % 20 === 0) mx += 0.05;
  moving.tick(pose(mx, 0.3, 0));
}
assert.equal(moving.status().recoveries_used, 0, "持续有进展 ⇒ 零恢复");
assert.equal(moving.status().state, "following", "有进展 ⇒ 始终 following");
assert.equal(moving.status().termination_reason, null, "未终止 ⇒ reason 为 null");

// --- 有进展但幅度小于 stuck_progress_m ⇒ 不算进展（服务端 220 行判据形状）---
// 判据是**相对 best 的累计改进 ≥ 0.08m**，不是单拍位移：累计蠕行 0.045m（> 4s）
// 仍判卡死——这正是防"慢速蠕行蹭进展"的形状。
const crawling = createNavigationRunner(stuckPayload(), { maxCmd: [8, 1.5, 2.5], controlDt: 0.05 });
let cx = 0.5;
let sawRecovery = false;
for (let i = 0; i < 120; i += 1) {
  cx += 0.0005; // 120 拍累计 0.06m < stuck_progress_m 0.08 ⇒ 不构成进展
  crawling.tick(pose(cx, 0.3, 0));
  if (crawling.status().state === "recovery") { sawRecovery = true; break; }
}
assert.ok(sawRecovery, "累计改进 < stuck_progress_m ⇒ 判卡死（防蠕行）");
assert.equal(crawling.status().recoveries_used, 1, "蠕行 ⇒ 触发 1 轮恢复");

// --- 单航点超时 ⇒ 终止原因 timeout（服务端 215–217 行同语义）---
// --- 单航点超时 ⇒ 终止原因 timeout（服务端 215–217 行同语义）---
// 静止在容差外（距航点 1.53m ≫ 0.35 容差），卡死窗口调大到 50s 隔离 ⇒ 只有超时能拉停。
const timeoutRunner = createNavigationRunner(
  stuckPayload({
    follow_controller: {
      ...stuckPayload().follow_controller,
      waypoint_timeout_s: 10.0,
      stuck_timeout_s: 50.0, // 隔离卡死路径
    },
  }),
  { maxCmd: [8, 1.5, 2.5], controlDt: 0.05 },
);
for (let i = 0; i < 210; i += 1) {
  timeoutRunner.tick(pose(0.5, 0.3, 0)); // 永不进容差 ⇒ waypoint_timeout 先到
  if (timeoutRunner.status().finished) break;
}
assert.equal(timeoutRunner.status().finished, true, "超过 waypoint_timeout_s ⇒ finished");
assert.equal(timeoutRunner.status().termination_reason, "timeout", "终止原因 = timeout（策略结论）");
assert.notEqual(timeoutRunner.status().termination_reason, "stuck", "timeout 与 stuck 分层，不混淆");

// --- 总时长预算 ⇒ 终止原因 truncated（服务端 188–191 行同语义；非策略结论）---
const budgeted = createNavigationRunner(
  stuckPayload({
    follow_controller: {
      ...stuckPayload().follow_controller,
      max_total_time_s: 20.0, // 400 拍
      stuck_timeout_s: 50.0, // 隔离卡死路径
      waypoint_timeout_s: 100.0, // 隔离超时路径
    },
  }),
  { maxCmd: [8, 1.5, 2.5], controlDt: 0.05 },
);
for (let i = 0; i < 410; i += 1) {
  if (budgeted.status().finished) break;
  budgeted.tick(pose(0.5 + i * 0.02, 0.3, 0)); // 一直有进展，只有预算能拉停
}
assert.equal(budgeted.status().finished, true, "超过 max_total_time_s ⇒ finished");
assert.equal(budgeted.status().termination_reason, "truncated", "终止原因 = truncated（预算拉停）");
assert.notEqual(budgeted.status().termination_reason, "timeout", "truncated ≠ timeout（LightNav 分层）");

// --- 到达判据触发 ⇒ 终止原因 complete（胜利路径接进状态机）---
const completed = createNavigationRunner(payload(), { maxCmd: [8, 1.5, 2.5], controlDt: 0.05 });
for (let i = 0; i < 3; i += 1) completed.tick(pose(2, 0, 0));
for (let i = 0; i < 3; i += 1) completed.tick(pose(4, 0, 0));
assert.equal(completed.status().finished, true, "走完全程 ⇒ finished");
assert.equal(completed.status().termination_reason, "complete", "终止原因 = complete");
assert.equal(completed.status().route_completion, 1, "完成率 100%");

// --- 卡死恢复后真能走完 ⇒ complete（恢复不是死刑，脱困后继续跟随）---
const rescued = createNavigationRunner(stuckPayload(), { maxCmd: [8, 1.5, 2.5], controlDt: 0.05 });
// 卡死 4s ⇒ 恢复段 2s（期间给"被推动"的位姿），然后正常走到目标
for (let i = 0; i < 82; i += 1) rescued.tick(pose(0.5, 0.3, 0));
assert.equal(rescued.status().state, "recovery", "先卡死进入恢复");
for (let i = 0; i < 42; i += 1) rescued.tick(pose(0.5 - 0.02 * i, 0.3, 0)); // 后退脱困
assert.equal(rescued.status().state, "following", "恢复段结束回 following");
for (let i = 0; i < 3; i += 1) rescued.tick(pose(2, 0, 0)); // 正常到达
for (let i = 0; i < 3; i += 1) rescued.tick(pose(4, 0, 0));
assert.equal(rescued.status().termination_reason, "complete", "卡死→恢复→脱困→走完全程 ⇒ complete");

// --- settling 零指令：容差内发令 [0,0,0]（服务端 197–211 行：到达判定分支先于恢复/跟随律）---
// 容差内若还按跟随律加前提航，机器人会冲过航点形成过冲振荡 ⇒ 距离无 0.08m 净改善
// ⇒ 卡死判据按共享语义触发。零指令停驻让 stable_ticks 攒得上、振荡收敛。
const settle = createNavigationRunner(payload(), { maxCmd: [8, 1.5, 2.5], controlDt: 0.05 });
assert.deepEqual(settle.command(pose(2, 0, 0)), [0, 0, 0], "容差内 ⇒ 零指令（settling，服务端 211 行同语义）");
assert.equal(settle.status().finished, false, "settling 未攒够稳定拍 ⇒ 不结束");
for (let i = 0; i < 3; i += 1) settle.tick(pose(2, 0, 0));
assert.equal(settle.status().waypoint_index, 2, "settling 零指令不阻碍稳定拍累积与推进");

// --- 分支顺序：容差内 + 恢复窗口开 ⇒ 仍零指令（服务端到达判定 197 行先于恢复段 223 行）---
const order = createNavigationRunner(stuckPayload(), { maxCmd: [8, 1.5, 2.5], controlDt: 0.05 });
for (let i = 0; i < 82; i += 1) order.tick(pose(0.5, 0.3, 0)); // 无进展 ⇒ 进入恢复
assert.equal(order.status().state, "recovery", "先卡死进入恢复");
order.tick(pose(2, 0, 0)); // 恢复窗口内被推进容差区
assert.equal(order.status().state, "settling", "容差内：到达判定先于恢复段（settling）");
assert.deepEqual(order.command(pose(2, 0, 0)), [0, 0, 0], "恢复窗口内但容差内 ⇒ 零指令（服务端分支顺序）");
for (let i = 0; i < 2; i += 1) order.tick(pose(2, 0, 0));
assert.equal(order.status().waypoint_index, 2, "稳定拍攒够 ⇒ 推进到下一航点");
// 服务端 advance（204–206 行）不清 recovery_until ⇒ 残余窗口在新航点容差外仍发恢复指令
assert.deepEqual(
  order.command(pose(2, 0, 0)),
  [stuckPayload().follow_controller.recovery_cmd.vx_factor, 0, -stuckPayload().follow_controller.recovery_cmd.wz_factor],
  "advance 后残余恢复窗口照发恢复指令（服务端同语义；sign 首轮翻转 ⇒ wz 取负）",
);

// --- reset 清空状态机（恢复计数/终止原因归零）---
exhausted.reset();
assert.equal(exhausted.status().finished, false, "reset 后可重跑");
assert.equal(exhausted.status().termination_reason, null, "reset 后终止原因清空");
assert.equal(exhausted.status().recoveries_used, 0, "reset 后恢复计数归零");

// --- H12 参数缺字段 ⇒ fail-closed（同 requiredNumber 惯例，不许自造默认值）---
const cases = [
  ["stuck_timeout_s", { stuck_timeout_s: undefined }],
  ["stuck_progress_m", { stuck_progress_m: undefined }],
  ["recovery_duration_s", { recovery_duration_s: undefined }],
  ["max_recoveries", { max_recoveries: undefined }],
  ["waypoint_timeout_s", { waypoint_timeout_s: undefined }],
  ["max_total_time_s", { max_total_time_s: undefined }],
];
for (const [key, patch] of cases) {
  assert.throws(
    () => createNavigationRunner(stuckPayload({ follow_controller: { ...stuckPayload().follow_controller, ...patch } })),
    new RegExp(key),
    `follow_controller.${key} 缺失 ⇒ 抛错`,
  );
}
assert.throws(
  () => createNavigationRunner(stuckPayload({
    follow_controller: { ...stuckPayload().follow_controller, recovery_cmd: null },
  })),
  /recovery_cmd/, "缺 recovery_cmd 子块 ⇒ 抛错",
);
assert.throws(
  () => createNavigationRunner(stuckPayload({
    follow_controller: { ...stuckPayload().follow_controller, recovery_cmd: { vx_factor: -0.1 } },
  })),
  /wz_factor/, "recovery_cmd 缺 wz_factor ⇒ 抛错",
);
// 缺 controlDt：构造不抛（发令不需要时间），第一次 tick 才抛（fail-closed 边界最窄）
assert.throws(
  () => createNavigationRunner(stuckPayload(), { maxCmd: [8, 1.5, 2.5], controlDt: undefined }).tick(pose(0, 0, 0)),
  /controlDt/, "缺 controlDt ⇒ 第一次 tick 抛错（时间不许自造）",
);

console.log("navigation.test.mjs OK");
