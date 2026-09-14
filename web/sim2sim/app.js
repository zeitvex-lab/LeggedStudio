// 全局错误捕获（诊断用）
window.__lastLoadError = null;
const __origConsoleError = console.error.bind(console);
console.error = (...args) => {
  window.__lastLoadError = args.map((a) => (a && a.stack) ? a.stack : String(a)).join(' | ');
  __origConsoleError(...args);
};
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import loadMujoco from "./vendor/mujoco/mujoco.js";
import { createObservationSystems } from "./obs/observation_builders.js?v=0.44.0";
import { createPieDepth } from "./pie_depth.js?v=0.46.0";
// 观测面板绘制器（深度帧 / 俯视高度场 / 极坐标扫描 / 点云散点 / 2D 轨迹平面）。
// 纯函数 + 注入 ctx：能画什么由参数决定，模块不读 sim / DOM，所以 Node 单测能覆盖。
import {
  drawDepthFrame,
  drawHeightField,
  drawPointCloud,
  drawPolarScan,
  drawTrail,
} from "./sensor_panels.js";
// 传感器视图悬浮窗：来源清单 / 插件清单 / 读数 / 装配与采样规格
// （纯逻辑在那边，这里只接线）。
import {
  applyMountEdit,
  availableSources,
  defaultPlugins,
  deg2rad,
  dockVisible,
  isMountOverridden,
  MOUNT_FIELDS,
  odomReadout,
  rangefinderReadout,
  readoutRows,
  resolveSource,
  SCAN_SPECS,
  SENSOR_MODELS,
  SENSOR_PLUGINS,
  sensorMount,
} from "./sensor_dock.js?v=0.54.2";
// 几何求交与四元数工具：深度 / 高度 / LiDAR / 点云 / 单点测距**共用同一套**，
// 采样几何（起点网格、扇扫方向）也在这儿 —— 见 raycast.js 头部说明。
import {
  fanDirections,
  gridOffsets,
  intersectSceneRay,
  intersectSceneRays,
  mountOriginWorld,
  mountRayDirections,
  quatFromRpy,
  quatMul,
  quatRot,
  quatToMat,
  rayHitPoint,
} from "./raycast.js?v=0.54.2";
import { MotionLoader } from "./motion_loader.js";
import { clamp, escapeAttr, escapeHtml, formatSigned, quatToRpy, quatRotateInverse, getGravityOrientation, getLinearVelocityBody, enumValue, isEditableElement } from "./utils.js";
import { applyTerrainSwitch, createNavigationRunner, poseFromQpos, NAVIGATION_VERSION } from "./navigation.js?v=0.54.2";
import { fanSegments, fanLineSegments } from "./dwa_fan.js?v=0.54.2";
// Loaded on demand only for an explicitly selected policy.
let ort = null;
const ORT_DIST_URL = new URL("./vendor/onnxruntime-web/dist/", import.meta.url);
const ORT_RUNTIME_REVISION = "1.23.2-local-2";

const CONFIG = {
  simulationDt: 0.002,
  controlDecimation: 10,
  maxFrameDt: 0.033,
  maxStepsPerFrame: 10,
  kps: new Float32Array(12).fill(20),
  kds: new Float32Array(12).fill(0.5),
  defaultAngles: new Float32Array([0.1, 0.8, -1.5, -0.1, 0.8, -1.5, 0.1, 1.0, -1.5, -0.1, 1.0, -1.5]),
  linVelScale: 2.0,
  angVelScale: 0.25,
  dofPosScale: 1.0,
  dofVelScale: 0.05,
  actionScale: 0.25,
  actionFilterAlpha: 1.0,
  actionFilterAlphas: null,
  actionFilterCutoffs: null,
  settleSteps: 0,
  hipScaleReduction: 1.0,
  baseHeightTarget: null,
  cmdScale: new Float32Array([2.0, 2.0, 0.25]),
  heightCommandScale: 2.0,
  // High-speed wheel-leg policies are trained symmetrically up to 8 m/s.
  // Lateral and yaw caps stay at their established values.
  maxCmd: new Float32Array([8.0, 1.5, 2.5]),
  defaultCommand: new Float32Array([0.0, 0.0, 0.0, 0.68, 0.0, 0.0]),
  autoplay: false,
  numActions: 12,
  numObs: 45,
  commandDims: 3,
  dofReindex: null,
  actionReindex: null,
  // Motion-tracking contracts (LeggedSkillDeploy protocol)：策略槽位 → CSV/机器人
  // 关节列的排列、腰关节槽位（策略序）与观测裁剪界。
  motionJointMapping: null,
  waistJointIndices: null,
  clipObs: null,
  torqueLimits: new Float32Array(12),
  motorVelocityLimits: new Float32Array(12),
  dynamicTorqueLimits: new Float32Array(12),
  motorEnvelopes: new Array(12).fill(null),
  jointOrder: [],
  actuatorRoles: new Array(12).fill("leg"),
  controlModes: new Array(12).fill("position"),
  actuatorInterface: "torque",
  positionActionScales: new Float32Array(12).fill(0.25),
  velocityActionScales: new Float32Array(12).fill(20),
  actionClip: null,
  observationKind: "default",
  historyLayout: "",
  gaitCommandGated: false,
  // 观测掩码（契约声明式，清单 ②）：{ "wrap_pi": ["FR_wheel_joint", ...], "zero": [...] }
  // 命中的槽位由构建器按声明处理，替代散落在各构建器里的硬编码约定。
  observationMask: null,
  gaitPeriodS: 0.7,
  gaitLocomotionGate: [0.05, 0.15],
  gaitYawCommandRadius: 0.25,
  agilityCommandDims: 0,
  commandAxes: [],
  commandRanges: null,
};
const ASSET_FETCH_CONCURRENCY = 4;
const LOW_FRICTION_TERRAINS = new Set(["stairs.xml", "cross_stairs.xml"]);
const STAIR_SURFACE_FRICTION = 0.7;
const SIGNAL_DELAY_MAX_STEPS = 10;
const IMU_SAMPLE_HISTORY_LIMIT = 64;
const WHEEL_LEG_GAIT_OBSERVATION = "wheel_leg_gait_moe_cts";
const WHEEL_LEG_GAIT_PERIOD_S = 0.7;
const WHEEL_LEG_JUMP_OBSERVATION = "wheel_leg_jump_moe_cts";
const WHEEL_LEG_JUMP_PERIOD_S = 0.7;
const WHEEL_LEG_JUMP_COMMAND_DURATION_S = [0.5, 1.0];
const BUNDLED_TERRAIN_ASSET_REVISION = "stairs-h16d25-20260731b";

const XML_FILES = ["go2.xml", "flat.xml", "slope.xml", "wave.xml", "stairs.xml", "obstacles.xml", "stepping_stones.xml", "gap.xml", "high_platforms.xml", "cross_stairs.xml", "cross_slope.xml", "race_track.xml"];
const FSDOG_SCENE_FILES = ["flat.xml", "slope.xml", "wave.xml", "stairs.xml", "obstacles.xml", "stepping_stones.xml", "gap.xml", "high_platforms.xml", "cross_stairs.xml", "cross_slope.xml", "race_track.xml"];
const TERRAIN_LABELS = {
  flat: "平地",
  slope: "斜坡",
  wave: "波浪地形",
  stairs: "楼梯",
  obstacles: "障碍物",
  stepping_stones: "踏石",
  gap: "沟壑",
  high_platforms: "高台（30-100 cm）",
  cross_stairs: "交叉楼梯",
  cross_slope: "横坡",
  race_track: "赛道",
};
const FSDOG_ROBOT = {
  name: "FSDog1",
  vendor: "Demo",
  morphology: "quadruped_12dof",
  joint_order: [
    "fl_hip_joint", "fl_thigh_joint", "fl_calf_joint",
    "fr_hip_joint", "fr_thigh_joint", "fr_calf_joint",
    "rl_hip_joint", "rl_thigh_joint", "rl_calf_joint",
    "rr_hip_joint", "rr_thigh_joint", "rr_calf_joint",
  ],
  default_joint_angles: {
    fl_hip_joint: 0.0,
    fl_thigh_joint: 0.75,
    fl_calf_joint: 1.5,
    fr_hip_joint: 0.0,
    fr_thigh_joint: 0.75,
    fr_calf_joint: 1.5,
    rl_hip_joint: 0.0,
    rl_thigh_joint: 0.75,
    rl_calf_joint: 1.5,
    rr_hip_joint: 0.0,
    rr_thigh_joint: 0.75,
    rr_calf_joint: 1.5,
  },
  control: {
    stiffness: { hip: 30.0, thigh: 30.0, calf: 30.0 },
    damping: { hip: 0.8, thigh: 0.8, calf: 0.8 },
    action_scale: 0.25,
    decimation: 4,
    torque_limits: { hip: 17.0, thigh: 17.0, calf: 17.0 },
  },
};
const MESH_FILES = [
  "base_0.obj",
  "base_1.obj",
  "base_2.obj",
  "base_3.obj",
  "base_4.obj",
  "hip_0.obj",
  "hip_1.obj",
  "thigh_0.obj",
  "thigh_1.obj",
  "thigh_mirror_0.obj",
  "thigh_mirror_1.obj",
  "calf_0.obj",
  "calf_1.obj",
  "calf_mirror_0.obj",
  "calf_mirror_1.obj",
  "foot.obj",
  "height_field.png",
  "wood.png",
];
const IMAGE_FILES = ["label_1.png", "label_4.png", "label_7.png", "label_10.png"];
const PAGE_PARAMS = new URLSearchParams(window.location.search);
const VIEWER_ONLY = PAGE_PARAMS.get("viewer") === "1";
// An explicit query parameter must be able to override a policy contract.
// Autoplay only selects the idle command; a loaded policy always stays active.
const URL_AUTOPLAY = PAGE_PARAMS.has("autoplay")
  ? PAGE_PARAMS.get("autoplay") === "1"
  : null;
const URL_TERRAIN = PAGE_PARAMS.get("terrain") || "";
// 仿真分层过滤：surface=advanced 只列外部传感器/目标驱动任务；surface=basic 排除它们。
const URL_SURFACE = PAGE_PARAMS.get("surface") || "";
// 仿真分层**两件事**（同一个仿真内核，两个仿真页）：
//   · 策略清单按 `sim_surface` 过滤（见 policyCandidates；高级仿真列出全部）
//   · **观测面板与传感器悬浮窗只属于高级仿真** —— 基础仿真的定义就是「本体 + 本体感知」
//     （只靠 IMU / 编码器 / 接触，不依赖外部世界），页面上只留 3D 视口与运行 HUD。
const SHOW_ADVANCED_PANELS = dockVisible(URL_SURFACE);
const SURFACE_LABEL = SHOW_ADVANCED_PANELS ? "高级仿真" : "基础仿真";
const DEFAULT_TERRAIN = "wave";
// 机器人 ID 别名表（数据）：覆盖全部内置包的「完整包 id」与「URL 短键」，
// 统一归一化到短键，消除「包下划线（unitree_go2）↔ 浏览器连字符/短键（go2）」命名双轨。
// 匹配顺序按 match 长度降序，避免 go2w / go2、b2w / b2 之类的前缀包含误匹配。
// 必须在首个 normalizeRobotParam 调用（下方 URL_ROBOT）之前初始化，否则模块顶层
// 执行会命中 const TDZ，整个 app.js 直接失败、页面卡在"加载 MuJoCo WASM..."。
const ROBOT_ID_ALIASES = [
  // 完整包 id → 短键（精确匹配优先）
  { match: "unitree_go2w", key: "go2w" },
  { match: "unitree_go1", key: "go1" },
  { match: "unitree_go2", key: "go2" },
  { match: "deeprobotics_lite3", key: "lite3" },
  { match: "deeprobotics_m20", key: "m20" },
  { match: "limx_tron1_pf", key: "tron1_pf" },
  { match: "limx_tron1_sf", key: "tron1_sf" },
  { match: "limx_tron1_wf", key: "tron1_wf" },
  { match: "unitree_b2w", key: "b2w" },
  { match: "unitree_b2", key: "b2" },
  { match: "unitree_g1", key: "g1" },
  // URL 短键 → 短键（含历史自定义短键）
  { match: "go2w", key: "go2w" },
  { match: "go1", key: "go1" },
  { match: "go2", key: "go2" },
  { match: "lite3", key: "lite3" },
  { match: "m20", key: "m20" },
  { match: "tron1_pf", key: "tron1_pf" },
  { match: "tron1_sf", key: "tron1_sf" },
  { match: "tron1_wf", key: "tron1_wf" },
  { match: "b2w", key: "b2w" },
  { match: "b2", key: "b2" },
  { match: "g1", key: "g1" },
  { match: "zex_w", key: "zex_w" },
  { match: "zex", key: "zex_w" },
  { match: "microduck", key: "microduck" },
  { match: "wuji_hand", key: "wuji_hand" },
  { match: "fsdog1", key: "fsdog1" },
  { match: "fsdog", key: "fsdog1" },
];
const URL_ROBOT = normalizeRobotParam(PAGE_PARAMS.get("robot") || "");
const DEBUG_ENABLED = PAGE_PARAMS.get("debug") === "1" || PAGE_PARAMS.has("qa");
if (PAGE_PARAMS.get("embedded") === "1") document.body.classList.add("embedded");
if (VIEWER_ONLY) document.body.classList.add("viewer-only");
// 观测面板与悬浮窗按分层显示：基础仿真**一个都不显示**。
// 用 hidden 属性**整体移除**而不是"画了再藏" —— updateSensorPanels 里会整段跳过，
// 省掉每帧的帧拷贝与 RGBA 转换。标题同时按分层区分：此前两个仿真页都叫「仿真验证」，
// 从标题上分不出自己开的是哪一个。
document.querySelectorAll('[data-surface="advanced"]').forEach((el) => {
  el.hidden = !SHOW_ADVANCED_PANELS;
});
document.title = `${SURFACE_LABEL} · Legged Studio`;
const surfaceTitle = document.querySelector("#surfaceTitle");
if (surfaceTitle) surfaceTitle.textContent = SURFACE_LABEL;

// ── 传感器视图悬浮窗（高级仿真专属）─────────────────────────────────────
// 单一视图 + 来源切换 + 外挂传感器勾选：来源与插件清单见 sensor_dock.js。
// 这里只做三件事：建 DOM、维护 dock 状态、以及把"当前来源"标出来。
// 装配覆盖（用户改过的位置 / 角度）。**刻意不挂在 sim 上** —— dock 的初始化早于
// sim 定义，挂上去会在初始化时就撞 TDZ；而且这本来就是 UI 侧的状态。
let sensorMountOverrides = {};

const dock = {
  visible: SHOW_ADVANCED_PANELS,
  plugins: defaultPlugins(), // 本体感知（odom / IMU）默认开，外挂传感器默认关
  source: "",
  collapsed: false,
};
const dockRoot = document.querySelector("#sensorDock");
const dockSourceSelect = document.querySelector("#dockSource");
const dockNote = document.querySelector("#dockNote");
const dockReadoutBox = document.querySelector("#dockReadout");
const dockCanvasEl = document.querySelector("#dockCanvas");
const dockPluginsBox = document.querySelector("#dockPlugins");
const dockMountsBox = document.querySelector("#dockMounts");

/** 重建来源下拉：只列**当前插件下可用**的来源（未勾选的外挂传感器对应的来源不出现）。 */
function renderDockSources() {
  if (!dockSourceSelect) return;
  const options = availableSources(dock.plugins);
  dockSourceSelect.innerHTML = options.map((s) => `<option value="${s.id}">${s.label}</option>`).join("");
  dock.source = resolveSource(dock.source, dock.plugins);
  dockSourceSelect.value = dock.source;
}

/** 重建插件勾选表。改勾选后来源清单要跟着变，且当前来源可能被关掉 → 回落。 */
function renderDockPlugins() {
  if (!dockPluginsBox) return;
  dockPluginsBox.innerHTML = SENSOR_PLUGINS.map((p) => `
    <label title="${p.hint}">
      <input type="checkbox" data-plugin="${p.id}"${dock.plugins[p.id] ? " checked" : ""} />
      <span>${p.label} · ${p.onboard ? "本体" : "外挂"}</span>
    </label>`).join("");
  dockPluginsBox.querySelectorAll("[data-plugin]").forEach((box) => {
    box.addEventListener("change", () => {
      dock.plugins[box.dataset.plugin] = box.checked;
      renderDockSources();
      // 3D 里的可视化模型跟着增删：勾上一个传感器就多一个小方块，取消就消失。
      ensureSensorModels();
      // 装配编辑器只列**已启用**的传感器 —— 没插的插件没有装配可言。
      renderDockMounts();
    });
  });
}

/** 重建装配编辑器（位置 xyz / 姿态 rpy 各三格）。 */
function renderDockMounts() {
  if (!dockMountsBox) return;
  const enabled = SENSOR_PLUGINS.filter((p) => dock.plugins[p.id]);
  if (!enabled.length) {
    dockMountsBox.className = "";
    dockMountsBox.innerHTML = '<p class="dock-mount-hint">先在上方勾选传感器</p>';
    return;
  }
  dockMountsBox.className = "dock-mount-list";
  dockMountsBox.innerHTML = enabled.map((p) => {
    const mount = sensorMount(p.id, sensorMountOverrides);
    const rows = MOUNT_FIELDS.map((f) => `
        <label>${f.label}
          <input type="number" step="${f.step}"
            data-mount="${p.id}" data-key="${f.key}" data-index="${f.index}"
            value="${mount[f.key][f.index]}"
            aria-label="${p.label} ${f.label}（${f.unit}）" />${f.unit}
        </label>`).join("");
    const cls = isMountOverridden(p.id, sensorMountOverrides) ? " overridden" : "";
    return `<div class="dock-mount-group${cls}">
      <header><strong>${p.label}</strong><button type="button" data-reset="${p.id}">重置</button></header>
      <div class="dock-mount-rows">${rows}</div>
    </div>`;
  }).join("");

  // 改一格即写覆盖；3D 模型与单点测距射线**下一帧**就会跟着动（它们在帧循环里读同一份覆盖表）。
  dockMountsBox.querySelectorAll("input[data-mount]").forEach((input) => {
    input.addEventListener("change", () => {
      const { mount: id, key, index } = input.dataset;
      sensorMountOverrides = applyMountEdit(sensorMountOverrides, id, key, Number(index), input.value);
      // 值被挡掉时（空串 / 非数字）把输入框拉回**真实**值，免得显示与状态不一致。
      const truth = sensorMount(id, sensorMountOverrides);
      input.value = truth[key][Number(index)];
      syncMountGroupFlag(id);
    });
  });
  dockMountsBox.querySelectorAll("button[data-reset]").forEach((button) => {
    button.addEventListener("click", () => {
      const next = { ...sensorMountOverrides };
      delete next[button.dataset.reset];
      sensorMountOverrides = next;
      renderDockMounts();
    });
  });
}

/** 重画某一个传感器那组的"已改过"标记（重置按钮的可见反馈）。 */
function syncMountGroupFlag(id) {
  const input = dockMountsBox?.querySelector(`input[data-mount="${id}"]`);
  const group = input?.closest(".dock-mount-group");
  if (group) group.classList.toggle("overridden", isMountOverridden(id, sensorMountOverrides));
}

if (dockRoot) dockRoot.hidden = !dock.visible;
renderDockPlugins();
renderDockSources();
renderDockMounts();
if (dockSourceSelect) {
  dockSourceSelect.addEventListener("change", () => { dock.source = dockSourceSelect.value; });
}
const dockToggleBtn = document.querySelector("#dockToggle");
if (dockToggleBtn && dockRoot) {
  dockToggleBtn.addEventListener("click", () => {
    dock.collapsed = !dock.collapsed;
    dockRoot.classList.toggle("collapsed", dock.collapsed);
    dockToggleBtn.textContent = dock.collapsed ? "+" : "−";
  });
}
const LATEST_POLICY_POLL_MS = 20000;
const MAX_PAYLOAD_KG = 70;

const elements = {
  viewer: document.querySelector("#viewer"),
  loading: document.querySelector("#loading"),
  loadingText: document.querySelector("#loadingText"),
  loadingBar: document.querySelector("#loadingBar"),
  terrainSelect: document.querySelector("#terrainSelect"),
  robotSelect: document.querySelector("#robotSelect"),
  modelSelect: document.querySelector("#modelSelect"),
  policySelect: document.querySelector("#policySelect"),
  configLink: document.querySelector("#configLink"),
  trainLink: document.querySelector("#trainLink"),
  playButton: document.querySelector("#playButton"),
  resetButton: document.querySelector("#resetButton"),
  mobileControlsToggle: document.querySelector("#mobileControlsToggle"),
  mobileJoystick: document.querySelector("#mobileJoystick"),
  mobileJoystickKnob: document.querySelector("#mobileJoystickKnob"),
  engineStatus: document.querySelector("#engineStatus"),
  policyStatus: document.querySelector("#policyStatus"),
  modelSubtitle: document.querySelector("#modelSubtitle"),
  jobLabel: document.querySelector("#jobLabel"),
  robotLabel: document.querySelector("#robotLabel"),
  modelLabel: document.querySelector("#modelLabel"),
  policyHealthLabel: document.querySelector("#policyHealthLabel"),
  policyHealthChecks: document.querySelector("#policyHealthChecks"),
  policyUpdatePrompt: document.querySelector("#policyUpdatePrompt"),
  policyUpdateText: document.querySelector("#policyUpdateText"),
  policyUpdateButton: document.querySelector("#policyUpdateButton"),
  cmdVx: document.querySelector("#cmdVx"),
  cmdVy: document.querySelector("#cmdVy"),
  cmdYaw: document.querySelector("#cmdYaw"),
  cmdJumpMetric: document.querySelector("#cmdJumpMetric"),
  cmdJump: document.querySelector("#cmdJump"),
  velVx: document.querySelector("#velVx"),
  velVy: document.querySelector("#velVy"),
  velYaw: document.querySelector("#velYaw"),
  baseHeight: document.querySelector("#baseHeight"),
  contacts: document.querySelector("#contacts"),
  gaitControl: document.querySelector("#gaitControl"),
  gaitToggle: document.querySelector("#gaitToggle"),
  gaitToggleState: document.querySelector("#gaitToggleState"),
  payloadMass: document.querySelector("#payloadMass"),
  payloadMassLabel: document.querySelector("#payloadMassLabel"),
  comOffsetSummary: document.querySelector("#comOffsetSummary"),
  comOffsetSliders: Array.from(document.querySelectorAll("[data-com-axis]")),
  comOffsetValues: Array.from(document.querySelectorAll("[data-com-value]")),
  terrainFriction: document.querySelector("#terrainFriction"),
  terrainFrictionLabel: document.querySelector("#terrainFrictionLabel"),
  imuAxisSummary: document.querySelector("#imuAxisSummary"),
  imuAxisToggles: Array.from(document.querySelectorAll("[data-imu-vector][data-imu-axis]")),
  signalDelaySummary: document.querySelector("#signalDelaySummary"),
  motorDelayToggle: document.querySelector("#motorDelayToggle"),
  motorDelaySteps: document.querySelector("#motorDelaySteps"),
  imuDelayToggle: document.querySelector("#imuDelayToggle"),
  imuDelaySteps: document.querySelector("#imuDelaySteps"),
  jumpCommandControl: document.querySelector("#jumpCommandControl"),
  jumpHeightLabel: document.querySelector("#jumpHeightLabel"),
  jumpHeightButtons: Array.from(document.querySelectorAll("[data-jump-height]")),
  cruiseButtons: Array.from(document.querySelectorAll("[data-cruise-speed]")),
  expertBars: document.querySelector("#expertBars"),
  rollBar: document.querySelector("#rollBar"),
  pitchBar: document.querySelector("#pitchBar"),
  rollVal: document.querySelector("#rollVal"),
  pitchVal: document.querySelector("#pitchVal"),
  expertPanel: document.querySelector("#expertPanel"),
  dominantExpert: document.querySelector("#dominantExpert"),
  followToggle: document.querySelector("#followToggle"),
  flipVisualToggle: document.querySelector("#flipVisualToggle"),
  collisionToggle: document.querySelector("#collisionToggle"),
  wireToggle: document.querySelector("#wireToggle"),
  simClock: document.querySelector("#simClock"),
  perfStats: document.querySelector("#perfStats"),
  fitViewButton: document.querySelector("#fitViewButton"),
  trailToggle: document.querySelector("#trailToggle"),
  velocityCommandControl: document.querySelector("#velocityCommandControl"),
  velCmdVx: document.querySelector("#velCmdVx"),
  velCmdVy: document.querySelector("#velCmdVy"),
  velCmdYaw: document.querySelector("#velCmdYaw"),
  velCmdEnable: document.querySelector("#velCmdEnable"),
  velCmdVxMax: document.querySelector("#velCmdVxMax"),
  velCmdVyMax: document.querySelector("#velCmdVyMax"),
  velCmdYawMax: document.querySelector("#velCmdYawMax"),
  velCmdVxMaxVal: document.querySelector("#velCmdVxMaxVal"),
  velCmdVyMaxVal: document.querySelector("#velCmdVyMaxVal"),
  velCmdYawMaxVal: document.querySelector("#velCmdYawMaxVal"),
  velCmdVxVal: document.querySelector("#velCmdVxVal"),
  velCmdVyVal: document.querySelector("#velCmdVyVal"),
  velCmdYawVal: document.querySelector("#velCmdYawVal"),
  velCmdZero: document.querySelector("#velCmdZero"),
  keys: {
    KeyW: document.querySelector("#keyW"),
    KeyS: document.querySelector("#keyS"),
    KeyA: document.querySelector("#keyA"),
    KeyD: document.querySelector("#keyD"),
    KeyQ: document.querySelector("#keyQ"),
    KeyE: document.querySelector("#keyE"),
  },
};

const sim = {
  mujoco: null,
  model: null,
  data: null,
  scene: null,
  camera: null,
  option: null,
  perturb: null,
  objGeom: 5,
  geomType: null,
  policy: null,
  policyInfo: null,
  policyLoading: false,
  recurrentState: Object.create(null),
  policyStateEpoch: 0,
  platformConfig: null,
  platformRevision: "",
  pendingPolicyUpdate: null,
  latestPolicyTimer: null,
  latestPolicyChecking: false,
  assetRoot: "/working",
  browserLightweight: false,
  history: new Float32Array(5 * CONFIG.numObs),
  obs: new Float32Array(CONFIG.numObs),
  action: new Float32Array(CONFIG.numActions),
  appliedAction: new Float32Array(CONFIG.numActions),
  filteredAction: new Float32Array(CONFIG.numActions),
  targetDofPos: new Float32Array(CONFIG.defaultAngles),
  targetDofVel: new Float32Array(CONFIG.numActions),
  pendingTargetDofPos: new Float32Array(CONFIG.defaultAngles),
  pendingTargetDofVel: new Float32Array(CONFIG.numActions),
  motorTargetPending: false,
  motorDelayRemaining: 0,
  imuSamples: [],
  weights: new Float32Array(8),
  estimatedVel: new Float32Array(3),
  latent: new Float32Array(32),
  cmd: new Float32Array([0.0, 0.0, 0.0, 0.68]),
  targetCmd: new Float32Array([0.0, 0.0, 0.0, 0.68]),
  counter: 0,
  gaitElapsedS: 0,
  gaitActive: false,
  accumulator: 0,
  paused: false,
  policyEnabled: PAGE_PARAMS.get("policy") !== "off",
  ready: false,
  // 感知导航（H3）：URL ?nav=<map_id> 时由服务端 /api/navigation/plan 装配，浏览器只跟随
  navigation: null,
  // H11 候选扇形：候选由服务端算（/api/navigation/local-plan），浏览器只成形与上色（?fan=0 可关）
  dvaFan: null,
  loadingTerrain: false,
  pendingTerrain: "",
  currentTerrain: "",
  qpos: null,
  qvel: null,
  ctrl: null,
  actuatorIds: [],
  jointQposAdr: [],
  jointDofAdr: [],
  baseBodyId: -1,
  baseBodyMassKg: 0,
  baseBodyComLocal: new Float64Array(3),
  jumpPulseDuration: 0,
  jumpPulseUntil: 0,
  jumpStartedAt: 0,
  jumpActive: false,
  jumpStartPending: false,
  g1PhaseS: 0,
};

const view = {
  scene: null,
  camera: null,
  renderer: null,
  controls: null,
  geoms: [],
  geometryCache: new Map(),
  materials: new Set(),
  followTarget: new THREE.Vector3(0, 0, 0.35),
  lastClockUpdate: performance.now(),
  frames: 0,
  simSteps: 0,
  fps: 0,
  simRate: 0,
  frameErrorCount: 0,
  trail: null,
  dragArrow: null,
};

const input = {
  keys: new Set(),
  // 「运动指令」滑条（vxSpeedLimit）已从面板移除；键盘 WASD/摇杆的前进速度
  // 固定 1.0 m/s（与原滑条默认值一致），速度指令滑条不受影响。
  vxSpeedLimit: 1,
  gaitEnabled: PAGE_PARAMS.get("gait") !== "0",
  payloadMassKg: 0,
  comOffsetM: new Float64Array(3),
  terrainFriction: STAIR_SURFACE_FRICTION,
  terrainFrictionOverride: null,
  imuAxisSigns: {
    angular: new Float32Array([1, 1, 1]),
    gravity: new Float32Array([1, 1, 1]),
  },
  motorDelayEnabled: false,
  motorDelayMaxSteps: 2,
  motorDelaySampleSteps: 0,
  imuDelayEnabled: false,
  imuDelayMaxSteps: 2,
  imuDelaySampleSteps: 0,
  cruiseVx: null,
  joystickPointer: null,
  joystickForward: 0,
  joystickTurn: 0,
  // 速度指令滑条直连策略（item 10）："启用"默认勾选 = 滑条默认接管 idle 指令。
  manualCmd: new Float32Array(3),
  manualCmdActive: true,
  velocityCmdTouched: false,
  // 鼠标拖拽施力（item 9）：move 只记 NDC，力在物理步内写入 xfrc_applied。
  drag: null,
};
const debugStateNode = DEBUG_ENABLED ? document.createElement("script") : null;
if (debugStateNode) {
  debugStateNode.id = "__sim2simDebugState";
  debugStateNode.type = "application/json";
  document.body.append(debugStateNode);
}

// Observation builder registry -- extracted to obs/observation_builders.js so
// adding a new policy observation contract no longer grows this god file.
const OBSERVATION = createObservationSystems({
  CONFIG,
  sim,
  input,
  elements,
  readImuSample,
  jointQpos,
  jointQvel,
  clamp,
  finiteNumber,
  jointGroup,
  enumValue,
  isJumpCommandActive,
  heightCommandIndex,
  bucketHeightCommand,
  observationLayout,
  publishDebugState,
  WHEEL_LEG_GAIT_OBSERVATION,
  WHEEL_LEG_GAIT_PERIOD_S,
  WHEEL_LEG_JUMP_OBSERVATION,
  WHEEL_LEG_JUMP_PERIOD_S,
});
init();

// Embedded Workbench pages can be laid out after this document starts. Accept
// an explicit size from the parent and remeasure locally so WebGL never keeps
// its default backing buffer while the iframe itself is full size.
window.addEventListener("message", (event) => {
  if (event.source !== window.parent || event.origin !== window.location.origin) return;
  if (event.data?.type !== "legged-studio:resize") return;
  resize(Number(event.data.width), Number(event.data.height));
});

async function init() {
  try {
    initExpertBars();
    initThree();
    bindUi();
    applyViewerStateFromUrl();
    applyDeterministicReplayFromUrl();
    await loadRobotOptions();
  await initNavigationFromUrl();
    setStatus(elements.engineStatus, "MuJoCo 初始化中", "pending");
    setStatus(elements.policyStatus, "ONNX 策略初始化中", "pending");
    sim.platformConfig = await loadPlatformConfig();
    applyPlatformLabels(sim.platformConfig);
    if (elements.robotSelect) {
      // URL_ROBOT is a normalized key ("go2", "zex_w") that may not equal any
      // option value ("unitree_go2", "zex-w"); match the way loadRobotOptions
      // does, otherwise the dropdown renders blank for Go2 and ZEX-W.
      // 无 URL/平台指定时不预设机器人——默认项由包 manifest 的 browser_default 决定。
      const requested = URL_ROBOT || sim.platformConfig?.sim?.robot || "";
      const match = requested && Array.from(elements.robotSelect.options).find(
        (option) => option.value === requested || normalizeRobotParam(option.value) === normalizeRobotParam(requested),
      );
      if (match) elements.robotSelect.value = match.value;
    }

    await setLoadingPainted(0.12, "① 加载 MuJoCo WASM...");
    const tMujoco = performance.now();
    sim.mujoco = await loadMujoco({
      locateFile: (path) => (path.endsWith(".wasm") ? "./vendor/mujoco/mujoco.wasm" : path),
    });
    console.log(`[sim2sim] ✔ MuJoCo WASM ${(performance.now() - tMujoco).toFixed(0)}ms`);
    sim.objGeom = enumValue(sim.mujoco.mjtObj.mjOBJ_GEOM);
    sim.geomType = makeGeomTypes(sim.mujoco);
    setupMujocoFs(sim.mujoco);

    const hasPlatformAssets = Boolean(sim.platformConfig?.sim?.asset_package?.files?.length);
    applyRuntimeConfig(sim.platformConfig);
    applyTerrainOptions(sim.platformConfig);

    await setLoadingPainted(0.28, hasPlatformAssets ? "② 加载机器人 MJCF 与网格资源..." : "② 加载 Go2 MJCF 与网格资源...");
    const tAssets = performance.now();
    await loadMujocoAssets();
    console.log(`[sim2sim] ✔ loadMujocoAssets ${(performance.now() - tAssets).toFixed(0)}ms`);

    const tScene = await setLoadingPainted(0.62, "④ 编译 MuJoCo 场景...");
    // Always start with the package's explicitly declared flat scene when
    // available. Complex terrains are opt-in after the model is visible.
    const initialScene = sim.platformConfig?.sim?.asset_package?.scenes?.find((name) => /(^|\/)flat\.xml$/i.test(name))
      || elements.terrainSelect.value;
    elements.terrainSelect.value = initialScene;
    await loadTerrain(initialScene);
    console.log(`[sim2sim] ✔ MuJoCo scene ${(performance.now() - tScene).toFixed(0)}ms`);

    // Policy loading is deliberately independent from scene compilation. A
    // missing or incompatible ONNX runtime must not leave a blank viewport.
    if (!sim.platformConfig?.policy?.disabled && sim.platformConfig?.policy?.onnx_url) {
      const tOnnx = await setLoadingPainted(0.86, "⑤ 加载 ONNX 策略...");
      try {
        await loadPolicyFromConfig(sim.platformConfig, true);
        console.log(`[sim2sim] ✔ ONNX policy ${(performance.now() - tOnnx).toFixed(0)}ms`);
      } catch (error) {
        console.error("[sim2sim] policy unavailable; continuing in pose-hold mode", error);
        sim.policy = null;
        sim.policyInfo = null;
        sim.policyEnabled = false;
        sim.paused = VIEWER_ONLY;
        const described = describeLoadError(error);
        setStatus(elements.policyStatus, `策略不可用: ${described?.message || error}`, "error");
      }
    } else {
      await loadPolicyFromConfig(sim.platformConfig, true);
    }

    await setLoadingPainted(1, "⑥ 启动仿真...");
    elements.loading.classList.add("is-hidden");
    startPlatformPolling();
    startLatestPolicyPolling();
    requestAnimationFrame(frame);
  } catch (error) {
    console.error(error);
    const described = describeLoadError(error);
    setStatus(elements.engineStatus, "MuJoCo 错误", "error");
    setStatus(elements.policyStatus, "策略错误", "error");
    showLoadingError(described?.message || String(described || error));
    await checkLatestPolicyUpdate({ quiet: true });
  }
}

async function loadRobotOptions() {
  if (!elements.robotSelect) return;
  try {
    const response = await fetch("/api/robots/presets", { cache: "no-store" });
    if (!response.ok) return;
    const payload = await response.json();
    const presets = Array.isArray(payload?.presets) ? payload.presets : [];
    if (!presets.length) return;
    const requested = PAGE_PARAMS.get("robot") || "";
    elements.robotSelect.innerHTML = "";
    for (const preset of presets) {
      const option = document.createElement("option");
      option.value = String(preset.robot_id || "");
      option.textContent = String(preset.family || preset.robot_id || "Robot");
      option.disabled = !preset.robot_package?.model?.path;
      option.dataset.browserDefault = preset.robot_package?.browser_default ? "true" : "false";
      elements.robotSelect.append(option);
    }
    const match = requested && Array.from(elements.robotSelect.options).find(
      (option) => option.value === requested || normalizeRobotParam(option.value) === normalizeRobotParam(requested),
    );
    if (match) elements.robotSelect.value = match.value;
    else {
      // 默认机器人由包 manifest 声明（browser_default），不再按机器人 ID 硬编码
      const defaultOption = Array.from(elements.robotSelect.options).find(
        (option) => option.dataset.browserDefault === "true",
      );
      if (defaultOption) elements.robotSelect.value = defaultOption.value;
      else if (elements.robotSelect.options.length) elements.robotSelect.selectedIndex = 0;
    }
  } catch (error) {
    console.warn("robot package list unavailable; keeping static simulation options", error);
  }
}

async function loadPlatformConfig() {
  // Public demos use a dedicated allowlisted endpoint; private runs keep the
  // owner-scoped /api/play/{run_id} contract.
  // Shape: { run_id, robot{joint_order, default_joint_angles, control}, policy{onnx_url, contract} }
  const params = new URLSearchParams(window.location.search);
  const demoId = params.get("demo") || "";
  const runId = params.get("run_id") || params.get("job_id") || "";
  const policyId = params.get("policy") || "";
  const selectedRobot = URL_ROBOT || normalizeRobotParam(elements.robotSelect?.value || "");
  // A package-backed browser session is the default for every robot. The
  // historical /api/play/latest path is only used when an explicit run/demo
  // is supplied; otherwise it cannot provide the selected package model.
  if (!runId && !demoId && selectedRobot) {
    const response = await fetch(`/api/simulation/browser-config/${encodeURIComponent(elements.robotSelect?.value || selectedRobot)}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`browser simulation package unavailable: ${selectedRobot}`);
    const config = await response.json();
    if (policyId === "off") {
      config.policy = { disabled: true, onnx_url: "", contract: config.policy?.contract || {} };
    }
    const requestedPolicy = PAGE_PARAMS.get("policy") || "";
    const policies = config?.sim?.asset_package?.policies || [];
    const selectedPolicy = policies.find((item) => item.id === requestedPolicy || item.path === requestedPolicy || item.url === requestedPolicy);
    if (selectedPolicy) {
      config.policy = {
        ...(config.policy || {}),
        id: selectedPolicy.id || config.policy?.id,
        disabled: false,
        onnx_url: selectedPolicy.url || config.policy?.onnx_url || "",
        encoder_url: selectedPolicy.encoder_url || config.policy?.encoder_url || null,
        contract: { ...(config.policy?.contract || {}), ...selectedPolicy.contract },
      };
    }
    return applyRobotOverride(config);
  }
  const base = demoId
    ? `/api/play/demos/${encodeURIComponent(demoId)}`
    : runId ? `/api/play/${encodeURIComponent(runId)}` : "/api/play/latest";
  if (!runId && !demoId) {
    return applyRobotOverride({
      run_id: null,
      robot: { joint_order: [], default_joint_angles: {}, control: { stiffness: {}, damping: {}, action_scale: 0.25, decimation: 10 } },
      policy: { disabled: true, onnx_url: "", contract: {} },
    });
  }
  try {
    const query = new URLSearchParams({ t: String(Date.now()) });
    if (runId && policyId && policyId !== "off") query.set("policy", policyId);
    const response = await fetch(`${base}?${query.toString()}`, { cache: "no-store", credentials: "include" });
    if (!response.ok) throw new Error(await responseErrorMessage(response));
    const config = await response.json();
    if (runId) ensureRunPolicyPlayable(config, runId);
    else if (demoId) ensureRunPolicyPlayable(config, config?.run_id || "");
    return applyRobotOverride(config);
  } catch (error) {
    if (runId || demoId) {
      const target = runId ? `run ${runId}` : `Demo ${demoId}`;
      throw new Error(`无法加载 ${target} 的 Sim2Sim 配置：${error?.message || error}`);
    }
    console.warn("platform play config unavailable; using manual MuJoCo mode", error);
    return applyRobotOverride({
      run_id: runId || null,
      robot: {
        joint_order: [],
        default_joint_angles: {},
        control: {
          stiffness: { hip: 20, thigh: 20, calf: 20 },
          damping: { hip: 0.5, thigh: 0.5, calf: 0.5 },
          action_scale: 0.25,
          decimation: 10,
        },
      },
      policy: { disabled: true, onnx_url: "", contract: {} },
    });
  }
}

function applyRobotOverride(config) {
  const robotKey = URL_ROBOT || normalizeRobotParam(config?.sim?.robot || "");
  if (robotKey !== "fsdog1") return config;
  const next = {
    ...(config || {}),
    robot: {
      ...FSDOG_ROBOT,
      ...(config?.robot || {}),
      name: FSDOG_ROBOT.name,
      vendor: FSDOG_ROBOT.vendor,
      morphology: FSDOG_ROBOT.morphology,
      joint_order: [...FSDOG_ROBOT.joint_order],
      default_joint_angles: { ...FSDOG_ROBOT.default_joint_angles },
      control: { ...FSDOG_ROBOT.control, ...(config?.robot?.control || {}) },
    },
    sim: {
      ...(config?.sim || {}),
      robot: "fsdog1",
      asset: "fsdog1_simplified",
    },
  };
  const control = next.robot.control || {};
  next.robot.control = {
    ...control,
    stiffness: { ...FSDOG_ROBOT.control.stiffness, ...(control.stiffness || {}) },
    damping: { ...FSDOG_ROBOT.control.damping, ...(control.damping || {}) },
    torque_limits: { ...FSDOG_ROBOT.control.torque_limits, ...(control.torque_limits || {}) },
  };
  return next;
}

async function responseErrorMessage(response) {
  const fallback = `${response.status} ${response.statusText}`;
  try {
    const body = await response.json();
    if (body?.detail?.reason === "legacy_overwritten_onnx") {
      const selectedIter = PAGE_PARAMS.get("iter");
      const iterText = selectedIter ? `第 ${selectedIter} 轮的` : "这个旧";
      return `${iterText} ONNX 已经被后续导出覆盖；请切到最新策略，或用新版 worker 重新训练生成按轮次保存的 ONNX。`;
    }
    const message = body?.error || body?.message || body?.detail?.message || body?.detail;
    if (typeof message === "string" && message.trim()) return message;
    return fallback;
  } catch (_) {
    return fallback;
  }
}

function ensureRunPolicyPlayable(config, runId) {
  const policy = config?.policy || null;
  if (!policy?.onnx_url) {
    throw new Error(policyDiagnosticMessage(config, "此任务没有可运行的 ONNX 策略。"));
  }
  const health = String(policy.health?.status || "pass").toLowerCase();
  if (!["pass", "ready"].includes(health)) {
    throw new Error(policyDiagnosticMessage(config, `ONNX 健康状态为 ${health}，请从训练页选择健康的导出策略。`));
  }
  if (config?.run_id && String(config.run_id) !== String(runId)) {
    throw new Error(`返回的任务编号不匹配：${config.run_id}`);
  }
}

function policyDiagnosticMessage(config, fallback) {
  const diagnostics = config?.policy_diagnostics || {};
  const health = diagnostics.health || config?.policy?.health || {};
  const checks = Array.isArray(health.checks) ? health.checks : [];
  const failed = checks.find((check) => !check?.ok);
  const parts = [
    diagnostics.message || fallback,
    diagnostics.checkpoint_iteration !== undefined && diagnostics.checkpoint_iteration !== null
      ? `第 ${diagnostics.checkpoint_iteration} 轮`
      : "",
    diagnostics.reason ? `原因 ${diagnostics.reason}` : "",
    diagnostics.diagnostic_policy_id ? `策略 ${diagnostics.diagnostic_policy_id}` : "",
    failed ? `${failed.id || "检查项"}: ${failed.message || "失败"}` : "",
  ];
  return parts.filter(Boolean).join(" | ");
}

async function loadPolicyFromConfig(config, initial = false) {
  const policy = config?.policy || {};
  // Manual simulation must not fall back to a bundled demo policy.
  const url = policy.onnx_url || "";
  if (!url) {
    sim.policy = null;
    sim.policyInfo = null;
    sim.policyEnabled = false;
    setStatus(elements.policyStatus, "No policy - manual mode", "ready");
    return false;
  }
  await ensureOrtRuntime();
  const contract = policy.contract || {};
  const revision = platformPolicyRevision(config, url);
  if (!initial && revision === sim.platformRevision) return false;
  setStatus(elements.policyStatus, initial ? "正在加载策略" : "正在加载新策略", "pending");
  sim.policyLoading = true;
  let session;
  let modelBytes;
  if (contract.motion_params?.motion_csv) {
    try {
      // 包内相对路径必须相对 asset_package.base_url 解析：base_url 由后端用
      // canonical robot id（unitree_go2）拼好。禁止读 config.robot_id —— 后端
      // browser-config 不下发该字段，曾退化成 ".../browser-package//simulation/
      // policies/xxx_motion.csv"（robot 段为空）→ 404 → 404 响应体被当 CSV 解析
      // → dofPositions 为空 → 每帧 jointPos 崩溃、仿真 time 永久停在 0。
      const packageBase = new URL(config?.sim?.asset_package?.base_url || "./", window.location.href);
      const csvUrl = new URL(
        String(contract.motion_params.motion_csv).replace(/^\/+/, ""),
        packageBase,
      ).toString();
      const response = await fetch(cacheBustedUrl(csvUrl, revision), { cache: "no-store" });
      if (!response.ok) throw new Error(`motion csv HTTP ${response.status}: ${csvUrl}`);
      sim.motionLoader = new MotionLoader(await response.text(), contract.motion_params);
      // 参考运动走完后的行为：默认【钳制保持末帧】（上游 rl_sdk
      // `motion_time = min(rl_time, duration)`）；motion_params.loop=true 时循环
      // 重放，用于需要连续演示的周期/可重放技能。
      CONFIG.motionLoop = contract.motion_params.loop === true
        || contract.motion_params.motion_loop === true;
      OBSERVATION.resetMotionTime();
    } catch (err) {
      console.warn("[sim2sim] motion csv load failed:", err);
      sim.motionLoader = null;
      CONFIG.motionLoop = false;
    }
  } else {
    sim.motionLoader = null;
    CONFIG.motionLoop = false;
  }
  try {
    // 手动 fetch(cache:"no-store") 拿字节再交给 ort：彻底绕开 HTTP 缓存里
    // 残留的旧版（带外部数据引用）ONNX 字节——go2w 曾因此报
    // 'Failed to load external data file "policy.onnx.data"'。
    modelBytes = await fetchPolicyModelBytes(cacheBustedUrl(url, `${revision}-t${Date.now()}`));
    session = await ort.InferenceSession.create(modelBytes, {
      executionProviders: ["wasm"],
      graphOptimizationLevel: "basic",
    });
  } finally {
    sim.policyLoading = false;
  }
  const previousPolicy = sim.policy;
  sim.policy = session;
  sim.policyInfo = inspectPolicy(session, contract);
  // 深度策略（PIE）：浏览器端 raycast 渲染深度历史。
  sim.pieDepth = sim.policyInfo.depthName ? createPieDepth({ sim, contract }) : null;
  sim.depthHistory = sim.pieDepth ? [] : null;
  sim.depthCounter = 0;
  // encoder+policy 双模型（TRON1 等）：额外加载 encoder 会话。
  try { await sim.encoderSession?.release?.(); } catch (error) { console.warn("encoder release failed", error); }
  sim.encoderSession = null;
  if (policy.encoder_url) {
    const encBytes = await fetchPolicyModelBytes(cacheBustedUrl(policy.encoder_url, `${revision}-enc-${Date.now()}`));
    sim.encoderSession = await ort.InferenceSession.create(encBytes, {
      executionProviders: ["wasm"],
      graphOptimizationLevel: "basic",
    });
  }
  resetPolicyState();
  // The MoE expert panel only makes sense for policies that emit per-expert
  // weights. NP3O (and other plain actors) don't, so hide it for them.
  if (elements.expertPanel) elements.expertPanel.classList.add("is-hidden");
  sim.platformConfig = config;
  sim.platformRevision = revision;
  applyRuntimeConfig(config);
  resizeObservationBuffers(
    sim.policyInfo.baseObsSize || CONFIG.numObs,
    sim.policyInfo.historyFrames || contract.history_len || 5,
  );
  // encoder 历史缓冲：TRON1 的 encoder 输入是单帧 obs 的 oldest→newest 历史。
  sim.encoderFrames = sim.encoderSession ? Math.max(1, Math.round(Number(contract?.tron1?.history) || 10)) : 0;
  sim.encoderHistory = sim.encoderFrames ? new Float32Array(sim.encoderFrames * CONFIG.numObs) : null;
  CONFIG.encoderChain = !!sim.encoderSession;
  const metaProblem = validatePolicyMetadata(modelBytes);
  applyPlatformLabels(config);
  setStatus(
    elements.policyStatus,
    metaProblem ? `已就绪 · 元数据不匹配（${metaProblem}）` : `${sim.policyInfo.mode} 已就绪`,
    metaProblem ? "error" : "ready",
  );
  if (previousPolicy && previousPolicy !== session) {
    try { await previousPolicy.release?.(); } catch (error) { console.warn("policy release failed", error); }
  }
  return true;
}

/** 极简 ONNX protobuf 扫描：只提取顶层 metadata_props（field 14），其余字段按 wire type 跳过。
 * vendored onnxruntime-web 是精简版、没有 InferenceSession.metadata API，所以自己读模型字节。 */
function readOnnxMetadataBytes(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const decoder = new TextDecoder();
  const cursor = { pos: 0 };
  const readVarint = () => {
    let result = 0, shift = 0;
    for (;;) {
      const b = view.getUint8(cursor.pos);
      cursor.pos += 1;
      result += (b & 0x7f) * Math.pow(2, shift);
      if (!(b & 0x80)) return result;
      shift += 7;
    }
  };
  const readSlice = () => {
    const len = readVarint();
    const slice = bytes.subarray(cursor.pos, cursor.pos + len);
    cursor.pos += len;
    return slice;
  };
  const readString = (slice) => decoder.decode(slice);
  const meta = {};
  while (cursor.pos < bytes.length) {
    const tag = readVarint();
    const field = tag >>> 3;
    const wire = tag & 7;
    if (wire === 0) {
      readVarint();
    } else if (wire === 1) {
      cursor.pos += 8;
    } else if (wire === 5) {
      cursor.pos += 4;
    } else if (wire === 2) {
      const slice = readSlice();
      if (field !== 14) continue;
      // StringStringEntryProto: key = field 1, value = field 2（都是 length-delim 字符串）
      const inner = { pos: 0 };
      const innerVarint = () => {
        let result = 0, shift = 0;
        for (;;) {
          const b = slice[inner.pos];
          inner.pos += 1;
          result += (b & 0x7f) * Math.pow(2, shift);
          if (!(b & 0x80)) return result;
          shift += 7;
        }
      };
      let key = null;
      let value = null;
      while (inner.pos < slice.length) {
        const tag2 = innerVarint();
        if ((tag2 & 7) !== 2) { inner.pos = slice.length; break; }
        const len2 = innerVarint();
        const s = readString(slice.subarray(inner.pos, inner.pos + len2));
        inner.pos += len2;
        if ((tag2 >>> 3) === 1) key = s;
        else if ((tag2 >>> 3) === 2) value = s;
      }
      if (key !== null) meta[key] = value ?? "";
    } else {
      throw new Error(`ONNX protobuf: 未知 wire type ${wire} @${cursor.pos}`);
    }
  }
  return meta;
}

/** 元数据契约校验：导出时盖章的 joint_names/clip_actions 与当前契约比对。
 * 无盖章的旧策略静默跳过；返回问题描述（用于就绪状态提示），一致返回 null。 */
function validatePolicyMetadata(modelBytes) {
  try {
    const meta = readOnnxMetadataBytes(modelBytes);
    const jointNamesCsv = meta.joint_names;
    if (!jointNamesCsv) return null;
    const stamped = jointNamesCsv.split(",").map((s) => s.trim());
    const expected = (CONFIG.actionJointOrder || CONFIG.jointOrder || []).map((s) => String(s));
    if (!expected.length) return null;
    if (stamped.length !== expected.length) {
      return `关节数 ${stamped.length} ≠ 契约 ${expected.length}`;
    }
    const first = stamped.findIndex((name, i) => name !== expected[i]);
    if (first >= 0) return `槽 ${first}: 元数据=${stamped[first]} 契约=${expected[first]}`;
    console.info(`[sim2sim] ✔ 策略元数据与契约一致（${stamped.length} 关节，来源=${meta.source || "stamped"}）`);
    // joint_ids_map：策略槽位 → 电机 ID 排列；非恒等映射时提示（浏览器按槽位直写执行器，
    // 硬件部署需要该排列，浏览器语义不受影响但值得可见）。
    if (meta.joint_ids_map) {
      try {
        const map = meta.joint_ids_map.split(",").map((s) => Number(s.trim()));
        const identity = map.every((v, i) => v === i);
        if (!identity) console.info(`[sim2sim] 策略携带非恒等 joint_ids_map（硬件部署用）：[${map.join(",")}]`);
      } catch (_) { /* 忽略解析失败 */ }
    }
    return null;
  } catch (error) {
    console.warn("[sim2sim] policy metadata validation skipped", error);
    return null;
  }
}

async function ensureOrtRuntime() {
  if (ort) return ort;
  const wrapperUrl = new URL("ort.wasm.min.mjs", ORT_DIST_URL);
  wrapperUrl.searchParams.set("v", ORT_RUNTIME_REVISION);
  ort = await import(wrapperUrl.href);

  const runtimeUrl = new URL("ort-wasm-simd-threaded.mjs", ORT_DIST_URL);
  runtimeUrl.searchParams.set("v", ORT_RUNTIME_REVISION);
  const wasmUrl = new URL("ort-wasm-simd-threaded.wasm", ORT_DIST_URL);
  wasmUrl.searchParams.set("v", ORT_RUNTIME_REVISION);
  ort.env.logLevel = "error";
  ort.env.wasm.wasmPaths = {
    "ort-wasm-simd-threaded.mjs": runtimeUrl.href,
    "ort-wasm-simd-threaded.wasm": wasmUrl.href,
  };
  ort.env.wasm.numThreads = 1;
  ort.env.wasm.proxy = false;
  return ort;
}

async function switchPolicy(policyId) {
  if (!sim.platformConfig || sim.policyLoading) return;
  const select = elements.policySelect;
  if (select) select.disabled = true;
  const previousConfig = sim.platformConfig;
  const previousPolicy = sim.policy;
  try {
    if (!policyId || policyId === "off") {
      sim.policy = null;
      sim.policyInfo = null;
      sim.policyEnabled = false;
      sim.platformRevision = "";
      sim.platformConfig = {
        ...previousConfig,
        policy: { ...(previousConfig.policy || {}), id: "off", disabled: true, onnx_url: "" },
      };
      resetPolicyState();
      resetSimulation();
      sim.paused = VIEWER_ONLY;
      elements.playButton.textContent = sim.paused ? "继续" : "暂停";
      applyPlatformLabels(sim.platformConfig);
      setStatus(elements.policyStatus, "无策略 · 姿态保持", "ready");
      try { await previousPolicy?.release?.(); } catch (error) { console.warn("policy release failed", error); }
    } else {
      const candidates = previousConfig?.sim?.asset_package?.policies || [];
      const selected = candidates.find((item) => (item.id || item.url || item.path) === policyId);
      if (!selected) throw new Error(`包内不存在策略: ${policyId}`);
      const nextConfig = {
        ...previousConfig,
        policy: {
          ...(previousConfig.policy || {}),
          id: selected.id || policyId,
          disabled: false,
          onnx_url: selected.url,
          encoder_url: selected.encoder_url || null,
          health: { status: "pass", checks: [{ id: "package", ok: true, message: "Package policy manifest" }] },
          contract: { ...(previousConfig.policy?.contract || {}), ...(selected.contract || {}) },
        },
      };
      await loadPolicyFromConfig(nextConfig, false);
      sim.policyEnabled = true;
      resetSimulation();
    }
    const url = new URL(window.location.href);
    url.searchParams.set("policy", policyId || "off");
    history.replaceState(null, "", url);
  } catch (error) {
    console.error("policy switch failed", error);
    sim.platformConfig = previousConfig;
    sim.policy = previousPolicy;
    applyPlatformLabels(previousConfig);
    const described = describeLoadError(error);
    setStatus(elements.policyStatus, `策略切换失败: ${described?.message || error}`, "error");
  } finally {
    if (select) select.disabled = false;
  }
}

function platformPolicyRevision(config, url) {
  const policy = config?.policy || {};
  const contract = policy.contract || {};
  const robot = config?.robot || {};
  return JSON.stringify({
    run_id: config?.run_id || "",
    policy_id: policy.id || "",
    onnx_url: url || policy.onnx_url || "",
    checkpoint: policy.checkpoint || "",
    checkpoint_iteration: policy.checkpoint_iteration ?? null,
    obs_dim: contract.obs_dim ?? null,
    history_len: contract.history_len ?? null,
    action_dim: contract.action_dim ?? null,
    action_scale: contract.action_scale ?? null,
    observation_kind: contract.observation_kind || "",
    history_layout: contract.history_layout || "",
    onnx_inputs: contract.onnx_inputs || [],
    onnx_outputs: contract.onnx_outputs || [],
    joint_order: robot.joint_order || [],
  });
}

function inspectPolicy(session, contract = {}) {
  const inputNames = session.inputNames || tensorMetadataNames(session.inputMetadata);
  const outputNames = session.outputNames || tensorMetadataNames(session.outputMetadata);
  const HISTORY_INPUT_NAMES = ["history", "hist", "obs_hist", "proprio_history"];
  const historyName = inputNames.find((n) => HISTORY_INPUT_NAMES.includes(n)) || "";
  const hasHistory = Boolean(historyName);
  // 深度输入（PIE 等）：独立的 depth_history 张量，由浏览器 raycast 渲染。
  const depthName = inputNames.find((n) => /depth/i.test(n)) || "";
  const obsName = inputNames.includes("obs")
    ? "obs"
    : inputNames.find((n) => n !== historyName && n !== depthName) || inputNames[0];
  const actionName = outputNames.includes("act")
    ? "act"
    : outputNames.includes("action")
      ? "action"
      : outputNames.includes("actions")
        ? "actions"
        : outputNames[0];
  const weightsName = outputNames.includes("weights") ? "weights" : "";
  const estimatedVelName = outputNames.includes("estimated_vel") ? "estimated_vel" : "";
  const latentName = outputNames.includes("latent") ? "latent" : "";
  const nextHistoryName = outputNames.includes("next_history") ? "next_history" : "";
  const recurrentStates = inspectRecurrentStates(
    session,
    contract,
    inputNames,
    outputNames,
    [obsName, historyName],
  );
  const obsDims = tensorMetadataShape(session.inputMetadata, obsName, inputNames);
  const historyDims = hasHistory
    ? tensorMetadataShape(session.inputMetadata, historyName, inputNames)
    : [];
  const historyObsSize = hasHistory ? validObservationDim(historyDims[2]) : 0;
  const contractObsSize = validObservationDim(contract?.obs_dim);
  const baseObsSize = contractObsSize || historyObsSize || CONFIG.numObs;
  const contractHistoryFrames = validObservationDim(contract?.history_len);
  const flatHistorySize = !hasHistory
    && inputNames.length === 1
    && (["w1w_moe_cts", "zexw_53", WHEEL_LEG_GAIT_OBSERVATION].includes(contract?.observation_kind)
      || contract?.observation_kind === WHEEL_LEG_JUMP_OBSERVATION)
    && contractHistoryFrames > 1
    ? baseObsSize * contractHistoryFrames
    : 0;
  const obsSize = validObservationDim(obsDims[1]) || flatHistorySize || baseObsSize;
  const stackedFrames = !hasHistory && obsSize > baseObsSize && obsSize % baseObsSize === 0
    ? Math.round(obsSize / baseObsSize)
    : 0;
  // History frame count: read from model metadata if available, else fall back
  // to the policy contract, then by input name.  2D history（如 PIE
  // proprio_history [1,450]）没有帧维，帧数 = 展平长度 / 单帧维度。
  const flatHistoryInput = hasHistory && historyDims.length === 2;
  const historyDimFromModel = flatHistoryInput
    ? (baseObsSize > 0 ? Math.round(Number(historyDims[1]) / baseObsSize) : 0)
    : Number(historyDims[1]);
  const historyDimFromContract = Number(contract?.history_len);
  const historyFrames = hasHistory
    ? (Number.isFinite(historyDimFromModel) && historyDimFromModel > 0
        ? historyDimFromModel
        : (Number.isFinite(historyDimFromContract) && historyDimFromContract > 0
            ? Math.round(historyDimFromContract)
            : (historyName === "history" ? 5 : 10)))
    : stackedFrames;
  const historyFlatSize = flatHistoryInput ? Number(historyDims[1]) : 0;
  const mode = recurrentStates.length
    ? (depthName ? "recurrent-depth" : hasHistory ? "recurrent-history" : "recurrent")
    : hasHistory
      ? (weightsName ? "moe-history" : (nextHistoryName ? "fused-history" : "history"))
      : (stackedFrames ? "stacked-history" : "single-obs");
  const observationKind = contract?.observation_kind
    || (baseObsSize === 99 && hasHistory ? "quadrupedal_agility_ll" : "default");
  return {
    mode,
    observationKind,
    inputNames,
    outputNames,
    obsName,
    historyName,
    historyFrames,
    depthName,
    historyFlatSize,
    stackedFrames,
    actionName,
    weightsName,
    estimatedVelName,
    latentName,
    nextHistoryName,
    recurrentStates,
    obsSize,
    baseObsSize,
    historyObsSize,
  };
}

function inspectRecurrentStates(session, contract, inputNames, outputNames, excludedNames) {
  const excluded = new Set(excludedNames.filter(Boolean));
  const contractInputs = onnxIoByName(contract?.onnx_inputs);
  const contractOutputs = onnxIoByName(contract?.onnx_outputs);
  const usedOutputs = new Set();
  const states = [];
  for (const inputName of inputNames) {
    if (excluded.has(inputName)) continue;
    const outputName = recurrentOutputName(inputName, outputNames, usedOutputs);
    if (!outputName) continue;
    const inputShape = staticTensorShape(
      tensorMetadataShape(session.inputMetadata, inputName, inputNames),
      contractInputs[inputName]?.shape,
      inputName,
    );
    const outputShape = staticTensorShape(
      tensorMetadataShape(session.outputMetadata, outputName, outputNames),
      contractOutputs[outputName]?.shape,
      outputName,
    );
    if (tensorElementCount(inputShape) !== tensorElementCount(outputShape)) {
      throw new Error(`循环状态 ${inputName}/${outputName} 的输入输出尺寸不一致`);
    }
    states.push({
      inputName,
      outputName,
      shape: inputShape,
      type: recurrentTensorType(tensorMetadata(session.inputMetadata, inputName, inputNames)?.type),
      size: tensorElementCount(inputShape),
    });
    usedOutputs.add(outputName);
  }
  return states;
}

function tensorMetadataNames(metadata) {
  if (Array.isArray(metadata)) return metadata.map((item) => item?.name).filter(Boolean);
  return Object.keys(metadata || {});
}

function tensorMetadata(metadata, name, names = []) {
  if (Array.isArray(metadata)) {
    return metadata.find((item) => item?.name === name) || metadata[names.indexOf(name)] || null;
  }
  return metadata?.[name] || null;
}

function tensorMetadataShape(metadata, name, names = []) {
  const value = tensorMetadata(metadata, name, names);
  return value?.shape || value?.dimensions || [];
}

function onnxIoByName(items) {
  const result = {};
  if (!Array.isArray(items)) return result;
  for (const item of items) {
    if (item?.name) result[String(item.name)] = item;
  }
  return result;
}

function recurrentOutputName(inputName, outputNames, usedOutputs) {
  const legacyAliases = {
    h: ["he"],
    c: ["ce"],
  };
  const candidates = [
    `${inputName}_out`,
    `next_${inputName}`,
    `${inputName}_next`,
    // PIE 等：输入/输出成对命名 memory_h_in / memory_h_out
    ...(inputName.endsWith("_in") ? [`${inputName.slice(0, -3)}_out`] : []),
    ...(legacyAliases[inputName] || []),
    inputName,
  ];
  return candidates.find((name) => outputNames.includes(name) && !usedOutputs.has(name)) || "";
}

function staticTensorShape(metadataShape, contractShape, tensorName) {
  for (const candidate of [metadataShape, contractShape]) {
    if (!Array.isArray(candidate) || !candidate.length) continue;
    const shape = candidate.map((value) => Number(value));
    if (shape.every((value) => Number.isInteger(value) && value > 0)) return shape;
  }
  throw new Error(`循环状态 ${tensorName} 需要在 ONNX 或策略契约中提供静态 shape`);
}

function tensorElementCount(shape) {
  return shape.reduce((total, value) => total * value, 1);
}

function recurrentTensorType(value) {
  const type = String(value || "float32").toLowerCase();
  if (["float", "float32", "tensor(float)"].includes(type)) return "float32";
  if (["double", "float64", "tensor(double)"].includes(type)) return "float64";
  throw new Error(`暂不支持 ${value} 类型的循环状态；请将隐藏状态导出为 float32/float64`);
}

function allocateTensorData(type, size) {
  return type === "float64" ? new Float64Array(size) : new Float32Array(size);
}

function resetPolicyState() {
  sim.policyStateEpoch += 1;
  sim.recurrentState = Object.create(null);
  for (const state of sim.policyInfo?.recurrentStates || []) {
    sim.recurrentState[state.inputName] = allocateTensorData(state.type, state.size);
  }
  if (sim.encoderHistory) sim.encoderHistory.fill(0);
  sim.tron1GaitIndex = 0;
  if (sim.pieDepth) { sim.depthHistory = []; sim.depthCounter = 0; }
  OBSERVATION?.resetWujiGoal?.();
}

function updateRecurrentStates(output, info) {
  for (const state of info.recurrentStates || []) {
    const tensor = output[state.outputName];
    if (!tensor?.data || tensor.data.length !== state.size) {
      throw new Error(`策略输出缺少有效循环状态 ${state.outputName}`);
    }
    const next = allocateTensorData(state.type, state.size);
    next.set(tensor.data);
    sim.recurrentState[state.inputName] = next;
  }
}

function cacheBustedUrl(url, revision) {
  const absolute = new URL(url, window.location.href);
  absolute.searchParams.set("rev", revision || Date.now());
  return absolute.toString();
}

/**
 * 策略 ONNX 一律手动 fetch(cache:"no-store") 后以 Uint8Array 交给
 * ort.InferenceSession.create——URL 直传会命中浏览器缓存的旧字节（曾导致
 * go2w 报外部数据文件缺失）。前后打日志确认实际收到的字节数与耗时，并在
 * 字节里检测到外部数据引用时给出明确告警。
 */
async function fetchPolicyModelBytes(url) {
  const started = performance.now();
  const response = await fetch(url, { cache: "no-store", credentials: "include" });
  if (!response.ok) {
    throw new Error(`策略 ONNX 下载失败 ${response.status} ${response.statusText}（cache no-store）: ${url}`);
  }
  const bytes = new Uint8Array(await response.arrayBuffer());
  console.log(
    `[sim2sim] policy fetch ${bytes.length} bytes in ${(performance.now() - started).toFixed(0)}ms (no-store) ${url}`,
  );
  if (!bytes.length) throw new Error("策略 ONNX 为空文件（0 字节）");
  // ONNX 是 protobuf：外部数据引用以 ASCII 文件名（如 policy.onnx.data）内嵌
  // 在字节流中，其后通常紧跟字段定界控制字节。据此给出旧字节/未内联告警。
  const head = new TextDecoder("latin1").decode(bytes.subarray(0, Math.min(bytes.length, 1 << 18)));
  const externalRef = /[\w./\\-]{2,120}\.data[\x00-\x1f]/.exec(head);
  if (externalRef) {
    console.warn(
      `[sim2sim] 收到的 ONNX 字节仍引用外部数据文件 ${externalRef[0].trim()} ——服务端文件未内联或缓存未刷新`,
    );
  }
  return bytes;
}

function applyPlatformLabels(config) {
  const robot = config?.robot || {};
  const policy = config?.policy || {};
  const contract = policy.contract || {};
  const onnxName = policy.onnx_url ? policy.onnx_url.split("/").pop() : "ONNX 策略";
  const checkpointName = String(policy.checkpoint || "").split(/[\\/]/).pop();
  const checkpointLabel = policyCheckpointLabel(policy, checkpointName || onnxName);
  const diagnostics = config?.policy_diagnostics || {};
  const health = policy.health || diagnostics.health || {};
  const policyId = policy.id ? ` / ${policy.id}` : "";
  const packageInfo = config?.sim?.asset_package || {};
  const packageModels = Array.isArray(packageInfo.models) ? packageInfo.models : [];
  if (elements.modelSelect) {
    const requestedModel = PAGE_PARAMS.get("model") || packageModels[0]?.id || "default";
    elements.modelSelect.innerHTML = "";
    (packageModels.length ? packageModels : [{ id: "default", label: "Default model", path: "model/robot.xml" }]).forEach((item) => {
      const option = document.createElement("option");
      option.value = item.id || item.path || "default";
      option.textContent = item.label || item.id || item.path || "Default model";
      elements.modelSelect.append(option);
    });
    elements.modelSelect.value = Array.from(elements.modelSelect.options).some((option) => option.value === requestedModel)
      ? requestedModel
      : elements.modelSelect.options[0]?.value;
  }
  if (elements.policySelect) {
    const current = policy.disabled || !policy.onnx_url ? "off" : (policy.id || policy.onnx_url);
    elements.policySelect.innerHTML = `<option value="off">无策略（姿态保持）</option>`;
    const packagePolicies = packageInfo.policies || [];
    const allCandidates = packagePolicies.length ? packagePolicies : (policy.onnx_url ? [{ id: policy.id || policy.onnx_url, url: policy.onnx_url, label: checkpointLabel }] : []);
    // 分层过滤。**高级仿真列出全部策略** —— 它的主线形态是「基础速度追踪策略 + 外挂传感器」
    // （B 类感知在策略外），默认那台 go2 速度追踪本身就是 basic；`sim_surface=advanced`
    // 只作为「该策略自带外部传感器」的标注，不再拿来过滤清单。
    // 基础仿真仍排除 advanced 策略：那些依赖外部传感器，不属于「本体 + 本体感知」。
    const candidates = allCandidates.filter((item) => {
      if (!URL_SURFACE) return true;
      if (URL_SURFACE === "advanced") return true;
      return String(item.sim_surface || "basic") !== "advanced";
    });
    candidates.forEach((item) => {
      const option = document.createElement("option");
      option.value = item.id || item.url || item.path;
      option.textContent = item.label || item.id || checkpointLabel;
      elements.policySelect.append(option);
    });
    elements.policySelect.value = candidates.some((item) => (item.id || item.url || item.path) === current) ? current : "off";
  }
  // 任务卡「任务」：有训练 Run 显示 run_id，否则显示当前策略的任务类型（速度跟踪/模仿/特技…）。
  elements.jobLabel.textContent = config?.run_id || TASK_LABELS[contract?.task_type || ""] || "-";
  elements.robotLabel.textContent = robot.name || robot.robot_name || "机器人";
  elements.modelLabel.textContent = packageModels.find((item) => (item.id || item.path) === elements.modelSelect?.value)?.label
    || packageModels[0]?.label
    || "Default model";
  elements.policyHealthLabel.textContent = health.status
    ? `${health.status}${policyId}`
    : diagnostics.status || "-";
  renderPolicyHealth(policy);
  elements.modelSubtitle.textContent = `观测 ${contract.obs_dim ?? "?"} · 历史 ${contract.history_len ?? "?"} · ${checkpointLabel}`;
  if (elements.modelSubtitle) elements.modelSubtitle.textContent = policy.onnx_url ? checkpointLabel : "MuJoCo WASM - manual control";
  updateNavigationLinks(config);
}

function renderPolicyHealth(policy = {}) {
  if (!elements.policyHealthChecks) return;
  const diagnostics = sim.platformConfig?.policy_diagnostics || {};
  const health = policy.health || diagnostics.health || {};
  const checks = Array.isArray(health.checks) ? health.checks : [];
  if (!checks.length) {
    elements.policyHealthChecks.className = "health-checks is-empty";
    elements.policyHealthChecks.innerHTML = `<span>${escapeHtml(diagnostics.message || "暂无策略健康检查。")}</span>`;
    return;
  }
  const failed = checks.filter((check) => !check.ok).length;
  const status = String(health.status || (failed ? "fail" : "pass")).toLowerCase();
  const summary = `${checks.length - failed}/${checks.length} 项通过`;
  elements.policyHealthChecks.className = `health-checks ${failed ? "has-failures" : "all-pass"}`;
  elements.policyHealthChecks.innerHTML = `
    <div class="health-checks-head">
      <span>策略检查</span>
      <strong class="${escapeAttr(status)}">${escapeHtml(summary)}</strong>
    </div>
    <div class="health-checks-list">
      ${checks.map((check) => `
        <div class="health-check ${check.ok ? "pass" : "fail"}">
          <span>${escapeHtml(check.id || "检查项")}</span>
          <strong>${check.ok ? "通过" : "失败"}</strong>
          <small>${escapeHtml(check.message || "")}</small>
        </div>
      `).join("")}
    </div>
  `;
}

function policyCheckpointLabel(policy, fallback) {
  const explicit = policyIteration(policy);
  if (explicit !== null) return `第 ${explicit} 轮 ONNX`;
  return fallback;
}

function policyIteration(policy = {}) {
  const explicit = integerOrNull(policy?.checkpoint_iteration);
  if (explicit !== null) return explicit;
  const checkpoint = String(policy?.checkpoint || "");
  const match = checkpoint.match(/(?:model|checkpoint|ckpt|iter|iteration)[_-]?(\d+)\b/i);
  if (match) return Number(match[1]);
  const url = String(policy?.onnx_url || "");
  const urlMatch = url.match(/(?:policy|model|checkpoint|ckpt|iter|iteration)[_-]?(\d+)\b/i);
  if (urlMatch) return Number(urlMatch[1]);
  return null;
}

function updateNavigationLinks(config) {
  const runId = config?.run_id || "";
  // The simulation page uses the shared five-module navigation in index.html.
  // Keep compatibility with older markup when embedded by checking nodes.
  if (elements.configLink) elements.configLink.href = "/web/workbench.html#config";
  if (elements.trainLink) elements.trainLink.href = runId ? `/web/workbench.html#training?run_id=${encodeURIComponent(runId)}` : "/web/workbench.html#training";
}

function applyRuntimeConfig(config) {
  const robot = config?.robot || {};
  let order = Array.isArray(robot.joint_order) ? robot.joint_order : [];
  const contract = config?.policy?.contract || {};
  const requestedActionDim = Number(contract.action_dim || order.length || CONFIG.numActions);
  if (Number.isInteger(requestedActionDim) && requestedActionDim > 0 && requestedActionDim <= 64) {
    resizeActionBuffers(requestedActionDim);
  }
  // 腿子集策略（如 go2w legs-only）：动作槽顺序来自 contract.action_joint_order
  // （SDK 序的 12 条腿），覆盖默认的模型前 N 关节序——执行器/默认角/限幅/增益
  // 的逐槽查找由此全部对准动作槽；轮子执行器不在其中，保持 ctrl=0 被动阻尼。
  if (Array.isArray(contract.action_joint_order) && contract.action_joint_order.length >= requestedActionDim) {
    order = contract.action_joint_order.slice(0, requestedActionDim);
  }
  CONFIG.jointOrder = order.slice(0, CONFIG.numActions);
  CONFIG.actionJointOrder = (Array.isArray(contract.action_joint_order) && contract.action_joint_order.length)
    ? contract.action_joint_order.slice(0)
    : null;
  const defaults = Object.keys(contract.default_joint_angles || {}).length
    ? contract.default_joint_angles
    : (robot.default_joint_angles || {});
  // default_joint_angles is keyed by CANONICAL lowercase slot. joint_order keeps
  // real URDF casing, so look up each order entry case-insensitively.
  const loweredDefaults = {};
  for (const [k, v] of Object.entries(defaults)) loweredDefaults[String(k).toLowerCase()] = v;
  CONFIG.defaultJointAnglesByName = loweredDefaults; // go2w_53 构造器按名查 default
  if (order.length >= CONFIG.numActions) {
    for (let i = 0; i < CONFIG.numActions; i += 1) {
      const key = String(order[i]).toLowerCase();
      CONFIG.defaultAngles[i] = finiteNumber(loweredDefaults[key], CONFIG.defaultAngles[i]);
    }
    sim.targetDofPos = new Float32Array(CONFIG.defaultAngles);
  }

  const control = robot.control || {};
  // 16 包 config 均声明 actuator_interface（payload 必带）；通用回退 = torque
  CONFIG.actuatorInterface = String(control.actuator_interface || "torque").toLowerCase();
  applyJointMotorLimits(robot.joint_limits, order);
  applyActuatorContract(contract, control, order);
  const stiffness = control.stiffness || {};
  const damping = control.damping || {};
  if (order.length >= CONFIG.numActions) {
    for (let i = 0; i < CONFIG.numActions; i += 1) {
      const group = jointGroup(order[i]);
      CONFIG.kps[i] = controlValue(stiffness, order[i], group, CONFIG.kps[i]);
      CONFIG.kds[i] = controlValue(damping, order[i], group, CONFIG.kds[i]);
    }
  }
  // Per-policy PD override (third-party rl_sar-style contracts pin their own
  // rl_kp/rl_kd, which can differ from the package-wide gains).
  const policyKps = normalizedNameMap(contract?.control?.stiffness);
  const policyKds = normalizedNameMap(contract?.control?.damping);
  // normalizedNameMap 返回普通对象（非 Map），读 .size 恒为 undefined——曾因此
  // 静默跳过整个 per-policy PD 覆盖。
  //
  // 覆盖【只对 torque 接口生效】，两条理由都由实测得出：
  //  - torque：CONFIG.kps/kds 就是应用每步下发的 PD 律，必须与训练一致。
  //    go2-backflip-69 训练 40/1，沿用包级 20/0.5 起跳发力不足，后空翻只翻到
  //    ~180° 就背部着地。全量扫描里 torque 接口仅此一个策略与包级不同。
  //  - position_target：PD 属于模型，后端按 contract_v3.actuator_profile 重建原生
  //    执行器（go1 = kp20/kv0.5）。运行时再改写 gainprm/biasprm 会破坏这一已验证
  //    配置——实测 go1-playground-joystick(35) 与 go1-moe-loco【PD 数值与包级完全
  //    相同】都会倒地。回退到"不覆盖"后两者均恢复稳定站立。
  const policyPdApplies = CONFIG.actuatorInterface === "torque";
  const hasPolicyKps = policyPdApplies && Object.keys(policyKps).length > 0;
  const hasPolicyKds = policyPdApplies && Object.keys(policyKds).length > 0;
  if (hasPolicyKps || hasPolicyKds) {
    for (let i = 0; i < CONFIG.numActions; i += 1) {
      const name = String(order[i] || CONFIG.jointOrder[i] || "").toLowerCase();
      const group = jointGroup(name);
      if (hasPolicyKps) {
        CONFIG.kps[i] = controlValue(policyKps, name, group, CONFIG.kps[i]);
      }
      if (hasPolicyKds) {
        CONFIG.kds[i] = controlValue(policyKds, name, group, CONFIG.kds[i]);
      }
    }
  }
  CONFIG.actionScale = finiteNumber(control.action_scale, CONFIG.actionScale);
  CONFIG.hipScaleReduction = finiteNumber(control.hip_scale_reduction, CONFIG.hipScaleReduction);
  const requestedBaseHeight = Number(control.base_height_target);
  CONFIG.baseHeightTarget = Number.isFinite(requestedBaseHeight)
    && requestedBaseHeight >= 0.1
    && requestedBaseHeight <= 1.5
    ? requestedBaseHeight
    : null;
  CONFIG.controlDecimation = Math.max(1, Math.round(finiteNumber(control.decimation, CONFIG.controlDecimation)));
  // sim_dt MUST match training: the policy runs every (sim_dt * decimation) seconds.
  // go2_moe_cts trains at sim_dt=0.005, decimation=4 -> 50 Hz. Keeping the bundled
  // 0.002 while applying decimation=4 gave 125 Hz, so the learned gait produced no
  // forward motion (robot balanced in place). A live model's timestep is updated too.
  CONFIG.simulationDt = finiteNumber(control.sim_dt, CONFIG.simulationDt);
  if (sim.model) sim.model.opt.timestep = CONFIG.simulationDt;
  // 物理常量契约（清单：armature/frictionloss 三端同源）：契约增量覆盖模型 default，
  // 与训练 worker / 验收器一致。按关节名覆盖，__default__ 兜底。
  applyJointPhysicsConstants(control.armature, control.frictionloss);
  CONFIG.settleSteps = Math.max(0, Math.round(finiteNumber(control.settle_steps, 0)));
  applyActionFilterCutoffs(control.action_filter_cutoffs);
  updateSignalDelayUi();
  applyTorqueLimits(control.torque_limits, order);
  applyVelocityLimits(control.velocity_limits, order);
  applyMotorEnvelopes(control.motor_envelopes, order);

  // Reindex is data, not code: PolicyContract.reindex is a single permutation
  // (null = identity). Applied to both the dof obs segment and the emitted
  // action so sim joints line up with the policy's expected leg order.
  applyPolicyContract(contract, order);
  const reindex = normalizeReindex(contract.reindex);
  CONFIG.dofReindex = reindex;
  CONFIG.actionReindex = reindex;

  const usedJobAngles = order.length >= CONFIG.numActions && Object.keys(defaults).length > 0;
  console.info(
    `[sim2sim] default angles source=${usedJobAngles ? "platform robot" : "bundled fallback"}`,
    "angles=", Array.from(CONFIG.defaultAngles),
    "reindex=", CONFIG.dofReindex ? CONFIG.dofReindex : "none",
    "scales=", {
      ang_vel: CONFIG.angVelScale,
      dof_pos: CONFIG.dofPosScale,
      dof_vel: CONFIG.dofVelScale,
      command: Array.from(CONFIG.cmdScale),
      height_command: CONFIG.heightCommandScale,
      action: CONFIG.actionScale,
      action_filter_alpha: CONFIG.actionFilterAlpha,
      hip: CONFIG.hipScaleReduction,
      base_height_target: CONFIG.baseHeightTarget,
      obs_dim: CONFIG.numObs,
      observation: CONFIG.observationKind,
      command_dims: CONFIG.commandDims,
      kps: Array.from(CONFIG.kps),
      kds: Array.from(CONFIG.kds),
      decimation: CONFIG.controlDecimation,
      default_command: Array.from(CONFIG.defaultCommand),
      autoplay: shouldAutoplayPolicy(),
      torque: Array.from(CONFIG.torqueLimits),
      motor_envelopes: CONFIG.motorEnvelopes,
      roles: CONFIG.actuatorRoles,
      modes: CONFIG.controlModes,
      velocity_scales: Array.from(CONFIG.velocityActionScales),
    },
  );
  sim.angleSignature = CONFIG.defaultAngles.join(",");
}

/** 把契约的 armature/frictionloss（增量真值）应用到已编译模型。
 * 键为关节名（或 __default__ 兜底）；模型编译后的 dof_armature/frictionloss 直接改写。 */
function applyJointPhysicsConstants(armature, frictionloss) {
  if ((!armature || !Object.keys(armature).length) && (!frictionloss || !Object.keys(frictionloss).length)) return;
  if (!sim.model || !sim.platformConfig?.robot?.joint_order) return;
  const model = sim.model;
  const resolveDof = (name) => {
    try {
      const jid = Number(model.mj_name2id(model, enumValue(sim.mujoco.mjtObj.mjOBJ_JOINT), String(name)));
      return jid >= 0 ? Number(model.jnt_dofadr[jid]) : -1;
    } catch (_) { return -1; }
  };
  let applied = 0;
  const applyTable = (table, target) => {
    if (!table || typeof table !== "object") return;
    const fallback = table.__default__;
    for (const [name, value] of Object.entries(table)) {
      if (name === "__default__" || !Number.isFinite(Number(value))) continue;
      const dof = resolveDof(name);
      if (dof >= 0) { target[dof] = Number(value); applied += 1; }
    }
    if (Number.isFinite(Number(fallback))) {
      // 未显式列出的关节回落到 __default__（按契约关节序，避免动世界自由关节）
      for (const name of sim.platformConfig.robot.joint_order) {
        if (table[String(name).toLowerCase()] !== undefined && table[String(name).toLowerCase()] !== null) continue;
        const dof = resolveDof(name);
        if (dof >= 0) target[dof] = Number(fallback);
      }
    }
  };
  applyTable(armature, model.dof_armature);
  applyTable(frictionloss, model.dof_frictionloss);
  if (applied) console.info(`[sim2sim] ✔ 契约物理常量已应用（${applied} 项 armature/frictionloss 覆盖）`);
}

function applyPolicyContract(contract, order = []) {
  const scales = contract?.scales || {};
  const control = contract?.control || {};
  CONFIG.hipScaleReduction = finiteNumber(contract?.hip_scale_reduction, CONFIG.hipScaleReduction);
  // Robot-owned motor envelopes are authoritative for uploaded assets. A
  // legacy contract may carry placeholder group limits (for example calf=1),
  // which must not override the calibrated envelope.
  if (!CONFIG.motorEnvelopes.some(Boolean)) applyTorqueLimits(contract?.torque_limits);
  // The run's robot snapshot is the training-time source of truth for PD
  // gains, action scale and decimation.  Algorithm manifests describe generic
  // defaults and must never overwrite an uploaded robot's calibrated control.
  CONFIG.actionFilterAlpha = clamp(finiteNumber(control.action_filter_alpha, CONFIG.actionFilterAlpha), 0, 1);
  const obsDim = validObservationDim(contract?.obs_dim);
  const historyLen = Math.max(1, Math.round(finiteNumber(contract?.history_len, Math.floor(sim.history.length / CONFIG.numObs) || 5)));
  if (obsDim) {
    resizeObservationBuffers(obsDim, historyLen);
  }
  CONFIG.observationKind = contract?.observation_kind
    || (CONFIG.numObs === 99 ? "quadrupedal_agility_ll" : "default");
  CONFIG.historyLayout = String(contract?.history_layout || "");
  // 显式 history 分段（Wuji reorient）：[[offset,len], ...]，每段 旧→新 逐帧拼接。
  CONFIG.historyTerms = Array.isArray(contract?.history_terms) ? contract.history_terms : null;
  // Isaac 元素主序交错 history（pushHistory 按 CONFIG.historyInterleaved 分派）
  CONFIG.historyInterleaved = Boolean(contract?.history_interleaved);
  CONFIG.gaitCommandGated = Boolean(contract?.gait_command_gated);
  // observation_mask（清单 ②）：{wrap_pi: [关节名], zero: [关节名]}，按关节名声明，
  // 构建器据此对连续关节位置观测做 wrap/清零——新增布局不再硬编码约定。
  const mask = contract?.observation_mask;
  if (mask && typeof mask === "object") {
    CONFIG.observationMask = {
      wrapPi: Array.isArray(mask.wrap_pi) ? mask.wrap_pi.map((s) => String(s).toLowerCase()) : [],
      zero: Array.isArray(mask.zero) ? mask.zero.map((s) => String(s).toLowerCase()) : [],
    };
  } else {
    CONFIG.observationMask = null;
  }
  // 部署一致的动作裁剪（训练 vec-env wrapper 在 scale/offset 前施加同一界）。
  // 接受 数字 / "0.9" / "0.9,0.9,..."（逐关节 CSV）；空值 = 不裁剪（仅保留 ±100 安全界）。
  const clipRaw = contract?.clip_actions;
  if (clipRaw === null || clipRaw === undefined || clipRaw === "") {
    CONFIG.actionClip = null;
  } else if (Array.isArray(clipRaw)) {
    CONFIG.actionClip = clipRaw.map(Number);
  } else if (typeof clipRaw === "string" && clipRaw.includes(",")) {
    CONFIG.actionClip = clipRaw.split(",").map((v) => Number(v.trim()));
  } else {
    const n = Number(clipRaw);
    CONFIG.actionClip = Number.isFinite(n) && n > 0 ? n : null;
  }
  const gaitPeriodS = finiteNumber(contract?.gait_period_s, WHEEL_LEG_GAIT_PERIOD_S);
  CONFIG.gaitPeriodS = gaitPeriodS > 0 ? gaitPeriodS : WHEEL_LEG_GAIT_PERIOD_S;
  const gaitGate = contract?.gait_locomotion_gate;
  CONFIG.gaitLocomotionGate = Array.isArray(gaitGate)
    && gaitGate.length === 2
    && Number.isFinite(Number(gaitGate[0]))
    && Number.isFinite(Number(gaitGate[1]))
    && Number(gaitGate[1]) > Number(gaitGate[0])
    ? [Number(gaitGate[0]), Number(gaitGate[1])]
    : [0.05, 0.15];
  // 动作跟踪契约（LeggedSkillDeploy 协议）：motion_joint_mapping = 策略槽位 →
  // CSV/模型关节列；waist_joint_indices = 策略序腰(yaw/roll/pitch)槽位；
  // clip_obs = 整条观测裁剪界（上游 ±100）。
  const motionMapping = contract?.motion_joint_mapping;
  CONFIG.motionJointMapping = Array.isArray(motionMapping) && motionMapping.length === CONFIG.numActions
    ? motionMapping.map(Number)
    : null;
  const waistIndices = contract?.waist_joint_indices;
  CONFIG.waistJointIndices = Array.isArray(waistIndices) && waistIndices.length === 3
    ? waistIndices.map(Number)
    : null;
  const clipObs = Number(contract?.clip_obs);
  CONFIG.clipObs = Number.isFinite(clipObs) && clipObs > 0 ? clipObs : null;
  CONFIG.gaitYawCommandRadius = Math.max(
    0,
    finiteNumber(contract?.gait_yaw_command_radius, 0.25),
  );
  CONFIG.commandAxes = normalizeCommandAxes(contract?.command_axes);
  const requestedCommandDims = Math.max(3, Math.round(finiteNumber(contract?.command_dims, commandDimsFromContract(contract))));
  resizeCommandBuffers(requestedCommandDims);
  CONFIG.commandDims = requestedCommandDims;
  // 速度指令滑条（vx/vy/ωz）的范围与默认值来自策略契约。
  CONFIG.commandRanges = normalizeCommandRanges(contract?.command_ranges);
  CONFIG.agilityCommandDims = CONFIG.observationKind === "quadrupedal_agility_ll" ? 9 : 0;
  CONFIG.defaultCommand.fill(0);
  if (hasHeightCommand()) CONFIG.defaultCommand[heightCommandIndex()] = 0.68;
  if (Array.isArray(contract?.default_command)) {
    for (let i = 0; i < Math.min(CONFIG.defaultCommand.length, contract.default_command.length); i += 1) {
      CONFIG.defaultCommand[i] = finiteNumber(contract.default_command[i], 0);
    }
  }
  applyVelocityCommandDefaults();
  CONFIG.autoplay = Boolean(contract?.autoplay);
  CONFIG.angVelScale = finiteNumber(scales.ang_vel, CONFIG.angVelScale);
  CONFIG.dofPosScale = finiteNumber(scales.dof_pos, CONFIG.dofPosScale);
  CONFIG.dofVelScale = finiteNumber(scales.dof_vel, CONFIG.dofVelScale);
  if (Array.isArray(scales.command)) {
    for (let i = 0; i < Math.min(CONFIG.cmdScale.length, scales.command.length); i += 1) {
      CONFIG.cmdScale[i] = finiteNumber(scales.command[i], CONFIG.cmdScale[i]);
    }
    if (scales.command.length > 3) {
      CONFIG.heightCommandScale = finiteNumber(scales.command[3], CONFIG.heightCommandScale);
    }
  }
  const rawObsDim = Number(contract?.obs_dim);
  if (Number.isFinite(rawObsDim) && rawObsDim > 0 && rawObsDim !== CONFIG.numObs) {
    console.warn(`[sim2sim] policy obs_dim=${rawObsDim} differs from viewer obs_dim=${CONFIG.numObs}`);
  }
  const actionDim = Number(contract?.action_dim);
  if (Number.isFinite(actionDim) && actionDim > 0 && actionDim !== CONFIG.numActions) {
    console.warn(`[sim2sim] policy action_dim=${actionDim} differs from viewer action_dim=${CONFIG.numActions}`);
  }
  // TRON1 型 encoder+policy 部署：观测/动作的 isaaclab 关节序 swap、gait 参数、命令缩放。
  const tron1 = contract?.tron1 || null;
  CONFIG.tron1Swap = Array.isArray(tron1?.swap) ? tron1.swap.map(Number) : null;
  CONFIG.tron1SwapPos = Array.isArray(tron1?.swap_pos) ? tron1.swap_pos.map(Number) : null;
  CONFIG.tron1JointPosIdx = Array.isArray(tron1?.joint_pos_idx) ? tron1.joint_pos_idx.map(Number) : null;
  CONFIG.tron1GaitFreq = finiteNumber(tron1?.gait_freq, 1.3);
  CONFIG.tron1GaitSwing = finiteNumber(tron1?.gait_swing, 0.12);
  CONFIG.tron1CmdScale = Array.isArray(tron1?.cmd_scale) ? tron1.cmd_scale.map(Number) : [1, 1, 1];
  if (!CONFIG.tron1Swap) {
    CONFIG.tron1SwapPos = null;
    CONFIG.tron1JointPosIdx = null;
  }
  sim.tron1GaitIndex = 0;
  CONFIG.taskType = String(contract?.task_type || "");
  updateCommandLabel();
  updateTaskPanels();
  OBSERVATION.updateGaitControl();
  updateVelocityCommandControls();
}

// 任务类型面板（控制面板顶部第一卡）：按 contract.task_type 适配 UI——
// 速度跟踪用通用速度指令组（velocityCommandControl），模仿 / 特技 / 跑酷各用专属子面板。
const TASK_LABELS = {
  velocity: "速度跟踪", stand: "站立 / 平衡", balance: "站立 / 平衡",
  imitation: "动作模仿 / 舞蹈", acrobatics: "特技", parkour: "跑酷 / 地形",
  manipulation: "操作 / 灵巧手",
};
// 只有这些任务需要专属子面板（模仿时间轴 / 特技重播 / 跑酷目标提示）；
// 其余任务（速度跟踪 / 站立 / 操作）的任务名已由下方「任务」卡显示，
// 这里不再重复一行「任务类型」标题，避免与「任务」卡撞车。
const TASK_SUBPANEL_TASKS = new Set(["imitation", "acrobatics", "parkour"]);
function updateTaskPanels() {
  const panel = document.getElementById("taskPanel");
  if (!panel) return;
  const task = CONFIG.taskType || "";
  panel.hidden = !TASK_SUBPANEL_TASKS.has(task);
  if (panel.hidden) return;
  const imitation = document.getElementById("imitationPanel");
  if (imitation) imitation.hidden = task !== "imitation";
  const trick = document.getElementById("trickPanel");
  if (trick) trick.hidden = task !== "acrobatics";
  const parkour = document.getElementById("parkourStatus");
  if (parkour) parkour.hidden = task !== "parkour";
  if (task === "imitation") {
    const duration = document.getElementById("mimicDuration");
    if (duration && sim.motionLoader?.duration) duration.textContent = `${Number(sim.motionLoader.duration).toFixed(2)}s`;
  }
}

function resizeCommandBuffers(commandDim) {
  const size = Math.max(3, commandDim);
  if (CONFIG.defaultCommand.length !== size) {
    const nextDefault = new Float32Array(size);
    nextDefault.set(CONFIG.defaultCommand.subarray(0, Math.min(size, CONFIG.defaultCommand.length)));
    CONFIG.defaultCommand = nextDefault;
  }
  if (sim.cmd.length !== size) {
    const next = new Float32Array(size);
    next.set(sim.cmd.subarray(0, Math.min(size, sim.cmd.length)));
    sim.cmd = next;
  }
  if (sim.targetCmd.length !== size) {
    const next = new Float32Array(size);
    next.set(sim.targetCmd.subarray(0, Math.min(size, sim.targetCmd.length)));
    sim.targetCmd = next;
  }
}

function resizeActionBuffers(actionDim) {
  if (actionDim === CONFIG.numActions) return;
  const resizeFloat = (source, fill = 0) => {
    const next = new Float32Array(actionDim);
    if (fill) next.fill(fill);
    if (source) next.set(source.subarray(0, Math.min(source.length, actionDim)));
    return next;
  };

  CONFIG.kps = resizeFloat(CONFIG.kps, 20);
  CONFIG.kds = resizeFloat(CONFIG.kds, 0.5);
  CONFIG.defaultAngles = resizeFloat(CONFIG.defaultAngles);
  CONFIG.torqueLimits = resizeFloat(CONFIG.torqueLimits);
  CONFIG.motorVelocityLimits = resizeFloat(CONFIG.motorVelocityLimits);
  CONFIG.dynamicTorqueLimits = resizeFloat(CONFIG.dynamicTorqueLimits);
  CONFIG.motorEnvelopes = Array.from(
    { length: actionDim },
    (_, index) => CONFIG.motorEnvelopes[index] || null,
  );
  CONFIG.positionActionScales = resizeFloat(CONFIG.positionActionScales, CONFIG.actionScale);
  CONFIG.velocityActionScales = resizeFloat(CONFIG.velocityActionScales, 20);
  CONFIG.actuatorRoles = Array.from({ length: actionDim }, (_, index) => CONFIG.actuatorRoles[index] || "leg");
  CONFIG.controlModes = Array.from({ length: actionDim }, (_, index) => CONFIG.controlModes[index] || "position");
  CONFIG.numActions = actionDim;

  sim.action = resizeFloat(sim.action);
  sim.appliedAction = resizeFloat(sim.appliedAction);
  sim.filteredAction = resizeFloat(sim.filteredAction);
  sim.targetDofPos = resizeFloat(sim.targetDofPos);
  sim.targetDofVel = resizeFloat(sim.targetDofVel);
  sim.pendingTargetDofPos = resizeFloat(sim.pendingTargetDofPos);
  sim.pendingTargetDofVel = resizeFloat(sim.pendingTargetDofVel);
}

function applyActuatorContract(contract, control, order) {
  const contractRoles = normalizedNameMap(contract?.actuator_roles);
  const contractModes = normalizedNameMap(contract?.control_modes);
  const robotModes = normalizedNameMap(control?.control_modes);
  const roleScales = control?.action_scale_by_role || {};
  const jointScales = normalizedNameMap(control?.action_scale_by_joint || contract?.action_scale_by_joint);
  const defaultPositionScale = finiteNumber(contract?.action_scale, finiteNumber(control?.action_scale, CONFIG.actionScale));
  const defaultVelocityScale = finiteNumber(
    contract?.control?.velocity_scale,
    finiteNumber(control?.velocity_scale, 20),
  );

  for (let i = 0; i < CONFIG.numActions; i += 1) {
    const name = String(order[i] || CONFIG.jointOrder[i] || "").toLowerCase();
    const inferredRole = jointGroup(name) === "wheel" ? "wheel" : "leg";
    const role = String(contractRoles[name] || inferredRole).toLowerCase();
    const mode = String(
      contractModes[name]
      || contractModes[role]
      || robotModes[name]
      || robotModes[role]
      || (role === "wheel" ? "velocity" : "position"),
    ).toLowerCase();
    CONFIG.actuatorRoles[i] = role;
    CONFIG.controlModes[i] = ["position", "velocity", "torque"].includes(mode) ? mode : "position";
    CONFIG.positionActionScales[i] = finiteNumber(
      jointScales[name],
      finiteNumber(roleScales[role], defaultPositionScale),
    );
    CONFIG.velocityActionScales[i] = finiteNumber(roleScales[role], defaultVelocityScale);
  }
}

function applyActionFilterCutoffs(cutoffs) {
  // Deployment references filter actuator targets per role (rc_mjlab wheels:
  // legs 5 Hz, wheels 15 Hz). alpha = dt / (dt + 1/(2*pi*fc)) evaluated at the
  // control period, matching LowPassFilter.alpha in the Python sim2sim.
  const source = cutoffs && typeof cutoffs === "object" ? cutoffs : null;
  if (!source) {
    CONFIG.actionFilterCutoffs = null;
    CONFIG.actionFilterAlphas = null;
    return;
  }
  const controlDt = CONFIG.simulationDt * CONFIG.controlDecimation;
  const perJoint = new Float32Array(CONFIG.numActions);
  const alphas = new Float32Array(CONFIG.numActions);
  for (let i = 0; i < CONFIG.numActions; i += 1) {
    const role = CONFIG.actuatorRoles[i] || "leg";
    const name = String(CONFIG.jointOrder[i] || "").toLowerCase();
    const cutoff = finiteNumber(source[name], finiteNumber(source[role], 0));
    perJoint[i] = cutoff;
    alphas[i] = cutoff > 0 && controlDt > 0
      ? controlDt / (controlDt + 1 / (2 * Math.PI * cutoff))
      : 1;
  }
  CONFIG.actionFilterCutoffs = perJoint;
  CONFIG.actionFilterAlphas = alphas;
}

function filterAlphaForJoint(index) {
  const alphas = CONFIG.actionFilterAlphas;
  return alphas ? alphas[index] : CONFIG.actionFilterAlpha;
}

function settleRobot() {
  // Deployment scripts hold the default pose under PD for ~1 s before the
  // policy takes over; free-falling from the spawn height without this
  // transient corrupts the initial observation and history.
  for (let i = 0; i < CONFIG.numActions; i += 1) {
    const actuatorId = sim.actuatorIds[i] ?? i;
    if (actuatorId < 0 || actuatorId >= sim.ctrl.length) continue;
    sim.ctrl[actuatorId] = CONFIG.controlModes[i] === "velocity" ? 0 : CONFIG.defaultAngles[i];
  }
  for (let step = 0; step < CONFIG.settleSteps; step += 1) {
    sim.mujoco.mj_step(sim.model, sim.data);
  }
}

function normalizedNameMap(value) {
  const result = {};
  if (!value || typeof value !== "object") return result;
  for (const [key, item] of Object.entries(value)) result[String(key).toLowerCase()] = item;
  return result;
}

// During polling the policy may be unchanged but the user may have edited the
// robot's default joint angles. Re-apply runtime config (and re-home the robot)
// only when the resolved angles actually changed.
function maybeApplyLiveConfig(config) {
  const prev = sim.angleSignature;
  const prevObsDim = CONFIG.numObs;
  const prevHistoryLength = sim.history.length;
  applyRuntimeConfig(config);
  if (sim.angleSignature !== prev || CONFIG.numObs !== prevObsDim || sim.history.length !== prevHistoryLength) {
    console.info("[sim2sim] live runtime contract update applied; re-homing pose");
    resetSimulation();
  }
}

function normalizeReindex(arr) {
  if (!Array.isArray(arr) || arr.length !== CONFIG.numActions) return null;
  const perm = arr.map((v) => Number(v));
  // Reject anything that is not a valid permutation of 0..numActions-1.
  const seen = new Set(perm);
  if (perm.some((v) => !Number.isInteger(v) || v < 0 || v >= CONFIG.numActions) || seen.size !== CONFIG.numActions) {
    return null;
  }
  // Identity permutation -> treat as no-op for clarity.
  if (perm.every((v, i) => v === i)) return null;
  return perm;
}

function validObservationDim(value) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 && parsed <= 512 ? parsed : 0;
}

function normalizeCommandAxes(value) {
  if (!Array.isArray(value)) return [];
  return value
    .map((axis, fallbackIndex) => {
      if (!axis || typeof axis !== "object") return null;
      const index = Number.isInteger(Number(axis.index)) ? Number(axis.index) : fallbackIndex;
      if (index < 0 || index >= CONFIG.defaultCommand.length) return null;
      return {
        name: String(axis.name || `cmd_${index}`),
        label: String(axis.label || axis.name || `cmd ${index}`),
        kind: String(axis.kind || "generic").toLowerCase(),
        unit: String(axis.unit || ""),
        index,
        scale: Number.isFinite(Number(axis.scale)) ? Number(axis.scale) : null,
        bucket: String(axis.bucket || ""),
      };
    })
    .filter(Boolean)
    .sort((a, b) => a.index - b.index);
}

function commandDimsFromContract(contract = null) {
  const axes = Array.isArray(contract?.command_axes)
    ? normalizeCommandAxes(contract.command_axes)
    : CONFIG.commandAxes;
  if (axes.length) {
    if (axes.some((axis) => axis.kind === "binary_jump" || axis.kind === "jump")) return 3;
    return Math.max(3, Math.min(CONFIG.defaultCommand.length, Math.max(...axes.map((axis) => axis.index)) + 1));
  }
  return CONFIG.numObs === 46 ? 4 : 3;
}

function heightCommandAxis() {
  return CONFIG.commandAxes.find((axis) => axis.kind === "height" || axis.kind === "jump_height")
    || (CONFIG.numObs === 46 ? { index: 3, label: "jump height", unit: "m", bucket: "omni_jump_height" } : null);
}

function heightCommandIndex() {
  return heightCommandAxis()?.index ?? 3;
}

function hasHeightCommand() {
  return Boolean(heightCommandAxis());
}

function hasBinaryJumpCommand() {
  return CONFIG.commandAxes.some((axis) => axis.kind === "binary_jump" || axis.kind === "jump")
    || CONFIG.observationKind === WHEEL_LEG_JUMP_OBSERVATION;
}

function isWheelLegJumpPolicy() {
  return CONFIG.observationKind === WHEEL_LEG_JUMP_OBSERVATION;
}

function observationLayout() {
  const commandDims = CONFIG.commandDims || commandDimsFromContract();
  const jointOffset = 6 + commandDims;
  return {
    commandDims,
    heightCommand: hasHeightCommand(),
    jointOffset,
    velocityOffset: jointOffset + CONFIG.numActions,
    actionOffset: jointOffset + 2 * CONFIG.numActions,
  };
}

function resizeObservationBuffers(obsDim, historyFrames = 5) {
  const nextObsDim = validObservationDim(obsDim) || CONFIG.numObs;
  const nextFrames = Math.max(1, Math.round(finiteNumber(historyFrames, 5)));
  const oldObs = sim.obs;
  const oldHistory = sim.history;
  const oldDim = CONFIG.numObs;

  CONFIG.numObs = nextObsDim;
  CONFIG.commandDims = commandDimsFromContract();
  CONFIG.agilityCommandDims = CONFIG.numObs === 99 ? 9 : 0;
  const heightIndex = heightCommandIndex();
  if (hasHeightCommand() && (!Number.isFinite(CONFIG.defaultCommand[heightIndex]) || CONFIG.defaultCommand[heightIndex] === 0)) {
    CONFIG.defaultCommand[heightIndex] = 0.68;
  }
  if (oldObs.length !== nextObsDim) {
    sim.obs = new Float32Array(nextObsDim);
    sim.obs.set(oldObs.subarray(0, Math.min(oldObs.length, nextObsDim)));
  }
  if (oldHistory.length !== nextFrames * nextObsDim) {
    sim.history = new Float32Array(nextFrames * nextObsDim);
    const oldFrames = Math.floor(oldHistory.length / oldDim);
    const framesToCopy = Math.min(oldFrames, nextFrames);
    for (let i = 0; i < framesToCopy; i += 1) {
      const oldFrame = oldFrames - framesToCopy + i;
      const newFrame = nextFrames - framesToCopy + i;
      const source = oldHistory.subarray(oldFrame * oldDim, oldFrame * oldDim + Math.min(oldDim, nextObsDim));
      sim.history.set(source, newFrame * nextObsDim);
    }
  }
}

function jointGroup(jointName) {
  const name = String(jointName).toLowerCase();
  if (name.includes("wheel") || name.includes("foot")) return "wheel";
  if (name.includes("calf")) return "calf";
  if (name.includes("thigh")) return "thigh";
  return "hip";
}

// Morphology-agnostic joint segment: strips the leg-side prefix and the
// trailing "joint" token, so "fl_hip_abduction_joint" -> "hip_abduction",
// "left_hip_yaw" -> "hip_yaw". Works for quadrupeds, bipeds, wheel-legs…
function jointSegment(jointName) {
  const parts = String(jointName).toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
  if (parts.length > 1 && ["joint", "actuator", "motor"].includes(parts[parts.length - 1])) parts.pop();
  if (parts.length > 1 && /^(fl|fr|rl|rr|lf|rf|lh|rh|l1|r1|l|r|hr|hl|front|rear|left|right)$/.test(parts[0])) parts.shift();
  return parts.join("_") || String(jointName).toLowerCase();
}

function controlValue(values, jointName, group, fallback) {
  const table = values || {};
  const segment = jointSegment(jointName);
  return finiteNumber(
    table[jointName],
    finiteNumber(
      table[segment],
      finiteNumber(table[group], finiteNumber(table.joint, fallback)),
    ),
  );
}

function finiteNumber(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function integerOrNull(value) {
  if (value === undefined || value === null || value === "") return null;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : null;
}

function applyVelocityLimits(limits, order = null) {
  // Motor speed caps keyed by exact joint name, inferred body segment, or the
  // legacy hip/thigh/calf/wheel groups — whatever the package provides.
  if (!limits || typeof limits !== "object") return;
  if (Array.isArray(limits) && limits.length === CONFIG.numActions) {
    for (let i = 0; i < CONFIG.numActions; i += 1) {
      CONFIG.motorVelocityLimits[i] = Math.max(0, finiteNumber(limits[i], CONFIG.motorVelocityLimits[i]));
    }
    return;
  }
  const jointOrder = Array.isArray(order) && order.length >= CONFIG.numActions
    ? order
    : CONFIG.jointOrder;
  for (let i = 0; i < CONFIG.numActions; i += 1) {
    const joint = String(jointOrder[i] || "");
    for (const key of [joint, jointSegment(joint), jointGroup(joint), joint.toLowerCase()]) {
      if (Object.prototype.hasOwnProperty.call(limits, key)) {
        CONFIG.motorVelocityLimits[i] = Math.max(0, finiteNumber(limits[key], CONFIG.motorVelocityLimits[i]));
        break;
      }
    }
  }
}

function applyTorqueLimits(limits, order = null) {
  if (!limits) return;
  if (Array.isArray(limits) && limits.length === CONFIG.numActions) {
    for (let i = 0; i < CONFIG.numActions; i += 1) {
      CONFIG.torqueLimits[i] = Math.max(0, finiteNumber(limits[i], CONFIG.torqueLimits[i]));
    }
    return;
  }
  if (typeof limits !== "object") return;
  const jointOrder = Array.isArray(order) && order.length >= CONFIG.numActions
    ? order
    : CONFIG.jointOrder;
  for (let i = 0; i < CONFIG.numActions; i += 1) {
    const joint = jointOrder[i];
    const group = jointGroup(joint);
    if (Object.prototype.hasOwnProperty.call(limits, joint)) {
      CONFIG.torqueLimits[i] = Math.max(0, finiteNumber(limits[joint], CONFIG.torqueLimits[i]));
      continue;
    }
    const segment = jointSegment(joint);
    if (Object.prototype.hasOwnProperty.call(limits, segment)) {
      CONFIG.torqueLimits[i] = Math.max(0, finiteNumber(limits[segment], CONFIG.torqueLimits[i]));
      continue;
    }
    if (Object.prototype.hasOwnProperty.call(limits, group)) {
      CONFIG.torqueLimits[i] = Math.max(0, finiteNumber(limits[group], CONFIG.torqueLimits[i]));
    }
  }
}

function applyJointMotorLimits(limits, order = null) {
  CONFIG.torqueLimits.fill(0);
  CONFIG.motorVelocityLimits.fill(0);
  if (!limits || typeof limits !== "object") return;
  const normalized = normalizedNameMap(limits);
  const jointOrder = Array.isArray(order) && order.length >= CONFIG.numActions
    ? order
    : CONFIG.jointOrder;
  for (let i = 0; i < CONFIG.numActions; i += 1) {
    const jointName = String(jointOrder[i] || "").toLowerCase();
    const item = normalized[jointName] || normalized[jointGroup(jointName)] || {};
    CONFIG.torqueLimits[i] = Math.max(0, finiteNumber(item.effort, 0));
    CONFIG.motorVelocityLimits[i] = Math.max(0, finiteNumber(item.velocity, 0));
  }
}

function normalizeMotorEnvelope(points) {
  if (!Array.isArray(points) || points.length < 2) return null;
  const normalized = points.map((point) => {
    if (Array.isArray(point)) return { rpm: Number(point[0]), torque: Number(point[1]) };
    return { rpm: Number(point?.rpm), torque: Number(point?.torque) };
  });
  if (normalized.some((point) => !Number.isFinite(point.rpm)
    || !Number.isFinite(point.torque)
    || point.rpm < 0
    || point.torque < 0)) return null;
  for (let i = 1; i < normalized.length; i += 1) {
    if (normalized[i].rpm <= normalized[i - 1].rpm) return null;
  }
  return normalized;
}

function applyMotorEnvelopes(envelopes, order = null) {
  CONFIG.motorEnvelopes = new Array(CONFIG.numActions).fill(null);
  CONFIG.dynamicTorqueLimits.fill(0);
  if (!envelopes || typeof envelopes !== "object") return;
  const normalized = normalizedNameMap(envelopes);
  const jointOrder = Array.isArray(order) && order.length >= CONFIG.numActions
    ? order
    : CONFIG.jointOrder;
  for (let i = 0; i < CONFIG.numActions; i += 1) {
    const jointName = String(jointOrder[i] || "").toLowerCase();
    const role = jointGroup(jointName);
    CONFIG.motorEnvelopes[i] = normalizeMotorEnvelope(
      normalized[jointName] || normalized[role],
    );
    // Uploaded URDFs may contain placeholder effort limits (0 or 1). Promote
    // the configured rated torque so the placeholder cannot clamp PD output.
    const points = CONFIG.motorEnvelopes[i];
    if (points && CONFIG.torqueLimits[i] <= 1) {
      CONFIG.torqueLimits[i] = Math.max(...points.map((point) => point.torque));
    }
  }
}

function motorEnvelopeTorqueAtSpeed(points, velocityRadPerSecond) {
  if (!points) return null;
  const rpm = Math.abs(velocityRadPerSecond) * 60 / (2 * Math.PI);
  if (rpm <= points[0].rpm) return points[0].torque;
  const last = points[points.length - 1];
  if (rpm >= last.rpm) return last.torque;
  for (let i = 1; i < points.length; i += 1) {
    const right = points[i];
    if (rpm <= right.rpm) {
      const left = points[i - 1];
      const alpha = (rpm - left.rpm) / (right.rpm - left.rpm);
      return left.torque + alpha * (right.torque - left.torque);
    }
  }
  return last.torque;
}

function actionScaleForJoint(index) {
  const group = jointGroup(CONFIG.jointOrder[index] || "");
  const reduction = group === "hip" ? CONFIG.hipScaleReduction : 1.0;
  return CONFIG.positionActionScales[index] * reduction;
}

function velocityScaleForJoint(index) {
  return CONFIG.velocityActionScales[index];
}

function applyTerrainOptions(config) {
  const packageInfo = config?.sim?.asset_package || {};
  const terrainOptions = Array.isArray(packageInfo.terrains) ? packageInfo.terrains : [];
  const scenes = packageInfo.scenes?.length
    ? packageInfo.scenes
    : (activeRobotKey() === "fsdog1" ? FSDOG_SCENE_FILES : XML_FILES);
  const current = elements.terrainSelect.value;
  const requested = resolveTerrainName(URL_TERRAIN, scenes);
  const currentScene = resolveTerrainName(current, scenes);
  const flatScene = resolveTerrainName("flat", scenes);
  elements.terrainSelect.innerHTML = "";
  scenes.forEach((sceneName) => {
    const option = document.createElement("option");
    option.value = sceneName;
    const manifestEntry = terrainOptions.find((item) => item?.path === sceneName);
    option.textContent = manifestEntry?.label || terrainLabel(sceneName);
    elements.terrainSelect.append(option);
  });
  if (requested) {
    elements.terrainSelect.value = requested;
  } else if (flatScene) {
    elements.terrainSelect.value = flatScene;
  } else if (currentScene) {
    elements.terrainSelect.value = currentScene;
  } else if (scenes.length) {
    elements.terrainSelect.value = scenes[0];
  }
}

function terrainLabel(sceneName) {
  const key = sceneBasename(sceneName).replace(/\.xml$/i, "").replace(/^scene_/, "").toLowerCase();
  return TERRAIN_LABELS[key] || key.replace(/_/g, " ");
}

function activeRobotKey() {
  return normalizeRobotParam(sim.platformConfig?.sim?.robot || URL_ROBOT || sim.platformConfig?.robot?.name || "");
}

function normalizeRobotParam(value) {
  const key = String(value || "")
    .trim()
    .toLowerCase()
    .replace(/^rbt_builtin_/, "")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  if (!key) return "";
  // 先精确匹配（覆盖全部 16 种完整包 id 与短键），消除 double-track。
  for (const alias of ROBOT_ID_ALIASES) {
    if (key === alias.match) return alias.key;
  }
  // includes 兜底：兼容历史模糊键入（如 ?robot=fsdog 含 fsdog 子串）。
  for (const alias of ROBOT_ID_ALIASES) {
    if (key.includes(alias.match)) return alias.key;
  }
  return key;
}

function resolveTerrainName(value, scenes) {
  const available = Array.isArray(scenes) ? scenes : [];
  const raw = sceneBasename(value).trim().toLowerCase();
  if (!raw || !available.length) return "";
  const normalized = raw.replace(/\.xml$/i, "").replace(/[-\s]+/g, "_");
  const aliases = {
    slope: "cross_slope",
    rough: "stairs",
    obstacle: "cross_stairs",
    obstacles: "cross_stairs",
    agility: "cross_stairs",
    parkour: "race_track",
    jump: "race_track",
    jumping: "race_track",
  };
  const wanted = aliases[normalized] || normalized;
  return available.find((scene) => sceneBasename(scene).toLowerCase() === `${wanted}.xml`)
    || available.find((scene) => sceneBasename(scene).toLowerCase().replace(/\.xml$/i, "") === wanted)
    || "";
}

function sceneBasename(value) {
  return String(value || "").replace(/\\/g, "/").split("/").pop() || "";
}

function startPlatformPolling() {
  if (!sim.platformConfig?.run_id) return;
  setInterval(async () => {
    try {
      const config = await loadPlatformConfig();
      // Do NOT auto-rebuild the ONNX session here. During training the policy
      // revision changes every save, and InferenceSession.create recompiles the
      // ~12MB onnxruntime WASM each time — polling every 5s would relaunch that
      // compile repeatedly and freeze the tab. Only apply lightweight runtime
      // updates (joint angles / contract). A genuinely new policy is surfaced by
      // startLatestPolicyPolling as a manual "update" prompt the user opts into.
      maybeApplyLiveConfig(config);
    } catch (error) {
      console.warn("policy refresh skipped", error);
    }
  }, 5000);
}

function startLatestPolicyPolling() {
  const params = new URLSearchParams(window.location.search);
  if (!params.get("run_id") && !params.get("job_id")) return;
  if (params.get("policy") === "off") return;
  checkLatestPolicyUpdate({ quiet: true });
  sim.latestPolicyTimer = setInterval(() => {
    checkLatestPolicyUpdate({ quiet: true });
  }, LATEST_POLICY_POLL_MS);
}

async function checkLatestPolicyUpdate({ quiet = false } = {}) {
  const params = new URLSearchParams(window.location.search);
  const runId = params.get("run_id") || params.get("job_id") || sim.platformConfig?.run_id || "";
  if (!runId || sim.latestPolicyChecking) return null;
  sim.latestPolicyChecking = true;
  try {
    const response = await fetch(`/api/runs/${encodeURIComponent(runId)}?t=${Date.now()}`, {
      cache: "no-store",
      credentials: "include",
    });
    if (!response.ok) throw new Error(await responseErrorMessage(response));
    const run = await response.json();
    const candidate = playablePolicyFromRun(run);
    const update = candidate ? buildPolicyUpdate(run, candidate) : null;
    renderPolicyUpdate(update);
    return update;
  } catch (error) {
    if (!quiet) console.warn("latest policy check skipped", error);
    return null;
  } finally {
    sim.latestPolicyChecking = false;
  }
}

function playablePolicyFromRun(run) {
  const candidates = [run?.playable_policy, run?.latest_policy].filter(Boolean);
  return candidates.find((policy) => {
    if (!policy?.id || !policy?.onnx_url) return false;
    const status = String(policy.health?.status || "pass").toLowerCase();
    return ["pass", "ready"].includes(status);
  }) || null;
}

function buildPolicyUpdate(run, nextPolicy) {
  const currentPolicy = sim.platformConfig?.policy || {};
  const currentIter = policyIteration(currentPolicy);
  const nextIter = policyIteration(nextPolicy);
  const currentId = String(currentPolicy.id || PAGE_PARAMS.get("policy") || "");
  const nextId = String(nextPolicy.id || "");
  const samePolicy = nextId && currentId && nextId === currentId;
  const newerIteration = nextIter !== null && (currentIter === null || nextIter > currentIter);
  if (samePolicy || !newerIteration) return null;
  if (!newerIteration && !nextId) return null;
  return {
    runId: run?.id || sim.platformConfig?.run_id || "",
    policyId: nextId,
    currentIteration: currentIter,
    nextIteration: nextIter,
    createdAt: nextPolicy.created_at ?? null,
  };
}

function renderPolicyUpdate(update) {
  if (!elements.policyUpdatePrompt || !elements.policyUpdateText || !elements.policyUpdateButton) return;
  sim.pendingPolicyUpdate = update;
  elements.policyUpdatePrompt.classList.toggle("is-hidden", !update);
  if (!update) return;
  const currentText = update.currentIteration !== null ? `当前 ${update.currentIteration}` : "当前策略";
  const nextText = update.nextIteration !== null ? `新 ONNX ${update.nextIteration}` : "新的 ONNX";
  elements.policyUpdateText.textContent = `${nextText} · ${currentText}`;
  elements.policyUpdateButton.disabled = !update.policyId || !update.runId;
}

function navigateToPolicyUpdate(update) {
  if (!update?.runId || !update?.policyId) return;
  const url = new URL("/sim2sim/", window.location.origin);
  url.searchParams.set("run_id", update.runId);
  url.searchParams.set("policy", update.policyId);
  if (update.nextIteration !== null) url.searchParams.set("iter", String(update.nextIteration));
  url.searchParams.set("v", String(Date.now()));
  window.location.href = url.toString();
}

function initThree() {
  view.scene = new THREE.Scene();
  // Keep the WebGL stage legible while a package is loading.  The previous
  // dark fog plus an alpha renderer made a missing/undersized terrain look
  // like a black viewport.
  view.scene.background = new THREE.Color(0xdbe5eb);
  view.scene.fog = new THREE.Fog(0xdbe5eb, 18, 80);

  view.camera = new THREE.PerspectiveCamera(48, 1, 0.01, 120);
  view.camera.up.set(0, 0, 1);
  view.camera.position.set(1.35, -1.55, 0.95);

  view.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
  view.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  view.renderer.shadowMap.enabled = false;
  view.renderer.outputColorSpace = THREE.SRGBColorSpace;
  elements.viewer.append(view.renderer.domElement);

  // 拖拽施力必须在 OrbitControls 之前注册：target 阶段监听按注册顺序执行，
  // 先注册才能用 stopImmediatePropagation 挡住 OrbitControls 的旋转起点。
  initDragInteraction();
  ensureDragArrow();

  view.controls = new OrbitControls(view.camera, view.renderer.domElement);
  view.controls.target.set(0, 0, 0.35);
  view.controls.enableDamping = true;
  view.controls.dampingFactor = 0.08;
  view.controls.maxPolarAngle = Math.PI * 0.49;
  view.controls.minDistance = 0.35;
  view.controls.maxDistance = 22;

  const hemi = new THREE.HemisphereLight(0xf2f7ff, 0x2b1f16, 1.9);
  view.scene.add(hemi);

  const key = new THREE.DirectionalLight(0xffffff, 2.6);
  key.position.set(-3.2, -4.2, 7.5);
  view.scene.add(key);

  resize();
  window.addEventListener("resize", resize);
  if ("ResizeObserver" in window) new ResizeObserver(() => resize()).observe(elements.viewer);
  requestAnimationFrame(() => resize());
}

function bindUi() {
  bindMobileJoystick();
  elements.robotSelect?.addEventListener("change", () => {
    const robot = elements.robotSelect.value;
    const url = new URL(window.location.href);
    url.searchParams.set("robot", robot);
    url.searchParams.delete("model");
    url.searchParams.delete("policy");
    window.location.href = url.toString();
  });
  elements.modelSelect?.addEventListener("change", () => {
    const url = new URL(window.location.href);
    url.searchParams.set("model", elements.modelSelect.value);
    window.location.href = url.toString();
  });
  elements.policySelect?.addEventListener("change", async () => {
    await switchPolicy(elements.policySelect.value);
  });
  window.addEventListener("keydown", (event) => {
    // 全局快捷键（C = 隐/显控制面板，R = 重置）。输入控件聚焦时不触发，
    // 但按钮/链接聚焦时仍可用（与移动键不同，不会与控件默认行为冲突）。
    if (!isEditableElement(event.target) && !event.repeat) {
      if (event.code === "KeyC") {
        event.preventDefault();
        toggleControlPanel();
        return;
      }
      if (event.code === "KeyR") {
        event.preventDefault();
        resetSimulation();
        return;
      }
    }
    if (
      event.target instanceof HTMLInputElement
      || event.target instanceof HTMLSelectElement
      || event.target instanceof HTMLTextAreaElement
      || event.target instanceof HTMLButtonElement
      || event.target instanceof HTMLAnchorElement
      || event.target?.isContentEditable
    ) return;
    if (["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Space"].includes(event.code)) {
      event.preventDefault();
    }
    if (event.code === "Space") {
      if (isWheelLegJumpPolicy()) {
        if (!event.repeat) triggerJumpCommand();
      } else {
        togglePause();
      }
      return;
    }
    input.keys.add(event.code);
    updateKeyCaps();
  });

  window.addEventListener("keyup", (event) => {
    input.keys.delete(event.code);
    updateKeyCaps();
  });
  window.addEventListener("blur", () => {
    input.keys.clear();
    resetMobileJoystick();
    zeroCommand();
    updateKeyCaps();
    updateHud(true);
  });

  elements.playButton.addEventListener("click", togglePause);
  for (const button of document.querySelectorAll("[data-jump-command]")) {
    button.addEventListener("pointerdown", (event) => {
      if (event.button !== 0 || !event.isPrimary) return;
      event.preventDefault();
      button.setPointerCapture?.(event.pointerId);
      triggerJumpCommand();
    });
    // Preserve keyboard and assistive-technology activation. Pointer clicks
    // are already handled above and have a non-zero detail value.
    button.addEventListener("click", (event) => {
      if (event.detail === 0) triggerJumpCommand();
    });
  }
  elements.resetButton.addEventListener("click", resetSimulation);
  // 任务子面板：模仿 = 重播参考动作（相位清零 + 重置仿真）；特技 = 重置演示。
  document.getElementById("mimicReplay")?.addEventListener("click", () => {
    OBSERVATION.resetMotionTime();
    resetSimulation();
  });
  document.getElementById("trickReplay")?.addEventListener("click", resetSimulation);
  elements.mobileControlsToggle?.addEventListener("click", () => {
    const panel = elements.mobileControlsToggle.closest(".panel-left");
    if (!panel) return;
    const expanded = panel.classList.toggle("is-collapsed") === false;
    document.body.classList.toggle("mobile-controls-expanded", expanded);
    elements.mobileControlsToggle.setAttribute("aria-expanded", String(expanded));
    elements.mobileControlsToggle.lastElementChild.textContent = expanded ? "⌃" : "⌄";
  });
  elements.policyUpdateButton?.addEventListener("click", () => {
    if (sim.pendingPolicyUpdate) navigateToPolicyUpdate(sim.pendingPolicyUpdate);
  });
  elements.terrainSelect.addEventListener("change", async () => {
    await loadTerrain(elements.terrainSelect.value);
  });
  window.addEventListener("message", (event) => {
    if (!VIEWER_ONLY || event.origin !== window.location.origin || !sim.ready) return;
    const payload = event.data || {};
    if (payload.type === "legged-studio:set-joints" && payload.positions) {
      const positions = payload.positions;
      CONFIG.jointOrder.forEach((name, index) => {
        if (!(name in positions)) return;
        const value = finiteNumber(positions[name], CONFIG.defaultAngles[index]);
        setJointQpos(index, value);
        sim.targetDofPos[index] = value;
      });
      sim.mujoco.mj_forward(sim.model, sim.data);
      syncVisualScene();
      updateHud(true);
    } else if (payload.type === "legged-studio:reset-pose") {
      resetSimulation();
    } else if (payload.type === "legged-studio:fit-view") {
      frameCameraToModel();
    }
  });
  elements.gaitToggle?.addEventListener("change", () => {
    OBSERVATION.setWheelLegGaitEnabled(elements.gaitToggle.checked);
  });
  OBSERVATION.updateGaitControl();
  elements.payloadMass?.addEventListener("input", () => {
    input.payloadMassKg = clamp(Number(elements.payloadMass.value) || 0, 0, MAX_PAYLOAD_KG);
    applyPayloadMass();
  });
  for (const slider of elements.comOffsetSliders) {
    slider.addEventListener("input", applyCenterOfMassOffset);
  }
  elements.terrainFriction?.addEventListener("input", () => {
    input.terrainFrictionOverride = clamp(Number(elements.terrainFriction.value) || 0, 0, 1.5);
    applyTerrainFriction(input.terrainFrictionOverride);
  });
  for (const toggle of elements.imuAxisToggles) {
    toggle.addEventListener("change", () => applyImuAxisToggle(toggle));
  }
  elements.motorDelayToggle?.addEventListener("change", applySignalDelaySettings);
  elements.motorDelaySteps?.addEventListener("change", applySignalDelaySettings);
  elements.imuDelayToggle?.addEventListener("change", applySignalDelaySettings);
  elements.imuDelaySteps?.addEventListener("change", applySignalDelaySettings);
  updateSignalDelayUi();
  for (const button of elements.jumpHeightButtons) {
    button.addEventListener("click", () => setJumpHeightCommand(Number(button.dataset.jumpHeight)));
  }
  for (const button of elements.cruiseButtons) {
    button.addEventListener("click", () => setCruiseSpeed(Number(button.dataset.cruiseSpeed)));
  }
  elements.flipVisualToggle.addEventListener("change", () => {
    syncVisualScene();
  });
  elements.collisionToggle.addEventListener("change", updateRenderFlags);
  elements.wireToggle.addEventListener("change", updateRenderFlags);
  elements.fitViewButton?.addEventListener("click", () => {
    frameCameraToModel();
  });
  elements.trailToggle?.addEventListener("change", () => {
    updateTrail();
    syncViewerStateToUrl();
  });
  bindVelocityCommandControls();
}

function fitViewerCamera() {
  if (!view.camera || !view.controls) return;
  // 取景参数来自包配置（sim.viewer），缺省为通用值——无机器人特判
  const viewer = sim.platformConfig?.sim?.viewer || {};
  const scale = finiteNumber(viewer.camera_scale, 1.0);
  const height = finiteNumber(CONFIG.baseHeightTarget, 0.45);
  view.controls.target.set(0, 0, height);
  view.controls.minDistance = Math.max(0.08, 0.35 * scale);
  view.controls.maxDistance = finiteNumber(viewer.camera_max_distance, 22);
  view.camera.position.set(1.35 * scale, -1.55 * scale, Math.max(height + 0.28 * scale, height + 0.12));
  view.camera.lookAt(view.controls.target);
  view.controls.update();
}

// 自适应取景（借鉴 mjswan 的 lookat/distance 语义）：按模型包围盒计算
// fitDistance 并居中，保持当前视线方向，只调整距离。
function frameCameraToModel() {
  if (!view.camera || !view.controls) return;
  const box = modelBoundingBox();
  if (!box) {
    fitViewerCamera();
    return;
  }
  const center = box.getCenter(new THREE.Vector3());
  const sphere = box.getBoundingSphere(new THREE.Sphere());
  const radius = Math.max(sphere.radius, 0.15);
  const fov = THREE.MathUtils.degToRad(view.camera.fov || 48);
  const verticalFit = radius / Math.max(Math.sin(fov / 2), 1e-3);
  const horizontalFit = verticalFit / Math.max(view.camera.aspect, 0.2);
  const distance = Math.max(verticalFit, horizontalFit) * 1.12;
  const direction = view.camera.position.clone().sub(view.controls.target);
  if (direction.lengthSq() < 1e-6) direction.set(1.35, -1.55, 0.6);
  direction.normalize();
  view.controls.minDistance = Math.max(0.08, radius * 0.25);
  view.controls.maxDistance = Math.max(8, distance * 6);
  view.controls.target.copy(center);
  view.camera.position.copy(center).add(direction.multiplyScalar(distance));
  view.followTarget.copy(center);
  view.camera.lookAt(center);
  view.controls.update();
}

/** 机器人（非 world body）geom 的世界包围盒；没有动态 geom 时返回 null。 */
function modelBoundingBox() {
  if (!view.geoms.length) return null;
  const box = new THREE.Box3();
  const tmp = new THREE.Box3();
  let included = 0;
  // 排除 world body 上的 90m 地面/地形，避免整片地面把相机拉得过远；
  // 同时跳过当前被「视觉模型/碰撞体」开关隐藏的 geom，取景与显示一致。
  for (const renderable of view.geoms) {
    const mesh = renderable?.mesh;
    if (!mesh || !mesh.visible) continue;
    const geomId = mesh.userData.geomId;
    const bodyId = geomId != null ? Number(sim.model?.geom_bodyid?.[geomId] ?? 0) : 0;
    if (bodyId <= 0) continue;
    const geometry = mesh.geometry;
    if (!geometry) continue;
    if (!geometry.boundingBox) geometry.computeBoundingBox();
    if (!geometry.boundingBox) continue;
    tmp.copy(geometry.boundingBox).applyMatrix4(mesh.matrix);
    box.union(tmp);
    included += 1;
  }
  if (!included || box.isEmpty()) return null;
  return box;
}

function applyImuAxisToggle(toggle) {
  const vector = toggle.dataset.imuVector;
  const axis = Number(toggle.dataset.imuAxis);
  const signs = input.imuAxisSigns[vector];
  if (!signs || !Number.isInteger(axis) || axis < 0 || axis > 2) return;
  signs[axis] = toggle.checked ? -1 : 1;
  updateImuAxisSummary();
  refreshPolicyObservation();
}

function updateImuAxisSummary() {
  if (!elements.imuAxisSummary) return;
  const axisNames = ["X", "Y", "Z"];
  const inverted = [];
  for (let axis = 0; axis < 3; axis += 1) {
    if (input.imuAxisSigns.angular[axis] < 0) inverted.push(`角${axisNames[axis]}`);
    if (input.imuAxisSigns.gravity[axis] < 0) inverted.push(`重${axisNames[axis]}`);
  }
  elements.imuAxisSummary.textContent = inverted.length ? inverted.join(" · ") : "原始";
}

function applySignalDelaySettings() {
  input.motorDelayEnabled = Boolean(elements.motorDelayToggle?.checked);
  input.motorDelayMaxSteps = selectedDelaySteps(elements.motorDelaySteps, input.motorDelayMaxSteps);
  input.imuDelayEnabled = Boolean(elements.imuDelayToggle?.checked);
  input.imuDelayMaxSteps = selectedDelaySteps(elements.imuDelaySteps, input.imuDelayMaxSteps);
  if (!input.motorDelayEnabled) {
    sim.motorDelayRemaining = 0;
    applyPendingMotorTargets();
  }
  updateSignalDelayUi();
  refreshPolicyObservation();
}

function selectedDelaySteps(select, fallback) {
  return clamp(Math.round(Number(select?.value) || fallback || 1), 1, SIGNAL_DELAY_MAX_STEPS);
}

function updateSignalDelayUi() {
  const millisecondsPerStep = CONFIG.simulationDt * 1000;
  for (const select of [elements.motorDelaySteps, elements.imuDelaySteps]) {
    if (!select) continue;
    for (const option of select.options) {
      const steps = Number(option.value);
      option.textContent = `${steps} 步 / ${(steps * millisecondsPerStep).toFixed(0)} ms`;
    }
  }
  if (elements.motorDelaySteps) elements.motorDelaySteps.disabled = !input.motorDelayEnabled;
  if (elements.imuDelaySteps) elements.imuDelaySteps.disabled = !input.imuDelayEnabled;
  if (!elements.signalDelaySummary) return;
  const active = [];
  if (input.motorDelayEnabled) active.push(`电机 ${input.motorDelayMaxSteps} 步`);
  if (input.imuDelayEnabled) active.push(`IMU ${input.imuDelayMaxSteps} 步`);
  elements.signalDelaySummary.textContent = active.length ? active.join(" · ") : "关闭";
}

function refreshPolicyObservation() {
  if (!sim.ready || !sim.qpos || !sim.qvel) return;
  OBSERVATION.buildObservation();
  seedHistory(sim.obs);
  resetPolicyState();
}

function bindMobileJoystick() {
  const pad = elements.mobileJoystick;
  const knob = elements.mobileJoystickKnob;
  if (!pad || !knob) return;

  const move = (event) => {
    if (event.pointerId !== input.joystickPointer) return;
    const rect = pad.getBoundingClientRect();
    const radius = rect.width * 0.31;
    let dx = event.clientX - (rect.left + rect.width / 2);
    let dy = event.clientY - (rect.top + rect.height / 2);
    const distance = Math.hypot(dx, dy);
    if (distance > radius) {
      dx *= radius / distance;
      dy *= radius / distance;
    }
    input.joystickTurn = clamp(dx / radius, -1, 1);
    input.joystickForward = clamp(-dy / radius, -1, 1);
    knob.style.transform = `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px))`;
    event.preventDefault();
  };

  const release = (event) => {
    if (event.pointerId !== input.joystickPointer) return;
    resetMobileJoystick();
  };

  pad.addEventListener("pointerdown", (event) => {
    if (input.joystickPointer !== null) return;
    input.joystickPointer = event.pointerId;
    pad.setPointerCapture(event.pointerId);
    move(event);
  });
  pad.addEventListener("pointermove", move);
  pad.addEventListener("pointerup", release);
  pad.addEventListener("pointercancel", release);
}

function resetMobileJoystick() {
  input.joystickPointer = null;
  input.joystickForward = 0;
  input.joystickTurn = 0;
  if (elements.mobileJoystickKnob) {
    elements.mobileJoystickKnob.style.transform = "translate(-50%, -50%)";
  }
}

function setupMujocoFs(mujoco) {
  ensureDir("/working");
  try {
    mujoco.FS.mount(mujoco.MEMFS, { root: "." }, "/working");
  } catch (error) {
    if (!String(error).includes("mount")) throw error;
  }
  ensureDir("/working/assets");
  ensureDir("/working/imgs");
}

async function loadMujocoAssets() {
  const packageInfo = sim.platformConfig?.sim?.asset_package;
  // Go2's learned policy is coupled to the reference MJCF in
  // references_1000framesai.  Keep that exact model/terrain bundle for the
  // browser session even when the package index also exposes a generic Go2
  // descriptor from assets/robots.
  if (activeRobotKey() === "go2") {
    await loadBundledGo2Assets();
    return;
  }
  if (packageInfo?.base_url && Array.isArray(packageInfo.files) && packageInfo.files.length) {
    sim.assetRoot = "/working/platform";
    sim.browserLightweight = Boolean(packageInfo.lightweight_preview);
    ensureDir(sim.assetRoot);
    const revision = packageInfo.revision || packageInfo.generated_at || Date.now();
    const packageFiles = packageInfo.files;
    await loadAssetEntries(
      packageFiles.map((path) => {
        const relPath = String(path).replace(/^\/+/, "");
        return {
          label: relPath,
          src: cacheBustedUrl(new URL(relPath, new URL(packageInfo.base_url, window.location.href)).toString(), revision),
          dest: `${sim.assetRoot}/${relPath}`,
          credentials: "include",
        };
      }),
      { start: 0.28, span: 0.3, loadingLabel: "加载平台资源" },
    );
    activateSelectedPackageModel(packageInfo);
    return;
  }

  const builtinRobot = String(sim.platformConfig?.sim?.builtin_robot || "").toLowerCase();
  if (builtinRobot === "go2" || !sim.platformConfig?.run_id) {
    await loadBundledGo2Assets();
    return;
  }

  if (builtinRobot === "fsdog1" || activeRobotKey() === "fsdog1") {
    sim.assetRoot = "/working";
    const sceneFiles = await buildFsdogSceneFiles();
    const files = [
      ["./assets/fsdog1/fsdog1.xml", "/working/fsdog1.xml"],
      ...IMAGE_FILES.map((name) => [`./assets/go2/imgs/${name}`, `/working/imgs/${name}`]),
    ];
    for (let index = 0; index < files.length; index += 1) {
      const [src, dest] = files[index];
      const response = await fetch(src);
      if (!response.ok) throw new Error(`asset load failed: ${src}`);
      const data = new Uint8Array(await response.arrayBuffer());
      sim.mujoco.FS.writeFile(dest, data);
      setLoading(0.28 + 0.18 * ((index + 1) / files.length), `加载 FSDog 资源 ${index + 1}/${files.length}`);
    }
    for (const [name, text] of sceneFiles.entries()) {
      sim.mujoco.FS.writeFile(`/working/${name}`, text);
    }
    return;
  }

  // No platform asset package and not the fsdog1 builtin → this robot has no
  // simulation model. Do NOT silently fall back to a generic go2; surface a
  // clear error so the user knows to (re)build the robot's URDF→MJCF assets.
  throw new Error(
    "该机器人没有可用的仿真模型（URDF→MJCF 资源包缺失）。请重新上传/导出其 URDF 后重试。"
  );
}

async function loadBundledGo2Assets() {
  sim.assetRoot = "/working";
  await loadAssetEntries([
    ...XML_FILES.map((name) => ({ src: bundledTerrainUrl(name), dest: `/working/${name}` })),
    ...MESH_FILES.map((name) => ({ src: `./assets/go2/assets/${name}`, dest: `/working/assets/${name}` })),
    ...IMAGE_FILES.map((name) => ({ src: `./assets/go2/imgs/${name}`, dest: `/working/imgs/${name}` })),
  ], { start: 0.28, span: 0.18, loadingLabel: "加载 Go2 资源" });
  // 公共地图库（assets/maps/）：内置链路的 FS 是 /working 平铺布局，地图在
  // /working/maps/ 下执行，服务端注入的 include "../model/robot.xml" 需要
  // /working/model/robot.xml 存在——用 go2.xml 落一份副本即可满足。
  try {
    const packageInfo = sim.platformConfig?.sim?.asset_package;
    const mapFiles = (packageInfo?.files || []).filter((f) => String(f).startsWith("maps/"));
    if (mapFiles.length && packageInfo?.base_url) {
      const robotCopy = sim.mujoco.FS.analyzePath("/working/go2.xml");
      if (robotCopy.exists) {
        ensureParentDirs("/working/model/robot.xml");
        sim.mujoco.FS.writeFile("/working/model/robot.xml", sim.mujoco.FS.readFile("/working/go2.xml"));
      }
      await loadAssetEntries(
        mapFiles.map((rel) => ({
          label: rel,
          src: cacheBustedUrl(new URL(String(rel).replace(/^\/+/, ""), new URL(packageInfo.base_url, window.location.href)).toString(), packageInfo.revision || Date.now()),
          dest: `/working/${String(rel).replace(/^\/+/, "")}`,
          credentials: "include",
          // go2 内置 FS 是平铺布局（mesh 在 /working/assets），平台布局的
          // "../model/assets" 在此解析不到 mesh，落盘前改写。
          rewriteXml: (xml) => xml.replace('meshdir="../model/assets"', 'meshdir="../assets"'),
        })),
        { start: 0.46, span: 0.1, loadingLabel: "加载公共地图" },
      );
    }
  } catch (error) {
    console.warn("[sim2sim] 公共地图加载失败（内置地形仍可用）:", error);
  }
}

async function loadAssetEntries(entries, { start, span, loadingLabel }) {
  let nextIndex = 0;
  let completed = 0;
  const total = entries.length;
  const workerCount = Math.min(ASSET_FETCH_CONCURRENCY, total);

  async function worker() {
    while (true) {
      const index = nextIndex;
      nextIndex += 1;
      if (index >= total) return;
      const entry = entries[index];
      ensureParentDirs(entry.dest);
      const response = await fetch(entry.src, {
        cache: "force-cache",
        credentials: entry.credentials || "same-origin",
      });
      if (!response.ok) throw new Error(`资源加载失败：${entry.label || entry.src}`);
      const data = new Uint8Array(await response.arrayBuffer());
      if (entry.dest.toLowerCase().endsWith(".xml")) {
        let rawXml = new TextDecoder().decode(data);
        if (typeof entry.rewriteXml === "function") rawXml = entry.rewriteXml(rawXml);
        // MuJoCo resolves an included model's meshdir relative to that model's
        // OWN directory (model/), not the including scene's. The package
        // robot.xml already carries meshdir="assets" (relative to model/), so
        // no rewrite here: rewriting it to "model/assets" broke every meshed
        // package (opening 'model/assets/...' from within model/).
        sim.mujoco.FS.writeFile(entry.dest, rawXml);
      } else {
        sim.mujoco.FS.writeFile(entry.dest, data);
      }
      completed += 1;
      setLoading(start + span * (completed / total), `${loadingLabel} ${completed}/${total}`);
    }
  }

  await Promise.all(Array.from({ length: workerCount }, () => worker()));
}

async function buildFsdogSceneFiles() {
  const scenes = new Map();
  for (let index = 0; index < FSDOG_SCENE_FILES.length; index += 1) {
    const name = FSDOG_SCENE_FILES[index];
    const response = await fetch(bundledTerrainUrl(name));
    if (!response.ok) throw new Error(`资源加载失败：./assets/go2/${name}`);
    const source = await response.text();
    scenes.set(name, source.replace(/<include\s+file=["']go2\.xml["']\s*\/>/i, '<include file="fsdog1.xml"/>'));
    setLoading(0.46 + 0.12 * ((index + 1) / FSDOG_SCENE_FILES.length), `准备 FSDog 地形 ${index + 1}/${FSDOG_SCENE_FILES.length}`);
  }
  return scenes;
}

function bundledTerrainUrl(name) {
  return `./assets/go2/${name}?v=${BUNDLED_TERRAIN_ASSET_REVISION}`;
}

async function loadTerrain(xmlName) {
  if (!sim.mujoco || !xmlName) return;
  if (sim.loadingTerrain) {
    sim.pendingTerrain = xmlName;
    return;
  }
  sim.loadingTerrain = true;
  sim.pendingTerrain = "";
  sim.ready = false;
  elements.terrainSelect.disabled = true;
  elements.loading.classList.remove("is-hidden");
  setLoading(0.72, `加载${terrainLabel(xmlName)}...`);

  let nextModel = null;
  let nextData = null;
  try {
    await setLoadingPainted(0.72, `④a 编译 ${terrainLabel(xmlName)} 场景...`);
    const tXml = performance.now();
    // 场景名可能来自平台 manifest 的 HTTP 相对路径（web/sim2sim/assets/...），
    // 而内置 go2 资源写在 /working/<basename>。精确路径不存在时回退到
    // basename，避免 ParseXML "Error opening file" 导致视口空白。
    let scenePath = `${sim.assetRoot}/${xmlName}`;
    if (!sim.mujoco.FS.analyzePath(scenePath).exists) {
      const fallbackPath = `${sim.assetRoot}/${sceneBasename(xmlName)}`;
      if (sim.mujoco.FS.analyzePath(fallbackPath).exists) scenePath = fallbackPath;
    }
    nextModel = loadMjModel(scenePath);
    console.log(`[sim2sim] ✔ loadMjModel(${xmlName}) ${(performance.now() - tXml).toFixed(0)}ms`);
    nextModel.opt.timestep = CONFIG.simulationDt;
    nextData = new sim.mujoco.MjData(nextModel);

    disposeMujocoScene();
    clearRenderGeoms();
    sim.model = nextModel;
    sim.data = nextData;
    nextModel = null;
    nextData = null;
    sim.qpos = sim.data.qpos;
    sim.qvel = sim.data.qvel;
    sim.ctrl = sim.data.ctrl;
    resolveJointAddresses();
    resolveActuatorAddresses();
    initializeTerrainFriction(xmlName);
    initializePayloadMass();

    resetSimulation();
    frameCameraToModel();
    sim.paused = VIEWER_ONLY;
    elements.playButton.textContent = sim.paused ? "继续" : "暂停";
    sim.ready = true;
    sim.currentTerrain = xmlName;
    setStatus(elements.engineStatus, "MuJoCo 已就绪", "ready");
    elements.loading.classList.add("is-hidden");
  } catch (error) {
    try { nextData?.delete?.(); } catch (_) { /* no-op */ }
    try { nextModel?.delete?.(); } catch (_) { /* no-op */ }
    console.error(error);
    const described = describeLoadError(error);
    setStatus(elements.engineStatus, "MuJoCo 错误", "error");
    showLoadingError(described?.message || String(described || error));
    if (sim.model && sim.data) {
      sim.ready = true;
      elements.terrainSelect.value = sim.currentTerrain;
    }
  } finally {
    sim.loadingTerrain = false;
    elements.terrainSelect.disabled = false;
    const pending = sim.pendingTerrain;
    sim.pendingTerrain = "";
    if (pending && pending !== sim.currentTerrain) queueMicrotask(() => loadTerrain(pending));
  }
}

function activateSelectedPackageModel(packageInfo) {
  const models = Array.isArray(packageInfo.models) ? packageInfo.models : [];
  const requested = PAGE_PARAMS.get("model") || models[0]?.id || "default";
  const selected = models.find((item) => item?.id === requested || item?.path === requested) || models[0];
  const selectedPath = String(selected?.path || "model/robot.xml").replace(/^\/+/, "");
  if (selectedPath === "model/robot.xml") return;
  const source = `${sim.assetRoot}/${selectedPath}`;
  const destination = `${sim.assetRoot}/model/robot.xml`;
  try {
    sim.mujoco.FS.writeFile(destination, sim.mujoco.FS.readFile(source));
  } catch (error) {
    throw new Error(`Selected model is unavailable: ${selectedPath} (${error?.message || error})`);
  }
}

function initializeTerrainFriction(xmlName) {
  const modelDefault = firstWorldGeomFriction();
  const terrainName = sceneBasename(xmlName).trim().toLowerCase();
  const sceneDefault = LOW_FRICTION_TERRAINS.has(terrainName)
    ? STAIR_SURFACE_FRICTION
    : modelDefault;
  const selected = Number.isFinite(input.terrainFrictionOverride)
    ? input.terrainFrictionOverride
    : sceneDefault;
  applyTerrainFriction(selected);
}

function firstWorldGeomFriction() {
  if (!sim.model?.geom_friction || !sim.model?.geom_bodyid) return 1;
  for (let geom = 0; geom < sim.model.ngeom; geom += 1) {
    if (sim.model.geom_bodyid[geom] === 0) {
      return clamp(Number(sim.model.geom_friction[geom * 3]) || 0, 0, 1.5);
    }
  }
  return 1;
}

function applyTerrainFriction(value) {
  const coefficient = clamp(Number(value) || 0, 0, 1.5);
  input.terrainFriction = coefficient;
  if (elements.terrainFriction) {
    elements.terrainFriction.value = String(coefficient);
    elements.terrainFriction.setAttribute("aria-valuetext", coefficient.toFixed(2));
  }
  if (elements.terrainFrictionLabel) {
    elements.terrainFrictionLabel.textContent = coefficient.toFixed(2);
  }
  if (!sim.model?.geom_friction) return;
  // MuJoCo combines the two contacting geoms' friction. Update both the
  // terrain and robot sides so zero really removes traction.
  for (let geom = 0; geom < sim.model.ngeom; geom += 1) {
    const offset = geom * 3;
    sim.model.geom_friction[offset] = coefficient;
    sim.model.geom_friction[offset + 1] = coefficient > 0 ? 0.005 : 0;
    sim.model.geom_friction[offset + 2] = coefficient > 0 ? 0.0001 : 0;
  }
  if (sim.data) sim.mujoco.mj_forward(sim.model, sim.data);
}

function loadMjModel(path) {
  if (typeof sim.mujoco.MjModel.loadFromXML === "function") {
    return sim.mujoco.MjModel.loadFromXML(path);
  }
  if (typeof sim.mujoco.MjModel.mj_loadXML === "function") {
    return sim.mujoco.MjModel.mj_loadXML(path);
  }
  throw new Error("当前 MuJoCo 组件不支持加载 XML 场景");
}

// ---------------------------------------------------------------------------
// .mjz 打包格式脚手架（item 14，借鉴 mjswan utils/mjzLoader 的思路）
// ---------------------------------------------------------------------------
// 约定：.mjz = ZIP 包，根目录含一个主 MJCF XML（唯一 *.xml 或 model.xml），
// 其余为 XML 引用的 assets（mesh/texture/hfield 等），保持包内相对路径。
//
// JSZip 引入方案（TODO）：
//   1. 下载 jszip.min.js 放入 web/sim2sim/vendor/jszip/（与 three/mujoco 同级，
//      本地 vendored，避免 CDN 运行时依赖）；
//   2. 因 importmap 只映射了 three，JSZip 用动态 import 加载：
//        const JSZip = (await import("./vendor/jszip/jszip.min.js")).default;
//   3. 失败时抛出可读错误提示部署方放置依赖，而不是静默降级。
//
// TODO(实现清单)：
//   a) zip.loadAsync(arrayBuffer) 遍历 entries；
//   b) 根目录 *.xml（TextDecoder 解码）写入 MEMFS /working/mjz/<name>；
//   c) 其余条目按包内相对路径写入 /working/mjz/（保持 meshdir 相对引用成立），
//      注意目录条目（以 / 结尾）要跳过；
//   d) 返回主 XML 的 MEMFS 路径，调用方交给 loadMjModel(path)。
async function loadMjzPackage(arrayBuffer, { entry = "" } = {}) {
  void entry;
  throw new Error(
    ".mjz 打包加载尚未实现：请按 app.js 中 loadMjzPackage 的注释放置 vendor/jszip 并完成解包流程。",
  );
}

function resolveJointAddresses() {
  sim.jointQposAdr = CONFIG.jointOrder.map((name, index) => {
    try {
      const address = Number(sim.model?.jnt?.(name)?.qposadr);
      if (Number.isInteger(address) && address >= 0) return address;
    } catch (_) { /* use the conventional free-joint layout */ }
    return 7 + index;
  });
  sim.jointDofAdr = CONFIG.jointOrder.map((name, index) => {
    try {
      const address = Number(sim.model?.jnt?.(name)?.dofadr);
      if (Number.isInteger(address) && address >= 0) return address;
    } catch (_) { /* use the conventional free-joint layout */ }
    return 6 + index;
  });
}

function resolveActuatorAddresses() {
  const count = Number(sim.model?.nu || sim.ctrl?.length || 0);
  const actuatorEnum = enumValue(sim.mujoco?.mjtObj?.mjOBJ_ACTUATOR);
  const jointEnum = enumValue(sim.mujoco?.mjtObj?.mjOBJ_JOINT);
  const trnid = sim.model?.actuator_trnid;
  sim.actuatorIds = CONFIG.jointOrder.map((jointName, index) => {
    let jointId = -1;
    try {
      jointId = Number(sim.mujoco.mj_name2id(sim.model, jointEnum, jointName));
    } catch (_) { /* fall through to name/order lookup */ }
    if (jointId >= 0 && trnid) {
      for (let actuatorId = 0; actuatorId < count; actuatorId += 1) {
        if (Number(trnid[actuatorId * 2]) === jointId) return actuatorId;
      }
    }
    try {
      const named = sim.model?.actuator?.(jointName);
      const namedId = Number(named?.id);
      if (Number.isInteger(namedId) && namedId >= 0) return namedId;
    } catch (_) { /* use mj_name2id below */ }
    try {
      const namedId = Number(sim.mujoco.mj_name2id(sim.model, actuatorEnum, jointName));
      if (Number.isInteger(namedId) && namedId >= 0) return namedId;
    } catch (_) { /* final positional fallback */ }
    return index < count ? index : -1;
  });
  if (DEBUG_ENABLED) console.info("[sim2sim] actuator map", sim.actuatorIds, CONFIG.jointOrder);
}

function jointQpos(index) {
  return sim.qpos?.[sim.jointQposAdr[index] ?? (7 + index)] ?? 0;
}

function jointQvel(index) {
  return sim.qvel?.[sim.jointDofAdr[index] ?? (6 + index)] ?? 0;
}

function setJointQpos(index, value) {
  const address = sim.jointQposAdr[index] ?? (7 + index);
  if (sim.qpos && address < sim.qpos.length) sim.qpos[address] = value;
}

function resetSimulation() {
  if (!sim.model || !sim.data) return;
  resetPolicyState();
  const initialKeyframe = String(sim.platformConfig?.robot?.control?.initial_keyframe || "");
  let keyframeId = -1;
  if (initialKeyframe && sim.mujoco.mj_name2id && sim.mujoco.mjtObj?.mjOBJ_KEY !== undefined) {
    keyframeId = Number(sim.mujoco.mj_name2id(
      sim.model,
      enumValue(sim.mujoco.mjtObj.mjOBJ_KEY),
      initialKeyframe,
    ));
  }
  if (keyframeId >= 0 && typeof sim.mujoco.mj_resetDataKeyframe === "function") {
    sim.mujoco.mj_resetDataKeyframe(sim.model, sim.data, keyframeId);
  } else {
    sim.mujoco.mj_resetData(sim.model, sim.data);
  }
  applyPayloadMass();
  applyCenterOfMassOffset();
  if (CONFIG.baseHeightTarget !== null && sim.qpos.length >= 7 + CONFIG.numActions) {
    sim.qpos[2] = CONFIG.baseHeightTarget;
  }
  for (let i = 0; i < CONFIG.numActions; i += 1) {
    setJointQpos(i, CONFIG.defaultAngles[i]);
    sim.action[i] = 0;
    sim.appliedAction[i] = 0;
    sim.filteredAction[i] = 0;
    sim.targetDofPos[i] = CONFIG.defaultAngles[i];
    sim.targetDofVel[i] = 0;
    sim.pendingTargetDofPos[i] = CONFIG.defaultAngles[i];
    sim.pendingTargetDofVel[i] = 0;
  }
  sim.motorTargetPending = false;
  sim.motorDelayRemaining = 0;
  sim.filterPrimed = false;
  input.motorDelaySampleSteps = 0;
  input.imuDelaySampleSteps = 0;
  sim.history.fill(0);
  sim.gaitElapsedS = 0;
  // Imitation policies: realign the reference motion to the robot's current
  // heading (yaw-only) and restart from the configured start time.
  if (sim.motionLoader) {
    OBSERVATION.resetMotionTime();
    sim.motionLoader.update(0);
    sim.motionLoader.reset(Array.from(sim.qpos.subarray(3, 7)), 0);
  }
  sim.gaitActive = false;
  sim.jumpPulseDuration = 0;
  sim.jumpPulseUntil = 0;
  sim.jumpStartedAt = 0;
  sim.jumpActive = false;
  sim.jumpStartPending = false;
  sim.g1PhaseS = 0;
  cancelDragInteraction();
  resetTrail();
  sim.weights.fill(0);
  sim.estimatedVel.fill(0);
  sim.latent.fill(0);
  applyIdleCommand();
  sim.counter = 0;
  sim.accumulator = 0;
  sim.data.time = 0;
  sim.mujoco.mj_forward(sim.model, sim.data);
  if (CONFIG.settleSteps > 0 && CONFIG.actuatorInterface === "position_target") {
    settleRobot();
    sim.data.time = 0;
  }
  resetImuSamples();
  OBSERVATION.buildObservation();
  seedHistory(sim.obs);
  syncVisualScene();
  updateHud(true);
}

function initializePayloadMass() {
  sim.baseBodyId = findFreeBaseBodyId();
  sim.baseBodyMassKg = sim.baseBodyId >= 0
    ? Number(sim.model.body_mass?.[sim.baseBodyId] || 0)
    : 0;
  sim.baseBodyComLocal.fill(0);
  if (sim.baseBodyId >= 0 && sim.model.body_ipos) {
    const offset = sim.baseBodyId * 3;
    for (let axis = 0; axis < 3; axis += 1) {
      sim.baseBodyComLocal[axis] = Number(sim.model.body_ipos[offset + axis] || 0);
    }
  }
  applyPayloadMass();
  applyCenterOfMassOffset();
}

function findFreeBaseBodyId() {
  if (!sim.model) return -1;
  const requestedFreeJointType = enumValue(sim.mujoco?.mjtJoint?.mjJNT_FREE);
  const freeJointType = Number.isFinite(requestedFreeJointType) ? requestedFreeJointType : 0;
  for (let bodyId = 1; bodyId < Number(sim.model.nbody || 0); bodyId += 1) {
    const jointStart = Number(sim.model.body_jntadr?.[bodyId] ?? -1);
    const jointCount = Number(sim.model.body_jntnum?.[bodyId] ?? 0);
    for (let offset = 0; offset < jointCount; offset += 1) {
      if (Number(sim.model.jnt_type?.[jointStart + offset]) === freeJointType) return bodyId;
    }
  }
  return Number(sim.model.body_mass?.[1] || 0) > 0 ? 1 : -1;
}

function applyPayloadMass() {
  const payloadKg = clamp(Number(input.payloadMassKg) || 0, 0, MAX_PAYLOAD_KG);
  input.payloadMassKg = payloadKg;
  if (elements.payloadMass) elements.payloadMass.value = String(payloadKg);
  if (elements.payloadMassLabel) elements.payloadMassLabel.textContent = `${payloadKg.toFixed(1)} kg`;
  if (!sim.model || sim.baseBodyId < 0 || !(sim.baseBodyMassKg > 0)) return;
  sim.model.body_mass[sim.baseBodyId] = sim.baseBodyMassKg + payloadKg;
  if (sim.data) sim.mujoco.mj_forward(sim.model, sim.data);
}

function applyCenterOfMassOffset() {
  for (const slider of elements.comOffsetSliders) {
    const axis = Number(slider.dataset.comAxis);
    if (!Number.isInteger(axis) || axis < 0 || axis > 2) continue;
    input.comOffsetM[axis] = clamp(Number(slider.value) || 0, -0.1, 0.1);
  }
  for (const output of elements.comOffsetValues) {
    const axis = Number(output.dataset.comValue);
    if (!Number.isInteger(axis) || axis < 0 || axis > 2) continue;
    const millimetres = Math.round(input.comOffsetM[axis] * 1000);
    output.textContent = `${millimetres > 0 ? "+" : ""}${millimetres} mm`;
  }
  if (elements.comOffsetSummary) {
    const labels = ["X", "Y", "Z"];
    const active = labels
      .map((label, axis) => [label, Math.round(input.comOffsetM[axis] * 1000)])
      .filter(([, value]) => value !== 0)
      .map(([label, value]) => `${label}${value > 0 ? "+" : ""}${value}`);
    elements.comOffsetSummary.textContent = active.length ? `${active.join(" ")} mm` : "0 mm";
  }
  if (!sim.model?.body_ipos || sim.baseBodyId < 0) return;
  const offset = sim.baseBodyId * 3;
  for (let axis = 0; axis < 3; axis += 1) {
    sim.model.body_ipos[offset + axis] = sim.baseBodyComLocal[axis] + input.comOffsetM[axis];
  }
  if (sim.data) sim.mujoco.mj_forward(sim.model, sim.data);
}

async function frame(now) {
  if (!view.lastFrameTime) view.lastFrameTime = now;
  const elapsed = Math.min((now - view.lastFrameTime) / 1000, CONFIG.maxFrameDt);
  view.lastFrameTime = now;
  view.frames += 1;

  if (sim.ready && !sim.paused && !sim.loadingTerrain) {
    sim.accumulator += elapsed;
    let steps = 0;
    try {
      while (sim.accumulator >= CONFIG.simulationDt && steps < CONFIG.maxStepsPerFrame) {
        await stepSimulation();
        sim.accumulator -= CONFIG.simulationDt;
        steps += 1;
      }
      if (steps === CONFIG.maxStepsPerFrame) sim.accumulator = 0;
      // 本帧物理成功则清除连续错误计数，恢复正常状态显示。
      if (view.frameErrorCount) {
        view.frameErrorCount = 0;
        setStatus(elements.engineStatus, "MuJoCo 已就绪", "ready");
      }
    } catch (error) {
      // 借鉴 mjswan runtime.ts 的容错语义：单步异常只记录并显示状态，
      // 下一帧继续尝试（清空 accumulator 防止错误后爆发性补步），
      // 而不是永久置错误态卡死循环。
      view.frameErrorCount = (view.frameErrorCount || 0) + 1;
      sim.accumulator = 0;
      console.error(`[sim2sim] frame error #${view.frameErrorCount}`, error);
      setStatus(
        elements.engineStatus,
        `仿真异常 · 自动重试中（${view.frameErrorCount}）`,
        "error",
      );
    }
  }

  // 暂停（sim.paused）只停 stepSimulation；syncVisualScene + renderer.render
  // 照常执行，冻结帧仍可旋转视角/缩放（对齐 mjswan 的 pause 语义）。
  if (sim.ready) {
    syncVisualScene();
    updateFollowCamera();
    updateDragArrow();
    updateTrail();
    updateHud(false);
  }
  // 诊断探针：骨盆高度 / 是否在跑
  try {
    window.__probe = {
      z: sim.qpos ? sim.qpos[2] : null,
      playing: sim.ready && !sim.paused,
      act0: sim.action ? Number(sim.action[0]) : null,
      obsNonZero: sim.obs ? Array.from(sim.obs).some((v) => Math.abs(v) > 1e-6) : null,
      obsHead: sim.obs ? Array.from(sim.obs.slice(0, 8)).map((v) => Number(v.toFixed(3))) : null,
      tpos0: sim.targetDofPos ? Number(sim.targetDofPos[0].toFixed(3)) : null,
      actIds: sim.actuatorIds ? Array.from(sim.actuatorIds.slice(0, 4)) : null,
    };
  } catch (_) {}

  view.controls.update();
  view.renderer.render(view.scene, view.camera);
  updatePerf(now);
  requestAnimationFrame(frame);
}

async function stepSimulation() {
  updateCommand();
  if (sim.counter % CONFIG.controlDecimation === 0) {
    activatePendingJumpCommand();
    await runPolicy();
    OBSERVATION.advanceWheelLegGaitClock();
  }
  advanceMotorDelay();

  for (let i = 0; i < CONFIG.numActions; i += 1) {
    const q = jointQpos(i);
    const dq = jointQvel(i);
    const mode = CONFIG.controlModes[i];
    const actuatorId = sim.actuatorIds[i] ?? i;
    if (actuatorId < 0 || actuatorId >= sim.ctrl.length) continue;

    // Native MuJoCo position/velocity actuators consume targets directly.
    // Applying a second browser-side PD loop here turns a target into a
    // nonsensical angle/velocity and was the source of MicroDuck/ZEX-W falls.
    if (CONFIG.actuatorInterface === "position_target") {
      sim.ctrl[actuatorId] = mode === "velocity"
        ? sim.targetDofVel[i]
        : (mode === "torque" ? sim.filteredAction[i] * actionScaleForJoint(i) : sim.targetDofPos[i]);
      CONFIG.dynamicTorqueLimits[i] = 0;
      continue;
    }

    let torque;
    if (mode === "velocity") {
      torque = (sim.targetDofVel[i] - dq) * CONFIG.kds[i];
    } else if (mode === "torque") {
      torque = sim.filteredAction[i] * actionScaleForJoint(i);
    } else {
      torque = (sim.targetDofPos[i] - q) * CONFIG.kps[i] - dq * CONFIG.kds[i];
    }
    const fixedLimit = CONFIG.torqueLimits[i];
    const envelopeLimit = motorEnvelopeTorqueAtSpeed(CONFIG.motorEnvelopes[i], dq);
    const velocityLimit = CONFIG.motorVelocityLimits[i];
    const linearDcLimit = fixedLimit > 0 && velocityLimit > 0
      ? fixedLimit * clamp(1 - Math.abs(dq) / velocityLimit, 0, 1)
      : (fixedLimit > 0 ? fixedLimit : null);
    const limit = envelopeLimit === null
      ? linearDcLimit
      : (fixedLimit > 0 ? Math.min(fixedLimit, envelopeLimit) : envelopeLimit);
    CONFIG.dynamicTorqueLimits[i] = limit === null ? 0 : limit;
    if (limit !== null) torque = clamp(torque, -limit, limit);
    sim.ctrl[actuatorId] = torque;
  }

  applyDragForce();
  sim.mujoco.mj_step(sim.model, sim.data);
  if (!stateIsFinite()) {
    resetSimulation();
    return;
  }
  updateJumpCommandState();
  recordImuSample();
  sim.counter += 1;
  view.simSteps += 1;
}

// ---------------------------------------------------------------------------
// ONNX 推理串行队列（item 11，借鉴 mjswan runQueue.ts）
// ---------------------------------------------------------------------------

// ORT-Web 的 wasm 绑定持有模块级 active-run 槽位：并发 run() 会抛
// "Session already started" / "Session mismatch"。全部 session.run 走这条
// promise 链即可串行化——wasm 后端本来就是单线程，没有吞吐损失。
let ortRunTail = Promise.resolve();

/**
 * 等前一次推理落定后再执行 `inference`。
 * 成功/失败两条路径都推进队列：失败的 run 同样会释放 ORT 的槽位。
 */
function queueOrtRun(inference) {
  const result = ortRunTail.then(inference, inference);
  ortRunTail = result.catch(() => undefined);
  return result;
}

function stateIsFinite() {
  for (let i = 0; i < sim.qpos.length; i += 1) {
    if (!Number.isFinite(sim.qpos[i])) return false;
  }
  for (let i = 0; i < sim.qvel.length; i += 1) {
    if (!Number.isFinite(sim.qvel[i])) return false;
  }
  return sim.qpos[2] > -0.5 && sim.qpos[2] < 3.0;
}

async function runPolicy() {
  if (!sim.policyEnabled || !sim.policy || !sim.policyInfo) {
    holdStance();
    OBSERVATION.buildObservation();
    pushHistory(sim.obs);
    return;
  }
  OBSERVATION.buildObservation();
  if (sim.frameLog && sim.frameLog.length < 300) {
    // 帧口径 = 控制步序号（counter/decimation），与桌面验收器的逐帧序列一一对应；
    // sim.time 仍随记录（调试用），但对齐 replay_diff 时以 stepIndex 为准。
    sim.frameLog.push({
      t: Number((sim.data?.time ?? 0).toFixed(3)),
      stepIndex: Math.floor(sim.counter / CONFIG.controlDecimation),
      obs: Array.from(sim.obs),
      action: null,
      ctrlBefore: Array.from(sim.ctrl),
    });
  }
  const info = sim.policyInfo;
  const policyStateEpoch = sim.policyStateEpoch;
  // encoder+policy 链（TRON1）：encoder 吃单帧 obs 的 oldest→newest 历史 → latent，
  // policy 输入 = [latent, obs, 缩放命令]（1D）。
  let encoderOutput = null;
  if (sim.encoderSession && sim.encoderHistory) {
    const frames = sim.encoderFrames;
    sim.encoderHistory.copyWithin(0, CONFIG.numObs);
    sim.encoderHistory.set(sim.obs, (frames - 1) * CONFIG.numObs);
    const encName = sim.encoderSession.inputNames[0];
    const encOut = await queueOrtRun(() => sim.encoderSession.run({
      [encName]: new ort.Tensor("float32", new Float32Array(sim.encoderHistory), [sim.encoderHistory.length]),
    }));
    encoderOutput = encOut[sim.encoderSession.outputNames[0]].data;
  }
  const feeds = {};
  if (encoderOutput) {
    const scale = CONFIG.tron1CmdScale || [1, 1, 1];
    const scaled = new Float32Array(3);
    for (let i = 0; i < 3; i += 1) scaled[i] = (sim.cmd[i] || 0) * (scale[i] || 1);
    const total = encoderOutput.length + CONFIG.numObs + 3;
    const buf = new Float32Array(total);
    buf.set(encoderOutput.subarray ? encoderOutput.subarray(0, encoderOutput.length) : encoderOutput, 0);
    buf.set(sim.obs, encoderOutput.length);
    buf.set(scaled, encoderOutput.length + CONFIG.numObs);
    feeds[info.obsName] = new ort.Tensor("float32", buf, [total]);
  } else if (info.depthName) {
    // 多输入 + 深度（PIE）：proprio 单帧 + 展平本体历史 + 深度历史（浏览器 raycast）。
    feeds[info.obsName] = new ort.Tensor("float32", new Float32Array(sim.obs), [1, CONFIG.numObs]);
    if (info.historyName && info.historyFlatSize) {
      const packed = buildPolicyObs(info.historyFlatSize);
      feeds[info.historyName] = new ort.Tensor("float32", packed, [1, packed.length]);
    }
    if (sim.pieDepth) {
      if (sim.depthCounter % sim.pieDepth.updateSteps === 0) {
        const frame = sim.pieDepth.captureFrame();
        if (!sim.depthHistory || sim.depthHistory.length === 0) {
          sim.depthHistory = [frame.slice(), frame.slice()];
        } else {
          sim.depthHistory.push(frame);
          while (sim.depthHistory.length > 2) sim.depthHistory.shift();
        }
      }
      sim.depthCounter += 1;
      const h = sim.pieDepth.frameShape[1];
      const w = sim.pieDepth.frameShape[2];
      const buf = new Float32Array(2 * h * w);
      buf.set(sim.depthHistory[0], 0);
      buf.set(sim.depthHistory[1], h * w);
      feeds[info.depthName] = new ort.Tensor("float32", buf, [1, 2, h, w]);
    }
  } else if (info.historyName) {
    const frames = info.historyFrames || Math.floor(sim.history.length / CONFIG.numObs) || 5;
    feeds[info.obsName] = new ort.Tensor("float32", new Float32Array(sim.obs), [1, CONFIG.numObs]);
    feeds[info.historyName] = new ort.Tensor("float32", new Float32Array(sim.history), [1, frames, CONFIG.numObs]);
  } else {
    const obs = buildPolicyObs(info.obsSize);
    feeds[info.obsName] = new ort.Tensor("float32", obs, [1, obs.length]);
  }
  for (const state of info.recurrentStates || []) {
    const data = sim.recurrentState[state.inputName] || allocateTensorData(state.type, state.size);
    feeds[state.inputName] = new ort.Tensor(state.type, data, state.shape);
  }
  const output = await queueOrtRun(() => sim.policy.run(feeds));
  if (policyStateEpoch !== sim.policyStateEpoch) return;
  let action = output[info.actionName]?.data || output.action?.data || output.actions?.data;
  const weights = info.weightsName ? output[info.weightsName]?.data : null;
  const estimatedVel = info.estimatedVelName ? output[info.estimatedVelName]?.data : null;
  const latent = info.latentName ? output[info.latentName]?.data : null;
  const nextHistory = info.nextHistoryName ? output[info.nextHistoryName]?.data : null;
  if (!action) throw new Error(`策略输出缺少动作张量；输出=${info.outputNames.join(",")}`);
  // TRON1：policy 输出为 isaaclab 关节序，反解回 SDK 序供 actuate 使用。
  if (encoderOutput && Array.isArray(CONFIG.tron1Swap)) {
    const map = CONFIG.tron1Swap;
    const sdk = new Float32Array(action.length);
    for (let i = 0; i < map.length && i < action.length; i += 1) sdk[map[i]] = action[i];
    action = sdk;
  }
  updateRecurrentStates(output, info);

  // 训练端 clip_actions 在 scale/offset 前逐关节裁剪原始动作（部署一致）。
  const clip = CONFIG.actionClip;
  const clipped = new Float32Array(CONFIG.numActions);
  for (let i = 0; i < CONFIG.numActions; i += 1) {
    // sim.action keeps the raw network output order (this is what the obs action
    // segment feeds back, matching NP3O's action_history_buf[:,-1]). Linear
    // heads can emit extreme values on a corrupted observation; deployment
    // clips raw actions to +-100 before feeding them back, then to the
    // contract's clip_actions bound (if any).
    let value = clamp(action[i], -100, 100);
    if (clip !== null && clip !== undefined) {
      const limit = typeof clip === "number" ? clip : clip[i];
      if (Number.isFinite(limit) && limit > 0) value = clamp(value, -limit, limit);
    }
    clipped[i] = value;
    sim.action[i] = value;
    // Some policies train with a target low-pass filter.  This is explicit in
    // the policy contract: go2_rl_gym uses alpha=1 (no persistent filter).
    // True IIR against the previous filtered output — averaging against the
    // previous raw input kills the filter and destabilises filtered policies.
    const applied = CONFIG.actionReindex ? clipped[CONFIG.actionReindex[i]] : clipped[i];
    const previousFiltered = sim.filterPrimed ? sim.filteredAction[i] : applied;
    sim.appliedAction[i] = applied;
    const alpha = filterAlphaForJoint(i);
    sim.filteredAction[i] = applied * alpha + previousFiltered * (1 - alpha);
    if (CONFIG.controlModes[i] === "velocity") {
      sim.pendingTargetDofPos[i] = CONFIG.defaultAngles[i];
      sim.pendingTargetDofVel[i] = sim.filteredAction[i] * velocityScaleForJoint(i);
    } else {
      sim.pendingTargetDofPos[i] = sim.filteredAction[i] * actionScaleForJoint(i) + CONFIG.defaultAngles[i];
      sim.pendingTargetDofVel[i] = 0;
    }
  }
  sim.filterPrimed = true;
  if (sim.frameLog?.length) {
    const entry = sim.frameLog[sim.frameLog.length - 1];
    if (entry && entry.action === null) {
      entry.action = Array.from(sim.action);
      entry.targetsPos = Array.from(sim.targetDofPos);
      entry.targetsVel = Array.from(sim.targetDofVel);
      entry.actuatorIds = [...sim.actuatorIds];
    }
  }
  scheduleMotorTargets();
  if (weights) sim.weights.set(weights.subarray ? weights.subarray(0, sim.weights.length) : weights);
  else sim.weights.fill(0);
  sim.estimatedVel.fill(0);
  if (estimatedVel) sim.estimatedVel.set(estimatedVel.subarray ? estimatedVel.subarray(0, sim.estimatedVel.length) : estimatedVel);
  sim.latent.fill(0);
  if (latent) sim.latent.set(latent.subarray ? latent.subarray(0, sim.latent.length) : latent);
  if (nextHistory && nextHistory.length === sim.history.length) sim.history.set(nextHistory);
  else pushHistory(sim.obs);
}

function shouldAutoplayPolicy() {
  return URL_AUTOPLAY === null ? CONFIG.autoplay : URL_AUTOPLAY;
}

function randomDelaySteps(maxSteps) {
  const limit = clamp(Math.round(Number(maxSteps) || 0), 0, SIGNAL_DELAY_MAX_STEPS);
  return Math.floor(Math.random() * (limit + 1));
}

function scheduleMotorTargets() {
  sim.motorTargetPending = true;
  input.motorDelaySampleSteps = input.motorDelayEnabled
    ? randomDelaySteps(input.motorDelayMaxSteps)
    : 0;
  sim.motorDelayRemaining = input.motorDelaySampleSteps;
  if (sim.motorDelayRemaining === 0) applyPendingMotorTargets();
}

function advanceMotorDelay() {
  if (!sim.motorTargetPending) return;
  if (sim.motorDelayRemaining > 0) {
    sim.motorDelayRemaining -= 1;
    return;
  }
  applyPendingMotorTargets();
}

function applyPendingMotorTargets() {
  if (!sim.motorTargetPending) return;
  sim.targetDofPos.set(sim.pendingTargetDofPos);
  sim.targetDofVel.set(sim.pendingTargetDofVel);
  sim.motorTargetPending = false;
}

function holdStance() {
  sim.motorTargetPending = false;
  sim.motorDelayRemaining = 0;
  input.motorDelaySampleSteps = 0;
  sim.g1PhaseS = 0; // 步态相位时钟归零
  for (let i = 0; i < CONFIG.numActions; i += 1) {
    sim.action[i] = 0;
    sim.appliedAction[i] = 0;
    sim.filteredAction[i] = 0;
    sim.targetDofPos[i] = CONFIG.defaultAngles[i];
    sim.targetDofVel[i] = 0;
    sim.pendingTargetDofPos[i] = CONFIG.defaultAngles[i];
    sim.pendingTargetDofVel[i] = 0;
  }
}

if (DEBUG_ENABLED) {
  window.__sim2simDebug = {
    state: buildDebugState,
    setPolicyEnabled(enabled) {
      const next = Boolean(enabled);
      if (next !== sim.policyEnabled) resetPolicyState();
      sim.policyEnabled = next;
    },
    setPaused(paused) {
      sim.paused = Boolean(paused);
      elements.playButton.textContent = sim.paused ? "继续" : "暂停";
    },
    reset() {
      resetSimulation();
    },
    startFrameLog() {
      sim.frameLog = [];
      // 帧口径：stepIndex = 控制步序号（reset 后从 0 起）。replay_diff.py 按此对齐桌面序列。
      return true;
    },
    stopFrameLog() {
      return sim.frameLog || [];
    },
    openLoopTest(ctrlValue, steps) {
      // Deterministic physical check: settle into the default pose, then hold
      // a constant ctrl vector and report the resulting base trajectory.
      const record = [];
      resetSimulation();
      const isArray = Array.isArray(ctrlValue);
      for (let i = 0; i < CONFIG.numActions; i += 1) {
        const actuatorId = sim.actuatorIds[i] ?? i;
        if (actuatorId >= 0 && actuatorId < sim.ctrl.length) {
          sim.ctrl[actuatorId] = isArray ? Number(ctrlValue[i]) || 0 : Number(ctrlValue) || 0;
        }
      }
      for (let step = 0; step < Number(steps) || 0; step += 1) {
        sim.mujoco.mj_step(sim.model, sim.data);
        if (step % 10 === 0) {
          record.push({ t: Number(sim.data.time.toFixed(3)), z: Number(sim.qpos[2].toFixed(4)), qvel: Array.from(sim.qvel.subarray(3, 6)).map((v) => Number(v.toFixed(4))) });
        }
      }
      record.push({ t: Number(sim.data.time.toFixed(3)), z: Number(sim.qpos[2].toFixed(4)), qvel: Array.from(sim.qvel.subarray(3, 6)).map((v) => Number(v.toFixed(4))) });
      return record;
    },
    // QA/评测采样器（?debug=1）：单帧物理与策略状态快照，供 Playwright
    // 批量验收（站立高度 / 姿态 / 指令追踪）读取，不触碰运行时行为。
    sample() {
      const q = sim.qpos;
      const imu = sim.imuSamples[sim.imuSamples.length - 1] || null;
      const round4 = (v) => Number(Number(v).toFixed(4));
      return {
        time: Number((sim.data?.time ?? 0).toFixed(3)),
        baseZ: q ? round4(q[2]) : null,
        quat: q ? Array.from(q.subarray(3, 7), round4) : null,
        bodyLinearVel: imu ? Array.from(imu.linear, round4) : null,
        bodyAngularVel: imu ? Array.from(imu.angular, round4) : null,
        cmd: Array.from(sim.cmd, round4),
        targetCmd: Array.from(sim.targetCmd, round4),
        action: Array.from(sim.action, round4),
        policyEnabled: sim.policyEnabled,
        paused: sim.paused,
      };
    },
    // 同步快进（?debug=1）：暂停渲染循环，按物理步长推进完整仿真链
    // （updateCommand → runPolicy → mj_step），用于批量验收在合理墙钟内
    // 跑够仿真时长（浏览器实时步进仅 ~0.3-0.5x，墙钟等待测不满追踪过程）。
    async fastForward(seconds) {
      const wasPaused = sim.paused;
      sim.paused = true;
      const dt = CONFIG.simulationDt || 0.005;
      const steps = Math.ceil(Number(seconds) / dt);
      for (let i = 0; i < steps; i += 1) {
        await stepSimulation();
      }
      sim.paused = wasPaused;
      return this.sample();
    },
  };
}

function captureImuSample() {
  const quaternion = sim.qpos.subarray(3, 7);
  // mjlab 语义：base_lin_vel/base_ang_vel 取自 root body 的 link 速度
  // （cvel 绕 subtree COM，须修正到 body origin，见 rootLinkVelW）。qvel 的自由关节
  // 线速度是 root body 原点速度，但角速度为体坐标系；mjswan 用 cvel 统一世界系后再投影，
  // 走行策略对参考点敏感（G1 实测：qvel 版 3 秒跌倒，cvel 版稳定行走）。
  let angular = sim.qvel.subarray(3, 6);
  let linearWorld = null;
  if (sim.model?.cvel && sim.model?.nbody > 1 && sim.data?.cvel) {
    try {
      const rootBody = 1; // 自由关节根 body（pelvis/torso）
      const cvel = sim.data.cvel;
      const base = rootBody * 6;
      const angW = [cvel[base], cvel[base + 1], cvel[base + 2]];
      const linC = [cvel[base + 3], cvel[base + 4], cvel[base + 5]];
      const pos = sim.data.xpos[rootBody];
      const com = sim.data.subtree_com[rootBody];
      const ox = com[0] - pos[0], oy = com[1] - pos[1], oz = com[2] - pos[2];
      linearWorld = [
        linC[0] - (angW[1] * oz - angW[2] * oy),
        linC[1] - (angW[2] * ox - angW[0] * oz),
        linC[2] - (angW[0] * oy - angW[1] * ox),
      ];
      // 角速度也走 cvel（世界系），与 mjswan slotReader 一致
      angular = new Float32Array(angW);
    } catch (_) { /* 回退到 qvel */ }
  }
  if (!linearWorld) linearWorld = [sim.qvel[0], sim.qvel[1], sim.qvel[2]];
  return {
    angular: new Float32Array(rotateVectorByQuatInverse(quaternion, angular)),
    linear: new Float32Array(rotateVectorByQuatInverse(quaternion, linearWorld)),
    gravity: new Float32Array(getGravityOrientation(quaternion)),
    rpy: new Float32Array(quatToRpy(quaternion)),
  };
}

// v_body = R^T · v_world
function rotateVectorByQuatInverse(quaternion, v) {
  const qw = quaternion[0], qx = quaternion[1], qy = quaternion[2], qz = quaternion[3];
  const [vx, vy, vz] = v;
  return [
    (1 - 2 * (qy * qy + qz * qz)) * vx + 2 * (qx * qy + qw * qz) * vy + 2 * (qx * qz - qw * qy) * vz,
    2 * (qx * qy - qw * qz) * vx + (1 - 2 * (qx * qx + qz * qz)) * vy + 2 * (qy * qz + qw * qx) * vz,
    2 * (qx * qz + qw * qy) * vx + 2 * (qy * qz - qw * qx) * vy + (1 - 2 * (qx * qx + qy * qy)) * vz,
  ];
}

function recordImuSample() {
  if (!sim.qpos || !sim.qvel) return;
  sim.imuSamples.push(captureImuSample());
  if (sim.imuSamples.length > IMU_SAMPLE_HISTORY_LIMIT) sim.imuSamples.shift();
}

function resetImuSamples() {
  sim.imuSamples.length = 0;
  recordImuSample();
}

function readImuSample() {
  if (!sim.imuSamples.length) recordImuSample();
  const requested = input.imuDelayEnabled ? randomDelaySteps(input.imuDelayMaxSteps) : 0;
  input.imuDelaySampleSteps = Math.min(requested, Math.max(0, sim.imuSamples.length - 1));
  return sim.imuSamples[sim.imuSamples.length - 1 - input.imuDelaySampleSteps]
    || captureImuSample();
}


function buildPolicyObs(size) {
  if (!size || size === CONFIG.numObs) return new Float32Array(sim.obs);
  const frames = Math.max(1, Math.round(size / CONFIG.numObs));
  const availableFrames = Math.floor(sim.history.length / CONFIG.numObs);
  const sourceFrames = [];
  for (let frame = 0; frame < availableFrames; frame += 1) {
    sourceFrames.push(sim.history.subarray(frame * CONFIG.numObs, (frame + 1) * CONFIG.numObs));
  }
  sourceFrames.push(sim.obs);
  const selected = sourceFrames.slice(-frames);
  // 预热填充用最新帧重复（ObservationBuffer.reset 的官方语义），零帧会让
  // 历史型策略在开局拿到断裂输入。
  while (selected.length < frames) selected.unshift(selected[0] || new Float32Array(CONFIG.numObs));
  const packed = packObsHistoryByTerm(selected);
  return size === packed.length ? packed : packed.slice(0, size);
}

function packObsHistoryByTerm(frames) {
  // frame_major_v1（LeggedSkillDeploy go1/himloco）：部署端 ObservationBuffer
  // .get_obs_vec 对 yaml 倒序表 [5,4,3,2,1,0] 做 reversed 遍历后 torch.cat ——
  // 语义 = 整帧依时序拼接且最新帧在前（[obs_t, obs_{t-1}, …, obs_{t-5}]），
  // 不做任何 term 重排。_frames 参数为 oldest→newest，故反向遍历。
  if (CONFIG.historyLayout === "frame_major_v1") {
    const packed = new Float32Array(frames.length * CONFIG.numObs);
    let cursor = 0;
    for (let i = frames.length - 1; i >= 0; i -= 1) {
      packed.set(frames[i], cursor);
      cursor += CONFIG.numObs;
    }
    return packed;
  }
  // Wuji reorient：显式分段，每段按 旧→新 逐帧拼接（段内 history 连续，term-major）。
  if (CONFIG.historyLayout === "wuji_term_major" && CONFIG.historyTerms) {
    const packed = new Float32Array(frames.length * CONFIG.numObs);
    let cursor = 0;
    for (const [rawOffset, rawLength] of CONFIG.historyTerms) {
      const offset = Number(rawOffset);
      const length = Number(rawLength);
      for (const obs of frames) {
        packed.set(obs.subarray(offset, offset + length), cursor);
        cursor += length;
      }
    }
    return packed;
  }
  // go2_rl_gym's ONNX exporter expects stacked observations grouped by term:
  // ang_vel history, gravity history, command history, q, dq, action, then
  // task-specific suffixes when the contract opts into the corrected layout.
  if (CONFIG.observationKind === "zexw_53") {
    const terms = [[0, 3], [3, 3], [6, 3], [9, 12], [21, 12], [33, 4], [37, 16]];
    const packed = new Float32Array(frames.length * CONFIG.numObs);
    let cursor = 0;
    for (const [offset, length] of terms) {
      for (const obs of frames) {
        packed.set(obs.subarray(offset, offset + length), cursor);
        cursor += length;
      }
    }
    return packed;
  }
  const layout = observationLayout();
  const terms = [
    [0, 3],
    [3, 3],
    [6, layout.commandDims],
  ];
  const extraOffset = layout.actionOffset + CONFIG.numActions;
  const extraLength = CONFIG.numObs - extraOffset;
  const actionTerms = [
    [layout.jointOffset, CONFIG.numActions],
    [layout.velocityOffset, CONFIG.numActions],
    [layout.actionOffset, CONFIG.numActions],
  ];
  if (CONFIG.historyLayout === "term_major_suffix_extra_v1") {
    terms.push(...actionTerms);
    if (extraLength > 0) terms.push([extraOffset, extraLength]);
  } else {
    if (extraLength > 0) terms.push([extraOffset, extraLength]);
    terms.push(...actionTerms);
  }
  const packed = new Float32Array(frames.length * CONFIG.numObs);
  let cursor = 0;
  for (const [offset, length] of terms) {
    for (const obs of frames) {
      packed.set(obs.subarray(offset, offset + length), cursor);
      cursor += length;
    }
  }
  return packed;
}

function pushHistory(obs) {
  // Isaac 风格元素主序交错（contract.history_interleaved）：每个观测元素的
  // 历史窗相邻 —— [a0_{t-n+1}..a0_t, a1_{t-n+1}..]，与 mjswan
  // HistoryObservation.writeInterleavedFrame 同布局；最老帧仍在窗首。
  if (CONFIG.historyInterleaved) {
    const frames = sim.history.length / CONFIG.numObs;
    for (let j = 0; j < CONFIG.numObs; j += 1) {
      const base = j * frames;
      sim.history.copyWithin(base + 1, base, base + frames - 1);
      sim.history[base] = obs[j];
    }
    return;
  }
  sim.history.copyWithin(0, CONFIG.numObs);
  sim.history.set(obs, sim.history.length - CONFIG.numObs);
}

function seedHistory(obs) {
  for (let offset = 0; offset < sim.history.length; offset += CONFIG.numObs) {
    sim.history.set(obs, offset);
  }
}

function updateCommand() {
  // 确定性回放指令源：压过键盘/摇杆/滑条（验收协议中的"固定指令"环节）。
  if (sim.deterministicReplay) {
    const cmd = sim.deterministicReplay.command;
    for (let i = 0; i < 3; i += 1) {
      const max = CONFIG.maxCmd[i];
      const value = clamp(cmd[i], -max, max);
      sim.targetCmd[i] = value;
      sim.cmd[i] = value;
    }
    syncBinaryJumpCommand();
    return;
  }
  // 感知导航（H3 command_source=planner）：planner 的 cmd_vel 压过键盘/摇杆/滑条，
  // 但**低于**确定性回放（验收协议的"固定指令"优先级最高）。
  if (sim.navigation?.runner) {
    applyNavigationCommand();
    return;
  }
  const xSpeed = clamp(input.vxSpeedLimit, 0.2, CONFIG.maxCmd[0]);
  const target = sim.targetCmd;
  const heightIndex = heightCommandIndex();
  target[0] = 0;
  target[1] = 0;
  target[2] = 0;
  target[heightIndex] = hasHeightCommand() ? activeHeightCommand() : 0;

  if (input.keys.has("KeyW") || input.keys.has("ArrowUp")) target[0] += xSpeed;
  if (input.keys.has("KeyS") || input.keys.has("ArrowDown")) target[0] -= xSpeed;
  if (input.keys.has("KeyA")) target[1] += CONFIG.maxCmd[1] * 0.55;
  if (input.keys.has("KeyD")) target[1] -= CONFIG.maxCmd[1] * 0.55;
  if (input.keys.has("KeyQ") || input.keys.has("ArrowLeft")) target[2] += CONFIG.maxCmd[2] * 0.48;
  if (input.keys.has("KeyE") || input.keys.has("ArrowRight")) target[2] -= CONFIG.maxCmd[2] * 0.48;

  if (!hasMotionKey()) {
    if (input.joystickPointer !== null) applyJoystickCommand();
    else if (input.manualCmdActive) applyManualCommand();
    else applyIdleCommand();
    syncBinaryJumpCommand();
    return;
  }

  for (let i = 0; i < 3; i += 1) {
    const max = CONFIG.maxCmd[i];
    target[i] = clamp(target[i], -max, max);
    sim.cmd[i] = target[i];
  }
  sim.targetCmd[heightIndex] = target[heightIndex];
  sim.cmd[heightIndex] = target[heightIndex];
  syncBinaryJumpCommand();
}

function zeroCommand() {
  const heightIndex = heightCommandIndex();
  sim.targetCmd[0] = 0;
  sim.targetCmd[1] = 0;
  sim.targetCmd[2] = 0;
  sim.targetCmd[heightIndex] = hasHeightCommand() ? activeHeightCommand() : 0;
  sim.cmd[0] = 0;
  sim.cmd[1] = 0;
  sim.cmd[2] = 0;
  sim.cmd[heightIndex] = sim.targetCmd[heightIndex];
}

function isJumpCommandActive() {
  return isWheelLegJumpPolicy() && sim.jumpActive;
}

function syncBinaryJumpCommand() {
  if (!isWheelLegJumpPolicy()) return;
  const value = isJumpCommandActive() ? 1 : 0;
  sim.targetCmd[3] = value;
  sim.cmd[3] = value;
}

function sampleJumpCommandDuration() {
  const [minimum, maximum] = WHEEL_LEG_JUMP_COMMAND_DURATION_S;
  return minimum + Math.random() * (maximum - minimum);
}

function triggerJumpCommand() {
  if (!isWheelLegJumpPolicy() || !sim.data) return;
  if (sim.jumpActive) return;
  const now = Number(sim.data.time || 0);
  sim.jumpPulseDuration = sampleJumpCommandDuration();
  sim.jumpStartedAt = now;
  sim.jumpPulseUntil = now + sim.jumpPulseDuration;
  sim.jumpActive = true;
  sim.jumpStartPending = true;
  syncBinaryJumpCommand();
  updateHud(true);
}

function finishJumpCommand() {
  sim.jumpActive = false;
  sim.jumpStartPending = false;
  syncBinaryJumpCommand();
  updateHud(true);
}

function activatePendingJumpCommand() {
  if (!sim.jumpActive || !sim.jumpStartPending || !sim.data) return;
  // UI events can arrive between policy ticks. Anchor phase zero to the next
  // inference boundary so the first browser observation matches training and
  // the native MuJoCo controller exactly.
  const now = Number(sim.data.time || 0);
  sim.jumpStartedAt = now;
  sim.jumpPulseUntil = now + sim.jumpPulseDuration;
  sim.jumpStartPending = false;
}

function updateJumpCommandState() {
  if (!isJumpCommandActive() || sim.jumpStartPending || !sim.data) return;
  if ((sim.counter + 1) % CONFIG.controlDecimation !== 0) return;
  const now = Number(sim.data.time || 0);
  if (now < sim.jumpPulseUntil) return;
  finishJumpCommand();
}

function applyIdleCommand() {
  // 命令唯一直连源 = 速度指令滑条（manualCmd），初始化为契约 default_command。
  // "启用"是真实开关：未勾选时命令清零（拖滑条只改数值不生效）；勾选后滑条接管。
  if (input.cruiseVx !== null) {
    applyCruiseCommand();
  } else if (input.manualCmdActive) {
    applyManualCommand();
  } else {
    zeroCommand();
  }
}

function applyCruiseCommand() {
  zeroCommand();
  const speed = clamp(input.cruiseVx, -CONFIG.maxCmd[0], CONFIG.maxCmd[0]);
  sim.targetCmd[0] = speed;
  sim.cmd[0] = speed;
}

function applyJoystickCommand() {
  zeroCommand();
  sim.cmd[0] = clamp(
    input.joystickForward * clamp(input.vxSpeedLimit, 0.2, CONFIG.maxCmd[0]),
    -CONFIG.maxCmd[0],
    CONFIG.maxCmd[0],
  );
  sim.cmd[2] = clamp(
    -input.joystickTurn * CONFIG.maxCmd[2] * 0.48,
    -CONFIG.maxCmd[2],
    CONFIG.maxCmd[2],
  );
  sim.targetCmd[0] = sim.cmd[0];
  sim.targetCmd[2] = sim.cmd[2];
}

function setCruiseSpeed(speed) {
  input.cruiseVx = clamp(finiteNumber(speed, 0), -CONFIG.maxCmd[0], CONFIG.maxCmd[0]);
  applyIdleCommand();
  updateCruiseButtons();
  if (sim.qpos && sim.qvel && sim.data) updateHud(true);
}

function updateCruiseButtons() {
  for (const button of elements.cruiseButtons) {
    const active = input.cruiseVx !== null
      && Math.abs(input.cruiseVx - Number(button.dataset.cruiseSpeed)) < 0.001;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  }
}

function applyDefaultCommand() {
  for (let i = 0; i < 3; i += 1) {
    const max = CONFIG.maxCmd[i];
    const value = clamp(CONFIG.defaultCommand[i], -max, max);
    sim.targetCmd[i] = value;
    sim.cmd[i] = value;
  }
  const heightIndex = heightCommandIndex();
  sim.targetCmd[heightIndex] = activeHeightCommand();
  sim.cmd[heightIndex] = sim.targetCmd[heightIndex];
}

function setJumpHeightCommand(value) {
  if (!hasHeightCommand()) return;
  const heightIndex = heightCommandIndex();
  const height = bucketHeightCommand(value);
  CONFIG.defaultCommand[heightIndex] = height;
  sim.targetCmd[heightIndex] = height;
  sim.cmd[heightIndex] = height;
  updateCommandLabel();
  updateHud(true);
}

function activeHeightCommand() {
  return hasHeightCommand() ? bucketHeightCommand(CONFIG.defaultCommand[heightCommandIndex()]) : 0;
}

function bucketHeightCommand(value) {
  const height = finiteNumber(value, 0.68);
  if (height < 0.46) return 0.32;
  if (height < 0.6) return 0.5;
  if (height < 0.85) return 0.68;
  return height;
}

function hasMotionKey() {
  return (
    input.keys.has("KeyW") ||
    input.keys.has("KeyS") ||
    input.keys.has("KeyA") ||
    input.keys.has("KeyD") ||
    input.keys.has("KeyQ") ||
    input.keys.has("KeyE") ||
    input.keys.has("ArrowUp") ||
    input.keys.has("ArrowDown") ||
    input.keys.has("ArrowLeft") ||
    input.keys.has("ArrowRight")
  );
}

// ── 传感器可视化模型 ────────────────────────────────────────────────────
// 每个**启用中**的传感器在场景里有个小模型，位置与朝向来自它的**装配**
// （sensor_dock.js 的 DEFAULT_MOUNTS + 用户覆盖）——「装在哪、朝哪」是**看得见**的，
// 而不是埋在配置里。形状与颜色取自 SENSOR_MODELS。
//
// 与机器人 mesh 用**同一套坐标**：three.js 那边直接用 MuJoCo 的 geom_xpos / geom_xmat
// 填 `mesh.matrix`（z 轴向上、四元数 (w,x,y,z)），所以这里也照 MuJoCo 约定算。
const sensorModelCache = new Map();

function disposeSensorModel(mesh) {
  view.scene?.remove(mesh);
  mesh.geometry?.dispose?.();
  mesh.material?.dispose?.();
}

/** 按当前**插件开关**增删模型：勾上一个传感器就多一个小方块，取消就消失。 */
function ensureSensorModels() {
  if (!view.scene || typeof THREE === "undefined") return;
  const wanted = SENSOR_PLUGINS.filter((p) => dock.plugins[p.id]).map((p) => p.id);
  for (const [id, mesh] of sensorModelCache) {
    if (!wanted.includes(id)) {
      disposeSensorModel(mesh);
      sensorModelCache.delete(id);
    }
  }
  for (const id of wanted) {
    if (sensorModelCache.has(id)) continue;
    const spec = SENSOR_MODELS[id];
    if (!spec) continue;
    let geometry;
    if (spec.kind === "sphere") {
      geometry = new THREE.SphereGeometry(spec.size[0], 10, 8);
    } else if (spec.kind === "cylinder") {
      geometry = new THREE.CylinderGeometry(spec.size[0], spec.size[0], spec.size[1] * 2, 10);
    } else {
      geometry = new THREE.BoxGeometry(spec.size[0] * 2, spec.size[1] * 2, spec.size[2] * 2);
    }
    const mesh = new THREE.Mesh(
      geometry,
      new THREE.MeshBasicMaterial({ color: spec.color, transparent: true, opacity: 0.9 }),
    );
    mesh.matrixAutoUpdate = false;
    view.scene.add(mesh);
    sensorModelCache.set(id, mesh);
  }
}

/** 每帧：世界位姿 = 机身位姿 × 装配位姿。 */
function updateSensorModels() {
  if (!sensorModelCache.size || !sim.qpos || sim.qpos.length < 7) return;
  const basePos = [sim.qpos[0], sim.qpos[1], sim.qpos[2]];
  const baseQuat = [sim.qpos[3], sim.qpos[4], sim.qpos[5], sim.qpos[6]]; // (w,x,y,z)
  sensorModelCache.forEach((mesh, id) => {
    const mount = sensorMount(id, sensorMountOverrides);
    if (!mount) return;
    const offset = quatRot(baseQuat, mount.pos);
    const pose = quatMul(baseQuat, quatFromRpy(mount.rpy.map(deg2rad)));
    const m = quatToMat(pose);
    mesh.matrix.set(
      m[0], m[1], m[2], basePos[0] + offset[0],
      m[3], m[4], m[5], basePos[1] + offset[1],
      m[6], m[7], m[8], basePos[2] + offset[2],
      0, 0, 0, 1,
    );
  });
}

function syncVisualScene() {
  if (!sim.model || !sim.data) return;
  if (view.geoms.length !== sim.model.ngeom) rebuildRenderGeoms();

  for (const renderable of view.geoms) {
    updateRenderable(renderable);
  }
  // 每帧调 ensure（幂等且只有 7 个传感器要过一遍）：这样"场景刚建好"与"用户刚勾上插件"
  // 两种情况都自然收敛，不需要额外的脏标记或初始化顺序约定。
  ensureSensorModels();
  updateSensorModels();
}

function rebuildRenderGeoms() {
  clearRenderGeoms();
  for (let geomId = 0; geomId < sim.model.ngeom; geomId += 1) {
    const info = modelGeomInfo(geomId);
    const key = geometryKey(info);
    const renderable = createRenderable(info, key);
    view.geoms.push(renderable);
    view.scene.add(renderable.mesh);
  }
  updateRenderFlags();
}

function createRenderable(info, key) {
  const type = info.type;
  const geometry = getGeometry(info, key);
  const material = makeMaterial(info);
  const mesh = new THREE.Mesh(geometry, material);
  mesh.matrixAutoUpdate = false;
  const kind = classifyGeom(info);
  mesh.castShadow = kind !== "terrain";
  mesh.receiveShadow = true;
  mesh.userData.kind = kind;
  mesh.userData.type = type;
  mesh.userData.geomId = info.objid;
  // 「视觉模型」开关按 geom 分组归属切换可见性：记录每个 mesh 对应的
  // geom group 与接触掩码（group 2 / contype=0 为视觉，group 3 等为碰撞）。
  if (info.objtype === sim.objGeom && info.objid >= 0 && sim.model) {
    mesh.userData.geomGroup = Number(sim.model.geom_group?.[info.objid] ?? 0);
    mesh.userData.contype = Number(sim.model.geom_contype?.[info.objid] ?? 0);
    mesh.userData.conaffinity = Number(sim.model.geom_conaffinity?.[info.objid] ?? 0);
  }
  mesh.userData.baseOpacity = material.opacity;
  view.materials.add(material);
  return { key, mesh, material };
}

function updateRenderable(renderable) {
  const geomId = renderable.mesh.userData.geomId;
  const matOffset = geomId * 9;
  const posOffset = geomId * 3;
  const mat = sim.data.geom_xmat;
  const pos = sim.data.geom_xpos;
  renderable.mesh.matrix.set(
    mat[matOffset],
    mat[matOffset + 1],
    mat[matOffset + 2],
    pos[posOffset],
    mat[matOffset + 3],
    mat[matOffset + 4],
    mat[matOffset + 5],
    pos[posOffset + 1],
    mat[matOffset + 6],
    mat[matOffset + 7],
    mat[matOffset + 8],
    pos[posOffset + 2],
    0,
    0,
    0,
    1,
  );
  renderable.mesh.matrixWorldNeedsUpdate = true;
}

function getGeometry(info, key) {
  const cached = view.geometryCache.get(key);
  if (cached) return cached;

  const type = info.type;
  const size = info.size;
  let geometry;

  const meshId = meshIdFromGeom(info);
  if (type === sim.geomType.mesh && meshId >= 0) {
    geometry = buildMeshGeometry(meshId);
  } else if (type === sim.geomType.box) {
    geometry = new THREE.BoxGeometry(Math.max(size[0] * 2, 0.001), Math.max(size[1] * 2, 0.001), Math.max(size[2] * 2, 0.001));
  } else if (type === sim.geomType.sphere) {
    geometry = new THREE.SphereGeometry(Math.max(size[0], 0.001), 28, 16);
  } else if (type === sim.geomType.cylinder) {
    geometry = new THREE.CylinderGeometry(Math.max(size[0], 0.001), Math.max(size[0], 0.001), Math.max(size[1] * 2, 0.001), 28, 1);
    geometry.rotateX(Math.PI / 2);
  } else if (type === sim.geomType.capsule) {
    geometry = makeCapsuleGeometry(Math.max(size[0], 0.001), Math.max(size[1], 0.001));
  } else if (type === sim.geomType.plane) {
    geometry = new THREE.PlaneGeometry(90, 90, 1, 1);
  } else if (type === sim.geomType.hfield) {
    geometry = buildHFieldGeometry(info);
  } else {
    geometry = new THREE.BoxGeometry(Math.max(size[0] * 2, 0.01), Math.max(size[1] * 2, 0.01), Math.max(size[2] * 2, 0.01));
  }

  geometry.computeBoundingSphere();
  view.geometryCache.set(key, geometry);
  return geometry;
}

function buildMeshGeometry(meshId) {
  const cacheKey = `mesh:${meshId}`;
  const cached = view.geometryCache.get(cacheKey);
  if (cached) return cached;

  const vertAdr = sim.model.mesh_vertadr[meshId];
  const vertNum = sim.model.mesh_vertnum[meshId];
  const faceAdr = sim.model.mesh_faceadr[meshId];
  const faceNum = sim.model.mesh_facenum[meshId];
  const positions = new Float32Array(vertNum * 3);
  const indices = new Uint32Array(faceNum * 3);

  for (let i = 0; i < positions.length; i += 1) {
    positions[i] = sim.model.mesh_vert[vertAdr * 3 + i];
  }
  for (let i = 0; i < indices.length; i += 1) {
    indices[i] = sim.model.mesh_face[faceAdr * 3 + i];
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setIndex(new THREE.BufferAttribute(indices, 1));
  geometry.computeVertexNormals();
  geometry.computeBoundingSphere();
  view.geometryCache.set(cacheKey, geometry);
  return geometry;
}

// 高度场网格（item 13）：按 mjModel.hfield_data 生成 PlaneGeometry 式网格。
// 参考 mjswan scene.ts 的 createHFieldGeometry；本查看器直接使用 MuJoCo 的
// Z-up 坐标系渲染（相机 up=(0,0,1)），因此无需 mjswan 的坐标轴重排。
function buildHFieldGeometry(info) {
  const hfieldId = meshIdFromGeom(info);
  const nrow = Number(sim.model?.hfield_nrow?.[hfieldId] || 0);
  const ncol = Number(sim.model?.hfield_ncol?.[hfieldId] || 0);
  if (!Number.isInteger(hfieldId) || hfieldId < 0 || nrow < 2 || ncol < 2 || !sim.model?.hfield_data) {
    return new THREE.BoxGeometry(1, 1, 0.01);
  }
  const size = sim.model.hfield_size;
  const halfSizeX = Number(size[hfieldId * 4]) || 0;
  const halfSizeY = Number(size[hfieldId * 4 + 1]) || 0;
  const elevationScale = Number(size[hfieldId * 4 + 2]) || 0;
  const baseLevel = Number(size[hfieldId * 4 + 3]) || 0;
  const address = Number(sim.model.hfield_adr[hfieldId]) || 0;
  const data = sim.model.hfield_data.subarray(address, address + nrow * ncol);

  const positions = new Float32Array(nrow * ncol * 3);
  const stepX = ncol > 1 ? (2 * halfSizeX) / (ncol - 1) : 0;
  const stepY = nrow > 1 ? (2 * halfSizeY) / (nrow - 1) : 0;

  let vertexOffset = 0;
  for (let row = 0; row < nrow; row += 1) {
    const y = stepY * row - halfSizeY;
    for (let col = 0; col < ncol; col += 1) {
      positions[vertexOffset++] = stepX * col - halfSizeX;
      positions[vertexOffset++] = y;
      positions[vertexOffset++] = baseLevel + data[row * ncol + col] * elevationScale;
    }
  }

  const indexCount = (nrow - 1) * (ncol - 1) * 6;
  const indices = indexCount > 65535 ? new Uint32Array(indexCount) : new Uint16Array(indexCount);
  let indexOffset = 0;
  for (let row = 0; row < nrow - 1; row += 1) {
    for (let col = 0; col < ncol - 1; col += 1) {
      const i0 = row * ncol + col;
      const i1 = i0 + 1;
      const i2 = i0 + ncol;
      const i3 = i2 + 1;
      indices[indexOffset++] = i0;
      indices[indexOffset++] = i1;
      indices[indexOffset++] = i3;
      indices[indexOffset++] = i0;
      indices[indexOffset++] = i3;
      indices[indexOffset++] = i2;
    }
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setIndex(new THREE.BufferAttribute(indices, 1));
  geometry.computeVertexNormals();
  return geometry;
}

function makeCapsuleGeometry(radius, halfLength) {
  const group = new THREE.Group();
  const cylinder = new THREE.CylinderGeometry(radius, radius, halfLength * 2, 24, 1);
  cylinder.rotateX(Math.PI / 2);
  const top = new THREE.SphereGeometry(radius, 24, 12);
  const bottom = new THREE.SphereGeometry(radius, 24, 12);
  top.translate(0, 0, halfLength);
  bottom.translate(0, 0, -halfLength);
  return mergeGeometries([cylinder, top, bottom]);
}

function mergeGeometries(geometries) {
  const positions = [];
  const indices = [];
  let offset = 0;
  for (const geometry of geometries) {
    const pos = geometry.getAttribute("position");
    for (let i = 0; i < pos.array.length; i += 1) positions.push(pos.array[i]);
    const idx = geometry.index?.array;
    if (idx) {
      for (let i = 0; i < idx.length; i += 1) indices.push(idx[i] + offset);
    }
    offset += pos.count;
    geometry.dispose();
  }
  const merged = new THREE.BufferGeometry();
  merged.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  merged.setIndex(indices);
  merged.computeVertexNormals();
  return merged;
}

function makeMaterial(info) {
  const rgba = info.rgba;
  const kind = classifyGeom(info);
  const color = kind === "terrain"
    ? new THREE.Color(0x5f7486)
    : new THREE.Color(rgba[0], rgba[1], rgba[2]);
  const material = new THREE.MeshStandardMaterial({
    color,
    roughness: kind === "visual" ? 0.52 : 0.84,
    metalness: kind === "visual" ? 0.18 : 0.02,
    transparent: kind === "terrain" ? false : (rgba[3] < 0.98 || kind === "collision"),
    opacity: kind === "terrain" ? 1 : rgba[3] * (kind === "collision" ? 0.28 : 1),
    side: THREE.DoubleSide,
  });
  return material;
}

function classifyGeom(info) {
  if (info.objtype === sim.objGeom && info.objid >= 0 && sim.model) {
    const group = sim.model.geom_group[info.objid];
    const body = sim.model.geom_bodyid[info.objid];
    const contype = Number(sim.model.geom_contype?.[info.objid] ?? 1);
    const conaffinity = Number(sim.model.geom_conaffinity?.[info.objid] ?? 1);
    // Imported packages do not consistently mark visual meshes as group=2.
    // A geom with no contact masks is visual regardless of its group/type.
    if (group === 2 || (contype === 0 && conaffinity === 0 && body !== 0)) return "visual";
    if (body === 0) {
      // World-body geoms are terrain only when they are ground-like: planes,
      // height fields, terrain-named geoms, or the unnamed primitive slabs the
      // bundled terrain scenes are composed of. Robot meshes and link-named
      // geoms that happen to sit on the world body must stay visual instead of
      // being repainted (and shadow-cast) as terrain.
      const name = geomName(info.objid).toLowerCase();
      if (info.type === sim.geomType.plane || info.type === sim.geomType.hfield) return "terrain";
      if (/floor|ground|terrain|wall|step|stair|slope|ramp|platform|obstacle|hfield/.test(name)) return "terrain";
      if (!name && info.type !== sim.geomType.mesh) return "terrain";
      return "visual";
    }
    return "collision";
  }
  return "visual";
}

function geomName(geomId) {
  if (!sim.model || geomId == null || geomId < 0) return "";
  try {
    if (typeof sim.model.geom === "function") return sim.model.geom(geomId)?.name || "";
  } catch (_) { /* use the C API below */ }
  try {
    return sim.mujoco.mj_id2name(sim.model, sim.objGeom, geomId) || "";
  } catch (_) {
    return "";
  }
}

function geometryKey(info) {
  const type = info.type;
  if (type === sim.geomType.mesh) return `mesh:${meshIdFromGeom(info)}`;
  if (type === sim.geomType.hfield) return `hfield:${meshIdFromGeom(info)}`;
  const size = info.size;
  return `${type}:${size[0].toFixed(5)}:${size[1].toFixed(5)}:${size[2].toFixed(5)}`;
}

function meshIdFromGeom(info) {
  if (info.objtype === sim.objGeom && info.objid >= 0 && sim.model) {
    return sim.model.geom_dataid[info.objid];
  }
  return info.dataid;
}

function modelGeomInfo(geomId) {
  return {
    objtype: sim.objGeom,
    objid: geomId,
    type: sim.model.geom_type[geomId],
    dataid: sim.model.geom_dataid[geomId],
    size: sim.model.geom_size.subarray(geomId * 3, geomId * 3 + 3),
    rgba: geomRgba(geomId),
  };
}

function geomRgba(geomId) {
  const matId = sim.model.geom_matid?.[geomId] ?? -1;
  if (matId >= 0 && sim.model.mat_rgba) {
    return sim.model.mat_rgba.subarray(matId * 4, matId * 4 + 4);
  }
  return sim.model.geom_rgba.subarray(geomId * 4, geomId * 4 + 4);
}

function updateRenderFlags() {
  // 「碰撞体」开关（合并自原「视觉模型」+「碰撞体」两个复选框，语义取原
  // 「视觉模型」不勾选分支）：不勾选（默认）= 渲染视觉 mesh（geom group 2 /
  // 无接触掩码）；勾选 = 隐藏视觉 mesh、只渲染碰撞体（group 3 及所有非视觉
  // geom），此时碰撞几何强制可见并改为不透明，保证机器人仍可辨识。只动
  // three.js 可见性/材质，不影响物理。
  const showCollision = elements.collisionToggle.checked;
  const wireframe = elements.wireToggle.checked;
  for (const renderable of view.geoms) {
    if (!renderable) continue;
    const mesh = renderable.mesh;
    const kind = mesh.userData.kind;
    mesh.visible = kind === "collision"
      ? showCollision
      : kind === "visual" ? !showCollision : true; // terrain 始终可见
    renderable.material.wireframe = wireframe;
    if (kind === "collision") {
      const baseOpacity = Number(mesh.userData.baseOpacity ?? renderable.material.opacity);
      const opaque = showCollision;
      renderable.material.opacity = opaque ? 1 : baseOpacity;
      renderable.material.transparent = opaque ? false : baseOpacity < 0.98;
    }
  }
}

function updateFollowCamera() {
  if (!elements.followToggle?.checked || !sim.data || !sim.qpos) return;
  // 平行跟踪（借鉴 mjswan viewer_config.ts 的 updateCameraFromData）：把根
  // body（自由关节 base）的世界位移 delta 同时加到轨道 target 与相机位置，
  // 视线角度与缩放保持不变。可通过页脚「跟随」开关关闭，默认开启。
  const offset = sim.baseBodyId >= 0 ? sim.baseBodyId * 3 : 0;
  const xpos = sim.data.xpos;
  const next = new THREE.Vector3(
    Number(xpos?.[offset] ?? sim.qpos[0]) || 0,
    Number(xpos?.[offset + 1] ?? sim.qpos[1]) || 0,
    Math.max(Number(xpos?.[offset + 2] ?? sim.qpos[2]) || 0, 0.35),
  );
  const previous = view.controls.target.clone();
  view.followTarget.lerp(next, 0.18);
  const delta = view.followTarget.clone().sub(previous);
  view.controls.target.copy(view.followTarget);
  view.camera.position.add(delta);
}

// ---------------------------------------------------------------------------
// 鼠标拖拽施力（item 9，借鉴 mjswan DragStateManager 思路）
// ---------------------------------------------------------------------------

const DRAG_FORCE_GAIN = 100; // offset(m) → 力(N) 的比例系数
const DRAG_FORCE_MAX = 300;  // 单轴力上限，防止把机器人弹飞

/** 注册 renderer 画布上的拖拽施力交互（capture 阶段，抢在 OrbitControls 之前）。 */
function initDragInteraction() {
  const canvas = view.renderer?.domElement;
  if (!canvas || input.drag) return;
  input.drag = {
    active: false,
    pointerId: null,
    bodyId: -1,
    ndc: new THREE.Vector2(),
    plane: new THREE.Plane(),
    raycaster: new THREE.Raycaster(),
    target: new THREE.Vector3(),
    direction: new THREE.Vector3(),
  };

  canvas.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || !sim.ready || !sim.model) return;
    const drag = input.drag;
    const bodyId = pickDynamicBodyAt(event.clientX, event.clientY);
    if (bodyId < 0) return;
    // 命中动态 body：接管指针事件，禁止 OrbitControls 在拖拽期间转动视角。
    event.stopImmediatePropagation();
    event.preventDefault();
    drag.active = true;
    drag.pointerId = event.pointerId;
    drag.bodyId = bodyId;
    updateDragNdc(event.clientX, event.clientY);
    // 拖拽平面：过抓取点、垂直于视线，拖动过程中保持抓取深度不变。
    view.camera.getWorldDirection(drag.direction);
    drag.plane.setFromNormalAndCoplanarPoint(drag.direction, bodyWorldPosition(bodyId, drag.target));
    view.controls.enabled = false;
    try { canvas.setPointerCapture(event.pointerId); } catch (_) { /* no-op */ }
  }, true);

  // move 只记录 NDC 坐标；力在物理步内（applyDragForce）按当前 NDC 计算，防抖。
  canvas.addEventListener("pointermove", (event) => {
    const drag = input.drag;
    if (!drag?.active || event.pointerId !== drag.pointerId) return;
    updateDragNdc(event.clientX, event.clientY);
  }, true);

  const release = (event) => {
    if (!input.drag?.active || event.pointerId !== input.drag.pointerId) return;
    cancelDragInteraction();
  };
  canvas.addEventListener("pointerup", release, true);
  canvas.addEventListener("pointercancel", release, true);
  window.addEventListener("blur", () => cancelDragInteraction());
}

function updateDragNdc(clientX, clientY) {
  const rect = view.renderer.domElement.getBoundingClientRect();
  const drag = input.drag;
  drag.ndc.x = ((clientX - rect.left) / Math.max(rect.width, 1)) * 2 - 1;
  drag.ndc.y = -((clientY - rect.top) / Math.max(rect.height, 1)) * 2 + 1;
}

/** raycast 拾取动态 body（有自由/关节驱动的非 world body），返回 bodyId 或 -1。 */
function pickDynamicBodyAt(clientX, clientY) {
  const drag = input.drag;
  if (!drag) return -1;
  updateDragNdc(clientX, clientY);
  view.scene.updateMatrixWorld();
  drag.raycaster.setFromCamera(drag.ndc, view.camera);
  const meshes = view.geoms.map((renderable) => renderable?.mesh).filter(Boolean);
  const hits = drag.raycaster.intersectObjects(meshes, false);
  for (const hit of hits) {
    const geomId = hit.object?.userData?.geomId;
    if (!Number.isInteger(geomId) || geomId < 0) continue;
    const bodyId = Number(sim.model.geom_bodyid?.[geomId] ?? 0);
    if (bodyId <= 0) continue;
    // 只抓可动 body：挂了关节（含自由关节）的才算动态。
    const jointCount = Number(sim.model.body_jntnum?.[bodyId] ?? 0);
    if (jointCount <= 0) continue;
    return bodyId;
  }
  return -1;
}

function bodyWorldPosition(bodyId, target) {
  const offset = bodyId * 3;
  const xpos = sim.data?.xpos;
  return target.set(
    Number(xpos?.[offset] || 0),
    Number(xpos?.[offset + 1] || 0),
    Number(xpos?.[offset + 2] || 0),
  );
}

/** 物理步内调用：把当前拖拽 NDC 换算为目标点并写入 xfrc_applied（力 + 零力矩）。 */
function applyDragForce() {
  const drag = input.drag;
  if (!drag?.active || drag.bodyId < 0 || !sim.data?.xfrc_applied) return;
  drag.raycaster.setFromCamera(drag.ndc, view.camera);
  if (!drag.raycaster.ray.intersectPlane(drag.plane, drag.target)) return;
  const positionOffset = drag.bodyId * 3;
  const xpos = sim.data.xpos;
  const fx = clamp((drag.target.x - Number(xpos?.[positionOffset] || 0)) * DRAG_FORCE_GAIN, -DRAG_FORCE_MAX, DRAG_FORCE_MAX);
  const fy = clamp((drag.target.y - Number(xpos?.[positionOffset + 1] || 0)) * DRAG_FORCE_GAIN, -DRAG_FORCE_MAX, DRAG_FORCE_MAX);
  const fz = clamp((drag.target.z - Number(xpos?.[positionOffset + 2] || 0)) * DRAG_FORCE_GAIN, -DRAG_FORCE_MAX, DRAG_FORCE_MAX);
  const forceOffset = drag.bodyId * 6;
  sim.data.xfrc_applied[forceOffset] = fx;
  sim.data.xfrc_applied[forceOffset + 1] = fy;
  sim.data.xfrc_applied[forceOffset + 2] = fz;
  sim.data.xfrc_applied[forceOffset + 3] = 0;
  sim.data.xfrc_applied[forceOffset + 4] = 0;
  sim.data.xfrc_applied[forceOffset + 5] = 0;
}

/** 松开/重置/换场景时清零施力并恢复轨道控制。 */
function cancelDragInteraction() {
  const drag = input.drag;
  if (drag?.bodyId >= 0 && sim.data?.xfrc_applied) {
    const forceOffset = drag.bodyId * 6;
    for (let i = 0; i < 6; i += 1) sim.data.xfrc_applied[forceOffset + i] = 0;
  }
  if (drag) {
    drag.active = false;
    drag.pointerId = null;
    drag.bodyId = -1;
  }
  if (view.controls) view.controls.enabled = true;
  if (view.dragArrow) view.dragArrow.visible = false;
}

/** 每帧更新拖拽力箭头（three ArrowHelper），方向/长度跟随当前施力。 */
function updateDragArrow() {
  const drag = input.drag;
  const arrow = view.dragArrow;
  if (!arrow) return;
  if (!drag?.active || drag.bodyId < 0 || !sim.data?.xfrc_applied) {
    arrow.visible = false;
    return;
  }
  const forceOffset = drag.bodyId * 6;
  const fx = Number(sim.data.xfrc_applied[forceOffset] || 0);
  const fy = Number(sim.data.xfrc_applied[forceOffset + 1] || 0);
  const fz = Number(sim.data.xfrc_applied[forceOffset + 2] || 0);
  const magnitude = Math.hypot(fx, fy, fz);
  if (magnitude < 0.5) {
    arrow.visible = false;
    return;
  }
  bodyWorldPosition(drag.bodyId, arrow.position);
  arrow.setDirection(drag.direction.set(fx / magnitude, fy / magnitude, fz / magnitude));
  arrow.setLength(clamp(magnitude / DRAG_FORCE_GAIN, 0.15, 1.5), 0.16, 0.09);
  arrow.visible = true;
}

function ensureDragArrow() {
  if (view.dragArrow) return view.dragArrow;
  view.dragArrow = new THREE.ArrowHelper(
    new THREE.Vector3(0, 0, 1),
    new THREE.Vector3(),
    0.6,
    0xe05a3a,
    0.16,
    0.09,
  );
  view.dragArrow.visible = false;
  view.scene.add(view.dragArrow);
  return view.dragArrow;
}

// ---------------------------------------------------------------------------
// 根轨迹拖尾（item 12，简化版幽灵）
// ---------------------------------------------------------------------------

const TRAIL_SAMPLE_INTERVAL_S = 0.2;
const TRAIL_MAX_POINTS = 200;
const TRAIL_COLOR_FROM = new THREE.Color(0xb9c8d4); // 旧点：趋近背景
const TRAIL_COLOR_TO = new THREE.Color(0x1f7ae0);   // 新点：青蓝色

function ensureTrail() {
  if (view.trail) return view.trail;
  const positions = new Float32Array(TRAIL_MAX_POINTS * 3);
  const colors = new Float32Array(TRAIL_MAX_POINTS * 3);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  geometry.setDrawRange(0, 0);
  const line = new THREE.Line(
    geometry,
    new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.85 }),
  );
  line.frustumCulled = false;
  line.visible = false;
  view.scene.add(line);
  view.trail = { line, geometry, positions, colors, count: 0, lastTime: -Infinity };
  return view.trail;
}

function updateTrail() {
  const enabled = Boolean(elements.trailToggle?.checked);
  const trail = ensureTrail();
  trail.line.visible = enabled && trail.count >= 2;
  if (!enabled || !sim.data) return;
  const now = Number(sim.data.time || 0);
  if (trail.count && now - trail.lastTime < TRAIL_SAMPLE_INTERVAL_S) return;
  const positionOffset = sim.baseBodyId >= 0 ? sim.baseBodyId * 3 : 0;
  const xpos = sim.data.xpos;
  const x = Number(xpos?.[positionOffset] || 0);
  const y = Number(xpos?.[positionOffset + 1] || 0);
  const z = Number(xpos?.[positionOffset + 2] || 0);
  if (trail.count >= TRAIL_MAX_POINTS) {
    trail.positions.copyWithin(0, 3);
    trail.colors.copyWithin(0, 3);
    trail.count = TRAIL_MAX_POINTS - 1;
  }
  const vertex = trail.count * 3;
  trail.positions[vertex] = x;
  trail.positions[vertex + 1] = y;
  trail.positions[vertex + 2] = z;
  trail.count += 1;
  // 渐隐配色：头（旧）→ 背景，尾（新）→ 青蓝。
  for (let i = 0; i < trail.count; i += 1) {
    const t = trail.count <= 1 ? 1 : i / (trail.count - 1);
    const base = i * 3;
    trail.colors[base] = TRAIL_COLOR_FROM.r + (TRAIL_COLOR_TO.r - TRAIL_COLOR_FROM.r) * t;
    trail.colors[base + 1] = TRAIL_COLOR_FROM.g + (TRAIL_COLOR_TO.g - TRAIL_COLOR_FROM.g) * t;
    trail.colors[base + 2] = TRAIL_COLOR_FROM.b + (TRAIL_COLOR_TO.b - TRAIL_COLOR_FROM.b) * t;
  }
  trail.geometry.setDrawRange(0, trail.count);
  trail.geometry.attributes.position.needsUpdate = true;
  trail.geometry.attributes.color.needsUpdate = true;
  trail.lastTime = now;
}

function resetTrail() {
  if (!view.trail) return;
  view.trail.count = 0;
  view.trail.lastTime = -Infinity;
  view.trail.geometry.setDrawRange(0, 0);
  view.trail.line.visible = false;
}

// ---------------------------------------------------------------------------
// 速度命令滑条直连策略（item 10）
// ---------------------------------------------------------------------------

function normalizeCommandRanges(value) {
  if (!Array.isArray(value) || !value.length) return null;
  let pairs = value;
  // 兼容扁平布局 [min0, max0, min1, max1, ...]
  if (value.every((item) => typeof item === "number")) {
    pairs = [];
    for (let i = 0; i + 1 < value.length; i += 2) pairs.push([value[i], value[i + 1]]);
  }
  const normalized = pairs
    .map((pair) => (Array.isArray(pair)
      && pair.length >= 2
      && Number.isFinite(Number(pair[0]))
      && Number.isFinite(Number(pair[1]))
      ? [Number(pair[0]), Number(pair[1])]
      : null))
    .filter(Boolean);
  return normalized.length ? normalized : null;
}

/** 前三个命令轴（vx/vy/ωz）的有效范围；契约缺省时回落到 CONFIG.maxCmd。 */
function velocityCommandRanges() {
  const ranges = CONFIG.commandRanges;
  const result = [];
  for (let i = 0; i < 3; i += 1) {
    const pair = Array.isArray(ranges?.[i])
      && ranges[i].length === 2
      && ranges[i].every((value) => Number.isFinite(Number(value)))
      ? [Number(ranges[i][0]), Number(ranges[i][1])]
      : [-CONFIG.maxCmd[i], CONFIG.maxCmd[i]];
    result.push([Math.min(pair[0], pair[1]), Math.max(pair[0], pair[1])]);
  }
  return result;
}

function velocityCommandSliders() {
  return [
    [elements.velCmdVx, elements.velCmdVxVal],
    [elements.velCmdVy, elements.velCmdVyVal],
    [elements.velCmdYaw, elements.velCmdYawVal],
  ];
}

/** 每轴命令滑条的当前上限（mjlab play 的 "Max xxx" 语义），Max 滑条未就绪时用默认值。 */
function velocityCommandMax(index) {
  const maxEl = [elements.velCmdVxMax, elements.velCmdVyMax, elements.velCmdYawMax][index];
  if (maxEl && Number.isFinite(Number(maxEl.value)) && maxEl.value !== "") return Number(maxEl.value);
  return velocityCommandMaxDefault(index);
}

/** Max 滑条初始值：一律 1.0；vy 若契约范围上下限均为 0（无横移能力）则保持 0.5。 */
function velocityCommandMaxDefault(index) {
  if (index === 1) {
    const [dMin, dMax] = velocityCommandRanges()[index];
    if (dMin === 0 && dMax === 0) return 0.5;
  }
  return 1.0;
}

/** contract.command_dims ≥ 3 时显示 vx/vy/ωz 滑条并同步范围与默认值（mjlab play 语义）。 */
function updateVelocityCommandControls() {
  const control = elements.velocityCommandControl;
  if (!control) return;
  // 无命令观测的策略（如 g1_mjswan_balance）不显示；模仿 / 特技 / 跑酷任务
  // 由任务子面板接管（时间轴 / 触发按钮），不与速度指令滑条混排。
  const taskDriven = ["imitation", "acrobatics", "parkour"].includes(CONFIG.taskType);
  const available = CONFIG.commandDims >= 3
    && CONFIG.observationKind !== "g1_mjswan_balance"
    && !taskDriven;
  control.hidden = !available;
  if (!available) return;
  const sliders = velocityCommandSliders();
  const maxEls = [elements.velCmdVxMax, elements.velCmdVyMax, elements.velCmdYawMax];
  const maxOuts = [elements.velCmdVxMaxVal, elements.velCmdVyMaxVal, elements.velCmdYawMaxVal];
  for (let i = 0; i < 3; i += 1) {
    const [slider, output] = sliders[i];
    if (!slider) continue;
    // Max 滑条：初始一律 1.0（vy 契约范围为 0 时 0.5），用户此后可调 0.1~10
    const maxEl = maxEls[i];
    // 每次策略/机器人切换都重置为默认 Max（1.0），不继承上一策略的旧值（曾出现残留 5.1）。
    if (maxEl) maxEl.value = String(velocityCommandMaxDefault(i));
    if (maxOuts[i]) maxOuts[i].textContent = Number(maxEl?.value || 0).toFixed(1);
    const max = velocityCommandMax(i);
    slider.min = String(-max);
    slider.max = String(max);
    slider.step = "0.05";
    const value = clamp(Number(input.manualCmd[i]) || 0, -max, max);
    slider.value = String(value);
    if (output) output.textContent = formatSigned(value);
  }
}

/** 速度指令值带符号显示（+0.50 / -0.30 / 0.00）。 */

function setVelocityCommandValue(index, value) {
  const max = velocityCommandMax(index);
  const clamped = clamp(Number(value) || 0, -max, max);
  input.manualCmd[index] = clamped;
  const sliders = velocityCommandSliders();
  if (sliders[index][0]) sliders[index][0].value = String(clamped);
  if (sliders[index][1]) sliders[index][1].textContent = formatSigned(clamped);
}

function bindVelocityCommandControls() {
  velocityCommandSliders().forEach(([slider], index) => {
    slider?.addEventListener("input", () => {
      setVelocityCommandValue(index, slider.value);
      // 启用是真实开关：只有勾选时滑条命令才接管；未勾选只更新数值，不改变指令生效状态。
      input.velocityCmdTouched = true;
      input.manualCmdActive = Boolean(elements.velCmdEnable?.checked);
    });
  });
  // mjlab play 的 "Max xxx" 语义：改 Max 即把该轴命令滑条对称重设为 ±Max。
  const maxSliders = [
    [elements.velCmdVxMax, elements.velCmdVxMaxVal, 0],
    [elements.velCmdVyMax, elements.velCmdVyMaxVal, 1],
    [elements.velCmdYawMax, elements.velCmdYawMaxVal, 2],
  ];
  for (const [maxEl, maxOut, axis] of maxSliders) {
    maxEl?.addEventListener("input", () => {
      const max = Math.max(0.1, Number(maxEl.value) || 0.1);
      if (maxOut) maxOut.textContent = max.toFixed(1);
      const [slider, output] = velocityCommandSliders()[axis];
      if (slider) {
        slider.min = String(-max);
        slider.max = String(max);
        const clamped = clamp(Number(input.manualCmd[axis]) || 0, -max, max);
        slider.value = String(clamped);
        input.manualCmd[axis] = clamped;
        if (output) output.textContent = formatSigned(clamped);
      }
    });
  }
  // Enable 勾选 = 滑条命令接管（未启用时保持零指令，键盘/摇杆仍优先）。
  elements.velCmdEnable?.addEventListener("change", () => {
    input.manualCmdActive = elements.velCmdEnable.checked;
    if (elements.velCmdEnable.checked) updateVelocityCommandControls();
  });
  elements.velCmdZero?.addEventListener("click", () => {
    input.manualCmd.fill(0);
    // 归零只清数值；生效状态完全跟随"启用"勾选（勾选时归零后保持零指令接管）。
    input.velocityCmdTouched = true;
    input.manualCmdActive = Boolean(elements.velCmdEnable?.checked);
    updateVelocityCommandControls();
  });
}

/** 把策略契约的 default_command 写入滑条初始值（仅用户未显式设置时）。 */
function applyVelocityCommandDefaults() {
  // 活跃轮询会周期性重放契约；用户已经触碰滑条/归零后不得被默认值覆盖。
  if (input.velocityCmdTouched) return;
  for (let i = 0; i < 3; i += 1) {
    if (Number.isFinite(CONFIG.defaultCommand[i])) input.manualCmd[i] = CONFIG.defaultCommand[i];
  }
}

/** 手动滑条命令：无按键/摇杆时作为 idle 目标直写 sim.cmd。 */
function applyManualCommand() {
  zeroCommand();
  for (let i = 0; i < 3; i += 1) {
    const value = clamp(Number(input.manualCmd[i]) || 0, -CONFIG.maxCmd[i], CONFIG.maxCmd[i]);
    sim.targetCmd[i] = value;
    sim.cmd[i] = value;
  }
}

function updateHud(force) {
  const now = performance.now();
  if (!force && now - (view.lastHudUpdate || 0) < 80) return;
  view.lastHudUpdate = now;

  const localVel = quatRotateInverse(sim.qpos.subarray(3, 7), sim.qvel.subarray(0, 3));
  const localAngVel = sim.qvel.subarray(3, 6);
  elements.cmdVx.textContent = sim.cmd[0].toFixed(2);
  elements.cmdVy.textContent = sim.cmd[1].toFixed(2);
  elements.cmdYaw.textContent = sim.cmd[2].toFixed(2);
  if (elements.cmdJump) elements.cmdJump.textContent = isWheelLegJumpPolicy()
    ? (isJumpCommandActive() ? "ON" : "OFF")
    : (hasHeightCommand() ? sim.cmd[heightCommandIndex()].toFixed(2) : "-");
  updateJumpControls();
  OBSERVATION.updateGaitControl();
  elements.velVx.textContent = localVel[0].toFixed(2);
  elements.velVy.textContent = localVel[1].toFixed(2);
  elements.velYaw.textContent = localAngVel[2].toFixed(2);
  elements.baseHeight.textContent = sim.qpos[2].toFixed(2);
  elements.contacts.textContent = String(sim.data.ncon || 0);
  // 模仿任务：参考轨迹时间轴（任务面板顶部子面板）。
  if (CONFIG.taskType === "imitation" && sim.motionLoader?.duration) {
    const motionTime = Number(OBSERVATION.getMotionTime?.() || 0);
    const progress = document.getElementById("mimicProgressBar");
    const timeOut = document.getElementById("mimicTime");
    if (progress) progress.style.width = `${clamp((motionTime / sim.motionLoader.duration) * 100, 0, 100).toFixed(1)}%`;
    if (timeOut) timeOut.textContent = `${motionTime.toFixed(2)}s`;
  }
  if (elements.rollBar && elements.pitchBar) {
    const quaternion = sim.qpos.subarray(3, 7);
    const roll = Math.atan2(2 * (quaternion[0] * quaternion[1] + quaternion[2] * quaternion[3]), 1 - 2 * (quaternion[1] ** 2 + quaternion[2] ** 2));
    const pitch = Math.asin(clamp(2 * (quaternion[0] * quaternion[2] - quaternion[3] * quaternion[1]), -1, 1));
    const degrees = 45;
    const rollPct = clamp((roll * 180) / Math.PI / degrees, -1, 1) * 50;
    const pitchPct = clamp((pitch * 180) / Math.PI / degrees, -1, 1) * 50;
    elements.rollBar.style.width = `${Math.abs(rollPct)}%`;
    elements.rollBar.style.left = `${50 + Math.min(0, rollPct)}%`;
    elements.pitchBar.style.width = `${Math.abs(pitchPct)}%`;
    elements.pitchBar.style.left = `${50 + Math.min(0, pitchPct)}%`;
    if (elements.rollVal) elements.rollVal.textContent = `${((roll * 180) / Math.PI).toFixed(1)}°`;
    if (elements.pitchVal) elements.pitchVal.textContent = `${((pitch * 180) / Math.PI).toFixed(1)}°`;
  }
  elements.simClock.textContent = `时间 ${sim.data.time.toFixed(2)}`;
  updateSensorPanels();
  updateExpertBars();
  publishDebugState();
}

// ---------------------------------------------------------------------------
// 观测面板：**单一悬浮窗、来源可切**（来源清单见 sensor_dock.js::DOCK_SOURCES）
// ---------------------------------------------------------------------------

/** 懒取悬浮窗 canvas 的 2D ctx（dock 可被分层隐藏，取不到就安静跳过）。 */
let dockCtxCache = null;
function dockCanvasCtx() {
  if (dockCtxCache) return dockCtxCache;
  if (!dockCanvasEl || typeof dockCanvasEl.getContext !== "function") return null;
  dockCtxCache = dockCanvasEl.getContext("2d");
  return dockCtxCache;
}

/** 机身偏航（与 updateHud 的 roll/pitch 用同一套四元数，避免两处各算一套）。 */
function baseYaw() {
  const q = sim.qpos.subarray(3, 7);
  return Math.atan2(2 * (q[0] * q[3] + q[1] * q[2]), 1 - 2 * (q[2] ** 2 + q[3] ** 2));
}

/** 按来源把 canvas 调到对应**像素尺寸**。
 *
 *  `putImageData` 不缩放，尺寸必须精确对上；改 `width`/`height` 会清空画布内容但
 * **ctx 对象不变**，所以 `dockCtxCache` 依然有效。 */
function sizeDockCanvas(width, height) {
  if (!dockCanvasEl) return false;
  if (dockCanvasEl.width !== width || dockCanvasEl.height !== height) {
    dockCanvasEl.width = width;
    dockCanvasEl.height = height;
  }
  return true;
}

/** 高度扫描：机周网格**起点**、射线都朝下，命中处换算出世界系高度。
 *
 *  **变的是起点不是方向**（与 LiDAR 的扇扫正好相反，见 `raycast.js::gridOffsets`）。
 *  返回行优先的一维数组，未命中的格子给 `null`（绘制时会画成空槽）。 */
function scanHeightField(basePos, baseQuat, mount) {
  const spec = SCAN_SPECS.height;
  const { offsets, side } = gridOffsets(spec.side, spec.extent);
  const mountQuat = quatFromRpy(mount.rpy.map(deg2rad));
  const [down] = mountRayDirections(baseQuat, mountQuat, [[0, 0, -1]]);
  const anchor = mountOriginWorld(basePos, baseQuat, mount.pos);
  // 网格偏移是**机体系**的，必须跟着机身转 —— 否则机器人一转身，扫描格子还朝着原来的方向。
  const origins = offsets.map(([ox, oy]) => {
    const shift = quatRot(baseQuat, [ox, oy, 0]);
    return [anchor[0] + shift[0], anchor[1] + shift[1], anchor[2] + shift[2]];
  });
  const distances = intersectSceneRays(
    sim.model, sim.data, origins, origins.map(() => down), { maxDist: spec.maxDist },
  );
  // 高度 = 起点 z + 方向 z × 距离。**不能直接取起点 z**：装配角一旦不是正朝下，
  // 那样算出来整个场都是等高，斜面扫描就成了一张纯色图。
  const field = distances.map((d, i) => (d < 0 ? null : origins[i][2] + down[2] * d));
  return { field, side, hits: distances.filter((d) => d >= 0).length, total: distances.length };
}

/** LiDAR：同一原点的整圈扇扫。命中点留给点云复用 —— **两图同源才对得齐**。 */
function scanLidar(basePos, baseQuat, mount) {
  const spec = SCAN_SPECS.lidar;
  const { dirs, angles, count } = fanDirections(spec.count);
  const mountQuat = quatFromRpy(mount.rpy.map(deg2rad));
  const origin = mountOriginWorld(basePos, baseQuat, mount.pos);
  const worldDirs = mountRayDirections(baseQuat, mountQuat, dirs);
  const distances = intersectSceneRays(
    sim.model, sim.data, worldDirs.map(() => origin), worldDirs, { maxDist: spec.maxDist },
  );
  return { angles, distances, worldDirs, origin, count, maxDist: spec.maxDist };
}

let rgbPreview = null;

/** 懒建 RGB 预览的离屏渲染器：**只有真的选到 RGB 才建**，不选就不花这份开销。 */
function rgbPreviewRenderer() {
  if (rgbPreview) return rgbPreview;
  if (typeof THREE === "undefined" || !view.scene) return null;
  const spec = SCAN_SPECS.rgb;
  const renderer = new THREE.WebGLRenderer({
    antialias: false,
    // 渲染完要把它的画布 drawImage 到 2D canvas：不保留缓冲的话读到的可能已经是空的。
    preserveDrawingBuffer: true,
  });
  renderer.setPixelRatio(1); // 预览只有 160×120，不跟设备像素比走（否则白花 4 倍像素）
  renderer.setSize(spec.width, spec.height, false);
  renderer.setClearColor(0x0b1220, 1);
  rgbPreview = {
    renderer,
    canvas: renderer.domElement,
    camera: new THREE.PerspectiveCamera(spec.fov, spec.width / spec.height, spec.near, spec.far),
  };
  return rgbPreview;
}

/**
 * 渲染 RGB 预览：**three.js 相机 + 离屏 renderer**，不是 MuJoCo 原生渲染
 * （`mjv_*` 这一套不在 WASM 导出里）。代价是光照与原生渲染有差异，好处是零服务端往返。
 *
 * **near 平面刻意取 0.12 m**：相机装在机身内部（机身半长约 0.35 m、装配 x=0.27），
 * 不裁掉的话整个视野就是一块机身外壳。真机上前置相机也会被取景框挡住近处的自身。
 */
function renderRgbPreview(basePos, baseQuat, mount, ctx, width, height) {
  const preview = rgbPreviewRenderer();
  if (!preview || !view.scene || !ctx || typeof ctx.drawImage !== "function") return false;
  const poseQuat = quatMul(baseQuat, quatFromRpy(mount.rpy.map(deg2rad)));
  const origin = mountOriginWorld(basePos, baseQuat, mount.pos);
  preview.camera.position.set(origin[0], origin[1], origin[2]);
  // MuJoCo 与 three.js 的相机约定**恰好一致**（都沿自身 −z 看、+y 为上），姿态可以直搬，
  // 只差四元数分量顺序：MuJoCo 是 (w,x,y,z)，three 是 (x,y,z,w)。
  preview.camera.quaternion.set(poseQuat[1], poseQuat[2], poseQuat[3], poseQuat[0]);
  preview.camera.updateMatrixWorld(true);
  preview.renderer.render(view.scene, preview.camera);
  ctx.drawImage(preview.canvas, 0, 0, width, height);
  return true;
}

/** 传感器视图渲染：**只画当前来源**（不是并排三块）。
 *
 *  基础仿真整段跳过 —— 它是「本体 + 本体感知」验证，页面上只留 3D 视口与运行 HUD。
 *  各来源的**采数据与绘制一一对应**（③~⑧），读数表最后统一渲染（⑨）——
 *  这样"图上写着 24² 而数里写 16²"就不可能发生（那是两处各算一份数据的结果）。 */
function updateSensorPanels() {
  if (!sim.qpos) return;
  if (!dock.visible || !dock.source) return;

  const q = sim.qpos;
  const rpy = quatToRpy(q.subarray(3, 7));
  const pose = { x: q[0], y: q[1], z: q[2], roll: rpy[0], pitch: rpy[1], yaw: rpy[2] };
  const angular = sim.qvel && sim.qvel.length >= 6 ? Array.from(sim.qvel.subarray(3, 6)) : null;
  const velBody = sim.qvel && sim.qvel.length >= 3 ? Array.from(sim.qvel.subarray(0, 3)) : null;
  const basePos = [q[0], q[1], q[2]];
  const baseQuat = [q[3], q[4], q[5], q[6]]; // (w,x,y,z)
  const fmtVec = (arr, digits = 3) => arr.map((v) => Number(v).toFixed(digits)).join(" / ");

  // ① **全局里程计**：累计里程是它的实质 —— 按世界系位移逐帧累加。
  //    复位（切策略 / 换场景）会让位姿跳变，跳变不计入（阈值 1 m，远超单帧位移）。
  if (dock.plugins.odom) {
    if (!Number.isFinite(sim.odomMileage)) sim.odomMileage = 0;
    if (Array.isArray(sim.odomLastPos)) {
      const dist = Math.hypot(pose.x - sim.odomLastPos[0], pose.y - sim.odomLastPos[1]);
      if (dist < 1) sim.odomMileage += dist;
    }
    sim.odomLastPos = [pose.x, pose.y];
  }

  const readout = odomReadout({ pose, angular, velBody, mileage: sim.odomMileage });
  // 读数表的值在**下面各来源分支里补齐**，最后统一渲染（见 ⑨）：
  // "图上写着 24² 而数里写 16²"就是两处各算一份数据算出来的。
  const extra = { baseHeight: Number.isFinite(pose.z) ? pose.z.toFixed(3) : "—" };
  let note = "";

  // ② 画布准备：每个分支各自 `sizeDockCanvas` —— 各来源像素尺寸不同
  //    （深度帧跟随策略、高度场 = 网格边长、极坐标/点云/RGB = 固定预览），
  //    且 `putImageData` 不缩放，尺寸必须精确对上。
  const canvasSources = ["depth", "height", "trail", "lidar", "cloud", "rgb"];
  if (dockCanvasEl) dockCanvasEl.hidden = !canvasSources.includes(dock.source);
  const ctx = dockCanvasCtx();
  const scanReady = Boolean(sim.model && sim.data);

  // ③ 单点测距：从装配点沿装配方向打**一条**射线，给出到最近障碍的距离。
  //    用的是与深度 / 高度 / LiDAR 同一套几何（raycast.js），不是另算一遍。
  if (dock.source === "rangefinder") {
    const mount = sensorMount("rangefinder", sensorMountOverrides);
    if (scanReady) {
      // 朝向 = 机身姿态 × 装配姿态；方向取局部 −z（与 MuJoCo 相机约定一致）。
      const dirQuat = quatMul(baseQuat, quatFromRpy(mount.rpy.map(deg2rad)));
      const origin = mountOriginWorld(basePos, baseQuat, mount.pos);
      const dir = quatRot(dirQuat, [0, 0, -1]);
      // 量程与深度相机的 3 m 不同：测距模块问的是"远一点的地方有没有东西"。
      const RANGE_MAX = 20;
      const hit = intersectSceneRay(sim.model, sim.data, origin, dir, { maxDist: RANGE_MAX });
      const reading = rangefinderReadout({ distance: hit, maxDist: RANGE_MAX });
      extra.distance = reading.distance;
      note = reading.note;
    } else {
      extra.distance = "—";
      note = "场景几何未就绪";
    }
    extra.mountPos = fmtVec(mount.pos);
    extra.mountRpy = fmtVec(mount.rpy, 0);
  }

  // ④ 深度相机（外部感知）：帧本来就在算（pie_depth.js），此前只喂策略、没人画
  if (dock.source === "depth") {
    const shape = sim.pieDepth && sim.pieDepth.frameShape;
    const frames = sim.depthHistory;
    if (shape && frames && frames.length) {
      sizeDockCanvas(shape[2], shape[1]);
      const drawn = ctx && drawDepthFrame(ctx, frames[frames.length - 1], shape[1], shape[2]);
      note = drawn ? `${shape[1]}×${shape[2]} 近亮远暗` : "绘制失败";
    } else {
      note = "当前策略无深度输入";
    }
  }

  // ⑤ 高度扫描：机周网格**起点**、射线朝下 → 俯视高度场（低蓝高黄，没打中是黑槽）
  if (dock.source === "height") {
    const mount = sensorMount("height", sensorMountOverrides);
    const span = SCAN_SPECS.height.extent * 2;
    if (scanReady) {
      const scan = scanHeightField(basePos, baseQuat, mount);
      sizeDockCanvas(scan.side, scan.side);
      const drawn = ctx && drawHeightField(ctx, scan.field, scan.side);
      note = drawn
        ? `${span.toFixed(0)} m × ${span.toFixed(0)} m · 命中 ${scan.hits}/${scan.total}`
        : "绘制失败";
      extra.scanExtent = `${span.toFixed(0)} m × ${span.toFixed(0)} m`;
      extra.scanGrid = `${scan.side} × ${scan.side}`;
      extra.hitRatio = `${scan.hits} / ${scan.total}`;
    } else {
      note = "场景几何未就绪";
    }
    extra.mountPos = fmtVec(mount.pos);
  }

  // ⑥ 2D 轨迹平面：复用 3D 场景里的根轨迹顶点（world x/y），不另记一份
  if (dock.source === "trail") {
    sizeDockCanvas(240, 150);
    const trail = view.trail;
    const points = [];
    if (trail && trail.count >= 2) {
      for (let i = 0; i < trail.count; i += 1) {
        points.push([trail.positions[i * 3], trail.positions[i * 3 + 1]]);
      }
    }
    if (ctx && points.length >= 2) {
      drawTrail(ctx, { trail: points, pose, width: 240, height: 150 });
      note = `${points.length} 点 · x,y 等比`;
    } else {
      note = "开启「轨迹」后显示";
    }
  }

  // ⑦ LiDAR / 点云：**共用同一次扫描**。分开扫的话"点云比极坐标图多出几个点"永远查不完
  //    —— 那本来就是同一次测量的两种画法。
  if (dock.source === "lidar" || dock.source === "cloud") {
    const mount = sensorMount("lidar", sensorMountOverrides);
    if (scanReady) {
      const scan = scanLidar(basePos, baseQuat, mount);
      const hits = scan.distances
        .map((d, i) => rayHitPoint(scan.origin, scan.worldDirs[i], d))
        .filter(Boolean);
      if (dock.source === "lidar") {
        sizeDockCanvas(240, 240);
        const drawn = ctx && drawPolarScan(ctx, {
          angles: scan.angles, distances: scan.distances, maxDist: scan.maxDist, width: 240, height: 240,
        });
        const reached = scan.distances.filter((d) => d >= 0);
        note = drawn ? `命中 ${hits.length}/${scan.count} · 量程 ${scan.maxDist} m` : "无回波";
        extra.fanSpec = `360° / ${scan.count} 线`;
        extra.hitRatio = `${hits.length} / ${scan.count}`;
        extra.nearest = reached.length ? `${Math.min(...reached).toFixed(3)} m` : "无回波";
        extra.mountRpy = fmtVec(mount.rpy, 0);
      } else {
        sizeDockCanvas(240, 240);
        const drawn = ctx && drawPointCloud(ctx, { points: hits, pose, width: 240, height: 240 });
        const xs = hits.map((p) => p[0]);
        const ys = hits.map((p) => p[1]);
        note = drawn ? `${hits.length} 点 · 俯视 x-y` : "无回波";
        extra.pointCount = String(hits.length);
        extra.cloudBounds = hits.length
          ? `${(Math.max(...xs) - Math.min(...xs)).toFixed(2)} × ${(Math.max(...ys) - Math.min(...ys)).toFixed(2)}`
          : "—";
        extra.cloudSource = "LiDAR 同一次扫描";
        extra.mountPos = fmtVec(mount.pos);
      }
    } else {
      note = "场景几何未就绪";
      if (dock.source === "lidar") extra.mountRpy = fmtVec(mount.rpy, 0);
      else extra.mountPos = fmtVec(mount.pos);
    }
  }

  // ⑧ RGB 相机：three.js 离屏渲染（near 为什么是 0.12 见 renderRgbPreview 的说明）
  if (dock.source === "rgb") {
    const mount = sensorMount("rgb", sensorMountOverrides);
    const spec = SCAN_SPECS.rgb;
    sizeDockCanvas(spec.width, spec.height);
    const drawn = renderRgbPreview(basePos, baseQuat, mount, ctx, spec.width, spec.height);
    note = drawn ? `${spec.width}×${spec.height} · three.js` : "渲染器未就绪";
    extra.rgbSize = `${spec.width} × ${spec.height}`;
    extra.rgbFov = `${spec.fov}°（垂直）`;
    extra.rgbBackend = "three.js（非 MuJoCo 原生）";
    extra.mountPos = fmtVec(mount.pos);
  }

  // ⑨ 读数表：**最后渲染** —— extra 由上面各分支填好，图与数同源。
  if (dockReadoutBox) {
    const rows = readoutRows(dock.source, { ...readout, ...extra });
    dockReadoutBox.innerHTML = rows
      .map(([label, value]) => `<div><small>${label}</small><strong>${value ?? "—"}</strong></div>`)
      .join("");
  }
  if (dockNote) dockNote.textContent = note || "—";
}

function updateCommandLabel() {
  // 「运动指令」区块（speedLabel）已移除；本函数只负责跳跃命令相关 UI。
  updateJumpControls();
  if (isWheelLegJumpPolicy()) {
    if (elements.cmdJumpMetric) elements.cmdJumpMetric.hidden = false;
    if (elements.cmdJumpMetric?.querySelector("small")) elements.cmdJumpMetric.querySelector("small").textContent = "跳跃命令";
    if (elements.cmdJump) elements.cmdJump.textContent = isJumpCommandActive() ? "ON" : "OFF";
    return;
  }
  if (hasHeightCommand()) {
    const height = activeHeightCommand();
    const axis = heightCommandAxis();
    const heightLabel = axis?.label || "跳跃高度";
    const heightUnit = axis?.unit || "m";
    if (elements.cmdJumpMetric) elements.cmdJumpMetric.hidden = false;
    if (elements.jumpCommandControl) elements.jumpCommandControl.hidden = false;
    if (elements.jumpHeightLabel) elements.jumpHeightLabel.textContent = `${height.toFixed(2)} ${heightUnit}`.trim();
    if (elements.cmdJumpMetric?.querySelector("small")) elements.cmdJumpMetric.querySelector("small").textContent = heightLabel;
    if (elements.cmdJump) elements.cmdJump.textContent = sim.cmd[heightCommandIndex()].toFixed(2);
    for (const button of elements.jumpHeightButtons) {
      const buttonHeight = bucketHeightCommand(Number(button.dataset.jumpHeight));
      button.classList.toggle("active", Math.abs(buttonHeight - height) < 0.001);
    }
    return;
  }
  if (elements.cmdJumpMetric) elements.cmdJumpMetric.hidden = true;
  if (elements.jumpCommandControl) elements.jumpCommandControl.hidden = true;
}

function updateJumpControls() {
  const enabled = isWheelLegJumpPolicy();
  const active = enabled && isJumpCommandActive();
  for (const button of document.querySelectorAll("[data-jump-command]")) {
    button.hidden = !enabled;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
    button.textContent = active ? "跳跃中" : "跳跃";
  }
  document.querySelector(".mobile-cruise-controls")?.classList.toggle("has-jump", enabled);
}

function publishDebugState() {
  if (!debugStateNode) return;
  debugStateNode.textContent = JSON.stringify(buildDebugState());
}

function maxAbs(values) {
  let result = 0;
  for (const value of values) result = Math.max(result, Math.abs(value));
  return result;
}

function buildDebugState() {
  return {
    paused: sim.paused,
    policyEnabled: sim.policyEnabled,
    time: sim.data?.time ?? null,
    model: sim.model ? {
      geomPos0: sim.model.geom_pos ? Array.from(sim.model.geom_pos.subarray(0, 3)) : null,
      ngeom: Number(sim.model.ngeom || 0),
      nmesh: Number(sim.model.nmesh || 0),
      geoms: (() => {
        try {
          const rows = [];
          for (let g = 0; g < Math.min(4, Number(sim.model.ngeom || 0)); g += 1) {
            rows.push({
              g,
              type: Number(sim.model.geom_type[g]),
              dataid: Number(sim.model.geom_dataid[g]),
              body: Number(sim.model.geom_bodyid[g]),
              pos: Array.from(sim.model.geom_pos.subarray(g * 3, g * 3 + 3)).map((v) => Number(v.toFixed(4))),
            });
          }
          return rows;
        } catch (_) { return null; }
      })(),
      meshes: (() => {
        try {
          const rows = [];
          for (let mi = 0; mi < Math.min(3, Number(sim.model.nmesh || 0)); mi += 1) {
            const vad = sim.model.mesh_vertadr[mi];
            const vnum = sim.model.mesh_vertnum[mi];
            const verts = sim.model.mesh_vert.subarray(vad * 3, (vad + vnum) * 3);
            const min = [Infinity, Infinity, Infinity];
            const max = [-Infinity, -Infinity, -Infinity];
            for (let i = 0; i < vnum; i += 1) {
              for (let a = 0; a < 3; a += 1) {
                const v = verts[i * 3 + a];
                if (v < min[a]) min[a] = v;
                if (v > max[a]) max[a] = v;
              }
            }
            rows.push({
              mi,
              pos: sim.model.mesh_pos ? Array.from(sim.model.mesh_pos.subarray(mi * 3, mi * 3 + 3)).map((v) => Number(v.toFixed(4))) : null,
              bounds: { min: min.map((v) => Number(v.toFixed(3))), max: max.map((v) => Number(v.toFixed(3))) },
            });
          }
          return rows;
        } catch (_) { return null; }
      })(),
    } : null,
    qpos: sim.qpos ? Array.from(sim.qpos) : [],
    qvel: sim.qvel ? Array.from(sim.qvel) : [],
    ctrl: sim.ctrl ? Array.from(sim.ctrl) : [],
    action: Array.from(sim.action),
    appliedAction: Array.from(sim.appliedAction),
    filteredAction: Array.from(sim.filteredAction),
    targetDofPos: Array.from(sim.targetDofPos),
    targetDofVel: Array.from(sim.targetDofVel),
    defaultAngles: Array.from(CONFIG.defaultAngles),
    dofReindex: CONFIG.dofReindex,
    actionReindex: CONFIG.actionReindex,
    hipScaleReduction: CONFIG.hipScaleReduction,
    torqueLimits: Array.from(CONFIG.torqueLimits),
    motorVelocityLimits: Array.from(CONFIG.motorVelocityLimits),
    dynamicTorqueLimits: Array.from(CONFIG.dynamicTorqueLimits),
    motorEnvelopes: CONFIG.motorEnvelopes,
    command: Array.from(sim.cmd),
    gait: {
      requested: OBSERVATION.wheelLegGaitRequested(),
      active: sim.gaitActive,
      commandSpeed: OBSERVATION.wheelLegGaitCommandSpeed(),
      elapsedS: sim.gaitElapsedS,
      commandGated: CONFIG.gaitCommandGated,
    },
    defaultCommand: Array.from(CONFIG.defaultCommand),
    cruiseVx: input.cruiseVx,
    joystickActive: input.joystickPointer !== null,
    obsDim: CONFIG.numObs,
    obs: Array.from(sim.obs),
    commandDims: CONFIG.commandDims,
    agilityCommandDims: CONFIG.agilityCommandDims,
    historyFrames: Math.floor(sim.history.length / CONFIG.numObs),
    historyLength: sim.history.length,
    policyMode: sim.policyInfo?.mode || "",
    policyInputs: sim.policyInfo?.inputNames || [],
    recurrentState: Object.fromEntries(
      Object.entries(sim.recurrentState).map(([name, data]) => [name, { length: data.length, maxAbs: maxAbs(data) }]),
    ),
    policyHealth: sim.platformConfig?.policy?.health || null,
    autoplay: shouldAutoplayPolicy(),
    controlDecimation: CONFIG.controlDecimation,
    kps: Array.from(CONFIG.kps),
    kds: Array.from(CONFIG.kds),
    motionLoop: CONFIG.motionLoop === true,
    motionDuration: sim.motionLoader?.duration ?? null,
    actuatorRoles: CONFIG.actuatorRoles,
    controlModes: CONFIG.controlModes,
    payloadMassKg: input.payloadMassKg,
    comOffsetM: Array.from(input.comOffsetM),
    terrainFriction: input.terrainFriction,
    imuAxisSigns: {
      angular: Array.from(input.imuAxisSigns.angular),
      gravity: Array.from(input.imuAxisSigns.gravity),
    },
    signalDelay: {
      motor: {
        enabled: input.motorDelayEnabled,
        maxSteps: input.motorDelayMaxSteps,
        sampledSteps: input.motorDelaySampleSteps,
        remainingSteps: sim.motorDelayRemaining,
        pending: sim.motorTargetPending,
      },
      imu: {
        enabled: input.imuDelayEnabled,
        maxSteps: input.imuDelayMaxSteps,
        sampledSteps: input.imuDelaySampleSteps,
        bufferedSamples: sim.imuSamples.length,
      },
    },
    baseBodyMassKg: sim.baseBodyMassKg,
    baseBodyComLocal: Array.from(sim.baseBodyComLocal),
    effectiveBaseBodyComLocal: sim.baseBodyId >= 0 && sim.model?.body_ipos
      ? Array.from(
        { length: 3 },
        (_, axis) => Number(sim.model.body_ipos[sim.baseBodyId * 3 + axis] || 0),
      )
      : [],
    effectiveBaseBodyMassKg: sim.baseBodyId >= 0
      ? Number(sim.model?.body_mass?.[sim.baseBodyId] || 0)
      : 0,
    geoms: DEBUG_ENABLED ? debugGeoms() : [],
    status: {
      engine: elements.engineStatus?.textContent || "",
      policy: elements.policyStatus?.textContent || "",
      height: elements.baseHeight?.textContent || "",
    },
  };
}

function debugGeoms() {
  if (!sim.model || !sim.data) return [];
  const geoms = [];
  for (let id = 0; id < sim.model.ngeom; id += 1) {
    const offset = id * 3;
    // mjtObj.mjOBJ_BODY === 1：geom -> body 名称（原 geomBodyName 未定义，
    // debug 模式一进 reset 就 ReferenceError，v0.43 修复）
    let bodyName = null;
    try {
      const bodyId = Number(sim.model.geom_bodyid[id]);
      bodyName = sim.mujoco.mj_id2name(sim.model, 1, bodyId) || `body${bodyId}`;
    } catch (_) { /* 保留 null */ }
    geoms.push({
      id,
      body: bodyName,
      kind: classifyGeom({ objtype: sim.objGeom, objid: id }),
      type: sim.model.geom_type[id],
      size: Array.from(sim.model.geom_size.subarray(offset, offset + 3)),
      position: Array.from(sim.data.geom_xpos.subarray(offset, offset + 3)),
    });
  }
  return geoms;
}

function updatePerf(now) {
  const elapsed = (now - view.lastClockUpdate) / 1000;
  if (elapsed < 1) return;
  view.fps = view.frames / elapsed;
  view.simRate = (view.simSteps * CONFIG.simulationDt) / elapsed;
  elements.perfStats.textContent = `${Math.round(view.fps)} 帧/秒 · ${view.simRate.toFixed(2)}x`;
  view.frames = 0;
  view.simSteps = 0;
  view.lastClockUpdate = now;
}

function initExpertBars() {
  if (!elements.expertBars) return;
  elements.expertBars.innerHTML = "";
  for (let i = 0; i < 8; i += 1) {
    const row = document.createElement("div");
    row.className = "expert";
    row.innerHTML = `<span>E${i + 1}</span><span class="expert-track"><i></i></span><span>0%</span>`;
    elements.expertBars.append(row);
  }
}

function updateExpertBars() {
  if (!elements.expertBars || !elements.dominantExpert || !sim.policyInfo?.weightsName) return;
  let bestIndex = 0;
  let best = -Infinity;
  const rows = [...elements.expertBars.querySelectorAll(".expert")];
  rows.forEach((row, index) => {
    const weight = Number(sim.weights[index] || 0);
    if (weight > best) {
      best = weight;
      bestIndex = index;
    }
    row.querySelector("i").style.width = `${clamp(weight * 100, 0, 100)}%`;
    row.querySelector("span:last-child").textContent = `${Math.round(weight * 100)}%`;
  });
  elements.dominantExpert.textContent = `E${bestIndex + 1}`;
}

function updateKeyCaps() {
  const mapping = {
    KeyW: input.keys.has("KeyW") || input.keys.has("ArrowUp"),
    KeyS: input.keys.has("KeyS") || input.keys.has("ArrowDown"),
    KeyA: input.keys.has("KeyA"),
    KeyD: input.keys.has("KeyD"),
    KeyQ: input.keys.has("KeyQ") || input.keys.has("ArrowLeft"),
    KeyE: input.keys.has("KeyE") || input.keys.has("ArrowRight"),
  };
  Object.entries(mapping).forEach(([code, active]) => {
    elements.keys[code]?.classList.toggle("active", active);
  });
}

function togglePause() {
  sim.paused = !sim.paused;
  elements.playButton.textContent = sim.paused ? "继续" : "暂停";
}


// 世界系线速度 → 机体系（v_body = R^T · v_world，与 getGravityOrientation 同一约定）



function makeGeomTypes(mujoco) {
  return {
    plane: enumValue(mujoco.mjtGeom.mjGEOM_PLANE),
    sphere: enumValue(mujoco.mjtGeom.mjGEOM_SPHERE),
    capsule: enumValue(mujoco.mjtGeom.mjGEOM_CAPSULE),
    cylinder: enumValue(mujoco.mjtGeom.mjGEOM_CYLINDER),
    box: enumValue(mujoco.mjtGeom.mjGEOM_BOX),
    mesh: enumValue(mujoco.mjtGeom.mjGEOM_MESH),
    hfield: enumValue(mujoco.mjtGeom.mjGEOM_HFIELD),
  };
}


function ensureDir(path) {
  try {
    sim.mujoco.FS.mkdir(path);
  } catch (error) {
    if (!String(error).includes("File exists")) throw error;
  }
}

function ensureParentDirs(filePath) {
  const parts = filePath.split("/").filter(Boolean);
  let current = "";
  for (let i = 0; i < parts.length - 1; i += 1) {
    current += `/${parts[i]}`;
    ensureDir(current);
  }
}

function setLoading(progress, text) {
  elements.loading.classList.remove("is-error");
  elements.loadingText.textContent = text;
  elements.loadingBar.style.width = `${clamp(progress * 100, 0, 100)}%`;
}

// Update the loading label AND force the browser to actually paint it before we
// return. The heavy init calls (ort InferenceSession.create, MuJoCo loadFromXML)
// are synchronous WASM that block the main thread; without a forced paint the
// label the user sees frozen on screen is the PREVIOUS step, not the one that is
// actually blocking. Double rAF + a macrotask guarantees a paint lands first, so
// whatever label is on screen when it freezes is precisely the culprit step.
async function setLoadingPainted(progress, text) {
  const t = performance.now();
  console.log(`[sim2sim] ▶ ${text}`);
  setLoading(progress, text);
  await new Promise((resolve) => {
    requestAnimationFrame(() =>
      requestAnimationFrame(() => setTimeout(resolve, 0)),
    );
  });
  return t;
}

// ---------------------------------------------------------------------------
// 查看器状态与 URL 持久化（借鉴 mjswan urlState.ts 的纯函数思路）
// ---------------------------------------------------------------------------

/**
 * 从 URL query 读取查看器 UI 状态（纯函数：只依赖入参，不触碰 DOM/地址栏）。
 * @param {URLSearchParams} params
 * @returns {{ panelVisible: boolean, trailVisible: boolean }}
 */
function readViewerStateFromUrl(params = new URLSearchParams(window.location.search)) {
  return {
    // panel=0 → 隐藏控制面板；缺省/其它值 → 显示。
    panelVisible: params.get("panel") !== "0",
    // trail=1 → 显示根轨迹拖尾；缺省 → 关闭。
    trailVisible: params.get("trail") === "1",
  };
}

/**
 * 把查看器 UI 状态合并进 query 串（纯函数：返回新的查询串，不改地址栏）。
 * @param {URLSearchParams} params 现有参数
 * @param {{ panelVisible?: boolean, trailVisible?: boolean }} state 增量状态
 * @returns {string} 新的 query（以 "?" 开头）
 */
function writeViewerStateToQuery(params, state) {
  const next = new URLSearchParams(params);
  if (typeof state.panelVisible === "boolean") next.set("panel", state.panelVisible ? "1" : "0");
  if (typeof state.trailVisible === "boolean") next.set("trail", state.trailVisible ? "1" : "0");
  return `?${next.toString()}`;
}

// 确定性回放（清单 ⑦，验收协议的浏览器环节）：?replay=vx,vy,wz[&seed=N]
// 固定指令优先级最高（压过键盘/摇杆/滑条），observation 随机化关闭，保证同一
// 策略+模型+seed 在任何机器上回放出同一条轨迹；配合 /acceptance 指标做"视觉不通过 = 不通过"。
function applyDeterministicReplayFromUrl() {
  // 注意：本函数在 init() 里调用；不能依赖模块顶层赋值（顶层语句会在 init()
  // 启动后才执行，覆盖掉这里设置的状态——曾导致回放指令被静默清零）。
  sim.deterministicReplay = null;
  const raw = PAGE_PARAMS.get("replay") || "";
  if (!raw) return;
  const parts = raw.split(",").map((v) => Number(v.trim()));
  if (parts.length < 1 || parts.some((v) => !Number.isFinite(v))) {
    console.warn("[sim2sim] invalid replay command, ignoring:", raw);
    return;
  }
  while (parts.length < 3) parts.push(0);
  const seedParam = Number(PAGE_PARAMS.get("seed") || "0");
  sim.deterministicReplay = {
    command: [parts[0], parts[1], parts[2]],
    seed: Number.isFinite(seedParam) ? seedParam : 0,
  };
  document.title = `确定性回放 ${raw} · seed ${sim.deterministicReplay.seed} · Locomotion Platform`;
  console.info(`[sim2sim] deterministic replay: cmd=[${parts.slice(0, 3)}] seed=${sim.deterministicReplay.seed}`);
}

// ---------------------------------------------------------------------------
// 感知导航（H3 `command_source=planner`）——浏览器侧
//
// 分工见 web/sim2sim/navigation.js 顶部：**规划与到达判据由服务端装配**
// （backend/navigation_plan.py → POST /api/navigation/plan），浏览器只做
// "折线 → 每拍 cmd_vel"的跟随，以及按服务端判据判定到达。URL 用法：
//   ?nav=warehouse                    用地图自带障碍与默认航点规划
//   ?nav=warehouse&nav_waypoints=0,0;6,0   指定航点（分号分隔）
// ---------------------------------------------------------------------------
const NAV_HUD_ID = "navigationHud";
//: 感知轮询频率：每 N 个控制步评一次地形（10 ⇒ 50 Hz 控制下 5 Hz）
const TERRAIN_POLL_CONTROL_STEPS = 10;
//: H11 候选扇形轮询频率与容量（35 候选 × 20 点 ≈ 1330 顶点，6000 顶点足够）
const DWA_FAN_POLL_CONTROL_STEPS = 10;
const DWA_FAN_MAX_VERTICES = 6000;
const DWA_FAN_COLORS = { best: 0x2ecc71, valid: 0x3b82f6, rejected: 0x8b98a5 };

/** 懒创建扇形线段对象（与 trail 同构：固定容量顶点 + 动态 DrawRange）。 */
function ensureDwaFan() {
  if (view.dwaFan) return view.dwaFan;
  const positions = new Float32Array(DWA_FAN_MAX_VERTICES * 3);
  const colors = new Float32Array(DWA_FAN_MAX_VERTICES * 3);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  geometry.setDrawRange(0, 0);
  const lines = new THREE.LineSegments(
    geometry,
    new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.6, depthWrite: false }),
  );
  lines.frustumCulled = false;
  lines.visible = false;
  view.scene.add(lines);
  view.dwaFan = { lines, geometry, positions, colors, maxVertices: DWA_FAN_MAX_VERTICES, segments: 0 };
  return view.dwaFan;
}

function resetDwaFan() {
  if (!view.dwaFan) return;
  view.dwaFan.geometry.setDrawRange(0, 0);
  view.dwaFan.lines.visible = false;
  view.dwaFan.segments = 0;
}

/**
 * H11：把候选扇形画进场景（被拒灰 → 可行蓝 → 最优绿，后画的覆盖先画的）。
 * 数据来自服务端 `POST /api/navigation/local-plan`，浏览器只做成形与上色——
 * 分组/展开规则在 `dwa_fan.js`（纯函数，有 node 单测），这里只负责写进 BufferGeometry。
 */
function paintDwaFan(candidates, baseZ) {
  const target = ensureDwaFan();
  const groups = fanSegments(candidates);
  const stacks = [
    [groups.rejected, DWA_FAN_COLORS.rejected],
    [groups.valid, DWA_FAN_COLORS.valid],
    [groups.best, DWA_FAN_COLORS.best],
  ];
  const color = new THREE.Color();
  let vertex = 0;
  for (const [polylines, hex] of stacks) {
    if (!polylines.length) continue;
    const flat = fanLineSegments(polylines);
    color.setHex(hex);
    for (let i = 0; i + 2 < flat.length && vertex < target.maxVertices; i += 3) {
      target.positions[vertex * 3] = flat[i];
      target.positions[vertex * 3 + 1] = flat[i + 1];
      // 轨迹是平面 2D（[x, y]），按机器人当前 base 高度贴地绘制
      target.positions[vertex * 3 + 2] = baseZ;
      target.colors[vertex * 3] = color.r;
      target.colors[vertex * 3 + 1] = color.g;
      target.colors[vertex * 3 + 2] = color.b;
      vertex += 1;
    }
  }
  target.geometry.setDrawRange(0, vertex);
  target.geometry.attributes.position.needsUpdate = true;
  target.geometry.attributes.color.needsUpdate = true;
  target.segments = Math.floor(vertex / 2);
  target.lines.visible = vertex >= 2 && Boolean(sim.dwaFan?.enabled && !sim.navigation?.status?.finished);
}

/** 每 N 控制步取一次候选扇形；失败即关闭并只提示一次（与感知闭环同口径，不刷屏）。 */
async function pollDwaFan(pose, controlStep) {
  const state = sim.dwaFan;
  if (!state?.enabled || state.inFlight || state.lastControlStep === controlStep) return;
  if (!sim.navigation?.payload) return;
  state.lastControlStep = controlStep;
  state.inFlight = true;
  try {
    const waypoints = (sim.navigation.payload.waypoints || []).map((w) => [Number(w.x), Number(w.y)]);
    const response = await fetch("/api/navigation/local-plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        map_id: sim.navigation.mapId,
        pose: [pose.x, pose.y, pose.yaw],
        velocity: [Number(sim.targetCmd?.[0] || 0), 0, Number(sim.targetCmd?.[2] || 0)],
        waypoints,
        include_fan: true,
      }),
    });
    const payload = await response.json();
    if (!response.ok || !payload?.success) {
      throw new Error(payload?.detail || `HTTP ${response.status}`);
    }
    paintDwaFan(payload.candidates, Number(sim.qpos?.[2] ?? 0.45));
    state.reason = payload.reason;
    state.polls = (state.polls || 0) + 1;
  } catch (error) {
    state.errors = (state.errors || 0) + 1;
    if (state.errors === 1) console.warn("[sim2sim] DWA 扇形已关闭：", error.message);
    state.enabled = false;
    resetDwaFan();
  } finally {
    state.inFlight = false;
  }
}

/**
 * 感知闭环：上传位姿 → 服务端按**同源地形**判定并给切换决定 → 下一拍施加。
 *
 * 失败即**禁用**感知并把原因显示出来（不静默按平地处理，也不每步重试刷屏）；
 * 浏览器侧依据是"场景地形数据 + 位姿"，**不是机载射线/深度**——这一点在 HUD 与
 * 服务端返回的 note 里都写明。
 */
async function pollTerrainPerception(pose, controlStep) {
  const perception = sim.perception;
  if (!perception || perception.disabledReason || perception.inFlight) return;
  perception.inFlight = true;
  perception.polls += 1;
  const policyIds = elements.policySelect
    ? Array.from(elements.policySelect.options).map((option) => option.value).filter(Boolean)
    : [];
  try {
    const response = await fetch("/api/perception/terrain/evaluate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scene_id: perception.sceneId,
        base_xy: [pose.x, pose.y],
        base_z: Number(sim.qpos?.[2] ?? 0.45),
        base_yaw: pose.yaw,
        base_limits: Array.from(sim.navigation?.status?.limits || []).length === 3
          ? { vx: sim.navigation.status.limits[0], vy: sim.navigation.status.limits[1], wz: sim.navigation.status.limits[2] }
          : undefined,
        available_policies: policyIds,
      }),
    });
    const payload = await response.json();
    if (!response.ok || !payload?.success) {
      throw new Error(payload?.detail || `感知评估失败（HTTP ${response.status}）`);
    }
    perception.lastReading = payload.reading;
    perception.decision = payload.switch;
    perception.scene = payload.scene;
    if (payload.switch?.kind === "policy" && payload.switch.policy_id) {
      // 策略可切换时才切（离散切换会重置策略状态，代价写在决定说明里）
      if (elements.policySelect && policyIds.includes(payload.switch.policy_id)) {
        await switchPolicy(payload.switch.policy_id);
      }
    }
    if (DEBUG_ENABLED) console.info(`[sim2sim] terrain @step ${controlStep}`, payload.reading.raw_class, payload.switch.kind);
  } catch (error) {
    perception.errors += 1;
    perception.disabledReason = error.message;
    perception.decision = null;
    console.warn("[sim2sim] terrain perception disabled:", error.message);
  } finally {
    perception.inFlight = false;
    renderNavigationHud();
  }
}

async function initNavigationFromUrl() {
  const mapId = PAGE_PARAMS.get("nav");
  if (!mapId) return;
  const raw = PAGE_PARAMS.get("nav_waypoints") || "";
  const waypoints = raw
    .split(";")
    .map((pair) => pair.split(",").map((value) => Number(value.trim())))
    .filter((point) => point.length === 2 && point.every((value) => Number.isFinite(value)));
  try {
    const response = await fetch("/api/navigation/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ map_id: mapId, ...(waypoints.length >= 2 ? { waypoints } : {}) }),
    });
    const payload = await response.json();
    if (!response.ok || !payload?.success) {
      throw new Error(payload?.detail || `规划失败（HTTP ${response.status}）`);
    }
    sim.navigation = {
      mapId,
      payload,
      runner: createNavigationRunner(payload, {
        maxCmd: Array.from(CONFIG.maxCmd),
        lookahead: Number(PAGE_PARAMS.get("nav_lookahead") || 0.6),
      }),
      status: null,
      lastControlStep: -1,
    };
    // 感知闭环（S6）：地形判定 + 切换决定由服务端唯一实现，浏览器只上传位姿并施加决定。
    // 场景 id 默认取导航地图；服务端不认识该场景时**禁用**感知（不按平地处理）。
    sim.perception = {
      sceneId: PAGE_PARAMS.get("nav_scene") || mapId,
      decision: null,
      lastReading: null,
      disabledReason: null,
      inFlight: false,
      polls: 0,
      errors: 0,
    };
    // H11 候选扇形：默认随导航开启，?fan=0 可关（候选/评分由服务端算，浏览器只画）
    sim.dwaFan = {
      enabled: PAGE_PARAMS.get("fan") !== "0",
      inFlight: false,
      lastControlStep: -1,
      polls: 0,
      errors: 0,
      reason: "",
    };
    renderNavigationHud(`导航已就绪 · ${mapId} · ${payload.waypoints.length} 个航点 · 判据 ${payload.arrival.source}`);
    console.info(`[sim2sim] navigation ${NAVIGATION_VERSION}`, payload);
  } catch (error) {
    sim.navigation = null;
    renderNavigationHud(`导航不可用：${error.message}`, true);
    console.error("[sim2sim] navigation init failed", error);
  }
}

/** 每物理步给指令；到达判定只在**控制步**推进（与 frameLog 的 stepIndex 同口径）。 */
function applyNavigationCommand() {
  if (!sim.qpos) return;
  const pose = poseFromQpos(sim.qpos);
  // 感知结果施加在**跟随指令之上**：只可能更严（限速/停机），不会放大权限
  const decision = sim.perception?.disabledReason ? null : (sim.perception?.decision ?? null);
  const switched = applyTerrainSwitch(sim.navigation.runner.command(pose), decision);
  for (let i = 0; i < 3; i += 1) {
    const value = clamp(switched.cmd[i], -CONFIG.maxCmd[i], CONFIG.maxCmd[i]);
    sim.targetCmd[i] = value;
    sim.cmd[i] = value;
  }
  syncBinaryJumpCommand();
  const controlStep = Math.floor(sim.counter / CONFIG.controlDecimation);
  if (sim.navigation.lastControlStep !== controlStep) {
    sim.navigation.lastControlStep = controlStep;
    sim.navigation.status = sim.navigation.runner.tick(pose);
    renderNavigationHud();
    if (controlStep % TERRAIN_POLL_CONTROL_STEPS === 0) {
      pollTerrainPerception(pose, controlStep);
      pollDwaFan(pose, controlStep);
    }
  }
}

function renderNavigationHud(message = "", failed = false) {
  let hud = document.querySelector(`#${NAV_HUD_ID}`);
  if (!sim.navigation) {
    if (hud) hud.remove();
    return;
  }
  if (!hud) {
    hud = document.createElement("div");
    hud.id = NAV_HUD_ID;
    hud.style.cssText = "position:fixed;left:12px;bottom:12px;z-index:40;padding:6px 10px;border-radius:8px;background:rgba(10,14,22,.82);color:#dfe8f5;font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;pointer-events:none;white-space:pre";
    document.body.appendChild(hud);
  }
  hud.style.color = failed ? "#ffb4b4" : "#dfe8f5";
  if (message) {
    hud.textContent = message;
    return;
  }
  const status = sim.navigation?.status;
  if (!status) return;
  const legs = `${Math.max(0, status.reached - 1)}/${status.waypoint_count - 1}`;
  hud.textContent = status.finished
    ? `导航 ${sim.navigation.mapId} · 航段 ${legs} · 完成率 100% · 已完成`
    : `导航 ${sim.navigation.mapId} · 航段 ${legs} · 完成率 ${Math.round(status.route_completion * 100)}%`
      + ` · 容差 ${status.tolerance_m}m（稳定 ${status.stable_count}/${status.stable_ticks}）`
      + ` · 上限 vx${status.limits[0]} wz${status.limits[2]}`;
  const perception = sim.perception;
  if (perception?.lastReading) {
    const reading = perception.lastReading;
    const kind = perception.decision?.kind || "无";
    hud.textContent += `\n地形 ${reading.raw_class}（置信 ${reading.confidence}）· 切换 ${kind}`;
  } else if (perception?.disabledReason) {
    hud.textContent += `\n感知不可用：${perception.disabledReason}`;
  }
}

/** 把当前 UI 状态写入地址栏（replaceState，不产生历史记录）。 */
function syncViewerStateToUrl() {
  try {
    const params = new URLSearchParams(window.location.search);
    const query = writeViewerStateToQuery(params, {
      panelVisible: !document.body.classList.contains("panel-hidden"),
      trailVisible: Boolean(elements.trailToggle?.checked),
    });
    history.replaceState(null, "", `${window.location.pathname}${query}${window.location.hash}`);
  } catch (error) {
    console.warn("viewer state url sync skipped", error);
  }
}

/** 应用 URL 中的查看器状态（init 时调用一次）。 */
function applyViewerStateFromUrl() {
  const state = readViewerStateFromUrl();
  document.body.classList.toggle("panel-hidden", !state.panelVisible);
  if (elements.trailToggle) elements.trailToggle.checked = state.trailVisible;
  if (elements.mobileControlsToggle) {
    elements.mobileControlsToggle.setAttribute("aria-expanded", String(state.panelVisible));
  }
}

/** C 键 / 面板折叠按钮共用的显隐切换。 */
function toggleControlPanel(force) {
  const nextHidden = typeof force === "boolean"
    ? !force
    : !document.body.classList.contains("panel-hidden");
  document.body.classList.toggle("panel-hidden", nextHidden);
  if (elements.mobileControlsToggle) {
    elements.mobileControlsToggle.setAttribute("aria-expanded", String(!nextHidden));
  }
  syncViewerStateToUrl();
}


// ---------------------------------------------------------------------------
// WASM OOM 友好报错（借鉴 mjswan runtime.ts 的 isWasmOom 思路）
// ---------------------------------------------------------------------------

// mj_loadXML / InferenceSession.create 在触顶 2 GB WASM 内存时有多种报错路径：
// null 返回值、MuJoCo 分配错误串、lodepng 解码错误、原始 bad_alloc 等。
function isWasmOom(error) {
  const message = error instanceof Error
    ? `${error.message || ""}\n${error.stack || ""}`
    : String(error);
  return /MjModel loading returned null|Could not allocate memory|memory allocation failed|bad_alloc|lodepng|Cannot enlarge memory|out of (memory|GPU memory)|array buffer allocation failed/i.test(message);
}

/** 统一把加载/编译错误转换成面向用户的中文提示。 */
function describeLoadError(error) {
  if (isWasmOom(error)) {
    return new Error("超出 WebAssembly 内存上限（约 2 GB）。请减小模型/网格规模，或关闭其它标签页后重试。");
  }
  return error;
}

function showLoadingError(text) {
  elements.loading.classList.remove("is-hidden");
  elements.loading.classList.add("is-error");
  elements.loadingText.textContent = text || "Sim2Sim 加载失败";
  elements.loadingBar.style.width = "100%";
}

function setStatus(element, text, state) {
  element.childNodes[element.childNodes.length - 1].textContent = text;
  element.classList.toggle("ready", state === "ready");
  element.classList.toggle("error", state === "error");
}

function resize(explicitWidth = 0, explicitHeight = 0) {
  if (!elements.viewer || !view.renderer || !view.camera) return;
  const width = Math.max(1, Math.round(explicitWidth || elements.viewer.clientWidth || window.innerWidth));
  const height = Math.max(1, Math.round(explicitHeight || elements.viewer.clientHeight || window.innerHeight));
  view.camera.aspect = width / Math.max(height, 1);
  view.camera.updateProjectionMatrix();
  view.renderer.setSize(width, height, false);
  view.renderer.domElement.style.width = "100%";
  view.renderer.domElement.style.height = "100%";
}

function disposeMujocoScene() {
  sim.scene?.delete();
  sim.camera?.delete();
  sim.perturb?.delete();
  sim.option?.delete();
  sim.data?.delete();
  sim.model?.delete();
  sim.scene = null;
  sim.camera = null;
  sim.perturb = null;
  sim.option = null;
  sim.data = null;
  sim.model = null;
  sim.qpos = null;
  sim.qvel = null;
  sim.ctrl = null;
  sim.baseBodyId = -1;
  sim.baseBodyMassKg = 0;
  sim.baseBodyComLocal.fill(0);
}

function clearRenderGeoms() {
  for (const renderable of view.geoms) disposeRenderable(renderable);
  view.geoms = [];
  for (const geometry of view.geometryCache.values()) geometry.dispose();
  view.geometryCache.clear();
  for (const material of view.materials.values()) material.dispose();
  view.materials.clear();
}

function disposeRenderable(renderable) {
  if (!renderable) return;
  view.scene.remove(renderable.mesh);
  renderable.material.dispose();
  view.materials.delete(renderable.material);
}



