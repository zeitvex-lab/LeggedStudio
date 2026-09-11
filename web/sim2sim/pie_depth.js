// PIE（Go2 深度跑酷）浏览器端深度相机 —— 无 GL 依赖的 CPU raycast。
//
// 对齐上游 00_resources/parkour_mjlab deploy/pie/sim2sim/contract.py：
//   60×106 相机（fovy 由 HFOV 87° 反解）→ 光学-Z → 裁 10px/侧 → 3×3 高斯 →
//   裁 [0.05,3] → /3；输出单帧 1×60×86（历史 2 帧由调用方维护）。
// MuJoCo WASM 未导出 mj_ray，故对 plane / sphere / box 三类地形 geom 做解析求交；
// 网格类 geom（机器人本体）跳过，既省算力也避免自身遮挡（相机装在机头前）。

const GAUSS = [
  0.07511361, 0.12384140, 0.07511361,
  0.12384140, 0.20417996, 0.12384140,
  0.07511361, 0.12384140, 0.07511361,
];

function quatMul(a, b) {
  return [
    a[0] * b[0] - a[1] * b[1] - a[2] * b[2] - a[3] * b[3],
    a[0] * b[1] + a[1] * b[0] + a[2] * b[3] - a[3] * b[2],
    a[0] * b[2] - a[1] * b[3] + a[2] * b[0] + a[3] * b[1],
    a[0] * b[3] + a[1] * b[2] - a[2] * b[1] + a[3] * b[0],
  ];
}
function quatRot(q, v) {
  const [w, x, y, z] = q;
  const t = [2 * (y * v[2] - z * v[1]), 2 * (z * v[0] - x * v[2]), 2 * (x * v[1] - y * v[0])];
  return [
    v[0] + w * t[0] + (y * t[2] - z * t[1]),
    v[1] + w * t[1] + (z * t[0] - x * t[2]),
    v[2] + w * t[2] + (x * t[1] - y * t[0]),
  ];
}
function quatToMat(q) {
  const [w, x, y, z] = q;
  return [
    1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y),
    2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x),
    2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y),
  ];
}
function matTVec(m, v) {
  return [
    m[0] * v[0] + m[3] * v[1] + m[6] * v[2],
    m[1] * v[0] + m[4] * v[1] + m[7] * v[2],
    m[2] * v[0] + m[5] * v[1] + m[8] * v[2],
  ];
}

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
      bid = Number(sim.mujoco.mj_name2id(model, sim.mujoco.mjtObj.mjOBJ_BODY, BASE_BODY));
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

  function intersectRay(origin, dir) {
    const model = sim.model;
    const data = sim.data;
    let best = -1;
    const ngeom = Number(model.ngeom || 0);
    for (let g = 0; g < ngeom; g += 1) {
      const type = Number(model.geom_type[g]);
      if (type !== 0 && type !== 2 && type !== 6) continue; // plane/sphere/box
      const bodyId = Number(model.geom_bodyid[g]);
      const bq = [data.xquat[bodyId * 4], data.xquat[bodyId * 4 + 1], data.xquat[bodyId * 4 + 2], data.xquat[bodyId * 4 + 3]];
      const gp = [model.geom_pos[g * 3], model.geom_pos[g * 3 + 1], model.geom_pos[g * 3 + 2]];
      const gq = [model.geom_quat[g * 4], model.geom_quat[g * 4 + 1], model.geom_quat[g * 4 + 2], model.geom_quat[g * 4 + 3]];
      const gpw = quatRot(bq, gp);
      const pos = [data.xpos[bodyId * 3] + gpw[0], data.xpos[bodyId * 3 + 1] + gpw[1], data.xpos[bodyId * 3 + 2] + gpw[2]];
      const quat = quatMul(bq, gq);
      const size = [model.geom_size[g * 3], model.geom_size[g * 3 + 1], model.geom_size[g * 3 + 2]];
      let t = -1;
      if (type === 0) {
        const n = quatRot(quat, [0, 0, 1]);
        const denom = n[0] * dir[0] + n[1] * dir[1] + n[2] * dir[2];
        if (Math.abs(denom) < 1e-9) continue;
        const num = (pos[0] - origin[0]) * n[0] + (pos[1] - origin[1]) * n[1] + (pos[2] - origin[2]) * n[2];
        const tt = num / denom;
        if (tt > 1e-4) t = tt;
      } else {
        const m = quatToMat(quat);
        const o = matTVec(m, [origin[0] - pos[0], origin[1] - pos[1], origin[2] - pos[2]]);
        const d = matTVec(m, dir);
        if (type === 2) {
          const r = size[0];
          const a = d[0] * d[0] + d[1] * d[1] + d[2] * d[2];
          const b = 2 * (o[0] * d[0] + o[1] * d[1] + o[2] * d[2]);
          const c = o[0] * o[0] + o[1] * o[1] + o[2] * o[2] - r * r;
          const disc = b * b - 4 * a * c;
          if (disc >= 0 && a > 1e-12) {
            const tt = (-b - Math.sqrt(disc)) / (2 * a);
            if (tt > 1e-4) t = tt;
          }
        } else {
          let tmin = 0, tmax = Infinity, hit = true;
          for (let k = 0; k < 3; k += 1) {
            if (Math.abs(d[k]) < 1e-9) {
              if (Math.abs(o[k]) > size[k]) { hit = false; break; }
            } else {
              let t1 = (-size[k] - o[k]) / d[k];
              let t2 = (size[k] - o[k]) / d[k];
              if (t1 > t2) { const tmp = t1; t1 = t2; t2 = tmp; }
              tmin = Math.max(tmin, t1);
              tmax = Math.min(tmax, t2);
              if (tmin > tmax) { hit = false; break; }
            }
          }
          if (hit && tmax > 1e-4) t = Math.max(tmin, 1e-4);
        }
      }
      if (t > 0 && t <= MAX_M * 1.5 && (best < 0 || t < best)) best = t;
    }
    return best;
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
