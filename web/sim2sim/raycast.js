// 无 GL 的 CPU 射线求交 —— 对 MuJoCo 场景几何（plane / sphere / box）解析求交。
//
// **为什么单独一个模块**：同一套求交被**四处**共用 ——
//   ① 深度相机（`pie_depth.js`：给 PIE 类策略喂 obs）
//   ② 高度扫描（机周垂直射线网格 → 高度场）
//   ③ LiDAR / 射线传感器（多方向扇扫 → 极坐标图 / 点云）
//   ④ 点云（**复用 LiDAR 的命中点**，不另扫一遍 —— 两图同源才对得齐）
// 各写一份的话，「深度图与高度场对不上」这类问题永远查不完 —— 那本是同一台相机在看同一片地。
//
// **支持的类型有限，且这是有意的**：只算 plane(0) / sphere(2) / box(6)。
//   · 好处：相机不会拍到自己的网格（本体多为 mesh，相机装在机头/机顶）；
//   · 代价：场景里少数 **mesh 障碍物**（如 apartment 的家具）不会出现在深度/点云里 —— 已知局限。
// MuJoCo WASM 未导出 `mj_ray`，所以只能在 JS 侧解析求交。

export function quatMul(a, b) {
  return [
    a[0] * b[0] - a[1] * b[1] - a[2] * b[2] - a[3] * b[3],
    a[0] * b[1] + a[1] * b[0] + a[2] * b[3] - a[3] * b[2],
    a[0] * b[2] - a[1] * b[3] + a[2] * b[0] + a[3] * b[1],
    a[0] * b[3] + a[1] * b[2] - a[2] * b[1] + a[3] * b[0],
  ];
}

export function quatRot(q, v) {
  const [w, x, y, z] = q;
  const t = [2 * (y * v[2] - z * v[1]), 2 * (z * v[0] - x * v[2]), 2 * (x * v[1] - y * v[0])];
  return [
    v[0] + w * t[0] + (y * t[2] - z * t[1]),
    v[1] + w * t[1] + (z * t[0] - x * t[2]),
    v[2] + w * t[2] + (x * t[1] - y * t[0]),
  ];
}

export function quatToMat(q) {
  const [w, x, y, z] = q;
  return [
    1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y),
    2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x),
    2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y),
  ];
}

/** 矩阵转置乘向量（`m` 为行主序 3×3 展平）。 */
export function matTVec(m, v) {
  return [
    m[0] * v[0] + m[3] * v[1] + m[6] * v[2],
    m[1] * v[0] + m[4] * v[1] + m[7] * v[2],
    m[2] * v[0] + m[5] * v[1] + m[8] * v[2],
  ];
}

/** 支持的 geom 类型：plane / sphere / box。 */
export const RAYCAST_GEOM_TYPES = [0, 2, 6];

/**
 * 逐 geom 的**世界系快照**：每批次（一次扫描）只算一遍，而不是每条射线重算一遍。
 *
 * 此前 `intersectSceneRays` 对每条射线都把全场景 geom 的世界变换（两次四元数乘法 +
 * 多次数组分配）重算一遍——240 线 LiDAR × 每次全场景重算，正是"开雷达就卡"的计算
 * 侧根源（2026-09-22 性能复盘；与坞面板/3D 层各自缓存导致的重复扫描一并修）。
 * geom 的世界变换只依赖当前物理状态，同批次内完全相同——摊平到每 geom 一次。
 *
 * 元素全部拆成标量字段（零分配的热路径），`rbound` 是包围球半径（mjModel.geom_rbound，
 * 缺失时按类型兜底），用于射线级**预剔除**：球心对射线的最近距离超过半径必不相交。
 */
function snapshotGeoms(model, data, { types = RAYCAST_GEOM_TYPES, worldBodyOnly = false }) {
  const geoms = [];
  const ngeom = Number(model.ngeom || 0);
  for (let g = 0; g < ngeom; g += 1) {
    const type = Number(model.geom_type[g]);
    if (!types.includes(type)) continue;
    const bodyId = Number(model.geom_bodyid[g]);
    // worldBodyOnly：只认世界体（body 0）的 geom——**地形/障碍**才在 body 0 上，
    // 机器人自己的碰撞体挂在子 body 上。高度场要的是地形高度（训练侧就是对地形函数
    // 采样），不滤掉自身的话，机腹正下方的格子会读到底盘高度，"地形"被自身污染。
    if (worldBodyOnly && bodyId !== 0) continue;
    const bq = [
      data.xquat[bodyId * 4], data.xquat[bodyId * 4 + 1],
      data.xquat[bodyId * 4 + 2], data.xquat[bodyId * 4 + 3],
    ];
    const gp = [model.geom_pos[g * 3], model.geom_pos[g * 3 + 1], model.geom_pos[g * 3 + 2]];
    const gq = [
      model.geom_quat[g * 4], model.geom_quat[g * 4 + 1],
      model.geom_quat[g * 4 + 2], model.geom_quat[g * 4 + 3],
    ];
    const gpw = quatRot(bq, gp);
    const quat = quatMul(bq, gq);
    const size = [model.geom_size[g * 3], model.geom_size[g * 3 + 1], model.geom_size[g * 3 + 2]];
    const entry = {
      type,
      px: data.xpos[bodyId * 3] + gpw[0],
      py: data.xpos[bodyId * 3 + 1] + gpw[1],
      pz: data.xpos[bodyId * 3 + 2] + gpw[2],
      s0: size[0], s1: size[1], s2: size[2],
      rbound: 0,
    };
    let rbound = Number(model.geom_rbound ? model.geom_rbound[g] : NaN);
    if (!Number.isFinite(rbound) || rbound <= 0) {
      if (type === 2) rbound = size[0];
      else if (type === 6) rbound = Math.hypot(size[0], size[1], size[2]);
      else rbound = 0; // 平面无限延伸，不做包围球剔除
    }
    entry.rbound = rbound;
    if (type === 0) {
      // 平面：法向为局部 +z，每 geom 算一次。
      const n = quatRot(quat, [0, 0, 1]);
      entry.nx = n[0]; entry.ny = n[1]; entry.nz = n[2];
    } else {
      entry.m = quatToMat(quat); // 行主序 R；用 matTVec(R, v) = Rᵀv 转进机体系
    }
    geoms.push(entry);
  }
  return geoms;
}

/** 对一份 geom 快照投一条射线（热路径：全标量、零分配）。语义与旧逐 geom 实现一致。 */
function castAgainstList(geoms, origin, dir, maxDist, epsilon) {
  let best = -1;
  for (let i = 0; i < geoms.length; i += 1) {
    const g = geoms[i];
    if (g.rbound > 0) {
      // 包围球预剔除：球心相对射线起点的投影 t_ca 与垂距平方 d²，d² > r² 必不相交。
      const cx = g.px - origin[0];
      const cy = g.py - origin[1];
      const cz = g.pz - origin[2];
      const tca = cx * dir[0] + cy * dir[1] + cz * dir[2];
      if (tca < -g.rbound) continue;
      if (cx * cx + cy * cy + cz * cz - tca * tca > g.rbound * g.rbound) continue;
    }
    let t = -1;
    if (g.type === 0) {
      const denom = g.nx * dir[0] + g.ny * dir[1] + g.nz * dir[2];
      if (Math.abs(denom) < 1e-9) continue;
      const tt = ((g.px - origin[0]) * g.nx + (g.py - origin[1]) * g.ny + (g.pz - origin[2]) * g.nz) / denom;
      if (tt > epsilon) t = tt;
    } else {
      const m = g.m;
      const wx = origin[0] - g.px, wy = origin[1] - g.py, wz = origin[2] - g.pz;
      const ox = m[0] * wx + m[3] * wy + m[6] * wz;
      const oy = m[1] * wx + m[4] * wy + m[7] * wz;
      const oz = m[2] * wx + m[5] * wy + m[8] * wz;
      const dx = m[0] * dir[0] + m[3] * dir[1] + m[6] * dir[2];
      const dy = m[1] * dir[0] + m[4] * dir[1] + m[7] * dir[2];
      const dz = m[2] * dir[0] + m[5] * dir[1] + m[8] * dir[2];
      if (g.type === 2) {
        // 球：解二次方程取近根。
        const r = g.s0;
        const a = dx * dx + dy * dy + dz * dz;
        const b = 2 * (ox * dx + oy * dy + oz * dz);
        const c = ox * ox + oy * oy + oz * oz - r * r;
        const disc = b * b - 4 * a * c;
        if (disc >= 0 && a > 1e-12) {
          const tt = (-b - Math.sqrt(disc)) / (2 * a);
          if (tt > epsilon) t = tt;
        }
      } else {
        // 盒：转到局部系做 slab 求交。
        let tmin = 0;
        let tmax = Infinity;
        let hit = true;
        const lo = [ox, oy, oz];
        const ld = [dx, dy, dz];
        const size = [g.s0, g.s1, g.s2];
        for (let k = 0; k < 3; k += 1) {
          if (Math.abs(ld[k]) < 1e-9) {
            if (Math.abs(lo[k]) > size[k]) { hit = false; break; }
          } else {
            let t1 = (-size[k] - lo[k]) / ld[k];
            let t2 = (size[k] - lo[k]) / ld[k];
            if (t1 > t2) { const tmp = t1; t1 = t2; t2 = tmp; }
            tmin = Math.max(tmin, t1);
            tmax = Math.min(tmax, t2);
            if (tmin > tmax) { hit = false; break; }
          }
        }
        if (hit && tmax > epsilon) t = Math.max(tmin, epsilon);
      }
    }
    if (t > 0 && t <= maxDist && (best < 0 || t < best)) best = t;
  }
  return best;
}

/**
 * 单条射线求交，返回**最近命中距离**（米），未命中返回 `-1`。
 *
 * `model` / `data` 是 MuJoCo WASM 的 MjModel / MjData（只读用到的数组）。
 * 多条射线请走 `intersectSceneRays`——它把 geom 快照摊平到每批次一次。
 */
export function intersectSceneRay(
  model,
  data,
  origin,
  dir,
  { maxDist = Infinity, epsilon = 1e-4, worldBodyOnly = false, types } = {},
) {
  const geoms = snapshotGeoms(model, data, { types, worldBodyOnly });
  return castAgainstList(geoms, origin, dir, maxDist, epsilon);
}

/** 便捷封装：给定机身位姿与"机体系下的射线方向"，返回世界系方向。 */
export function bodyRayDirection(bodyQuat, localDir) {
  return quatRot(bodyQuat, localDir);
}

/**
 * RPY（**弧度**）→ 四元数 `(w,x,y,z)`，约定 `R = Rz·Ry·Rx`（即 `quatToRpy` 的逆）。
 *
 * **只用于传感器的装配角** —— 那是给人看的"装在哪个角度"，不是物理真值，
 * 所以用标准 RPY 约定即可；默认装配里只有单轴旋转（如单点测距的 `y = −90°`），单轴下任何约定都一致。
 */
export function quatFromRpy(rpy) {
  const [r, p, y] = rpy.map(Number);
  const cr = Math.cos(r / 2);
  const sr = Math.sin(r / 2);
  const cp = Math.cos(p / 2);
  const sp = Math.sin(p / 2);
  const cy = Math.cos(y / 2);
  const sy = Math.sin(y / 2);
  return [
    cr * cp * cy + sr * sp * sy,
    sr * cp * cy - cr * sp * sy,
    cr * sp * cy + sr * cp * sy,
    cr * cp * sy - sr * sp * cy,
  ];
}

/**
 * **高度扫描的采样网格**：机体系 x-y 平面上 `side × side` 个**起点**，覆盖 `[-extent, extent]`。
 *
 * **变的是起点，不是方向** —— 高度扫描所有射线**同向朝下**，换格子等于换"从头上的哪个位置
 * 往下看"。这是它与 LiDAR（`fanDirections`，同一起点、方向扇开）的根本区别，
 * 两者混起来会算出一张看着像图但完全不对的东西。
 *
 * 返回行优先（先 x 后 y），与**俯视图的像素行序**对齐：
 * 第 0 行是机头方向（+x），每行第 0 列是机身左侧（+y）—— 于是数组直接当图像用，
 * 不必在绘制时再翻一次（翻转写在两处最容易只改对一处）。
 */
export function gridOffsets(side, extent) {
  const n = Math.max(1, Math.floor(Number(side) || 1));
  const half = Math.max(0, Number(extent) || 0);
  const step = n > 1 ? (2 * half) / (n - 1) : 0;
  const offsets = [];
  for (let row = 0; row < n; row += 1) {
    for (let col = 0; col < n; col += 1) {
      offsets.push([half - row * step, half - col * step]);
    }
  }
  return { offsets, side: n, extent: half, step };
}

/**
 * **水平扇扫方向**：机体系 x-y 平面内 `count` 条均布方向，整圈 360°。
 *
 * 从局部 **+x**（正前）起、绕 **+z** 逆时针，覆盖一整圈 —— 角度数组一并返回，
 * 画极坐标图时要用（那才是图的横轴）。
 *
 * 扫描平面的朝向由装配的 `rpy` 决定：默认 `[0,0,0]` 恰好让 x-y 平面与地面平行
 * （"机顶旋转雷达"），把俯仰拨一下就变成斜面扫描，不需要额外开关。
 */
export function fanDirections(count) {
  const n = Math.max(1, Math.floor(Number(count) || 1));
  const angles = [];
  const dirs = [];
  for (let i = 0; i < n; i += 1) {
    const a = (2 * Math.PI * i) / n;
    angles.push(a);
    dirs.push([Math.cos(a), Math.sin(a), 0]);
  }
  return { dirs, angles, count: n };
}

/**
 * **批量求交**：`origins[i]` 配 `dirs[i]`（长度取短者）。
 *
 * 逐条配对而不是"一个原点 + 多方向"，因为高度扫描要的正是**多起点同方向**
 * （见 `gridOffsets`）—— 调用方把方向数组广播成等长即可，比多写一个接口划算。
 * 未命中仍是 `-1`，与单条 `intersectSceneRay` 一致。
 *
 * geom 快照每批次只建一次（见 `snapshotGeoms`）——这是本函数相对"循环调单条"
 * 的全部性能差异所在。
 */
export function intersectSceneRays(model, data, origins, dirs, options = {}) {
  const from = Array.isArray(origins) ? origins : [];
  const along = Array.isArray(dirs) ? dirs : [];
  const n = Math.min(from.length, along.length);
  const geoms = snapshotGeoms(model, data, options);
  const { maxDist = Infinity, epsilon = 1e-4 } = options;
  const distances = new Array(n);
  for (let i = 0; i < n; i += 1) {
    distances[i] = castAgainstList(geoms, from[i], along[i], maxDist, epsilon);
  }
  return distances;
}

/**
 * **射线命中点 → 世界系坐标**。未命中（`-1`）返回 `null`，**不返回射线终点** ——
 * 那会在点云/极坐标图上凭空画出一个"什么都没有"的点，看着像障碍物。
 */
export function rayHitPoint(origin, dir, distance) {
  // **空值必须单独挡**：`Number(null) === 0` 且 `0 < 0` 为假，于是"没这条射线"会被当成
  // "命中距离 0" → 返回**射线起点本身**，在点云图上画出一个贴在传感器上的点，
  // 看着像"贴脸有障碍"。这是同一个坑在这个项目里第三次出现（另两次见 `sensor_dock.js`）。
  if (distance === null || distance === undefined || distance === "") return null;
  const t = Number(distance);
  if (!Number.isFinite(t) || t < 0) return null;
  return [origin[0] + dir[0] * t, origin[1] + dir[1] * t, origin[2] + dir[2] * t];
}

/**
 * **按装配把射线铺到世界系**：`localDirs` 是机体系方向，返回世界系方向数组。
 * 高度扫描与扇扫都用它，免得各自写一遍"机身姿态 × 装配姿态"。
 */
export function mountRayDirections(baseQuat, mountQuat, localDirs) {
  const world = quatMul(baseQuat, mountQuat);
  return localDirs.map((d) => quatRot(world, d));
}

/** 装配点在世界系的位置：`机身位置 + 机身姿态 × 装配位置`。 */
export function mountOriginWorld(basePos, baseQuat, mountPos) {
  const offset = quatRot(baseQuat, mountPos);
  return [basePos[0] + offset[0], basePos[1] + offset[1], basePos[2] + offset[2]];
}
