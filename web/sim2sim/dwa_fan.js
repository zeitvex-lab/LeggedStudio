// H11 局部规划器（DWA）候选扇形——**成形层**（纯函数，可 node 单测）。
//
// 数据来自服务端 `POST /api/navigation/local-plan`（`candidate_fan()` 的输出，见
// backend/dwa_planner.py）。这一层只做一件事：把「候选轨迹列表」变成页面（three.js）
// 能直接画的**折线集合**，按"最优 / 可行 / 被拒"分组——分组规则与颜色由调用方决定，
// 这里不碰渲染，因此可以脱离浏览器单测（与 navigation.js 的分工一致）。
//
// 约定：轨迹点 `[x, y, theta]`（world 米 / rad），输出折线为 `[[x, y], ...]`。

export const DWA_FAN_VERSION = "dwa-fan-1.0";

/** 取一条候选轨迹的平面折线（丢掉 theta；过滤非法点）。 */
function toPolyline(trajectory) {
  if (!Array.isArray(trajectory)) return [];
  const points = [];
  for (const point of trajectory) {
    if (!Array.isArray(point) || point.length < 2) continue;
    const x = Number(point[0]);
    const y = Number(point[1]);
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    points.push([x, y]);
  }
  return points;
}

/**
 * 把候选扇形拆成三组折线。
 *
 * @param {object[]} candidates 服务端 `candidates`（含 `valid` / `score` / `trajectory`）
 * @returns {{version: string, best: number[][][], valid: number[][][], rejected: number[][][], bestIndex: number|null}}
 *   `best` 恒为 0 或 1 条（可行候选中分数最高者），`valid`/`rejected` 分别是其余可行 / 被拒候选。
 */
export function fanSegments(candidates) {
  const list = Array.isArray(candidates) ? candidates : [];
  const valid = [];
  const rejected = [];
  let bestIndex = null;
  let bestScore = -Infinity;

  list.forEach((candidate, index) => {
    const polyline = toPolyline(candidate?.trajectory);
    if (!polyline.length) return;
    if (candidate?.valid) {
      valid.push({ index, polyline, score: Number(candidate?.score) });
      const score = Number(candidate?.score);
      if (Number.isFinite(score) && score > bestScore) {
        bestScore = score;
        bestIndex = valid.length - 1;
      }
    } else {
      rejected.push(polyline);
    }
  });

  const best = bestIndex === null ? [] : [valid[bestIndex].polyline];
  const others = valid.filter((_entry, position) => position !== bestIndex).map((entry) => entry.polyline);
  return { version: DWA_FAN_VERSION, best, valid: others, rejected, bestIndex };
}

/**
 * 扇形折线 → three.js `LineSegments` 顶点数组（每条折线展开成相邻点对）。
 *
 * 用 `LineSegments`（而不是 `Line`）是因为一次要画很多条候选，一个 BufferGeometry
 * 就够了；`stride` 可隔点抽样（候选多时减负，末点始终保留）。
 */
export function fanLineSegments(polylines, options = {}) {
  const stride = Math.max(1, Math.floor(Number(options.stride) || 1));
  const positions = [];
  for (const polyline of Array.isArray(polylines) ? polylines : []) {
    if (!Array.isArray(polyline) || polyline.length < 2) continue;
    const sampled = [];
    for (let i = 0; i < polyline.length; i += stride) sampled.push(polyline[i]);
    const last = polyline[polyline.length - 1];
    if (sampled[sampled.length - 1] !== last) sampled.push(last);
    for (let i = 0; i + 1 < sampled.length; i += 1) {
      positions.push(sampled[i][0], sampled[i][1], 0, sampled[i + 1][0], sampled[i + 1][1], 0);
    }
  }
  return positions;
}
