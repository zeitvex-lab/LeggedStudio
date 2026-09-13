// H11 扇形成形层单测（node --test 风格的自包含断言，与 observation_builders.test.mjs 同风格）。
import assert from "node:assert/strict";
import { fanSegments, fanLineSegments, DWA_FAN_VERSION } from "./dwa_fan.js";

function makeCandidate(v, w, valid, score, trajectory) {
  return { v, w, valid, score, trajectory };
}

// 1) 基本分组：可行 / 被拒 / 最优
{
  const candidates = [
    makeCandidate(0.5, 0.0, true, 1.5, [[0, 0, 0], [0.5, 0, 0]]),
    makeCandidate(0.5, 0.3, true, 2.5, [[0, 0, 0], [0.4, 0.2, 0.3]]),
    makeCandidate(0.5, -0.3, false, -Infinity, [[0, 0, 0], [0.3, -0.1, -0.3]]),
    makeCandidate(-0.5, 0.0, false, -Infinity, [[0, 0, 0], [-0.3, 0, 0]]),
  ];
  const fan = fanSegments(candidates);
  assert.equal(fan.version, DWA_FAN_VERSION);
  assert.equal(fan.best.length, 1, "应选出一条最优");
  assert.equal(fan.valid.length, 1, "另一条可行候选进 valid");
  assert.equal(fan.rejected.length, 2, "两条被拒候选进 rejected");
  // 最优是分数最高的那条（trajectory 末端 y=0.2）
  assert.equal(fan.best[0][1][1], 0.2);
}

// 2) 被拒候选的 trajectory 为空时不画
{
  const fan = fanSegments([makeCandidate(0.5, 0, false, -Infinity, [])]);
  assert.equal(fan.best.length, 0);
  assert.equal(fan.rejected.length, 0);
}

// 3) 全部被拒 ⇒ 无 best
{
  const fan = fanSegments([
    makeCandidate(0.5, 0, false, -Infinity, []),
    makeCandidate(-0.5, 0, false, -Infinity, []),
  ]);
  assert.equal(fan.bestIndex, null);
  assert.equal(fan.best.length, 0);
}

// 4) 非法输入不抛错
{
  const fan = fanSegments(null);
  assert.equal(fan.best.length, 0);
  assert.equal(fan.valid.length, 0);
  assert.equal(fan.rejected.length, 0);
}

// 5) 非法轨迹点被过滤
{
  const fan = fanSegments([
    makeCandidate(0.5, 0, true, 1, [[0, 0, 0], [Number.NaN, 1, 0], [1, 1, 0]]),
  ]);
  assert.equal(fan.best.length, 1);
  assert.equal(fan.best[0].length, 2, "NaN 点应被过滤");
}

// 6) LineSegments 顶点展开：n 点折线 → (n-1) 段 → 2*(n-1) 个点
{
  const positions = fanLineSegments([[[0, 0], [1, 0], [1, 1]]]);
  assert.equal(positions.length, 4 * 3, "2 段 × 2 点 × 3 分量");
  assert.deepEqual(positions.slice(0, 6), [0, 0, 0, 1, 0, 0]);
}

// 7) stride 抽样但保留末点
{
  const polyline = [[0, 0], [1, 0], [2, 0], [3, 0], [4, 0]];
  const full = fanLineSegments([polyline]);
  const sampled = fanLineSegments([polyline], { stride: 2 });
  assert.ok(sampled.length < full.length, "抽样后顶点更少");
  const lastX = sampled[sampled.length - 3];
  assert.equal(lastX, 4, "末点必须保留");
}

console.log("dwa_fan.test.mjs: all assertions passed");
