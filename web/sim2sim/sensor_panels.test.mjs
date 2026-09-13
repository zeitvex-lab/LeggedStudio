// 观测面板绘制器单测（自包含断言，与 dwa_fan.test.mjs 同风格）。
//
// 这些绘制器此前**一个都不存在**（深度只喂策略、高度图只展示契约、2D 平面只有地图编辑器）。
// 用**假 ctx** 断言"画了什么、画在哪"——不需要浏览器，CI 里直接跑。
import assert from "node:assert/strict";
import {
  depthFrameToRgba,
  drawDepthFrame,
  drawHeightScan,
  drawTrail,
  heightScanToBars,
  observationReadout,
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
  };
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

// 5) 高度扫描：相对归一（含全平与显式 min/max）
{
  assert.deepEqual(heightScanToBars([0, 1, 2]), [0, 0.5, 1]);
  assert.deepEqual(heightScanToBars([5, 5, 5]), [0.5, 0.5, 0.5], "全平应取中线而不是除零");
  assert.deepEqual(heightScanToBars([]), []);
  assert.deepEqual(heightScanToBars([1, 3], { min: 0, max: 4 }), [0.25, 0.75], "显式 min/max 生效");
}

// 6) 高度扫描绘制：每格一次 fillRect
{
  const ctx = makeCtx();
  assert.equal(drawHeightScan(ctx, [0, 1, 2, 3], { w: 40, h: 20 }), true);
  assert.equal(count(ctx, "fillRect"), 4);
  assert.equal(count(ctx, "clearRect"), 1, "重画前应清空，否则旧柱残留");
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

// 12) 数值读出：格式化与缺值占位（缺值必须是「—」而不是 0.00，否则看起来像真数据）
{
  const readout = observationReadout({
    pose: { x: 1.234, y: -0.5, yaw: Math.PI / 2 },
    angular: [0.1, 0.2, 0.3],
    baseHeight: 0.42,
  });
  assert.equal(readout.position, "1.23 , -0.50");
  assert.equal(readout.yaw, "90.0°");
  assert.equal(readout.angular, "0.10 / 0.20 / 0.30");
  assert.equal(readout.baseHeight, "0.42");
  const empty = observationReadout({});
  assert.equal(empty.position, "—");
  assert.equal(empty.yaw, "—");
  assert.equal(empty.angular, "—");
  assert.equal(empty.baseHeight, "—");
}

console.log("sensor_panels: 12 checks ok");
