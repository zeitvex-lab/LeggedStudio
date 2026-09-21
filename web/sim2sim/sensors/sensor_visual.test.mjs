// 传感器可视化数据层单测（`node web/sim2sim/sensors/sensor_visual.test.mjs`）。
//
// 钉的是 Isaac 风格可视化的**数据侧**：彩虹高度着色、距离着色、接触状态映射。
// 3D 对象（THREE.Points/球/轴）的创建在 app.js，Node 里没有 WebGL 不测。
import assert from "node:assert/strict";
import {
  contactVisualStates,
  distancePointColors,
  distanceRamp,
  heightPointColors,
  heightRamp,
} from "./sensor_visual.js";

// 1) 彩虹渐变：端点与中点
{
  const low = heightRamp(0);
  const mid = heightRamp(0.5);
  const high = heightRamp(1);
  assert.ok(low[2] > 200 && low[0] < 100, "低处应为蓝");
  assert.ok(mid[1] > 180 && mid[0] < 120, "中点应为绿");
  assert.ok(high[0] > 200 && high[2] < 100, "高处应为红");
  // 越界钳制
  assert.deepEqual(heightRamp(-1), heightRamp(0));
  assert.deepEqual(heightRamp(2), heightRamp(1));
}

// 2) 高度场着色：min/max 归一、null 黑
{
  const field = [0, null, 0.5, 1];
  const colors = heightPointColors(field);
  assert.equal(colors.length, field.length * 3);
  // null 点保持黑（0,0,0）——调用方把位置藏到远处
  assert.deepEqual([colors[3], colors[4], colors[5]], [0, 0, 0]);
  // 最低点 = 蓝 (40,90,230)/255
  assert.ok(Math.abs(colors[0] - 40 / 255) < 1e-6, '最低点蓝');
  // 最高点 = 红 (235,70,40)/255
  assert.ok(Math.abs(colors[9] - 235 / 255) < 1e-6, '最高点红');
  // 全平取中点色（绿）
  const flat = heightPointColors([0.3, 0.3, 0.3]);
  // 全平：t=0.5 ⇒ 绿色 stop（205/255 ≈ 0.804）
  assert.ok(Math.abs(flat[1] - 205 / 255) < 1e-6, "全平高度场取彩虹中点色");
}

// 3) 距离着色：近绿远红、miss 黑
{
  const colors = distancePointColors([1, 5, 10, null, -1], 10);
  // 近（d=1）应偏绿：g 明显高于 r/b；远（d=10）应偏红：r 明显高于 g/b
  assert.ok(colors[1] > colors[0] && colors[1] > colors[2], `近点偏绿，实得 ${[colors[0],colors[1],colors[2]]}`);
  assert.ok(colors[6] > colors[7], "远点 r > g（偏红）");
  assert.deepEqual([colors[12], colors[13], colors[14]], [0, 0, 0], "miss 黑");
  assert.equal(colors[12], 0, "miss 位置应是黑");
  assert.equal(colors[13], 0, "miss 位置应是黑");
  assert.equal(colors[14], 0, "miss 位置应是黑");
}

// 4) 接触状态映射
{
  const states = contactVisualStates([
    { name: "FL", grounded: true, force: 12 },
    { name: "FR", grounded: false, force: 0 },
  ]);
  assert.equal(states[0].color[1], 0.77, "着地绿");
  assert.equal(states[0].scale, 1);
  assert.equal(states[1].scale, 0.6, "离地缩小");
  // 空数组与缺省不抛错
  assert.deepEqual(contactVisualStates([]), []);
  assert.deepEqual(contactVisualStates(null), []);
}

console.log("sensor_visual.test.mjs: 4 组断言全部通过 ✔");
