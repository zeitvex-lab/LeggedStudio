import { createObservationSystems } from './observation_builders.js';

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
    model: { njnt: numActions, geom_bodyid: null, jnt_qposadr: null, jnt_bodyid: null },
    data: { time: 0, ncon: 0, contact: null },
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
test('unknown -> locomotion', makeCtx({ kind:'unknown_xyz', numObs:45, numActions:12 }));
test('g1_mjlab_velocity_98', makeCtx({ kind:'g1_mjlab_velocity_98', numObs:98, numActions:29 }));
test('g1_mjswan_balance', makeCtx({ kind:'g1_mjswan_balance', numObs:93, numActions:29 }));
test('g1_mjswan_locomotion', makeCtx({ kind:'g1_mjswan_locomotion', numObs:99, numActions:29 }));
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
// s07_amp_cts
test('s07_amp_cts', makeCtx({ kind:'s07_amp_cts', numObs:45, numActions:12 }));
console.log(`\nFINAL PASS=${passed} FAIL=${failed}`);
