// Train page: pick robot + trainable algorithm + hyperparams -> POST /api/runs,
// then poll the run + its event stream for a live log.
import { auth, robots, algorithms, billing, runs, ApiError } from "../shared/api.js?v=run-pagination-2";

const TERMINAL = new Set(["succeeded", "failed", "canceled"]);
const RUN_PAGE_SIZE = 50;
const RUN_LIST_REFRESH_MS = 10000;
const WHEEL_LEG_MORPHOLOGY = "wheel_leg_16dof_v1";
const TRAINING_CONTROL_MORPHOLOGIES = new Set(["quadruped_12dof", WHEEL_LEG_MORPHOLOGY]);
const ALGORITHM_ORDER = ["go2_rl_gym", "wheel_leg_rl_gym", "wheel_leg_gait_rl_gym", "wheel_leg_jump_rl_gym", "wheel_leg_high_speed", "wheel_leg_gait_hip_degradation", "amp_cts", "np3o", "quadrupedal_agility", "parkour", "omni_jump"];
const GPU_OPTIONS = [
  { spec: "4090D", label: "RTX 4090D  24G" },
  { spec: "v-48g", label: "RTX 4090  48G" },
  { spec: "v-32g-p", label: "RTX 4080(S)  32G" },
  { spec: "v-48g-350w", label: "RTX 3090  48G (350W)" },
  { spec: "3090", label: "RTX 3090  24G" },
  { spec: "3080Ti", label: "RTX 3080Ti  12G" },
  { spec: "3080", label: "RTX 3080  10G" },
  { spec: "3070Ti", label: "RTX 3070Ti  8G" },
  { spec: "3060", label: "RTX 3060  12G" },
  { spec: "5090-p", label: "RTX 5090  32G" },
  { spec: "h800", label: "H800  80G" },
  { spec: "A100", label: "A100  80G" },
  { spec: "A800", label: "A800  80G" },
  { spec: "A40", label: "A40   48G" },
  { spec: "A10", label: "A10   24G" },
  { spec: "A5000", label: "A5000 24G" },
];
const REWARD_FIELDS = [
  ["tracking_lin_vel", "tracking_lin_vel", 1.0],
  ["tracking_ang_vel", "tracking_ang_vel", 0.5],
  ["lin_vel_z", "lin_vel_z", -2.0],
  ["ang_vel_xy", "ang_vel_xy", -0.05],
  ["orientation", "orientation", -1.0],
  ["base_height", "base_height", -1.0],
  ["torques", "torques", -0.0002],
  ["dof_acc", "dof_acc", -2.5e-7],
  ["action_rate", "action_rate", -0.01],
  ["action_smoothness", "action_smoothness", -0.01],
  ["collision", "collision", -1.0],
];
const REWARD_LABELS = {
  collision: "机身/腿部碰撞惩罚（不含轮子正常触地）",
  zero_cmd_wheel_vel: "零指令轮速惩罚",
  zero_cmd_feet_contact: "零指令缺失足接触惩罚",
  zero_cmd_dof_pos: "零指令站立姿态惩罚",
  stand_nice: "非 Gait 零命令站姿惩罚",
  foot_stance_timeout: "足端接触周期异常惩罚",
  joint_velocity_overspeed: "关节速度超限惩罚",
};
const AMP_PARAM_FIELDS = [
  ["amp_reward_coefficient", "amp_reward_coefficient", "number", 0, 1000, "any"],
  ["amp_task_reward_lerp", "amp_task_reward_lerp", "number", 0, 1, "0.01"],
  ["amp_discriminator_hidden_dim_1", "amp_discriminator_hidden_dim_1", "number", 1, 8192, "1"],
  ["amp_discriminator_hidden_dim_2", "amp_discriminator_hidden_dim_2", "number", 1, 8192, "1"],
  ["amp_learning_rate", "amp_learning_rate", "number", 0.00000001, 1, "any"],
  ["amp_weight_decay", "amp_weight_decay", "number", 0, 1, "any"],
  ["amp_replay_buffer_size", "amp_replay_buffer_size", "number", 1, 10000000, "1"],
  ["amp_batch_size", "amp_batch_size", "number", 1, 1000000, "1"],
  ["amp_num_updates", "amp_num_updates", "number", 0, 1000, "1"],
  ["amp_gradient_penalty_coefficient", "amp_gradient_penalty_coefficient", "number", 0, 100000, "any"],
  ["amp_max_grad_norm", "amp_max_grad_norm", "number", 0.00000001, 100000, "any"],
  ["amp_normalizer_clip", "amp_normalizer_clip", "number", 0.00000001, 1000000, "any"],
  ["amp_reference_state_initialization_probability", "amp_reference_state_initialization_probability", "number", 0, 1, "0.01"],
  ["amp_randomize_reference_yaw", "amp_randomize_reference_yaw", "checkbox"],
  ["amp_reference_xy_jitter", "amp_reference_xy_jitter", "number", 0, 10, "any"],
  ["amp_reference_height_offset", "amp_reference_height_offset", "number", -2, 2, "any"],
  ["amp_contact_force_threshold", "amp_contact_force_threshold", "number", 0, 1000000, "any"],
];
const HIDDEN_REWARD_KEYS = new Set([
  "reflex_swing_pattern",
  "reflex_foot_clearance",
  "reflex_hip_recenter",
  "vertical_contact",
  "soft_landing",
  "diagonal_symmetry",
  "lr_torque_balance",
  "roll_orientation",
  "foot_stance_timeout",
  "velocity_overspeed",
  "_joint_velocity_limit",
  "_added_mass_min_kg",
  "_added_mass_max_kg",
]);
const METRIC_GROUPS = [
  ["overview", "概览"],
  ["reward", "奖励"],
  ["loss", "损失"],
  ["performance", "性能"],
  ["terrain", "地形"],
  ["all", "全部"],
];
const OVERVIEW_METRICS = [
  "Train/mean_reward", "Train/mean_teacher_reward", "Train/mean_student_reward",
  "Train/mean_episode_length", "Train/mean_teacher_episode_length", "Train/mean_student_episode_length",
  "Perf/total_fps", "Policy/mean_noise_std", "Loss/value_function", "Loss/surrogate",
  "Terrain/terrain_level_all", "Episode/rew_tracking_lin_vel", "Episode/rew_tracking_ang_vel",
];
const DEFAULT_METRIC_TAGS = [
  ...OVERVIEW_METRICS,
  "Loss/entropy", "Loss/latent", "Loss/load_balance", "Loss/learning_rate",
  "Perf/collection_time", "Perf/learning_time", "Perf/iteration_time", "Perf/eta_seconds",
  "Episode/rew_correct_base_height", "Episode/rew_torques", "Episode/rew_dof_power",
  "Episode/rew_action_rate", "Episode/rew_action_smoothness", "Episode/rew_collision",
];
const METRIC_LABELS = {
  "Train/mean_reward": "平均奖励",
  "Train/mean_teacher_reward": "Teacher 平均奖励",
  "Train/mean_student_reward": "Student 平均奖励",
  "Train/mean_episode_length": "平均回合长度",
  "Train/mean_teacher_episode_length": "Teacher 回合长度",
  "Train/mean_student_episode_length": "Student 回合长度",
  "Perf/total_fps": "训练速度 (steps/s)",
  "Perf/collection_time": "采样耗时 (s)",
  "Perf/learning_time": "学习耗时 (s)",
  "Perf/iteration_time": "单轮耗时 (s)",
  "Perf/total_time": "累计耗时 (s)",
  "Perf/eta_seconds": "预计剩余 (s)",
  "Perf/total_timesteps": "累计步数",
  "Policy/mean_noise_std": "动作噪声标准差",
  "Loss/value_function": "价值函数损失",
  "Loss/surrogate": "策略代理损失",
  "Loss/entropy": "熵损失",
  "Loss/latent": "潜变量损失",
  "Loss/load_balance": "专家负载均衡损失",
  "Loss/actor_load_balance": "Actor 负载均衡损失",
  "Loss/learning_rate": "学习率",
};
const URL_PARAMS = new URLSearchParams(location.search);

const el = {
  form: document.getElementById("createForm"),
  robotRow: document.getElementById("robotRow"),
  robotSelect: document.getElementById("robotSelect"),
  algoSelect: document.getElementById("algoSelect"),
  taskRow: document.getElementById("taskRow"),
  taskSelect: document.getElementById("taskSelect"),
  cloudGpuRow: document.getElementById("cloudGpuRow"),
  cloudGpuSelect: document.getElementById("cloudGpuSelect"),
  cloudGpuHint: document.getElementById("cloudGpuHint"),
  gpuCountRow: document.getElementById("gpuCountRow"),
  gpuCountSelect: document.getElementById("gpuCountSelect"),
  gpuCountHint: document.getElementById("gpuCountHint"),
  runContextNotice: document.getElementById("runContextNotice"),
  algorithmMeta: document.getElementById("algorithmMeta"),
  paramSummary: document.getElementById("paramSummary"),
  rewardGrid: document.getElementById("rewardGrid"),
  ampParamGrid: document.getElementById("ampParamGrid"),
  rewardSummary: document.getElementById("rewardSummary"),
  numEnvs: document.getElementById("numEnvs"),
  maxIterations: document.getElementById("maxIterations"),
  seed: document.getElementById("seed"),
  baseHeightTargetRow: document.getElementById("baseHeightTargetRow"),
  baseHeightTarget: document.getElementById("baseHeightTarget"),
  jointVelocityLimitRow: document.getElementById("jointVelocityLimitRow"),
  jointVelocityLimit: document.getElementById("jointVelocityLimit"),
  addedMassMinRow: document.getElementById("addedMassMinRow"),
  addedMassMin: document.getElementById("addedMassMin"),
  addedMassMaxRow: document.getElementById("addedMassMaxRow"),
  addedMassMax: document.getElementById("addedMassMax"),
  selfCollisions: document.getElementById("selfCollisions"),
  priceQuote: document.getElementById("priceQuote"),
  priceQuoteAmount: document.getElementById("priceQuoteAmount"),
  priceQuoteDetail: document.getElementById("priceQuoteDetail"),
  createButton: document.getElementById("createButton"),
  createError: document.getElementById("createError"),
  refreshRuns: document.getElementById("refreshRuns"),
  loadOlderRuns: document.getElementById("loadOlderRuns"),
  runListSummary: document.getElementById("runListSummary"),
  runList: document.getElementById("runList"),
  runTitle: document.getElementById("runTitle"),
  runMeta: document.getElementById("runMeta"),
  runStatus: document.getElementById("runStatus"),
  runBody: document.getElementById("runBody"),
  progressBar: document.getElementById("progressBar"),
  progressText: document.getElementById("progressText"),
  runHealthGrid: document.getElementById("runHealthGrid"),
  cancelButton: document.getElementById("cancelButton"),
  resumeButton: document.getElementById("resumeButton"),
  playLink: document.getElementById("playLink"),
  deploymentDownload: document.getElementById("deploymentDownload"),
  errorText: document.getElementById("errorText"),
  curveSelect: document.getElementById("curveSelect"),
  metricGroupTabs: document.getElementById("metricGroupTabs"),
  metricWindowSelect: document.getElementById("metricWindowSelect"),
  metricSmoothSelect: document.getElementById("metricSmoothSelect"),
  metricLatestGrid: document.getElementById("metricLatestGrid"),
  metricTagCount: document.getElementById("metricTagCount"),
  curveStatus: document.getElementById("curveStatus"),
  rewardCurve: document.getElementById("rewardCurve"),
  curveEmpty: document.getElementById("curveEmpty"),
  eventCount: document.getElementById("eventCount"),
  eventLog: document.getElementById("eventLog"),
  resumeDialog: document.getElementById("resumeDialog"),
  resumeForm: document.getElementById("resumeForm"),
  resumeCloseButton: document.getElementById("resumeCloseButton"),
  resumeCancelButton: document.getElementById("resumeCancelButton"),
  resumeConfirmButton: document.getElementById("resumeConfirmButton"),
  resumeSource: document.getElementById("resumeSource"),
  resumeCheckpoint: document.getElementById("resumeCheckpoint"),
  resumeSourceGpu: document.getElementById("resumeSourceGpu"),
  resumeGpuSelect: document.getElementById("resumeGpuSelect"),
  resumeGpuHint: document.getElementById("resumeGpuHint"),
  resumeGpuCountRow: document.getElementById("resumeGpuCountRow"),
  resumeGpuCountSelect: document.getElementById("resumeGpuCountSelect"),
  resumeIterations: document.getElementById("resumeIterations"),
  resumeIterationsLabel: document.getElementById("resumeIterationsLabel"),
  resumeNumEnvs: document.getElementById("resumeNumEnvs"),
  resumeSeed: document.getElementById("resumeSeed"),
  resumeBaseHeightTargetRow: document.getElementById("resumeBaseHeightTargetRow"),
  resumeBaseHeightTarget: document.getElementById("resumeBaseHeightTarget"),
  resumeJointVelocityLimitRow: document.getElementById("resumeJointVelocityLimitRow"),
  resumeJointVelocityLimit: document.getElementById("resumeJointVelocityLimit"),
  resumeAddedMassMinRow: document.getElementById("resumeAddedMassMinRow"),
  resumeAddedMassMin: document.getElementById("resumeAddedMassMin"),
  resumeAddedMassMaxRow: document.getElementById("resumeAddedMassMaxRow"),
  resumeAddedMassMax: document.getElementById("resumeAddedMassMax"),
  resumeSelfCollisions: document.getElementById("resumeSelfCollisions"),
  resumeRewardGrid: document.getElementById("resumeRewardGrid"),
  resumeAmpParamGrid: document.getElementById("resumeAmpParamGrid"),
  resumeError: document.getElementById("resumeError"),
  resumePriceQuote: document.getElementById("resumePriceQuote"),
  resumePriceQuoteAmount: document.getElementById("resumePriceQuoteAmount"),
  resumePriceQuoteDetail: document.getElementById("resumePriceQuoteDetail"),
};

let state = {
  robots: [],
  algorithms: [],
  runList: [],
  liveRuns: [],
  historyRuns: new Map(),
  historyOffset: 0,
  historyStarted: false,
  hasOlderRuns: false,
  loadingOlderRuns: false,
  runListRequestSeq: 0,
  preferredRun: null,
  selectedRunId: null,
  preferredAlgorithm: URL_PARAMS.get("algorithm") || "",
  preferredTask: URL_PARAMS.get("task") || "",
  preferredRunId: URL_PARAMS.get("run_id") || URL_PARAMS.get("job_id") || "",
  logLines: [],
  rewardSeries: emptyRewardSeries(),
  metricGroup: "overview",
  metricTick: 0,
  metricIteration: null,
  seenSeq: -1,
  seenMetricSeq: -1,
  pollTimer: null,
  listTimer: null,
  pollFailures: 0,
  resumeSourceRun: null,
  createRequest: null,
  resumeRequest: null,
  pricing: null,
  balanceRefreshAt: 0,
  balanceRefreshing: false,
  isAdmin: false,
};

init();

async function init() {
  const session = await auth.me().catch(() => ({ user: null }));
  state.isAdmin = session.user?.role === "admin";
  keepRobotPickerVisible();
  renderRewardFields();
  renderCurveOptions();
  el.form.addEventListener("submit", onCreate);
  el.refreshRuns.addEventListener("click", async () => {
    el.refreshRuns.disabled = true;
    try { await loadRuns(); } finally { el.refreshRuns.disabled = false; }
  });
  el.loadOlderRuns.addEventListener("click", loadOlderRuns);
  el.cancelButton.addEventListener("click", onCancel);
  el.resumeButton.addEventListener("click", openResumeDialog);
  el.resumeForm.addEventListener("submit", onResume);
  el.resumeCloseButton.addEventListener("click", closeResumeDialog);
  el.resumeCancelButton.addEventListener("click", closeResumeDialog);
  el.robotSelect.addEventListener("change", () => renderAlgorithmOptions());
  el.algoSelect.addEventListener("change", () => renderTaskOptions({ applyDefaults: true }));
  el.taskSelect.addEventListener("change", () => applySelectedTaskDefaults());
  el.cloudGpuSelect.addEventListener("change", updatePriceQuote);
  el.gpuCountSelect.addEventListener("change", updatePriceQuote);
  el.curveSelect.addEventListener("change", renderRewardCurve);
  el.metricWindowSelect.addEventListener("change", renderRewardCurve);
  el.metricSmoothSelect.addEventListener("change", renderRewardCurve);
  el.metricGroupTabs.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-metric-group]");
    if (!button) return;
    state.metricGroup = button.dataset.metricGroup;
    renderCurveOptions();
  });
  [el.numEnvs, el.maxIterations, el.seed, el.baseHeightTarget].forEach((input) => {
    input.addEventListener("input", updateParamSummary);
  });
  el.resumeIterations.addEventListener("input", updateResumePriceQuote);
  el.resumeGpuSelect.addEventListener("change", updateResumePriceQuote);
  el.resumeGpuCountSelect.addEventListener("change", updateResumePriceQuote);
  updateParamSummary();
  await loadPricing();
  await Promise.all([loadRobots(), loadAlgorithms(), loadRuns({ autoSelect: false }), loadGpuOptions()]);
  selectPreferredRobotForAlgorithm();
  renderAlgorithmOptions();
  renderTaskOptions({ applyDefaults: true });
  renderRunList();
  scheduleRunListRefresh();
  if (!state.preferredRunId && (state.preferredAlgorithm || state.preferredTask)) {
    return;
  }
  autoSelectRun();
}

function selectPreferredRobotForAlgorithm() {
  if (!state.preferredAlgorithm && !state.preferredTask) return;
  const algorithm = state.algorithms.find((item) => {
    const name = item?.manifest?.name || item?.name || "";
    return item.id === state.preferredAlgorithm
      || name === state.preferredAlgorithm
      || normalizedTasks(item).some((task) => task.id === state.preferredTask);
  });
  if (!algorithm) return;
  const allTasks = normalizedTasks(algorithm);
  const preferredTasks = allTasks.filter((task) => task.id === state.preferredTask);
  const tasks = preferredTasks.length ? preferredTasks : allTasks;
  const current = state.robots.find((robot) => robot.id === el.robotSelect.value);
  if (current && tasks.some((task) => taskCompatible(task, algorithm, current))) return;
  const compatibleRobot = state.robots.find((robot) =>
    tasks.some((task) => taskCompatible(task, algorithm, robot))
  );
  if (compatibleRobot) el.robotSelect.value = compatibleRobot.id;
}

async function loadRobots() {
  try {
    state.robots = await robots.list();
  } catch { state.robots = []; }
  el.robotSelect.innerHTML = state.robots.length
    ? state.robots.map((r) => `<option value="${r.id}">${escapeHtml(r.name || r.id)}</option>`).join("")
    : `<option value="">无可用机器人</option>`;
  renderAlgorithmOptions();
}

async function loadAlgorithms() {
  try {
    state.algorithms = await algorithms.list();
  } catch { state.algorithms = []; }
  renderAlgorithmOptions();
}

async function loadPricing() {
  try {
    state.pricing = await billing.pricing();
  } catch {
    state.pricing = null;
  }
  updatePriceQuote();
}

async function loadGpuOptions() {
  if (!el.cloudGpuRow) return;
  const allowed = new Set(state.pricing?.allowed_gpu_specs || Object.keys(state.pricing?.prices_cents_hr || {}));
  const visibleGpus = GPU_OPTIONS.filter((gpu) => allowed.has(gpu.spec));
  el.cloudGpuRow.style.display = "";
  const defaultSpec = state.pricing?.default_gpu_spec || "";
  const opts = [`<option value="">默认${defaultSpec ? `（${escapeHtml(defaultSpec)}）` : "（配置文件指定）"}</option>`];
  for (const g of visibleGpus) {
    opts.push(`<option value="${escapeHtml(g.spec)}">${escapeHtml(g.label)}</option>`);
  }
  el.cloudGpuSelect.innerHTML = opts.join("");
  renderGpuCountOptions(Number(el.gpuCountSelect?.value) || 1);
  renderResumeGpuOptions();
  if (el.cloudGpuHint) el.cloudGpuHint.textContent = "（按需分配）";
  updatePriceQuote();
}

function renderResumeGpuOptions(preferredSpec = "") {
  if (!el.resumeGpuSelect) return;
  const configured = state.pricing?.allowed_gpu_specs || Object.keys(state.pricing?.prices_cents_hr || {});
  const allowed = new Set(configured);
  const visible = GPU_OPTIONS.filter((gpu) => allowed.has(gpu.spec));
  const defaultSpec = state.pricing?.default_gpu_spec || "";
  if (!visible.length) {
    const fallback = preferredSpec || defaultSpec;
    el.resumeGpuSelect.innerHTML = fallback
      ? `<option value="${escapeHtml(fallback)}">${escapeHtml(fallback)}</option>`
      : `<option value="">平台默认</option>`;
    return;
  }
  el.resumeGpuSelect.innerHTML = visible
    .map((gpu) => `<option value="${escapeHtml(gpu.spec)}">${escapeHtml(gpu.label)}</option>`)
    .join("");
  const selected = visible.some((gpu) => gpu.spec === preferredSpec)
    ? preferredSpec
    : (visible.some((gpu) => gpu.spec === defaultSpec) ? defaultSpec : visible[0].spec);
  el.resumeGpuSelect.value = selected;
}

function allowedGpuCounts(task, algo = selectedAlgorithm()) {
  const providerCounts = new Set(
    (state.pricing?.allowed_gpu_counts || [1]).map((value) => Number(value)),
  );
  const capabilities = task?.capabilities || algo?.manifest?.capabilities || {};
  const maxCount = capabilities.multi_gpu === true
    ? Math.max(1, Number(capabilities.max_gpu_count) || 1)
    : 1;
  return [1, 2, 4].filter((count) => count <= maxCount && providerCounts.has(count));
}

function renderGpuCountOptions(preferredCount = 1, { resume = false, task = selectedTask(), algo = selectedAlgorithm() } = {}) {
  const row = resume ? el.resumeGpuCountRow : el.gpuCountRow;
  const select = resume ? el.resumeGpuCountSelect : el.gpuCountSelect;
  if (!row || !select) return;
  const counts = allowedGpuCounts(task, algo);
  const available = counts.length ? counts : [1];
  select.innerHTML = available
    .map((count) => `<option value="${count}">${count} 卡</option>`)
    .join("");
  const requested = Number(preferredCount) || 1;
  select.value = String(available.includes(requested) ? requested : 1);
  row.hidden = available.length <= 1;
}

function renderAlgorithmOptions() {
  if (!el.algoSelect) return;
  keepRobotPickerVisible();
  const robot = state.robots.find((r) => r.id === el.robotSelect.value);
  const ready = state.algorithms.filter((a) => {
    if (a.status !== "ready") return false;
    return normalizedTasks(a).some((task) => taskCompatible(task, a, robot));
  }).sort((a, b) => algorithmSortKey(a) - algorithmSortKey(b));
  const previous = el.algoSelect.value;
  el.algoSelect.innerHTML = ready.length
    ? ready.map((a) => `<option value="${a.id}">${escapeHtml(readableAlgorithmName(a))} v${escapeHtml(a.version || "")}</option>`).join("")
    : `<option value="">暂无兼容的可训练算法，请先在算法页查看</option>`;
  const current = ready.find((a) => a.id === previous);
  const preferred = ready.find((a) => {
    const name = (a.manifest && a.manifest.name) || a.name || "";
    return a.id === state.preferredAlgorithm || name === state.preferredAlgorithm;
  });
  const selected = current || preferred || ready[0];
  if (selected) el.algoSelect.value = selected.id;
  renderAlgorithmMeta();
  renderTaskOptions({ applyDefaults: true });
}

function keepRobotPickerVisible() {
  if (el.robotRow) el.robotRow.hidden = false;
}

function normalizedTasks(algo) {
  const tasks = Array.isArray(algo?.manifest?.tasks) ? algo.manifest.tasks : [];
  if (tasks.length) return tasks;
  return [{
    id: "default",
    name: algo?.manifest?.name || algo?.name || "默认任务",
    description: algo?.manifest?.description || "",
    compatible_robots: algo?.manifest?.compatible_robots || [],
    default_hyperparams: {},
    reward_scales: {},
    contract: algo?.manifest?.contract || {},
    resolved_default_hyperparams: algo?.manifest?.resolved_default_hyperparams || {},
  }];
}

function taskCompatible(task, algo, robot) {
  const morphology = robot?.morphology || "";
  const compatible = task.compatible_robots?.length ? task.compatible_robots : (algo?.manifest?.compatible_robots || []);
  if (compatible.length && !compatible.includes(morphology)) return false;
  if (task.allow_uploaded_robots === true) return true;
  const allowedAssets = Array.isArray(task.compatible_robot_assets)
    ? task.compatible_robot_assets.map((asset) => String(asset || "").trim().toLowerCase()).filter(Boolean)
    : [];
  if (!allowedAssets.length) return true;
  const asset = robotAssetName(robot);
  return Boolean(asset && allowedAssets.includes(asset));
}

function robotAssetName(robot) {
  return String(robot?.urdf_ref || "")
    .replaceAll("\\", "/")
    .replace(/^\/+/, "")
    .split("/", 1)[0]
    .trim()
    .toLowerCase();
}

function selectedAlgorithm() {
  return state.algorithms.find((a) => a.id === el.algoSelect.value);
}

function selectedRobot() {
  return state.robots.find((robot) => robot.id === el.robotSelect.value);
}

function supportsTrainingControls(robot) {
  return TRAINING_CONTROL_MORPHOLOGIES.has(robot?.morphology || "");
}

function syncRobotTrainingControls() {
  const robot = selectedRobot();
  const configurable = supportsTrainingControls(robot);
  el.baseHeightTargetRow.hidden = !configurable;
  el.jointVelocityLimitRow.hidden = !configurable;
  el.addedMassMinRow.hidden = !configurable;
  el.addedMassMaxRow.hidden = !configurable;
  if (configurable && el.baseHeightTargetRow.dataset.robotId !== robot.id) {
    const configuredHeight = Number(robot?.control_defaults?.base_height_target);
    el.baseHeightTarget.value = Number.isFinite(configuredHeight)
      ? String(configuredHeight)
      : "0.45";
    el.baseHeightTargetRow.dataset.robotId = robot.id;
  }
}

function selectedTask() {
  const algo = selectedAlgorithm();
  return normalizedTasks(algo).find((task) => task.id === el.taskSelect.value);
}

function renderTaskOptions({ applyDefaults = false } = {}) {
  if (!el.taskSelect) return;
  const algo = selectedAlgorithm();
  const robot = state.robots.find((r) => r.id === el.robotSelect.value);
  const tasks = normalizedTasks(algo).filter((task) => taskCompatible(task, algo, robot));
  el.taskRow.hidden = tasks.length <= 1;
  const previous = el.taskSelect.value;
  el.taskSelect.innerHTML = tasks.length
    ? tasks.map((task) => `<option value="${escapeHtml(task.id || "default")}">${escapeHtml(task.name || task.id || "默认任务")}</option>`).join("")
    : `<option value="">暂无兼容任务</option>`;
  const current = tasks.find((task) => task.id === previous);
  const preferred = tasks.find((task) => task.id === state.preferredTask);
  const trainable = tasks.find((task) => task.capabilities?.train !== false);
  const selected = current || preferred || trainable || tasks[0];
  if (selected) el.taskSelect.value = selected.id;
  renderGpuCountOptions();
  syncRobotTrainingControls();
  renderAlgorithmMeta();
  if (applyDefaults) applySelectedTaskDefaults();
}

function applySelectedTaskDefaults() {
  const task = selectedTask();
  if (!task) return;
  renderGpuCountOptions(Number(el.gpuCountSelect?.value) || 1);
  const defaults = resolvedTaskDefaults(task);
  if (Number.isFinite(Number(defaults.num_envs))) el.numEnvs.value = Number(defaults.num_envs);
  if (Number.isFinite(Number(defaults.max_iterations))) el.maxIterations.value = Number(defaults.max_iterations);
  if (Number.isFinite(Number(defaults.seed))) el.seed.value = Number(defaults.seed);
  if (Number.isFinite(Number(defaults.joint_velocity_limit))) {
    el.jointVelocityLimit.value = Number(defaults.joint_velocity_limit);
  }
  if (Number.isFinite(Number(defaults.added_mass_min_kg))) {
    el.addedMassMin.value = Number(defaults.added_mass_min_kg);
  }
  if (Number.isFinite(Number(defaults.added_mass_max_kg))) {
    el.addedMassMax.value = Number(defaults.added_mass_max_kg);
  }
  renderRewardFields(rewardScalesForTask(task));
  renderAmpInputs(el.ampParamGrid, defaults);
  updateParamSummary();
  updateRewardSummary();
  renderAlgorithmMeta();
}

function ampFieldsForValues(values) {
  const source = plainObject(values) ? values : {};
  return AMP_PARAM_FIELDS.filter(([key]) => Object.prototype.hasOwnProperty.call(source, key));
}

function renderAmpInputs(container, values, overrides = {}) {
  if (!container) return;
  const source = { ...(plainObject(values) ? values : {}), ...(plainObject(overrides) ? overrides : {}) };
  const fields = ampFieldsForValues(source);
  container.hidden = fields.length === 0;
  container.innerHTML = fields.map(([key, label, type, min, max, step]) => {
    const value = source[key];
    if (type === "checkbox") {
      return `<label class="amp-field amp-toggle"><span>${escapeHtml(label)}</span><input type="checkbox" data-amp-key="${escapeHtml(key)}" ${value ? "checked" : ""} /></label>`;
    }
    const rendered = Number.isFinite(Number(value)) ? String(value) : "";
    return `<label class="amp-field"><span>${escapeHtml(label)}</span><input class="field" type="number" data-amp-key="${escapeHtml(key)}" min="${min}" max="${max}" step="${step}" value="${escapeHtml(rendered)}" /></label>`;
  }).join("");
}

function collectAmpInputs(container) {
  const result = {};
  if (!container || container.hidden) return result;
  container.querySelectorAll("[data-amp-key]").forEach((input) => {
    const key = input.dataset.ampKey;
    if (!key) return;
    result[key] = input.type === "checkbox" ? input.checked : Number(input.value);
  });
  return result;
}

function renderAlgorithmMeta() {
  if (!el.algorithmMeta) return;
  const algo = selectedAlgorithm();
  const task = selectedTask();
  if (!algo) {
    el.algorithmMeta.className = "algorithm-meta";
    el.algorithmMeta.innerHTML = "";
    return;
  }
  const caps = algo.manifest?.capabilities || {};
  const deployment = String(caps.deployment || (caps.sim2sim === false ? "partial" : "experimental")).toLowerCase();
  const deploymentText = algorithmStatusLabel(algo, deployment);
  const tasks = normalizedTasks(algo);
  const defaults = resolvedTaskDefaults(task);
  const rewardScales = rewardScalesForTask(task);
  const taskName = task?.name || task?.id || "默认任务";
  const description = task?.description || algo.manifest?.description || "";
  const defaultText = [
    Number.isFinite(Number(defaults.num_envs)) ? `${Number(defaults.num_envs)} envs` : "",
    Number.isFinite(Number(defaults.max_iterations)) ? `${Number(defaults.max_iterations)} iter` : "",
    Number.isFinite(Number(defaults.seed)) ? `seed ${Number(defaults.seed)}` : "",
    defaults.preset ? `${defaults.preset} preset` : "",
  ].filter(Boolean).join(" · ");
  el.algorithmMeta.className = "algorithm-meta visible";
  el.algorithmMeta.innerHTML = `
    <div class="algorithm-meta-head">
      <span class="algorithm-meta-title">${escapeHtml(readableAlgorithmName(algo))} / ${escapeHtml(taskName)}</span>
      <span class="algorithm-meta-badge ${escapeHtml(deployment)}">${escapeHtml(deploymentText)}</span>
    </div>
    <div class="algorithm-meta-text">${escapeHtml(compactDescription(description))}</div>
    <div class="algorithm-meta-pills">
      ${metaPill(`${tasks.length} 个任务`, true)}
      ${metaPill(caps.resume ? "支持续训" : "单次训练", caps.resume === true)}
      ${metaPill(caps.sim2sim ? "支持 Sim2Sim" : "仿真适配中", caps.sim2sim !== false)}
      ${metaPill(caps.pretrained_policy ? "含预训练权重" : "训练后生成权重", caps.pretrained_policy === true)}
      ${metaPill(`${Object.keys(rewardScales || {}).length || REWARD_FIELDS.length} 项奖励`, true)}
    </div>
    <div class="algorithm-meta-text">默认参数来自算法任务配置：${escapeHtml(defaultText || "平台默认配置")}</div>
    <div class="algorithm-meta-text">奖励预览：${escapeHtml(rewardPreview(rewardScales))}</div>
  `;
}

function metaPill(label, ok) {
  return `<span class="algorithm-meta-pill ${ok ? "ok" : "warn"}">${escapeHtml(label)}</span>`;
}

function compactDescription(value) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length > 138 ? `${text.slice(0, 135)}...` : text;
}

function readableAlgorithmName(algo) {
  const name = (algo.manifest && algo.manifest.name) || algo.name || algo.id;
  return readableAlgorithmLabel(name);
}

function readableAlgorithmLabel(value) {
  const raw = String(value || "");
  const key = raw.toLowerCase().replace(/^alg_builtin_/, "").replace(/[\s-]+/g, "_");
  const mapping = {
    go2_rl_gym: "Go2 RL Gym",
    wheel_leg_rl_gym: "Wheel-Leg MoE-CTS",
    wheel_leg_gait_rl_gym: "Wheel-Leg Gait MoE-CTS",
    wheel_leg_gait_hip_degradation: "Wheel-Leg Gait Full-Torque MoE-CTS",
    wheel_leg_jump_rl_gym: "Wheel-Leg Jump MoE-CTS",
    wheel_leg_high_speed: "Wheel-Leg High-Speed",
    amp_cts: "P1 · AMP-CTS",
    np3o: "NP3O",
    quadrupedal_agility: "Quadrupedal Agility",
    parkour: "Robot Parkour",
    omni_jump: "Omni-Jump",
  };
  mapping.amp_cts = "W1W AMP MoE-CTS";
  return mapping[key] || raw || "-";
}

function algorithmStatusLabel(algo, deployment) {
  const name = String(algo?.manifest?.name || algo?.name || algo?.id || "").toLowerCase();
  const labels = {
    ready: "可训练 · 已验证",
    partial: "可训练 · 持续优化",
    experimental: "开放体验",
    blocked: "开发中",
    invalid: "暂未开放",
  };
  return labels[String(deployment || "").toLowerCase()] || "可训练";
}

function algorithmSortKey(algo) {
  const name = ((algo.manifest && algo.manifest.name) || algo.name || "").toLowerCase();
  const index = ALGORITHM_ORDER.indexOf(name);
  return index >= 0 ? index : ALGORITHM_ORDER.length;
}

function renderRewardInputs(container, rewardScales = null) {
  const fields = rewardFieldsForScales(rewardScales);
  container.innerHTML = fields.map(({ key, label, value }) => {
    const rendered = formatRewardValue(value);
    return `
    <label class="reward-field">
      <span>${escapeHtml(label)}</span>
      <input class="field" type="number" step="any" data-reward="${escapeHtml(key)}" data-default="${escapeHtml(rendered)}" value="${escapeHtml(rendered)}" />
    </label>
  `;
  }).join("");
}

function renderRewardFields(rewardScales = null) {
  renderRewardInputs(el.rewardGrid, rewardScales);
  el.rewardGrid.querySelectorAll("input[data-reward]").forEach((input) => {
    input.addEventListener("input", updateRewardSummary);
  });
  updateRewardSummary();
}

function rewardScalesForTask(task) {
  const defaults = resolvedTaskDefaults(task);
  const taskRewards = plainObject(task?.reward_scales) ? task.reward_scales : {};
  const defaultRewards = plainObject(defaults.reward_scales) ? defaults.reward_scales : {};
  return visibleRewardScales(Object.keys(taskRewards).length ? taskRewards : defaultRewards);
}

function visibleRewardScales(rewardScales) {
  return Object.fromEntries(
    Object.entries(rewardScales || {}).filter(([key]) => !HIDDEN_REWARD_KEYS.has(key)),
  );
}

function rewardScalesForResume(run) {
  const algorithm = state.algorithms.find((item) => item.id === run?.algorithm_id);
  const task = normalizedTasks(algorithm).find((item) => item.id === run?.task_id);
  return visibleRewardScales({
    ...rewardScalesForTask(task),
    ...(plainObject(run?.hyperparams?.reward_scales) ? run.hyperparams.reward_scales : {}),
  });
}

function resolvedTaskDefaults(task) {
  const resolved = plainObject(task?.resolved_default_hyperparams) ? task.resolved_default_hyperparams : null;
  const legacy = plainObject(task?.default_hyperparams) ? task.default_hyperparams : {};
  return resolved || legacy || {};
}

function rewardFieldsForScales(rewardScales) {
  const fallback = REWARD_FIELDS.map(([key, label, value]) => ({ key, label, value: num(value, 0) }));
  if (!plainObject(rewardScales) || !Object.keys(rewardScales).length) return fallback;
  const fallbackByKey = new Map(fallback.map((field) => [field.key, field]));
  return Object.entries(rewardScales)
    .filter(([key]) => key)
    .map(([key, raw]) => {
      const known = fallbackByKey.get(key);
      return {
        key,
        label: known?.label || REWARD_LABELS[key] || key,
        value: num(raw, known?.value ?? 0),
      };
    });
}

function rewardPreview(rewardScales) {
  if (!plainObject(rewardScales) || !Object.keys(rewardScales).length) return "平台默认奖励";
  return Object.entries(rewardScales)
    .slice(0, 4)
    .map(([key, value]) => `${key}=${formatRewardValue(value)}`)
    .join(" / ");
}

function renderCurveOptions() {
  const previous = el.curveSelect.value;
  const tags = metricTagsForGroup(state.metricGroup);
  el.curveSelect.innerHTML = tags
    .map((tag) => `<option value="${escapeHtml(tag)}">${escapeHtml(metricLabel(tag))}</option>`)
    .join("");
  el.curveSelect.value = tags.includes(previous) ? previous : (tags[0] || "");
  el.metricGroupTabs.querySelectorAll("button[data-metric-group]").forEach((button) => {
    button.classList.toggle("active", button.dataset.metricGroup === state.metricGroup);
  });
  renderRewardCurve();
}

function updateParamSummary() {
  const envs = Math.max(1, parseInt(el.numEnvs.value, 10) || 64);
  const iterations = Math.max(1, parseInt(el.maxIterations.value, 10) || 1000);
  const seed = parseInt(el.seed.value, 10) || 1;
  const height = supportsTrainingControls(selectedRobot())
    ? ` · ${num(el.baseHeightTarget.value, 0.45).toFixed(2)} m`
    : "";
  el.paramSummary.textContent = `${envs} envs · ${iterations} iter · seed ${seed}${height}`;
  updatePriceQuote();
}

function liveBillingQuote(gpuSpec = "", gpuCount = 1) {
  const pricing = state.pricing;
  if (!pricing?.enabled) return null;
  const effectiveSpec = gpuSpec || pricing.default_gpu_spec || "";
  const count = Math.max(1, Number(gpuCount) || 1);
  if (pricing.price_mode === "provider_actual") {
    return { providerActual: true, gpuSpec: effectiveSpec, gpuCount: count };
  }
  const rate = Number(pricing.prices_cents_hr?.[effectiveSpec]);
  if (!effectiveSpec || !Number.isFinite(rate) || rate <= 0) return null;
  const reserveSeconds = Math.max(0, Number(pricing.startup_reserve_seconds) || 0);
  return {
    hourlyCents: rate * count,
    reserveCents: Math.ceil(rate * count * reserveSeconds / 3600),
    gpuSpec: effectiveSpec,
    gpuCount: count,
  };
}

function formatYuan(cents) {
  return `¥${(Math.max(0, Number(cents) || 0) / 100).toFixed(2)}`;
}

function updatePriceQuote() {
  const quote = liveBillingQuote(
    el.cloudGpuSelect?.value || "",
    Number(el.gpuCountSelect?.value) || 1,
  );
  el.priceQuote.hidden = !quote;
  if (!quote) {
    el.createButton.textContent = "创建并开始训练";
    return;
  }
  if (quote.providerActual) {
    el.priceQuoteAmount.textContent = "按云端实际价";
    el.priceQuoteDetail.textContent = `${quote.gpuCount} 卡实例分配后确认真实小时价，按实际占用时间扣费；余额不足自动停止`;
  } else {
    el.priceQuoteAmount.textContent = `${formatYuan(quote.hourlyCents)} / 小时`;
    el.priceQuoteDetail.textContent = `${quote.gpuSpec} × ${quote.gpuCount} 卡 · 启动仅保留 ${formatYuan(quote.reserveCents)}，之后按实际 GPU 时间扣费；余额不足自动停止`;
  }
  el.createButton.textContent = "创建并开始训练";
}

function updateResumePriceQuote() {
  const source = state.resumeSourceRun;
  if (!source) {
    el.resumePriceQuote.hidden = true;
    el.resumeConfirmButton.textContent = "创建续训任务";
    return;
  }
  const quote = liveBillingQuote(
    el.resumeGpuSelect?.value || source.gpu_spec || "",
    Number(el.resumeGpuCountSelect?.value) || Number(source.gpu_count) || 1,
  );
  el.resumePriceQuote.hidden = !quote;
  if (!quote) {
    el.resumeConfirmButton.textContent = "创建续训任务";
    return;
  }
  if (quote.providerActual) {
    el.resumePriceQuoteAmount.textContent = "按云端实际价";
    el.resumePriceQuoteDetail.textContent = `${quote.gpuCount} 卡实例分配后确认真实小时价，按实际占用时间扣费；余额不足自动停止`;
  } else {
    el.resumePriceQuoteAmount.textContent = `${formatYuan(quote.hourlyCents)} / 小时`;
    el.resumePriceQuoteDetail.textContent = `${quote.gpuSpec} × ${quote.gpuCount} 卡 · 按实际 GPU 时间持续扣费，余额不足自动停止`;
  }
  el.resumeConfirmButton.textContent = "创建续训任务";
}

function updateRewardSummary() {
  const inputs = [...el.rewardGrid.querySelectorAll("input[data-reward]")];
  const changed = rewardOverrideCount(inputs);
  el.rewardSummary.textContent = changed ? `${changed} changed` : `${inputs.length} scales`;
}

function hasRewardOverrides() {
  return rewardOverrideCount() > 0;
}

function rewardOverrideCount(inputs = [...el.rewardGrid.querySelectorAll("input[data-reward]")]) {
  return inputs.filter((input) => num(input.value, 0) !== num(input.dataset.default, 0)).length;
}

function collectRewards() {
  return collectRewardInputs(el.rewardGrid);
}

function collectRewardInputs(container) {
  const rewards = {};
  container.querySelectorAll("input[data-reward]").forEach((input) => {
    const fallback = num(input.dataset.default, 0);
    rewards[input.dataset.reward] = num(input.value, fallback);
  });
  return rewards;
}

function formatRewardValue(value) {
  return String(num(value, 0));
}

function plainObject(value) {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function num(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function emptyRewardSeries() {
  return Object.fromEntries(DEFAULT_METRIC_TAGS.map((tag) => [tag, []]));
}

async function loadRuns({ autoSelect = true, showError = true } = {}) {
  const requestSeq = ++state.runListRequestSeq;
  let recentRuns;
  let activeRuns;
  try {
    [recentRuns, activeRuns] = await Promise.all([
      runs.list({ limit: RUN_PAGE_SIZE, offset: 0 }),
      runs.list({ active_only: true }),
    ]);
  } catch (err) {
    if (requestSeq !== state.runListRequestSeq) return false;
    renderRunListSummary(true);
    if (showError) {
      el.errorText.textContent = err instanceof ApiError ? err.message : "训练列表刷新失败，已保留上次结果";
    }
    return false;
  }

  if (requestSeq !== state.runListRequestSeq) return false;

  state.liveRuns = mergeRuns(activeRuns, recentRuns);
  if (!state.historyStarted) {
    state.historyOffset = recentRuns.length;
    state.hasOlderRuns = recentRuns.length === RUN_PAGE_SIZE;
  }
  for (const run of recentRuns) state.historyRuns.set(run.id, run);
  for (const run of state.liveRuns) {
    if (state.historyRuns.has(run.id)) state.historyRuns.set(run.id, run);
  }
  await ensurePreferredRun();
  if (requestSeq !== state.runListRequestSeq) return false;
  rebuildRunList();
  renderRunList();
  renderRunListSummary(false);
  renderLoadOlderRuns();
  if (autoSelect) autoSelectRun();
  return true;
}

async function ensurePreferredRun() {
  if (!state.preferredRunId) return;
  const live = state.liveRuns.find((run) => run.id === state.preferredRunId);
  if (live) {
    state.preferredRun = live;
    return;
  }
  if (state.preferredRun) return;
  try {
    state.preferredRun = await runs.get(state.preferredRunId);
  } catch {
    state.preferredRun = null;
  }
}

function mergeRuns(...sources) {
  const merged = new Map();
  for (const source of sources) {
    for (const run of source || []) {
      const current = merged.get(run.id);
      const currentUpdatedAt = Number(current?.updated_at || current?.created_at || 0);
      const nextUpdatedAt = Number(run.updated_at || run.created_at || 0);
      if (!current || nextUpdatedAt >= currentUpdatedAt) merged.set(run.id, run);
    }
  }
  return [...merged.values()];
}

function rebuildRunList() {
  const selected = state.runList.find((run) => run.id === state.selectedRunId);
  const merged = mergeRuns(
    [...state.historyRuns.values()],
    selected ? [selected] : [],
    state.preferredRun ? [state.preferredRun] : [],
    state.liveRuns,
  ).sort((a, b) => {
    const createdDelta = Number(b.created_at || 0) - Number(a.created_at || 0);
    return createdDelta || String(b.id).localeCompare(String(a.id));
  });
  const preferredIndex = merged.findIndex((run) => run.id === state.preferredRunId);
  if (preferredIndex > 0) merged.unshift(merged.splice(preferredIndex, 1)[0]);
  state.runList = merged;
}

async function loadOlderRuns() {
  if (state.loadingOlderRuns || !state.hasOlderRuns) return;
  state.loadingOlderRuns = true;
  renderLoadOlderRuns();
  try {
    const page = await runs.list({ limit: RUN_PAGE_SIZE, offset: state.historyOffset });
    for (const run of page) state.historyRuns.set(run.id, run);
    state.historyOffset += page.length;
    state.historyStarted = state.historyStarted || page.length > 0;
    state.hasOlderRuns = page.length === RUN_PAGE_SIZE;
    rebuildRunList();
    renderRunList();
    renderRunListSummary(false);
  } catch (err) {
    el.errorText.textContent = err instanceof ApiError ? err.message : "加载历史训练失败";
  } finally {
    state.loadingOlderRuns = false;
    renderLoadOlderRuns();
  }
}

function renderLoadOlderRuns() {
  if (!el.loadOlderRuns) return;
  el.loadOlderRuns.hidden = !state.hasOlderRuns;
  el.loadOlderRuns.disabled = state.loadingOlderRuns;
  el.loadOlderRuns.textContent = state.loadingOlderRuns ? "加载中" : "加载更早";
}

function scheduleRunListRefresh() {
  if (state.listTimer) clearTimeout(state.listTimer);
  state.listTimer = setTimeout(async () => {
    await loadRuns({ autoSelect: false, showError: false });
    scheduleRunListRefresh();
  }, RUN_LIST_REFRESH_MS);
}

function renderRunListSummary(refreshFailed = false) {
  if (!el.runListSummary) return;
  if (refreshFailed) {
    el.runListSummary.textContent = "刷新失败 · 显示上次结果";
    return;
  }
  const running = state.liveRuns.filter((run) => ["running", "evaluating"].includes(run.status)).length;
  const queued = state.liveRuns.filter((run) => run.status === "queued").length;
  el.runListSummary.textContent = `${running} 运行中 · ${queued} 排队`;
}

function renderRunList() {
  el.runList.innerHTML = "";
  const queuePositions = new Map(
    state.runList
      .filter((run) => run.status === "queued")
      .sort((a, b) => Number(a.created_at || 0) - Number(b.created_at || 0))
      .map((run, index) => [run.id, index + 1]),
  );
  for (const run of state.runList) {
    const visibleStatus = effectiveRunStatus(run);
    const li = document.createElement("li");
    li.className = "session-item" + (run.id === state.selectedRunId ? " active" : "");
    li.innerHTML = `
      <span class="s-body">
        <span class="s-title">${escapeHtml(displayRobotName(run))} / ${escapeHtml(displayAlgorithmName(run))}</span>
        <span class="s-sub">${escapeHtml(runSubText(run, queuePositions.get(run.id)))}</span>
      </span>
      <span class="status-badge ${visibleStatus}">${visibleStatus}</span>`;
    li.addEventListener("click", () => selectRun(run.id));
    el.runList.append(li);
  }
}

function autoSelectRun() {
  if (!state.runList.length) return;
  if (state.selectedRunId && state.runList.some((run) => run.id === state.selectedRunId)) return;
  const preferred = state.runList.find((run) => run.id === state.preferredRunId);
  const selected = preferred || state.runList[0];
  if (!preferred && (state.preferredAlgorithm || state.preferredTask)) return;
  selectRun(selected.id, { updateUrl: false });
}

function runSubText(run, queuePosition) {
  const parts = [displayTaskName(run), shortRunId(run.id)];
  if (queuePosition) parts.push(`队列 #${queuePosition}`);
  const playable = playablePolicy(run);
  if (run.latest_policy) {
    parts.push(`${playable ? "ONNX playable" : "ONNX unhealthy"} ${policyLabel(playable || run.latest_policy)}`);
    if (playable && run.latest_policy.id !== playable.id) {
      parts.push(`latest ${policyLabel(run.latest_policy)} unhealthy`);
    }
  }
  const stage = run.progress && run.progress.stage;
  if (stage && stage !== run.status) parts.push(stage);
  return parts.join(" / ");
}

function effectiveRunStatus(run) {
  if (run?.cancel_requested && !TERMINAL.has(run.status)) return "canceling";
  return run?.status || "unknown";
}

function robotName(id) {
  const r = state.robots.find((x) => x.id === id);
  return r ? r.name || id : id;
}

function displayRobotName(run) {
  return run?.robot_name || robotName(run?.robot_id);
}

function displayAlgorithmName(run) {
  return readableAlgorithmLabel(run?.algorithm_name || run?.algorithm_id || "-");
}

function displayTaskName(run) {
  return run?.task_name || run?.task_id || "default";
}

async function onCreate(e) {
  e.preventDefault();
  el.createError.textContent = "";
  if (!el.robotSelect.value || !el.algoSelect.value) {
    el.createError.textContent = "请选择机器人和可训练算法";
    return;
  }
  if (!el.taskSelect.value) {
    el.createError.textContent = "请选择算法 task";
    return;
  }
  const robot = selectedRobot();
  const configurable = supportsTrainingControls(robot);
  const baseHeightTarget = Number(el.baseHeightTarget.value);
  const jointVelocityLimit = Number(el.jointVelocityLimit.value);
  const addedMassMin = Number(el.addedMassMin.value);
  const addedMassMax = Number(el.addedMassMax.value);
  if (configurable && (!Number.isFinite(baseHeightTarget) || baseHeightTarget < 0.1 || baseHeightTarget > 1.5)) {
    el.createError.textContent = "目标机身高度必须在 0.10–1.50 m 之间";
    return;
  }
  if (configurable && (!Number.isFinite(jointVelocityLimit) || jointVelocityLimit < 0.1 || jointVelocityLimit > 100)) {
    el.createError.textContent = "腿部关节速度上限必须在 0.1-100 rad/s 之间";
    return;
  }
  if (configurable && (!Number.isFinite(addedMassMin) || !Number.isFinite(addedMassMax) || addedMassMin < -100 || addedMassMax > 100 || addedMassMin > addedMassMax)) {
    el.createError.textContent = "随机附加重量范围必须在 -100 到 100 kg 且下限不大于上限";
    return;
  }
  el.createButton.disabled = true;
  const hyperparams = {
    num_envs: Math.max(1, parseInt(el.numEnvs.value, 10) || 64),
    max_iterations: Math.max(1, parseInt(el.maxIterations.value, 10) || 1000),
    seed: parseInt(el.seed.value, 10) || 1,
    self_collisions: Number(el.selfCollisions?.value) === 0 ? 0 : 1,
    ...(configurable ? { joint_velocity_limit: jointVelocityLimit } : {}),
  };
  if (hasRewardOverrides()) {
    hyperparams.preset = "custom";
    hyperparams.reward_scales = collectRewards();
  }
  if (configurable) {
    hyperparams.reward_scales = {
      ...(hyperparams.reward_scales || {}),
      _joint_velocity_limit: jointVelocityLimit,
      _added_mass_min_kg: addedMassMin,
      _added_mass_max_kg: addedMassMax,
    };
    hyperparams.added_mass_min_kg = addedMassMin;
    hyperparams.added_mass_max_kg = addedMassMax;
  }
  Object.assign(hyperparams, collectAmpInputs(el.ampParamGrid));
  const payload = {
    robot_id: el.robotSelect.value,
    algorithm_id: el.algoSelect.value,
    task_id: el.taskSelect.value,
    hyperparams,
    gpu_spec: el.cloudGpuSelect?.value || "",
    gpu_count: Number(el.gpuCountSelect?.value) || 1,
  };
  if (configurable) payload.base_height_target = baseHeightTarget;
  const idempotencyKey = requestKey("createRequest", payload);
  try {
    const run = await runs.create(payload, idempotencyKey);
    replaceRun(run);
    selectRun(run.id);
    try {
      await loadRuns({ autoSelect: false });
      state.createRequest = null;
    } catch {
      el.createError.textContent = "训练已创建，任务列表稍后自动刷新";
    }
  } catch (err) {
    el.createError.textContent = err instanceof ApiError ? err.message : "创建失败";
  } finally {
    el.createButton.disabled = false;
  }
}

function selectRun(id, { updateUrl = true } = {}) {
  if (state.pollTimer) { clearTimeout(state.pollTimer); state.pollTimer = null; }
  state.selectedRunId = id;
  const selected = state.runList.find((run) => run.id === id);
  if (selected) renderRunContextNotice(selected);
  if (updateUrl) {
    const url = new URL(location.href);
    url.searchParams.set("run_id", id);
    history.replaceState(null, "", url);
  }
  state.logLines = [];
  state.rewardSeries = emptyRewardSeries();
  state.metricGroup = "overview";
  state.metricTick = 0;
  state.metricIteration = null;
  state.seenSeq = -1;
  state.seenMetricSeq = -1;
  state.pollFailures = 0;
  el.eventLog.innerHTML = "";
  el.eventCount.textContent = "0";
  el.runBody.style.display = "block";
  renderCurveOptions();
  renderRunList();
  poll();
}

function renderRunContextNotice(run) {
  if (!el.runContextNotice) return;
  if (!run) {
    el.runContextNotice.classList.add("hidden");
    el.runContextNotice.textContent = "";
    return;
  }
  const runLabel = `${displayAlgorithmName(run)} / ${displayTaskName(run)}`;
  el.runContextNotice.className = "run-context-notice detached";
  el.runContextNotice.innerHTML = `<strong>当前查看</strong><span>${escapeHtml(runLabel)}；左侧新建表单保持当前选择。</span>`;
}

async function poll() {
  const id = state.selectedRunId;
  if (!id) return;
  let run, events, metrics;
  try {
    [run, events, metrics] = await Promise.all([
      runs.get(id),
      runs.events(id, state.seenSeq >= 0 ? state.seenSeq : undefined).catch(() => null), // events endpoint may lag; tolerate
      runs.metrics(id, state.seenMetricSeq >= 0 ? state.seenMetricSeq : undefined).catch(() => null),
    ]);
  } catch (err) {
    if (state.selectedRunId !== id) return;
    state.pollFailures += 1;
    el.errorText.textContent = err instanceof ApiError
      ? `${err.message}，正在重试`
      : "实时连接中断，正在重试";
    const retryDelay = Math.min(10000, 2000 * (2 ** Math.min(3, state.pollFailures - 1)));
    schedulePoll(retryDelay);
    return;
  }
  if (state.selectedRunId !== id) return; // user switched away mid-request
  state.pollFailures = 0;
  renderRun(run);
  if (events) ingestEvents(events);
  if (metrics) ingestMetricEvents(metrics);

  replaceRun(run);
  void refreshLiveBalance(TERMINAL.has(run.status));

  if (!TERMINAL.has(run.status)) {
    schedulePoll();
  }
}

function schedulePoll(delay = 2000) {
  state.pollTimer = setTimeout(poll, delay);
}

function replaceRun(run) {
  const liveIndex = state.liveRuns.findIndex((item) => item.id === run.id);
  if (liveIndex >= 0) state.liveRuns[liveIndex] = run;
  if (state.historyRuns.has(run.id)) state.historyRuns.set(run.id, run);
  if (state.preferredRun?.id === run.id) state.preferredRun = run;
  const index = state.runList.findIndex((item) => item.id === run.id);
  if (index < 0) {
    state.runList.unshift(run);
    return;
  }
  state.runList[index] = run;
}

function renderRun(run) {
  const rawPolicy = run.latest_policy || null;
  const policy = playablePolicy(run);
  const visibleStatus = effectiveRunStatus(run);
  const usingFallbackPolicy = Boolean(policy && rawPolicy && policy.id !== rawPolicy.id);
  const policyText = policy
    ? ` / ONNX ${policyLabel(policy)}${usingFallbackPolicy ? ` / latest ${policyLabel(rawPolicy)} unhealthy` : ""}`
    : rawPolicy ? ` / ONNX ${policyLabel(rawPolicy)} unhealthy` : "";
  el.runTitle.textContent = `${displayRobotName(run)} / ${displayAlgorithmName(run)} / ${visibleStatus}${policy ? " / ONNX 可播放" : rawPolicy ? " / ONNX 健康检查未通过" : ""}`;
  el.runMeta.textContent = `${displayTaskName(run)} / ${shortRunId(run.id)}${policyText}`;
  el.runMeta.title = run.id;
  el.runStatus.textContent = visibleStatus;
  el.runStatus.className = `status-badge ${visibleStatus}`;

  const pct = Number(run.progress && run.progress.percent);
  const stage = (run.progress && run.progress.stage) || run.status;
  el.progressBar.style.width = `${Number.isFinite(pct) ? Math.max(0, Math.min(100, pct)) : (TERMINAL.has(run.status) ? 100 : 0)}%`;
  const curriculumText = progressCurriculumText(run.progress || {});
  el.progressText.textContent = `${stage}${Number.isFinite(pct) ? ` / ${pct.toFixed(0)}%` : ""}${policyText}${curriculumText}`;
  renderRunHealth(run, policy, rawPolicy);

  const cancelPending = Boolean(run.cancel_requested && !TERMINAL.has(run.status));
  el.cancelButton.disabled = TERMINAL.has(run.status) || cancelPending;
  el.cancelButton.textContent = cancelPending ? "停止中…" : "停止训练";
  const canResume = run.resume_available === true && rawPolicy?.checkpoint_available === true;
  el.resumeButton.disabled = !canResume;
  el.resumeButton.textContent = canResume ? `继续训练 (${policyLabel(rawPolicy)})` : "继续训练";
  el.resumeButton.title = canResume ? "" : String(run.resume_reason || "当前任务不可续训");

  // Sim2Sim is enabled only when the ONNX artifact and contract pass health checks.
  const playable = Boolean(policy && policy.onnx_url);
  el.playLink.href = playable ? sim2simHref(run, policy) : "#";
  el.playLink.textContent = playable
    ? `→ Sim2Sim 播放 (${policyLabel(policy)})`
    : rawPolicy ? `→ Sim2Sim 不可用 (${policyHealthLabel(rawPolicy)})` : "→ Sim2Sim 播放";
  el.playLink.classList.toggle("disabled", !playable);
  const canDownload = state.isAdmin && playable;
  el.deploymentDownload.href = canDownload
    ? `/api/ops/runs/${encodeURIComponent(run.id)}/deployment-bundle`
    : "#";
  el.deploymentDownload.textContent = state.isAdmin
    ? (canDownload ? `下载部署包 (${policyLabel(policy)})` : "下载部署包")
    : "下载部署包（仅管理员）";
  el.deploymentDownload.title = state.isAdmin
    ? (canDownload ? "下载 ONNX、默认站立角度和控制参数" : "当前没有健康的 ONNX")
    : "当前仅管理员拥有模型下载权限";
  el.deploymentDownload.classList.toggle("disabled", !canDownload);
  el.deploymentDownload.setAttribute("aria-disabled", String(!canDownload));
  const errorMessage = run.error ? (run.error.message || JSON.stringify(run.error)) : "";
  const latestWarning = usingFallbackPolicy ? `最新导出 ${policyLabel(rawPolicy)} 不健康，已使用 ${policyLabel(policy)} 播放` : "";
  el.errorText.textContent = playable && run.status === "failed"
    ? [errorMessage, latestWarning || `ONNX ${policyLabel(policy)} 可播放`].filter(Boolean).join("; ")
    : playable
      ? [errorMessage, latestWarning].filter(Boolean).join("; ")
      : rawPolicy
        ? `${errorMessage ? `${errorMessage}; ` : ""}ONNX health ${policyHealthLabel(rawPolicy)}`
      : errorMessage;
}

function renderRunHealth(run, policy, rawPolicy) {
  if (!el.runHealthGrid) return;
  const progress = run.progress || {};
  const trainIter = integerOrNull(progress.iteration);
  const maxIter = integerOrNull(progress.max_iterations);
  const policyIter = policyIterationValue(policy || rawPolicy);
  const lag = trainIter !== null && policyIter !== null ? Math.max(0, trainIter - policyIter) : null;
  const heartbeat = Number(progress.heartbeat_at);
  const heartbeatLabel = Number.isFinite(heartbeat) ? ageLabel(Date.now() / 1000 - heartbeat) : "-";
  const terrain = Number(progress.terrain_level);
  const phase = progress.heartbeat_phase || progress.stage || run.status || "-";
  const cost = runCostLabel(run);
  const policyStatus = policy
    ? `可播放 / ${policyHealthLabel(policy)}`
    : rawPolicy ? `不可播放 / ${policyHealthLabel(rawPolicy)}` : "等待导出";
  const heartbeatAge = Number.isFinite(heartbeat) ? (Date.now() / 1000 - heartbeat) : null;
  const providerPriceMilliYuan = Number(
    progress.provider_price_milli_yuan_hr ?? progress.billing_rate_milli_yuan_hr,
  );
  const providerPrice = Number.isFinite(providerPriceMilliYuan) && providerPriceMilliYuan > 0
    ? `¥${(providerPriceMilliYuan / 1000).toFixed(3)}/小时`
    : "等待云端确认";
  const items = [
    ["训练迭代", trainIter !== null ? `${trainIter}${maxIter !== null ? ` / ${maxIter}` : ""}` : "-", "ok"],
    ["最新 ONNX", policyIter !== null ? `第 ${policyIter} 轮` : policyStatus, policy ? "ok" : rawPolicy ? "warn" : "idle"],
    ["同步差", lag !== null ? `${lag} 轮` : "-", lag !== null && lag > 250 ? "warn" : "ok"],
    ["Heartbeat", heartbeatLabel, heartbeatAge !== null && heartbeatAge > 300 ? "warn" : "ok"],
    ["阶段", phase, TERMINAL.has(run.status) ? "idle" : "ok"],
    ["Terrain", Number.isFinite(terrain) ? terrain.toFixed(2) : "-", "idle"],
    ["GPU", `${run.gpu_spec || "默认"} × ${Number(run.gpu_count) || 1} 卡`, "idle"],
    ["GPU 小时价", providerPrice, providerPriceMilliYuan > 0 ? "ok" : "idle"],
    ["费用", cost, Number(run.cost_charged_cents || 0) > 0 ? "ok" : "idle"],
    ["GPU 时长", durationLabel(Number(run.gpu_seconds || 0)), "idle"],
  ];
  el.runHealthGrid.innerHTML = items.map(([label, value, tone]) => `
    <div class="run-health-item ${escapeAttr(tone || "idle")}">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `).join("");
}

function runCostLabel(run) {
  const charged = Number(run?.cost_charged_cents || 0);
  const frozen = Number(run?.cost_frozen_cents || 0);
  if (charged > 0) return `¥${(charged / 100).toFixed(2)} 实时已扣`;
  if (frozen > 0) return `¥${(frozen / 100).toFixed(2)} 启动保留`;
  return "未计费";
}

async function refreshLiveBalance(force = false) {
  const now = Date.now();
  if (state.balanceRefreshing || (!force && now - state.balanceRefreshAt < 10000)) return;
  state.balanceRefreshing = true;
  state.balanceRefreshAt = now;
  try {
    const wallet = await billing.me(1);
    const navBalance = document.querySelector(".pnav-balance");
    if (navBalance) navBalance.textContent = formatYuan(wallet.balance_cents);
  } catch (_) {
    // The run poll remains authoritative; a stale nav balance is non-fatal.
  } finally {
    state.balanceRefreshing = false;
  }
}

function durationLabel(seconds) {
  if (!Number.isFinite(seconds) || seconds <= 0) return "-";
  if (seconds < 60) return `${Math.round(seconds)} 秒`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} 分钟`;
  return `${(seconds / 3600).toFixed(1)} 小时`;
}

function sim2simHref(run, policy) {
  const params = new URLSearchParams({ run_id: run.id });
  if (policy.id) params.set("policy", policy.id);
  const iter = policyIterationValue(policy);
  if (iter !== null) params.set("iter", String(iter));
  if (policy.created_at) params.set("v", String(Date.parse(policy.created_at) || policy.created_at));
  return `/sim2sim/?${params.toString()}`;
}

function policyLabel(policy) {
  if (!policy) return "";
  const iter = policyIterationValue(policy);
  if (iter !== null) return `iter ${iter}`;
  const name = String(policy.checkpoint || "").split(/[\\/]/).pop();
  return name || "ONNX 已导出";
}

function policyIterationValue(policy) {
  const direct = integerOrNull(policy?.checkpoint_iteration);
  if (direct !== null) return direct;
  const checkpoint = String(policy?.checkpoint || "");
  const match = checkpoint.match(/(?:model|checkpoint|ckpt|iter|iteration)[_-]?(\d+)\b/i);
  if (match) return Number(match[1]);
  const artifact = String(policy?.health?.artifact || "");
  const artifactMatch = artifact.match(/(?:policy|model|checkpoint|ckpt|iter|iteration)[_-]?(\d+)\b/i);
  return artifactMatch ? Number(artifactMatch[1]) : null;
}

function integerOrNull(value) {
  if (value === undefined || value === null || value === "") return null;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : null;
}

function ageLabel(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "-";
  if (seconds < 5) return "刚刚";
  if (seconds < 60) return `${Math.round(seconds)} 秒前`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} 分钟前`;
  return `${Math.round(minutes / 60)} 小时前`;
}

function shortRunId(id) {
  const text = String(id || "");
  if (!text) return "-";
  return text.length > 18 ? `${text.slice(0, 12)}...${text.slice(-6)}` : text;
}

function isPolicyPlayable(policy) {
  if (!policy?.id || !policy?.onnx_url) return false;
  const status = String(policy.health?.status || "pass").toLowerCase();
  return status === "pass" || status === "ready";
}

function playablePolicy(run) {
  if (isPolicyPlayable(run?.playable_policy)) return run.playable_policy;
  if (isPolicyPlayable(run?.latest_policy)) return run.latest_policy;
  return null;
}

function policyHealthLabel(policy) {
  return String(policy?.health?.status || "unknown");
}

function progressCurriculumText(progress) {
  const parts = [];
  if (Number.isFinite(Number(progress.terrain_level))) {
    parts.push(`terrain ${Number(progress.terrain_level).toFixed(2)}`);
  }
  if (Number.isFinite(Number(progress.max_command_x))) {
    parts.push(`vx ${Number(progress.max_command_x).toFixed(2)}`);
  }
  return parts.length ? ` / ${parts.join(" / ")}` : "";
}

// Normalize whatever the events endpoint returns (array or {events:[...]}) and
// append only unseen entries, de-duped by seq when present.
function ingestEvents(payload) {
  const list = Array.isArray(payload) ? payload : (payload.events || payload.items || []);
  for (const ev of list) {
    const seq = Number(ev.seq);
    if (Number.isFinite(seq)) {
      if (seq <= state.seenSeq) continue;
      state.seenSeq = Math.max(state.seenSeq, seq);
    }
    ingestRewardEvent(ev);
    state.logLines.push(normalizeEvent(ev));
  }
  if (state.logLines.length > 600) state.logLines = state.logLines.slice(-600);
  el.eventCount.textContent = String(state.logLines.length);
  renderCurveOptions();
  renderLog();
}

function ingestMetricEvents(payload) {
  const list = Array.isArray(payload) ? payload : (payload.events || payload.items || []);
  for (const event of list) {
    const seq = Number(event.seq);
    if (Number.isFinite(seq)) {
      if (seq <= state.seenMetricSeq) continue;
      state.seenMetricSeq = Math.max(state.seenMetricSeq, seq);
    }
    ingestRewardEvent(event);
  }
  renderCurveOptions();
}

function ingestRewardEvent(ev) {
  const line = ev.line || ev.text || ev.message || "";
  const lineIteration = trainingIterationFromLine(line);
  if (lineIteration !== null) state.metricIteration = lineIteration;
  const step = metricStep(ev);
  const metricMap = flattenMetricPayload(ev);
  for (const [tag, value] of Object.entries(metricMap)) addRewardPoint(tag, step, value);

  if (line) ingestRewardLogLine(line, step);
}

function trainingIterationFromLine(line) {
  const match = stripAnsi(String(line || "")).match(/Learning iteration\s+(\d+)\s*\/\s*\d+/i);
  return match ? Number(match[1]) : null;
}

function metricStep(ev) {
  const step = Number(ev.iteration ?? ev.step ?? ev.global_step ?? ev.iter ?? NaN);
  if (Number.isFinite(step)) return step;
  if (Number.isFinite(state.metricIteration)) return state.metricIteration;
  state.metricTick += 1;
  return state.metricTick;
}

function flattenMetricPayload(ev) {
  const out = {};
  const visit = (value, prefix = "") => {
    if (!value || typeof value !== "object") return;
    for (const [key, raw] of Object.entries(value)) {
      const name = prefix ? `${prefix}/${key}` : key;
      const n = Number(raw);
      if (Number.isFinite(n)) {
        out[name] = n;
      } else if (raw && typeof raw === "object") {
        visit(raw, name);
      }
    }
  };
  visit(ev.metrics || {});
  visit(ev.values || {});
  visit(ev.scalars || {});
  if (typeof ev.tag === "string" && Number.isFinite(Number(ev.value))) out[ev.tag] = Number(ev.value);
  return out;
}

function ingestRewardLogLine(line, step) {
  const text = stripAnsi(line);
  const number = "([-+]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:e[-+]?\\d+)?)";
  const computation = text.match(new RegExp(`Computation:\\s*${number}\\s*steps/s\\s*\\(collection:\\s*${number}s,\\s*learning\\s*${number}s\\)`, "i"));
  if (computation) {
    addRewardPoint("Perf/total_fps", step, Number(computation[1]));
    addRewardPoint("Perf/collection_time", step, Number(computation[2]));
    addRewardPoint("Perf/learning_time", step, Number(computation[3]));
    return;
  }
  const episode = text.match(new RegExp(`Mean episode\\s+([\\w./ -]+):\\s*${number}`, "i"));
  if (episode) {
    const name = episode[1].trim().replace(/\s+/g, "_");
    addRewardPoint(name.startsWith("terrain_level") ? `Terrain/${name}` : `Episode/${name}`, step, Number(episode[2]));
    return;
  }
  const patterns = [
    ["Loss/value_function", "Value function loss"],
    ["Loss/surrogate", "Surrogate loss"],
    ["Loss/entropy", "Entropy loss"],
    ["Loss/latent", "Latent loss"],
    ["Loss/actor_load_balance", "Actor load balance loss"],
    ["Loss/load_balance", "Load balance loss"],
    ["Loss/learning_rate", "Learning rate"],
    ["Policy/mean_noise_std", "Mean action noise std"],
    ["Train/mean_teacher_reward", "Mean teacher reward"],
    ["Train/mean_teacher_episode_length", "Mean teacher episode length"],
    ["Train/mean_student_reward", "Mean student reward"],
    ["Train/mean_student_episode_length", "Mean student episode length"],
    ["Train/mean_reward", "Mean reward"],
    ["Train/mean_episode_length", "Mean episode length"],
    ["Perf/total_timesteps", "Total timesteps"],
    ["Perf/iteration_time", "Iteration time"],
    ["Perf/total_time", "Total time"],
    ["Perf/eta_seconds", "ETA"],
  ];
  for (const [tag, label] of patterns) {
    const match = text.match(new RegExp(`${label}:\\s*${number}`, "i"));
    if (match) {
      addRewardPoint(tag, step, Number(match[1]));
      return;
    }
  }
}

function addRewardPoint(key, step, value) {
  if (!Number.isFinite(value)) return;
  const series = state.rewardSeries[key] || (state.rewardSeries[key] = []);
  const existing = series.findIndex((point) => point.step === step);
  if (existing >= 0) {
    series[existing].value = value;
  } else {
    series.push({ step, value });
    if (series.length > 1 && series[series.length - 2].step > step) {
      series.sort((a, b) => a.step - b.step);
    }
  }
  if (series.length > 1000) series.splice(0, series.length - 1000);
}

function average(values) {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function metricGroupForTag(tag) {
  if (tag.startsWith("Episode/rew_")) return "reward";
  if (tag.startsWith("Loss/")) return "loss";
  if (tag.startsWith("Perf/")) return "performance";
  if (tag.startsWith("Terrain/")) return "terrain";
  return "overview";
}

function metricLabel(tag) {
  if (METRIC_LABELS[tag]) return METRIC_LABELS[tag];
  const raw = tag.split("/").pop().replace(/^rew_/, "");
  const label = raw.replaceAll("_", " ");
  if (tag.startsWith("Episode/rew_")) return `奖励 · ${label}`;
  if (tag.startsWith("Terrain/")) return `地形 · ${label.replace(/^terrain level /, "")}`;
  return label;
}

function metricTagsForGroup(group) {
  const all = Object.keys(state.rewardSeries);
  const populated = all.filter((tag) => state.rewardSeries[tag]?.length);
  const available = populated.length ? populated : all;
  if (group === "all") return available.sort((a, b) => metricLabel(a).localeCompare(metricLabel(b), "zh-CN"));
  if (group === "overview") {
    const selected = OVERVIEW_METRICS.filter((tag) => available.includes(tag));
    return selected.length ? selected : available.slice(0, 1);
  }
  return available
    .filter((tag) => metricGroupForTag(tag) === group)
    .sort((a, b) => metricLabel(a).localeCompare(metricLabel(b), "zh-CN"));
}

function renderRewardCurve() {
  const key = el.curveSelect.value;
  const rawSeries = state.rewardSeries[key] || [];
  const range = Number(el.metricWindowSelect.value || 300);
  const visible = range > 0 ? rawSeries.slice(-range) : rawSeries;
  const series = smoothMetricSeries(visible, Number(el.metricSmoothSelect.value || 1));
  const label = key ? metricLabel(key) : "训练指标";
  el.curveStatus.textContent = series.length ? `${series.length} 个点 · ${label}` : `等待 ${label}`;
  el.curveEmpty.classList.toggle("hidden", series.length > 0);
  renderMetricLatest();

  const width = 360;
  const height = 170;
  const pad = { left: 42, right: 14, top: 16, bottom: 30 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const base = `
    <line x1="${pad.left}" y1="${pad.top}" x2="${pad.left}" y2="${height - pad.bottom}" stroke="#1e293b" stroke-width="1" />
    <line x1="${pad.left}" y1="${height - pad.bottom}" x2="${width - pad.right}" y2="${height - pad.bottom}" stroke="#1e293b" stroke-width="1" />
  `;
  if (!series.length) {
    el.rewardCurve.innerHTML = base;
    return;
  }

  const steps = series.map((p) => p.step);
  const values = series.map((p) => p.value);
  const minStep = Math.min(...steps);
  const maxStep = Math.max(...steps);
  let minValue = Math.min(...values);
  let maxValue = Math.max(...values);
  if (minValue === maxValue) {
    minValue -= 1;
    maxValue += 1;
  }
  const xFor = (step) => pad.left + (maxStep === minStep ? innerW / 2 : ((step - minStep) / (maxStep - minStep)) * innerW);
  const yFor = (value) => pad.top + (1 - ((value - minValue) / (maxValue - minValue))) * innerH;
  const points = series.map((p) => `${xFor(p.step).toFixed(1)},${yFor(p.value).toFixed(1)}`).join(" ");
  const last = series[series.length - 1];
  const firstStep = fmtAxis(minStep);
  const lastStep = fmtAxis(maxStep);
  const minLabel = fmtAxis(minValue);
  const maxLabel = fmtAxis(maxValue);

  el.rewardCurve.innerHTML = `
    ${base}
    <text x="8" y="${pad.top + 4}" fill="#64748b" font-size="10">${maxLabel}</text>
    <text x="8" y="${height - pad.bottom}" fill="#64748b" font-size="10">${minLabel}</text>
    <text x="${pad.left}" y="${height - 9}" fill="#64748b" font-size="10">${firstStep}</text>
    <text x="${width - pad.right - 48}" y="${height - 9}" fill="#64748b" font-size="10">${lastStep}</text>
    <polyline points="${points}" fill="none" stroke="#14b8a6" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
    <circle cx="${xFor(last.step).toFixed(1)}" cy="${yFor(last.value).toFixed(1)}" r="3.5" fill="#5eead4" />
  `;
}

function smoothMetricSeries(series, windowSize) {
  const size = Math.max(1, Math.floor(windowSize) || 1);
  if (size === 1) return series;
  return series.map((point, index) => {
    const values = series.slice(Math.max(0, index - size + 1), index + 1).map((item) => item.value);
    return { step: point.step, value: average(values) };
  });
}

function renderMetricLatest() {
  const allPopulated = Object.entries(state.rewardSeries).filter(([, series]) => series.length);
  el.metricTagCount.textContent = `${allPopulated.length} 项`;
  const tags = metricTagsForGroup(state.metricGroup).filter((tag) => state.rewardSeries[tag]?.length);
  if (!tags.length) {
    el.metricLatestGrid.innerHTML = '<div class="metric-latest-empty">等待训练指标</div>';
    return;
  }
  el.metricLatestGrid.innerHTML = tags.map((tag) => {
    const series = state.rewardSeries[tag];
    const latest = series[series.length - 1];
    const previous = series.length > 1 ? series[series.length - 2] : null;
    const delta = previous ? latest.value - previous.value : null;
    const deltaText = delta === null ? `迭代 ${fmtAxis(latest.step)}` : `${delta >= 0 ? "+" : ""}${fmtMetric(delta)} / 上轮`;
    return `
      <div class="metric-latest-item" title="${escapeAttr(tag)}">
        <span>${escapeHtml(metricLabel(tag))}</span>
        <strong>${escapeHtml(fmtMetric(latest.value))}</strong>
        <small>${escapeHtml(deltaText)}</small>
      </div>
    `;
  }).join("");
}

function fmtMetric(value) {
  if (!Number.isFinite(value)) return "-";
  if (Math.abs(value) >= 1000000) return value.toExponential(3);
  if (Math.abs(value) >= 1000) return value.toFixed(0);
  if (Math.abs(value) > 0 && Math.abs(value) < 0.0001) return value.toExponential(3);
  return value.toFixed(4).replace(/\.?0+$/, "");
}

function fmtAxis(value) {
  if (!Number.isFinite(value)) return "-";
  if (Math.abs(value) >= 1000 || (Math.abs(value) > 0 && Math.abs(value) < 0.001)) return value.toExponential(1);
  if (Math.abs(value) < 10) return value.toFixed(3).replace(/\.?0+$/, "");
  return value.toFixed(0);
}

function normalizeEvent(ev) {
  const at = ev.at || ev.ts || ev.time || "";
  const type = ev.type || ev.kind || "";
  if (type === "state_changed" || type === "state") {
    return { at, kind: "state", label: "state", text: `${ev.from || "-"} → ${ev.to || ev.status || ""} ${ev.message || ""}`.trim() };
  }
  if (type === "log_line" || type === "log") {
    return { at, kind: ev.phase || "worker", label: ev.phase || "worker", text: stripAnsi(ev.line || ev.text || "") };
  }
  if (type === "metric_update" || type === "metric") {
    return { at, kind: "metric", label: "metric", text: ev.message || `iter ${ev.iteration ?? "-"} tags ${ev.tag_count ?? "-"}` };
  }
  if (type === "artifact_created" || type === "onnx_exported" || type === "artifact") {
    const iter = ev.checkpoint_iteration !== undefined && ev.checkpoint_iteration !== null
      ? `iter ${ev.checkpoint_iteration}`
      : "";
    const text = [iter, ev.path || ev.url || ev.checkpoint || ""].filter(Boolean).join(" · ");
    return { at, kind: "artifact", label: type === "onnx_exported" ? "onnx" : "artifact", text };
  }
  if (type === "error") {
    return { at, kind: "error", label: "error", text: typeof ev.error === "string" ? ev.error : JSON.stringify(ev.error || ev) };
  }
  return { at, kind: "worker", label: type || "event", text: ev.message || ev.line || ev.text || JSON.stringify(ev) };
}

// Render log rows. Stick to bottom ONLY if the user is already near the bottom —
// don't yank them down when they've scrolled up to read (specific UX complaint).
function renderLog() {
  const log = el.eventLog;
  const stick = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
  log.innerHTML = "";
  if (!state.logLines.length) {
    const empty = document.createElement("div");
    empty.className = "log-empty";
    empty.textContent = "等待 worker 事件…";
    log.append(empty);
    return;
  }
  for (const item of state.logLines) {
    const row = document.createElement("div");
    row.className = `log-row ${item.kind}`;
    const time = document.createElement("span");
    time.className = "log-time";
    time.textContent = compactTime(item.at);
    const label = document.createElement("span");
    label.className = "log-label";
    label.textContent = item.label;
    const text = document.createElement("span");
    text.className = "log-text";
    text.textContent = item.text;
    row.append(time, label, text);
    log.append(row);
  }
  if (stick) log.scrollTop = log.scrollHeight;
}

async function onCancel() {
  if (!state.selectedRunId) return;
  const selected = state.runList.find((run) => run.id === state.selectedRunId);
  const label = selected
    ? `${displayAlgorithmName(selected)} / ${displayTaskName(selected)}\n${selected.id}`
    : state.selectedRunId;
  if (!window.confirm(`确认停止这条训练？\n\n${label}`)) return;
  el.cancelButton.disabled = true;
  el.cancelButton.textContent = "停止中…";
  try {
    const run = await runs.cancel(state.selectedRunId);
    replaceRun(run);
    renderRun(run);
  } catch (err) {
    el.errorText.textContent = err instanceof ApiError ? err.message : "停止失败";
    el.cancelButton.disabled = false;
    el.cancelButton.textContent = "停止训练";
  }
}

function openResumeDialog() {
  const run = state.runList.find((item) => item.id === state.selectedRunId);
  if (!run || run.resume_available !== true || !run.latest_policy?.checkpoint_available) return;
  state.resumeSourceRun = run;
  const checkpointIter = integerOrNull(run.latest_policy.checkpoint_iteration) || 0;
  const sourceMax = integerOrNull(run.hyperparams?.max_iterations) || checkpointIter;
  const additionalMode = run.hyperparams?.iteration_mode === "additional";
  const increment = Math.max(500, Math.ceil(Math.max(1, sourceMax) * 0.25 / 100) * 100);
  el.resumeSource.textContent = `${displayAlgorithmName(run)} / ${displayTaskName(run)}`;
  el.resumeSource.title = run.id;
  el.resumeCheckpoint.textContent = policyLabel(run.latest_policy);
  el.resumeSourceGpu.textContent = `${run.gpu_spec || "默认"} × ${Number(run.gpu_count) || 1} 卡`;
  renderResumeGpuOptions(run.gpu_spec || "");
  const resumeAlgorithm = state.algorithms.find((item) => item.id === run.algorithm_id);
  const resumeTask = normalizedTasks(resumeAlgorithm).find((task) => task.id === run.task_id);
  renderGpuCountOptions(Number(run.gpu_count) || 1, {
    resume: true,
    task: resumeTask,
    algo: resumeAlgorithm,
  });
  if (el.resumeGpuHint) {
    el.resumeGpuHint.textContent = run.gpu_spec
      ? `（来源 ${run.gpu_spec}，可更换）`
      : "（可更换规格）";
  }
  el.resumeIterationsLabel.textContent = additionalMode ? "追加迭代" : "目标总迭代";
  el.resumeIterations.min = additionalMode ? "1" : String(checkpointIter + 1);
  el.resumeIterations.value = additionalMode
    ? String(Math.max(1, sourceMax))
    : String(Math.max(sourceMax, checkpointIter) + increment);
  el.resumeNumEnvs.value = String(integerOrNull(run.hyperparams?.num_envs) || 64);
  el.resumeSeed.value = String(integerOrNull(run.hyperparams?.seed) ?? 1);
  const resumeRobot = state.robots.find((robot) => robot.id === run.robot_id);
  const configurable = supportsTrainingControls(resumeRobot)
    || ["point_foot_moe_cts", "w1w_moe_cts"].includes(run.task_id);
  const sourceHeight = Number(run.base_height_target);
  const configuredHeight = Number(resumeRobot?.control_defaults?.base_height_target);
  el.resumeBaseHeightTargetRow.hidden = !configurable;
  el.resumeBaseHeightTarget.value = String(
    Number.isFinite(sourceHeight) ? sourceHeight : (Number.isFinite(configuredHeight) ? configuredHeight : 0.45)
  );
  el.resumeJointVelocityLimitRow.hidden = !configurable;
  el.resumeJointVelocityLimit.value = String(Number(run.hyperparams?.joint_velocity_limit) || 8);
  el.resumeAddedMassMinRow.hidden = !configurable;
  el.resumeAddedMassMaxRow.hidden = !configurable;
  const sourceMassMin = Number(run.hyperparams?.added_mass_min_kg);
  const sourceMassMax = Number(run.hyperparams?.added_mass_max_kg);
  el.resumeAddedMassMin.value = String(Number.isFinite(sourceMassMin) ? sourceMassMin : -1);
  el.resumeAddedMassMax.value = String(Number.isFinite(sourceMassMax) ? sourceMassMax : 1);
  if (el.resumeSelfCollisions) {
    el.resumeSelfCollisions.value = String(Number(run.hyperparams?.self_collisions) === 0 ? 0 : 1);
  }
  renderAmpInputs(el.resumeAmpParamGrid, resolvedTaskDefaults(resumeTask), run.hyperparams);
  renderRewardInputs(el.resumeRewardGrid, rewardScalesForResume(run));
  el.resumeError.textContent = "";
  updateResumePriceQuote();
  el.resumeDialog.showModal();
  el.resumeIterations.focus();
  el.resumeIterations.select();
}

function closeResumeDialog() {
  if (el.resumeDialog.open) el.resumeDialog.close();
  state.resumeSourceRun = null;
  el.resumeError.textContent = "";
}

async function onResume(event) {
  event.preventDefault();
  const source = state.resumeSourceRun;
  if (!source) return;
  const checkpointIter = integerOrNull(source.latest_policy?.checkpoint_iteration) || 0;
  const maxIterations = Math.max(1, parseInt(el.resumeIterations.value, 10) || 0);
  const numEnvs = parseInt(el.resumeNumEnvs.value, 10);
  const seed = parseInt(el.resumeSeed.value, 10);
  const baseHeightTarget = Number(el.resumeBaseHeightTarget.value);
  const jointVelocityLimit = Number(el.resumeJointVelocityLimit.value);
  const addedMassMin = Number(el.resumeAddedMassMin.value);
  const addedMassMax = Number(el.resumeAddedMassMax.value);
  const additionalMode = source.hyperparams?.iteration_mode === "additional";
  if (!additionalMode && maxIterations <= checkpointIter) {
    el.resumeError.textContent = `目标总迭代必须大于 ${checkpointIter}`;
    return;
  }
  if (!Number.isInteger(numEnvs) || numEnvs < 1 || numEnvs > 16384) {
    el.resumeError.textContent = "并行环境数必须在 1-16384 之间";
    return;
  }
  if (!Number.isInteger(seed) || seed < 0 || seed > 2147483647) {
    el.resumeError.textContent = "随机种子必须在 0-2147483647 之间";
    return;
  }
  if (!el.resumeBaseHeightTargetRow.hidden && (!Number.isFinite(baseHeightTarget) || baseHeightTarget < 0.1 || baseHeightTarget > 1.5)) {
    el.resumeError.textContent = "目标机身高度必须在 0.10–1.50 m 之间";
    return;
  }
  if (!el.resumeJointVelocityLimitRow.hidden && (!Number.isFinite(jointVelocityLimit) || jointVelocityLimit < 0.1 || jointVelocityLimit > 100)) {
    el.resumeError.textContent = "腿部关节速度上限必须在 0.1-100 rad/s 之间";
    return;
  }
  if (!el.resumeAddedMassMinRow.hidden && (!Number.isFinite(addedMassMin) || !Number.isFinite(addedMassMax) || addedMassMin < -100 || addedMassMax > 100 || addedMassMin > addedMassMax)) {
    el.resumeError.textContent = "随机附加重量范围必须在 -100 到 100 kg 且下限不大于上限";
    return;
  }
  el.resumeConfirmButton.disabled = true;
  el.resumeError.textContent = "";
  const payload = {
    max_iterations: maxIterations,
    num_envs: numEnvs,
    seed,
    self_collisions: Number(el.resumeSelfCollisions?.value) === 0 ? 0 : 1,
    gpu_spec: el.resumeGpuSelect.value,
    gpu_count: Number(el.resumeGpuCountSelect?.value) || 1,
    reward_scales: collectRewardInputs(el.resumeRewardGrid),
    ...collectAmpInputs(el.resumeAmpParamGrid),
  };
  if (!el.resumeBaseHeightTargetRow.hidden) {
    payload.base_height_target = baseHeightTarget;
  }
  if (!el.resumeJointVelocityLimitRow.hidden) {
    payload.joint_velocity_limit = jointVelocityLimit;
    payload.reward_scales._joint_velocity_limit = jointVelocityLimit;
    payload.added_mass_min_kg = addedMassMin;
    payload.added_mass_max_kg = addedMassMax;
    payload.reward_scales._added_mass_min_kg = addedMassMin;
    payload.reward_scales._added_mass_max_kg = addedMassMax;
  }
  const idempotencyKey = requestKey("resumeRequest", { source_id: source.id, ...payload });
  try {
    const run = await runs.resume(source.id, payload, idempotencyKey);
    if (el.resumeDialog.open) el.resumeDialog.close();
    state.resumeSourceRun = null;
    replaceRun(run);
    selectRun(run.id);
    try {
      await loadRuns({ autoSelect: false });
      state.resumeRequest = null;
    } catch {
      el.errorText.textContent = "续训任务已创建，任务列表稍后自动刷新";
    }
  } catch (err) {
    el.resumeError.textContent = err instanceof ApiError ? err.message : "继续训练失败";
  } finally {
    el.resumeConfirmButton.disabled = false;
    updateResumePriceQuote();
  }
}

function requestKey(stateKey, payload) {
  const signature = JSON.stringify(payload);
  if (state[stateKey]?.signature !== signature) {
    const fallback = `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`;
    state[stateKey] = {
      signature,
      key: globalThis.crypto?.randomUUID?.() || fallback.slice(0, 64),
    };
  }
  return state[stateKey].key;
}

function compactTime(at) {
  if (!at) return "";
  const d = typeof at === "number" ? new Date(at * 1000) : new Date(at);
  if (Number.isNaN(d.getTime())) return String(at).slice(11, 19);
  return d.toTimeString().slice(0, 8);
}

function stripAnsi(s) { return String(s).replace(/\x1b\[[0-9;]*m/g, ""); }

function escapeAttr(s) { return String(s).replace(/[^a-zA-Z0-9_-]/g, ""); }

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
