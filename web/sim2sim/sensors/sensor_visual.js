// 传感器框架 · 3D 可视化数据层（纯函数，Node 可测）。
//
// 对标 Isaac Sim 的传感器可视化习惯（用户裁决 2026-09-21）：
//   * Height Scanner —— 射线命中点画成**彩色小球**（按高度彩虹着色）；
//   * RTX LiDAR —— 3D 点云**按距离着色**（近绿远红）；
//   * Contact Sensor —— 接触点**半透明球**（着地亮/离地暗）+ 力方向标记；
//   * IMU —— 坐标轴三脚架标在装配位。
// 颜色映射是纯函数：输入数值数组、输出 Float32Array（THREE.Points 的 color attribute
// 直接可吃），Node 里不需要 WebGL 就能断言。

/** 三段线性渐变：t∈[0,1] → 蓝→绿→红（Isaac 地形调色板的近似）。 */
export function heightRamp(t) {
  const u = Math.min(1, Math.max(0, Number(t) || 0));
  const stops = [
    [40, 90, 230],   // 低：蓝
    [60, 205, 90],   // 中：绿
    [235, 70, 40],   // 高：红
  ];
  const seg = u < 0.5 ? 0 : 1;
  const local = u < 0.5 ? u / 0.5 : (u - 0.5) / 0.5;
  const a = stops[seg];
  const b = stops[seg + 1];
  return [
    a[0] + (b[0] - a[0]) * local,
    a[1] + (b[1] - a[1]) * local,
    a[2] + (b[2] - a[2]) * local,
  ];
}

/** 近绿远红（LiDAR/深度按距离着色的常规口径）。 */
export function distanceRamp(t) {
  const u = Math.min(1, Math.max(0, Number(t) || 0));
  // 绿 (60,220,90) → 黄 (230,210,60) → 红 (235,60,50)
  const stops = [
    [60, 220, 90],
    [230, 210, 60],
    [235, 60, 50],
  ];
  const seg = u < 0.5 ? 0 : 1;
  const local = u < 0.5 ? u / 0.5 : (u - 0.5) / 0.5;
  const a = stops[seg];
  const b = stops[seg + 1];
  return [
    a[0] + (b[0] - a[0]) * local,
    a[1] + (b[1] - a[1]) * local,
    a[2] + (b[2] - a[2]) * local,
  ];
}

/**
 * 高度场 → 每点颜色（彩虹，按观测到的 min/max 归一；全平取中点色）。
 * null（未命中）→ [0,0,0]，配合调用方把位置藏到远处即可。
 */
export function heightPointColors(field, { low = null, high = null } = {}) {
  const known = field.filter((v) => v !== null && Number.isFinite(v));
  const lo = Number.isFinite(low) ? low : (known.length ? Math.min(...known) : 0);
  const hi = Number.isFinite(high) ? high : (known.length ? Math.max(...known) : 1);
  const span = hi - lo;
  const colors = new Float32Array(field.length * 3);
  for (let i = 0; i < field.length; i += 1) {
    const v = field[i];
    if (v === null || !Number.isFinite(v)) continue; // 未命中：黑，调用方藏点
    const t = span > 1e-9 ? (v - lo) / span : 0.5;
    const [r, g, b] = heightRamp(t);
    colors[i * 3] = r / 255;
    colors[i * 3 + 1] = g / 255;
    colors[i * 3 + 2] = b / 255;
  }
  return colors;
}

/** 命中点 → 每点颜色（按距离归一；null = 未命中 → 黑）。 */
export function distancePointColors(distances, maxDist) {
  const colors = new Float32Array(distances.length * 3);
  const cap = Number(maxDist) || 1;
  for (let i = 0; i < distances.length; i += 1) {
    const d = distances[i];
    // miss/负值/超量程一律黑——"没打到"与"打到了"必须在图上可分辨
    if (d === null || d === undefined || d < 0 || d > cap) continue;
    const [r, g, b] = distanceRamp(d / cap);
    colors[i * 3] = r / 255;
    colors[i * 3 + 1] = g / 255;
    colors[i * 3 + 2] = b / 255;
  }
  return colors;
}

/**
 * 足底接触 → 每脚可视化状态（着地绿 + 力记号；离地暗）。
 * 力来自接触计数（WASM 侧暂无 efc_force）或真实力，调用方决定。
 */
export function contactVisualStates(feet) {
  return (feet || []).map((foot) => ({
    name: foot.name,
    grounded: Boolean(foot.grounded),
    force: Number(foot.force) || 0,
    color: foot.grounded ? [0.13, 0.77, 0.37] : [0.28, 0.33, 0.41],
    scale: foot.grounded ? 1.0 : 0.6,
  }));
}
