// 高级仿真**传感器框架** · 目录（单一真值）。
//
// 为什么要有这一层：此前每种传感器的参数（24×24 网格、240 线、87° HFOV、60×86 深度…）
// 散落在三处——`sensor_dock.js` 的 SCAN_SPECS、`app.js` 的扫描函数、`pie_depth.js` 的常量，
// 且**没有一处说明这些数字凭什么这么定**。本目录把"有哪些传感器、每种用什么采样 pattern、
// 加什么噪声、凭什么"收敛成一份数据，页面与测试都读它。
//
// **与训练栈对齐**：pattern 语义逐条对标本仓训练栈
// `mjlab/sensor/raycast_sensor.py` 的三种 PatternCfg（GridPattern / RingPattern /
// PinholeCameraPattern）——浏览器端与训练端对同一种传感器的描述必须是同一套语言，
// 否则"仿真里看到的"和"训练时吃到的"永远对不上。
//
// **本体自知 vs 外挂**（用户裁决 2026-09-21）：`onboard: true` 只给**不依赖外部世界模型**
// 的器件。一台"盲狗"只有 IMU 与电机编码器（编码器不是插件，是机器人自身状态）。里程计
// （odom）是外部估计管线的输出，实体机器人全局定位至今是开放问题，故归外挂、默认关。

/** 采样 pattern 的种类（与 mjlab raycast_sensor 的 PatternCfg 一一对应，外加 point）。 */
export const PATTERN_KINDS = ["point", "grid", "ring", "pinhole", "fan"];

/**
 * 传感器目录。每条字段的含义：
 *   id/label    —— 坞里显示的身份
 *   onboard     —— 是否本体自知（默认开关的唯一依据）
 *   kind        —— readout（数值表）/ canvas（图像）/ rays（射线类）/ camera（渲染类）/ contact（接触）
 *   pattern     —— 射线类传感器的采样 pattern（对应 sensor_patterns.js）
 *   noise       —— 该传感器默认启用的退化模型（对应 sensor_noise.js），null = 理想传感器
 *   mountable   —— 是否有物理装配位姿（odom 没有：它不是器件）
 *   upstream    —— **凭什么这么定**：训练栈/上游资源的可核对出处
 */
export const SENSOR_CATALOG = [
  {
    id: "imu",
    label: "IMU",
    onboard: true,
    kind: "readout",
    pattern: null,
    noise: "imu",
    mountable: true,
    defaultMount: { pos: [0, 0, 0.05], rpy: [0, 0, 0] },
    hint: "三轴角速度 + 重力投影（本体自知，盲狗策略的输入之一）",
    upstream: "mjlab/sensor/builtin_sensor.py（本体状态直读）；噪声模型参考 newton/_src/sensors/sensor_imu.py 的偏置+白噪声结构",
  },
  {
    id: "odom",
    label: "全局里程计 odom",
    onboard: false,
    kind: "readout",
    pattern: null,
    noise: null,
    mountable: false,
    defaultMount: { pos: [0, 0, 0], rpy: [0, 0, 0] },
    hint: "世界系位姿（外部估计管线的输出，本体并不知道；全局定位仍是开放问题）",
    upstream: "newton/_src/sensors/sensor_frame_transform.py（世界系变换的归属）；外部管线实见 00_resources/g1-mujoco-ros2-nav-sim-.../lidar_localization_ros2",
  },
  {
    id: "rangefinder",
    label: "单点测距",
    onboard: false,
    kind: "rays",
    pattern: "point",
    noise: "range",
    mountable: true,
    defaultMount: { pos: [0.30, 0, 0.05], rpy: [0, -90, 0] },
    hint: "沿装配方向打一条射线，给出到最近障碍的距离",
    upstream: "mjlab raycast_sensor 的 point 用法（单射线）；量测退化参考 robosuite demo_sensor_corruption",
  },
  {
    id: "height",
    label: "高度扫描（雷达）",
    onboard: false,
    kind: "rays",
    pattern: "grid",
    noise: "range",
    mountable: true,
    defaultMount: { pos: [0, 0, 0.06], rpy: [0, 0, 0] },
    hint: "机周网格高度场（多起点、同向朝下）",
    upstream: "mjlab GridPatternCfg 语义 + backend/height_scan.py 的 187 网格契约（x -0.8..0.8 共 17、y -0.5..0.5 共 11、x 主序 index=i_x*11+i_y、值=base_z−terrain_z）",
    patternParams: {
      size: [1.6, 1.0],
      resolution: 0.1,
      direction: [0, 0, -1],
      // 与 height_scan.py 的 grid_spec() 逐值对齐（A 类绑定认的是这一份，不是坞里画得好看的那份）
      order: "x_major",
      grid: { nx: 17, ny: 11, x0: -0.8, y0: -0.5, order: "x_major", value: "base_z_minus_terrain_z" },
    },
  },
  {
    id: "lidar_height_scan",
    label: "雷达高度扫描",
    onboard: false,
    kind: "rays",
    pattern: "grid",
    noise: "range",
    mountable: false,
    // **派生视图**：与 LiDAR 共用同一次扫描，不是独立插件——坞里勾 LiDAR 就该能看到它，
    // 再给一个独立开关会让人以为"这是另一个传感器"（勾错一个就看不着，且没有任何提示）。
    derivedFrom: "lidar",
    defaultMount: { pos: [0, 0, 0], rpy: [0, 0, 0] },
    hint: "LiDAR 点云按 187 网格聚合 min-z（与 heightfield 同格，可逐格对齐）",
    upstream: "backend/height_scan.py::point_cloud_to_heights（min_z_per_cell，空单元填 fill）",
    patternParams: {
      size: [1.6, 1.0],
      resolution: 0.1,
      direction: [0, 0, -1],
      order: "x_major",
      grid: { nx: 17, ny: 11, x0: -0.8, y0: -0.5, order: "x_major", value: "base_z_minus_min_z", aggregate: "min" },
    },
  },
  {
    id: "lidar",
    label: "LiDAR（射线）",
    onboard: false,
    kind: "rays",
    pattern: "fan",
    noise: "range",
    mountable: true,
    defaultMount: { pos: [0.05, 0, 0.16], rpy: [0, 0, 0] },
    hint: "水平扇扫 → 极坐标图与点云（两图同源）",
    upstream: "mjlab RingPatternCfg 的单环展开（同一起点、方向均布）；MJCF 挂法参考 mujoco_3d_lidar 插件",
    patternParams: { count: 240, maxDist: 12 },
  },
  {
    id: "depth",
    label: "深度相机",
    onboard: false,
    kind: "camera",
    pattern: "pinhole",
    noise: "depth",
    mountable: true,
    defaultMount: { pos: [0.28, 0, 0.08], rpy: [0, -80, 0] },
    hint: "机头前向针孔相机深度帧（裁剪/高斯/截止，对齐训练侧观测）",
    upstream: "mjlab/sensor/raycast_sensor.py::PinholeCameraPatternCfg + camera_sensor；观测后处理对齐 parkour_mjlab mdp/observations.py::camera_depth",
    patternParams: { width: 106, height: 60, fovy: 66 },
  },
  {
    id: "rgb",
    label: "RGB 相机",
    onboard: false,
    kind: "camera",
    pattern: "pinhole",
    noise: null,
    mountable: true,
    // 装配 x 取 0.345：**躯干壳体之外**（go2 躯干前缘 ≈0.30m，壳内 x=0.27 会让 near=0.12
    // 裁不掉全部壳体，相机看 own mesh）。与 pie 深度相机的机头位同源，两个前向相机并排。
    defaultMount: { pos: [0.345, 0, 0.07], rpy: [0, -80, 0] },
    hint: "three.js 离屏渲染（非 MuJoCo 原生，与训练栈 camera_sensor 的 RGB 不同源）",
    upstream: "mjlab camera_sensor 的 RGB/分割走 MuJoCo 渲染；本处为浏览器预览，已注明不同源",
    patternParams: { width: 160, height: 120, fovy: 60 },
  },
  {
    id: "foot_contact",
    label: "足底接触",
    onboard: false,
    kind: "contact",
    pattern: null,
    noise: "contact",
    mountable: false,
    defaultMount: { pos: [0, 0, 0], rpy: [0, 0, 0] },
    hint: "四足接触力/是否着地（H21/H22 的素材；训练栈早有，浏览器坞此前没有）",
    upstream: "mjlab/sensor/contact_sensor.py；genesis-world sensors/contact_force",
  },
];

/** 目录里按 id 取条目（未知 id 返回 null，调用方 fail-closed）。 */
export function sensorEntry(id) {
  return SENSOR_CATALOG.find((item) => item.id === id) || null;
}

/** 默认插件开关：**只有本体自知开**（当前即 IMU 一个）。
 *  派生视图（`derivedFrom`）不占开关——它随被派生传感器一起出现。 */
export function defaultPlugins() {
  return Object.fromEntries(
    SENSOR_CATALOG.filter((item) => !item.derivedFrom).map((item) => [item.id, Boolean(item.onboard)]),
  );
}

/** 该传感器的 pattern 参数（目录默认值 + 调用方覆盖），无 pattern 返回 null。 */
export function patternParams(id, overrides = {}) {
  const entry = sensorEntry(id);
  if (!entry || !entry.pattern) return null;
  return { ...(entry.patternParams || {}), ...(overrides || {}) };
}


/** LiDAR 点云 → 187 维高度扫描（min-z 聚合）——`backend/height_scan.py::point_cloud_to_heights`
 *  的浏览器侧同语义实现：每格取落入其中点的**最低 z**，值 = base_z − min_z，空单元 null
 *  （不编高度——编一个"看着有"的高度比空槽危险得多）。
 *
 *  @param {Array<[number,number,number]>} points 世界系命中点
 *  @param {{x: number, y: number, z: number, yaw: number}} base 机身位姿（yaw 弧度）
 *  @param {object} grid 网格契约（默认取 lidar_height_scan 条目）
 *  @returns {{field: (number|null)[], filled: number, total: number}}
 */
export function aggregateHeightScan(points, base, grid = null) {
  const spec = grid || patternParams("lidar_height_scan")?.grid || {};
  const nx = spec.nx || 17;
  const ny = spec.ny || 11;
  const x0 = spec.x0 ?? -0.8;
  const y0 = spec.y0 ?? -0.5;
  const step = 0.1;
  const buckets = new Array(nx * ny).fill(null);
  const yaw = Number(base?.yaw) || 0;
  const cos = Math.cos(-yaw);
  const sin = Math.sin(-yaw);
  const bx = Number(base?.x) || 0;
  const by = Number(base?.y) || 0;
  const bz = Number(base?.z) || 0;
  for (const point of points || []) {
    if (!point || point.length < 3) continue;
    const dx = point[0] - bx;
    const dy = point[1] - by;
    // 世界 → 机身（仅平面旋转；z 不参与）
    const ox = dx * cos - dy * sin;
    const oy = dx * sin + dy * cos;
    const ix = Math.round((ox - x0) / step);
    const iy = Math.round((oy - y0) / step);
    if (ix < 0 || ix >= nx || iy < 0 || iy >= ny) continue;
    const index = ix * ny + iy;
    if (buckets[index] === null || point[2] < buckets[index]) buckets[index] = point[2];
  }
  return {
    field: buckets.map((z) => (z === null ? null : bz - z)),
    filled: buckets.filter((z) => z !== null).length,
    total: nx * ny,
  };
}
