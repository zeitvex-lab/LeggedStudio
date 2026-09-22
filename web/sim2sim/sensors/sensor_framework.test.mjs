// 传感器框架单测（`node web/sim2sim/sensors/sensor_framework.test.mjs`）。
//
// 钉四件事：
//   1. **目录即真值**：本体自知只有 IMU（odom 是外部估计管线的输出，默认关）；
//      每条传感器都带 `upstream` 出处——没有出处的条目不许进目录；
//   2. **pattern 语义对标训练栈**：grid 的点数/方向、fan 的方向均布、pinhole 的焦距与
//      像素中心，都与 mjlab raycast_sensor 的三种 PatternCfg 同口径（逐值对拍少量样本）；
//      **唯一例外是 pinhole 的行方向**——上游注释 "+Y down" 与右手系矛盾，本框架以真实
//      渲染图像为准（见 `screen_frame.js` 头部与下面第 4 组断言）；
//   3. **噪声可复现**：同 seed 同序列；不同 seed 不同序列；miss/超量程/丢帧语义正确；
//   4. **fail-closed**：未知 pattern / 未知噪声 / 未知传感器 id 一律返回 null，不猜。
import assert from "node:assert/strict";
import {
  PATTERN_KINDS,
  SENSOR_CATALOG,
  defaultPlugins,
  patternParams,
  sensorEntry,
} from "./sensor_catalog.js";
import { buildPattern, fanPattern, gridPattern, pinholePattern, pointPattern, ringPattern } from "./sensor_patterns.js";
import {
  createContactNoise,
  createDepthNoise,
  createGaussian,
  createImuNoise,
  createNoise,
  createRandom,
  createRangeNoise,
} from "./sensor_noise.js";

// 1) 目录：本体自知只有 IMU；每条都有上游出处
{
  const plugins = defaultPlugins();
  const enabled = Object.entries(plugins).filter(([, on]) => on).map(([id]) => id);
  assert.deepEqual(enabled, ["imu"], "默认开启的必须只有 IMU（盲狗的全部本体自知）");
  assert.equal(plugins.odom, false, "odom 是外部里程计管线的输出，不是本体自知");
  for (const item of SENSOR_CATALOG) {
    assert.ok(item.upstream && item.upstream.length > 10, `${item.id} 必须写清上游依据（凭什么这么定）`);
    assert.ok(item.kind && item.hint, `${item.id} 必须有 kind 与 hint`);
    if (item.pattern) assert.ok(PATTERN_KINDS.includes(item.pattern), `${item.id} 的 pattern 必须是已知种类`);
  }
  // 目录 id 唯一
  const ids = SENSOR_CATALOG.map((s) => s.id);
  assert.equal(new Set(ids).size, ids.length, "传感器 id 必须唯一");
  // 未知 id fail-closed
  assert.equal(sensorEntry("no_such_sensor"), null);
  assert.equal(patternParams("no_such_sensor"), null);
  assert.equal(patternParams("imu"), null, "无 pattern 的传感器返回 null 而不是空对象");
}

// 2) grid pattern：点数与 mjlab GridPatternCfg 同口径（size 4m / res 0.1m ⇒ 41×41）
{
  const grid = gridPattern({ size: [4, 4], resolution: 0.1, direction: [0, 0, -1] });
  assert.equal(grid.count, 41 * 41, "4m/0.1m 网格应为 41×41（与 mjlab arange 取点一致）");
  // 方向全部相同且已归一
  for (const d of grid.directions) assert.deepEqual(d, [0, 0, -1]);
  // 起点铺满 [-2,2]²，**降序**：offsets[0] 是 (+x,+y) 角（俯视图第 0 行=机头方向）
  assert.deepEqual(grid.offsets[0], [2, 2, 0]);
  assert.deepEqual(grid.offsets[grid.count - 1], [-2, -2, 0]);
  // 非整数倍 resolution 也要能出点（不抛错、不塌成 1 个点）
  const odd = gridPattern({ size: [1, 1], resolution: 0.3 });
  assert.ok(odd.count >= 4 && odd.count <= 25, `1m/0.3m 应得 4×4=16 点，实得 ${odd.count}`);
  // 方向非朝下时照样归一（斜面扫描）
  const tilted = gridPattern({ size: [1, 1], resolution: 0.5, direction: [0, 0.3, -1] });
  const n = Math.hypot(...tilted.directions[0]);
  assert.ok(Math.abs(n - 1) < 1e-9, "pattern 方向必须归一");
}

// 3) fan pattern：同一起点、方向均布一整圈（RingPattern 的半径 0 退化）
{
  const fan = fanPattern({ count: 240 });
  assert.equal(fan.count, 240);
  assert.equal(fan.angles.length, 240);
  assert.ok(Math.abs(fan.angles[1] - fan.angles[0] - (2 * Math.PI / 240)) < 1e-12, "角度均布");
  for (const o of fan.offsets) assert.deepEqual(o, [0, 0, 0], "fan 的所有射线同起点");
  for (const d of fan.directions) assert.ok(Math.abs(Math.hypot(d[0], d[1]) - 1) < 1e-12, "fan 方向在局部平面内");
  assert.equal(fanPattern({ count: 1 }).count, 1, "count=1 不塌");
}

// 4) pinhole pattern：焦距与像素中心（与 PinholeCameraPatternCfg 同口径），
//    **朝向以真实渲染图像为准**：行 0 = 图像顶部、列 0 = 图像左侧、图像上 = 局部 +y。
//    （2026-09-22 修：此前按上游注释 "+Y down" 把 y 取了正号 ⇒ 与真实图像上下颠倒；
//     依据见 screen_frame.js 头部：mujoco.Renderer.render 的 np.flipud + 右手系定理。）
{
  // 奇数宽高才有**正中像素**（偶数宽的正中落在两像素之间，不是缺陷）
  const cam = pinholePattern({ width: 5, height: 3, fovy: 90 });
  assert.equal(cam.count, 15);
  // fovy=90° ⇒ focal = 0.5*h/tan(45°) = 1.5；正中像素方向应为 (0,0,-1)
  const mid = cam.directions[1 * 5 + 2]; // 第 1 行第 2 列
  assert.ok(Math.abs(mid[0]) < 1e-9 && Math.abs(mid[1]) < 1e-9 && Math.abs(mid[2] + 1) < 1e-9, "中心像素朝 −z");
  // 光轴是局部 −z（MuJoCo 相机约定）
  for (const d of cam.directions) assert.ok(d[2] < 0, "针孔射线都必须朝 −z 半球");
  // 左上与右下方向相反（对称性）。第 0 行是图像**顶部** ⇒ 局部 +y；第 0 列是最左 ⇒ 局部 −x
  const tl = cam.directions[0];
  const br = cam.directions[cam.count - 1];
  assert.ok(tl[0] < 0 && br[0] > 0, "左右应发散（列 0 在左 ⇒ x 为负）");
  assert.ok(tl[1] > 0 && br[1] < 0, "上下应发散（行 0 在顶 ⇒ 局部 +y；MuJoCo 相机图像上 = +y）");
  assert.ok(Math.abs(tl[0] + br[0]) < 1e-9 && Math.abs(tl[1] + br[1]) < 1e-9, "对角色应严格反向");
  // 焦距 sanity：fovy 90°、h=3 ⇒ focal=1.5；角像素 px=−4/3、py=−2/3 ⇒ px/(−py) = −2
  const edge = cam.directions[0];
  assert.ok(Math.abs(edge[0] / edge[1] + 2) < 1e-9, "边缘像素两轴比例应由焦距决定（符号随 y 取负）");
  assert.ok(Math.abs(Math.hypot(...edge) - 1) < 1e-9, "方向必须归一");
}

// 5) ring / point：环半径与点数、单射线
{
  const ring = ringPattern({ rings: [{ radius: 0.2, samples: 4 }], includeCenter: true });
  assert.equal(ring.count, 5, "4 采样 + 1 中心");
  assert.deepEqual(ring.offsets[0], [0, 0, 0]);
  assert.ok(Math.abs(Math.hypot(ring.offsets[1][0], ring.offsets[1][1]) - 0.2) < 1e-9);
  const noCenter = ringPattern({ rings: [{ radius: 0.1, samples: 8 }], includeCenter: false });
  assert.equal(noCenter.count, 8);
  const point = pointPattern({ direction: [1, 0, 0] });
  assert.equal(point.count, 1);
  assert.deepEqual(point.directions[0], [1, 0, 0]);
  // fail-closed
  assert.equal(buildPattern("nope"), null);
}

// 6) 随机数可复现：同 seed 同序列，异 seed 异序列
{
  const a = createRandom(42);
  const b = createRandom(42);
  const c = createRandom(43);
  const seqA = [a(), a(), a(), a()];
  const seqB = [b(), b(), b(), b()];
  assert.deepEqual(seqA, seqB, "同 seed 必须同序列");
  assert.notDeepEqual(seqA, [c(), c(), c(), c()], "异 seed 应不同");
  for (const v of seqA) assert.ok(v >= 0 && v < 1, "LCG 输出在 [0,1)");
  const g1 = createGaussian(createRandom(7));
  const g2 = createGaussian(createRandom(7));
  assert.deepEqual([g1(), g1()], [g2(), g2()], "高斯序列同样可复现");
}

// 7) IMU 噪声：偏置 episode 内固定、白噪声逐拍变
{
  const imu = createImuNoise({ bias: [0.01, 0, 0], noise: [0.02, 0, 0], seed: 5 });
  const s1 = imu.apply([0, 0, 0]);
  const s2 = imu.apply([0, 0, 0]);
  assert.notDeepEqual(s1, s2, "白噪声应逐拍不同");
  // 无噪声轴必须逐位不变
  assert.equal(s1[1], 0);
  assert.equal(s1[2], 0);
  // 偏置固定：两次的"偏置+噪声"偏差都围绕同一 bias
  const imu2 = createImuNoise({ bias: [0, 0, 0], noise: [0, 0, 0], seed: 5 });
  assert.deepEqual(imu2.apply([1, 2, 3]), [1, 2, 3], "零配置必须是恒等");
}

// 8) 测距退化：miss 保持 miss、超量程记 miss、丢帧可复现、量化生效
{
  const identity = createRangeNoise({ maxDist: 12 });
  assert.deepEqual(identity.apply([1.5, null, -1]), [1.5, null, null], "未命中/负值一律 miss");
  const clipped = createRangeNoise({ maxDist: 5 });
  assert.deepEqual(clipped.apply([4.9, 5.1]), [4.9, null], "超量程记 miss 而非记最大值");
  const dropped = createRangeNoise({ maxDist: 12, dropRate: 1.0, seed: 3 });
  assert.deepEqual(dropped.apply([1, 2, 3]), [null, null, null], "丢帧率 1.0 全丢");
  const quant = createRangeNoise({ maxDist: 12, quantization: 0.5 });
  assert.deepEqual(quant.apply([1.13, 1.26]), [1, 1.5], "量化到 0.5m 栅格");
}

// 9) 深度退化：miss → 截止值、负值钳零、可复现
{
  const depth = createDepthNoise({ missValue: 3.0, noise: 0, quantization: 0, seed: 9 });
  assert.deepEqual(depth.apply([1.2, 0, -1, NaN]), [1.2, 3.0, 3.0, 3.0], "miss/非正值一律记截止距离");
  const noisy = createDepthNoise({ missValue: 3, noise: 0.1, seed: 9 });
  const f1 = noisy.apply([1, 1, 1]);
  const f2 = noisy.apply([1, 1, 1]);
  assert.notDeepEqual(f1, f2, "深度噪声逐帧不同");
  for (const v of f1) assert.ok(v >= 0, "深度不许为负");
  const again = createDepthNoise({ missValue: 3, noise: 0.1, seed: 9 });
  assert.deepEqual(f1, again.apply([1, 1, 1]), "同 seed 深度噪声可复现");
}

// 10) 接触噪声：迟滞 + 漏检
{
  const contact = createContactNoise({ threshold: 5, hysteresis: 1, missRate: 0, seed: 1 });
  assert.equal(contact.apply("FL", 0), false);
  assert.equal(contact.apply("FL", 5), true, "达到阈值报接触");
  assert.equal(contact.apply("FL", 4.2), true, "已进入后用低阈值保持（迟滞）");
  assert.equal(contact.apply("FL", 3), false, "掉出迟滞带才报离地");
  const flaky = createContactNoise({ threshold: 5, missRate: 1.0, seed: 1 });
  assert.equal(flaky.apply("FL", 100), false, "漏检率 1.0 时报了也读不到");
}

// 11) createNoise 分发 + fail-closed
{
  assert.ok(createNoise("imu"));
  assert.ok(createNoise("range"));
  assert.ok(createNoise("depth"));
  assert.ok(createNoise("contact"));
  assert.equal(createNoise("nope"), null, "未知噪声种类返回 null");
  assert.equal(createNoise(null), null, "目录里 noise=null 的传感器（理想）得到 null");
}

// 12) **形状契约**：调用方（app.js 的 scanHeightField/scanLidar）按这套字段名读。
//     字段改名必须同步改调用方，否则拿到 undefined ⇒ 空射线数组 ⇒ "全 miss"而不报错
//     （2026-09-21 实测踩中：fan 的 directions 被当成旧名 dirs 读，点云 0/240）。
{
  for (const kind of ["grid", "ring", "fan", "pinhole", "point"]) {
    const pattern = buildPattern(kind, kind === "grid" ? patternParams("height") : kind === "fan" ? patternParams("lidar") : {});
    assert.ok(pattern, `${kind} 应能构建`);
    assert.ok(Array.isArray(pattern.offsets), `${kind} 必须返回 offsets 数组`);
    assert.ok(Array.isArray(pattern.directions), `${kind} 必须返回 directions 数组`);
    assert.equal(pattern.offsets.length, pattern.directions.length, `${kind} 两数组必须等长`);
    assert.ok(Number.isFinite(pattern.count) && pattern.count > 0, `${kind} 必须返回 count`);
    for (const d of pattern.directions) {
      assert.ok(Math.abs(Math.hypot(d[0], d[1], d[2]) - 1) < 1e-9, `${kind} 的方向必须归一`);
    }
  }
  // fan 额外带 angles（极坐标图的横轴）
  assert.equal(buildPattern("fan", patternParams("lidar")).angles.length, 240);
  // grid 的点数必须等于目录契约的 **187**（17×11，与 backend/height_scan.py 的
  // GRID_POINTS 一致）——A 类绑定认的是这一份，坞里画得好看不算数
  assert.equal(buildPattern("grid", patternParams("height")).count, 187);
  assert.equal(buildPattern("grid", patternParams("lidar_height_scan")).count, 187);
  // x 主序：index = i_x * 11 + i_y ⇒ 第 0 点是最左后角 (-0.8,-0.5)，第 186 点是最右前角
  const g = buildPattern("grid", patternParams("height"));
  const nearPt = (a, b) => a.length === 3 && b.length === 3 && a.every((v, i) => Math.abs(v - b[i]) < 1e-9);
  assert.ok(nearPt(g.offsets[0], [-0.8, -0.5, 0]), `首点应为 (-0.8,-0.5)，实得 ${g.offsets[0]}`);
  assert.ok(nearPt(g.offsets[186], [0.8, 0.5, 0]), `末点应为 (0.8,0.5)，实得 ${g.offsets[186]}`);
  assert.ok(nearPt(g.offsets[1], [-0.8, -0.4, 0]), "x 主序：i_y 是快轴，第二个点沿 +y 前进");
  assert.ok(nearPt(g.offsets[11], [-0.7, -0.5, 0]), "第 12 点（i_x=1, i_y=0）换到下一列 x");
}

// 13) 运行时装配：默认关（透传）、开了才退化、同 seed 可复现
{
  const {
    applyContactNoise,
    applyDepthNoise,
    applyImuNoise,
    applyRangeNoise,
    createNoiseRegistry,
    describeNoiseRegistry,
  } = await import("./sensor_runtime.js");

  // 默认关：四个 apply 全部原样透传（不静默改变历史读数）
  const off = createNoiseRegistry(7, false);
  assert.equal(off.enabled, false);
  assert.deepEqual(applyImuNoise(off, [1, 2, 3]), [1, 2, 3]);
  assert.deepEqual(applyRangeNoise(off, [1.5, null]), [1.5, null]);
  assert.deepEqual(applyDepthNoise(off, [0.5, 0]), [0.5, 0]);
  assert.equal(describeNoiseRegistry(off), "理想值（未启用退化模型）");

  // 开了：IMU 逐拍不同但零配置轴不变
  const on = createNoiseRegistry(7, true, { imu: { bias: [0.01, 0, 0], noise: [0.02, 0, 0] } });
  const a = applyImuNoise(on, [0, 0, 0]);
  const b = applyImuNoise(on, [0, 0, 0]);
  assert.notDeepEqual(a, b, "启用后 IMU 应逐拍不同");
  assert.equal(a[1], 0, "未配噪声的轴必须不变");
  assert.equal(a[2], 0);
  assert.match(describeNoiseRegistry(on), /退化模型（seed=7）/);

  // 同 seed 同序列（可复现是硬要求）
  const again = createNoiseRegistry(7, true, { imu: { bias: [0.01, 0, 0], noise: [0.02, 0, 0] } });
  assert.deepEqual(a, applyImuNoise(again, [0, 0, 0]), "同 seed 必须复现同一条噪声");

  // 缺 register / 缺样本时不抛错（坞里读数可能瞬时为空）
  assert.deepEqual(applyImuNoise(null, [1, 2]), [1, 2]);
  assert.deepEqual(applyRangeNoise(on, null), null);
  assert.deepEqual(applyDepthNoise(on, "not-an-array"), "not-an-array");
  // 接触：registry 关时按"有力即接触"的旧语义
  assert.equal(applyContactNoise(off, "FL", 5), true);
  assert.equal(applyContactNoise(off, "FL", 0), false);
}

// 14) 点云 → 187 高度扫描聚合（min-z、空单元 null、坐标变换）
{
  const { aggregateHeightScan } = await import("./sensor_catalog.js");
  const base = { x: 0, y: 0, z: 0.35, yaw: 0 };
  // 机前 0.3m、左 0.1m、高 0.42m 一个点 ⇒ 该格值 = 0.35 − 0.42 = −0.07
  const one = aggregateHeightScan([[0.3, 0.1, 0.42]], base);
  assert.equal(one.filled, 1, "一个点落一格");
  assert.equal(one.total, 187);
  assert.ok(Math.abs(one.field.find((v) => v !== null) + 0.07) < 1e-9, "值 = base_z − z");

  // min-z：同格两个点取低的（0.42 与 0.30 ⇒ 取 0.30 ⇒ 0.05）
  const two = aggregateHeightScan([[0.3, 0.1, 0.42], [0.31, 0.11, 0.30]], base);
  assert.equal(two.filled, 1, "两点落同一格");
  assert.ok(Math.abs(two.field.find((v) => v !== null) - 0.05) < 1e-9, "min-z 聚合");

  // 网格外不填（1.4m 外的障碍不该进 ±0.8m 的格）
  const far = aggregateHeightScan([[1.4, 0, 0.5]], base);
  assert.equal(far.filled, 0, "网格外的点不进格");
  assert.ok(far.field.every((v) => v === null), "空单元必须是 null 而不是 0");

  // yaw 90°：机身 +x 指向世界 +y ⇒ 世界 (0, 0.3) 的点在机**前** 0.3m、居中
  //   ⇒ 机身系 (0.3, 0) ⇒ 格 (ix=11, iy=5)
  const turned = aggregateHeightScan([[0, 0.3, 0.42]], { ...base, yaw: Math.PI / 2 });
  assert.equal(turned.filled, 1, "旋转后仍能落格");
  const ix = Math.round((0.3 - (-0.8)) / 0.1);
  const iy = Math.round((0 - (-0.5)) / 0.1);
  assert.equal(ix, 11);
  assert.equal(iy, 5);
  assert.ok(turned.field[ix * 11 + iy] !== null, "应落在机前 0.3m 居中那格");

  // 缺省/坏输入不抛错
  assert.equal(aggregateHeightScan([], base).filled, 0);
  assert.equal(aggregateHeightScan(null, base).filled, 0);
  assert.equal(aggregateHeightScan([[1, 2]], base).filled, 0, "长度不足 3 的点跳过");
}

console.log("sensor_framework.test.mjs: 14 组断言全部通过 ✔");
