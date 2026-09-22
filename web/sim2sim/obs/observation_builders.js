// Observation builder registry, extracted from app.js god file.
//
// Each builder composes a policy observation vector into sim.obs from the
// shared sim/CONFIG/input state plus a few robot-agnostic helpers.  Keeping
// them in this module means adding a new policy observation contract only
// requires registering a builder here, never touching app.js.
//
// The factory receives a documented ctx so this module stays unit-testable in
// plain Node (a mocked ctx can drive every builder through a smoke path).
export function createObservationSystems(ctx) {
  const {
    // Shared mutable runtime state.
    CONFIG, sim, input,
    // DOM element cache used by the gait-control UI sync helpers.
    elements,
    // Cross-cutting helpers defined in app.js and reused by the builders.
    readImuSample, jointQpos, jointQvel,
    clamp, finiteNumber, jointGroup, enumValue,
    isJumpCommandActive, heightCommandIndex, bucketHeightCommand,
    observationLayout, publishDebugState,
    // Wheel-leg policy contract constants.
    WHEEL_LEG_GAIT_OBSERVATION, WHEEL_LEG_GAIT_PERIOD_S,
    WHEEL_LEG_JUMP_OBSERVATION, WHEEL_LEG_JUMP_PERIOD_S,
  } = ctx;

  // Motion-clock for imitation policies, scoped to this module (was module-level
  // in app.js).  resetMotionTime() lets app.js reset it on load/reset.
  let motionTime = 0;
function buildMicroDuckObservation() {
  if (CONFIG.numObs !== 61 || CONFIG.numActions !== 14) {
    throw new Error(`microduck_61 requires 61 observations and 14 actions; got ${CONFIG.numObs}/${CONFIG.numActions}`);
  }
  const imu = readImuSample();
  sim.obs.fill(0);
  let offset = 0;
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.angular[i] * input.imuAxisSigns.angular[i];
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.gravity[i] * input.imuAxisSigns.gravity[i];
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = jointQpos(i) - CONFIG.defaultAngles[i];
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = jointQvel(i);
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = sim.action[i];
  for (let i = 0; i < 13; i += 1) sim.obs[offset++] = sim.cmd[i] || 0;
}

function buildZexWObservation() {
  if (CONFIG.numObs !== 53 || CONFIG.numActions !== 16) {
    throw new Error(`zexw_53 requires 53 observations and 16 actions; got ${CONFIG.numObs}/${CONFIG.numActions}`);
  }
  const imu = readImuSample();
  sim.obs.fill(0);
  let offset = 0;
  // Matches rc_mjlab/sim2sim.py: angular velocity, projected gravity,
  // command, 12 leg positions, 12 leg velocities, 4 wheel velocities,
  // then the raw 16-action history slot.
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.angular[i] * input.imuAxisSigns.angular[i] * CONFIG.angVelScale;
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.gravity[i] * input.imuAxisSigns.gravity[i];
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = sim.cmd[i] * CONFIG.cmdScale[i];
  for (let i = 0; i < CONFIG.numActions; i += 1) {
    if (CONFIG.controlModes[i] === "velocity") continue;
    sim.obs[offset++] = (jointQpos(i) - CONFIG.defaultAngles[i]) * CONFIG.dofPosScale;
  }
  for (let i = 0; i < CONFIG.numActions; i += 1) {
    if (CONFIG.controlModes[i] === "velocity") continue;
    sim.obs[offset++] = jointQvel(i) * CONFIG.dofVelScale;
  }
  for (let i = 0; i < CONFIG.numActions; i += 1) {
    if (CONFIG.controlModes[i] !== "velocity") continue;
    sim.obs[offset++] = jointQvel(i) * CONFIG.dofVelScale;
  }
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = sim.action[i];
}

function buildWheelLegGaitObservation() {
  if (![60, 76].includes(CONFIG.numObs) || CONFIG.numActions !== 16) {
    throw new Error(
      `wheel_leg_gait_moe_cts requires 60 or 76 observations and 16 actions; got ${CONFIG.numObs}/${CONFIG.numActions}`,
    );
  }
  buildLocomotionObservation();

  const gaitOffset = CONFIG.numObs - 3;
  // Legacy 76D policies contain 16 normalized motor-temperature slots before
  // the gait suffix. Browser Sim2Sim does not model thermal derating, so those
  // slots retain the training baseline of zero. New 60D policies omit them.
  if (CONFIG.numObs === 76) sim.obs.fill(0, 57, gaitOffset);
  const gaitActive = wheelLegGaitIsActive();
  const phase = gaitActive ? (sim.gaitElapsedS / CONFIG.gaitPeriodS) % 1 : 0;
  const angle = 2 * Math.PI * phase;
  sim.gaitActive = gaitActive;
  sim.obs[gaitOffset] = Math.sin(angle);
  sim.obs[gaitOffset + 1] = Math.cos(angle);
  sim.obs[gaitOffset + 2] = gaitActive ? 1 : 0;
}

function wheelLegGaitRequested() {
  return isWheelLegGaitPolicy() && input.gaitEnabled;
}

function wheelLegGaitCommandSpeed() {
  const yawSpeed = Math.abs(sim.cmd[2]) * CONFIG.gaitYawCommandRadius;
  return Math.sqrt(sim.cmd[0] ** 2 + sim.cmd[1] ** 2 + yawSpeed ** 2);
}

function wheelLegGaitIsActive() {
  if (!wheelLegGaitRequested()) return false;
  return !CONFIG.gaitCommandGated
    || wheelLegGaitCommandSpeed() > CONFIG.gaitLocomotionGate[0] + 1e-6;
}

function isWheelLegGaitPolicy() {
  return CONFIG.observationKind === WHEEL_LEG_GAIT_OBSERVATION;
}

function setWheelLegGaitEnabled(enabled) {
  input.gaitEnabled = Boolean(enabled);
  sim.gaitElapsedS = 0;
  sim.gaitActive = false;
  if (!input.gaitEnabled && isWheelLegGaitPolicy() && [60, 76].includes(sim.obs.length)) {
    const gaitOffset = sim.obs.length - 3;
    sim.obs[gaitOffset] = 0;
    sim.obs[gaitOffset + 1] = 1;
    sim.obs[gaitOffset + 2] = 0;
  }
  updateGaitControl();
  publishDebugState();
}

function updateGaitControl() {
  const available = isWheelLegGaitPolicy();
  if (elements.gaitControl) elements.gaitControl.hidden = !available;
  if (elements.gaitToggle) {
    elements.gaitToggle.disabled = !available;
    elements.gaitToggle.checked = available && input.gaitEnabled;
  }
  if (elements.gaitToggleState) {
    elements.gaitToggleState.textContent = input.gaitEnabled ? "ON" : "OFF";
  }
}

function advanceWheelLegGaitClock() {
  if (CONFIG.observationKind !== WHEEL_LEG_GAIT_OBSERVATION) return;
  const active = wheelLegGaitIsActive();
  sim.gaitActive = active;
  sim.gaitElapsedS = active
    ? sim.gaitElapsedS + CONFIG.simulationDt * CONFIG.controlDecimation
    : 0;
}

function buildWheelLegJumpObservation() {
  if (CONFIG.numObs !== 76 || CONFIG.numActions !== 16) {
    throw new Error(
      `wheel_leg_jump_moe_cts requires 76 observations and 16 actions; got ${CONFIG.numObs}/${CONFIG.numActions}`,
    );
  }
  buildLocomotionObservation();
  const active = isJumpCommandActive();
  const elapsed = active ? Math.max(0, (sim.data?.time || 0) - sim.jumpStartedAt) : 0;
  const phase = active ? Math.min(elapsed / WHEEL_LEG_JUMP_PERIOD_S, 1) : 0;
  const angle = 2 * Math.PI * phase;
  sim.obs.fill(0, 57, 73);
  sim.obs[73] = Math.sin(angle);
  sim.obs[74] = Math.cos(angle);
  sim.obs[75] = active ? 1 : 0;
}

function buildS07AmpCtsObservation() {
  if (CONFIG.numObs !== 45 || CONFIG.numActions !== 12) {
    throw new Error(`s07_amp_cts 需要 45 维观测和 12 维动作，当前为 ${CONFIG.numObs}/${CONFIG.numActions}`);
  }
  buildLocomotionObservation();
}

// Go2-W legs-only（unitree_rl_mjlab_go2w 部署契约，53 维）：
// base_ang_vel(3), projected_gravity(3), command(3),
// leg_jpos_rel(12 SDK 序), leg_jvel(12), wheel_jpos_rel(4), wheel_jvel(4), prev_leg_actions(12)
// 重力直立 (0,0,-1) 取负；关节顺序经 contract.action_joint_order 映射到模型索引；轮被动（ctrl=0）。
// Go2-W legs+wheel 混合策略（go2w_sim2sim 参考项目，53 维）：
// gyro*0.25(3), projected_gravity(3), cmd(3), 腿pos_rel(12), 全关节vel*0.05(16), last_action(16)
// 传感器序：FL,FR,RL,RR 每腿 hip/thigh/calf（12 腿 pos）；vel 追加 4 轮（FL,FR,RL,RR）。重力直立 (0,0,-1)。
function buildGo2wLegsObservation() {
  if (CONFIG.numObs !== 53 || CONFIG.numActions !== 16) {
    throw new Error(`go2w_53 requires 53 observations and 16 actions; got ${CONFIG.numObs}/${CONFIG.numActions}`);
  }
  const imu = readImuSample();
  const full = (sim.platformConfig?.robot?.joint_order) || [];
  const key = full.join(",") + "|" + (CONFIG.actionJointOrder || []).join(",");
  if (!sim.g2wIdx || sim.g2wIdxKey !== key) {
    const sensorLegOrder = [
      "FL_hip_joint", "FL_thigh_joint", "FL_calf_joint",
      "FR_hip_joint", "FR_thigh_joint", "FR_calf_joint",
      "RL_hip_joint", "RL_thigh_joint", "RL_calf_joint",
      "RR_hip_joint", "RR_thigh_joint", "RR_calf_joint",
    ];
    const resolveAddr = (name) => {
      try {
        const jid = Number(sim.mujoco.mj_name2id(sim.model, enumValue(sim.mujoco.mjtObj.mjOBJ_JOINT), String(name)));
        if (jid >= 0) return { q: Number(sim.model.jnt_qposadr[jid]) - 7, d: Number(sim.model.jnt_dofadr[jid]) - 6 };
      } catch (_) { /* 名单序回退 */ }
      return { q: 7 + full.indexOf(String(name)), d: 6 + full.indexOf(String(name)) };
    };
    // 动作槽 0..15 = SDK 序（12 腿 + 4 轮），需映射回模型 q/d 地址
    const sdkOrder = (CONFIG.actionJointOrder || []).slice(0, 16);
    const actAddr = sdkOrder.map((name) => resolveAddr(String(name)));
    // obs 腿段顺序 = 动作槽 SDK 序（FR,FL,RR,RL），与策略观测一致
  const legAddr = (CONFIG.actionJointOrder || []).slice(0, 12).map((name) => resolveAddr(name));
  const legDefaultBySlot = (CONFIG.actionJointOrder || []).slice(0, 12).map((name) =>
    Number(CONFIG.defaultJointAnglesByName?.[String(name).toLowerCase()] ?? 0));
    const wheelAddr = ["FL_wheel_joint", "FR_wheel_joint", "RL_wheel_joint", "RR_wheel_joint"].map((name) => resolveAddr(name));
    sim.g2wIdx = { key, legAddr, wheelAddr, actAddr, legDefault: legDefaultBySlot };
  }
  const { legAddr, wheelAddr, actAddr, legDefault } = sim.g2wIdx;
  sim.obs.fill(0);
  let offset = 0;
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.angular[i] * input.imuAxisSigns.angular[i] * 0.25;
  // go2w_sim2sim 参考实现：projected_gravity = R^T·[0,0,-1]，直立 (0,0,-1)，与采样同号，勿取负。
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.gravity[i] * input.imuAxisSigns.gravity[i];
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = sim.cmd[i] * CONFIG.cmdScale[i];
  for (let i = 0; i < 12; i += 1) {
    const { q } = legAddr[i];
    sim.obs[offset++] = (sim.qpos[q] - legDefault[i]) * 1.0;
  }
  // dof_vel 16：12 腿（传感器序）+ 4 轮（FL,FR,RL,RR）×0.05
  for (let i = 0; i < 12; i += 1) sim.obs[offset++] = sim.qvel[legAddr[i].d] * 0.05;
  for (const addr of wheelAddr) sim.obs[offset++] = sim.qvel[addr.d] * 0.05;
  for (let i = 0; i < 16; i += 1) sim.obs[offset++] = sim.action[i];
}

// Go2-W（unitree_rl_mjlab_go2w velocity_legs_only，53 维，12 腿动作 + 轮被动）：
// base_ang_vel(3), projected_gravity(3), command(3), joint_pos_rel(12), joint_vel_rel(12),
// wheel_pos_rel(4, wrap ±π), wheel_vel_rel(4), last_action(12)。
// 顺序 = mjlab 实体序：腿 SDK 按腿分组（FR,FL,RR,RL），轮 FR,FL,RR,RL。
// 重力：mjlab projected_gravity_b = R^T·[0,0,-1]，直立 (0,0,-1)，与采样同号，勿取负。
function buildGo2wMjlabLegsObservation() {
  if (CONFIG.numObs !== 53 || CONFIG.numActions !== 12) {
    throw new Error(`go2w_mjlab_legs_53 requires 53 observations and 12 actions; got ${CONFIG.numObs}/${CONFIG.numActions}`);
  }
  const imu = readImuSample();
  const key = (sim.platformConfig?.robot?.joint_order || []).join(",");
  if (!sim.g2wMjIdx || sim.g2wMjIdxKey !== key) {
    const resolve = (name) => {
      const jid = Number(sim.mujoco.mj_name2id(sim.model, enumValue(sim.mujoco.mjtObj.mjOBJ_JOINT), name));
      return jid >= 0
        ? { q: Number(sim.model.jnt_qposadr[jid]), d: Number(sim.model.jnt_dofadr[jid]) }
        : null;
    };
    sim.g2wMjIdx = {
      key,
      wheels: (CONFIG.observationMask?.wrapPi?.length
      ? CONFIG.observationMask.wrapPi
      : ["FR_wheel_joint", "FL_wheel_joint", "RR_wheel_joint", "RL_wheel_joint"]
    ).map(resolve),
    };
  }
  const wrapPi = (a) => Math.atan2(Math.sin(a), Math.cos(a));
  sim.obs.fill(0);
  let offset = 0;
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.angular[i] * input.imuAxisSigns.angular[i] * CONFIG.angVelScale;
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.gravity[i] * input.imuAxisSigns.gravity[i];
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = sim.cmd[i] * CONFIG.cmdScale[i];
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = (jointQpos(i) - CONFIG.defaultAngles[i]) * CONFIG.dofPosScale;
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = jointQvel(i) * CONFIG.dofVelScale;
  for (const w of sim.g2wMjIdx.wheels) sim.obs[offset++] = w ? wrapPi(sim.qpos[w.q]) : 0;
  for (const w of sim.g2wMjIdx.wheels) sim.obs[offset++] = (w ? sim.qvel[w.d] : 0) * CONFIG.dofVelScale;
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = sim.action[i];
}

// Go2-W rl_sar/robot_lab 部署契约（57 维，16 动作 = 12 腿位置 + 4 轮速度）：
// ang_vel×0.25(body), gravity, cmd×1.0, (dof_pos-default)×1.0【轮位置清零】,
// dof_vel×0.05（全 16）, 原始 action（未乘 scale，clip ±100 后）。
// 输出端：腿 PD 目标 = a×scale+default（rl_kp20/rl_kd0.5）；轮 = a×5.0 纯速度目标（rl_kp=0）。
function buildGo2wRlSdkObservation() {
  if (CONFIG.numObs !== 57 || CONFIG.numActions !== 16) {
    throw new Error(`go2w_rl_sdk_57 requires 57 observations and 16 actions; got ${CONFIG.numObs}/${CONFIG.numActions}`);
  }
  const imu = readImuSample();
  sim.obs.fill(0);
  let offset = 0;
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.angular[i] * input.imuAxisSigns.angular[i] * CONFIG.angVelScale;
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.gravity[i] * input.imuAxisSigns.gravity[i];
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = sim.cmd[i] * CONFIG.cmdScale[i];
  for (let i = 0; i < CONFIG.numActions; i += 1) {
    const rel = (jointQpos(i) - CONFIG.defaultAngles[i]) * CONFIG.dofPosScale;
    sim.obs[offset++] = CONFIG.controlModes[i] === "velocity" ? 0 : rel;
  }
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = jointQvel(i) * CONFIG.dofVelScale;
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = sim.action[i];
}

// Go2-W HIMLoco（LeggedSkillDeploy go2w_himloco，57 维，16 动作 = 12 腿位置 + 4 轮速度）：
// 单帧按部署 yaml `observations` 列表序：commands(3)·[2,2,0.25], ang_vel(3)·0.25(body),
//   projected_gravity(3), (dof_pos-default)(16)·1.0【wheel 位置清零】, dof_vel(16)·0.05,
//   原始 action(16)。onnx 输入 [1,342] = 57×6 帧 history，frame_major_v1（最新帧在前）。
// 输出端：腿 PD 目标 = a×0.25+default（kp20/kd0.5）；轮 = a×5.0 纯速度目标（kp=0）。
function buildGo2wHimlocoObservation() {
  if (CONFIG.numObs !== 57 || CONFIG.numActions !== 16) {
    throw new Error(`go2w_himloco_57 requires 57 observations and 16 actions; got ${CONFIG.numObs}/${CONFIG.numActions}`);
  }
  const imu = readImuSample();
  sim.obs.fill(0);
  let offset = 0;
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = sim.cmd[i] * CONFIG.cmdScale[i];
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.angular[i] * input.imuAxisSigns.angular[i] * CONFIG.angVelScale;
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.gravity[i] * input.imuAxisSigns.gravity[i];
  for (let i = 0; i < CONFIG.numActions; i += 1) {
    const rel = (jointQpos(i) - CONFIG.defaultAngles[i]) * CONFIG.dofPosScale;
    sim.obs[offset++] = CONFIG.controlModes[i] === "velocity" ? 0 : rel;
  }
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = jointQvel(i) * CONFIG.dofVelScale;
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = sim.action[i];
}

// Wuji Hand in-hand 立方体重定向（69 维，20 动作）：归一化关节角(20) + 关节目标
// 误差(20) + tag 系立方体位置(3) + 目标 6D 朝向误差(6) + 上一动作(20)，history 3。
// 参考 00_resources/wuji-mjlab tasks/reorient（observations.py / reorient_terms.py）。
// tag 系：palm 世界位姿 ∘ 恒定 tag-in-palm 刚体变换；目标按 SO(3) 均匀采样于 tag 系。
const WUJI_TAG_POS = [0.0262, 0.0, -0.0563];
const WUJI_TAG_QUAT = [Math.SQRT1_2, 0.0, Math.SQRT1_2, 0.0]; // R_y(+90°), wxyz

function wujiQuatMul(a, b) {
  return [
    a[0] * b[0] - a[1] * b[1] - a[2] * b[2] - a[3] * b[3],
    a[0] * b[1] + a[1] * b[0] + a[2] * b[3] - a[3] * b[2],
    a[0] * b[2] - a[1] * b[3] + a[2] * b[0] + a[3] * b[1],
    a[0] * b[3] + a[1] * b[2] - a[2] * b[1] + a[3] * b[0],
  ];
}
function wujiQuatConj(q) { return [q[0], -q[1], -q[2], -q[3]]; }
function wujiRotate(q, v) {
  const [w, x, y, z] = q;
  const t = [2 * (y * v[2] - z * v[1]), 2 * (z * v[0] - x * v[2]), 2 * (x * v[1] - y * v[0])];
  return [
    v[0] + w * t[0] + (y * t[2] - z * t[1]),
    v[1] + w * t[1] + (z * t[0] - x * t[2]),
    v[2] + w * t[2] + (x * t[1] - y * t[0]),
  ];
}
function wujiMatrixFromQuat(q) {
  const [w, x, y, z] = q;
  return [
    1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y),
    2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x),
    2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y),
  ];
}
function wujiSampleGoal(tagQuat) {
  const u1 = Math.random(), u2 = Math.random(), u3 = Math.random();
  const rel = [
    Math.sqrt(1 - u1) * Math.sin(2 * Math.PI * u2),
    Math.sqrt(1 - u1) * Math.cos(2 * Math.PI * u2),
    Math.sqrt(u1) * Math.sin(2 * Math.PI * u3),
    Math.sqrt(u1) * Math.cos(2 * Math.PI * u3),
  ];
  return wujiQuatMul(tagQuat, rel);
}
function wujiSoftLimit(model, jid) {
  // center ± 0.9·half（mjlab soft_joint_pos_limit_factor=0.9）
  const lo = Number(model.jnt_range[2 * jid]);
  const hi = Number(model.jnt_range[2 * jid + 1]);
  return [0.5 * (lo + hi), 0.5 * (hi - lo) * 0.9];
}
function buildWujiReorientObservation() {
  if (CONFIG.numObs !== 69 || CONFIG.numActions !== 20) {
    throw new Error(`wuji_reorient_69 requires 69 observations and 20 actions; got ${CONFIG.numObs}/${CONFIG.numActions}`);
  }
  const model = sim.model;
  const data = sim.data;
  const mj = sim.mujoco;
  // WASM 枚举是包装对象：mj_name2id 需要 enumValue() 解包后的数字
  // （G1 全机型浏览器实测缺陷 C——wuji 两个 builder 直接传包装对象，
  // 抛 'Cannot convert "[object Object]" to int'，仿真异常自动重试循环）。
  const jntObj = enumValue(mj.mjtObj.mjOBJ_JOINT);
  const bodyObj = enumValue(mj.mjtObj.mjOBJ_BODY);
  const order = CONFIG.actionJointOrder || [];
  const bodyId = (name) => Number(mj.mj_name2id(model, bodyObj, String(name)));

  sim.obs.fill(0);
  let offset = 0;
  const normJoint = new Float64Array(CONFIG.numActions);
  for (let i = 0; i < CONFIG.numActions; i += 1) {
    const jid = Number(mj.mj_name2id(model, jntObj, String(order[i])));
    let normalized = 0;
    if (jid >= 0) {
      const [center, half] = wujiSoftLimit(model, jid);
      normalized = clamp((jointQpos(i) - center) / (half + 1e-6), -1, 1);
    }
    normJoint[i] = normalized;
    sim.obs[offset++] = normalized;
  }
  // qpos_error：当前归一化关节角 - 上一步处理后的动作目标（与 mjlab 同序）
  for (let i = 0; i < CONFIG.numActions; i += 1) {
    const jid = Number(mj.mj_name2id(model, jntObj, String(order[i])));
    let target = 0;
    if (jid >= 0) {
      const [center, half] = wujiSoftLimit(model, jid);
      target = clamp((sim.targetDofPos[i] - center) / (half + 1e-6), -1, 1);
    }
    sim.obs[offset++] = normJoint[i] - target;
  }
  // tag 系立方体位置 + 目标 6D 朝向误差
  const palmId = bodyId("right_palm_link");
  const cubeId = bodyId("cube");
  const palmPos = [data.xpos[3 * palmId], data.xpos[3 * palmId + 1], data.xpos[3 * palmId + 2]];
  const palmQuat = [data.xquat[4 * palmId], data.xquat[4 * palmId + 1], data.xquat[4 * palmId + 2], data.xquat[4 * palmId + 3]];
  const tagOffset = wujiRotate(palmQuat, WUJI_TAG_POS);
  const tagPos = [palmPos[0] + tagOffset[0], palmPos[1] + tagOffset[1], palmPos[2] + tagOffset[2]];
  const tagQuat = wujiQuatMul(palmQuat, WUJI_TAG_QUAT);
  const cubePos = [data.xpos[3 * cubeId], data.xpos[3 * cubeId + 1], data.xpos[3 * cubeId + 2]];
  const cubeQuat = [data.xquat[4 * cubeId], data.xquat[4 * cubeId + 1], data.xquat[4 * cubeId + 2], data.xquat[4 * cubeId + 3]];
  const cubePosTag = wujiRotate(wujiQuatConj(tagQuat), [cubePos[0] - tagPos[0], cubePos[1] - tagPos[1], cubePos[2] - tagPos[2]]);
  sim.obs[offset++] = cubePosTag[0];
  sim.obs[offset++] = cubePosTag[1];
  sim.obs[offset++] = cubePosTag[2];

  // 目标状态机：未设/达成后重采样（朝向误差 < 0.2 连续 5 步算达成）
  if (!sim.wujiGoalQuat) { sim.wujiGoalQuat = wujiSampleGoal(tagQuat); sim.wujiHold = 0; }
  const tagInv = wujiQuatConj(tagQuat);
  const qErr = wujiQuatMul(wujiQuatMul(tagInv, cubeQuat), wujiQuatConj(wujiQuatMul(tagInv, sim.wujiGoalQuat)));
  const mat = wujiMatrixFromQuat(qErr);
  for (let i = 3; i < 9; i += 1) sim.obs[offset++] = mat[i];
  const dot = Math.abs(
    cubeQuat[0] * sim.wujiGoalQuat[0] + cubeQuat[1] * sim.wujiGoalQuat[1]
    + cubeQuat[2] * sim.wujiGoalQuat[2] + cubeQuat[3] * sim.wujiGoalQuat[3],
  );
  const oriErr = 2 * Math.acos(clamp(Math.min(1, dot), -1, 1));
  sim.wujiHold = oriErr < 0.2 ? (sim.wujiHold || 0) + 1 : 0;
  if (sim.wujiHold >= 5) { sim.wujiGoalQuat = wujiSampleGoal(tagQuat); sim.wujiHold = 0; }

  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = sim.action[i];
}

// Go1（mujoco_playground Joystick 官方导出，play_go1_joystick.py 逐行取证）：
// local_linvel(3), gyro(3), projected_gravity(3), joint_pos_rel(12),
// joint_vel(12), last_action(12), command(3) —— 全部裸值无缩放；
// 动作 = position target：action * 0.5 + default（action_scale=0.5，50Hz）。
function buildGo1PlaygroundObservation() {
  if (CONFIG.numObs !== 48 || CONFIG.numActions !== 12) {
    throw new Error(`go1_playground_48 requires 48 observations and 12 actions; got ${CONFIG.numObs}/${CONFIG.numActions}`);
  }
  const imu = readImuSample();
  sim.obs.fill(0);
  let offset = 0;
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = (imu.linear ? imu.linear[i] : 0);
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.angular[i] * input.imuAxisSigns.angular[i];
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.gravity[i] * input.imuAxisSigns.gravity[i];
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = jointQpos(i) - CONFIG.defaultAngles[i];
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = jointQvel(i);
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = sim.action[i];
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = sim.cmd[i];
}

// Go1 HIM（HIMLoco 系；LeggedSkillDeploy go1/himloco config.yaml + 官方
// src/scripts/{rl_sdk.py,observation_buffer.py} 源码取证）：
// 单帧 45 按部署 yaml `observations` 列表序拼接（rl_sdk 按列表序逐项取值）：
//   commands(3)·[2,2,0.25], ang_vel(3)·0.25【body 系】, projected_gravity(3),
//   joint_pos_rel(12)·1.0, joint_vel(12)·0.05, last_action(12)。
// onnx 输入 [1,270] = 45×6 帧 history，布局 frame_major_v1（新）：
//   ObservationBuffer.get_obs_vec 对 yaml 倒序表 [5,4,3,2,1,0] 做 reversed
//   遍历后 torch.cat —— 语义 = 整帧拼接且最新帧在前（[obs_t, obs_{t-1}, …]）。
//   旧注释"块主序、最老帧在前"是误读，已被官方代码证伪。mjswan himloco.json
//   的 interleaved/world_frame 声明同样不采信。动作 = position target
//   （rl_kp=40/rl_kd=1，per-policy PD 写入模型执行器，见包内 robot.xml）。
function buildGo1HimlocoObservation() {
  if (CONFIG.numObs !== 45 || CONFIG.numActions !== 12) {
    throw new Error(`himloco_45_hist6 requires 45 single-frame observations and 12 actions; got ${CONFIG.numObs}/${CONFIG.numActions}`);
  }
  const imu = readImuSample();
  sim.obs.fill(0);
  let offset = 0;
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = sim.cmd[i] * CONFIG.cmdScale[i];
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.angular[i] * input.imuAxisSigns.angular[i] * CONFIG.angVelScale;
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.gravity[i] * input.imuAxisSigns.gravity[i];
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = (jointQpos(i) - CONFIG.defaultAngles[i]) * CONFIG.dofPosScale;
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = jointQvel(i) * CONFIG.dofVelScale;
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = sim.action[i];
}

// Go2/B2 四足 rl_sar/robot_lab 部署契约（45 维，12 位置动作）：
// ang_vel×0.25(body), gravity, cmd×1.0, (dof_pos-default)×1.0, dof_vel×0.05, 原始 action。
// 45 维帧的**共享填充**：lainlab_handstand_48（3 个恒零 legacy 前缀 + 同一帧）也用它，
// 抽取时逐字保持原实现 —— 既有 go2_rl_sdk_45 策略的行为不得有任何变化（测试钉着）。
function fillRlSdkActorFrame(startOffset) {
  const imu = readImuSample();
  let offset = startOffset;
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.angular[i] * input.imuAxisSigns.angular[i] * CONFIG.angVelScale;
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.gravity[i] * input.imuAxisSigns.gravity[i];
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = sim.cmd[i] * CONFIG.cmdScale[i];
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = (jointQpos(i) - CONFIG.defaultAngles[i]) * CONFIG.dofPosScale;
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = jointQvel(i) * CONFIG.dofVelScale;
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = sim.action[i];
  return offset;
}

function buildGo2RlSdkObservation() {
  if (CONFIG.numObs !== 45 || CONFIG.numActions !== 12) {
    throw new Error(`go2_rl_sdk_45 requires 45 observations and 12 actions; got ${CONFIG.numObs}/${CONFIG.numActions}`);
  }
  sim.obs.fill(0);
  fillRlSdkActorFrame(0);
}

// ── LainLab playground 技能族（2026-09-20 入库；全部布局由 ONNX 图 + 包内训练源取证）──
// 共同点：12 位置动作、action_scale 0.25、50Hz 控制（physics_dt 0.005 × decimation 4）。
// **缩放用字面量**（训练源即真值），不走 CONFIG 的缩放字段——那些是各部署契约的，混用会漂移。

// DreamWaQ / AMP-CTS 单帧（45，**cmd 在前**，与 rl_sdk 的 ang_vel 在前**不同序**，见
// dreamwaq/mdp/observations.py::_actor_frame）。ONNX 270 = [history 5×45（旧→新）, 当前帧]
// （图实测：首个 Slice 为 [0:-45]，encoder 吃前 225、actor MLP 吃末 45）⇒ 契约
// history_layout 必须 = "frame_major_oldest_first"。
function buildLainlabDreamObservation() {
  if (CONFIG.numObs !== 45 || CONFIG.numActions !== 12) {
    throw new Error(`lainlab_dream_45_hist6 requires 45 observations and 12 actions; got ${CONFIG.numObs}/${CONFIG.numActions}`);
  }
  const imu = readImuSample();
  sim.obs.fill(0);
  let offset = 0;
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = sim.cmd[i] * [2.0, 2.0, 0.25][i];
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.angular[i] * input.imuAxisSigns.angular[i] * 0.25;
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.gravity[i] * input.imuAxisSigns.gravity[i];
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = jointQpos(i) - CONFIG.defaultAngles[i];
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = jointQvel(i) * 0.05;
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = sim.action[i];
}

// trot / jump / spring_jump 单帧（47，trot/mdp/observations.py::actor_frame）：
// [sin(2π·phase), cos(2π·phase), cmd_x×2, cmd_y×2, cmd_w×0.25]（5）+ ang_vel×0.25（3）
// + euler_xyz（3）+ (dof_pos−default)（12）+ dof_vel×0.05（12）+ action（12）。
// ONNX 470 = 10×47 按历史缓冲原序（frame-major、旧→新，_SourceHistory）⇒ 同上 layout。
// phase = (episode 计步 × step_dt) mod cycle_time / cycle_time，cycle_time 逐技能
// （trot 0.5 / jump 1.5，进契约 gait_period_s），step_dt = 0.02s。这里用 mujoco 的
// sim.data.time（每步推进、reset 归零）对应 episode_length_buf × step_dt。
// euler 取 IMU rpy（mjlab 侧为 root_link_quat_w 的 xyz euler）。
function buildLainlabGaitObservation() {
  if (CONFIG.numObs !== 47 || CONFIG.numActions !== 12) {
    throw new Error(`lainlab_gait_47_hist10 requires 47 observations and 12 actions; got ${CONFIG.numObs}/${CONFIG.numActions}`);
  }
  const imu = readImuSample();
  const period = CONFIG.gaitPeriodS > 0 ? CONFIG.gaitPeriodS : 0.5;
  const elapsed = Number(sim.data && sim.data.time) || 0;
  const phase = (elapsed % period) / period;
  sim.obs.fill(0);
  let offset = 0;
  sim.obs[offset++] = Math.sin(2 * Math.PI * phase);
  sim.obs[offset++] = Math.cos(2 * Math.PI * phase);
  sim.obs[offset++] = sim.cmd[0] * 2.0;
  sim.obs[offset++] = sim.cmd[1] * 2.0;
  sim.obs[offset++] = sim.cmd[2] * 0.25;
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.angular[i] * input.imuAxisSigns.angular[i] * 0.25;
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.rpy ? imu.rpy[i] : 0;
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = jointQpos(i) - CONFIG.defaultAngles[i];
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = jointQvel(i) * 0.05;
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = sim.action[i];
}

// spring_jump 单帧（47，spring_jump/mdp/observations.py::_actor_frame）：**无相位项**（该任务
// 没有 cycle_time 参数），前 2 位是恒零 legacy 前缀：[zeros(2), 裸 cmd（**无缩放**）,
// ang_vel×0.25, euler_xyz, (dof_pos−default), dof_vel×0.05, action]。ONNX 470 = 10×47
// 按历史缓冲原序（旧→新）⇒ 同 frame_major_oldest_first。
function buildLainlabSpringObservation() {
  if (CONFIG.numObs !== 47 || CONFIG.numActions !== 12) {
    throw new Error(`lainlab_spring_47_hist10 requires 47 observations and 12 actions; got ${CONFIG.numObs}/${CONFIG.numActions}`);
  }
  const imu = readImuSample();
  sim.obs.fill(0);
  let offset = 2; // 前 2 位恒零（legacy 字段，训练时从未被写）
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = sim.cmd[i];
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.angular[i] * input.imuAxisSigns.angular[i] * 0.25;
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.rpy ? imu.rpy[i] : 0;
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = jointQpos(i) - CONFIG.defaultAngles[i];
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = jointQvel(i) * 0.05;
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = sim.action[i];
}

// handstand 单帧（48）= **3 个恒零 legacy 前缀**（上游注释：zeros(2)+stand_command(1)，
// 训练时恒为零、从未被写）+ 45 维 rl_sdk 标准帧（同序同缩放，handstand_actor_frame 的
// constant_prefix_dim=3）。
function buildLainlabHandstandObservation() {
  if (CONFIG.numObs !== 48 || CONFIG.numActions !== 12) {
    throw new Error(`lainlab_handstand_48 requires 48 observations and 12 actions; got ${CONFIG.numObs}/${CONFIG.numActions}`);
  }
  sim.obs.fill(0);
  fillRlSdkActorFrame(3);
}

// Go2 模仿学习技能（LeggedSkillDeploy 协议，69 维）：
// motion_command(24) = [ref_joint_pos(12), ref_joint_vel(12)]（按 joint_mapping 从 CSV 序重排到训练序）
// motion_anchor_ori_b(6) = conj(init_quat*ref_quat)*real_quat 旋转矩阵前两列展平
// ang_vel×1.0 + (dof_pos−default)×1.0 + dof_vel×1.0 + action
// 参考动作 CSV：simulation/policies/backflip_motion.csv（fps50, 0-1.6s, xyzw 四元数）
function buildGo2MotionObservation() {
  if (CONFIG.numObs !== 69 || CONFIG.numActions !== 12) {
    throw new Error(`go2_motion_69 requires 69 observations and 12 actions; got ${CONFIG.numObs}/${CONFIG.numActions}`);
  }
  const loader = sim.motionLoader;
  sim.obs.fill(0);
  if (!loader) return;
  motionTime += 0.02;
  // 上游 rl_sdk.py:203 `motion_time = min(self.rl_time, duration)`：默认【钳制保持
  // 末帧】。曾无条件取模回绕，backflip 落地阶段参考被重置回起始蹲跳段，策略被要求
  // 重新起跳 → 机器人背部着地。契约声明 motion_params.loop=true 时才循环重放
  // （需要连续演示的可重放技能），此时要求参考首末帧姿态连续。
  if (motionTime > loader.duration) {
    motionTime = CONFIG.motionLoop === true ? motionTime % loader.duration : loader.duration;
  }
  loader.update(motionTime);

  const imu = readImuSample();
  let offset = 0;

  // motion_command(24): reference joint pos/vel mapped into training order
  const refPos = loader.jointPos();
  const refVel = loader.jointVel();
  const mapping = CONFIG.motionJointMapping || refPos.map((_, i) => i);
  for (let i = 0; i < mapping.length; i += 1) sim.obs[offset++] = refPos[mapping[i]];
  for (let i = 0; i < mapping.length; i += 1) sim.obs[offset++] = refVel[mapping[i]];

  // motion_anchor_ori_b(6)
  const realQuat = Array.from(sim.qpos.subarray(3, 7));
  const refQuat = loader.rootQuaternion();
  sim.obs.set(loader.motionAnchorOriB(realQuat, refQuat), offset);
  offset += 6;

  // ang_vel + dof_pos + dof_vel + actions
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.angular[i] * input.imuAxisSigns.angular[i] * CONFIG.angVelScale;
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = jointQpos(i) - CONFIG.defaultAngles[i];
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = jointQvel(i);
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = sim.action[i];
}

// G1 动作跟踪策略（LeggedSkillDeploy 协议，154 维，29 自由度含腰三关节）：
// motion_command(58) = [ref_dof_pos(29), ref_dof_vel(29)]——CSV 机器人关节列按
//   motion_joint_mapping 重排到策略槽位序（该序为左右成对序，腰 yaw/roll/pitch 在槽 2/5/8）；
// motion_anchor_ori_b(6) = conj(init_quat*ref_torso)*real_torso 旋转矩阵前两列展平。
//   torso 四元数 = root 四元数 ∘ 腰 yaw(z) ∘ roll(x) ∘ pitch(y)——29 自由度腰部补偿；
//   ref 侧腰角取 CSV 第 12/13/14 列（机器人关节序的腰三轴），real 侧取机器人当前腰角。
// ang_vel(3) + (dof_pos−default)(29) + dof_vel(29) + actions(29)，全部按策略槽位序；
// 整条观测按 contract.clip_obs（上游 ±100）裁剪。
function buildG1Motion154Observation() {
  if (CONFIG.numObs !== 154 || CONFIG.numActions !== 29) {
    throw new Error(`g1_motion_154 requires 154 observations and 29 actions; got ${CONFIG.numObs}/${CONFIG.numActions}`);
  }
  const loader = sim.motionLoader;
  sim.obs.fill(0);
  if (!loader) return;
  motionTime += CONFIG.simulationDt * CONFIG.controlDecimation;
  if (motionTime > loader.duration) motionTime = motionTime % loader.duration;
  loader.update(motionTime);

  const imu = readImuSample();
  let offset = 0;

  // motion_command(58): reference joint pos/vel mapped into policy slot order
  const refPos = loader.jointPos();
  const refVel = loader.jointVel();
  const mapping = CONFIG.motionJointMapping || refPos.map((_, i) => i);
  for (let i = 0; i < mapping.length; i += 1) sim.obs[offset++] = refPos[mapping[i]];
  for (let i = 0; i < mapping.length; i += 1) sim.obs[offset++] = refVel[mapping[i]];

  // motion_anchor_ori_b(6): waist-compensated torso relative orientation
  const baseQuat = Array.from(sim.qpos.subarray(3, 7));
  const waistSlots = CONFIG.waistJointIndices || [2, 5, 8];
  const waistReal = waistSlots.map((slot) => jointQpos(mapping[slot]));
  const realQuat = loader.torsoQuatW(baseQuat, waistReal);
  const refQuat = loader.anchorQuatW();
  sim.obs.set(loader.motionAnchorOriB(realQuat, refQuat), offset);
  offset += 6;

  // ang_vel + dof_pos_rel + dof_vel + actions（策略槽位序）
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.angular[i] * input.imuAxisSigns.angular[i] * CONFIG.angVelScale;
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = (jointQpos(mapping[i]) - CONFIG.defaultAngles[mapping[i]]) * CONFIG.dofPosScale;
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = jointQvel(mapping[i]) * CONFIG.dofVelScale;
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = sim.action[i];

  if (CONFIG.clipObs !== null) {
    for (let i = 0; i < CONFIG.numObs; i += 1) {
      sim.obs[i] = clamp(sim.obs[i], -CONFIG.clipObs, CONFIG.clipObs);
    }
  }
}

// G1 AMP（parkour_mjlab sim2sim 契约，96 维）：
// 约定：mjlab projected_gravity_b = R^T·[0,0,-1]，直立 (0,0,-1)，与 app IMU 采样同号。
function buildG1AmpObservation() {
  if (CONFIG.numObs !== 96 || CONFIG.numActions !== 29) {
    throw new Error(`g1_amp_96 requires 96 observations and 29 actions; got ${CONFIG.numObs}/${CONFIG.numActions}`);
  }
  const imu = readImuSample();
  sim.obs.fill(0);
  let offset = 0;
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.angular[i] * input.imuAxisSigns.angular[i] * CONFIG.angVelScale;
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.gravity[i] * input.imuAxisSigns.gravity[i];
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = sim.cmd[i] * CONFIG.cmdScale[i];
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = (jointQpos(i) - CONFIG.defaultAngles[i]) * CONFIG.dofPosScale;
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = jointQvel(i) * CONFIG.dofVelScale;
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = sim.action[i];
}

// G1 mjlab velocity（98 维，含步态相位）：
// base_ang_vel(3), projected_gravity(3), command(3), phase(2), joint_pos_rel(29), joint_vel(29), actions(29)
// phase：周期 0.6s 的 [sin, cos]，|command| < 0.1（站立）时清零；重力直立 (0,0,-1)，与采样同号。
function buildG1MjlabVelocityObservation() {
  if (CONFIG.numObs !== 98 || CONFIG.numActions !== 29) {
    throw new Error(`g1_mjlab_velocity_98 requires 98 observations and 29 actions; got ${CONFIG.numObs}/${CONFIG.numActions}`);
  }
  const imu = readImuSample();
  if (!Number.isFinite(sim.g1PhaseS)) sim.g1PhaseS = 0;
  const period = CONFIG.gaitPeriodS > 0 ? CONFIG.gaitPeriodS : 0.6;
  const cmdNorm = Math.hypot(sim.cmd[0], sim.cmd[1], sim.cmd[2]);
  // 训练相位钟 = 回合时间；站立只清零输出，时钟不停。
  //
  // **2026-09-22 订正（口径）**：原先是"先推进、再算相位" ⇒ 第一帧相位就 ≠ 0，
  // 比训练侧（`episode_length_buf=0` 的 reset obs，相位 0）与验收器镜像
  // （`_frame_g1_mjlab_velocity_98`：先算后推进）都**领先一个控制步**，实测对拍
  // 第 [9] 维 验收器 +0.000000 vs 浏览器 +0.207912。改为"**用当前相位、算完再推进**"，
  // 与本文件 `advanceWheelLegGaitClock()`（app.js 在 runPolicy() **之后**调用）同拍，
  // 也与上游训练一致：obs 用**本步开始时**的相位。
  const globalPhase = (sim.g1PhaseS % period) / period;
  const phaseSin = cmdNorm < 0.1 ? 0 : Math.sin(globalPhase * Math.PI * 2);
  const phaseCos = cmdNorm < 0.1 ? 0 : Math.cos(globalPhase * Math.PI * 2);
  sim.g1PhaseS += CONFIG.simulationDt * CONFIG.controlDecimation;
  sim.obs.fill(0);
  let offset = 0;
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.angular[i] * input.imuAxisSigns.angular[i] * CONFIG.angVelScale;
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.gravity[i] * input.imuAxisSigns.gravity[i];
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = sim.cmd[i] * CONFIG.cmdScale[i];
  sim.obs[offset++] = phaseSin;
  sim.obs[offset++] = phaseCos;
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = (jointQpos(i) - CONFIG.defaultAngles[i]) * CONFIG.dofPosScale;
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = jointQvel(i) * CONFIG.dofVelScale;
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = sim.action[i];
}

// G1（mjswan 移植策略，mjlab velocity 观测序）：base_lin_vel(3), base_ang_vel(3),
// projected_gravity(3), joint_pos_rel(29), joint_vel(29), last_action(29), command(3)
// 注意：mjlab projected_gravity_b = R^T·[0,0,-1]，直立 (0,0,-1)，与 app IMU 采样同号，勿取负。
function buildG1MjswanLocomotionObservation() {
  if (CONFIG.numObs !== 99 || CONFIG.numActions !== 29) {
    throw new Error(`g1_mjswan_locomotion requires 99 observations and 29 actions; got ${CONFIG.numObs}/${CONFIG.numActions}`);
  }
  const imu = readImuSample();
  sim.obs.fill(0);
  let offset = 0;
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = (imu.linear ? imu.linear[i] : 0);
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.angular[i] * input.imuAxisSigns.angular[i] * CONFIG.angVelScale;
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.gravity[i] * input.imuAxisSigns.gravity[i];
  // mjlab joint_pos_rel：关节角减 default（桌面复现环验证 rel 站立/行走稳定）
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = (jointQpos(i) - CONFIG.defaultAngles[i]) * CONFIG.dofPosScale;
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = jointQvel(i) * CONFIG.dofVelScale;
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = sim.action[i];
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = sim.cmd[i] * CONFIG.cmdScale[i];
}

// G1 Balance（mjswan 移植策略）：base_ang_vel(3), projected_gravity(3),
// joint_pos_rel(29), joint_vel(29), last_action(29) —— 无指令输入
function buildG1MjswanBalanceObservation() {
  if (CONFIG.numObs !== 93 || CONFIG.numActions !== 29) {
    throw new Error(`g1_mjswan_balance requires 93 observations and 29 actions; got ${CONFIG.numObs}/${CONFIG.numActions}`);
  }
  const imu = readImuSample();
  sim.obs.fill(0);
  let offset = 0;
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.angular[i] * input.imuAxisSigns.angular[i] * CONFIG.angVelScale;
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.gravity[i] * input.imuAxisSigns.gravity[i];
  // 同上：rel 语义
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = (jointQpos(i) - CONFIG.defaultAngles[i]) * CONFIG.dofPosScale;
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = jointQvel(i) * CONFIG.dofVelScale;
  for (let i = 0; i < CONFIG.numActions; i += 1) sim.obs[offset++] = sim.action[i];
}

function buildLocomotionObservation() {
  const layout = observationLayout();
  const imu = readImuSample();
  const gravity = imu.gravity;
  // MuJoCo free-joint angular qvel is already expressed in the body frame.
  const bodyAngularVelocity = imu.angular;

  sim.obs.fill(0);
  sim.obs[0] = bodyAngularVelocity[0] * input.imuAxisSigns.angular[0] * CONFIG.angVelScale;
  sim.obs[1] = bodyAngularVelocity[1] * input.imuAxisSigns.angular[1] * CONFIG.angVelScale;
  sim.obs[2] = bodyAngularVelocity[2] * input.imuAxisSigns.angular[2] * CONFIG.angVelScale;
  sim.obs[3] = gravity[0] * input.imuAxisSigns.gravity[0];
  sim.obs[4] = gravity[1] * input.imuAxisSigns.gravity[1];
  sim.obs[5] = gravity[2] * input.imuAxisSigns.gravity[2];
  sim.obs[6] = sim.cmd[0] * CONFIG.cmdScale[0];
  sim.obs[7] = sim.cmd[1] * CONFIG.cmdScale[1];
  sim.obs[8] = sim.cmd[2] * CONFIG.cmdScale[2];
  if (layout.heightCommand) {
    sim.obs[9] = bucketHeightCommand(sim.cmd[heightCommandIndex()]) * CONFIG.heightCommandScale;
  }

  for (let i = 0; i < CONFIG.numActions; i += 1) {
    // src = sim joint index that goes into obs slot i. With NP3O reindex the
    // policy expects dof segments permuted (FL<->FR, RL<->RR).
    const src = CONFIG.dofReindex ? CONFIG.dofReindex[i] : i;
    sim.obs[layout.jointOffset + i] = CONFIG.controlModes[src] === "velocity"
      ? 0
      : (jointQpos(src) - CONFIG.defaultAngles[src]) * CONFIG.dofPosScale;
    sim.obs[layout.velocityOffset + i] = jointQvel(src) * CONFIG.dofVelScale;
    // Action segment mirrors the network output order (already stored permuted
    // in sim.action), so no extra reindex here.
    sim.obs[layout.actionOffset + i] = sim.action[i];
  }
}

// TRON1（LimX）encoder+policy 部署：单帧 obs 与 tron1-rl-deploy-python 的
// controllers 对齐。isaaclab 模式关节段按 swap 表重排；点足/足底末尾拼
// gait_clock(2)+gait(4)；轮足 joint_pos 排除轮（jointPosIdx）。编码器输入为
// 该单帧的历史缓冲（oldest→newest），由 app.js 的 encoder 链负责打包。
function swapByMapping(arr, mapping) {
  const out = new Array(mapping.length).fill(0);
  for (let i = 0; i < mapping.length; i += 1) out[i] = arr[mapping[i]];
  return out;
}

function buildTron1Observation(gait) {
  const imu = readImuSample();
  const n = CONFIG.numActions;
  const mapping = CONFIG.tron1Swap || Array.from({ length: n }, (_, i) => i);
  sim.obs.fill(0);
  const q = [];
  const dq = [];
  const act = [];
  for (let i = 0; i < n; i += 1) {
    q.push(jointQpos(i));
    dq.push(jointQvel(i));
    act.push(sim.action[i]);
  }
  let jp = q.map((v, i) => (v - CONFIG.defaultAngles[i]) * CONFIG.dofPosScale);
  if (CONFIG.tron1JointPosIdx && CONFIG.tron1JointPosIdx.length) {
    jp = CONFIG.tron1JointPosIdx.map((idx) => jp[idx]);
    jp = swapByMapping(jp, CONFIG.tron1SwapPos || mapping);
  } else {
    jp = swapByMapping(jp, mapping);
  }
  const dqs = swapByMapping(dq.map((v) => v * CONFIG.dofVelScale), mapping);
  const acts = swapByMapping(act, mapping);
  let offset = 0;
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.angular[i] * input.imuAxisSigns.angular[i] * CONFIG.angVelScale;
  for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.gravity[i] * input.imuAxisSigns.gravity[i];
  for (const v of jp) sim.obs[offset++] = v;
  for (const v of dqs) sim.obs[offset++] = v;
  for (const v of acts) sim.obs[offset++] = v;
  if (gait) {
    const freq = CONFIG.tron1GaitFreq || 1.3;
    const swing = CONFIG.tron1GaitSwing || 0.12;
    sim.tron1GaitIndex = ((sim.tron1GaitIndex || 0) + 0.02 * freq) % 1;
    sim.obs[offset++] = Math.sin(sim.tron1GaitIndex * 2 * Math.PI);
    sim.obs[offset++] = Math.cos(sim.tron1GaitIndex * 2 * Math.PI);
    for (const v of [freq, 0.5, 0.5, swing]) sim.obs[offset++] = v;
  }
}

function buildTron1PfObservation() {
  if (CONFIG.numObs !== 30 || CONFIG.numActions !== 6) throw new Error(`tron1_pf_30 requires 30/6; got ${CONFIG.numObs}/${CONFIG.numActions}`);
  buildTron1Observation(true);
}

function buildTron1SfObservation() {
  if (CONFIG.numObs !== 36 || CONFIG.numActions !== 8) throw new Error(`tron1_sf_36 requires 36/8; got ${CONFIG.numObs}/${CONFIG.numActions}`);
  buildTron1Observation(true);
}

function buildTron1WfObservation() {
  if (CONFIG.numObs !== 28 || CONFIG.numActions !== 8) throw new Error(`tron1_wf_28 requires 28/8; got ${CONFIG.numObs}/${CONFIG.numActions}`);
  buildTron1Observation(false);
}

function buildAgilityLowLevelObservation() {
  const imu = readImuSample();
  const rpy = imu.rpy;

  sim.obs.fill(0);
  sim.obs[0] = rpy[0];
  sim.obs[1] = rpy[1];
  sim.obs[2] = imu.angular[0] * input.imuAxisSigns.angular[0] * CONFIG.angVelScale;
  sim.obs[3] = imu.angular[1] * input.imuAxisSigns.angular[1] * CONFIG.angVelScale;
  sim.obs[4] = imu.angular[2] * input.imuAxisSigns.angular[2] * CONFIG.angVelScale;

  const jointOffset = 5;
  const velocityOffset = jointOffset + CONFIG.numActions;
  const actionOffset = velocityOffset + CONFIG.numActions;
  for (let i = 0; i < CONFIG.numActions; i += 1) {
    const src = CONFIG.dofReindex ? CONFIG.dofReindex[i] : i;
    sim.obs[jointOffset + i] = CONFIG.controlModes[src] === "velocity"
      ? 0
      : (jointQpos(src) - CONFIG.defaultAngles[src]) * CONFIG.dofPosScale;
    sim.obs[velocityOffset + i] = jointQvel(src) * CONFIG.dofVelScale;
    sim.obs[actionOffset + i] = sim.action[i];
  }
  const contactOffset = actionOffset + CONFIG.numActions;
  for (let i = 0; i < 4; i += 1) {
    sim.obs[contactOffset + i] = footContactState(i);
  }

  const commandOffset = 57 + 4 + 29;
  const mode = agilityModeOneHot();
  sim.obs[commandOffset] = clamp(sim.cmd[0], -2.5, 2.5);
  sim.obs[commandOffset + 1] = clamp(sim.cmd[1], -1.0, 1.0);
  sim.obs[commandOffset + 2] = clamp(sim.cmd[2], -2.5, 2.5);
  sim.obs[commandOffset + 3] = agilityJumpHeightCommand(mode);
  sim.obs[commandOffset + 4] = agilityLocomotionHeightCommand(mode);
  sim.obs[commandOffset + 5] = finiteNumber(CONFIG.defaultCommand[5], 0);
  sim.obs[commandOffset + 6] = mode[0];
  sim.obs[commandOffset + 7] = mode[1];
  sim.obs[commandOffset + 8] = mode[2];
}

function agilityModeOneHot() {
  const vx = Math.abs(sim.cmd[0]);
  const vy = Math.abs(sim.cmd[1]);
  const yaw = Math.abs(sim.cmd[2]);
  if (vx > 1.35 || vy > 0.55 || yaw > 1.2) return [0, 1, 0];
  if (vx > 0.2 || vy > 0.05 || yaw > 0.05) return [1, 0, 0];
  return [1, 0, 0];
}

function agilityJumpHeightCommand(mode) {
  if (mode?.[2] > 0.5) return finiteNumber(CONFIG.defaultCommand[3], 0.45);
  return finiteNumber(CONFIG.defaultCommand[3], 0);
}

function agilityLocomotionHeightCommand(mode) {
  if (mode?.[2] > 0.5) return 0;
  return finiteNumber(CONFIG.defaultCommand[4], 0.25);
}

function footContactState(index) {
  if (!sim.data || !sim.model) return 0;
  const targetBodyId = wheelContactBodyId(index);
  const bodyHints = ["FL_foot", "FR_foot", "RL_foot", "RR_foot"];
  const hint = bodyHints[index]?.toLowerCase() || "";
  for (let i = 0; i < (sim.data.ncon || 0); i += 1) {
    const contact = sim.data.contact?.[i];
    if (!contact) continue;
    const g1 = contact.geom1;
    const g2 = contact.geom2;
    const body1 = Number(sim.model.geom_bodyid?.[g1]);
    const body2 = Number(sim.model.geom_bodyid?.[g2]);
    if (targetBodyId >= 0 && (body1 === targetBodyId || body2 === targetBodyId)) {
      return 1;
    }
    const name1 = geomBodyName(g1).toLowerCase();
    const name2 = geomBodyName(g2).toLowerCase();
    if (name1.includes(hint) || name2.includes(hint)) {
      return 1;
    }
  }
  return 0;
}

function wheelContactBodyId(index) {
  if (!sim.model?.jnt_qposadr || !sim.model?.jnt_bodyid) return -1;
  const wheelActions = [];
  for (let actionIndex = 0; actionIndex < CONFIG.numActions; actionIndex += 1) {
    if (
      CONFIG.controlModes[actionIndex] === "velocity"
      || CONFIG.actuatorRoles[actionIndex] === "wheel"
      || jointGroup(CONFIG.jointOrder[actionIndex]) === "wheel"
    ) {
      wheelActions.push(actionIndex);
    }
  }
  const actionIndex = wheelActions[index];
  if (!Number.isInteger(actionIndex)) return -1;
  const expectedQposAddress = 7 + actionIndex;
  const jointCount = Number(sim.model.njnt || sim.model.jnt_qposadr.length || 0);
  for (let jointId = 0; jointId < jointCount; jointId += 1) {
    if (Number(sim.model.jnt_qposadr[jointId]) === expectedQposAddress) {
      return Number(sim.model.jnt_bodyid[jointId]);
    }
  }
  return -1;
}

function geomBodyName(geomId) {
  if (!sim.model || geomId == null || geomId < 0) return "";
  const bodyId = sim.model.geom_bodyid?.[geomId];
  if (bodyId == null || bodyId < 0) return "";
  if (typeof sim.model.getBodyName === "function") return sim.model.getBodyName(bodyId) || "";
  if (typeof sim.model.body === "function") return sim.model.body(bodyId)?.name || "";
  return "";
}

  // ── mjswan 四输入 RNN 的 `actor` 槽（117）——规格 = 上游 `examples/demo/main.py` + TS 运行时 ──
// `actor` 117 = projected_gravity(3) + joint_pos_rel(12) + joint_vel_rel(12) + last_action(12)，
// **每一项各自带 3 帧**、偏移 `(0,1,2)` = **新→旧**（dense 的 `history_length` 才是旧→新）；
// 其中 `last_action` 是 `history_interleaved` = **element-major**（每个关节自己的 3 帧相邻）：
//   `[a_t[0], a_{t-1}[0], a_{t-2}[0], a_t[1], a_{t-1}[1], a_{t-2}[1], …]`
// 其余项按 offset 序整段铺（`[g_t(3), g_{t-1}(3), g_{t-2}(3)]`）。**各 term 无缩放**（该组
// scale=1.0）。**reset 后首帧要填满每一槽**（上游 `HistoryObservation.needsPrime`：不许把
// 未训练的零当历史）。
//
// **为什么要 builder 自带状态**：现成的两种历史 layout（`frame_major_v1` 新→旧整帧 /
// `frame_major_oldest_first` 旧→新整帧）都表达不了"逐 term 稀疏 + 其中一项 element-major
// 交错"这张表 —— 硬套任一 layout 都是**静默错序**（跑得动、只是喂错）。与 Python 侧
// `adapters/mjlab/policy_acceptance.py::_MjswanActorHistory` **逐值同口径**：这类"两份实现
// 差一步"的缺陷不抛异常，只有同状态对拍才抓得到（同 `sensors/screen_frame.js` 那条纪律）。
//
// `command_`(16) / `is_init` / `adapt_hx`(128) **不在 obs 里**：它们由 app.js 按契约
// `onnx_slots` 的槽表**按位置**喂（onnx 张量名是导出器产物名，无意义）。
function buildMjswanVelocityObservation() {
  if (CONFIG.numObs !== 117 || CONFIG.numActions !== 12) {
    throw new Error(`go2_mjswan_velocity requires 117 observations and 12 actions; got ${CONFIG.numObs}/${CONFIG.numActions}`);
  }
  const imu = readImuSample();
  const a = CONFIG.numActions;
  const frame = new Float32Array(3 + 3 * a);
  let p = 0;
  for (let i = 0; i < 3; i += 1) frame[p++] = imu.gravity[i] * input.imuAxisSigns.gravity[i];
  for (let i = 0; i < a; i += 1) frame[p++] = jointQpos(i) - CONFIG.defaultAngles[i];
  for (let i = 0; i < a; i += 1) frame[p++] = jointQvel(i);
  for (let i = 0; i < a; i += 1) frame[p++] = sim.action[i];

  const kept = Array.isArray(sim.mjswanActorFrames) && sim.mjswanActorFrames.length === 3
    ? sim.mjswanActorFrames
    : null;
  // 首帧（含 reset 后）⇒ 三槽同帧；否则新帧入槽 0、旧帧后移（槽 0 = 最新）
  sim.mjswanActorFrames = kept ? [frame, kept[0], kept[1]] : [frame, frame.slice(), frame.slice()];
  const seq = sim.mjswanActorFrames;

  sim.obs.fill(0);
  let offset = 0;
  for (const f of seq) for (let i = 0; i < 3; i += 1) sim.obs[offset++] = f[i];          // gravity 9
  for (const base of [3, 3 + a]) {                                                        // q 36 + dq 36
    for (const f of seq) for (let i = 0; i < a; i += 1) sim.obs[offset++] = f[base + i];
  }
  for (let j = 0; j < a; j += 1) for (const f of seq) sim.obs[offset++] = f[3 + 2 * a + j]; // action 36（交错）
}

const OBSERVATION_BUILDERS = {
    microduck_61: buildMicroDuckObservation,
    zexw_53: buildZexWObservation,
    go1_playground_48: buildGo1PlaygroundObservation,
    himloco_45_hist6: buildGo1HimlocoObservation,
    quadrupedal_agility_ll: buildAgilityLowLevelObservation,
    s07_amp_cts: buildS07AmpCtsObservation,
    g1_amp_96: buildG1AmpObservation,
    go2w_53: buildGo2wLegsObservation,
    go2w_mjlab_legs_53: buildGo2wMjlabLegsObservation,
    go2w_rl_sdk_57: buildGo2wRlSdkObservation,
    go2w_himloco_57: buildGo2wHimlocoObservation,
    go2_rl_sdk_45: buildGo2RlSdkObservation,
    go2_motion_69: buildGo2MotionObservation,
    // mjswan 四输入 RNN 的 `actor` 槽（117 = 3×39，逐 term 新→旧 + last_action element-major
    // 交错，builder 自带 3 帧状态）；另三路（is_init / adapt_hx / command_）由 app.js 按
    // 契约 `onnx_slots` 的槽表按位置喂。
    go2_mjswan_velocity: buildMjswanVelocityObservation,
    g1_motion_154: buildG1Motion154Observation,
    g1_mjlab_velocity_98: buildG1MjlabVelocityObservation,
    g1_mjswan_locomotion: buildG1MjswanLocomotionObservation,
    g1_mjswan_balance: buildG1MjswanBalanceObservation,
    [WHEEL_LEG_GAIT_OBSERVATION]: buildWheelLegGaitObservation,
    [WHEEL_LEG_JUMP_OBSERVATION]: buildWheelLegJumpObservation,
    tron1_pf_30: buildTron1PfObservation,
    tron1_sf_36: buildTron1SfObservation,
    tron1_wf_28: buildTron1WfObservation,
    wuji_reorient_69: buildWujiReorientObservation,
    // PIE 深度跑酷：单帧本体 45 与 go2_rl_sdk_45 同序同缩放（合约按 1.0），
    // 另由 app.js 喂 proprio_history / depth_history / GRU memory。
    go2_pie_depth: buildGo2RlSdkObservation,
    // LainLab playground 技能族（2026-09-20）。rear-stand 45×1 与 go2_rl_sdk_45
    // **同序同缩放**（_stand_actor_frame 与 rl_sdk 帧逐字段一致），直接复用该 builder。
    lainlab_dream_45_hist6: buildLainlabDreamObservation,
    lainlab_gait_47_hist10: buildLainlabGaitObservation,
    lainlab_spring_47_hist10: buildLainlabSpringObservation,
    lainlab_handstand_48: buildLainlabHandstandObservation,
  };

  //: 已经报过"kind 没有 builder"的 kind（**只报一次**：每帧抛异常会把控制台刷爆，反而没人看见）。
  const _unbuiltKindsReported = new Set();

  // ── 声明式观测布局：**与 Python `policy_acceptance.py::frame_from_spec` 同一份规格** ──────
  // 契约里的 `observation_layout`（段列表）两侧共用。目的：布局从"每个 kind 一个 builder
  // （Python + 浏览器各写一份）"收成"一份规格、两侧消费"——因为**两份实现一致 ≠ 规格正确**
  // （实测过：缩放两侧一起错，逐维对拍照样全绿，策略却崩）。
  // 段词汇与 Python 逐字一致：zeros / ang_vel / gravity / euler / cmd / phase_sin / phase_cos /
  // joint_pos / joint_vel / action；缺省 width = 动作关节数、缺省 scale = 1（cmd 的 scale 可逐维）。
  //
  // **关节类段的语义筛选（2026-09-22 v0.58.0 补）**：原先关节段只能"按位置取前 N 个"
  // （`joint_pos` 永远是 `order[0..width)`），于是"轮位清零/按控制模式分列"这类**语义**
  // 只能靠"腿恰好排在前 12"的位置巧合表达 —— 一旦契约换序就静默错位。新增两个**语义**
  // 选项（与 Python `frame_from_spec` 逐字同规则）：
  //   · `"mode": "position" | "velocity"`：只取该控制模式的关节（取哪个关节由**控制模式**定，
  //      不是由位置定）；**必须显式声明 `width`**（= 选中关节数，不符即抛，fail-closed）；
  //   · `"zero_velocity_joints": true`：宽度不变，但**速度控制**的关节写 0
  //      （`go2w_rl_sdk_57` / `go2w_himloco_57` 的"轮位置清零"就是这一条）。
  function applyLayoutSpec(spec) {
    const imu = readImuSample();
    const signs = input.imuAxisSigns;
    const period = CONFIG.gaitPeriodS > 0 ? CONFIG.gaitPeriodS : 0.5;
    const elapsed = Number(sim.data && sim.data.time) || 0;
    const phase = (elapsed % period) / period;
    const angle = 2 * Math.PI * phase;
    sim.obs.fill(0);
    let offset = 0;
    const fixedWidth = { gravity: 3, euler: 3, phase_sin: 1, phase_cos: 1 };
    for (const seg of spec) {
      const source = seg && seg.source;
      const rawScale = seg && seg.scale !== undefined ? seg.scale : 1.0;
      // 宽度默认值按来源定（与 Python 同规则）：定宽来源固定；cmd = 命令维数；
      // 关节/动作类 = 动作关节数；zeros **必须显式给宽**（没有天然宽度，猜错就是静默错位）。
      let width;
      if (fixedWidth[source] !== undefined) width = fixedWidth[source];
      else if (source === "cmd") width = Number((seg && seg.width) || (CONFIG.cmdScale ? CONFIG.cmdScale.length : 3));
      else width = Number((seg && seg.width) || CONFIG.numActions);
      if (source === "zeros" && !(seg && seg.width)) {
        throw new Error("段 'zeros' 必须显式声明 width（零占位没有天然宽度）");
      }
      // 语义筛选：选中的关节下标（**按控制模式**，不是按位置）。`mode` 缺省 any ⇒ 全取。
      const rawMode = String((seg && seg.mode) || "any").toLowerCase();
      if (rawMode === "torque") {
        throw new Error("段 mode=\"torque\" 尚未实现（词汇表只区分 position/velocity）");
      }
      let jointIndex = null;
      if (rawMode === "position" || rawMode === "velocity") {
        const want = rawMode === "velocity";
        jointIndex = [];
        for (let i = 0; i < CONFIG.numActions; i += 1) {
          if ((CONFIG.controlModes[i] === "velocity") === want) jointIndex.push(i);
        }
        if (!(seg && seg.width)) {
          throw new Error(`段 ${source} 声明了 mode=${rawMode} 就必须显式给 width（= 选中关节数 ${jointIndex.length}）`);
        }
        if (jointIndex.length !== width) {
          throw new Error(
            `段 ${source} 的 width=${width} ≠ mode=${rawMode} 选中的关节数 ${jointIndex.length}（规格与契约不符）`,
          );
        }
      }
      const zeroVelocity = Boolean(seg && seg.zero_velocity_joints);
      const writeJoint = (i) => (jointIndex === null ? i : jointIndex[i]);
      const isZeroed = (i) => zeroVelocity && CONFIG.controlModes[i] === "velocity";
      // scale 除字面量外认 "@contract"：用契约声明的缩放字段（同一 kind 跨机型时各按各的契约）。
      let scaleList = null;
      if (rawScale === "@contract") {
        if (source === "ang_vel") scaleList = CONFIG.angVelScale;
        else if (source === "joint_pos") scaleList = CONFIG.dofPosScale;
        else if (source === "joint_vel") scaleList = CONFIG.dofVelScale;
        else if (source === "cmd") scaleList = CONFIG.cmdScale;
        else throw new Error(`段 ${source} 不支持 scale="@contract"（无对应契约字段）`);
      }
      const scaleAt = (i) => {
        const src = scaleList !== null ? scaleList : rawScale;
        // 注意：契约里的缩放数组在浏览器侧常是 **TypedArray**（如 `Float32Array`），
        // 而 `Array.isArray(Float32Array)` 是 **false** ⇒ 早期版本走到 `Number(typedArray)`
        // 得 `NaN`（JSON 里序列化成 `null`），把整条观测污染掉。故两种数组都要认。
        if (Array.isArray(src) || ArrayBuffer.isView(src)) return Number(src[i]);
        return Number(src);
      };
      switch (source) {
        case "zeros":
          for (let i = 0; i < width; i += 1) sim.obs[offset++] = 0;
          break;
        case "ang_vel":
          for (let i = 0; i < width; i += 1) sim.obs[offset++] = imu.angular[i] * signs.angular[i] * scaleAt(i);
          break;
        case "gravity":
          for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.gravity[i] * signs.gravity[i];
          break;
        case "euler":
          for (let i = 0; i < 3; i += 1) sim.obs[offset++] = imu.rpy ? imu.rpy[i] : 0;
          break;
        case "cmd":
          for (let i = 0; i < width; i += 1) sim.obs[offset++] = sim.cmd[i] * scaleAt(i);
          break;
        case "phase_sin":
          sim.obs[offset++] = Math.sin(angle);
          break;
        case "phase_cos":
          sim.obs[offset++] = Math.cos(angle);
          break;
        case "joint_pos":
          for (let i = 0; i < width; i += 1) {
            const j = writeJoint(i);
            sim.obs[offset++] = isZeroed(j) ? 0 : (jointQpos(j) - CONFIG.defaultAngles[j]) * scaleAt(i);
          }
          break;
        case "joint_vel":
          for (let i = 0; i < width; i += 1) sim.obs[offset++] = jointQvel(writeJoint(i)) * scaleAt(i);
          break;
        case "action":
          for (let i = 0; i < width; i += 1) sim.obs[offset++] = sim.action[i];
          break;
        default:
          throw new Error(`未知的观测段来源 ${source}（与 Python frame_from_spec 同一词汇表）`);
      }
    }
    return offset;
  }

  function buildObservation() {
    // **声明式布局优先**（与验收器同一条路）；没声明才退回每 kind 的 builder（增量迁移）。
    const layout = CONFIG.observationLayout;
    if (Array.isArray(layout) && layout.length) {
      const written = applyLayoutSpec(layout);
      if (CONFIG.numObs && written !== CONFIG.numObs) {
        throw new Error(`声明式布局段宽之和 ${written} ≠ numObs ${CONFIG.numObs}`);
      }
      return;
    }
    const kind = CONFIG.observationKind;
    const builder = OBSERVATION_BUILDERS[kind];
    if (builder) {
      builder();
      return;
    }
    // 未声明 kind（真空值）或 app.js 的缺省哨兵 "default" 都走通用 locomotion
    // 布局 —— 那是既有策略的既定默认，不是"未知"。哨兵必须放行：2026-09-20
    // 实测 go2-baseline-164k（demo 契约不声明 observation_kind）被 app.js 标成
    // "default"，此处误当"声明了具体 kind"抛错，页面每帧报错且策略拿不到观测。
    if (kind && kind !== "default") {
      // **声明了具体 kind 却没有 builder ⇒ 不静默回落**。
      // 回落会让"跑得起来但吃错观测"变成无声错误：页面照常出动作，只是布局是另一套
      // （如把 57 维轮足观测按 45 维四足布局填），从现象上完全看不出来。
      if (!_unbuiltKindsReported.has(kind)) {
        _unbuiltKindsReported.add(kind);
        throw new Error(
          `observation_kind=${kind} 没有对应的观测 builder，拒绝按通用布局静默代跑。`
          + `请在 observation_builders.js 里补 builder，或在策略声明里标 sim_ready:false（并进 sim_blocker 说明）。`
        );
      }
      buildLocomotionObservation();
      return;
    }
    buildLocomotionObservation();
  }

  return {
    OBSERVATION_BUILDERS,
    buildObservation,
    buildLocomotionObservation,
    setWheelLegGaitEnabled,
    wheelLegGaitRequested,
    wheelLegGaitCommandSpeed,
    advanceWheelLegGaitClock,
    updateGaitControl,
    isWheelLegGaitPolicy,
    resetMotionTime() { motionTime = 0; },
    getMotionTime() { return motionTime; },
    // Wuji reorient：清空 tag 系目标，下一次构建时重新采样（复位/换场景调用）。
    resetWujiGoal() { sim.wujiGoalQuat = null; sim.wujiHold = 0; },
  };
}
