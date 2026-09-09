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

// Go2/B2 四足 rl_sar/robot_lab 部署契约（45 维，12 位置动作）：
// ang_vel×0.25(body), gravity, cmd×1.0, (dof_pos-default)×1.0, dof_vel×0.05, 原始 action。
function buildGo2RlSdkObservation() {
  if (CONFIG.numObs !== 45 || CONFIG.numActions !== 12) {
    throw new Error(`go2_rl_sdk_45 requires 45 observations and 12 actions; got ${CONFIG.numObs}/${CONFIG.numActions}`);
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
  if (motionTime > loader.duration) motionTime = motionTime % loader.duration;
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
  // 训练相位钟 = 回合时间，每控制步推进 step_dt；站立只清零输出，时钟不停。
  sim.g1PhaseS += CONFIG.simulationDt * CONFIG.controlDecimation;
  const globalPhase = (sim.g1PhaseS % period) / period;
  const phaseSin = cmdNorm < 0.1 ? 0 : Math.sin(globalPhase * Math.PI * 2);
  const phaseCos = cmdNorm < 0.1 ? 0 : Math.cos(globalPhase * Math.PI * 2);
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

  const OBSERVATION_BUILDERS = {
    microduck_61: buildMicroDuckObservation,
    zexw_53: buildZexWObservation,
    quadrupedal_agility_ll: buildAgilityLowLevelObservation,
    s07_amp_cts: buildS07AmpCtsObservation,
    g1_amp_96: buildG1AmpObservation,
    go2w_53: buildGo2wLegsObservation,
    go2w_mjlab_legs_53: buildGo2wMjlabLegsObservation,
    go2w_rl_sdk_57: buildGo2wRlSdkObservation,
    go2_rl_sdk_45: buildGo2RlSdkObservation,
    go2_motion_69: buildGo2MotionObservation,
    g1_motion_154: buildG1Motion154Observation,
    g1_mjlab_velocity_98: buildG1MjlabVelocityObservation,
    g1_mjswan_locomotion: buildG1MjswanLocomotionObservation,
    g1_mjswan_balance: buildG1MjswanBalanceObservation,
    [WHEEL_LEG_GAIT_OBSERVATION]: buildWheelLegGaitObservation,
    [WHEEL_LEG_JUMP_OBSERVATION]: buildWheelLegJumpObservation,
  };

  function buildObservation() {
    const builder = OBSERVATION_BUILDERS[CONFIG.observationKind];
    if (builder) {
      builder();
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
  };
}
