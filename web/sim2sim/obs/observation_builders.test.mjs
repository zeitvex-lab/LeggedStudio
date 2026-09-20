import { createObservationSystems } from './observation_builders.js';
import { quatToRpy } from '../utils.js';

function makeCtx(overrides = {}) {
  const numObs = overrides.numObs ?? 45;
  const numActions = overrides.numActions ?? 12;
  const CONFIG = {
    observationKind: overrides.kind ?? 'go2_rl_sdk_45',
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
console.log(`\nFINAL PASS=${passed} FAIL=${failed}`);
