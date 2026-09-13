// 传感器视图悬浮窗：**单一视图 + 来源切换** + 外挂传感器插件开关（左上角）。
//
// **为什么单独一个模块**：来源清单、插件清单、以及"当前该画什么"的判定都是**数据**，
// 写成纯函数就能在 Node 里断言（CI 不装浏览器）；DOM 那一层只负责取值与贴图。
//
// **为什么不再并排三块面板**：并排占位置且来源固定 —— 要看别的就得改 HTML。
// 收成一个悬浮窗后，"看什么"是下拉里的一次选择，传感器是勾选出来的。

/**
 * 视图来源。
 * - `kind: "canvas"` 画在 canvas 上；`kind: "readout"` 画成读数表。
 * - `requires` 指向插件 id：该插件**没勾选**时这个来源不可选（灰掉）——
 *   这就是"插件可以选择外挂传感器"落到 UI 上的样子。`null` 表示不依赖插件。
 */
export const DOCK_SOURCES = [
  { id: "odom", label: "全局里程计 odom", kind: "readout", requires: "odom" },
  { id: "imu", label: "IMU", kind: "readout", requires: "imu" },
  { id: "rangefinder", label: "单点测距", kind: "readout", requires: "rangefinder" },
  { id: "depth", label: "深度相机", kind: "canvas", requires: "depth" },
  { id: "height", label: "高度扫描", kind: "canvas", requires: "height" },
  { id: "trail", label: "2D 轨迹平面", kind: "canvas", requires: null },
  { id: "lidar", label: "射线 LiDAR", kind: "canvas", requires: "lidar" },
  { id: "cloud", label: "点云", kind: "canvas", requires: "lidar" },
  { id: "rgb", label: "RGB 相机", kind: "canvas", requires: "rgb" },
];

/**
 * 传感器清单。
 * `onboard: true` 是**本体感知**（IMU / 里程计 —— 机器人本来就有的），默认开；
 * 其余是**外挂传感器**，默认关 —— "插件可以选择"，要就勾上。
 * 每个都有**默认装配**（`DEFAULT_MOUNTS`）与**可视化模型**（`SENSOR_MODELS`）。
 */
export const SENSOR_PLUGINS = [
  { id: "odom", label: "全局里程计 odom", onboard: true, hint: "世界坐标系位姿 x/y/z + 姿态 + 累计里程" },
  { id: "imu", label: "IMU", onboard: true, hint: "三轴角速度 + 重力投影" },
  { id: "rangefinder", label: "单点测距", onboard: false, hint: "沿装配方向打一条射线，给出到最近障碍的距离" },
  { id: "depth", label: "深度相机", onboard: false, hint: "机头前向 60×86 深度帧" },
  { id: "height", label: "高度扫描（雷达）", onboard: false, hint: "机周 0.1 m 网格高度场" },
  { id: "lidar", label: "LiDAR（射线）", onboard: false, hint: "水平扇扫 → 极坐标图与点云" },
  { id: "rgb", label: "RGB 相机", onboard: false, hint: "three.js 相机（非 MuJoCo 原生渲染）" },
];

/**
 * **默认装配**（机身坐标系：x 前、y 左、z 上；位置单位 m，角度单位**度**）。
 *
 * **朝向约定：传感器的"看"方向 = 它局部的 −z**（与 MuJoCo 相机一致）。
 * 于是 `rpy = [0, 0, 0]` 是**朝下**，朝前要把 −z 绕 y 转到 +x —— 即 **y = −90°**。
 * 这几个默认值是"出厂位置"，全部可以在 UI 里改（位置与角度各三格）。
 */
export const DEFAULT_MOUNTS = {
  odom: { pos: [0, 0, 0], rpy: [0, 0, 0] }, // 本体感知：机身原点（不是物理器件）
  imu: { pos: [0, 0, 0.05], rpy: [0, 0, 0] }, // 机身中部上方
  rangefinder: { pos: [0.30, 0, 0.05], rpy: [0, -90, 0] }, // 机头，水平前视
  depth: { pos: [0.28, 0, 0.08], rpy: [0, -80, 0] }, // 机头，朝前略下俯
  height: { pos: [0, 0, 0.06], rpy: [0, 0, 0] }, // 雷达，垂直向下
  lidar: { pos: [0.05, 0, 0.16], rpy: [0, 0, 0] }, // 机顶旋转雷达
  rgb: { pos: [0.27, 0, 0.09], rpy: [0, -80, 0] }, // 与深度相机并排
};

/**
 * **可视化模型**：每个传感器在 3D 场景里的默认外形，让人能看出"装在哪、朝哪"。
 * `size` 随 `kind` 解释：box = `[半长, 半宽, 半高]`；sphere = `[半径]`；cylinder = `[半径, 半高]`。
 * 尺寸按 go2 机身量级取（机身约 0.7 m 长），够小到不挡视线、够大到看得见。
 */
export const SENSOR_MODELS = {
  odom: { kind: "sphere", size: [0.02], color: 0x94a3b8, label: "odom" },
  imu: { kind: "box", size: [0.04, 0.03, 0.012], color: 0xa78bfa, label: "IMU" },
  rangefinder: { kind: "cylinder", size: [0.012, 0.03], color: 0xf97316, label: "测距" },
  depth: { kind: "box", size: [0.03, 0.06, 0.035], color: 0x38bdf8, label: "深度" },
  height: { kind: "cylinder", size: [0.03, 0.02], color: 0x22c55e, label: "雷达" },
  lidar: { kind: "cylinder", size: [0.04, 0.05], color: 0xeab308, label: "LiDAR" },
  rgb: { kind: "box", size: [0.03, 0.06, 0.035], color: 0xf472b6, label: "RGB" },
};

/**
 * **采样规格**：由射线驱动的来源各自扫多少、看多远。
 *
 * 集中放这里而不是散进 `app.js`，是因为**分辨率同时决定扫描量、画布像素尺寸与图上的网格感**
 * —— 放在一处，改的时候就不会只改对一半（"画布是 24² 但只扫了 16²"这种，图上看起来只是边缘发黑）。
 * 三个数都是"画得出图"与"每帧算得完"之间的折中：场景 geom 是两位数，
 * 576 条射线/帧对 CPU 求交来说不构成负担。
 */
export const SCAN_SPECS = {
  /** 高度扫描：机周 4 m × 4 m 的 24×24 **起点**网格（射线都朝下）。 */
  height: { side: 24, extent: 2.0, maxDist: 4.5 },
  /** LiDAR：整圈 360° 均布 240 线，量程 12 m。 */
  lidar: { count: 240, maxDist: 12 },
  /** 点云与 LiDAR **共用同一次扫描**：两图必须同源，否则"点云比极坐标图多出几个点"永远查不完。 */
  cloud: { maxDist: 12 },
  /** RGB：预览分辨率与视场角。渲染方式见 `app.js::renderRgbPreview`（three.js，非 MuJoCo 原生）。 */
  rgb: { width: 160, height: 120, fov: 60, near: 0.12, far: 60 },
};

/** 取某传感器的装配（**默认 + 用户覆盖**）。缺项回落默认；未知 id 返回 null。 */
export function sensorMount(id, overrides = {}) {
  const base = DEFAULT_MOUNTS[id];
  if (!base) return null;
  const override = overrides?.[id] || {};
  const pick = (key) => {
    const value = override[key];
    return Array.isArray(value) && value.length === 3 && value.every((v) => Number.isFinite(Number(v)))
      ? value.map(Number)
      : base[key].slice();
  };
  return { pos: pick("pos"), rpy: pick("rpy") };
}

/** 度 → 弧度（装配角用度更顺手，算的时候要弧度）。 */
export function deg2rad(deg) {
  return (Number(deg) * Math.PI) / 180;
}

/** 全部传感器的装配表（默认 + 覆盖），供 3D 可视化与射线共用。 */
export function allMounts(overrides = {}) {
  return Object.fromEntries(SENSOR_PLUGINS.map((p) => [p.id, sensorMount(p.id, overrides)]));
}

/**
 * 装配编辑器的六个格子（顺序即显示顺序）。
 * `key` 指向 `mount` 里的哪个数组，`index` 是三轴中的哪一个。
 */
export const MOUNT_FIELDS = [
  { key: "pos", index: 0, axis: "x", label: "位置 x", unit: "m", step: 0.01 },
  { key: "pos", index: 1, axis: "y", label: "位置 y", unit: "m", step: 0.01 },
  { key: "pos", index: 2, axis: "z", label: "位置 z", unit: "m", step: 0.01 },
  { key: "rpy", index: 0, axis: "r", label: "滚转 r", unit: "°", step: 5 },
  { key: "rpy", index: 1, axis: "p", label: "俯仰 p", unit: "°", step: 5 },
  { key: "rpy", index: 2, axis: "y", label: "偏航 y", unit: "°", step: 5 },
];

/**
 * 把编辑器的一格改动写进覆盖表，返回**新的**覆盖表（不改入参）。
 *
 * **改成与默认值相同就删掉这条覆盖** —— 否则"我把 y 拨到 −90 又拨回去"会在表里
 * 留一条与默认值相等的记录，之后默认值一改，这里就静默地不再跟随了。
 * 值非法（NaN / 空）时**保持原样**，避免把输入框打到一半的中间态写进去。
 */
export function applyMountEdit(overrides, id, key, index, value, defaults = DEFAULT_MOUNTS) {
  const base = defaults[id];
  if (!base || !["pos", "rpy"].includes(key)) return { ...overrides };
  // **空值必须单独挡**：`Number(null) === 0`、`Number("") === 0`、`Number([]) === 0`，
  // 这三个都会被下面的 isFinite 放行，然后悄悄把值清成 0。
  // 输入框清空是极常见的中间态（想重打一个数），必须当成"没改"而不是"改成 0"。
  if (value === null || value === undefined || value === "") return { ...overrides };
  const num = Number(value);
  if (!Number.isFinite(num)) return { ...overrides };

  const current = sensorMount(id, overrides);
  const next = { pos: current.pos.slice(), rpy: current.rpy.slice() };
  next[key][index] = num;

  const sameAsDefault = next.pos.every((v, i) => v === base.pos[i])
    && next.rpy.every((v, i) => v === base.rpy[i]);
  const result = { ...overrides };
  if (sameAsDefault) delete result[id];
  else result[id] = next;
  return result;
}

/** 某传感器当前是否被改过装配（用于在 UI 上标出来并提供"重置"）。 */
export function isMountOverridden(id, overrides = {}) {
  return Boolean(overrides?.[id]);
}

/**
 * **单点测距**读数。
 *
 * **没有回波要显式说"无回波"**，不能显示 0 —— 那看起来像"贴着障碍"，
 * 而实际是"这条线上什么都没有"。`maxDist` 只在无回波时用来交代量程。
 */
export function rangefinderReadout({ distance = null, maxDist = null, hit = null } = {}) {
  const has = (v) => v !== null && v !== undefined && Number.isFinite(Number(v));
  const belowRange = Number.isFinite(Number(distance)) && Number(distance) < 0;
  if (hit === false || !has(distance) || belowRange) {
    return { distance: "无回波", note: has(maxDist) ? `量程 ${Number(maxDist).toFixed(2)} m` : "—" };
  }
  return { distance: `${Number(distance).toFixed(3)} m`, note: "单点回波" };
}

/** 默认插件开关：本体感知开、外挂传感器关。 */
export function defaultPlugins() {
  return Object.fromEntries(SENSOR_PLUGINS.map((p) => [p.id, Boolean(p.onboard)]));
}

/** 悬浮窗归属：**只有高级仿真显示**（与 sensor_panels.js 的分层规则一致）。
 *  基础仿真是「本体 + 本体感知」验证，只留 3D 视口与运行 HUD。 */
export function dockVisible(surface) {
  return String(surface || "") === "advanced";
}

/** 该来源在当前插件开关下是否可选。**fail-closed**：未知来源、未知插件一律不可选。 */
export function sourceEnabled(sourceId, plugins = {}) {
  const source = DOCK_SOURCES.find((s) => s.id === sourceId);
  if (!source) return false;
  if (!source.requires) return true;
  return Boolean(plugins[source.requires]);
}

/** 可选来源清单（保序）。 */
export function availableSources(plugins = {}) {
  return DOCK_SOURCES.filter((s) => sourceEnabled(s.id, plugins));
}

/** 当前来源被关掉后，回落到第一个可选来源；没有可选项则返回空串。 */
export function resolveSource(currentId, plugins = {}) {
  if (sourceEnabled(currentId, plugins)) return currentId;
  const first = availableSources(plugins)[0];
  return first ? first.id : "";
}

/** 世界系线速度：把**体轴**线速度按偏航角旋到世界系。
 *
 *  `yaw` 绕 z 轴、逆时针为正（MuJoCo 约定）。**只转 yaw 是刻意的**：
 *  里程计的"全局速度"是地面投影上的量，俯仰/横滚不该把水平速度拧到竖直方向去。 */
export function bodyToWorldVelocity(velBody, yaw) {
  const vx = Number(velBody?.[0]);
  const vy = Number(velBody?.[1]);
  const vz = Number(velBody?.[2]);
  if (![vx, vy, vz].every(Number.isFinite)) return null;
  const c = Math.cos(Number(yaw) || 0);
  const s = Math.sin(Number(yaw) || 0);
  return [vx * c - vy * s, vx * s + vy * c, vz];
}

/**
 * **全局里程计**读数：世界坐标系下的位姿、速度与累计里程。
 *
 * **"全局"是重点**：给的是**世界坐标系**下的量与**累计里程**，
 * 而不是机体系速度 —— 两者在导航里的含义完全不同（前者能直接对地图，后者只能看快慢）。
 * **缺值一律「—」**，绝不显示 `0.00`：那看起来像真读数（`Number(null) === 0`）。
 */
export function odomReadout({
  pose = null,
  angular = null,
  velBody = null,
  mileage = null,
  digits = 3,
  angleDigits = 1,
} = {}) {
  const fmt = (value, unit = "", d = digits) => {
    if (value === null || value === undefined || value === "") return "—";
    const num = Number(value);
    return Number.isFinite(num) ? `${num.toFixed(d)}${unit}` : "—";
  };
  const vec = (arr, fn) => (Array.isArray(arr) && arr.length ? arr.map(fn).join(" / ") : "—");
  const has = (v) => v !== null && v !== undefined && Number.isFinite(Number(v));
  // 角度单独精度：3 位小数在姿态上是假精度（0.001° 无意义），1 位是这类读数的惯用粒度。
  const deg = (rad) => fmt((Number(rad) * 180) / Math.PI, "°", angleDigits);

  const yaw = has(pose?.yaw) ? Number(pose.yaw) : 0;
  const world = bodyToWorldVelocity(velBody, yaw);
  const attitudeParts = [pose?.roll, pose?.pitch, pose?.yaw];

  return {
    // x/y 是平面位置的核心：任一缺值则整行不可信；z 单独判定，缺了显示「—」而不是 0。
    position: has(pose?.x) && has(pose?.y)
      ? `${fmt(pose.x)} , ${fmt(pose.y)} , ${has(pose.z) ? fmt(pose.z) : "—"}`
      : "—",
    // 分量各自判定：某个角缺值只让那一格显「—」，不要用 0 把它伪装成真读数。
    attitude: attitudeParts.some(has)
      ? attitudeParts.map((v) => (has(v) ? deg(v) : "—")).join(" / ")
      : "—",
    worldVelocity: world ? vec(world, (v) => fmt(v)) : "—",
    angular: Array.isArray(angular) && angular.length >= 3 ? vec(angular.slice(0, 3), (v) => fmt(v)) : "—",
    mileage: fmt(mileage, " m"),
  };
}

/** 悬浮窗读数表的行定义（顺序即显示顺序）。 */
export function readoutRows(sourceId, values = {}) {
  if (sourceId === "odom") {
    return [
      ["位置 x , y , z (m)", values.position],
      ["姿态 r / p / y (deg)", values.attitude],
      ["世界系速度 x/y/z", values.worldVelocity],
      ["累计里程", values.mileage],
    ];
  }
  if (sourceId === "imu") {
    return [
      ["角速度 x / y / z", values.angular],
      ["姿态 r / p / y (deg)", values.attitude],
      ["机体高度 (m)", values.baseHeight],
    ];
  }
  if (sourceId === "rangefinder") {
    return [
      ["距离", values.distance],
      ["装配位置 x / y / z (m)", values.mountPos],
      ["装配角度 r / p / y (deg)", values.mountRpy],
    ];
  }
  // 以下四个是"有图也有数"的来源：数用来交代**这张图是什么尺度**（扫了多少、看多远），
  // 光看图读不出量纲，容易把 4 m 的地形当成 40 m。
  if (sourceId === "height") {
    return [
      ["扫描范围", values.scanExtent],
      ["网格", values.scanGrid],
      ["命中 / 总数", values.hitRatio],
      ["装配位置 x / y / z (m)", values.mountPos],
    ];
  }
  if (sourceId === "lidar") {
    return [
      ["扇扫", values.fanSpec],
      ["命中 / 总数", values.hitRatio],
      ["最近回波", values.nearest],
      ["装配角度 r / p / y (deg)", values.mountRpy],
    ];
  }
  if (sourceId === "cloud") {
    return [
      ["点数", values.pointCount],
      ["范围 x / y (m)", values.cloudBounds],
      ["来源", values.cloudSource],
      ["装配位置 x / y / z (m)", values.mountPos],
    ];
  }
  if (sourceId === "rgb") {
    return [
      ["预览分辨率", values.rgbSize],
      ["视场角", values.rgbFov],
      ["渲染方式", values.rgbBackend],
      ["装配位置 x / y / z (m)", values.mountPos],
    ];
  }
  return [];
}
