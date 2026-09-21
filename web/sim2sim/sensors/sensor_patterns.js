// 传感器框架 · 采样 pattern（纯函数）。
//
// 语义**逐条对标**本仓训练栈 `mjlab/sensor/raycast_sensor.py` 的三种 PatternCfg：
//   GridPatternCfg     —— 多起点、**同方向**（size/resolution/direction）
//   RingPatternCfg     —— 同心环（本框架的 fan 是它的单环展开：同一起点、方向均布一圈）
//   PinholeCameraPatternCfg —— 针孔发散（width/height/fovy，fovy 与 MuJoCo 同约定）
// 浏览器端与训练端描述同一种传感器必须是同一套语言，否则"看到的"和"吃到的"对不上。
//
// 与训练栈的**实现差异**（如实记）：训练栈在 GPU 上并行求交，返回 (offsets, directions)
// 两个张量；本框架返回普通数组，交给 `raycast.js` 的 CPU 解析求交。形状与语义一致，
// 数值路径不同——这点在测试里用"同参数下网格点数/方向数可对"来守，不用逐值对拍。

/** 归一化（训练栈的 direction / direction.norm() 同款）。 */
function normalize(v) {
  const n = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / n, v[1] / n, v[2] / n];
}

/**
 * GridPattern：`n × n` 个**起点**、**同一个方向**。
 *
 * 与 mjlab GridPatternCfg 的对应：`size` → (extent×2, extent×2)，`resolution` → 步长；
 * mjlab 用 `arange(-size/2, size/2 + res*0.5, res)` 取点数，本处用 `n = round(size/res)+1`
 * 再线性铺开——两者在 size 为 resolution 整数倍时点数一致（测试钉住）。
 *
 * **铺开方向：从 +half 到 −half（降序）**，因此 offsets[0] 是 (+x, +y) 角。这不是随意选的：
 * 高度场画成俯视图时第 0 行要对应**机头方向**（+x）、第 0 列对应机身左侧（+y）——与
 * `raycast.js::gridOffsets` 的既有约定一致，改成升序会让图上下翻转而没有任何报错。
 *
 * @returns {{offsets: number[][], directions: number[][], count: number}}
 */
export function gridPattern({ size = [4, 4], resolution = 0.1, direction = [0, 0, -1], order = "front_first" } = {}) {
  const extentX = Math.max(1e-6, Number(size?.[0]) || 1);
  const extentY = Math.max(1e-6, Number(size?.[1]) || 1);
  const step = Math.max(1e-6, Number(resolution) || 0.1);
  const nx = Math.max(1, Math.round(extentX / step) + 1);
  const ny = Math.max(1, Math.round(extentY / step) + 1);
  const dir = normalize(direction.map(Number));
  // 铺开方向由 order 决定，**不能默认**（两种都有人要，猜错就是静默错图）：
  //   front_first（默认）——降序，offsets[0] 是 (+x,+y) 角；高度场俯视图第 0 行对应机头方向，
  //     与 raycast.js::gridOffsets 的既有约定一致；
  //   x_major —— 按 backend/height_scan.py 的 187 网格契约升序（index = i_x*ny + i_y，
  //     x −0.8→0.8、y −0.5→0.5）；**A 类感知绑定认的是这一份**，坞里画得好看不算数。
  const axis = (i, n, extent) => (order === "x_major"
    ? -extent / 2 + (extent * i) / (n - 1 || 1)
    : extent / 2 - (extent * i) / (n - 1 || 1));
  const offsets = [];
  for (let i = 0; i < nx; i += 1) {
    const x = axis(i, nx, extentX);
    for (let j = 0; j < ny; j += 1) {
      offsets.push([x, axis(j, ny, extentY), 0]);
    }
  }
  const directions = offsets.map(() => dir.slice());
  return { offsets, directions, count: offsets.length };
}

/**
 * RingPattern：同心环采样（朝下为典型用法——每只脚周围的地形高度）。
 *
 * `rings: [{radius, samples}]`；`include_center` 决定是否加中心那一条。
 * 方向可配（默认朝下），与 mjlab RingPatternCfg.direction 同义。
 */
export function ringPattern({ rings = [{ radius: 0.1, samples: 8 }], includeCenter = true, direction = [0, 0, -1] } = {}) {
  const dir = normalize(direction.map(Number));
  const offsets = [];
  if (includeCenter) offsets.push([0, 0, 0]);
  for (const ring of rings) {
    const radius = Math.max(0, Number(ring?.radius) || 0);
    const samples = Math.max(1, Math.round(Number(ring?.samples) || 1));
    for (let i = 0; i < samples; i += 1) {
      const a = (2 * Math.PI * i) / samples;
      offsets.push([radius * Math.cos(a), radius * Math.sin(a), 0]);
    }
  }
  const directions = offsets.map(() => dir.slice());
  return { offsets, directions, count: offsets.length };
}

/**
 * FanPattern：**同一起点**、方向在局部 x-y 平面内均布一整圈（LiDAR 扇扫）。
 *
 * 这是 RingPatternCfg 的退化用法（半径 0、只有方向不同）；单独成类是因为调用方拿到的
 * 是"一个原点 + N 个方向"，与 grid 的"N 个起点 + 一个方向"正好对偶——两者混用会算出
 * 一张看着像图但完全不对的东西（raycast.js 的注释记着这个坑）。
 *
 * @returns {{offsets: number[][], directions: number[][], angles: number[], count: number}}
 */
export function fanPattern({ count = 240 } = {}) {
  const n = Math.max(1, Math.round(Number(count) || 1));
  const offsets = [];
  const directions = [];
  const angles = [];
  for (let i = 0; i < n; i += 1) {
    const a = (2 * Math.PI * i) / n;
    angles.push(a);
    directions.push([Math.cos(a), Math.sin(a), 0]);
    offsets.push([0, 0, 0]);
  }
  return { offsets, directions, angles, count: n };
}

/**
 * PinholePattern：针孔相机射线（局部 **−z 为光轴**，与 MuJoCo 相机一致）。
 *
 * `width/height/fovy`：fovy 为垂直视场角（度，MuJoCo 约定）。返回的 offsets 全零
 * （都从针心出发），directions 按像素中心发散——训练栈同款。
 */
export function pinholePattern({ width = 16, height = 12, fovy = 45 } = {}) {
  const w = Math.max(1, Math.round(Number(width) || 1));
  const h = Math.max(1, Math.round(Number(height) || 1));
  const fovY = (Math.max(1e-3, Number(fovy) || 45) * Math.PI) / 180;
  const focal = 0.5 * h / Math.tan(fovY / 2);
  const offsets = [];
  const directions = [];
  for (let v = 0; v < h; v += 1) {
    const py = (v + 0.5 - 0.5 * h) / focal;
    for (let u = 0; u < w; u += 1) {
      const px = (u + 0.5 - 0.5 * w) / focal;
      offsets.push([0, 0, 0]);
      directions.push(normalize([px, py, -1]));
    }
  }
  return { offsets, directions, count: w * h, width: w, height: h };
}

/** 单射线（point pattern）：一个起点、一个方向。 */
export function pointPattern({ direction = [0, 0, -1] } = {}) {
  const dir = normalize(direction.map(Number));
  return { offsets: [[0, 0, 0]], directions: [dir], count: 1 };
}

/** 按名字取 pattern（未知名字返回 null，调用方 fail-closed）。 */
export function buildPattern(kind, params = {}) {
  switch (kind) {
    case "grid": return gridPattern(params);
    case "ring": return ringPattern(params);
    case "fan": return fanPattern(params);
    case "pinhole": return pinholePattern(params);
    case "point": return pointPattern(params);
    default: return null;
  }
}
