// 屏幕系 / 相机系单测（`node web/sim2sim/sensors/screen_frame.test.mjs`）。
//
// **为什么这些断言值得单独一个文件**：朝向缺陷（画反、转置、上下颠倒）**不抛异常、
// 不改变任何读数**，只有人眼能发现——每次都要开浏览器、找一块楼梯、盯着图看很久。
// 把"哪边朝上"写成断言，缺陷就在 CI 里当场死，而不是等用户来报"图被旋转了"。
//
// 钉三件事：
//   1. 相机系：−z 光轴、+x 图像右、+y 图像上、帧数组行优先且**行 0 = 图像顶部**；
//   2. 平面画布系：+x 向右、+y 向上（含极坐标角度与俯视网格 i_x/i_y 的换算）；
//   3. 退化输入不产生 NaN（正朝下/正朝上的相机、空向量）。
import assert from "node:assert/strict";
import {
  CAMERA_AXES,
  cameraBasis,
  focalLength,
  gridIndexToPixel,
  pinholeRays,
  planeToCanvas,
  polarToCanvas,
  rayFromBasis,
} from "./screen_frame.js";

const near = (a, b, eps = 1e-9) => Math.abs(a - b) < eps;
const vecNear = (a, b, eps = 1e-9) => a.every((v, i) => near(v, b[i], eps));
const unit = (v) => near(Math.hypot(...v), 1, 1e-9);

// 1) 相机轴：光轴 −z（MuJoCo 约定），+x 右、+y 上
{
  assert.deepEqual(CAMERA_AXES.fwd, [0, 0, -1]);
  assert.deepEqual(CAMERA_AXES.right, [1, 0, 0]);
  assert.deepEqual(CAMERA_AXES.up, [0, 1, 0]);
  // fovy 90°、h=3 ⇒ focal = 1.5（0.5*3/tan45）
  assert.ok(near(focalLength(3, 90), 1.5));
}

// 2) 像素 → 射线：**行 0 = 图像顶部（+y）**、列 0 = 图像左侧（−x）、中心朝 −z
{
  const cam = pinholeRays({ width: 5, height: 3, fovy: 90 });
  assert.equal(cam.count, 15, "5×3");
  assert.equal(cam.directions.length, 15);
  assert.equal(cam.offsets.length, 15);
  for (const o of cam.offsets) assert.deepEqual(o, [0, 0, 0], "针孔的都从针心出发");
  for (const d of cam.directions) {
    assert.ok(unit(d), "方向必须归一");
    assert.ok(d[2] < 0, "必须朝 −z 半球（光轴）");
  }
  const mid = cam.directions[1 * 5 + 2];
  assert.ok(vecNear(mid, [0, 0, -1]), "正中像素朝 −z");
  const topLeft = cam.directions[0];
  const bottomRight = cam.directions[cam.count - 1];
  assert.ok(topLeft[0] < 0, "列 0 在图像左侧 ⇒ x 分量为负");
  assert.ok(topLeft[1] > 0, "行 0 在图像顶部 ⇒ y 分量为正（+y 朝上）");
  assert.ok(bottomRight[0] > 0 && bottomRight[1] < 0, "右下角反之");
  assert.ok(near(topLeft[0] + bottomRight[0], 0) && near(topLeft[1] + bottomRight[1], 0), "对角落严格反向");
  // 首行整行 y 都为正、末行整行 y 都为负（行序不能混淆）
  for (let u = 0; u < 5; u += 1) {
    assert.ok(cam.directions[u][1] > 0, `首行第 ${u} 列应在图像上侧`);
    assert.ok(cam.directions[10 + u][1] < 0, `末行第 ${u} 列应在图像下侧`);
  }
}

// 3) 基架：装配 rpy 只定"往哪看"，图像右/上由光轴 + 世界上方向构造
{
  // 正前视（+x）：右 = 机身 −y（机器人自己的右侧）、上 = 世界 +z
  const level = cameraBasis([1, 0, 0]);
  assert.ok(vecNear(level.right, [0, -1, 0]), `右应是机身右侧，实得 ${level.right}`);
  assert.ok(vecNear(level.up, [0, 0, 1]), `上应是世界上方向，实得 ${level.up}`);
  // 相机系右手：right × up = −fwd（z 轴朝后）
  const cross = [
    level.right[1] * level.up[2] - level.right[2] * level.up[1],
    level.right[2] * level.up[0] - level.right[0] * level.up[2],
    level.right[0] * level.up[1] - level.right[1] * level.up[0],
  ];
  assert.ok(vecNear(cross, [-1, 0, 0]), "right × up 必须是 −fwd");
  // 下俯（前视 + 低头）：右仍水平（不滚转），上抬高
  const pitched = cameraBasis([1, 0, -0.5]);
  assert.ok(vecNear(pitched.right, [0, -1, 0]), "俯仰不该把右轴转出水平面");
  assert.ok(pitched.up[2] > 0.8, "上应仍以世界 +z 为主");
  // 真·滚转（光轴带 y 分量）时才允许右轴离开 ±y
  const yawed = cameraBasis([1, 1, 0]);
  assert.ok(yawed.right[0] > 0 && yawed.right[1] < 0, "偏航 45° 时右轴应指向 (+, −, 0)");
  for (const b of [level, pitched, yawed]) {
    assert.ok(unit(b.fwd) && unit(b.right) && unit(b.up));
  }
}

// 4) 基架退化：正朝下 / 正朝上（光轴与世界上方向平行）不许出 NaN
{
  for (const fwd of [[0, 0, -1], [0, 0, 1], [0, 0, 0]]) {
    const basis = cameraBasis(fwd);
    for (const axis of [basis.fwd, basis.right, basis.up]) {
      assert.ok(axis.every((v) => Number.isFinite(v)), `退化输入 ${fwd} 不许出 NaN：${axis}`);
    }
    assert.ok(unit(basis.right) && unit(basis.up));
  }
}

// 5) 相机系射线 → 世界系：轴向量必须原样落位
{
  const basis = { fwd: [1, 0, 0], right: [0, -1, 0], up: [0, 0, 1] };
  assert.ok(vecNear(rayFromBasis(basis, [0, 0, -1]), [1, 0, 0]), "局部 −z（光轴）→ fwd");
  assert.ok(vecNear(rayFromBasis(basis, [1, 0, 0]), [0, -1, 0]), "局部 +x → 右");
  assert.ok(vecNear(rayFromBasis(basis, [0, 1, 0]), [0, 0, 1]), "局部 +y → 上");
  // 像素射线必须落在光轴半球（点积 > 0），别整出"回头看"
  const cam = pinholeRays({ width: 6, height: 4, fovy: 80 });
  for (const d of cam.directions) {
    const w = rayFromBasis(basis, d);
    assert.ok(w[0] > 0, "所有像素射线都应指向 fwd 一侧");
    assert.ok(unit(w), "世界系方向同样归一");
  }
}

// 6) 平面画布：+x 向右、+y 向上
{
  assert.deepEqual(planeToCanvas(1, 0, { cx: 10, cy: 20, scale: 2 }), [12, 20]);
  assert.deepEqual(planeToCanvas(0, 1, { cx: 10, cy: 20, scale: 2 }), [10, 18], "+y 向上 ⇒ 屏幕 y 减小");
  // 极坐标：0 rad → 右；π/2 → 上；π → 左；−π/2 → 下
  const around = (a) => polarToCanvas(a, 10, { cx: 0, cy: 0 });
  assert.ok(vecNear(around(0), [10, 0]));
  assert.ok(vecNear(around(Math.PI / 2), [0, -10]));
  assert.ok(vecNear(around(Math.PI), [-10, 0]));
  assert.ok(vecNear(around(-Math.PI / 2), [0, 10]));
}

// 7) 俯视网格：x 主序值序 → 行主序像素序（col = i_x、row = ny−1−i_y）
{
  assert.deepEqual(gridIndexToPixel(0, 0, 17, 11), { col: 0, row: 10 }, "(x最小,y最小) 在左下角");
  assert.deepEqual(gridIndexToPixel(16, 10, 17, 11), { col: 16, row: 0 }, "(x最大,y最大) 在右上角");
  assert.deepEqual(gridIndexToPixel(11, 5, 17, 11), { col: 11, row: 5 }, "机前 0.3m 居中那格");
  // 越界夹住（画布不能因为一个坏格号就把像素写到画布外）
  assert.deepEqual(gridIndexToPixel(-3, 99, 17, 11), { col: 0, row: 0 });
}

// 8) 170 个像素的"全图覆盖"自检：每格都落在画布内、且不重叠
{
  const seen = new Set();
  for (let ix = 0; ix < 17; ix += 1) {
    for (let iy = 0; iy < 11; iy += 1) {
      const { row, col } = gridIndexToPixel(ix, iy, 17, 11);
      assert.ok(row >= 0 && row < 11 && col >= 0 && col < 17, `格 (${ix},${iy}) 越界`);
      const key = row * 17 + col;
      assert.ok(!seen.has(key), `格 (${ix},${iy}) 与已有像素重叠 ⇒ 换算不是双射（图会被撕开）`);
      seen.add(key);
    }
  }
  assert.equal(seen.size, 17 * 11, "187 格必须一一对应 187 个像素");
}

console.log("screen_frame: 8 组断言全部通过 ✔");
