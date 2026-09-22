import { createObservationSystems } from './observation_builders.js';
import { quatToRpy } from '../utils.js';

function makeCtx(overrides = {}) {
  const numObs = overrides.numObs ?? 45;
  const numActions = overrides.numActions ?? 12;
  const CONFIG = {
    observationKind: overrides.kind ?? 'go2_rl_sdk_45',
    // 声明式布局规格（`observation_layout`）：非空即优先于 kind builder（与验收器同一条路）。
    observationLayout: overrides.layout ?? null,
    numObs, numActions,
    simulationDt: 0.002, controlDecimation: 10,
    angVelScale: 0.25, dofPosScale: 1.0, dofVelScale: 0.05,
    cmdScale: new Float32Array([2,2,0.25]), heightCommandScale: 2.0,
    defaultAngles: new Float32Array(numActions).fill(0.1),
    controlModes: new Array(numActions).fill('position'),
    dofReindex: null, gaitPeriodS: 0.7,
    gaitYawCommandRadius: 1.0, gaitCommandGated: false,
    gaitLocomotionGate: [0, 1], clipObs: null,
    actuatorRoles: new Array(numActions).fill('joint'),
    jointOrder: Array.from({length: numActions}, (_,i)=>`joint${i}`),
    defaultCommand: new Array(6).fill(0),
    observationMask: null, motionJointMapping: null,
    waistJointIndices: [2,5,8], commandDims: 3,
    defaultJointAnglesByName: {},
    actionJointOrder: Array.from({length: numActions}, (_,i)=>`joint${i}`),
  };
  const sim = {
    obs: new Float32Array(numObs),
    action: new Float32Array(numActions),
    cmd: new Float32Array([0,0,0]),
    qpos: new Float32Array(7+numActions).fill(0.1),
    qvel: new Float32Array(6+numActions),
    model: {
      njnt: numActions, geom_bodyid: null, jnt_bodyid: null,
      jnt_qposadr: Array.from({length:numActions},(_,i)=>7+i),
      jnt_range: new Float32Array(2*numActions).fill(0.5),
    },
    data: {
      time: 0, ncon: 0, contact: null,
      xpos: new Float32Array(3*32),
      xquat: (() => { const q = new Float32Array(4*32); for (let b=0;b<32;b+=1) q[4*b]=1; return q; })(),
    },
    gaitElapsedS: 0, gaitActive: false, g1PhaseS: 0,
    history: new Float32Array(200), jumpStartedAt: 0, jumpActive: false,
    mujoco: { mj_name2id: () => -1, mjtObj: {} },
    platformConfig: null, motionLoader: null, g2wIdx: null, g2wMjIdx: null,
    jointQposAdr: null, jointDofAdr: null,
  };
  const input = {
    imuAxisSigns: { angular: [1,1,1], gravity: [1,1,1] },
    imuDelayEnabled: false, imuDelayMaxSteps: 0, imuDelaySampleSteps: 0,
    gaitEnabled: false,
  };
  const elements = { gaitControl: null, gaitToggle: null, gaitToggleState: null };
  const ctx = {
    CONFIG, sim, input, elements,
    readImuSample: () => ({ angular: [0,0,0], gravity: [0,0,-1], rpy: [0,0,0], linear: [0,0,0] }),
    jointQpos: (i) => CONFIG.defaultAngles[i],
    jointQvel: (i) => 0,
    clamp: (v,min,max)=>Math.max(min,Math.min(max,v)),
    finiteNumber: (v,f)=> (Number.isFinite(v)?v:f),
    jointGroup: () => 'leg',
    enumValue: (v)=>v,
    isJumpCommandActive: () => false,
    heightCommandIndex: () => 3,
    bucketHeightCommand: () => 0,
    observationLayout: () => ({ heightCommand: false, jointOffset: 6, velocityOffset: 6+numActions, actionOffset: 6+2*numActions }),
    publishDebugState: () => {},
    WHEEL_LEG_GAIT_OBSERVATION: 'wheel_leg_gait_moe_cts',
    WHEEL_LEG_GAIT_PERIOD_S: 0.7,
    WHEEL_LEG_JUMP_OBSERVATION: 'wheel_leg_jump_moe_cts',
    WHEEL_LEG_JUMP_PERIOD_S: 0.7,
    ...overrides.ctx,
  };
  return ctx;
}

let passed = 0, failed = 0;
function test(name, ctx) {
  try {
    const obs = createObservationSystems(ctx);
    obs.buildObservation();
    passed++;
    console.log('OK', name);
  } catch (e) {
    failed++;
    console.log('FAIL', name, '--', e.message);
  }
}
/** 断言"**应当拒绝**"的用例：声明了具体 kind 却没有 builder 时必须抛错，不许静默回落。 */
function testRefuses(name, ctx) {
  try {
    const obs = createObservationSystems(ctx);
    obs.buildObservation();
    failed++;
    console.log('FAIL', name, '-- 应当拒绝（抛错），却静默跑过了');
  } catch (e) {
    passed++;
    console.log('OK', name, '--', e.message.slice(0, 40));
  }
}
function makeMotionLoader(n, { torso=false }={}) {
  const loader = {
    duration: 10,
    jointPos: ()=>new Array(n).fill(0),
    jointVel: ()=>new Array(n).fill(0),
    rootQuaternion: ()=>[1,0,0,0],
    update: ()=>{},
  };
  if (torso) {
    loader.torsoQuatW = (q,w)=>q;
    loader.anchorQuatW = ()=>[1,0,0,0];
    loader.motionAnchorOriB = (a,b)=>new Float32Array(6);
  } else {
    loader.motionAnchorOriB = (a,b)=>new Float32Array(6);
  }
  return loader;
}

test('microduck_61', makeCtx({ kind:'microduck_61', numObs:61, numActions:14 }));
test('zexw_53', makeCtx({ kind:'zexw_53', numObs:53, numActions:16 }));
test('go2_rl_sdk_45', makeCtx({ kind:'go2_rl_sdk_45', numObs:45, numActions:12 }));
// LainLab 技能族（2026-09-20 入库）：帧构成/拼接顺序的取证记录见 00_know/05 §P1③。
test('lainlab_dream_45_hist6', makeCtx({ kind:'lainlab_dream_45_hist6', numObs:45, numActions:12 }));
test('lainlab_gait_47_hist10', makeCtx({ kind:'lainlab_gait_47_hist10', numObs:47, numActions:12 }));
test('lainlab_spring_47_hist10', makeCtx({ kind:'lainlab_spring_47_hist10', numObs:47, numActions:12 }));
test('lainlab_handstand_48', makeCtx({ kind:'lainlab_handstand_48', numObs:48, numActions:12 }));
// **契约变更（2026-09-20）**：本行原为 `test('unknown -> locomotion', ...)` —— 断言"未知 kind
// 回落到通用布局"。那个回落正是"跑得起来但吃错观测"的成因（57 维轮足观测被按 45 维四足布局填），
// 故反转为**必须拒绝**；"未声明 kind（空值）仍回落"作为既定默认单独保留一条正向用例。
testRefuses('未知 kind 拒绝静默回落', makeCtx({ kind:'unknown_xyz', numObs:45, numActions:12 }));
test('未声明 kind 仍回落通用布局', makeCtx({ kind:'', numObs:45, numActions:12 }));
// app.js 对契约未声明 observation_kind 的策略写入哨兵 "default"（1786 行），
// 必须与空串同走通用布局——go2-baseline-164k 实测在此抛错（2026-09-20）。
test('"default" 哨兵回落通用布局', makeCtx({ kind:'default', numObs:45, numActions:12 }));
test('g1_mjlab_velocity_98', makeCtx({ kind:'g1_mjlab_velocity_98', numObs:98, numActions:29 }));
test('g1_mjswan_balance', makeCtx({ kind:'g1_mjswan_balance', numObs:93, numActions:29 }));
test('g1_mjswan_locomotion', makeCtx({ kind:'g1_mjswan_locomotion', numObs:99, numActions:29 }));
test('go1_playground_48', makeCtx({ kind:'go1_playground_48', numObs:48, numActions:12 }));
test('himloco_45_hist6', makeCtx({ kind:'himloco_45_hist6', numObs:45, numActions:12 }));
test('g1_amp_96', makeCtx({ kind:'g1_amp_96', numObs:96, numActions:29 }));
{
  const c = makeCtx({ kind:'g1_motion_154', numObs:154, numActions:29 });
  c.CONFIG.motionJointMapping = Array.from({length:29},(_,i)=>i);
  c.sim.motionLoader = makeMotionLoader(29, {torso:true});
  test('g1_motion_154 (mock loader)', c);
}
{
  const c = makeCtx({ kind:'go2_motion_69', numObs:69, numActions:12 });
  c.CONFIG.motionJointMapping = Array.from({length:12},(_,i)=>i);
  c.sim.motionLoader = makeMotionLoader(12);
  test('go2_motion_69 (mock loader)', c);
}
{
  const c = makeCtx({ kind:'wheel_leg_gait_moe_cts', numObs:60, numActions:16 });
  test('wheel_leg_gait_moe_cts', c);
}
{
  const c = makeCtx({ kind:'wheel_leg_jump_moe_cts', numObs:76, numActions:16 });
  test('wheel_leg_jump_moe_cts', c);
}
{
  const c = makeCtx({ kind:'quadrupedal_agility_ll', numObs:96, numActions:12 });
  test('quadrupedal_agility_ll', c);
}
{
  const c = makeCtx({ kind:'tron1_pf_30', numObs:30, numActions:6 });
  c.CONFIG.tron1Swap = [0, 3, 1, 4, 2, 5];
  test('tron1_pf_30', c);
}
{
  const c = makeCtx({ kind:'tron1_sf_36', numObs:36, numActions:8 });
  c.CONFIG.tron1Swap = [0, 4, 1, 5, 2, 6, 3, 7];
  test('tron1_sf_36', c);
}
{
  const c = makeCtx({ kind:'tron1_wf_28', numObs:28, numActions:8 });
  c.CONFIG.tron1Swap = [0, 4, 1, 5, 2, 6, 3, 7];
  c.CONFIG.tron1JointPosIdx = [0, 1, 2, 4, 5, 6];
  c.CONFIG.tron1SwapPos = [0, 3, 1, 4, 2, 5];
  test('tron1_wf_28', c);
}
{
  const c = makeCtx({ kind:'wheel_leg_gait_moe_cts', numObs:60, numActions:16 });
  const obs = createObservationSystems(c);
  obs.updateGaitControl();
  obs.setWheelLegGaitEnabled(true);
  obs.wheelLegGaitRequested();
  obs.wheelLegGaitCommandSpeed();
  obs.advanceWheelLegGaitClock();
  obs.resetMotionTime();
  passed++;
  console.log('OK gait control helpers');
}
console.log(`\nPASS=${passed} FAIL=${failed}`);

// go2w_53 (uses g2wIdx caching)
{
  const c = makeCtx({ kind:'go2w_53', numObs:53, numActions:16 });
  c.sim.mujoco = { mj_name2id: () => -1, mjtObj: {} };
  c.sim.platformConfig = { robot: { joint_order: Array.from({length:16},(_,i)=>`j${i}`) } };
  c.CONFIG.defaultJointAnglesByName = {};
  c.CONFIG.actionJointOrder = Array.from({length:16},(_,i)=>`j${i}`);
  test('go2w_53', c);
}
// go2w_mjlab_legs_53
{
  const c = makeCtx({ kind:'go2w_mjlab_legs_53', numObs:53, numActions:12 });
  c.sim.mujoco = { mj_name2id: () => -1, mjtObj: {} };
  c.sim.platformConfig = { robot: { joint_order: Array.from({length:12},(_,i)=>`j${i}`) } };
  c.CONFIG.observationMask = null;
  test('go2w_mjlab_legs_53', c);
}
// go2w_rl_sdk_57
test('go2w_rl_sdk_57', makeCtx({ kind:'go2w_rl_sdk_57', numObs:57, numActions:16 }));
// go2w_himloco_57（LeggedSkillDeploy go2w_himloco：commands 在前的 57 维）
test('go2w_himloco_57', makeCtx({ kind:'go2w_himloco_57', numObs:57, numActions:16 }));
// wuji_reorient_69（Wuji Hand 掌内立方体重定向：69 维 + history 3）
test('wuji_reorient_69', makeCtx({ kind:'wuji_reorient_69', numObs:69, numActions:20 }));
// s07_amp_cts
test('s07_amp_cts', makeCtx({ kind:'s07_amp_cts', numObs:45, numActions:12 }));
// 参考时钟到达 duration 后【默认钳制保持末帧】（上游 rl_sdk
// `motion_time = min(rl_time, duration)`）。回绕会让 backflip 在落地阶段被重置
// 回起始蹲跳段，机器人背部着地。
{
  const c = makeCtx({ kind:'go2_motion_69', numObs:69, numActions:12 });
  c.CONFIG.motionJointMapping = Array.from({length:12},(_,i)=>i);
  const seen = [];
  const loader = makeMotionLoader(12);
  loader.update = (t) => { seen.push(t); };
  c.sim.motionLoader = loader;
  const obs = createObservationSystems(c);
  obs.resetMotionTime();
  for (let i = 0; i < 620; i += 1) obs.buildObservation(); // 620 * 0.02s = 12.4s > duration 10s
  const maxSeen = Math.max(...seen);
  const wrapped = seen.some((t, i) => i > 0 && t < seen[i - 1]);
  if (Math.abs(maxSeen - loader.duration) > 1e-9 || wrapped) {
    failed++;
    console.log('FAIL go2_motion_69 clamps clock at duration --', maxSeen, 'wrapped=', wrapped);
  } else {
    passed++;
    console.log('OK go2_motion_69 clamps clock at duration');
  }
}
// 契约声明 motion_params.loop=true 时改为循环重放（go2-jump-69 用）：时钟回绕到
// [0, duration) 并持续循环，且绝不越过 duration。
{
  const c = makeCtx({ kind:'go2_motion_69', numObs:69, numActions:12 });
  c.CONFIG.motionJointMapping = Array.from({length:12},(_,i)=>i);
  c.CONFIG.motionLoop = true;
  const seen = [];
  const loader = makeMotionLoader(12);
  loader.update = (t) => { seen.push(t); };
  c.sim.motionLoader = loader;
  const obs = createObservationSystems(c);
  obs.resetMotionTime();
  for (let i = 0; i < 620; i += 1) obs.buildObservation();
  const wrapped = seen.some((t, i) => i > 0 && t < seen[i - 1]);
  const inRange = seen.every((t) => t >= 0 && t <= loader.duration);
  if (!wrapped || !inRange) {
    failed++;
    console.log('FAIL go2_motion_69 loops clock when motionLoop=true -- wrapped=', wrapped, 'inRange=', inRange);
  } else {
    passed++;
    console.log('OK go2_motion_69 loops clock when motionLoop=true');
  }
}
// ── euler_xyz 的 (w,x,y,z) 布局回归（2026-09-20 浏览器实测事故）──
// captureImuSample 的 quaternion = sim.qpos.subarray(3,7)，MuJoCo 自由关节位姿段是
// (w,x,y,z)。utils.js 的 quatToRpy 曾按 three.js 的 (x,y,z,w) 解包 ⇒ roll↔yaw 互换、
// pitch 变号：lainlab_gait_47_hist10 / lainlab_spring_47_hist10 观测的 euler 段
// （第 8..10 维，3/47）每帧都在喂错值。同一 checkpoint 在 mjlab 训练环境里 vx=0.5
// 稳定跟踪（vx≈0.47），浏览器里 2.7s 倒地。下面两组四元数取自那次浏览器取证。
function eulerXyzReference([w, x, y, z]) {
  // 与 mjlab/Isaac 的 euler_xyz_from_quat 同一公式，此处独立复算（避免同源错）。
  const roll = Math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y));
  const sinp = 2 * (w * y - z * x);
  const pitch = Math.asin(Math.max(-1, Math.min(1, sinp)));
  const yaw = Math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z));
  return [roll, pitch, yaw];
}
function eulerXyzMisread([w0, x0, y0, z0]) {
  // 旧约定：把同一个缓冲当成 (x, y, z, w)。
  return eulerXyzReference([z0, w0, x0, y0]);
}
{
  const quats = [
    [1, 0, 0, 0],
    [0.963937, -0.008327, 0.197449, 0.178242],
    [0.7071068, 0.0, 0.7071068, 0.0],
    // 注意：不能放 [0.5,0.5,0.5,0.5] 这类四元数——循环移位后数值集合不变，
    // 两种约定算出同一组 Euler，失去"能区分误读"的判别力。
  ];
  let worst = 0;
  let discriminated = true;
  for (const q of quats) {
    const got = quatToRpy(q);
    const want = eulerXyzReference(q);
    const wrong = eulerXyzMisread(q);
    worst = Math.max(worst, ...want.map((v, i) => Math.abs(v - got[i])));
    if (Math.max(...wrong.map((v, i) => Math.abs(v - got[i]))) < 1e-3) discriminated = false;
  }
  if (worst > 1e-6 || !discriminated) {
    failed++;
    console.log('FAIL quatToRpy MuJoCo (w,x,y,z) 布局 -- 最大差', worst, '可区分误读', discriminated);
  } else {
    passed++;
    console.log('OK quatToRpy MuJoCo (w,x,y,z) 布局');
  }
}
{
  // 端到端：gait 观测第 8..10 维必须等于该姿态的 euler_xyz（mjlab root_euler）。
  const quat = [0.963937, -0.008327, 0.197449, 0.178242];
  const c = makeCtx({ kind: 'lainlab_gait_47_hist10', numObs: 47, numActions: 12 });
  c.readImuSample = () => ({
    angular: [0, 0, 0], gravity: [0, 0, -1], rpy: quatToRpy(quat), linear: [0, 0, 0],
  });
  const obs = createObservationSystems(c);
  obs.buildObservation();
  const want = eulerXyzReference(quat);
  const got = [c.sim.obs[8], c.sim.obs[9], c.sim.obs[10]];
  const gap = Math.max(...want.map((v, i) => Math.abs(v - got[i])));
  const fromMisread = Math.max(...eulerXyzMisread(quat).map((v, i) => Math.abs(v - got[i])));
  if (gap > 1e-6 || fromMisread < 1e-3) {
    failed++;
    console.log('FAIL gait 观测 euler 段 -- 与参考差', gap, '与误读差', fromMisread, '实际', got);
  } else {
    passed++;
    console.log('OK gait 观测 euler 段（第 8..10 维）= euler_xyz(w,x,y,z)');
  }
}
{
  // ── mjswan 四输入链的 `actor` 117（2026-09-22）：**逐 term 新→旧 + last_action element-major
  // 交错 + 首帧填满每一槽**。这是"两份实现逐值同口径"的钉子：Python 侧
  // `adapters/mjlab/policy_acceptance.py::_MjswanActorHistory` 必须给出同一张表 ——
  // 这类错序不抛异常、只在策略行为上显现，靠人眼看图永远抓不到。
  let g = [1, 2, 3];
  let qBase = 100;
  let dqBase = 200;
  const c = makeCtx({
    kind: 'go2_mjswan_velocity', numObs: 117, numActions: 12,
    ctx: {
      // 这三个（连同 IMU）在 `createObservationSystems` 时就被闭包捕获 ⇒ 只能靠**可变闭包**换值；
      // 事后 `c.jointQpos = ...` 赋值不会生效（第一版就是这么错的：q_rel 段恒 0）。
      readImuSample: () => ({ angular: [0, 0, 0], gravity: g, rpy: [0, 0, 0], linear: [0, 0, 0] }),
      jointQpos: (i) => qBase + i,
      jointQvel: (i) => dqBase + i,
    },
  });
  const obs = createObservationSystems(c);
  const DEF = 0.1; // 脚手架 defaultAngles 全 0.1
  c.sim.action.set(Array.from({ length: 12 }, (_, i) => 300 + i));
  obs.buildObservation();
  // 段序：gravity(3) | joint_pos_rel(12) | joint_vel(12) | last_action(12)，**每段 3 帧新→旧**
  const want = [];
  const frame = (gravity, qBase, dqBase, aBase) => {
    const out = [...gravity];
    for (let i = 0; i < 12; i += 1) out.push(qBase + i - DEF);
    for (let i = 0; i < 12; i += 1) out.push(dqBase + i);
    for (let i = 0; i < 12; i += 1) out.push(aBase + i);
    return out;
  };
  const newest = frame([1, 2, 3], 100, 200, 300);
  // gravity 段：3 帧整段铺
  for (let rep = 0; rep < 3; rep += 1) for (let i = 0; i < 3; i += 1) want.push(newest[i]);
  // joint_pos / joint_vel：同样整段铺
  for (const base of [3, 15]) {
    for (let rep = 0; rep < 3; rep += 1) for (let i = 0; i < 12; i += 1) want.push(newest[base + i]);
  }
  // last_action：**element-major**（每个关节自己的 3 帧相邻）
  for (let j = 0; j < 12; j += 1) for (let rep = 0; rep < 3; rep += 1) want.push(newest[27 + j]);
  const gap0 = Math.max(...want.map((v, i) => Math.abs(v - c.sim.obs[i])));
  // 容差 1e-5：`sim.obs` 是 Float32（`99.9` 存进去是 99.9000015…），与对拍工具同一口径
  if (c.sim.obs.length !== 117 || gap0 > 1e-5) {
    failed++;
    console.log('FAIL mjswan actor 117 首帧布局 -- 最大差', gap0, '前 12 位', Array.from(c.sim.obs.slice(0, 12)));
  } else {
    passed++;
    console.log('OK mjswan actor 117：首帧填满每一槽 + last_action element-major 交错');
  }

  // 第二步：新帧入槽 0、旧帧后移（**新→旧**）——换成一组可区分的值再验一次
  g = [7, 8, 9];
  qBase = 400;
  dqBase = 500;
  c.sim.action.set(Array.from({ length: 12 }, (_, i) => 600 + i));
  obs.buildObservation();
  const step2 = Array.from(c.sim.obs);
  const near = (a, b) => Math.abs(a - b) < 1e-5;
  const q3 = step2.slice(9, 45);
  const la = step2.slice(81, 117);
  const gravityOk = near(step2[0], 7) && near(step2[3], 1) && near(step2[6], 1); // 新, 旧, 最旧
  // q_rel = jointQpos(i) − 0.1 ⇒ 新帧 399.9+i、上一帧 99.9+i（首帧被 prime 成了第一步的值）
  const qOk = near(q3[0], 399.9) && near(q3[11], 410.9) && near(q3[12], 99.9) && near(q3[23], 110.9);
  const laOk = near(la[0], 600) && near(la[1], 300) && near(la[2], 300) && near(la[3], 601) && near(la[4], 301);
  if (!gravityOk || !qOk || !laOk) {
    failed++;
    console.log('FAIL mjswan actor 117：第二帧未按 新→旧 入槽（gravity', step2.slice(0, 9), '| q_rel', q3.slice(0, 3), '| la', la.slice(0, 6), '）');
  } else {
    passed++;
    console.log('OK mjswan actor 117：新帧入槽 0、旧帧后移（逐位核对 gravity / 关节 / 动作三段）');
  }
}
// ── 声明式布局解释器（`CONFIG.observationLayout`）的**语义筛选**（2026-09-22 v0.58.0）─────
// 为什么单独测：这两个选项（`mode` / `zero_velocity_joints`）是为了让"轮位清零""按控制模式
// 分列"从"腿恰好排在前 12"的**位置巧合**升级成**语义**（契约一换序，位置写法就静默错位）。
// 两侧（JS `applyLayoutSpec` / Python `frame_from_spec`）规则逐字相同，故判据必须落到**值**上。
/** 断言"跑得通 + 逐维值对"（解释器必须看值，不能只看"没抛错"）。 */
function testSpecValues(name, ctx, check) {
  try {
    const obs = createObservationSystems(ctx);
    obs.buildObservation();
    check(ctx);
    passed++;
    console.log('OK', name);
  } catch (e) {
    failed++;
    console.log('FAIL', name, '--', e.message);
  }
}

// 16 动作：前 12 腿（position）、后 4 轮（velocity）；关节角 = i+1、dq = 10·(i+1)。
// 注意：测试用的 ctx 默认把 `jointQpos/jointQvel` 打成了常量假体（`defaultAngles[i]` / 0），
// 所以这里必须**从 ctx 覆盖**这两个访问器——否则本组用例全是 0，看着"通过"其实什么都没测。
function makeWheelLegLayoutCtx(layout, numObs) {
  const numActions = 16;
  const ctx = makeCtx({
    kind: 'go2w_rl_sdk_57', numObs, numActions, layout,
    ctx: { jointQpos: (i) => (i + 1), jointQvel: (i) => 10 * (i + 1) },
  });
  ctx.CONFIG.controlModes = [...new Array(12).fill('position'), ...new Array(4).fill('velocity')];
  return ctx;
}

testSpecValues('布局·zero_velocity_joints：轮位清零、腿位保留', 
  makeWheelLegLayoutCtx([{ source: 'joint_pos', scale: '@contract', zero_velocity_joints: true }], 16),
  (ctx) => {
    const o = ctx.sim.obs;
    const near = (a, b) => Math.abs(a - b) < 1e-5;
    // q_rel = (i+1) − 0.1，dofPosScale = 1.0
    if (!near(o[0], 0.9) || !near(o[11], 11.9)) throw new Error(`腿位不对：${o[0]}, ${o[11]}`);
    if (!near(o[12], 0) || !near(o[15], 0)) throw new Error(`轮位没清零：${o[12]}, ${o[15]}`);
  });

testSpecValues('布局·mode=velocity：只取速度控制关节（按语义，不按位置）',
  makeWheelLegLayoutCtx([{ source: 'joint_vel', mode: 'velocity', width: 4, scale: '@contract' }], 4),
  (ctx) => {
    const o = ctx.sim.obs;
    const near = (a, b) => Math.abs(a - b) < 1e-5;
    // dofVelScale = 0.05；选中的是 12..15 号关节 ⇒ 10·(12+1)·0.05 = 6.5 起
    if (!near(o[0], 6.5) || !near(o[3], 8.0)) throw new Error(`取的关节不对：${o.slice(0, 4)}`);
  });

testSpecValues('布局·mode=position：取非速度控制关节',
  makeWheelLegLayoutCtx([{ source: 'joint_vel', mode: 'position', width: 12, scale: '@contract' }], 12),
  (ctx) => {
    const o = ctx.sim.obs;
    const near = (a, b) => Math.abs(a - b) < 1e-5;
    if (!near(o[0], 0.5) || !near(o[11], 6.0)) throw new Error(`取的关节不对：${o.slice(0, 3)}`);
  });

testRefuses('布局·mode 不给 width ⇒ 拒绝（宽度不许猜）',
  makeWheelLegLayoutCtx([{ source: 'joint_vel', mode: 'velocity' }], 4));
testRefuses('布局·width 与 mode 选中的关节数不符 ⇒ 拒绝',
  makeWheelLegLayoutCtx([{ source: 'joint_vel', mode: 'velocity', width: 5 }], 5));
testRefuses('布局·mode="torque" 未实现 ⇒ 拒绝（不许静默当 position）',
  makeWheelLegLayoutCtx([{ source: 'joint_vel', mode: 'torque', width: 16 }], 16));
testRefuses('布局·段宽之和 ≠ numObs ⇒ 拒绝',
  makeWheelLegLayoutCtx([{ source: 'gravity' }], 45));

console.log(`\nFINAL PASS=${passed} FAIL=${failed}`);
