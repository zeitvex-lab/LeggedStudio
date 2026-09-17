// PIE（Go2 深度跑酷）浏览器端深度相机 —— 无 GL 依赖的 CPU raycast。
//
// 对齐上游 00_resources/parkour_mjlab deploy/pie/sim2sim/contract.py：
//   60×106 相机（fovy 由 HFOV 87° 反解）→ 光学-Z → 裁 10px/侧 → 3×3 高斯 →
//   裁 [0.05,3] → /3；输出单帧 1×60×86（历史 2 帧由调用方维护）。
// MuJoCo WASM 未导出 mj_ray，故对 plane / sphere / box 三类地形 geom 做解析求交；
// 网格类 geom（机器人本体）跳过，既省算力也避免自身遮挡（相机装在机头前）。

import { intersectSceneRay, quatMul, quatRot, quatToMat } from "./raycast.js";

const GAUSS = [
  0.07511361, 0.12384140, 0.07511361,
  0.12384140, 0.20417996, 0.12384140,
  0.07511361, 0.12384140, 0.07511361,
];

export function createPieDepth({ sim, contract }) {
  if (!sim?.model || !sim?.data) return null;
  const cfg = contract?.depth_camera || {};
  const HEIGHT = Math.max(1, Math.round(Number(cfg.height) || 60));
  const RAW_W = Math.max(2, Math.round(Number(cfg.raw_width) || 106));
  const CROP = Math.max(0, Math.round(Number(cfg.crop) || 10));
  const WIDTH = RAW_W - 2 * CROP;
  const MIN_M = Number(cfg.min_m ?? 0.05);
  const MAX_M = Number(cfg.max_m ?? 3.0);
  const UPDATE_STEPS = Math.max(1, Math.round(Number(cfg.update_steps) || 5));
  const HFOV = Number(cfg.horizontal_fov_deg ?? 87.0);
  const FOVY = Number(cfg.fovy_deg) > 0
    ? Number(cfg.fovy_deg)
    : (2 * Math.atan(Math.tan((HFOV * Math.PI) / 360) * HEIGHT / RAW_W) * 180) / Math.PI;
  const CAM_POS = (cfg.pos || [0.345, 0.0, 0.07]).map(Number);
  const CAM_QUAT = (cfg.quat || [0.5792280, 0.4055798, -0.4055798, -0.5792280]).map(Number);
  const BASE_BODY = String(cfg.base_body || "base");
  const focal = (0.5 * HEIGHT) / Math.tan((FOVY * Math.PI) / 360);

  const dirs = new Float64Array(HEIGHT * RAW_W * 3);
  const zScale = new Float64Array(HEIGHT * RAW_W);
  for (let v = 0; v < HEIGHT; v += 1) {
    const py = (v + 0.5 - 0.5 * HEIGHT) / focal;
    for (let u = 0; u < RAW_W; u += 1) {
      const px = (u + 0.5 - 0.5 * RAW_W) / focal;
      const n = Math.sqrt(px * px + py * py + 1);
      const i = v * RAW_W + u;
      dirs[i * 3] = -px / n;
      dirs[i * 3 + 1] = -py / n;
      dirs[i * 3 + 2] = -1 / n;
      zScale[i] = Math.sqrt(1 + px * px + py * py);
    }
  }

  function bodyPose() {
    const model = sim.model;
    const data = sim.data;
    let bid = -1;
    if (typeof sim.mujoco?.mj_name2id === "function" && sim.mujoco.mjtObj) {
      // mj_name2id 的 objtype 形参是 **int**（WASM toWireType），必须传枚举的数值。
      // 直接把 emscripten 枚举对象（{value: 1}）传进去会每帧抛
      // `Cannot convert "[object Object]" to int` —— 深度帧链路整个断掉，
      // 页面表现为「当前策略无深度输入」+ 仿真时钟停在 0（app.js 各处都先过 enumValue）。
      const objtype = sim.mujoco.mjtObj.mjOBJ_BODY?.value ?? sim.mujoco.mjtObj.mjOBJ_BODY;
      if (Number.isFinite(Number(objtype))) {
        bid = Number(sim.mujoco.mj_name2id(model, Number(objtype), String(BASE_BODY)));
      }
    }
    if (bid < 0) {
      for (let b = 1; b < Number(model.nbody || 0); b += 1) {
        if (String(model.body?.[b]?.name || "") === BASE_BODY) { bid = b; break; }
      }
    }
    if (bid < 0) bid = 1;
    return {
      pos: [data.xpos[bid * 3], data.xpos[bid * 3 + 1], data.xpos[bid * 3 + 2]],
      quat: [data.xquat[bid * 4], data.xquat[bid * 4 + 1], data.xquat[bid * 4 + 2], data.xquat[bid * 4 + 3]],
    };
  }

  // 求交搬到 raycast.js（深度 / 高度扫描 / LiDAR / 点云共用同一套几何 ——
  // 各写一份的话「深度图与高度场对不上」这类问题永远查不完）。
  // 上限沿用原来的 `MAX_M * 1.5`：超出该距离的命中在 60×86 的深度图里与"无穷远"无区别。
  function intersectRay(origin, dir) {
    return intersectSceneRay(sim.model, sim.data, origin, dir, { maxDist: MAX_M * 1.5 });
  }

  function captureRaw() {
    const { pos, quat } = bodyPose();
    const off = quatRot(quat, CAM_POS);
    const origin = [pos[0] + off[0], pos[1] + off[1], pos[2] + off[2]];
    const camRot = quatToMat(quatMul(quat, CAM_QUAT));
    const depth = new Float32Array(HEIGHT * RAW_W);
    for (let v = 0; v < HEIGHT; v += 1) {
      for (let u = 0; u < RAW_W; u += 1) {
        const i = v * RAW_W + u;
        const dx = dirs[i * 3], dy = dirs[i * 3 + 1], dz = dirs[i * 3 + 2];
        const world = [
          camRot[0] * dx + camRot[1] * dy + camRot[2] * dz,
          camRot[3] * dx + camRot[4] * dy + camRot[5] * dz,
          camRot[6] * dx + camRot[7] * dy + camRot[8] * dz,
        ];
        const dist = intersectRay(origin, world);
        depth[i] = dist > 0 ? dist / zScale[i] : MAX_M;
      }
    }
    return depth;
  }

  function toFrame(depth) {
    const cropped = new Float32Array(HEIGHT * WIDTH);
    for (let v = 0; v < HEIGHT; v += 1) {
      for (let u = 0; u < WIDTH; u += 1) {
        const idx = v * RAW_W + u + CROP;
        cropped[v * WIDTH + u] = Math.min(Math.max(depth[idx] * zScale[idx], MIN_M), MAX_M);
      }
    }
    const pw = WIDTH + 2;
    const padded = new Float32Array((HEIGHT + 2) * pw);
    for (let v = 0; v < HEIGHT + 2; v += 1) {
      const sv = v === 0 ? 1 : (v === HEIGHT + 1 ? HEIGHT : v);
      for (let u = 0; u < WIDTH + 2; u += 1) {
        const su = u === 0 ? 1 : (u === WIDTH + 1 ? WIDTH : u);
        padded[v * pw + u] = cropped[(sv - 1) * WIDTH + (su - 1)];
      }
    }
    const out = new Float32Array(HEIGHT * WIDTH);
    for (let v = 0; v < HEIGHT; v += 1) {
      for (let u = 0; u < WIDTH; u += 1) {
        let acc = 0;
        for (let kv = 0; kv < 3; kv += 1) {
          for (let ku = 0; ku < 3; ku += 1) {
            acc += padded[(v + kv) * pw + (u + ku)] * GAUSS[kv * 3 + ku];
          }
        }
        out[v * WIDTH + u] = Math.min(Math.max(acc, MIN_M), MAX_M) / MAX_M;
      }
    }
    return out;
  }

  return {
    frameShape: [1, HEIGHT, WIDTH],
    updateSteps: UPDATE_STEPS,
    captureFrame() { return toFrame(captureRaw()); },
  };
}
