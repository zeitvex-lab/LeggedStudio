// 观测面板绘制器：深度帧 / 高度扫描 / 2D 轨迹平面。
//
// **为什么单独一个模块**：这三张图此前**一张都不存在**——深度只在 `pie_depth.js` 里算出来
// 直接喂给策略（`feeds[depthName]`），页面上看不见；高度扫描只在 `advanced_sim.html` 里
// 展示**契约字段**，不是实时图；2D 平面图只有地图编辑器（`navigation_editor.html`）有。
// 而"闭环要看得见"（H18）缺的正是这一环。
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

/** 把深度帧贴到 ctx 的 (x,y) 处，按 (w,h) 拉伸。返回是否真的画了。 */
export function drawDepthFrame(ctx, frame, height, width, { x = 0, y = 0, w = width, h = height } = {}) {
  const image = depthFrameToRgba(frame, height, width);
  if (!image || !ctx || typeof ctx.putImageData !== 'function') return false;
  const raster = typeof ctx.createImageData === 'function'
    ? ctx.createImageData(width, height)
    : null;
  if (raster) {
    raster.data.set(image.data);
  }
  // createImageData 不可用时（测试用假 ctx / 老浏览器）退回 ImageData 构造。
  const payload = raster || (typeof ImageData === 'function' ? new ImageData(image.data, width, height) : null);
  if (!payload) return false;
  ctx.putImageData(payload, x, y);
  if (typeof ctx.drawImage === 'function' && (w !== width || h !== height)) {
    // 需要缩放时先画到离屏再 drawImage 的成本更高，这里只在尺寸一致时用 putImageData，
    // 否则交由调用方决定（保持函数单一职责）。
    return false;
  }
  return true;
}

/** 高度扫描（一维高度数组）→ 归一化柱高数组，长度与输入一致。 */
export function heightScanToBars(scan, { min = null, max = null } = {}) {
  if (!Array.isArray(scan) || scan.length === 0) return [];
  const values = scan.map((v) => (Number.isFinite(Number(v)) ? Number(v) : 0));
  const low = Number.isFinite(min) ? Number(min) : Math.min(...values);
  const high = Number.isFinite(max) ? Number(max) : Math.max(...values);
  const span = high - low;
  // 全平的高度场（span=0）会除零：此时所有柱高取 0.5，画出来是一条中线，语义正确。
  if (!(span > 1e-9)) return values.map(() => 0.5);
  return values.map((v) => Math.min(1, Math.max(0, (v - low) / span)));
}

/** 画高度扫描条带（左→右按格序，柱高表示相对高度）。 */
export function drawHeightScan(ctx, scan, { x = 0, y = 0, w = 200, h = 60, color = '#38bdf8' } = {}) {
  if (!ctx || typeof ctx.fillRect !== 'function') return false;
  const bars = heightScanToBars(scan);
  if (!bars.length || w <= 0 || h <= 0) return false;
  if (typeof ctx.clearRect === 'function') ctx.clearRect(x, y, w, h);
  const slot = w / bars.length;
  ctx.fillStyle = color;
  bars.forEach((ratio, index) => {
    const barWidth = Math.max(1, slot - 1);
    const barHeight = Math.max(1, ratio * h);
    ctx.fillRect(x + index * slot, y + (h - barHeight), barWidth, barHeight);
  });
  return true;
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
  if (pose && Number.isFinite(Number(pose.x)) && Number.isFinite(Number(pose.y))) {
    // 位姿点单独投影（可能落在 bounds 之外）——必须复用折线那一套 scale/origin/y0 基准，
    // 否则"机器人点"与"轨迹"不在同一坐标系里，看起来会漂。
    const projection = reference.points.length ? reference : walked;
    const scale = projection.scale;
    if (scale > 0) {
      const sx = projection.origin[0] + Number(pose.x) * scale;
      const sy = height - (projection.origin[1] + (Number(pose.y) - projection.y0) * scale);
      const yaw = Number(pose.yaw) || 0;
      ctx.fillStyle = '#f97316';
      if (typeof ctx.beginPath === 'function' && typeof ctx.arc === 'function') {
        ctx.beginPath();
        ctx.arc(sx, sy, 3, 0, Math.PI * 2);
        if (typeof ctx.fill === 'function') ctx.fill();
      }
      if (typeof ctx.beginPath === 'function') {
        // 朝向箭头：世界 yaw 逆时针为正，屏幕 y 向下，故纵轴取负。
        ctx.strokeStyle = '#f97316';
        ctx.beginPath();
        ctx.moveTo(sx, sy);
        ctx.lineTo(sx + Math.cos(yaw) * 12, sy - Math.sin(yaw) * 12);
        if (typeof ctx.stroke === 'function') ctx.stroke();
      }
    }
  }
  return true;
}

/** 观测面板要显示的**数值**行（odom 位姿 / IMU 三轴角速度 / 机体高度）——纯格式化，可测。 */
export function observationReadout({ pose = null, angular = null, baseHeight = null, digits = 2 } = {}) {
  // **缺值必须是「—」，不能是 0.00**：`Number(null) === 0`，直接 isFinite 会把"没数据"
  // 显示成"高度 0.00"，看起来像真读数（本模块单测抓到的第一个 bug）。
  const fmt = (value) => {
    if (value === null || value === undefined || value === '') return '—';
    const num = Number(value);
    return Number.isFinite(num) ? num.toFixed(digits) : '—';
  };
  const triple = (vec) => (Array.isArray(vec) && vec.length >= 3
    ? vec.slice(0, 3).map(fmt).join(' / ')
    : '—');
  const has = (value) => value !== null && value !== undefined && Number.isFinite(Number(value));
  return {
    position: pose && has(pose.x) && has(pose.y) ? `${fmt(pose.x)} , ${fmt(pose.y)}` : '—',
    yaw: pose && has(pose.yaw) ? `${((Number(pose.yaw) * 180) / Math.PI).toFixed(1)}°` : '—',
    angular: triple(angular),
    baseHeight: fmt(baseHeight),
  };
}
