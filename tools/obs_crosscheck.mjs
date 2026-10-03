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
// 角色/控制模式解析：**复用浏览器运行时那一份**（app.js 里的 applyActuatorContract 同源）。
// 2026-09-22 前这里把 `controlModes` 写死全 "position"、`jointGroup` 写死恒返回 "leg"，
// 于是 m20/b2w 两条 `go2w_rl_sdk_57` 被**误报**不一致（Δ=5.000e-02 = 轮位该清零却给了
// rel×scale）——真因是尺子少喂了一个输入。
import { resolveActuatorRolesAndModes, jointGroup } from "../web/sim2sim/obs/actuator_modes.js";

const statePath = process.argv[2];
if (!statePath) {
  console.log(JSON.stringify({ ok: false, error: `${error?.name || "Error"}: ${error?.message || error}` }));
  process.exit(2);
}
const D = JSON.parse(readFileSync(statePath, "utf8"));
const numObs = Number(D.contract.obs_dim);
const numActions = Number(D.contract.action_dim);
const joints = D.state.joints;

// ── 模型态（真值由 Python 侧从 MuJoCo 原样搬过来）────────────────────────────
// 读 `sim.model` / `sim.data` 的 builder（wuji-reorient 等）必须拿到**真**关节 id、
// 软限位与 body 位姿，否则算出来是 NaN/错值 —— 而对拍报告只会说"不一致"。
const MJ_OBJ_BODY = 1;     // MuJoCo mjtObj 的**真实取值**（mjOBJ_BODY=1, mjOBJ_JOINT=3）；
const MJ_OBJ_JOINT = 3;    // 用占位数字会让"按对象类型分派"的查找退化成同一张表。
const mjState = D.mujoco || {};
const bodyIds = mjState.body_ids || {};
const jointIds = mjState.joint_ids || {};
const nbody = Math.max(Number(mjState.nbody) || 0,
  Object.keys(bodyIds).length ? Math.max(...Object.values(bodyIds)) + 1 : 0, 32);
const njnt = Math.max(Number(mjState.njnt) || 0,
  Object.keys(jointIds).length ? Math.max(...Object.values(jointIds)) + 1 : 0, numActions);
const jntRange = new Float32Array(2 * njnt);
for (const [i, pair] of (mjState.jnt_range || []).entries()) {
  if (2 * i + 1 < jntRange.length) { jntRange[2 * i] = pair[0]; jntRange[2 * i + 1] = pair[1]; }
}
const xpos = new Float32Array(3 * nbody);
(mjState.xpos || []).forEach((v, i) => { if (i < xpos.length) xpos[i] = v; });
const xquat = new Float32Array(4 * nbody);
for (let b = 0; b < nbody; b += 1) xquat[4 * b] = 1;
(mjState.xquat || []).forEach((v, i) => { if (i < xquat.length) xquat[i] = v; });

// qpos/qvel **原样**来自 Python 侧（同一状态），不再按"pos+quat+关节"假设重建：
// wuji_hand 的唯一自由关节是立方体、手指关节排在 qpos[0..19]，重建出来的 qpos[3:7]
// 不是四元数 ⇒ IMU 段读的是垃圾（对拍会红，但不是实现不一致）。
const qpos = new Float32Array(D.state.qpos || [0, 0, 0, ...D.state.quat_wxyz, ...joints.map((j) => j.q)]);
const qvel = new Float32Array(D.state.qvel || [...D.state.qvel_head, ...joints.map((j) => j.dq)]);

const sim = {
  obs: new Float32Array(numObs),
  action: new Float32Array(D.action || joints.map(() => 0)),
  cmd: new Float32Array(D.cmd),
  qpos,
  qvel,
  model: {
    njnt, geom_bodyid: null, jnt_bodyid: null,
    jnt_qposadr: mjState.jnt_qposadr || joints.map((j, i) => Number(j.qpos_adr ?? 7 + i)),
    jnt_dofadr: mjState.jnt_dofadr || joints.map((j, i) => Number(j.dof_adr ?? 6 + i)),
    jnt_range: jntRange,
  },
  data: {
    time: 0, ncon: 0, contact: null,
    xpos, xquat,
  },
  gaitElapsedS: 0, gaitActive: false, g1PhaseS: 0,
  history: new Float32Array(1024), jumpStartedAt: 0, jumpActive: false,
  // `mj_name2id` 按对象类型分派到 Python 侧搬来的 id 表（未知名 ⇒ -1，与 MuJoCo 同约定）。
  mujoco: {
    mj_name2id: (_model, objType, name) => {
      const key = String(name);
      if (Number(objType) === MJ_OBJ_JOINT) return jointIds[key] ?? -1;
      if (Number(objType) === MJ_OBJ_BODY) return bodyIds[key] ?? -1;
      return -1;
    },
    mjtObj: { mjOBJ_BODY: MJ_OBJ_BODY, mjOBJ_JOINT: MJ_OBJ_JOINT },
  },
  platformConfig: null, motionLoader: null, g2wIdx: null, g2wMjIdx: null,
  jointQposAdr: joints.map((j, i) => Number(j.qpos_adr ?? 7 + i)),
  jointDofAdr: joints.map((j, i) => Number(j.dof_adr ?? 6 + i)),
  // 策略内部状态：**原始**动作目标（qpos_error 的基准；builder 自己归一化）与目标朝向
  // （不喂 ⇒ 浏览器侧随机采样 ⇒ 不可比）
  targetDofPos: new Float32Array(D.policy_state?.target_dof_pos_raw || new Array(numActions).fill(0)),
  wujiGoalQuat: Array.isArray(D.policy_state?.goal_quat) && D.policy_state.goal_quat.length === 4
    ? Array.from(D.policy_state.goal_quat)
    : null,
  wujiHold: 0,
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
  // 声明式布局（与 Python frame_from_spec 同一份规格）：两侧消费同一份，不各写一份实现。
  observationLayout: D.contract.observation_layout || null,
  numObs, numActions,
  simulationDt: D.contract.simulation_dt, controlDecimation: D.contract.decimation,
  angVelScale: D.scales.ang_vel, dofPosScale: D.scales.dof_pos, dofVelScale: D.scales.dof_vel,
  cmdScale: new Float32Array(D.scales.command),
  heightCommandScale: 2.0,
  defaultAngles: new Float32Array(joints.map((j) => j.default)),
  // 角色/控制模式：**按运行时的同一函数解**（输入由 Python 侧给全：策略契约
  // `control_modes` / `actuator_roles` + 机器人 `control.control_modes`）。原先写死
  // 全 "position"，会让"轮位清零"这类分支在对拍里悄悄走错——比缺测更坏，因为它报红。
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

{
  const { roles, modes } = resolveActuatorRolesAndModes({
    actionDim: numActions,
    jointOrder: joints.map((j) => j.name),
    jointGroup,
    contractRoles: D.contract.actuator_roles,
    contractModes: D.contract.control_modes,
    robotModes: D.control_modes?.robot,
  });
  CONFIG.actuatorRoles = roles;
  CONFIG.controlModes = modes;
}

const ctx = {
  CONFIG, sim, input,
  elements: { gaitControl: null, gaitToggle: null, gaitToggleState: null },
  readImuSample: () => imuSampleFromQpos(sim.qpos, sim.qvel),
  // 关节地址**用真的**（`qpos_adr/dof_adr` 来自 Python 侧：与浏览器运行时按名解析出的
  // 地址同一来源）；原先写死 `7+i`/`6+i`，只在"机器人本体是第一个自由关节"时成立。
  jointQpos: (i) => sim.qpos[Number(joints[i]?.qpos_adr ?? 7 + i)],
  jointQvel: (i) => sim.qvel[Number(joints[i]?.dof_adr ?? 6 + i)],
  clamp: (v, lo, hi) => Math.max(lo, Math.min(hi, v)),
  finiteNumber: (v, f) => (Number.isFinite(v) ? v : f),
  // 真 jointGroup（不是 `() => "leg"` 的假体）：构建器里用它判断"这维是不是轮子"，
  // 假体等于把轮足策略的判据全判错 —— 与上面对拍红是同一个错因。
  jointGroup, enumValue: (v) => v,
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
