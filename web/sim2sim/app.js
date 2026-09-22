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
// 执行器角色/控制模式解析：与同状态对拍工具（tools/obs_crosscheck.mjs）**同一个函数**，
// 不许各写一份（2026-09-22：工具少读 `control_modes` 就把 m20/b2w 误判成实现不一致）。
import {
  normalizeNameMap,
  jointGroup,
  resolveActuatorRolesAndModes,
} from "./obs/actuator_modes.js?v=0.62.0";
// 契约级**槽表**（`onnx_slots`）：导出器命名不可依赖的产物按**位置**绑定 in/out 槽。
import { resolveOnnxSlots } from "./obs/onnx_slots.js?v=0.46.0";
import { createPieDepth } from "./pie_depth.js?v=0.46.0";
// 观测面板绘制器（深度帧 / 俯视高度场 / 极坐标扫描 / 点云散点 / 2D 轨迹平面）。
// 纯函数 + 注入 ctx：能画什么由参数决定，模块不读 sim / DOM，所以 Node 单测能覆盖。
import {
  drawContactStates,
  drawDepthFrame,
  drawHeightGrid,
  drawHeightField,
  drawPointCloud,
  drawPolarScan,
  drawTrail,
} from "./sensor_panels.js";
// 传感器视图悬浮窗：来源清单 / 插件清单 / 读数 / 装配与采样规格
// （纯逻辑在那边，这里只接线）。
// 传感器框架：pattern 生成（对标 mjlab raycast_sensor 的三种 PatternCfg）+ 目录参数真值
import { buildPattern } from "./sensors/sensor_patterns.js?v=0.46.0";
import { aggregateHeightScan, patternParams } from "./sensors/sensor_catalog.js?v=0.46.0";
import { createHeightScanLayer, createLidarLayer, createContactLayer, createImuAxes, createRangefinderLayer, updatePointsLayer } from "./sensors/sensor_layers.js?v=0.46.0";
import {
  applyContactNoise,
  applyDepthNoise,
  applyImuNoise,
  applyRangeNoise,
  createNoiseRegistry,
  describeNoiseRegistry,
} from "./sensors/sensor_runtime.js?v=0.46.0";
import { EXECUTOR_COMMAND_SOURCES, unsupportedCommandSourceProblems } from "./scenario_run.js?v=0.46.0";
import { resolveTerrainKit, paintFloorTile } from "./terrain_materials.js?v=0.46.0";
import { heightPointColors, distancePointColors, contactVisualStates } from "./sensors/sensor_visual.js?v=0.46.0";
// 屏幕系/相机系**唯一真值**（哪边朝上、哪边朝右、像素↔射线）——坞里所有图与两个相机
// 预览都从这里取换算，见该文件头部"为什么单独一个模块"。
import { cameraBasis, rayFromBasis } from "./sensors/screen_frame.js?v=0.46.0";
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
} from "./sensor_dock.js?v=0.55.0";
// A1 场景运行侧：交运消息解析 + 判据/度量/记录器产物（纯逻辑在那边，这里只接线）。
import {
  buildRunSummary,
  parseScenarioMessage,
  recorderArtifacts,
  SCENARIO_MESSAGE_TYPE,
  tracePoint,
} from "./scenario_run.js?v=0.46.0";
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
} from "./raycast.js?v=0.55.0";
import { MotionLoader } from "./motion_loader.js";
// G3「加载即校验」：ONNX metadata_props 扫描 + 契约校验（纯函数，Node 单测覆盖）。
import {
  checkOnnxMetadataContract,
  contractSummaryFromConfig,
  formatContractViolations,
  scanOnnxMetadata,
} from "./onnx_contract_check.js";
import { clamp, escapeAttr, escapeHtml, formatSigned, quatToRpy, quatRotateInverse, imuSampleFromQpos, enumValue, isEditableElement } from "./utils.js";
import { applyTerrainSwitch, createNavigationRunner, poseFromQpos, NAVIGATION_VERSION } from "./navigation.js?v=0.55.0";
// 地形归组（G5）：_index.json 分类快照 → optgroup 分组结构（纯函数，Node 单测覆盖）。
import { groupTerrains } from "./terrain_groups.js?v=0.55.41";
import { fanSegments, fanLineSegments } from "./dwa_fan.js?v=0.55.0";
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
// 高级仿真：左上角是传感器悬浮窗（sensor-dock），品牌卡（top:16/left:16）会和它叠在一起
// （embedded 入口本来就隐藏 .brand，直连 URL 没有 embedded 类 → 补一个等价类，见 styles.css）。
if (SHOW_ADVANCED_PANELS) document.body.classList.add("surface-advanced");
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
  dockPluginsBox.className = "dock-plugin-list"; // 列表网格样式在 CSS 里只挂在 .dock-plugin-list 上，重建内容时必须把类挂回去
  dockPluginsBox.innerHTML = SENSOR_PLUGINS.map((p) => `
    <label title="${p.hint}">
      <input type="checkbox" data-plugin="${p.id}"${dock.plugins[p.id] ? " checked" : ""} />
      <span>${p.label} · ${p.onboard ? "本体" : "外挂"}</span>
    </label>`).join("");
  // 退化模型开关：**默认关**（历史读数均为理想值）。开了按当前场景种子可复现地退化，
  // 摘要显示在读数 note 里——"这次读数是理想值还是退化值"必须看得见。
  const noiseBox = dockPluginsBox.querySelector('[data-noise-toggle]');
  if (noiseBox) {
    noiseBox.checked = sim.sensorNoise.enabled;
    noiseBox.addEventListener("change", () => {
      sim.sensorNoise = createNoiseRegistry(Number(PAGE_PARAMS.get("seed") || 0), noiseBox.checked);
      console.info("[sim2sim] sensor noise", describeNoiseRegistry(sim.sensorNoise));
    });
  }
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

/** 场景感知项 → 坞插件 id（**同一张表**驱动"声明即开"与来源可选性）。 */
const PERCEPTION_TO_DOCK_PLUGIN = {
  heightfield: "height",
  depth_camera: "depth",
  foot_contact: "foot_contact",
};

/**
 * 场景声明了某项感知 ⇒ **把坞里对应的插件真的打开**（2026-09-23 修）。
 *
 * 此前 `sim.scenarioSensors` 只被写过一次、**全仓没有读者**：页面上明明提示
 * "感知传感器已启用：depth_camera"，但坞的插件勾选没动 ⇒ 来源下拉里**根本没有"深度相机"
 * 这一项**（`DOCK_SOURCES[].requires` 就是按插件过滤的），用户既看不到声明的那台相机，
 * 也就无从判断它"对不对"——典型的**声明与实际不符的静默空转**。
 *
 * @returns {string[]} 本次新打开的插件 id（用于在面板里如实说明"顺带开了什么"）
 */
function enableDockPluginsForScenario(perception) {
  const ids = Object.entries(PERCEPTION_TO_DOCK_PLUGIN)
    .filter(([field]) => Boolean(perception?.[field]))
    .map(([, plugin]) => plugin)
    .filter((id) => SENSOR_PLUGINS.some((item) => item.id === id));
  if (!ids.length) return [];
  if (!dock.plugins) dock.plugins = {};
  const turned = ids.filter((id) => !dock.plugins[id]);
  for (const id of ids) dock.plugins[id] = true;
  if (turned.length) {
    renderDockPlugins();
    renderDockSources();
    ensureSensorModels();
    renderDockMounts();
  }
  return turned;
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

if (dockRoot) {
  dockRoot.hidden = !dock.visible;
  // 定位基准改挂 #viewer：dock 原是 .panel-left（滚动容器）的子元素，absolute 相对面板
  // 解析会盖住面板状态行、且随面板滚动被裁掉；CSS 里 .sensor-dock 的注释有实测记录。
  // viewer 是 fixed+inset:0 的全屏视口，dock 移进去后钉在视口左上角。
  // （#viewer 按 id 现查：此时 elements 常量还没初始化，不能引用它。）
  document.querySelector("#viewer")?.appendChild(dockRoot);
}
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
  shadowToggle: document.querySelector("#shadowToggle"),
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
  // A1 场景运行态：交运来的完整场景 + 轨迹采样 + 判据/摘要。场景说了算——
  // 未声明的判据不跑、未声明的记录器不造文件（见 scenario_run.js）。
  scenario: null,
  scenarioRun: {
    trace: [],
    active: false,
    deadlineS: null,
    summary: null,
    applied: null,
    refusedReason: "",
  },
  // 就绪前到达的场景（父页不等 ready 回执就发的情况）——就绪后应用，不丢不假拒
  pendingScenario: null,
  // B1：执行器能力矩阵（GET /api/simulation/executors）——指令来源能不能跑由它判
  executorMatrix: null,
  // 传感器退化模型（框架 sensors/sensor_runtime.js）。**默认关**——历史读数均为理想值，
  // 默认打开会静默改变所有读数与策略表现。开了就按场景种子可复现地退化。
  sensorNoise: createNoiseRegistry(0, false),
  // 坞内射线类扫描的节流状态（上次重扫时刻/来源）
  dockScan: { lastMs: -1e9, lastSource: "" },
  // Isaac 风格 3D 可视化层（高度彩球 / LiDAR 点云 / 足底接触球 / IMU 轴）
  sensorViz: {},
};

const view = {
  scene: null,
  camera: null,
  renderer: null,
  controls: null,
  geoms: [],
  geometryCache: new Map(),
  materials: new Set(),
  // 地形漆装缓存：键 `${mapId}:${role}`（floor/props）。纹理画一次反复用；
  // 换场景（clearRenderGeoms）整体作废。
  terrainSurfaceCache: new Map(),
  keyLight: null,
  shadowsEnabled: false,
  shadowLowFpsSince: 0,
  shadowEverHealthy: false,
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

// A1：场景交运的**接收侧**。编辑器（advanced_sim.html 的 iframe 父页）把完整 Scenario
// 用 postMessage 送进来 —— 不再是 7 个有损 URL 参数。握手两步：
//   ① 本页就绪后向父页发 ready（父页据此重发，防"消息比页面先到"）；
//   ② 收到场景后应用，并把**应用结果**回给父页（拒收也要说清理由，不让编辑器假绿）。
window.addEventListener("message", (event) => {
  if (event.origin !== window.location.origin) return;
  const data = event.data;
  if (!data || typeof data !== "object") return;
  if (data.type === "legged-studio:ready-request") {
    // 编辑器问"你在吗"——就绪才答；未就绪时它会在 load 事件里重试
    if (sim.ready) postToParent({ type: "legged-studio:ready" });
    return;
  }
  if (data.type !== SCENARIO_MESSAGE_TYPE) return;
  const verdict = parseScenarioMessage(event);
  if (!verdict.ok) {
    sim.scenarioRun.refusedReason = verdict.reason;
    postToParent({ type: "legged-studio:scenario-applied", ok: false, reason: verdict.reason });
    return;
  }
  // 页面还没就绪（模型/策略清单未加载）就到了 ⇒ **先存着**，就绪后应用。直接应用会让
  // "策略不在清单里"这类假拒绝发生（策略下拉还没填），而用户看到的是"场景被拒"。
  if (!sim.ready) {
    sim.pendingScenario = verdict.payload;
    postToParent({ type: "legged-studio:scenario-applied", ok: true, reason: "", pending: true });
    return;
  }
  applyScenario(verdict.payload).then(
    (result) => postToParent({ type: "legged-studio:scenario-applied", ...result }),
    (error) => postToParent({
      type: "legged-studio:scenario-applied",
      ok: false,
      reason: `应用场景失败：${error?.message || String(error)}`,
    }),
  );
});

function postToParent(message) {
  if (window.parent === window) return;
  try {
    window.parent.postMessage(message, window.location.origin);
  } catch (error) {
    console.warn("[sim2sim] postMessage to parent failed", error);
  }
}

async function init() {
  try {
    initExpertBars();
    initThree();
    bindUi();
    applyViewerStateFromUrl();
    applyDeterministicReplayFromUrl();
    await loadRobotOptions();
  await initNavigationFromUrl();
    // 执行器能力矩阵（B1）：拿不到不阻塞页面（框架目录里的镜像兜底），但要在场景应用前
    // 尽力拿到——"这个指令来源到底能不能跑"由它判，不由页面里的副本判。
    try {
      const response = await fetch("/api/simulation/executors", { cache: "no-store" });
      if (response.ok) sim.executorMatrix = await response.json();
    } catch (error) {
      console.info("[sim2sim] executor matrix unavailable; using bundled mirror", error?.message || error);
    }
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
    // **但 URL 的地形参数就是那个 opt-in**：`?terrain=warehouse`（场景编辑器按
    // map_id 发）若被这里无条件覆盖成 flat，用户选的地图就静默失效——编辑器说
    // warehouse、仿真跑平地面。故 URL 优先，解析不到才回落包内 flat。
    const urlScene = resolveTerrainName(URL_TERRAIN, sim.platformConfig?.sim?.asset_package?.scenes || []);
    const initialScene = urlScene
      || sim.platformConfig?.sim?.asset_package?.scenes?.find((name) => /(^|\/)flat\.xml$/i.test(name))
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
    sim.metadataCheck = null; // 无策略即无元数据校验结果，清掉上一次的附注
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
  let metadataCheck = null;
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
    // G3「加载即校验」：下载完字节后、创建推理会话**前**扫描 metadata_props 并
    // 对照 browser-config 契约。不符 → 直接抛错拒绝加载（此前是半成品：会话照建、
    // 策略照跑，只在状态栏事后标红）。扫描失败/无盖章 ≠ 契约不符——历史/第三方
    // 导入策略（实测 34/45 条）没有盖章，按「missing」放行但如实提示，见模块头注释。
    const metaScan = scanOnnxMetadata(modelBytes);
    metadataCheck = metaScan.ok
      ? checkOnnxMetadataContract(metaScan.metadata, contractSummaryFromConfig(config))
      : {
          status: "missing",
          violations: [],
          warnings: [`ONNX 元数据扫描失败（按无章放行，等 ort 自行把关字节）：${metaScan.error}`],
          info: { jointCount: 0, source: null, jointIdsMap: null },
        };
    if (metadataCheck.status === "reject") {
      throw new Error(`策略元数据与仿真契约不符，已拒绝加载：${formatContractViolations(metadataCheck)}`);
    }
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
  // C2：场景在策略加载前到达时挂起的 A 类绑定校验，在这里判（fail-closed：不过就停）
  verifyScenarioPerceptionBinding();
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
  sim.metadataCheck = metadataCheck;
  applyPlatformLabels(config);
  const metaNote = metadataStatusNote(metadataCheck);
  setStatus(
    elements.policyStatus,
    metaNote ? `已就绪 · ${metaNote}` : `${sim.policyInfo.mode} 已就绪`,
    "ready",
  );
  if (metadataCheck?.info?.jointCount) {
    console.info(
      `[sim2sim] ✔ 策略元数据契约校验通过（${metadataCheck.info.jointCount} 关节，来源=${metadataCheck.info.source || "stamped"}）`,
    );
    // joint_ids_map：策略槽位 → 电机 ID 排列；非恒等映射时提示（浏览器按槽位直写
    // 执行器，硬件部署需要该排列，浏览器语义不受影响但值得可见）。
    const idsMap = metadataCheck.info.jointIdsMap;
    if (idsMap && !idsMap.every((v, i) => v === i)) {
      console.info(`[sim2sim] 策略携带非恒等 joint_ids_map（硬件部署用）：[${idsMap.join(",")}]`);
    }
  }
  if (previousPolicy && previousPolicy !== session) {
    try { await previousPolicy.release?.(); } catch (error) { console.warn("policy release failed", error); }
  }
  return true;
}

/** 元数据校验结果 → 状态栏附注（reject 走不到这里：加载路径已抛错拒绝）。
 * ok=无附注；missing/警告类=如实提示但不影响就绪。 */
function metadataStatusNote(check) {
  if (!check || check.status === "ok") return null;
  if (check.status === "reject") {
    return `元数据不匹配（${formatContractViolations(check)}）`;
  }
  return (check.warnings || []).filter(Boolean).join("；") || null;
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
          // 整体替换，不做 { 旧, ...新 } 合并：清单条目的契约是**每策略完整**的，
          // 稀疏条目（如 go2-baseline-164k 不声明 observation_kind）靠缺省回落到
          // 通用布局——合并会把上一个策略的 observation_kind/gait_period_s 等
          // 键残留下来（实测 handstand→baseline：numObs 已按 45 重置，builder
          // 仍按残留的 lainlab_handstand_48 校验，每帧抛错刷屏）。
          contract: { ...(selected.contract || {}) },
          // checkpoint 元数据同理：属于上一个策略的轮次不得冒充新策略（下拉
          // 标签"第 N 轮 ONNX"按此读数）。
          checkpoint: selected.checkpoint || "",
          checkpoint_iteration: selected.checkpoint_iteration ?? null,
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
    // 被拒/失败的候选策略没有有效的校验结果，清掉，别让旧结果冒充它
    sim.metadataCheck = null;
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
  // 契约级**槽表**（`onnx_slots`，见 `obs/onnx_slots.js`）：mjswan 一类**导出器命名不可依赖**
  // 的产物按**位置**绑定（名字毫无语义：`l_kwargs_policy_` / `l__args___0_module_1_1`）。
  // 声明了槽表 ⇒ 本体观测、动作、递归 in/out 全由它定，下面的名字约定不再参与（两条路径
  // 同时生效就必然有一份是错的）。
  const slots = resolveOnnxSlots(contract, inputNames, outputNames);
  const historyName = slots ? "" : (inputNames.find((n) => HISTORY_INPUT_NAMES.includes(n)) || "");
  const hasHistory = Boolean(historyName);
  // 深度输入（PIE 等）：独立的 depth_history 张量，由浏览器 raycast 渲染。
  const depthName = slots ? "" : (inputNames.find((n) => /depth/i.test(n)) || "");
  const obsName = slots
    ? slots.actorName
    : (inputNames.includes("obs")
      ? "obs"
      : inputNames.find((n) => n !== historyName && n !== depthName) || inputNames[0]);
  const actionName = slots?.actionName
    || (outputNames.includes("act")
      ? "act"
      : outputNames.includes("action")
        ? "action"
        : outputNames.includes("actions")
          ? "actions"
          : outputNames[0]);
  const weightsName = outputNames.includes("weights") ? "weights" : "";
  const estimatedVelName = outputNames.includes("estimated_vel") ? "estimated_vel" : "";
  const latentName = outputNames.includes("latent") ? "latent" : "";
  const nextHistoryName = outputNames.includes("next_history") ? "next_history" : "";
  // 递归状态：槽表声明时按**输出位置**配对（`outputs.recurrent`），名字约定配不上导出器命名
  const slotRecurrentStates = slots && slots.recurrentName ? [{
    inputName: slots.recurrentName,
    outputName: slots.recurrentOutputName,
    shape: tensorMetadataShape(session.inputMetadata, slots.recurrentName, inputNames),
    type: "float32",
    size: tensorElementCount(tensorMetadataShape(session.inputMetadata, slots.recurrentName, inputNames)),
  }] : [];
  const recurrentStates = slots
    ? slotRecurrentStates
    : inspectRecurrentStates(session, contract, inputNames, outputNames, [obsName, historyName]);
  // 命令槽宽度在这里（**只有这一处拿得到 session metadata**）读出来存进 info：喂入那段
  // `runPolicy()` 作用域里没有 session（第一版直接在那边读 `session.inputMetadata`，
  // 一跑必 ReferenceError）。
  const slotCommandShape = slots
    ? tensorMetadataShape(session.inputMetadata, slots.commandName, inputNames)
    : [];
  const slotCommandDim = Number(slotCommandShape[slotCommandShape.length - 1]) || 0;
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
    observationLayout: contract?.observation_layout || null,
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
    slots,
    slotCommandDim,
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
  // mjswan 四输入链的 `is_init`：**episode 首帧为真**（上游 OnnxModule.ts 实测 true→false），
  // 复位时挂上"待发首帧"标记，喂入那一步消费掉（`resetPolicyState` 是唯一的复位入口）。
  sim.mjswanInitPending = true;
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
      // **声明了"不可仿真"的策略一律不列出**（`simulation/config.json` 的 `sim_ready:false`）：
      // 它们的观测布局没有浏览器 builder，列出来只会让用户选到一个必然吃错观测的策略
      // （症状是"跑得起来但动作很怪"，看不出原因）。原因在条目的 `sim_blocker` 里，
      // 覆盖守卫见 backend/test_policy_obs_builders_cover_kinds.py。
      if (item.sim_ready === false) return false;
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
  // 关节槽序变了就必须重建 qpos/dof/执行器地址表：这三张表按 CONFIG.jointOrder 的
  // **名字**解析模型地址，却原来只在加载 MuJoCo 模型时建一次。切换策略时若新旧契约
  // 的关节序不同（默认 per-leg 序 ↔ LeggedSkillDeploy 的 type-major 序），不重建就会
  // 拿旧序的地址配新序的默认角/观测/动作——复位把髋角写进大腿槽、后腿髋被设到
  // ±1.5 rad（"伸出来一条腿然后马上死"），观测与动作也全部错位。模型未就绪时（首屏
  // 契约先于模型应用）跳过，模型加载流程自己会建。
  if (sim.model) {
    resolveJointAddresses();
    resolveActuatorAddresses();
  }
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
  const policyKps = normalizeNameMap(contract?.control?.stiffness);
  const policyKds = normalizeNameMap(contract?.control?.damping);
  // normalizeNameMap 返回普通对象（非 Map），读 .size 恒为 undefined——曾因此
  // 静默跳过整个 per-policy PD 覆盖。
  //
  // 覆盖【只对 torque 接口生效】，两条理由都由实测得出：
  //  - torque：CONFIG.kps/kds 就是应用每步下发的 PD 律，必须与训练一致。
  //    go2-backflip-69 训练 40/1，沿用包级 20/0.5 起跳发力不足，后空翻只翻到
  //    ~180° 就背部着地。全量扫描里 torque 接口仅此一个策略与包级不同。
  //  - position_target：PD 属于模型，后端按 contract_truth.actuator_profile 重建原生
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
  // 声明式观测布局（契约 observation_layout）：有它就走**与验收器同一份规格**的解释器。
  CONFIG.observationLayout = contract?.observation_layout || null;
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
  const roleScales = control?.action_scale_by_role || {};
  const jointScales = normalizeNameMap(control?.action_scale_by_joint || contract?.action_scale_by_joint);
  const defaultPositionScale = finiteNumber(contract?.action_scale, finiteNumber(control?.action_scale, CONFIG.actionScale));
  const defaultVelocityScale = finiteNumber(
    contract?.control?.velocity_scale,
    finiteNumber(control?.velocity_scale, 20),
  );

  // 角色/模式解析走 `obs/actuator_modes.js`（**单一真值**，对拍工具调同一个函数）：
  // 这里只负责把输入摆出来（策略契约 + 机器人 control）与消费结果（缩放表）。
  const names = Array.from(
    { length: CONFIG.numActions },
    (_, index) => String(order[index] || CONFIG.jointOrder[index] || ""),
  );
  const { roles, modes } = resolveActuatorRolesAndModes({
    actionDim: CONFIG.numActions,
    jointOrder: names,
    jointGroup,
    contractRoles: contract?.actuator_roles,
    contractModes: contract?.control_modes,
    robotModes: control?.control_modes,
  });

  for (let i = 0; i < CONFIG.numActions; i += 1) {
    const name = names[i].toLowerCase();
    const role = roles[i];
    CONFIG.actuatorRoles[i] = role;
    CONFIG.controlModes[i] = modes[i];
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

// `normalizeNameMap` / `jointGroup` 已抽到 `obs/actuator_modes.js`（**单一真值**，
// 对拍工具与浏览器共用）——见文件头 import 与 `applyActuatorContract` 的说明。

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

// `jointGroup` 见 `obs/actuator_modes.js`（与对拍工具共用同一份）。

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
  const normalized = normalizeNameMap(limits);
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
  const normalized = normalizeNameMap(envelopes);
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
  // G5「地形与扰动归组」：按 category 用 <optgroup> 归组渲染。
  // terrain entries（包声明 terrains + 公共地图库）带 id/label/path ——
  // 有 category 用 category，没有的按 id 落到内置分类快照；未知的 fail-closed 进「其他」组。
  const terrainEntries = scenes.map((sceneName) => {
    const manifestEntry = terrainOptions.find((item) => item?.path === sceneName);
    return {
      id: manifestEntry?.id || sceneBasename(sceneName).replace(/\.xml$/i, "").replace(/^scene_/, "").toLowerCase(),
      label: manifestEntry?.label || terrainLabel(sceneName),
      path: sceneName,
    };
  });
  const terrainGroups = groupTerrains(terrainEntries);
  for (const group of terrainGroups) {
    // 每组一个 <optgroup>（含「其他」兜底组——未分类/未知 category 的地图落这里，绝不消失）。
    const optgroup = document.createElement("optgroup");
    optgroup.label = group.label;
    group.items.forEach((item) => optgroup.append(buildTerrainOption(item)));
    elements.terrainSelect.append(optgroup);
  }
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

function buildTerrainOption(item) {
  const option = document.createElement("option");
  option.value = item.path;
  option.textContent = item.label;
  return option;
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

/** 「光影」开关 → renderer/keyLight。three 的 shadowMap.enabled 运行期切换必须
 *  让现存材质重编译（needsUpdate），否则现场不刷新——这是 three 的坑，不是可选优化。 */
function applyShadowSetting() {
  const on = elements.shadowToggle ? Boolean(elements.shadowToggle.checked) : false;
  view.shadowsEnabled = on;
  view.shadowLowFpsSince = 0;
  // 见过一次健康帧率才允许看门狗动作：加载期（编译场景/着色器）必然有低帧率窗口，
  // 不设这道武装门槛就会在页面刚打开时误关光影（2026-09-22 实测踩中）。
  view.shadowEverHealthy = false;
  if (!view.renderer || !view.keyLight) return;
  view.renderer.shadowMap.enabled = on;
  view.keyLight.castShadow = on;
  for (const material of view.materials) material.needsUpdate = true;
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
  // 光影默认跟随「光影」勾选框（applyShadowSetting）：PCFSoft + 1024 阴影图对集成
  // 显卡也便宜，但帧率守不住 40 会自动关（updatePerf 的看门狗）——性能优先。
  view.renderer.shadowMap.enabled = false;
  view.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
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

  // 主光（阴影投手）：目标物每帧跟随机器人（syncVisualScene），阴影相机罩住
  // 机周 ±7 m；target 必须 add 进 scene，否则它的 matrixWorld 不更新、阴影框不动。
  const key = new THREE.DirectionalLight(0xffffff, 2.6);
  key.position.set(-3.2, -4.2, 7.5);
  key.castShadow = false;
  key.shadow.mapSize.set(1024, 1024);
  key.shadow.camera.left = -7;
  key.shadow.camera.right = 7;
  key.shadow.camera.top = 7;
  key.shadow.camera.bottom = -7;
  key.shadow.camera.near = 0.5;
  key.shadow.camera.far = 30;
  key.shadow.bias = -0.0006;
  view.scene.add(key);
  view.scene.add(key.target);
  view.keyLight = key;
  applyShadowSetting();

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
  elements.shadowToggle?.addEventListener("change", applyShadowSetting);
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
    // 先记地形名再置 ready：首帧 syncVisualScene 就会建地形材质并缓存，
    // ready 之后再赋值会让第一份缓存落成兜底漆装（2026-09-22 实测踩中）。
    sim.currentTerrain = xmlName;
    initializePayloadMass();

    resetSimulation();
    frameCameraToModel();
    sim.paused = VIEWER_ONLY;
    elements.playButton.textContent = sim.paused ? "继续" : "暂停";
    sim.ready = true;
    setStatus(elements.engineStatus, "MuJoCo 已就绪", "ready");
    elements.loading.classList.add("is-hidden");
    // A1 握手：告诉父页（场景编辑器）"我可以收场景了"——它可能在页面就绪前就发过消息。
    postToParent({ type: "legged-studio:ready" });
    // 就绪前到达的场景在此应用（缓冲见 message handler）
    if (sim.pendingScenario) {
      const payload = sim.pendingScenario;
      sim.pendingScenario = null;
      applyScenario(payload).then(
        (result) => postToParent({ type: "legged-studio:scenario-applied", ...result }),
        (error) => postToParent({
          type: "legged-studio:scenario-applied",
          ok: false,
          reason: `应用场景失败：${error?.message || String(error)}`,
        }),
      );
    }
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
  // mjswan 四输入链（`go2_mjswan_velocity`）的 actor 帧缓冲：**复位后必须重新 prime**
  // （首帧填满每一槽），否则下一段会把上一段的帧当历史——上游 `HistoryObservation.needsPrime`
  // 同口径；`sim.history` 那份共享缓冲管不到它（那是另一种 layout）。
  sim.mjswanActorFrames = null;
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
  // 场景运行随之**重新开始**（R 键/重置按钮都走这里）：旧轨迹与旧摘要不作数——
  // 留着会让"上一趟的判据结论"冒充这一趟的。
  if (sim.scenarioRun.active && sim.scenario) {
    sim.scenarioRun.trace = [];
    sim.scenarioRun.summary = null;
    renderScenarioPanel();
  }
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
    try {
      syncVisualScene();
      updateFollowCamera();
      updateDragArrow();
      updateTrail();
      updateHud(false);
    } catch (error) {
      // HUD/可视化段的单帧异常（如 WASM 堆扩容瞬间视图 detach）只丢帧——
      // 异常绝不能逃出 frame()：requestAnimationFrame 在函数末尾，逃逸即整循环卡死
      // （2026-09-21 实测：detached ArrayBuffer 抛在 buildDebugState，画面/HUD 全冻结）。
      view.frameErrorCount = (view.frameErrorCount || 0) + 1;
      console.warn(`[sim2sim] hud error #${view.frameErrorCount}`, error);
    }
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

// ── Isaac 风格 3D 传感器可视化层 ────────────────────────────────────────────
// 高度扫描 → 187 彩球、LiDAR → 距离点云、足底接触 → 半透明球、IMU → 坐标轴。
// 数据侧在 sensor_visual.js（纯色映射），本节只做 THREE 对象的创建/更新/可见性。
// 层的开关**跟随坞里的插件勾选**（勾高度 → 场景里出彩球）——同一个开关管两处视图，
// 不另设第二份开关（两份必然漂移）。射线类扫描与坞同用 10 Hz 节流：这是"开雷达就卡"
// 的教训（updateSensorPanels 处有完整注释），3D 层不重新犯一遍。
function ensureSensorViz() {
  if (!view.scene) return;
  const viz = sim.sensorViz;
  if (!viz.heightScan) {
    viz.heightScan = createHeightScanLayer(187);
    view.scene.add(viz.heightScan);
  }
  if (!viz.lidarScan) {
    viz.lidarScan = createLidarLayer(240);
    view.scene.add(viz.lidarScan);
  }
  if (!viz.contact) {
    const contact = createContactLayer(["FL", "FR", "RL", "RR"]);
    viz.contact = contact;
    view.scene.add(contact.group);
  }
  if (!viz.imuAxes) {
    viz.imuAxes = createImuAxes(0.09);
    view.scene.add(viz.imuAxes);
  }
  if (!viz.rangefinder) {
    viz.rangefinder = createRangefinderLayer();
    view.scene.add(viz.rangefinder.group);
  }
}

/** 层可见性 ⇆ 坞插件勾选（每帧对齐，省一套事件接线）。 */
function syncSensorVizVisibility(viz) {
  const on = (id) => Boolean(dock.plugins && dock.plugins[id]);
  viz.heightScan.visible = on("height");
  viz.lidarScan.visible = on("lidar");
  if (viz.contact) viz.contact.group.visible = on("foot_contact");
  if (viz.imuAxes) viz.imuAxes.visible = on("imu");
  if (viz.rangefinder) viz.rangefinder.group.visible = on("rangefinder");
}

/** 更新 3D 传感器可视化层：高度彩球、LiDAR 点云、足底接触球、IMU 轴。
 *
 *  每帧从 updateHud 调；射线扫描（187/240 条）按 DOCK_SCAN_INTERVAL_MS 节流后缓存，
 *  读数组/摆位姿的部分逐帧（便宜）。不可见的层直接跳过——visible=false 不进 GPU 管线。
 */
function updateSensorViz() {
  const viz = sim.sensorViz;
  if (!viz.heightScan || !sim.qpos) return;
  syncSensorVizVisibility(viz);
  const basePos = [sim.qpos[0], sim.qpos[1], sim.qpos[2]];
  const baseQuat = [sim.qpos[3], sim.qpos[4], sim.qpos[5], sim.qpos[6]];

  // 高度扫描彩球：画在**真实命中点**（scanHeightField 的射线交点），颜色按地形
  // 世界高度彩虹映射——与坞里 height 来源同一条数据（cachedScan 共享缓存），必然一致。
  if (viz.heightScan.visible) {
    const scan = cachedScan("height", (bp, bq) => scanHeightField(bp, bq, sensorMount("height", sensorMountOverrides)));
    const colors = heightPointColors(scan.world);
    const positions = new Float32Array(scan.total * 3);
    const colorArr = new Float32Array(scan.total * 3);
    const points = scan.points || [];
    for (let i = 0; i < scan.total; i += 1) {
      const p = points[i];
      if (p) {
        positions[i * 3] = p[0]; positions[i * 3 + 1] = p[1]; positions[i * 3 + 2] = p[2];
        colorArr[i * 3] = colors[i * 3]; colorArr[i * 3 + 1] = colors[i * 3 + 1]; colorArr[i * 3 + 2] = colors[i * 3 + 2];
      } else {
        positions[i * 3 + 2] = -999; // 未命中：藏远处 + 黑（同坞里黑槽口径）
      }
    }
    updatePointsLayer(viz.heightScan, positions, colorArr);
  }

  // LiDAR 点云：真实射线的命中点（origin + dir·distance）+ 距离着色（近绿远红，
  // miss/超量程黑）——与坞里 lidar 来源同一份缓存扫描。
  if (viz.lidarScan.visible) {
    const scan = cachedScan("lidar", (bp, bq) => scanLidar(bp, bq, sensorMount("lidar", sensorMountOverrides)));
    const colors = distancePointColors(scan.distances, scan.maxDist);
    const positions = new Float32Array(scan.count * 3);
    const colorArr = new Float32Array(scan.count * 3);
    for (let i = 0; i < scan.count; i += 1) {
      const d = scan.distances[i];
      const dir = scan.worldDirs[i];
      if (dir && d >= 0 && d <= scan.maxDist) {
        positions[i * 3] = scan.origin[0] + dir[0] * d;
        positions[i * 3 + 1] = scan.origin[1] + dir[1] * d;
        positions[i * 3 + 2] = scan.origin[2] + dir[2] * d;
        colorArr[i * 3] = colors[i * 3]; colorArr[i * 3 + 1] = colors[i * 3 + 1]; colorArr[i * 3 + 2] = colors[i * 3 + 2];
      } else {
        positions[i * 3 + 2] = -999;
      }
    }
    updatePointsLayer(viz.lidarScan, positions, colorArr);
  }

  // 单点测距特效：装配方向射线 + 命中点标记（命中亮黄线+黄球 / 未命中暗灰线到量程上限）
  // ——此前这个传感器只有读数没有 3D 特效（2026-09-22 用户反馈补齐）。
  if (viz.rangefinder && viz.rangefinder.group.visible) {
    const mount = sensorMount("rangefinder", sensorMountOverrides);
    const dirQuat = quatMul(baseQuat, quatFromRpy(mount.rpy.map(deg2rad)));
    const origin = mountOriginWorld(basePos, baseQuat, mount.pos);
    const dir = quatRot(dirQuat, [0, 0, -1]);
    const RANGE_MAX = 20;
    const hit = cachedScan("rangefinder", () => intersectSceneRay(sim.model, sim.data, origin, dir, { maxDist: RANGE_MAX }));
    const end = hit >= 0 ? hit : RANGE_MAX;
    const pos = viz.rangefinder.line.geometry.getAttribute("position");
    pos.setXYZ(0, origin[0], origin[1], origin[2]);
    pos.setXYZ(1, origin[0] + dir[0] * end, origin[1] + dir[1] * end, origin[2] + dir[2] * end);
    pos.needsUpdate = true;
    viz.rangefinder.line.material.color.setHex(hit >= 0 ? 0xffd23f : 0x5a6470);
    viz.rangefinder.marker.visible = hit >= 0;
    if (hit >= 0) {
      viz.rangefinder.marker.position.set(origin[0] + dir[0] * hit, origin[1] + dir[1] * hit, origin[2] + dir[2] * hit);
    }
  }

  // 足底接触球：只在**实际接触**时显示，画在命中 geom 的世界位（两种模型布局都真：
  // 平台包的足球叫 FL/…，bundle 里足球无名——都从接触表反查，不靠猜名字）。
  if (viz.contact && viz.contact.group.visible && sim.data) {
    const scan = scanFootContacts();
    const states = contactVisualStates(scan.feet);
    for (const st of states) {
      const mesh = viz.contact.spheres.get(st.name);
      if (!mesh) continue;
      const foot = scan.feet.find((f) => f.name === st.name);
      if (!st.grounded || !foot || !(foot.geomId >= 0) || !sim.data.geom_xpos) {
        mesh.visible = false;
        continue;
      }
      const o = foot.geomId * 3;
      mesh.position.set(sim.data.geom_xpos[o], sim.data.geom_xpos[o + 1], sim.data.geom_xpos[o + 2]);
      mesh.material.color.setRGB(st.color[0], st.color[1], st.color[2]);
      mesh.visible = true;
    }
  }

  // IMU 轴：跟随装配位（红=x 绿=y 蓝=z）
  if (viz.imuAxes && viz.imuAxes.visible) {
    const mount = sensorMount("imu", {});
    const imuOrigin = mountOriginWorld(basePos, baseQuat, mount.pos);
    const imuQuat = quatMul(baseQuat, quatFromRpy(mount.rpy.map(deg2rad)));
    viz.imuAxes.position.set(imuOrigin[0], imuOrigin[1], imuOrigin[2]);
    viz.imuAxes.quaternion.set(imuQuat[1], imuQuat[2], imuQuat[3], imuQuat[0]);
  }
}

/** 场景运行采样（A1）：每个**控制步**记一点；到 `episode_length_s` 就收打出摘要。 */
function sampleScenarioRun() {
  const run = sim.scenarioRun;
  if (!run.active || !sim.scenario || !sim.qpos) return;
  const pose = poseFromQpos(sim.qpos);
  const quat = [sim.qpos[3], sim.qpos[4], sim.qpos[5], sim.qpos[6]];
  const rpy = quatToRpy(quat);
  const fallen = sim.qpos[2] < 0.12 || Math.abs(rpy[0]) > 1.2 || Math.abs(rpy[1]) > 1.2;
  run.trace.push(tracePoint({
    t: sim.data?.time ?? 0,
    x: pose.x,
    y: pose.y,
    yawDeg: (pose.yaw ?? 0) * 180 / Math.PI,
    rollDeg: rpy[0] * 180 / Math.PI,
    pitchDeg: rpy[1] * 180 / Math.PI,
    vx: sim.cmd[0] ?? 0,
    vy: sim.cmd[1] ?? 0,
    wz: sim.cmd[2] ?? 0,
    fallen,
  }));
  if (run.trace.length % 50 === 0) renderScenarioPanel();
  if (run.deadlineS !== null && (sim.data?.time ?? 0) >= run.deadlineS) {
    sim.paused = true;
    elements.playButton.textContent = "继续";
    finishScenarioRun(`到达场景时长上限 ${run.deadlineS}s`);
  }
}

/** WASM 堆扩容后，旧的 TypedArray 视图会变 detached（%TypedArray%.prototype.values
 *  抛 "detached or out-of-bounds ArrayBuffer"，2026-09-21 跑 83s 实测踩中）。`data.qpos`
 *  这类 getter 每次访问都从**当前**堆重新包视图——所以每帧重取，不缓存。 */
function refreshDataViews() {
  if (!sim.data) return;
  try {
    sim.qpos = sim.data.qpos;
    sim.qvel = sim.data.qvel;
    sim.ctrl = sim.data.ctrl;
  } catch (_) { /* 堆重分配竞态：丢一帧读数，下一帧自然恢复 */ }
}

async function stepSimulation() {
  refreshDataViews();
  ensureSensorViz();
  updateCommand();
  if (sim.counter % CONFIG.controlDecimation === 0) {
    activatePendingJumpCommand();
    await runPolicy();
    OBSERVATION.advanceWheelLegGaitClock();
    sampleScenarioRun();
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
  if (info.slots) {
    // 命令槽（`command_`）：`velocity_cmd(3) × cmd_scale` + 其余**零占位**（oscillator 槽，
    // 上游 `velocity_command_padding` 就是 zeros(13)）。宽度在 `inspectPolicy` 里读好存进
    // `info.slotCommandDim`（这里没有 session 可读）。
    const cmdDim = Number(info.slotCommandDim) || 0;
    if (cmdDim >= 3) {
      const cmdVec = new Float32Array(cmdDim);
      for (let i = 0; i < 3; i += 1) cmdVec[i] = sim.cmd[i] * (CONFIG.cmdScale?.[i] ?? 1);
      feeds[info.slots.commandName] = new ort.Tensor("float32", cmdVec, [1, cmdDim]);
    }
    // `is_init`：**episode 首帧为真**（上游 `OnnxModule.ts` 实测 true→其后 false）。必须是
    // **rank-1 的 bool**：上游张量是 `[1]`，喂 `[[..]]` 会被 onnxruntime 判 `Invalid rank`
    // （Python 侧踩过同一个坑）。
    if (info.slots.isInitName) {
      const first = sim.mjswanInitPending === true;
      sim.mjswanInitPending = false;
      feeds[info.slots.isInitName] = new ort.Tensor("bool", Uint8Array.from([first ? 1 : 0]), [1]);
    }
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
    // H3 导航到达判据暴露（?debug=1）：E2E 实测需要轮询 arrival 状态（finished /
    // reached / stable_count 等），buildDebugState 快照太大且不含 navigation。
    navigation() {
      if (!sim.navigation) return null;
      return {
        mapId: sim.navigation.mapId,
        payload: sim.navigation.payload
          ? {
              waypoints: sim.navigation.payload.waypoints,
              arrival: sim.navigation.payload.arrival,
              follow_controller: sim.navigation.payload.follow_controller,
            }
          : null,
        status: sim.navigation.status ? { ...sim.navigation.status } : null,
      };
    },
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
        // H12/E2E 观测：策略会话是否真的加载完（policyEnabled 只是开关，
        // 加载没完成时 runPolicy 走 holdStance——机器人站桩不动）。
        policyLoaded: Boolean(sim.policy && sim.policyInfo),
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
  // 状态 → 机体系 IMU 读数**只写一处**（`utils.js::imuSampleFromQpos`），口径与验收器
  // `policy_acceptance.py::ObsBuilder.base_state` 逐条一致：**角速度不转、线速度转**。
  //
  // 这里曾经自己实现，并且把**两段都乘了 Rᵀ**：自由关节的 `qvel[3:6]` 本来就是机体系角速度，
  // 再转一次等于双重旋转——yaw≈0 时 R≈I 所以完全看不出来（策略照走，"看着没事"了很久），
  // yaw→180° 时水平两轴翻号（Rᵀ·ω = (−ωx,−ωy,ωz)）⇒ 角速度反馈变成**正反馈** ⇒ 机器人
  // 直接乱动失衡（用户报的"转到 180° 左右必然抽风"，2026-09-22 用浏览器同款 WASM 复核后修）。
  //
  // 那段 `cvel` 分支一并删掉：守卫写的是 `sim.model?.cvel`，而 **cvel 属 MjData** ⇒ 条件恒假、
  // 分支**从未执行**（Node 里加载 `vendor/mujoco/mujoco.js` 实测：`model.cvel === undefined`，
  // 而 `data.cvel` 确实存在、是平铺 `Float64Array(18)`）。它本身口径是对的（世界系角速度再
  // Rᵀ），但"看着有两条路、实际永远走另一条"正是这类缺陷最容易藏身的地方——留一条永远不跑
  // 的正确实现，比删掉它更危险。
  return imuSampleFromQpos(sim.qpos, sim.qvel);
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
  const sample = sim.imuSamples[sim.imuSamples.length - 1 - input.imuDelaySampleSteps]
    || captureImuSample();
  // 退化模型只作用在**读数出口**（观测构造与坞的显示同源），且默认关——见 sim.sensorNoise。
  return applyImuNoise(sim.sensorNoise, sample) || sample;
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
  // LainLab 技能族（dreamwaq/amp-cts 270、trot/jump/spring 470）：整帧依时序拼接、
  // **最旧在前、当前帧在最后** —— ONNX 图实测（dreamwaq 首个 Slice 为 [0:-45]：
  // encoder 吃前 225=5 帧历史，actor MLP 吃末 45=当前帧）。与 frame_major_v1（最新在前）相反。
  if (CONFIG.historyLayout === "frame_major_oldest_first") {
    const packed = new Float32Array(frames.length * CONFIG.numObs);
    let cursor = 0;
    for (const frame of frames) {
      packed.set(frame, cursor);
      cursor += CONFIG.numObs;
    }
    return packed;
  }
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
  // 阴影相机的目标跟随机器人：光照方向不变，只是整框平移到机周——
  // 否则机器人一走远就出阴影相机的覆盖范围，影子整片消失。
  if (view.keyLight && sim.qpos) {
    view.keyLight.position.set(sim.qpos[0] - 3.2, sim.qpos[1] - 4.2, sim.qpos[2] + 7.5);
    view.keyLight.target.position.set(sim.qpos[0], sim.qpos[1], sim.qpos[2]);
    view.keyLight.target.updateMatrixWorld();
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

function currentMapId() {
  // "maps/flat.xml" / "flat.xml" → "flat"；未知地形（Default scene 等）落兜底漆装。
  return String(sim.currentTerrain || "").split("/").pop().replace(/\.xml$/i, "");
}

/** 地面/地形件材质（按地图漆装，替代原全地形一个硬编码色）。
 *
 *  plane 地面吃 `floor` 贴图（CanvasTexture，repeat 按 90 m 平面 / cell 换算，
 *  纹素密度与地图无关）；名字带 floor/ground 的板式地面（如 apartment 的
 *  floor_* 拼板）吃底色素面；其余地形件（台阶/货箱/墙）吃 `props` 素色。
 *  材质按 `${mapId}:${role}` 缓存——同一场景几十个 geom 共享一份。
 */
function makeTerrainMaterial(info) {
  const mapId = currentMapId();
  const kit = resolveTerrainKit(mapId);
  const isFloorPlane = info.type === sim.geomType.plane;
  const isFloorSlab = !isFloorPlane && /floor|ground/.test(geomName(info.objid).toLowerCase());
  const role = isFloorPlane ? "floor" : (isFloorSlab ? "floor-slab" : "props");
  const cacheKey = `${mapId}:${role}`;
  const cached = view.terrainSurfaceCache.get(cacheKey);
  if (cached) return cached;

  let material;
  if (role === "floor") {
    const S = 512;
    const canvas = document.createElement("canvas");
    canvas.width = S;
    canvas.height = S;
    const ctx = canvas.getContext("2d");
    paintFloorTile(ctx, S, kit.floor);
    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;
    // 平面几何固定 90×90 m（getGeometry），repeat 让一个贴片正好覆盖 cell 米。
    const repeat = 90 / (kit.floor.cell || 1);
    texture.repeat.set(repeat, repeat);
    texture.anisotropy = Math.min(4, view.renderer?.capabilities?.getMaxAnisotropy?.() || 1);
    material = new THREE.MeshStandardMaterial({
      map: texture,
      roughness: 0.92,
      metalness: 0.0,
      side: THREE.DoubleSide,
    });
  } else {
    const spec = role === "floor-slab"
      ? { color: resolveTerrainKit(mapId).floor.base || "#7f878e", roughness: 0.9, metalness: 0.02 }
      : kit.props;
    material = new THREE.MeshStandardMaterial({
      color: new THREE.Color(spec.color),
      roughness: spec.roughness ?? 0.88,
      metalness: spec.metalness ?? 0.02,
      side: THREE.DoubleSide,
    });
  }
  view.terrainSurfaceCache.set(cacheKey, material);
  return material;
}

function makeMaterial(info) {
  const rgba = info.rgba;
  const kind = classifyGeom(info);
  if (kind === "terrain") return makeTerrainMaterial(info);
  const material = new THREE.MeshStandardMaterial({
    color: new THREE.Color(rgba[0], rgba[1], rgba[2]),
    roughness: kind === "visual" ? 0.52 : 0.84,
    metalness: kind === "visual" ? 0.18 : 0.02,
    transparent: rgba[3] < 0.98 || kind === "collision",
    opacity: rgba[3] * (kind === "collision" ? 0.28 : 1),
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

// geom 名查表缓存：`mj_id2name` 每次调用都从 WASM 堆分配新字符串——接触扫描逐帧调用
// 就是逐帧分配，堆被顶到扩容，旧 TypedArray 视图随之 detach（2026-09-21 实测的崩溃根源）。
// 名字在模型生命周期内不变，按 geomId 缓存；换模型（sim.model 引用变化）整体失效。
const _geomNameCache = { model: null, names: new Map(), bodies: new Map() };
function geomNameCache() {
  if (_geomNameCache.model !== sim.model) {
    _geomNameCache.model = sim.model;
    _geomNameCache.names.clear();
    _geomNameCache.bodies.clear();
  }
  return _geomNameCache;
}

function geomName(geomId) {
  if (!sim.model || geomId == null || geomId < 0) return "";
  const cache = geomNameCache();
  if (cache.names.has(geomId)) return cache.names.get(geomId);
  let name = "";
  try {
    if (typeof sim.model.geom === "function") name = sim.model.geom(geomId)?.name || "";
  } catch (_) { /* use the C API below */ }
  if (!name) {
    try {
      name = sim.mujoco.mj_id2name(sim.model, sim.objGeom, geomId) || "";
    } catch (_) {
      name = "";
    }
  }
  cache.names.set(geomId, name);
  return name;
}

/** geom → **身体**名（`mjOBJ_BODY === 1`）。足底碰撞 geom 在浏览器 bundle 里**无名**
 *  （`web/sim2sim/assets/go2/go2.xml` 只给 base 三块命了名），但承载它的身体叫
 *  `FL_calf`/`FR_calf`/… —— 所以接触归属按**身体**做，这也正是训练栈
 *  `mjlab/sensor/contact_sensor.py` 的做法（它按名字把 primary 元素解析成一组再逐项取）。
 */
function geomBodyName(geomId) {
  if (!sim.model || !Number.isInteger(geomId) || geomId < 0) return "";
  const cache = geomNameCache();
  if (cache.bodies.has(geomId)) return cache.bodies.get(geomId);
  let name = "";
  try {
    const bodyId = Number(sim.model.geom_bodyid[geomId]);
    name = sim.mujoco.mj_id2name(sim.model, 1, bodyId) || `body${bodyId}`;
  } catch (_) {
    name = "";
  }
  cache.bodies.set(geomId, name);
  return name;
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
  refreshDataViews();

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
  updateSensorViz();
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
 *  返回行优先的一维数组，未命中的格子给 `null`（绘制时会画成空槽）。
 *  **pattern 参数取自传感器框架目录**（`sensors/sensor_catalog.js` 的 height 条目，
 *  与训练栈 mjlab GridPatternCfg 同语义）——不再在这里写死 24×24。 */
function scanHeightField(basePos, baseQuat, mount) {
  // 网格契约取自框架目录（187 = 17×11，x 主序，与 backend/height_scan.py 逐值一致）——
  // A 类感知绑定认的是这一份；坞里此前的 24×24 只是"画着好看"，与契约不同格。
  // SCAN_SPECS.height 只在目录缺失时兜底。
  const spec = SCAN_SPECS.height;
  const grid = patternParams("height")?.grid || {};
  const pattern = buildPattern("grid", patternParams("height")) || gridOffsets(spec.side, spec.extent);
  const offsets = pattern.offsets || [];
  const side = grid.nx ? grid.ny : (pattern.count ? Math.round(Math.sqrt(pattern.count)) : spec.side);
  const mountQuat = quatFromRpy(mount.rpy.map(deg2rad));
  const [down] = mountRayDirections(baseQuat, mountQuat, [[0, 0, -1]]);
  const anchor = mountOriginWorld(basePos, baseQuat, mount.pos);
  // 网格偏移是**机体系**的，必须跟着机身转 —— 否则机器人一转身，扫描格子还朝着原来的方向。
  const origins = offsets.map(([ox, oy]) => {
    const shift = quatRot(baseQuat, [ox, oy, 0]);
    return [anchor[0] + shift[0], anchor[1] + shift[1], anchor[2] + shift[2]];
  });
  const distances = intersectSceneRays(
    sim.model, sim.data, origins, origins.map(() => down), { maxDist: spec.maxDist, worldBodyOnly: true },
  );
  // 两个值都留：`field` 是**契约值** base_z − terrain_z（A 类观测要的那个，未缩放），
  // `world` 是地形世界高度（绘制用——彩色图看绝对高度更直观）。**不能直接取起点 z**：
  // 装配角一旦不是正朝下，那样算出来整个场都是等高，斜面扫描就成了一张纯色图。
  const terrain = distances.map((d, i) => (d < 0 ? null : origins[i][2] + down[2] * d));
  const field = terrain.map((h) => (h === null ? null : basePos[2] - h));
  // 命中点的**世界坐标**：3D 彩球层直接画在这（Isaac 风格）——坞图与 3D 层同一条扫描，
  // 两视图不会各画各的。
  const points = distances.map((d, i) => (d < 0 ? null : [
    origins[i][0] + down[0] * d, origins[i][1] + down[1] * d, origins[i][2] + down[2] * d,
  ]));
  return { field, world: terrain, points, side, hits: distances.filter((d) => d >= 0).length, total: distances.length };
}

/** LiDAR：同一原点的整圈扇扫。命中点留给点云复用 —— **两图同源才对得齐**。
 *  pattern 参数同样取自框架目录（lidar 条目；fan pattern = mjlab RingPattern 的半径 0 退化）。 */
function scanLidar(basePos, baseQuat, mount) {
  const spec = SCAN_SPECS.lidar;
  const legacy = fanDirections(spec.count);
  // 框架 pattern 的字段名是 **offsets/directions/angles/count**（对标 mjlab 的
  // (local_offsets, local_directions)），与旧 `fanDirections` 返回的 `dirs` **不同名**——
  // 照旧名读会得到 undefined ⇒ 空射线数组 ⇒ "全 miss"而不报错（本框架接线第一版就这么
  // 错的，被 Node 形状契约测试钉住）。
  const fan = buildPattern("fan", patternParams("lidar"))
    || { offsets: legacy.offsets, directions: legacy.dirs, angles: legacy.angles, count: legacy.count };
  const dirs = fan.directions || [];
  const angles = fan.angles || [];
  const count = fan.count || spec.count;
  const mountQuat = quatFromRpy(mount.rpy.map(deg2rad));
  const origin = mountOriginWorld(basePos, baseQuat, mount.pos);
  const worldDirs = mountRayDirections(baseQuat, mountQuat, dirs);
  const distances = intersectSceneRays(
    sim.model, sim.data, worldDirs.map(() => origin), worldDirs, { maxDist: spec.maxDist },
  );
  return { angles, distances, worldDirs, origin, count, maxDist: spec.maxDist };
}

/** 射线扫描**共享缓存**：坞面板与 3D 叠加层同吃一份（此前各缓存各的——同帧最多
 *  把同一扫描算三遍，"雷达（LiDAR）类来源还是很卡"的另一半根源，2026-09-22）。
 *  100 ms 节流；谁先要谁触发重扫，另一个直接吃缓存。 */
function cachedScan(kind, compute) {
  if (!sim.scanCache) sim.scanCache = {};
  const now = performance.now();
  const entry = sim.scanCache[kind];
  if (entry && now - entry.ms < DOCK_SCAN_INTERVAL_MS) return entry.scan;
  const basePos = [sim.qpos[0], sim.qpos[1], sim.qpos[2]];
  const baseQuat = [sim.qpos[3], sim.qpos[4], sim.qpos[5], sim.qpos[6]];
  const scan = compute(basePos, baseQuat);
  sim.scanCache[kind] = { ms: now, scan };
  return scan;
}

/** 外挂深度预览：20×12 粗针孔网格（策略没吃深度也能"看"——深度相机本就是外挂件，
 *  此前坞里只会写"当前策略无深度输入"，2026-09-22 用户指正）。宽高比与视场对齐目录
 *  的 pinhole 参数，画布上放大显示（预览给人看，不必喂策略的 106×60）。
 *
 *  **朝向与 RGB 预览同源**（`sensors/screen_frame.js`）：装配 rpy 只定"往哪看"，
 *  图像右/上由 `cameraBasis(光轴)` 从**光轴 + 世界上方向**构造出来。此前这里把
 *  `mountQuat` 直接当基架用，而前视相机的 rpy `[0,-80,0]` 自带 90° 滚转 ⇒ 预览里的
 *  地平线是**竖的**（用户报的"深度图被旋转过"，2026-09-22 修；同一坑 RGB 预览此前
 *  已用 lookAt 构造绕过）。 */
function scanDepthPreview(basePos, baseQuat, mount) {
  const params = patternParams("depth") || {};
  // **相机规格：场景声明优先，传感器目录兜底**（2026-09-23 修）。
  //
  // 此前这里把分辨率写死 `20×12`、把归一化距离写死 `8 m`，于是坞里那张"深度图"：
  //   ① 分辨率与声明/目录里的相机（默认 106×60）**不是同一台**——用户看到的是粗格图，
  //      与策略/训练侧口径无关，第一眼就是"深度相机不对"；
  //   ② 距离刻度用的是 8 m，而场景声明的是 `cutoff_m`（默认 3 m）⇒ 同一面墙在预览里
  //      "才走了一半"，在策略口径里已接近截止 —— 亮度含义两套；
  //   ③ 标签还写死"20×12 粗格"，与它自己画的数据（数据源早已按声明走）**互相矛盾**。
  // 现在三者同源：分辨率与截止距离都取 `sim.scenario.perception.depth_camera`
  // （缺项回落到目录默认），标签按实际尺寸渲染。
  const declared = sim.scenario?.perception?.depth_camera;
  const spec = declared && typeof declared === "object" ? declared : {};
  const clampInt = (value, lo, hi, fallback) => {
    const n = Math.round(Number(value));
    return Number.isFinite(n) && n > 0 ? Math.max(lo, Math.min(hi, n)) : fallback;
  };
  const width = clampInt(spec.width ?? params.width, 12, 160, 106);
  const height = clampInt(spec.height ?? params.height, 8, 120, 60);
  const maxDist = Number(spec.cutoff_m) > 0 ? Number(spec.cutoff_m) : 3.0;
  const pattern = buildPattern("pinhole", { ...params, width, height });
  const origin = mountOriginWorld(basePos, baseQuat, mount.pos);
  // 像素 → 相机系射线（buildPattern）→ 世界系（基架），两步都在 screen_frame 的口径下。
  const fwd = quatRot(quatMul(baseQuat, quatFromRpy(mount.rpy.map(deg2rad))), [0, 0, -1]);
  const basis = cameraBasis(fwd);
  const worldDirs = pattern.directions.map((d) => rayFromBasis(basis, d));
  const distances = intersectSceneRays(
    sim.model, sim.data, worldDirs.map(() => origin), worldDirs, { maxDist },
  );
  // 帧归一化到 [0,1]（0=近 1=远，miss→远），与 pie_depth 的输出口径一致——
  // drawDepthFrame 吃的是这个，不是原始米距。
  const frame = distances.map((d) => (Number.isFinite(d) && d >= 0 ? Math.min(1, d / maxDist) : 1));
  const declaredSpec = Number(spec.width) > 0 || Number(spec.height) > 0;
  return {
    width: pattern.width,
    height: pattern.height,
    frame,
    maxDist,
    source: declaredSpec ? "scenario" : "catalog",
  };
}

/** 足底接触：遍历 MuJoCo 接触表，按 geom 名把接触归属到 FL/FR/RL/RR。
 *
 *  与训练栈 `mjlab/sensor/contact_sensor.py` 的口径对齐：那边用正则把 primary 元素解析成
 *  一组名字再逐 primary 取数据；这里模型小（四只脚各一个 collision geom，名字就是 FL/FR/
 *  RL/RR），直接按名字归属即可——但**归属规则必须一样**：geom 名的精确匹配，不做
 *  "包含 calf 就算"这类猜测（go2 的碰撞 geom 名与训练侧 primary 名逐字一致）。
 *
 *  力取该足所有接触的法向力之和（MuJoCo 的 contact force 在 `efc_force` 里，WASM 侧
 *  取不到时退回**接触数**作为着地判据，并如实标注用的是哪个口径）。
 */
function scanFootContacts() {
  const feet = ["FL", "FR", "RL", "RR"].map((name) => ({ name, grounded: false, force: 0, contacts: 0, geomId: -1 }));
  if (!sim.data) return { feet, contactCount: 0, forceAvailable: false };
  const ncon = Number(sim.data.ncon || 0);
  const contact = sim.data.contact;
  // `contact` 在 WASM 侧是 **embind 向量**（`MjContactVec*`）：`.size()` / `.get(i)`，
  // 元素是 `{geom1, geom2, ...}`（值是 `{value: N}` 包装）。**不是**扁平数组——
  // 按 `contact[i*6]` 读会恒得 undefined ⇒ "ncon=4 却着地 无"（2026-09-21 实测踩中，
  // 常驻诊断字段 `model.contacts.pairs` 就是为这类形状猜错留下的）。
  const readGeomPair = (i) => {
    try {
      if (typeof contact?.get === "function") {
        const el = contact.get(i);
        if (!el) return null;
        const pick = (v) => Number(v?.value ?? v ?? -1);
        return [pick(el.geom1), pick(el.geom2)];
      }
    } catch (_) { /* 落到扁平读法 */ }
    const base = i * 6;
    const g1 = Number(contact?.[base] ?? -1);
    const g2 = Number(contact?.[base + 1] ?? -1);
    return Number.isFinite(g1) && g1 >= 0 ? [g1, g2] : null;
  };
  for (let i = 0; i < ncon; i += 1) {
    const pair = readGeomPair(i);
    if (!pair) continue;
    for (const gid of pair) {
      if (gid < 0) continue;
      // 先按 geom 名（包里 model/robot.xml 的足碰撞球就叫 FL/FR/…），再按身体名
      // （浏览器 bundle 的足球无名，但身体叫 FL_calf…）。两条路覆盖两种模型布局。
      const candidates = [String(geomName(gid) || "").toUpperCase(), String(geomBodyName(gid) || "").toUpperCase()];
      const foot = feet.find((f) => candidates.some((c) => c === f.name || c.startsWith(`${f.name}_`)));
      if (!foot) continue;
      foot.contacts += 1;
      foot.grounded = true;
      // 记下命中 geom：3D 接触球要画在它的世界位（两种模型布局都真，见上文两条例）
      if (foot.geomId < 0) foot.geomId = gid;
    }
  }
  // 退化模型（默认关）：迟滞 + 漏检，键为足名
  const noised = feet.map((foot) => ({
    ...foot,
    force: foot.contacts, // WASM 侧拿不到 efc_force 的时代替：接触数即"力"的离散版
    grounded: applyContactNoise(sim.sensorNoise, foot.name, foot.contacts > 0 ? 1 : 0),
  }));
  return { feet: noised, contactCount: ncon, forceAvailable: false };
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
  // 朝向用 **lookAt 构造**而不是直搬四元数：装配 rpy 只定义"前向"（局部 −z 转到世界系），
  // "图像上方"由 `cameraBasis` 从光轴 + 世界上方向构造。直搬四元数的问题：装配 rpy 里
  // y=−90 的俯仰会把相机的局部 +y（three 的 up）转到世界左侧 ⇒ 地平线在图里变成竖线
  // （图像转了 90°，用户报的"RGB 是旋转过的"就是它）。基架与深度外挂预览**同一份**
  // （`sensors/screen_frame.js`），两个前向相机不会各转一个角度。
  const fwd = quatRot(poseQuat, [0, 0, -1]);
  const basis = cameraBasis(fwd);
  preview.camera.up.set(basis.up[0], basis.up[1], basis.up[2]);
  preview.camera.lookAt(origin[0] + fwd[0], origin[1] + fwd[1], origin[2] + fwd[2]);
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
  // 射线类来源的节流在 `cachedScan`（每 kind 一份共享缓存，坞面板与 3D 叠加层同吃）：
  // 此前这里按"来源"各自限频——换来源就重扫，且与 3D 层的缓存互不知晓，同一扫描
  // 一帧最多算三遍（"LiDAR 类来源还是很卡"的另一半根源，2026-09-22 复盘后收口）。

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
      const raw = intersectSceneRay(sim.model, sim.data, origin, dir, { maxDist: RANGE_MAX });
      // 单射线也走同一条退化管线（包成数组）：丢帧/量化/超量程的语义与 LiDAR 完全一致，
      // 不会出现"测距说 3m、LiDAR 说 miss"的分裂。
      const [hit] = applyRangeNoise(sim.sensorNoise, [raw]);
      const reading = rangefinderReadout({ distance: hit === undefined ? raw : hit, maxDist: RANGE_MAX });
      extra.distance = reading.distance;
      note = reading.note;
    } else {
      extra.distance = "—";
      note = "场景几何未就绪";
    }
    extra.mountPos = fmtVec(mount.pos);
    extra.mountRpy = fmtVec(mount.rpy, 0);
  }

  // ⑧ 足底接触：四只脚的着地状态（训练栈 contact_sensor 的浏览器侧对应物）
  if (dock.source === "contact") {
    sizeDockCanvas(240, 150);
    const scan = scanFootContacts();
    const drawn = ctx && drawContactStates(ctx, scan, { width: 240, height: 150 });
    const grounded = scan.feet.filter((f) => f.grounded).map((f) => f.name);
    note = drawn ? `着地 ${grounded.length ? grounded.join(" / ") : "无"}` : "无接触数据";
    extra.grounded = grounded.join(" / ") || "无";
    extra.forces = scan.feet.map((f) => `${f.name} ${f.grounded ? "●" : "○"}`).join(" ");
    extra.contactCount = String(scan.contactCount);
    extra.noiseMode = sim.sensorNoise.enabled ? "退化（迟滞+漏检）" : "理想";
  }

  // ④ 深度相机（外部感知）：策略吃深度时画策略那份（pie_depth.js）；
  //    不吃时走**外挂预览**——深度相机本就是外挂件，没策略输入也应该能"看"
  //  （此前只会写"当前策略无深度输入"，2026-09-22 用户指正）。
  if (dock.source === "depth") {
    const shape = sim.pieDepth && sim.pieDepth.frameShape;
    const frames = sim.depthHistory;
    if (shape && frames && frames.length) {
      sizeDockCanvas(shape[2], shape[1]);
      const rawFrame = frames[frames.length - 1];
      const frame = applyDepthNoise(sim.sensorNoise, Array.from(rawFrame)) || rawFrame;
      const drawn = ctx && drawDepthFrame(ctx, frame, shape[1], shape[2]);
      note = drawn ? `${shape[1]}×${shape[2]} 近亮远暗` : "绘制失败";
    } else if (scanReady) {
      const preview = cachedScan("depth", (bp, bq) => scanDepthPreview(bp, bq, sensorMount("depth", sensorMountOverrides)));
      sizeDockCanvas(preview.width, preview.height);
      const drawn = ctx && drawDepthFrame(ctx, preview.frame, preview.height, preview.width);
      note = drawn
        ? `外挂预览 ${preview.width}×${preview.height} · 截止 ${preview.maxDist} m（当前策略不消费深度）`
        : "绘制失败";
      extra.depthMode = `外挂预览（${preview.width}×${preview.height}，`
        + `截止 ${preview.maxDist} m，规格来源：${preview.source === "scenario" ? "场景声明" : "传感器目录"}）`;
      extra.depthCutoffM = String(preview.maxDist);
    } else {
      note = "场景几何未就绪";
    }
  }

  // ⑤ 高度扫描（heightfield 项，A 类契约 187 = 17×11）：机周网格**起点**、射线朝下
  //   → 俯视高度场。画的是**世界高度**（彩色图看绝对高度直观），读数给的是**契约值**
  //   base_z − terrain_z（策略要吃的那份）——两者都要，各有去处。
  if (dock.source === "height") {
    const mount = sensorMount("height", sensorMountOverrides);
    const grid = patternParams("height")?.grid || {};
    const nx = grid.nx || 17;
    const ny = grid.ny || 11;
    if (scanReady) {
      const scan = cachedScan("height", (bp, bq) => scanHeightField(bp, bq, mount));
      sizeDockCanvas(nx, ny);
      const drawn = ctx && drawHeightGrid(ctx, scan.world, nx, ny);
      note = drawn ? `187 点契约网格 · 命中 ${scan.hits}/${scan.total}` : "绘制失败";
      extra.scanExtent = "1.6 m × 1.0 m（x −0.8..0.8 / y −0.5..0.5）";
      extra.scanGrid = `${nx} × ${ny}（x 主序）`;
      extra.hitRatio = `${scan.hits} / ${scan.total}`;
      extra.contractValue = "base_z − terrain_z（未缩放）";
    } else {
      note = "场景几何未就绪";
    }
    extra.mountPos = fmtVec(mount.pos);
  }

  // ⑤b LiDAR 聚合高度场（lidar_height_scan 项）：LiDAR 点云按同一 187 网格聚合 min-z。
  //     与 heightfield **同格**是本项存在的理由——两条链路可以逐格对齐回归。
  if (dock.source === "lidar_height_scan") {
    const grid = patternParams("lidar_height_scan")?.grid || {};
    const nx = grid.nx || 17;
    const ny = grid.ny || 11;
    if (scanReady) {
      const lidar = cachedScan("lidar", (bp, bq) => scanLidar(bp, bq, sensorMount("lidar", sensorMountOverrides)));
      const points = lidar.distances
        .map((d, i) => (d < 0 ? null : [
          lidar.origin[0] + lidar.worldDirs[i][0] * d,
          lidar.origin[1] + lidar.worldDirs[i][1] * d,
          lidar.origin[2] + lidar.worldDirs[i][2] * d,
        ]))
        .filter(Boolean);
      const q = sim.qpos ? [sim.qpos[3], sim.qpos[4], sim.qpos[5], sim.qpos[6]] : [1, 0, 0, 0];
      const yaw = Math.atan2(2 * (q[0] * q[3] + q[1] * q[2]), 1 - 2 * (q[2] * q[2] + q[3] * q[3]));
      const scan = aggregateHeightScan(points, { x: basePos[0], y: basePos[1], z: basePos[2], yaw });
      sizeDockCanvas(nx, ny);
      const drawn = ctx && drawHeightGrid(ctx, scan.field, nx, ny);
      note = drawn
        ? `点云聚合 min-z · 有值 ${scan.filled}/${scan.total} 格`
        : "绘制失败";
      extra.scanGrid = `${nx} × ${ny}（与 heightfield 同格）`;
      extra.aggregate = "min_z_per_cell";
      extra.filled = `${scan.filled} / ${scan.total}`;
      extra.emptyFill = "空单元填 null（绘制为黑槽，不编高度）";
    } else {
      note = "场景几何未就绪";
    }
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
      const scan = cachedScan("lidar", (bp, bq) => scanLidar(bp, bq, mount));
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
    // 诊断：相机世界位姿（排查"看到的不是前方"时用）
    const camQuat = quatMul(baseQuat, quatFromRpy(mount.rpy.map(deg2rad)));
    const camOrigin = mountOriginWorld(basePos, baseQuat, mount.pos);
    const camDir = quatRot(camQuat, [0, 0, -1]);
    extra.camWorld = `${camOrigin.map((v) => v.toFixed(2)).join(" / ")} · 朝向 ${camDir.map((v) => v.toFixed(2)).join(" / ")}`;
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

/** WASM 视图快照：视图在"取引用 → Array.from"窗口里被堆扩容 detach 时（refreshDataViews
 *  也挡不住窗口内的扩容），重取一次再试；仍失败就丢这一帧读数，不让异常上抛。 */
function snapshotOf(getView) {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const view = getView();
      return view ? Array.from(view) : [];
    } catch (_) {
      refreshDataViews();
    }
  }
  return [];
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
      // 接触诊断（常驻）：`contact` 在 WASM 侧是 embind 向量（`MjContactVec*`，`.get(i)`），
      // 不是扁平数组；足底归属按 geom 名 → 身体名两级匹配。原始接触对留在这里，
      // "着地 无"这类症状才能一眼分清是布局猜错还是真没接触。
      contacts: (() => {
        try {
          const data = sim.data;
          if (!data) return null;
          const ncon = Number(data.ncon || 0);
          const raw = data.contact;
          const pairs = [];
          if (raw && typeof raw.get === "function") {
            for (let i = 0; i < Math.min(ncon, 8); i += 1) {
              const el = raw.get(i);
              if (!el) continue;
              const a = Number(el.geom1?.value ?? el.geom1 ?? -1);
              const b = Number(el.geom2?.value ?? el.geom2 ?? -1);
              pairs.push([geomName(a) || geomBodyName(a) || a, geomName(b) || geomBodyName(b) || b]);
            }
          }
          return { ncon, pairs };
        } catch (error) {
          return { error: String(error).slice(0, 80) };
        }
      })(),
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
    qpos: snapshotOf(() => sim.qpos),
    qvel: snapshotOf(() => sim.qvel),
    ctrl: snapshotOf(() => sim.ctrl),
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
  // 光影看门狗：武装后（见过健康帧率）连续 5 秒 < 40 帧 → 自动关掉并如实报告。
  // 只兜一次底，用户重新勾上不再拦（那是用户在知情下的取舍）。
  if (view.shadowsEnabled && view.fps >= 40) {
    view.shadowEverHealthy = true;
  }
  if (view.shadowsEnabled && view.shadowEverHealthy && view.fps > 0 && view.fps < 40) {
    if (!view.shadowLowFpsSince) {
      view.shadowLowFpsSince = now;
    } else if (now - view.shadowLowFpsSince > 5000) {
      if (elements.shadowToggle) elements.shadowToggle.checked = false;
      applyShadowSetting();
      setStatus(elements.engineStatus, "帧率偏低 · 光影已自动关闭", "ready");
    }
  } else {
    view.shadowLowFpsSince = 0;
  }
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
/** 坞内射线类来源的重扫间隔（ms）。10 Hz 与常见 LiDAR 的旋转频率同量级——
 *  逐帧重扫（60 fps × 240 射线）是"开雷达就卡"的根源，而且不比 10 Hz 更真实。 */
const DOCK_SCAN_INTERVAL_MS = 100;
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

/**
 * A1：应用交运来的完整 Scenario。
 *
 * 三条纪律：
 *   1. **不支持就拒**，不静默降级（`command_source=script/perception` 浏览器执行器跑不了，
 *      见 `backend/executors.py` 的 UNSUPPORTED_CONTRACT_OPTIONS）；
 *   2. **能应用的应用，不能应用的明说**（种子/机型/运行面只能在加载时定，中途改不了）——
 *      返回的 `applied` / `skipped` 两边都让编辑器显示出来，不许"看起来全应用了"；
 *   3. 场景的判据/记录器**按声明**跑（未声明的不跑、不造文件）。
 *
 * @returns {Promise<{ok: boolean, reason: string, applied: string[], skipped: string[]}>}
 */
/** 场景声明的感知项里，**当前策略没有对应输入**的那些（C2 的 fail-closed 判据）。
 *
 *  映射关系（场景项 → 策略输入）只有一条是今天真通的：`depth_camera` → 策略 ONNX 的
 *  `depth` 输入（PIE 族，浏览器 raycast 喂深度历史）。其余三项目录里有定义、浏览器执行器
 *  还没有对应输入 ⇒ 一律算"未接入"——不猜一个近似输入顶上。
 */
/** 策略加载完成后，补判场景挂起的 A 类感知绑定（C2）。
 *  不过 ⇒ 暂停仿真并在场景面板写明原因（不静默跑一个吃不到感知的场景）。 */
function verifyScenarioPerceptionBinding() {
  const pending = sim.pendingPerceptionCheck;
  if (!pending || !sim.scenario || !sim.scenarioRun.active) return;
  sim.pendingPerceptionCheck = null;
  const gaps = unsupportedPerceptionItems(pending);
  if (!gaps.length) {
    renderScenarioPanel(`A 类绑定通过：${pending.join(" / ")} 已接入策略观测`);
    return;
  }
  sim.paused = true;
  elements.playButton.textContent = "继续";
  const reason = `场景声明 A 类感知（route=obs）但当前策略没有对应输入：${gaps.join("；")}`
    + `（A 类 = 感知进策略观测，策略没声明就是吃不到；B 类请用 route=external）`;
  sim.scenarioRun.refusedReason = reason;
  renderScenarioPanel(`场景被拒：${reason}`, true);
  console.warn("[sim2sim] scenario perception binding failed", reason);
}

/** 场景声明的感知项里，**当前策略没有对应输入**的那些（C2 的 fail-closed 判据）。
 *
 *  **浏览器执行器能产出什么**（与策略是否吃它是两件事，别混）：`depth_camera`（raycast
 *  深度历史）、`heightfield` / `lidar_height_scan`（187 网格射线 / 点云聚合）、
 *  `foot_contact`（四脚状态）——四项目前都能在坞里看到数。
 *  **但"执行器能产出"≠"策略会吃"**：除 depth 外，今天没有任何已登记策略在其 ONNX 上
 *  声明这些输入 ⇒ A 类场景声明它们仍然拒启。拒绝理由必须区分"执行器没接线"与
 *  "策略没声明"，否则修的人找错方向。
 */
function unsupportedPerceptionItems(items) {
  const info = sim.policyInfo || {};
  const executorCanProduce = {
    depth_camera: true,
    heightfield: true,
    lidar_height_scan: true,
    foot_contact: true,
  };
  const policyDeclares = {
    depth_camera: Boolean(info.depthName),
    heightfield: false,
    lidar_height_scan: false,
    foot_contact: false,
  };
  return items.filter((item) => !policyDeclares[item]).map((item) => (
    executorCanProduce[item]
      ? `${item}：浏览器执行器能产出（坞里可看），但当前策略没有对应输入`
      : `${item}：浏览器执行器暂无该观测输入（目录有定义、接线未做）`
  ));
}

async function applyScenario(payload) {
  const scenario = payload.scenario;
  const applied = [];
  const skipped = [];
  const note = (text) => { applied.push(text); };
  const skip = (text) => { skipped.push(text); };

  const commandSource = String(scenario.command_source || "policy");
  // 执行器能力真值从 /api/simulation/executors 拿（B1）；拿不到时用框架目录里的浏览器镜像。
  const supportedSources = sim.executorMatrix?.executors
    ?.find((item) => item.id === "browser_wasm")?.supports?.command_sources
    || EXECUTOR_COMMAND_SOURCES.browser_wasm;
  const gaps = unsupportedCommandSourceProblems(commandSource, supportedSources);
  if (gaps.length) {
    const reason = `${gaps[0]}（可执行：${supportedSources.join(" / ")}）`;
    sim.scenarioRun.refusedReason = reason;
    return { ok: false, reason, applied, skipped };
  }

  // 机型：交运的机型与当前不一致时**拒绝**（换机型要整页重载，偷偷按当前的跑等于跑错场景）
  const currentRobot = String(elements.robotSelect?.value || URL_ROBOT || "");
  if (payload.robot && currentRobot && payload.robot !== currentRobot
      && normalizeRobotParam(payload.robot) !== normalizeRobotParam(currentRobot)) {
    const reason = `场景指定机器人 ${payload.robot}，当前加载的是 ${currentRobot} —— 换机型需重新打开页面（不按当前机型假跑）`;
    sim.scenarioRun.refusedReason = reason;
    return { ok: false, reason, applied, skipped };
  }
  if (payload.robot) note(`机器人 ${payload.robot}`);

  // 策略：不同才切（同 id 不重启会话，避免白丢一次加载）
  const currentPolicy = String(elements.policySelect?.value || "off");
  if (payload.policy && payload.policy !== currentPolicy) {
    if (payload.policy === "off") {
      await switchPolicy("off");
      note("策略：无（姿态保持）");
    } else if (Array.from(elements.policySelect?.options || []).some((option) => option.value === payload.policy)) {
      await switchPolicy(payload.policy);
      note(`策略 ${payload.policy}`);
    } else {
      skip(`策略 ${payload.policy} 不在本包策略清单里`);
    }
  } else if (payload.policy) {
    note(`策略 ${payload.policy}（已在运行）`);
  }

  // 地形：map_id 走**同一条解析链**（resolveTerrainName）。解析不到就明说——
  // 静默回落 flat 会让"编辑器说 warehouse、仿真跑平地面"（A3 的同源缺陷）。
  const requestedTerrain = String(scenario.map_id || "");
  if (requestedTerrain) {
    const scenes = Array.from(elements.terrainSelect?.options || []).map((option) => option.value);
    const resolved = resolveTerrainName(requestedTerrain, scenes);
    const currentTerrain = elements.terrainSelect?.value || "";
    if (resolved && resolved !== currentTerrain) {
      elements.terrainSelect.value = resolved;
      elements.terrainSelect.dispatchEvent(new Event("change", { bubbles: true }));
      note(`地形 ${requestedTerrain} → ${resolved}`);
    } else if (resolved) {
      note(`地形 ${requestedTerrain}（已加载）`);
    } else {
      skip(`地形 ${requestedTerrain} 在本包没有对应场景（可选：${scenes.join(" / ") || "无"}）——未静默改用其它地形`);
    }
  }

  // 指令上限：场景的 command_limits 覆盖 CONFIG.maxCmd（跟随/规划都按它夹取）
  const limits = scenario.command_limits || {};
  let limitText = "";
  for (const [index, key] of ["vx", "vy", "wz"].entries()) {
    const value = Number(limits[key]);
    if (Number.isFinite(value) && value > 0) {
      CONFIG.maxCmd[index] = value;
      limitText += ` ${key}=${value}`;
    }
  }
  if (limitText) note(`指令上限${limitText}`);

  // 指令来源：planner/perception ⇒ 起导航（waypoints 由场景给）；policy ⇒ 确保不接管；
  // teleop ⇒ 键盘/摇杆（默认行为，无需动作）。
  const waypoints = (Array.isArray(scenario.waypoints) ? scenario.waypoints : [])
    .map((point) => ({ x: Number(point?.x) || 0, y: Number(point?.y) || 0 }));
  if (commandSource === "planner" || commandSource === "perception") {
    if (waypoints.length >= 2) {
      await startNavigation(requestedTerrain || "flat", waypoints);
      note(`指令来源 ${commandSource}：导航已就绪（${waypoints.length} 个航点）`);
    } else {
      const reason = `command_source=${commandSource} 需要至少 2 个航点，场景只给了 ${waypoints.length} 个`;
      sim.scenarioRun.refusedReason = reason;
      return { ok: false, reason, applied, skipped };
    }
  } else if (commandSource === "policy") {
    if (sim.navigation) {
      sim.navigation = null;
      renderNavigationHud();
      note("指令来源 policy：已关闭导航接管");
    } else {
      note("指令来源 policy（无导航接管）");
    }
  } else {
    note(`指令来源 ${commandSource}（键盘/摇杆直驱）`);
  }

  // 时长：只认"加载时定的 seed / 运行面"，中途改不了的要明说（不假报已应用）
  if (Number.isFinite(Number(scenario.seed)) && Number(scenario.seed) !== Number(PAGE_PARAMS.get("seed") || 0)) {
    skip(`种子 ${scenario.seed} 需在打开页面时指定（当前 ${PAGE_PARAMS.get("seed") || 0}）`);
  }
  // 运行面：**反向才 skip**（场景需要高级面、而页面在基础面 ⇒ 确实跑不了导航那套）；
  // 反过来不是错——高级仿真页跑一份 `mode=basic` 的场景正是编辑器的常态
  // （高级面是"创作面"，它照样能跑基础任务）。原先写成"两侧不等就 skip"，于是**每次**
  // 从高级仿真页按默认场景启动都会白报一句"未应用：运行面 basic…"（诚实提示被噪声淹没）。
  const needsAdvanced = scenario.mode === "navigation";
  const pageSurface = PAGE_PARAMS.get("surface") || "basic";
  if (needsAdvanced && pageSurface !== "advanced") {
    skip(`运行面 advanced 需在打开页面时指定（当前 ${pageSurface}）`);
  }

  // 感知（C2）：场景声明的传感器**真的开**（dock 插件开关），且 **route=obs（A 类）时
  // 校验当前策略是否真的声明了该项**——服务端会话早有这道闸（simulation_api 的 A-class
  // guard），浏览器侧此前没有：场景说"感知进观测"而策略没有对应输入时，页面照常启动、
  // 传感器照常画，只是策略永远吃不到它（"看着生效、其实没生效"）。
  const perception = scenario.perception && typeof scenario.perception === "object" ? scenario.perception : null;
  if (perception) {
    const enabled = [];
    if (perception.heightfield) enabled.push("heightfield");
    if (perception.depth_camera) enabled.push("depth_camera");
    if (perception.foot_contact) enabled.push("foot_contact");
    if (enabled.length) {
      sim.scenarioSensors = { route: perception.route || "external", mount: perception.mount || "base", enabled };
      // 声明即开：把坞里对应的插件勾上（否则"已启用"只是面板上的一句话，坞里无从查看）。
      const turnedOn = enableDockPluginsForScenario(perception);
      note(`感知传感器已启用：${enabled.join(" / ")}（route=${perception.route || "external"}）`
        + (turnedOn.length ? `；坞里已打开：${turnedOn.join(" / ")}` : ""));
      if ((perception.route || "external") === "obs") {
        if (sim.policyInfo) {
          const gaps = unsupportedPerceptionItems(enabled);
          if (gaps.length) {
            const reason = `场景声明 A 类感知（route=obs）但当前策略没有对应输入：${gaps.join("；")}`
              + `（A 类 = 感知进策略观测，策略没声明就是吃不到；B 类请用 route=external）`;
            sim.scenarioRun.refusedReason = reason;
            return { ok: false, reason, applied, skipped };
          }
          note(`A 类绑定：${enabled.join(" / ")} 已接入策略观测`);
        } else {
          // 策略还没加载完（`policyInfo` 在 ONNX 会话建好后才填）——**此时判会把好场景
          // 误拒**（2026-09-21 实测：pie-parkour 有 depth 输入，但消息比策略先到）。
          // 挂起，等策略加载完再由 `verifyScenarioPerceptionBinding` 判。
          sim.pendingPerceptionCheck = enabled.slice();
          note(`A 类绑定待策略加载后校验：${enabled.join(" / ")}`);
        }
      }
    }
  }

  sim.scenario = scenario;
  sim.scenarioRun = {
    trace: [],
    active: true,
    deadlineS: Number(scenario.episode_length_s) > 0 ? Number(scenario.episode_length_s) : null,
    summary: null,
    applied,
    refusedReason: "",
  };
  resetSimulation();
  renderScenarioPanel(`场景 ${scenario.scenario_id} 已应用 · ${applied.length} 项生效`
    + (skipped.length ? ` · ${skipped.length} 项未应用（见摘要）` : ""));
  console.info("[sim2sim] scenario applied", { scenario, applied, skipped });
  return { ok: true, reason: "", applied, skipped };
}

/** 把 `/api/navigation/plan` 的失败原因拼成人能读的一句话（detail 可能是字符串/数组/对象）。 */
function describePlanFailure(payload, status) {
  const detail = payload?.detail ?? payload?.message;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map((item) => {
      if (typeof item === "string") return item;
      const where = Array.isArray(item?.loc) ? item.loc.join(".") : "";
      return where ? `${where}: ${item.msg}` : String(item?.msg ?? item);
    }).filter(Boolean);
    if (parts.length) return `规划请求被拒（${parts.join("；")}）`;
  }
  if (detail && typeof detail === "object") {
    const msg = detail.msg || detail.error || detail.reason;
    if (typeof msg === "string" && msg) return msg;
  }
  return `规划失败（HTTP ${status}）`;
}

/** 起导航（与 initNavigationFromUrl 同一服务端真值，只是航点来自场景而非 URL）。 */
async function startNavigation(mapId, waypoints) {
  // 服务端 `NavigationPlanRequest.waypoints` 是 `list[list[float]]`（[[x, y], …]）——
  // 场景契约里是 [{x, y}, …]，这里做**唯一一次**形状转换（与 initNavigationFromUrl
  // 从 URL 串解析出的形状一致），别把两种形状混着发。
  const pairs = waypoints.map((point) => [Number(point.x) || 0, Number(point.y) || 0]);
  const response = await fetch("/api/navigation/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ map_id: mapId, waypoints: pairs }),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok || !payload?.success) {
    // FastAPI 的 detail 可能是字符串、数组（422 校验错误 [{loc,msg}]）或对象——
    // 直接 `String(detail)` 会得到 "[object Object]"，把人挡在原因外面。
    throw new Error(describePlanFailure(payload, response.status));
  }
  sim.navigation = {
    mapId,
    payload,
    runner: createNavigationRunner(payload, {
      maxCmd: Array.from(CONFIG.maxCmd),
      lookahead: Number(PAGE_PARAMS.get("nav_lookahead") || 0.6),
      controlDt: () => CONFIG.simulationDt * CONFIG.controlDecimation,
    }),
    status: null,
    lastControlStep: -1,
  };
  sim.perception = {
    sceneId: mapId,
    decision: null,
    lastReading: null,
    disabledReason: null,
    inFlight: false,
    polls: 0,
    errors: 0,
  };
  sim.dwaFan = { enabled: PAGE_PARAMS.get("fan") !== "0", inFlight: false, lastControlStep: -1, polls: 0, errors: 0, reason: "" };
  renderNavigationHud(`导航已就绪 · ${mapId} · ${payload.waypoints.length} 个航点 · 判据 ${payload.arrival.source}`);
}

/** 场景运行面板（A1）：应用项/未应用项/判据结论/记录器产物，一处看完，不拆页面。 */
function renderScenarioPanel(message = "", failed = false) {
  let panel = document.querySelector("#scenarioPanel");
  const run = sim.scenarioRun;
  if (!sim.scenario && !message) {
    if (panel) panel.remove();
    return;
  }
  if (!panel) {
    panel = document.createElement("div");
    panel.id = "scenarioPanel";
    panel.style.cssText = "position:fixed;right:12px;top:12px;z-index:40;max-width:340px;padding:8px 10px;"
      + "border-radius:8px;background:rgba(10,14,22,.86);color:#dfe8f5;"
      + "font:11px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap";
    document.body.appendChild(panel);
  }
  panel.style.color = failed ? "#ffb4b4" : "#dfe8f5";
  if (message) {
    panel.textContent = message;
    return;
  }
  const summary = run.summary;
  if (!summary) {
    panel.textContent = `场景 ${sim.scenario?.scenario_id || ""} 运行中 · 采样 ${run.trace.length} 点`
      + (run.deadlineS ? ` · 上限 ${run.deadlineS}s` : "");
    return;
  }
  const lines = [`场景 ${summary.scenarioId} · ${summary.passed ? "通过" : "未通过"}`];
  for (const check of summary.checks) lines.push(`  ${check.ok ? "✓" : "✗"} ${check.name}: ${check.detail}`);
  lines.push(`  度量: ${summary.metrics.distanceM}m / ${summary.metrics.durationS}s / 最大 roll ${summary.metrics.maxRollDeg}°`
    + ` / 摔倒 ${summary.metrics.fell ? "是" : "否"}`);
  if (summary.artifacts.length) lines.push(`  记录器产物: ${summary.artifacts.join(", ")}`);
  if (run.episode?.dir) {
    lines.push(`  episode 已落档: ${run.episode.dir}`);
    lines.push(`  回放: ${run.episode.replay_url}`);
  }
  panel.textContent = lines.join("\n");
}

/** 收尾一趟场景运行：求判据、出摘要、按声明产记录器文件、面板显示。
 *
 *  B4：若场景声明了 `trajectory` 记录器，就把这一趟**上报成 episode**（POST
 *  /api/episode/import）—— 此前 `EpisodeRecorder` 只在测试里实例化，回放页结构上恒空。
 *  上报失败**不阻断收尾**（摘要已在面板上），但要在控制台如实说失败原因。
 */
async function finishScenarioRun(reason) {
  const run = sim.scenarioRun;
  if (!run.active || !sim.scenario) return;
  run.active = false;
  const arrival = sim.navigation?.payload?.arrival || null;
  run.summary = buildRunSummary(sim.scenario, run.trace, arrival);
  renderScenarioPanel();
  console.info(`[sim2sim] scenario run finished (${reason})`, run.summary);
  const artifacts = recorderArtifacts(sim.scenario, run.trace, arrival);
  sim.scenarioArtifacts = artifacts;
  if (Object.keys(artifacts).length) {
    console.info("[sim2sim] recorder artifacts ready", Object.keys(artifacts));
  }
  if (!run.summary.recorders.includes("trajectory")) return;
  try {
    const response = await fetch("/api/episode/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildEpisodeImportPayload(reason)),
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(payload?.detail || `HTTP ${response.status}`);
    }
    run.episode = payload;
    renderScenarioPanel();
    console.info("[sim2sim] episode recorded", payload);
  } catch (error) {
    console.warn("[sim2sim] episode upload failed", error?.message || error);
  }
}

/** 轨迹 → episode 记录（LightNav 语义：`waypoints` = 该步**指令**位置，`pointing.actual` = 实测）。
 *
 *  指令位置由轨迹里的 vx/vy **积分**得到（世界系）—— 于是回放页的"预测 vs 实际"
 *  实际是"指令积分 vs 实测轨迹"，这正是本仓要对齐的那条比较。
 */
function buildEpisodeImportPayload(reason) {
  const run = sim.scenarioRun;
  const scenario = sim.scenario;
  const records = [];
  let cmdX = 0;
  let cmdY = 0;
  let previousT = null;
  for (const point of run.trace) {
    const dt = previousT === null ? 0 : Math.max(0, point.t - previousT);
    previousT = point.t;
    cmdX += point.vx * dt;
    cmdY += point.vy * dt;
    records.push({
      step: records.length,
      seq: records.length,
      waypoints: [[Number(cmdX.toFixed(4)), Number(cmdY.toFixed(4))]],
      pointing: { actual: [Number(point.x.toFixed(4)), Number(point.y.toFixed(4))] },
      stop: point.fallen,
      extra: { t: point.t, yawDeg: point.yawDeg, rollDeg: point.rollDeg, pitchDeg: point.pitchDeg },
    });
  }
  const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  return {
    run: `${scenario.scenario_id}-${stamp}`,
    conn: "browser-wasm",
    episode: 1,
    manifest: {
      task: "scenario",
      instruction: scenario.scenario_id,
      model_path: String(elements.policySelect?.value || ""),
      waypoint_dt_s: 0.02,
      extra: {
        scenario_id: scenario.scenario_id,
        command_source: scenario.command_source,
        episode_length_s: scenario.episode_length_s,
        finish_reason: reason,
        checks: run.summary.checks,
        metrics: run.summary.metrics,
      },
    },
    records,
  };
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
        // H12 卡死恢复状态机需要真实时间：控制拍时长 = sim_dt × decimation。
        // 传 getter（每拍求值）：模型合约（simulationDt/decimation）可能晚于导航初始化到达，
        // 且热切换/换机型会改写 CONFIG——runner 每拍取最新值，避免快照过期。
        controlDt: () => CONFIG.simulationDt * CONFIG.controlDecimation,
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
    // 策略未就绪（ONNX 会话仍在加载，runPolicy 走 holdStance）时**不推状态机时钟**：
    // H12 卡死/超时判据衡量的是"执行层接到指令却不动"；执行层还没接上时计时是
    // 假卡死（冷启动实测：策略加载慢于场景 ⇒ 4s 内烧光 4 轮恢复、误判 stuck）。
    if (sim.policy && sim.policyInfo) {
      sim.navigation.status = sim.navigation.runner.tick(pose);
    }
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
  // H12 终止原因分层（抄 LightNav：策略结论 / 预算截断 / 判据未定义 分开）——
  // 页面状态栏如实显示中文原因，不把 timeout/stuck/truncated 混称"已完成"。
  const reasonText = {
    complete: "到达判据触发，走完全程",
    timeout: "单航点超时（策略结论）",
    stuck: `卡死：恢复动作 ${status.recoveries_used}/${status.max_recoveries} 轮后仍无进展`,
    truncated: "总时长预算拉停（非策略结论）",
    undefined: "判据未定义（无有效航点）",
  }[status.termination_reason] || null;
  if (status.finished) {
    hud.textContent = `导航 ${sim.navigation.mapId} · 航段 ${legs} · 完成率 ${Math.round(status.route_completion * 100)}%`
      + (status.termination_reason === "complete" ? " · 已完成" : ` · 终止：${reasonText}`);
  } else {
    hud.textContent = `导航 ${sim.navigation.mapId} · 航段 ${legs} · 完成率 ${Math.round(status.route_completion * 100)}%`
      + ` · 容差 ${status.tolerance_m}m（稳定 ${status.stable_count}/${status.stable_ticks}）`
      + ` · 上限 vx${status.limits[0]} wz${status.limits[2]}`;
    // 恢复中如实显示（卡死恢复是 H12 状态机动作，不是正常跟随）
    if (status.stuck) hud.textContent += `\n卡死恢复中（第 ${status.recoveries_used}/${status.max_recoveries} 轮）`;
  }
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
  // 地形漆装（含 CanvasTexture 的材质）随场景一起作废——换地图必须重画。
  for (const material of view.terrainSurfaceCache.values()) material.dispose();
  view.terrainSurfaceCache.clear();
}

function disposeRenderable(renderable) {
  if (!renderable) return;
  view.scene.remove(renderable.mesh);
  renderable.material.dispose();
  view.materials.delete(renderable.material);
}



