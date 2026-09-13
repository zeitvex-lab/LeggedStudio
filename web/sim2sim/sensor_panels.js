// 观测面板绘制器：深度帧 / 俯视高度场 / 极坐标扫描 / 点云散点 / 2D 轨迹平面。
//
// **为什么单独一个模块**：这些图此前**一张都不存在** —— 深度只在 `pie_depth.js` 里算出来
// 直接喂给策略（`feeds[depthName]`），页面上看不见；高度扫描只在 `advanced_sim.html` 里
// 展示**契约字段**，不是实时图；2D 平面图只有地图编辑器（`navigation_editor.html`）有。
// 而"闭环要看得见"（H18）缺的正是这一环。
//
// **分工**：**射线怎么打**在 `raycast.js`（采样几何 + 求交，也是纯函数、也有单测），
// 这里只负责**把数字变成像素**。两边都是纯函数，所以"图画错了"与"数据算错了"能分开定位。
//
// **为什么写成纯函数 + 注入 ctx**：Node 里可以直接拿假 ctx 断言"画了什么、画在哪"，
// 不必开浏览器（CI 不装浏览器）。约定：**只画不算** —— 不读 sim、不读 DOM，输入全是参数。

/** 深度帧 → RGBA 像素。输入是 `pie_depth.js` 的输出（已归一化到 [0,1]，0=近、1=远）。 */
export function depthFrameToRgba(frame, height, width, { nearIsBright = true } = {}) {
  if (!frame || !Number.isFinite(height) || !Number.isFinite(width)) return null;
  if (height < 1 || width < 1 || frame.length < height * width) return null;
  const data = new Uint8ClampedArray(height * width * 4);
  for (let i = 0; i < height * width; i += 1) {
    const raw = Number(frame[i]);
    const normalized = Number.isFinite(raw) ? Math.min(1, Math.max(0, raw)) : 1;
    // 近处亮、远处暗：把"距离"读成"亮度"要反过来，否则整屏一片白（全是远点）。
    const level = nearIsBright ? 1 - normalized : normalized;
    const shade = Math.round(level * 255);
    data[i * 4] = shade;
    data[i * 4 + 1] = shade;
    data[i * 4 + 2] = shade;
    data[i * 4 + 3] = 255;
  }
  return { data, height, width };
}

/**
 * **RGBA 像素 → ctx**（深度帧与高度场共用）。
 *
 * `putImageData` **不缩放**，所以调用方要先把 canvas 调到像素尺寸，再用 CSS 放大
 * （`image-rendering: pixelated`）。放在一处，省得两张图各写一遍 createImageData / ImageData 的回退。
 */
export function blitRgba(ctx, image, { x = 0, y = 0 } = {}) {
  if (!image || !ctx || typeof ctx.putImageData !== 'function') return false;
  const raster = typeof ctx.createImageData === 'function'
    ? ctx.createImageData(image.width, image.height)
    : null;
  if (raster) {
    raster.data.set(image.data);
  }
  // createImageData 不可用时（测试用假 ctx / 老浏览器）退回 ImageData 构造。
  const payload = raster
    || (typeof ImageData === 'function' ? new ImageData(image.data, image.width, image.height) : null);
  if (!payload) return false;
  ctx.putImageData(payload, x, y);
  return true;
}

/** 把深度帧贴到 ctx 的 (x,y)。**不负责缩放**：`w`/`h` 与帧尺寸不符时返回 false。 */
export function drawDepthFrame(ctx, frame, height, width, { x = 0, y = 0, w = width, h = height } = {}) {
  const image = depthFrameToRgba(frame, height, width);
  if (!image) return false;
  if (w !== width || h !== height) return false;
  return blitRgba(ctx, image, { x, y });
}

/**
 * **俯视高度场 → RGBA 像素**（低处偏蓝、高处偏黄）。
 *
 * 与 `depthFrameToRgba` 分开，是因为**缺值的含义相反**：深度帧里"远"仍是有效数据，
 * 高度场里"没打中"是**没有数据** —— 必须画成显眼的空槽（这里用纯黑），
 * 不能混进"很低"里，否则**一块悬空的墙角与一个坑会长得一模一样**。
 *
 * 输入是行优先的一维数组（`side × side`），行序已与俯视图像素行序对齐（见 `raycast.js::gridOffsets`），
 * 所以这里不再翻一次 —— 翻转写在两处，最容易只改对一处。
 */
export function heightFieldToRgba(field, side, { min = null, max = null } = {}) {
  const n = Math.max(1, Math.floor(Number(side) || 0));
  if (!Array.isArray(field) || field.length < n * n) return null;
  const values = field.slice(0, n * n);
  const known = values.map(Number).filter((v) => Number.isFinite(v));
  const low = Number.isFinite(min) ? Number(min) : (known.length ? Math.min(...known) : 0);
  const high = Number.isFinite(max) ? Number(max) : (known.length ? Math.max(...known) : 1);
  const span = high - low;
  const data = new Uint8ClampedArray(n * n * 4);
  for (let i = 0; i < n * n; i += 1) {
    const raw = values[i];
    // 空值必须单独挡：`Number(null) === 0`，直接 Number 会把"没打中"当成"零高度"。
    const hasValue = raw !== null && raw !== undefined && raw !== '' && Number.isFinite(Number(raw));
    if (!hasValue) {
      data[i * 4] = 0; data[i * 4 + 1] = 0; data[i * 4 + 2] = 0; data[i * 4 + 3] = 255;
      continue;
    }
    // 全平的高度场（span≈0）取 0.5，画成一条中间色带，语义正确（不是除零）。
    const t = span > 1e-9 ? Math.min(1, Math.max(0, (Number(raw) - low) / span)) : 0.5;
    data[i * 4] = Math.round(30 + t * 225);
    data[i * 4 + 1] = Math.round(80 + t * 175);
    data[i * 4 + 2] = Math.round(180 - t * 140);
    data[i * 4 + 3] = 255;
  }
  return { data, height: n, width: n };
}

/** 画俯视高度场。像素尺寸 = `side`，放大交给 CSS（`image-rendering: pixelated`）。 */
export function drawHeightField(ctx, field, side, { x = 0, y = 0 } = {}) {
  const image = heightFieldToRgba(field, side);
  if (!image) return false;
  return blitRgba(ctx, image, { x, y });
}

/** 世界折线 → 屏幕坐标（等比缩放 + 居中，x 右、y 上）。返回 `{points, scale, origin}`。 */
export function projectTrail(points, { width, height, padding = 8, bounds = null } = {}) {
  const clean = (Array.isArray(points) ? points : [])
    .filter((p) => p && Number.isFinite(Number(p[0])) && Number.isFinite(Number(p[1])))
    .map((p) => [Number(p[0]), Number(p[1])]);
  if (!clean.length || !(width > 0) || !(height > 0)) return { points: [], scale: 0, origin: [width / 2, height / 2] };

  let [x0, x1, y0, y1] = [0, 0, 0, 0];
  if (Array.isArray(bounds) && bounds.length === 4) {
    [x0, x1, y0, y1] = bounds.map(Number);
  } else {
    const xs = clean.map((p) => p[0]);
    const ys = clean.map((p) => p[1]);
    x0 = Math.min(...xs); x1 = Math.max(...xs);
    y0 = Math.min(...ys); y1 = Math.max(...ys);
  }
  const innerW = Math.max(1, width - 2 * padding);
  const innerH = Math.max(1, height - 2 * padding);
  const spanX = Math.max(1e-6, x1 - x0);
  const spanY = Math.max(1e-6, y1 - y0);
  const scale = Math.min(innerW / spanX, innerH / spanY); // 等比，避免轨迹被拉歪
  const originX = padding + (innerW - spanX * scale) / 2 - x0 * scale;
  const originY = padding + (innerH - spanY * scale) / 2;
  const projected = clean.map(([wx, wy]) => [
    originX + wx * scale,
    // 屏幕 y 向下、世界 y 向上：这里翻一次，否则轨迹上下颠倒。
    height - (originY + (wy - y0) * scale),
  ]);
  // 把 y0 一并返回：**位姿点必须用同一基准投影**，否则箭头会相对轨迹偏移
  // （`drawTrail` 里位姿是单独投影的，用错基准就画歪）。
  return { points: projected, scale, origin: [originX, originY], y0 };
}

/** 画 2D 轨迹平面：路径折线 + 已走轨迹 + 当前位姿（含朝向箭头）。 */
export function drawTrail(ctx, { path = [], trail = [], pose = null, bounds = null, width = 200, height = 140 } = {}) {
  if (!ctx) return false;
  const reference = projectTrail(path, { width, height, bounds });
  const walked = projectTrail(trail, { width, height, bounds });
  if (typeof ctx.clearRect === 'function') ctx.clearRect(0, 0, width, height);

  if (reference.points.length > 1 && typeof ctx.beginPath === 'function') {
    ctx.strokeStyle = '#64748b';
    ctx.lineWidth = 1;
    ctx.beginPath();
    reference.points.forEach(([sx, sy], index) => (index === 0 ? ctx.moveTo(sx, sy) : ctx.lineTo(sx, sy)));
    if (typeof ctx.stroke === 'function') ctx.stroke();
  }
  if (walked.points.length > 1 && typeof ctx.beginPath === 'function') {
    ctx.strokeStyle = '#38bdf8';
    ctx.lineWidth = 2;
    ctx.beginPath();
    walked.points.forEach(([sx, sy], index) => (index === 0 ? ctx.moveTo(sx, sy) : ctx.lineTo(sx, sy)));
    if (typeof ctx.stroke === 'function') ctx.stroke();
  }
  // 位姿点单独投影（可能落在 bounds 之外）——必须复用折线那一套 scale/origin/y0 基准，
  // 否则"机器人点"与"轨迹"不在同一坐标系里，看起来会漂。
  drawPoseMarker(ctx, reference.points.length ? reference : walked, pose, height);
  return true;
}

/**
 * **机器人位姿标记**（圆点 + 朝向箭头）。
 *
 * 抽出来是因为**轨迹图与点云图都要画它**，而它必须复用画该图时的**同一套投影基准**
 * —— 各写一份的话，"点云图里的机器人与点云错开"这类问题永远查不完。
 * 箭头纵轴取负：世界 yaw 逆时针为正，而屏幕 y 向下。
 */
export function drawPoseMarker(ctx, projection, pose, height, { color = '#f97316', radius = 3, arrow = 12 } = {}) {
  if (!ctx || !projection || !(projection.scale > 0) || !pose) return false;
  if (!Number.isFinite(Number(pose.x)) || !Number.isFinite(Number(pose.y))) return false;
  const sx = projection.origin[0] + Number(pose.x) * projection.scale;
  const sy = height - (projection.origin[1] + (Number(pose.y) - projection.y0) * projection.scale);
  const yaw = Number(pose.yaw) || 0;
  ctx.fillStyle = color;
  ctx.strokeStyle = color;
  if (typeof ctx.beginPath === 'function' && typeof ctx.arc === 'function') {
    ctx.beginPath();
    ctx.arc(sx, sy, radius, 0, Math.PI * 2);
    if (typeof ctx.fill === 'function') ctx.fill();
  }
  if (typeof ctx.beginPath === 'function' && typeof ctx.moveTo === 'function') {
    ctx.beginPath();
    ctx.moveTo(sx, sy);
    ctx.lineTo(sx + Math.cos(yaw) * arrow, sy - Math.sin(yaw) * arrow);
    if (typeof ctx.stroke === 'function') ctx.stroke();
  }
  return true;
}

/**
 * **极坐标扫描图**（LiDAR）：中心是传感器，向外按角度铺命中距离。
 *
 * **未命中的方向不画任何东西** —— 画到量程边界会让人以为"那边有障碍"，
 * 而实际是"那边什么都没有"。这与单点测距显示「无回波」是同一条原则：
 * **把"没有"画成"有"是这类图最坏的一种错**。
 * 量程圆环只画圈不填充（填了就像"整个范围都被占了"）。
 */
export function drawPolarScan(ctx, {
  angles = [], distances = [], maxDist = 12, width = 240, height = 240,
  color = '#eab308', ringColor = 'rgba(148,178,188,0.22)',
} = {}) {
  if (!ctx || typeof ctx.beginPath !== 'function') return false;
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.max(1, Math.min(cx, cy) - 3);
  if (typeof ctx.clearRect === 'function') ctx.clearRect(0, 0, width, height);

  ctx.strokeStyle = ringColor;
  ctx.lineWidth = 1;
  if (typeof ctx.arc === 'function' && typeof ctx.stroke === 'function') {
    for (const frac of [0.25, 0.5, 0.75, 1]) {
      ctx.beginPath();
      ctx.arc(cx, cy, radius * frac, 0, Math.PI * 2);
      ctx.stroke();
    }
    // 十字：交代方位基准 —— 局部 +x（机头）是 0 弧度，落在屏幕右侧。
    ctx.beginPath();
    ctx.moveTo(cx - radius, cy);
    ctx.lineTo(cx + radius, cy);
    ctx.moveTo(cx, cy - radius);
    ctx.lineTo(cx, cy + radius);
    ctx.stroke();
  }

  const span = Number(maxDist) > 0 ? Number(maxDist) : 1;
  const count = Math.min(angles.length, distances.length);
  ctx.fillStyle = color;
  let hits = 0;
  for (let i = 0; i < count; i += 1) {
    const d = Number(distances[i]);
    if (!Number.isFinite(d) || d < 0) continue; // 未命中：不画
    const a = Number(angles[i]) || 0;
    const r = Math.min(1, d / span) * radius;
    // 屏幕 y 向下，而机体系绕 +z 逆时针 → 纵轴取负。
    const sx = cx + Math.cos(a) * r;
    const sy = cy - Math.sin(a) * r;
    if (typeof ctx.fillRect === 'function') ctx.fillRect(sx - 1, sy - 1, 2, 2);
    hits += 1;
  }
  return hits > 0;
}

/**
 * **点云俯视散点**：世界系 x-y 投影（高度在俯视图里没有位置可言，只用前两维）。
 *
 * 复用 `projectTrail` 的等比缩放与 `drawPoseMarker`，于是**点云与 2D 轨迹天然对得齐**
 * —— 同一片地被两处画，错开了就得查半天。
 */
export function drawPointCloud(ctx, {
  points = [], pose = null, bounds = null, width = 240, height = 240, color = '#eab308',
} = {}) {
  if (!ctx) return false;
  const flat = (Array.isArray(points) ? points : [])
    .filter((p) => p && Number.isFinite(Number(p[0])) && Number.isFinite(Number(p[1])))
    .map((p) => [Number(p[0]), Number(p[1])]);
  const projection = projectTrail(flat, { width, height, bounds });
  if (typeof ctx.clearRect === 'function') ctx.clearRect(0, 0, width, height);
  if (!projection.points.length) return false;
  ctx.fillStyle = color;
  if (typeof ctx.fillRect === 'function') {
    projection.points.forEach(([sx, sy]) => ctx.fillRect(sx - 1, sy - 1, 2, 2));
  }
  drawPoseMarker(ctx, projection, pose, height);
  return true;
}


