// 射线求交单测（自包含，与 dwa_fan.test.mjs / sensor_panels.test.mjs 同风格）。
//
// 这套求交此前**没有任何测试** —— 它内联在 `pie_depth.js` 里、只被"深度图看起来对不对"间接覆盖。
// 抽成共用模块后，深度 / 高度扫描 / LiDAR / 点云都建立在它上面，所以这里用**可手算的几何**
// 逐个钉住：平面 / 球 / 盒的命中距离、多物体取最近、maxDist 截断、几何体自身旋转、body 位姿偏移。
import assert from "node:assert/strict";
import {
  fanDirections,
  gridOffsets,
  intersectSceneRay,
  intersectSceneRays,
  matTVec,
  mountOriginWorld,
  mountRayDirections,
  quatFromRpy,
  quatMul,
  quatRot,
  quatToMat,
  rayHitPoint,
  RAYCAST_GEOM_TYPES,
} from "./raycast.js";

/** 造一个最小可用的 MjModel/MjData：所有 geom 挂在 body 0 上。 */
function scene(geoms, { bodyPos = [0, 0, 0], bodyQuat = [1, 0, 0, 0] } = {}) {
  return {
    model: {
      ngeom: geoms.length,
      geom_type: Int32Array.from(geoms.map((g) => g.type)),
      geom_bodyid: Int32Array.from(geoms.map(() => 0)),
      geom_pos: Float64Array.from(geoms.flatMap((g) => g.pos || [0, 0, 0])),
      geom_quat: Float64Array.from(geoms.flatMap((g) => g.quat || [1, 0, 0, 0])),
      geom_size: Float64Array.from(geoms.flatMap((g) => g.size)),
    },
    data: {
      xpos: Float64Array.from(bodyPos),
      xquat: Float64Array.from(bodyQuat),
    },
  };
}

const DOWN = [0, 0, -1];
const near = (a, b, tol = 1e-9) => Math.abs(a - b) < tol;

// 1) 平面：从 z=1 垂直向下 → 命中 1
{
  const { model, data } = scene([{ type: 0, size: [0, 0, 1] }]);
  assert.ok(near(intersectSceneRay(model, data, [0, 0, 1], DOWN), 1), "平面命中应为 1");
}

// 2) 球：球心在原点、r=1，从 z=5 向下 → 4
{
  const { model, data } = scene([{ type: 2, size: [1, 0, 0] }]);
  assert.ok(near(intersectSceneRay(model, data, [0, 0, 5], DOWN), 4), "球面命中应为 4");
}

// 3) 盒：中心在原点、半边长 1，从 z=5 向下 → 4
{
  const { model, data } = scene([{ type: 6, size: [1, 1, 1] }]);
  assert.ok(near(intersectSceneRay(model, data, [0, 0, 5], DOWN), 4), "盒面命中应为 4");
}

// 4) 背向：射线朝外，不应命中
{
  const { model, data } = scene([{ type: 0, size: [0, 0, 1] }]);
  assert.equal(intersectSceneRay(model, data, [0, 0, 1], [0, 0, 1]), -1, "背向不应命中");
}

// 5) 多物体：取**最近**命中（盒更远、平面更近 → 应报平面）
{
  const { model, data } = scene([
    { type: 6, size: [1, 1, 1], pos: [0, 0, -3] }, // 顶面 z=-2 ⇒ 距离 7
    { type: 0, size: [0, 0, 1] }, // 平面 z=0 ⇒ 距离 5
  ]);
  assert.ok(near(intersectSceneRay(model, data, [0, 0, 5], DOWN), 5), "应取最近命中");
}

// 6) maxDist 截断：超出即视为未命中（pie_depth 靠它把远处压成"无穷远"）
{
  const { model, data } = scene([{ type: 0, size: [0, 0, 1] }]);
  assert.equal(
    intersectSceneRay(model, data, [0, 0, 5], DOWN, { maxDist: 3 }),
    -1,
    "超出 maxDist 应视为未命中",
  );
  assert.ok(
    near(intersectSceneRay(model, data, [0, 0, 5], DOWN, { maxDist: 6 }), 5),
    "范围内应命中",
  );
}

// 7) 几何体**自身带旋转**：size=[1,1,0.5] 绕 x 转 90° 后，z 向半厚变成 1 → 命中 4
{
  const q = [Math.cos(Math.PI / 4), Math.sin(Math.PI / 4), 0, 0];
  const { model, data } = scene([{ type: 6, size: [1, 1, 0.5], quat: q }]);
  assert.ok(
    near(intersectSceneRay(model, data, [0, 0, 5], DOWN), 4, 1e-9),
    "旋转后盒面命中应为 4（说明 geom_quat 参与了求交）",
  );
}

// 8) **body 位姿**参与求交：body 抬高 2 → 盒顶面 z=3 ⇒ 距离 2
{
  const { model, data } = scene([{ type: 6, size: [1, 1, 1] }], { bodyPos: [0, 0, 2] });
  assert.ok(near(intersectSceneRay(model, data, [0, 0, 5], DOWN), 2), "body 抬高后命中应为 2");
}

// 9) 类型过滤：mesh(7) 不参与 —— 已知局限（好处是相机不会拍到自己身上的网格）
{
  const { model, data } = scene([{ type: 7, size: [1, 1, 1] }]);
  assert.equal(intersectSceneRay(model, data, [0, 0, 5], DOWN), -1, "mesh 不参与求交");
  assert.ok(!RAYCAST_GEOM_TYPES.includes(7), "mesh 不在支持类型里");
  assert.deepEqual(RAYCAST_GEOM_TYPES, [0, 2, 6]);
}

// 10) 四元数工具自洽：绕 z 转 90° 应把 x 轴变成 y 轴
{
  const q = [Math.cos(Math.PI / 4), 0, 0, Math.sin(Math.PI / 4)];
  const r = quatRot(q, [1, 0, 0]);
  assert.ok(Math.abs(r[0]) < 1e-12 && Math.abs(r[1] - 1) < 1e-12, `x 应变成 y，实际 ${r}`);
  assert.deepEqual(quatMul([1, 0, 0, 0], [1, 2, 3, 4]), [1, 2, 3, 4], "单位四元数左乘应不变");
  const m = quatToMat([1, 0, 0, 0]);
  assert.deepEqual(m, [1, 0, 0, 0, 1, 0, 0, 0, 1], "单位四元数应是单位阵");
  assert.deepEqual(matTVec(m, [1, 2, 3]), [1, 2, 3], "单位阵转置乘应不变");
}

// 11) 高度扫描的**起点网格**：行优先，第 0 行是机头（+x）、每行第 0 列是左侧（+y）。
//     这个顺序**直接决定俯视高度场图的朝向** —— 错了图会上下颠倒，而颠倒的图看着仍然"像地形"。
{
  const { offsets, side } = gridOffsets(3, 1);
  assert.equal(side, 3);
  assert.equal(offsets.length, 9);
  assert.deepEqual(offsets[0], [1, 1], "左上角 = 机头 + 左侧");
  assert.deepEqual(offsets[2], [1, -1], "右上角 = 机头 + 右侧");
  assert.deepEqual(offsets[6], [-1, 1], "左下角 = 机尾 + 左侧");
  assert.deepEqual(offsets[8], [-1, -1], "右下角 = 机尾 + 右侧");
  assert.deepEqual(gridOffsets(1, 1).offsets, [[1, 1]], "边长 1：只有一格（不除零）");
  assert.deepEqual(gridOffsets(2, 0).offsets, [[0, 0], [0, 0], [0, 0], [0, 0]], "半径 0：都落在装配点");
}

// 12) 扇扫方向：整圈均布、从 +x 起逆时针，且落在**局部 x-y 平面**内
//     （默认装配 rpy=[0,0,0] 时这个平面正好水平 —— 这就是"水平扇扫"的来历）
{
  const { dirs, angles, count } = fanDirections(4);
  assert.equal(count, 4);
  assert.deepEqual(angles, [0, Math.PI / 2, Math.PI, (3 * Math.PI) / 2]);
  assert.ok(near(dirs[0][0], 1) && near(dirs[0][1], 0), "第一条是 +x");
  assert.ok(near(dirs[1][0], 0) && near(dirs[1][1], 1), "逆时针 90° → +y");
  assert.ok(dirs.every((d) => near(d[2], 0)), "扇扫是平面的（z 分量为 0）");
}

// 13) 批量求交：逐条配对（**多起点同方向**正是高度扫描的形状），长度取短者，未命中仍是 -1
{
  const { model, data } = scene([{ type: 0, size: [0, 0, 0] }]);
  assert.deepEqual(intersectSceneRays(model, data, [[0, 0, 3], [0, 0, 5]], [DOWN, DOWN]), [3, 5]);
  assert.deepEqual(intersectSceneRays(model, data, [[0, 0, 3]], [DOWN, DOWN]), [3], "长度取短者");
  assert.deepEqual(
    intersectSceneRays(model, data, [[0, 0, 3], [0, 0, 3]], [[0, 0, 1], [0, 0, 1]]),
    [-1, -1],
    "背向不命中",
  );
}

// 14) 命中点：未命中返回 **null**，不返回射线终点
//     （返回终点会在点云/极坐标图上凭空画出一个"什么都没有"的点，看着像障碍）
{
  assert.deepEqual(rayHitPoint([0, 0, 3], DOWN, 3), [0, 0, 0]);
  assert.equal(rayHitPoint([0, 0, 3], DOWN, -1), null);
  assert.equal(rayHitPoint([0, 0, 3], DOWN, Number.NaN), null);
  assert.equal(rayHitPoint([0, 0, 3], DOWN, null), null, "`Number(null) === 0` 不能当成命中在原点");
}

// 15) 装配 → 世界系：装配点随**机身姿态**转，射线方向是"机身姿态 × 装配姿态"
{
  const s = Math.SQRT1_2;
  const baseQuat = [s, 0, 0, s]; // 机身绕 z 转 90°（+x → +y）
  const origin = mountOriginWorld([1, 2, 3], baseQuat, [0.5, 0, 0]);
  assert.ok(
    near(origin[0], 1) && near(origin[1], 2.5) && near(origin[2], 3),
    `装配点 +0.5m 在机体系前方 → 机身后，世界系应落在 +y，实际 ${origin}`,
  );
  // 装配再朝前 90°（局部 −z → 局部 +x）；机身已转 90° ⇒ 世界系应为 +y
  const [dir] = mountRayDirections(baseQuat, quatFromRpy([0, -Math.PI / 2, 0]), [[0, 0, -1]]);
  assert.ok(near(dir[0], 0, 1e-9) && near(dir[1], 1, 1e-9) && near(dir[2], 0, 1e-9), `实际 ${dir}`);
}

console.log("raycast: 15 checks ok");
