// obs_crosscheck.mjs —— "同状态 obs 对拍"的**浏览器侧**执行体（由 tools/obs_crosscheck.py 调用）。
//
// 它不做任何判断：把 Python 侧造好的状态原样喂给**浏览器真的那份观测构建器**
// （`web/sim2sim/obs/observation_builders.js`），把算出来的观测打成 JSON 交回去。
// 判据（逐段 max|Δ|）在 Python 侧算——两边各自只做自己那份真值，工具不引入第三份实现。
//
// 关键点：`readImuSample` 必须走 `utils.js::imuSampleFromQpos`（浏览器**运行时真路径**），
// 不能在这里另写一份——否则工具就成了"测一个仿真品"，2026-09-22 那次双重旋转正是
// 靠"驱动真函数"才当场复现的。
//
// 用法：node tools/obs_crosscheck.mjs <state.json>
import { readFileSync } from "node:fs";
import { createObservationSystems } from "../web/sim2sim/obs/observation_builders.js";
import { imuSampleFromQpos } from "../web/sim2sim/utils.js";

const statePath = process.argv[2];
if (!statePath) {
  console.log(JSON.stringify({ ok: false, error: "用法: node tools/obs_crosscheck.mjs <state.json>" }));
  process.exit(2);
}
const D = JSON.parse(readFileSync(statePath, "utf8"));
const numObs = Number(D.contract.obs_dim);
const numActions = Number(D.contract.action_dim);
const joints = D.state.joints;

const sim = {
  obs: new Float32Array(numObs),
  action: new Float32Array(D.action || joints.map(() => 0)),
  cmd: new Float32Array(D.cmd),
  // 自由关节布局：qpos = [pos(3), quat(4), joints...]，qvel = [lin(3), ang(3), dofs...]
  qpos: new Float32Array([0, 0, 0, ...D.state.quat_wxyz, ...joints.map((j) => j.q)]),
  qvel: new Float32Array([...D.state.qvel_head, ...joints.map((j) => j.dq)]),
  model: {
    njnt: numActions, geom_bodyid: null, jnt_bodyid: null,
    jnt_qposadr: joints.map((_, i) => 7 + i),
    jnt_range: new Float32Array(2 * numActions).fill(0.5),
  },
  data: {
    time: 0, ncon: 0, contact: null,
    xpos: new Float32Array(3 * 32),
    xquat: (() => { const q = new Float32Array(4 * 32); for (let b = 0; b < 32; b += 1) q[4 * b] = 1; return q; })(),
  },
  gaitElapsedS: 0, gaitActive: false, g1PhaseS: 0,
  history: new Float32Array(1024), jumpStartedAt: 0, jumpActive: false,
  mujoco: { mj_name2id: () => -1, mjtObj: {} },
  platformConfig: null, motionLoader: null, g2wIdx: null, g2wMjIdx: null,
  jointQposAdr: null, jointDofAdr: null,
};

const input = {
  imuAxisSigns: {
    angular: D.imu_axis_signs?.angular || [1, 1, 1],
    gravity: D.imu_axis_signs?.gravity || [1, 1, 1],
  },
  imuDelayEnabled: false, imuDelayMaxSteps: 0, imuDelaySampleSteps: 0,
  gaitEnabled: false,
};

const CONFIG = {
  observationKind: D.contract.observation_kind,
  numObs, numActions,
  simulationDt: D.contract.simulation_dt, controlDecimation: D.contract.decimation,
  angVelScale: D.scales.ang_vel, dofPosScale: D.scales.dof_pos, dofVelScale: D.scales.dof_vel,
  cmdScale: new Float32Array(D.scales.command),
  heightCommandScale: 2.0,
  defaultAngles: new Float32Array(joints.map((j) => j.default)),
  controlModes: new Array(numActions).fill("position"),
  dofReindex: null, gaitPeriodS: D.contract.gait_period_s || 0.7,
  gaitYawCommandRadius: 1.0, gaitCommandGated: false, gaitLocomotionGate: [0, 1],
  clipObs: null,
  actuatorRoles: new Array(numActions).fill("joint"),
  jointOrder: joints.map((j) => j.name),
  defaultCommand: new Array(6).fill(0),
  observationMask: null, motionJointMapping: null,
  waistJointIndices: [2, 5, 8],
  commandDims: D.contract.command_dims,
  defaultJointAnglesByName: {},
  actionJointOrder: joints.map((j) => j.name),
};

const ctx = {
  CONFIG, sim, input,
  elements: { gaitControl: null, gaitToggle: null, gaitToggleState: null },
  readImuSample: () => imuSampleFromQpos(sim.qpos, sim.qvel),
  jointQpos: (i) => sim.qpos[7 + i],
  jointQvel: (i) => sim.qvel[6 + i],
  clamp: (v, lo, hi) => Math.max(lo, Math.min(hi, v)),
  finiteNumber: (v, f) => (Number.isFinite(v) ? v : f),
  jointGroup: () => "leg", enumValue: (v) => v,
  isJumpCommandActive: () => false,
  heightCommandIndex: () => 3, bucketHeightCommand: () => 0,
  observationLayout: () => ({
    heightCommand: false, jointOffset: 6,
    velocityOffset: 6 + numActions, actionOffset: 6 + 2 * numActions,
  }),
  publishDebugState: () => {},
  WHEEL_LEG_GAIT_OBSERVATION: "wheel_leg_gait_moe_cts", WHEEL_LEG_GAIT_PERIOD_S: 0.7,
  WHEEL_LEG_JUMP_OBSERVATION: "wheel_leg_jump_moe_cts", WHEEL_LEG_JUMP_PERIOD_S: 0.7,
};

try {
  const systems = createObservationSystems(ctx);
  // 同状态重复建帧 = 顺带把 history 打包顺序也一起比了（两侧都是 N 份相同帧）
  const rounds = Math.max(1, Number(D.contract.history_len) || 1);
  for (let i = 0; i < rounds; i += 1) systems.buildObservation();
  const imu = ctx.readImuSample();
  console.log(JSON.stringify({
    ok: true,
    obs: Array.from(sim.obs),
    imu: {
      angular: Array.from(imu.angular), linear: Array.from(imu.linear),
      gravity: Array.from(imu.gravity), rpy: Array.from(imu.rpy),
    },
  }));
} catch (error) {
  console.log(JSON.stringify({ ok: false, error: `${error?.name || "Error"}: ${error?.message || error}` }));
  process.exit(2);
}
