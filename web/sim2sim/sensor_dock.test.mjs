// 悬浮窗纯逻辑单测（自包含断言，与 raycast / sensor_panels 同风格）。
//
// 这里钉的是**规则**而不是像素：插件默认开关、来源与插件的依赖关系（fail-closed）、
// 来源被关掉后的回落、以及"全局里程计"最要紧的一条 —— **世界系速度**要按偏航角转，不是机体系原值。
import assert from "node:assert/strict";
import {
  allMounts,
  applyMountEdit,
  availableSources,
  bodyToWorldVelocity,
  DEFAULT_MOUNTS,
  defaultPlugins,
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
  sourceEnabled,
} from "./sensor_dock.js";

// 1) 默认插件：**本体感知开、外挂传感器关**（"插件可以选择"，要就勾上）
{
  const plugins = defaultPlugins();
  assert.equal(plugins.odom, true, "odom 是本体感知，默认开");
  assert.equal(plugins.imu, true, "IMU 是本体感知，默认开");
  assert.equal(plugins.depth, false, "深度相机是外挂传感器，默认关");
  assert.equal(plugins.height, false);
  assert.equal(plugins.lidar, false);
  assert.equal(plugins.rgb, false);
  assert.equal(Object.keys(plugins).length, SENSOR_PLUGINS.length);
}

// 2) 悬浮窗归属：**只有高级仿真**（基础仿真只留 3D 视口与运行 HUD）
{
  assert.equal(dockVisible("advanced"), true);
  assert.equal(dockVisible(""), false, "默认（基础仿真）不显示");
  assert.equal(dockVisible("basic"), false);
}

// 3) 来源 ↔ 插件依赖：插件没勾就**不可选**；未知来源/未知插件一律 false（fail-closed）
{
  assert.equal(sourceEnabled("trail", {}), true, "轨迹不依赖插件");
  assert.equal(sourceEnabled("depth", {}), false, "深度相机插件没开 ⇒ 来源不可选");
  assert.equal(sourceEnabled("depth", { depth: true }), true);
  assert.equal(sourceEnabled("odom", { odom: false }), false);
  assert.equal(sourceEnabled("nope", { nope: true }), false, "未知来源必须 false");
  assert.equal(sourceEnabled("height", {}), false, "未知插件（height 未声明）也必须 false");
}

// 4) 可选来源清单随插件增减；被关掉后**回落到第一个可选项**
{
  assert.deepEqual(
    availableSources({}).map((s) => s.id),
    ["trail"],
    "默认只有不依赖插件的来源可用",
  );
  const withDepth = availableSources({ depth: true, lidar: true });
  assert.deepEqual(withDepth.map((s) => s.id), ["depth", "trail", "lidar", "cloud"]);
  assert.equal(resolveSource("depth", {}), "trail", "当前来源被关 ⇒ 回落到第一个可选项");
  assert.equal(resolveSource("depth", { depth: true }), "depth", "仍可选则保持不变");
  assert.equal(resolveSource("nope", {}), "trail", "未知来源也要回落");
}

// 5) **世界系速度**：偏航 0 时与体轴一致；偏航 90° 时体轴 +x 应变成世界系 +y
{
  assert.deepEqual(bodyToWorldVelocity([1, 0, 0], 0), [1, 0, 0]);
  const turned = bodyToWorldVelocity([1, 0, 0], Math.PI / 2);
  assert.ok(Math.abs(turned[0]) < 1e-12 && Math.abs(turned[1] - 1) < 1e-12, `应转到 +y，实际 ${turned}`);
  assert.deepEqual(bodyToWorldVelocity([0, 0, -0.5], Math.PI / 2), [0, 0, -0.5], "z 分量不该被 yaw 影响");
  assert.equal(bodyToWorldVelocity(null, 0), null, "缺值返回 null 而不是 0 向量");
  assert.equal(bodyToWorldVelocity([1, NaN, 0], 0), null);
}

// 6) 全局里程计读数：位置三轴、姿态度、世界系速度、累计里程
{
  const r = odomReadout({
    pose: { x: 1.2345, y: -0.5, z: 0.42, roll: 0, pitch: 0, yaw: Math.PI / 2 },
    angular: [0.1, 0.2, 0.3],
    velBody: [1, 0, 0],
    mileage: 12.4801,
  });
  assert.equal(r.position, "1.234 , -0.500 , 0.420");
  assert.equal(r.attitude, "0.0° / 0.0° / 90.0°");
  assert.equal(r.worldVelocity, "0.000 / 1.000 / 0.000", "yaw 90° 时整体速度应落在世界系 +y");
  assert.equal(r.mileage, "12.480 m");
}

// 7) 缺值必须是「—」，不能是 0.00（`Number(null) === 0` 会让空数据看起来像真读数）
{
  const empty = odomReadout({});
  assert.equal(empty.position, "—");
  assert.equal(empty.attitude, "—");
  assert.equal(empty.worldVelocity, "—");
  assert.equal(empty.mileage, "—");
  assert.equal(empty.angular, "—");
  const partial = odomReadout({ pose: { x: null, y: 2 } });
  assert.equal(partial.position, "—", "x 缺值即整行不可信");
}

// 8) 读数表行定义：odom 与 imu 各自成表，未知来源为空表
{
  const odomRows = readoutRows("odom", { position: "1 , 2 , 0", attitude: "a", worldVelocity: "v", mileage: "3 m" });
  assert.deepEqual(odomRows.map((row) => row[0]), ["位置 x , y , z (m)", "姿态 r / p / y (deg)", "世界系速度 x/y/z", "累计里程"]);
  assert.deepEqual(odomRows.map((row) => row[1]), ["1 , 2 , 0", "a", "v", "3 m"]);
  assert.ok(readoutRows("imu", {}).length > 0);
  assert.deepEqual(readoutRows("depth", {}), [], "canvas 型来源没有读数表");
  assert.deepEqual(readoutRows("nope", {}), []);
}

// 9) **默认装配**：每个传感器都有位置与角度；覆盖只影响该传感器，缺项回落默认
{
  const mounts = allMounts();
  for (const p of SENSOR_PLUGINS) {
    assert.ok(mounts[p.id], `${p.id} 缺默认装配`);
    assert.equal(mounts[p.id].pos.length, 3, `${p.id} 位置应是三轴`);
    assert.equal(mounts[p.id].rpy.length, 3, `${p.id} 角度应是三轴`);
  }
  // 朝向约定：局部 −z 是"看"的方向 ⇒ 朝前 = 绕 y 转 −90°
  assert.deepEqual(DEFAULT_MOUNTS.rangefinder.rpy, [0, -90, 0], "单点测距默认朝前");
  assert.deepEqual(DEFAULT_MOUNTS.height.rpy, [0, 0, 0], "高度雷达默认朝下");
  // 覆盖
  const overridden = sensorMount("depth", { depth: { pos: [1, 2, 3] } });
  assert.deepEqual(overridden.pos, [1, 2, 3], "覆盖应生效");
  assert.deepEqual(overridden.rpy, DEFAULT_MOUNTS.depth.rpy, "没覆盖的字段回落默认");
  assert.equal(sensorMount("nope", {}), null, "未知传感器返回 null");
  const bad = sensorMount("imu", { imu: { pos: [1, 2] } });
  assert.deepEqual(bad.pos, DEFAULT_MOUNTS.imu.pos, "非法覆盖要回落而不是崩");
}

// 10) **可视化模型**：每个传感器都有外形规格，且 kind/size 与 kind 语义匹配
{
  for (const p of SENSOR_PLUGINS) {
    const model = SENSOR_MODELS[p.id];
    assert.ok(model, `${p.id} 缺可视化模型`);
    assert.ok(["box", "sphere", "cylinder"].includes(model.kind), `${p.id} 的 kind 不认识`);
    assert.ok(Array.isArray(model.size) && model.size.length >= 1, `${p.id} 缺尺寸`);
    assert.ok(Number.isFinite(model.color), `${p.id} 缺颜色`);
    assert.ok(model.label, `${p.id} 缺标签`);
  }
  assert.equal(SENSOR_MODELS.odom.kind, "sphere");
  assert.equal(SENSOR_MODELS.lidar.kind, "cylinder");
}

// 11) **单点测距**读数：命中给米，**未命中必须说"无回波"**（显示 0 会像贴着障碍）
{
  // 用不落在二进制边界上的数：1.2345 实际是 1.23449…，toFixed(3) 得 1.234（正常浮点行为，不是 bug）。
  assert.deepEqual(rangefinderReadout({ distance: 2.5 }), { distance: "2.500 m", note: "单点回波" });
  assert.deepEqual(rangefinderReadout({ distance: 1.2346 }), { distance: "1.235 m", note: "单点回波" });
  assert.equal(rangefinderReadout({ distance: -1 }).distance, "无回波", "未命中（负数）应说无回波");
  assert.equal(rangefinderReadout({ hit: false, maxDist: 5 }).distance, "无回波");
  assert.equal(rangefinderReadout({ hit: false, maxDist: 5 }).note, "量程 5.00 m");
  assert.equal(rangefinderReadout({}).distance, "无回波");
  assert.equal(rangefinderReadout({ distance: 0 }).distance, "0.000 m", "0 是真值：正贴着");
}

// 12) 单点测距的读数表 + 来源依赖（插件没勾就不可选）
{
  const rows = readoutRows("rangefinder", { distance: "1.235 m", mountPos: "0.3 , 0 , 0.05", mountRpy: "0 / -90 / 0" });
  assert.deepEqual(rows.map((r) => r[0]), ["距离", "装配位置 x / y / z (m)", "装配角度 r / p / y (deg)"]);
  assert.deepEqual(rows.map((r) => r[1]), ["1.235 m", "0.3 , 0 , 0.05", "0 / -90 / 0"]);
  assert.equal(sourceEnabled("rangefinder", {}), false, "单点测距插件没开 ⇒ 来源不可选");
  assert.equal(sourceEnabled("rangefinder", { rangefinder: true }), true);
  assert.deepEqual(
    availableSources({ rangefinder: true }).map((s) => s.id),
    ["rangefinder", "trail"],
  );
}

// 13) 装配编辑：写入覆盖、**改回默认值就删掉覆盖**、非法值不动
{
  assert.deepEqual(MOUNT_FIELDS.map((f) => f.label), ["位置 x", "位置 y", "位置 z", "滚转 r", "俯仰 p", "偏航 y"]);
  assert.deepEqual(MOUNT_FIELDS.map((f) => f.key), ["pos", "pos", "pos", "rpy", "rpy", "rpy"]);
  assert.deepEqual(MOUNT_FIELDS.map((f) => f.index), [0, 1, 2, 0, 1, 2]);

  // 改一格 ⇒ 该格进覆盖，其余保持默认
  let ov = {};
  ov = applyMountEdit(ov, "depth", "pos", 0, 0.9);
  assert.deepEqual(sensorMount("depth", ov).pos, [0.9, DEFAULT_MOUNTS.depth.pos[1], DEFAULT_MOUNTS.depth.pos[2]]);
  assert.equal(isMountOverridden("depth", ov), true);

  // 再改另一个字段 ⇒ 累积
  ov = applyMountEdit(ov, "depth", "rpy", 1, -45);
  assert.deepEqual(sensorMount("depth", ov).rpy, [DEFAULT_MOUNTS.depth.rpy[0], -45, DEFAULT_MOUNTS.depth.rpy[2]]);

  // ↓ 全部拨回默认 ⇒ **覆盖整条删掉**，不是留一条等于默认值的记录
  ov = applyMountEdit(ov, "depth", "pos", 0, DEFAULT_MOUNTS.depth.pos[0]);
  ov = applyMountEdit(ov, "depth", "rpy", 1, DEFAULT_MOUNTS.depth.rpy[1]);
  assert.deepEqual(ov, {}, "全部回到默认后不应再留覆盖");
  assert.equal(isMountOverridden("depth", ov), false);

  // 非法值（NaN / 空串 / null）保持原样，不把输入框中间态写进去
  const before = { imu: { pos: [1, 2, 3], rpy: [0, 0, 0] } };
  assert.deepEqual(applyMountEdit(before, "imu", "pos", 0, ""), before);
  assert.deepEqual(applyMountEdit(before, "imu", "pos", 0, NaN), before);
  assert.deepEqual(applyMountEdit(before, "imu", "pos", 0, null), before, "null 的 Number() 是 0，必须挡掉");
  // 未知传感器 / 未知字段名一律原样返回
  assert.deepEqual(applyMountEdit(before, "nope", "pos", 0, 5), before);
  assert.deepEqual(applyMountEdit(before, "imu", "nope", 0, 5), before);
  // 不改入参
  assert.deepEqual(before, { imu: { pos: [1, 2, 3], rpy: [0, 0, 0] } }, "入参必须不被修改");
}

// 14) 采样规格：三个射线驱动的来源各自**有量程**，且刻度自洽（分辨率 × 网格跨度）
{
  for (const id of ["height", "lidar", "cloud"]) {
    assert.ok(SCAN_SPECS[id], `${id} 应有采样规格`);
  }
  assert.ok(SCAN_SPECS.height.side >= 8, "网格太稀就看不出地形起伏");
  assert.ok(SCAN_SPECS.height.extent > 0, "扫描半径必须为正");
  assert.ok(SCAN_SPECS.height.maxDist > SCAN_SPECS.height.extent, "量程要盖住斜向格点（约 √2 × 半径）");
  assert.ok(SCAN_SPECS.lidar.count >= 90, "线数太少极坐标图会缺口");
  assert.equal(
    SCAN_SPECS.lidar.maxDist, SCAN_SPECS.cloud.maxDist,
    "点云与 LiDAR 共用同一次扫描 ⇒ 量程必须一致，否则两图对不上",
  );
  assert.ok(SCAN_SPECS.rgb.near > 0, "near 平面为正（它负责裁掉镜头前的机身外壳）");
  assert.ok(SCAN_SPECS.rgb.near < SCAN_SPECS.rgb.far);
}

// 15) 有图也有数的四个来源：**读数表不能是空的**
//     （光看图读不出量纲，容易把 4 m 的地形当成 40 m）
{
  for (const [id, values] of [
    ["height", { scanExtent: "4 m × 4 m", scanGrid: "24 × 24", hitRatio: "100 / 576", mountPos: "0 / 0 / 0" }],
    ["lidar", { fanSpec: "360° / 240 线", hitRatio: "3 / 240", nearest: "1.2 m", mountRpy: "0 / 0 / 0" }],
    ["cloud", { pointCount: "3", cloudBounds: "1 × 2", cloudSource: "LiDAR 同一次扫描", mountPos: "0 / 0 / 0" }],
    ["rgb", { rgbSize: "160 × 120", rgbFov: "60°（垂直）", rgbBackend: "three.js", mountPos: "0 / 0 / 0" }],
  ]) {
    const rows = readoutRows(id, values);
    assert.equal(rows.length, 4, `${id} 应有 4 行读数`);
    assert.ok(rows.every(([, v]) => typeof v === "string" && v.length), `${id} 不应有空值`);
  }
  // 缺值时靠 UI 的 `?? "—"` 兜底，但行定义本身必须**始终给出四行**（不能随数据增减行数，
  // 否则读数表会一跳一跳）。
  assert.equal(readoutRows("lidar", {}).length, 4);
}

console.log("sensor_dock: 15 checks ok");
