// 观测面板绘制器单测（自包含断言，与 dwa_fan.test.mjs 同风格）。
//
// 这些绘制器此前**一个都不存在**（深度只喂策略、高度图只展示契约、2D 平面只有地图编辑器）。
// 用**假 ctx** 断言"画了什么、画在哪"——不需要浏览器，CI 里直接跑。
import assert from "node:assert/strict";
import {
  blitRgba,
  depthFrameToRgba,
  drawContactStates,
  drawHeightGrid,
  drawDepthFrame,
  drawHeightField,
  drawPointCloud,
  drawPolarScan,
  drawPoseMarker,
  drawTrail,
  heightFieldToRgba,
  projectTrail,
} from "./sensor_panels.js";

function makeCtx() {
  const calls = [];
  const ctx = {
    calls,
    createImageData: (w, h) => ({ width: w, height: h, data: new Uint8ClampedArray(w * h * 4) }),
    clearRect: (...a) => calls.push(["clearRect", ...a]),
    putImageData: (...a) => calls.push(["putImageData", ...a]),
    fillRect: (...a) => calls.push(["fillRect", ...a]),
    beginPath: () => calls.push(["beginPath"]),
    moveTo: (...a) => calls.push(["moveTo", ...a]),
    lineTo: (...a) => calls.push(["lineTo", ...a]),
    arc: (...a) => calls.push(["arc", ...a]),
    fill: () => calls.push(["fill"]),
    stroke: () => calls.push(["stroke"]),
    strokeRect: (...a) => calls.push(["strokeRect", ...a]),
    fillText: (text, ...a) => calls.push(["fillText", text, ...a]),
  };
  // fillStyle 是属性而非方法：用 setter 记录，才能断言"这块板涂的什么颜色"
  let style = "";
  Object.defineProperty(ctx, "fillStyle", {
    get: () => style,
    set: (v) => { style = String(v); calls.push(["fillStyle", style]); },
  });
  Object.defineProperty(ctx, "strokeStyle", {
    get: () => style,
    set: (v) => { style = String(v); calls.push(["strokeStyle", String(v)]); },
  });
  return ctx;
}
const count = (ctx, name) => ctx.calls.filter((call) => call[0] === name).length;

// 1) 深度：近处亮、远处暗（0=近 ⇒ 白，1=远 ⇒ 黑，alpha 满）
{
  const rgba = depthFrameToRgba([0, 0.5, 1], 1, 3);
  assert.equal(rgba.width, 3);
  assert.equal(rgba.height, 1);
  assert.equal(rgba.data[0], 255, "最近点应为白");
  assert.equal(rgba.data[4], 128, "0.5 应为中灰");
  assert.equal(rgba.data[8], 0, "最远点应为黑");
  assert.equal(rgba.data[3], 255, "alpha 必须为不透明");
}

// 2) 深度：非法输入返回 null（不抛异常，面板不能把主循环带崩）
{
  assert.equal(depthFrameToRgba(null, 1, 1), null);
  assert.equal(depthFrameToRgba([0, 0], 1, 3), null, "长度不足应拒绝");
  assert.equal(depthFrameToRgba([0], 0, 1), null, "尺寸非法应拒绝");
}

// 3) 深度：NaN 按最远处理（画成黑），不产生 NaN 像素
{
  const rgba = depthFrameToRgba([NaN], 1, 1);
  assert.equal(rgba.data[0], 0);
  assert.ok(Number.isFinite(rgba.data[0]));
}

// 4) 深度贴图：恰好一次 putImageData
{
  const ctx = makeCtx();
  assert.equal(drawDepthFrame(ctx, [0, 1, 0, 1], 2, 2), true);
  assert.equal(count(ctx, "putImageData"), 1);
}

// 5) 俯视高度场：低偏蓝、高偏黄、**没打中是纯黑空槽**
//    （缺值必须与"很低"在视觉上分开：一块悬空墙角与一个坑不能长得一样）
{
  const px = (image, i) => [image.data[i * 4], image.data[i * 4 + 1], image.data[i * 4 + 2]];
  const image = heightFieldToRgba([0, 1, 2, 3], 2);
  assert.equal(image.width, 2);
  assert.equal(image.height, 2);
  assert.deepEqual(px(image, 0), [30, 80, 180], "最低处偏蓝");
  assert.deepEqual(px(image, 3), [255, 255, 40], "最高处偏黄");
  const gap = heightFieldToRgba([0, null, Number.NaN, 3], 2);
  assert.deepEqual(px(gap, 1), [0, 0, 0], "没打中 → 黑槽");
  assert.deepEqual(px(gap, 2), [0, 0, 0], "NaN 同样是没打中（`Number(null) === 0` 会把它当零高度）");
}

// 6) 高度场：全平不除零；输入不足 / 非数组返回 null（面板不能把主循环带崩）
{
  const flat = heightFieldToRgba([2, 2, 2, 2], 2);
  assert.equal(flat.data[0], Math.round(30 + 0.5 * 225), "全平取中线");
  assert.equal(heightFieldToRgba([1], 2), null, "元素不足 side² → null");
  assert.equal(heightFieldToRgba(null, 2), null);
}

// 7) 轨迹投影：等比 + y 轴翻转（世界 y 大 ⇒ 屏幕 y 小）
{
  const flat = projectTrail([[0, 0], [10, 0]], { width: 100, height: 100, padding: 10 });
  assert.ok(flat.scale > 0);
  assert.equal(flat.points[0][1], flat.points[1][1], "同一水平线上的两点屏幕 y 应相同");
  const rising = projectTrail([[0, 0], [0, 10]], { width: 100, height: 100, padding: 10 });
  assert.ok(rising.points[1][1] < rising.points[0][1], "世界 y 大者屏幕 y 小（未上下颠倒）");
  assert.equal(rising.y0, 0, "y0 必须回传，供位姿点复用基准");
}

// 8) 轨迹投影：等比而非拉伸（长宽比保留）
{
  const wide = projectTrail([[0, 0], [100, 0]], { width: 100, height: 100, padding: 0 });
  const square = projectTrail([[0, 0], [100, 100]], { width: 100, height: 100, padding: 0 });
  const wideSpan = Math.abs(wide.points[1][0] - wide.points[0][0]);
  const squareSpan = Math.abs(square.points[1][0] - square.points[0][0]);
  assert.equal(wideSpan, squareSpan, "同一 scale 下 100 单位的 x 跨度应一致");
}

// 9) 轨迹投影：空输入与非法点被剔除
{
  assert.deepEqual(projectTrail([], { width: 10, height: 10 }).points, []);
  const filtered = projectTrail([[1, 2], [NaN, 3], ["a", "b"]], { width: 10, height: 10 });
  assert.equal(filtered.points.length, 1);
}

// 10) 轨迹绘制：path 3 点 ⇒ 1 次 moveTo + 2 次 lineTo；无位姿则不画箭头
{
  const ctx = makeCtx();
  drawTrail(ctx, { path: [[0, 0], [1, 0], [2, 0]], width: 60, height: 40 });
  assert.equal(count(ctx, "moveTo"), 1);
  assert.equal(count(ctx, "lineTo"), 2);
  assert.equal(count(ctx, "arc"), 0, "没给位姿不该画机器人点");
}

// 11) 位姿箭头与轨迹同基准（起点落在画布内，否则说明基准用错了）
{
  const ctx = makeCtx();
  drawTrail(ctx, {
    path: [[0, 0], [10, 0]],
    pose: { x: 5, y: 0, yaw: 0 },
    width: 100,
    height: 100,
  });
  const moves = ctx.calls.filter((call) => call[0] === "moveTo");
  assert.equal(moves.length, 2, "轨迹一次 + 箭头一次");
  const [, ax, ay] = moves[moves.length - 1];
  assert.ok(ax > 0 && ax < 100 && ay > 0 && ay < 100, `箭头起点应在画布内，实际 ${ax},${ay}`);
  assert.equal(count(ctx, "arc"), 1, "机器人位置应画一个点");
}

// 注：原先这里还有两组 —— 12) `observationReadout`（读数格式化）与 13) `panelVisible`
//     （面板归属）。两者都已被取代：读数搬到 `sensor_dock.js::odomReadout`（多了世界系速度
//     与累计里程），归属搬到 `sensor_dock.js::dockVisible` + `DOCK_SOURCES.requires`
//     （来源与插件的依赖关系）。留着就是第二份"真值"，迟早与新的对不上。
//     `Number(null) === 0` 那个教训没丢 —— 它在 `odomReadout` 与 `applyMountEdit` 里各挡了一次。

// 12) 高度场绘制：**一次贴图**（不是每格一次 fillRect —— 24×24 会变成 576 次调用）
{
  const ctx = makeCtx();
  assert.equal(drawHeightField(ctx, new Array(24 * 24).fill(0.5), 24), true);
  assert.equal(count(ctx, "putImageData"), 1);
  assert.equal(count(ctx, "fillRect"), 0);
  assert.equal(drawHeightField(ctx, new Array(4).fill(0), 24), false, "元素不足时不贴");
}

// 13) 极坐标扫描：**未命中的方向不画任何东西**
//     （画到量程边界会让人以为"那边有障碍"，而实际是"那边什么都没有"）
{
  const ctx = makeCtx();
  const angles = [0, Math.PI / 2, Math.PI];
  assert.equal(
    drawPolarScan(ctx, { angles, distances: [5, -1, 10], maxDist: 10, width: 100, height: 100 }),
    true,
  );
  assert.equal(count(ctx, "fillRect"), 2, "3 条射线里只有 2 条命中");
  assert.equal(count(ctx, "stroke"), 5, "4 个量程环 + 1 个十字");
  // 命中点落在量程内：maxDist=10、width=100 ⇒ 半径 47，距离 5 应落在半径一半处
  const hit = ctx.calls.find((c) => c[0] === "fillRect");
  assert.ok(Math.abs(hit[1] - (50 + 47 * 0.5)) < 1.5, `5/10 应落在半径一半处，实际 x=${hit[1]}`);
  const miss = makeCtx();
  assert.equal(
    drawPolarScan(miss, { angles, distances: [-1, -1, -1], maxDist: 10, width: 100, height: 100 }),
    false,
    "全未命中：不画点，也不谎报画成功了",
  );
  assert.equal(count(miss, "fillRect"), 0);

  // **方位基准**（2026-09-22 钉住，见 screen_frame.js）：角度 0 = 局部 +x（机头）→ 屏幕右；
  // 绕 +z 逆时针 → **屏幕上**。于是"机头左侧（+y）有障碍"必须画在中心**上方**——
  // 画反了就是"障碍在机头左侧却出现在右侧"这类投诉的来源。
  const left = makeCtx();
  drawPolarScan(left, { angles: [Math.PI / 2], distances: [10], maxDist: 10, width: 100, height: 100 });
  const leftHit = left.calls.find((c) => c[0] === "fillRect");
  assert.ok(Math.abs(leftHit[1] - 50) < 1.5, `+y 方向应画在中心列，实际 x=${leftHit[1]}`);
  assert.ok(leftHit[2] < 50, `+y 方向（机身左侧）应画在中心**上方**，实际 y=${leftHit[2]}`);
}

// 14) 点云：俯视投影 + 位姿标记**共用同一套基准**（各算一份就会机器人与点云错开）
{
  const ctx = makeCtx();
  const points = [[0, 0, 1], [2, 0, 1], [0, 2, 1]];
  assert.equal(drawPointCloud(ctx, { points, pose: { x: 1, y: 1, yaw: 0 }, width: 100, height: 100 }), true);
  assert.equal(count(ctx, "fillRect"), 3, "每点一次 fillRect（z 不参与投影）");
  assert.equal(count(ctx, "arc"), 1, "机器人位置一次 arc");
  assert.equal(count(ctx, "moveTo"), 1, "朝向箭头一次 moveTo");
  assert.equal(drawPointCloud(makeCtx(), { points: [], width: 100, height: 100 }), false, "空点云不画");
  // 非法点被剔除：不因为一个 NaN 就让整张点云图缩成一团
  const dirty = makeCtx();
  drawPointCloud(dirty, { points: [[0, 0], [Number.NaN, 1], [2, 2]], width: 100, height: 100 });
  assert.equal(count(dirty, "fillRect"), 2);
}

// 15) 位姿标记：投影退化成 0 时不画（scale=0 时所有点挤在原点，箭头指向没意义）
{
  const ctx = makeCtx();
  assert.equal(drawPoseMarker(ctx, { scale: 0, origin: [0, 0], y0: 0 }, { x: 0, y: 0 }, 100), false);
  assert.equal(drawPoseMarker(ctx, { scale: 1, origin: [0, 0], y0: 0 }, null, 100), false, "无位姿不画");
  assert.equal(count(ctx, "arc"), 0);
}

// 16) blitRgba：尺寸从 image 取（**不能从别处传**，否则 putImageData 会静默画错位置）
{
  const ctx = makeCtx();
  const image = { width: 2, height: 3, data: new Uint8ClampedArray(2 * 3 * 4) };
  assert.equal(blitRgba(ctx, image, { x: 4, y: 5 }), true);
  assert.equal(count(ctx, "putImageData"), 1);
  const call = ctx.calls.find((c) => c[0] === "putImageData");
  assert.deepEqual([call[2], call[3]], [4, 5], "落到指定的 (x,y)");
  assert.equal(blitRgba(ctx, null, {}), false);
}

console.log("sensor_panels: 16 checks ok");


// 矩形高度网格（A 类契约 187 = 17×11）：方形渲染器喂矩形场会"有数据却画不出"
{
  const ctx = makeCtx();
  const field = new Array(187).fill(0.3);
  field[0] = 0.0; field[186] = 0.6; // 首末点拉出跨度，避免全平中间色不好判
  const ok = drawHeightGrid(ctx, field, 17, 11);
  assert.equal(ok, true, "17×11 矩形场应能画出");
  const puts = ctx.calls.filter(([op]) => op === "putImageData");
  assert.equal(puts.length, 1, "应有一次 putImageData");
  const img = puts[0][1];
  assert.equal(img.width, 17, "宽 = x 方向格数");
  assert.equal(img.height, 11, "高 = y 方向格数");
  // 空值画黑槽（不编高度）
  const withHoles = field.slice();
  withHoles[5] = null;
  assert.equal(drawHeightGrid(makeCtx(), withHoles, 17, 11), true, "含空值的场也要能画");
  // 长度不足必须拒（而不是画一张缺角的图）
  assert.equal(drawHeightGrid(makeCtx(), new Array(100).fill(0.1), 17, 11), false, "187 格场只有 100 个值要拒");
  assert.equal(drawHeightGrid(null, field, 17, 11), false, "ctx 缺失返回 false");

  // **值序 → 像素序**（2026-09-22 钉住）：场是 **x 主序**（`i = i_x*11 + i_y`），
  // 而 ImageData 是**行主序**。直接按 `i%17` 铺图会把这张表转置着乱序贴上去——
  // 平地看不出来（全同色），楼梯/斜坡上就是一片斜条（用户报的"高度图也是旋转过的"）。
  // 画布约定：+x 向右、+y 向上 ⇒ col = i_x、row = 11−1−i_y。
  const probe = new Array(187).fill(null);
  probe[0 * 11 + 0] = 0;    // (x=−0.8, y=−0.5)：左下角 ⇒ col 0、row 10
  probe[16 * 11 + 10] = 1;  // (x=+0.8, y=+0.5)：右上角 ⇒ col 16、row 0
  const gridCtx = makeCtx();
  assert.equal(drawHeightGrid(gridCtx, probe, 17, 11, { min: 0, max: 1 }), true);
  const image = gridCtx.calls.find(([op]) => op === "putImageData")[1];
  const pixel = (row, col) => {
    const i = (row * 17 + col) * 4;
    return [image.data[i], image.data[i + 1], image.data[i + 2]];
  };
  assert.deepEqual(pixel(10, 0), [30, 80, 180], "(x最小, y最小) 应落在左下角（最低色）");
  assert.deepEqual(pixel(0, 16), [255, 255, 40], "(x最大, y最大) 应落在右上角（最高色）");
  assert.deepEqual(pixel(0, 0), [0, 0, 0], "其余格是空值 ⇒ 黑槽（不编高度）");
}

// 足底接触：四块板、着地亮/离地暗、按 FL/FR/RL/RR 方位排
{
  const ctx = makeCtx();
  const calls = ctx.calls;
  const ok = drawContactStates(ctx, {
    feet: [
      { name: "FL", grounded: true, force: 12.5 },
      { name: "FR", grounded: false, force: 0 },
      { name: "RL", grounded: true, force: 9.1 },
      { name: "RR", grounded: false, force: 0 },
    ],
  });
  assert.equal(ok, true, "有脚数据应返回 true");
  const fills = calls.filter(([op]) => op === "fillRect");
  assert.ok(fills.length >= 5, `背景 + 四块板 = 至少 5 次 fillRect，实得 ${fills.length}`);
  // 着地的两块用绿色、离地的用暗灰
  const greens = calls.filter(([op, style]) => op === "fillStyle" && /34,\s*197,\s*94/.test(String(style)));
  const darks = calls.filter(([op, style]) => op === "fillStyle" && /100,\s*116,\s*139/.test(String(style)));
  assert.equal(greens.length, 2, `着地两脚应为绿，实得 ${greens.length}`);
  assert.equal(darks.length, 2, `离地两脚应为暗，实得 ${darks.length}`);
  // 足名必须画出来（方位错位的投诉永远查不完，所以名字要在图上）
  const texts = calls.filter(([op]) => op === "fillText").map(([, text]) => text);
  for (const name of ["FL", "FR", "RL", "RR"]) assert.ok(texts.includes(name), `图上必须有 ${name}`);
  // 空数据不抛错、返回 false
  assert.equal(drawContactStates(makeCtx(), { feet: [] }), false, "无脚数据返回 false");
  assert.equal(drawContactStates(null, { feet: [] }), false, "ctx 缺失也返回 false");
}
