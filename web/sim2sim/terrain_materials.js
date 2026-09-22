// 地形材质包（2026-09-22 用户指令：各地形要有区分度；flat 换 MuJoCo 经典棋盘格）。
//
// **为什么程序化 CanvasTexture**：WASM 侧 mjModel 不暴露 MJCF 纹理，`makeMaterial`
// 此前把所有地形 geom 涂同一个硬编码色（0x5f7486）——十一张地图一张脸。这里按地图
// 给一套**漆装**。取色习惯参考 MuJoCo menagerie 场景与 Gazebo/Isaac 教学环境的共识：
// 中性低饱和底色 + 少量高对比特征线——感知任务（步态/雷达/高度场）是主角，
// 地面只做"可读的背景"，不抢戏也不糊成一团。
//
// 结构约定：
//   * `floor.cell` = 一个纹理贴片覆盖的**世界米数**（调用方按 repeat = planeSize/cell
//     换算，保证任何地图换过来纹素密度一致）；
//   * `seamEvery`/`period` 等也是米（画笔内部按 S*米/cell 转像素）；
//   * 画笔只依赖标准 2D context API，且**只用注入的种子随机数**——同一参数逐像素可复现，
//     Node 里用 stub context 也能断言。

// 确定性 LCG（与传感器框架同族）：噪点/斑块的随机性必须可复现，测试才立得住。
export function createPaletteRandom(seed) {
  let s = (Number(seed) || 0) >>> 0;
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

/** 十一张地图的漆装表。`props` 是台阶/货箱/墙等非地面地形件的素色。 */
export const TERRAIN_KITS = {
  // MuJoCo 经典棋盘格：rgb1 0.2 0.3 0.4 / rgb2 0.3 0.4 0.5（texgrid 的原配色），
  // 机器人领域最眼熟的"默认检查环境"——基线验证就该长这样。
  flat: {
    label: "平地 · MuJoCo 经典棋盘格",
    floor: { pattern: "checker", a: "#334d66", b: "#4d6680", cell: 0.8 },
    props: { color: "#8a939c", roughness: 0.85, metalness: 0.02 },
  },
  // 混凝土预制台阶：浅灰底 + 细噪 + 0.3 m 接缝线（踏步尺度的参照物），
  // 台阶体比地面深一档，边缘在俯视时也可读。
  stairs: {
    label: "楼梯 · 混凝土",
    floor: { pattern: "concrete", base: "#99a1a8", seam: "#7e868e", seamEvery: 0.3, cell: 1.2 },
    props: { color: "#6d7680", roughness: 0.88, metalness: 0.02 },
  },
  cross_stairs: {
    label: "交叉楼梯 · 混凝土（深）",
    floor: { pattern: "concrete", base: "#99a1a8", seam: "#7e868e", seamEvery: 0.3, cell: 1.2 },
    props: { color: "#565f69", roughness: 0.88, metalness: 0.02 },
  },
  // 坡面用**沿行进方向的条纹**帮人读出坡向（斜坡走廊沿 x，横坡沿 y）——
  // 坡度是这几张图的考察点，地面纹理直接把方向画出来。
  slope: {
    label: "斜坡 · 条纹（沿 x）",
    floor: { pattern: "stripes", base: "#98938a", stripe: "#84807a", alongX: true, period: 0.5, cell: 2.0 },
    props: { color: "#7a756c", roughness: 0.9, metalness: 0.02 },
  },
  cross_slope: {
    label: "横坡 · 条纹（沿 y）",
    floor: { pattern: "stripes", base: "#8f949a", stripe: "#7d8288", alongX: false, period: 0.5, cell: 2.0 },
    props: { color: "#6f747a", roughness: 0.9, metalness: 0.02 },
  },
  // 高台：地面深灰混凝土，台面亮一档——落点判断看的是台面。
  high_platforms: {
    label: "高台 · 混凝土（亮台面）",
    floor: { pattern: "concrete", base: "#7d848c", seam: "#676e76", seamEvery: 0.5, cell: 1.5 },
    props: { color: "#a9b1b9", roughness: 0.82, metalness: 0.02 },
  },
  // 粗糙/起伏：土色系斑驳（户外土场），两家用相近但可分辨的底色。
  rough: {
    label: "粗糙地形 · 斑驳土色",
    floor: { pattern: "mottle", a: "#8a8272", b: "#75705f", spots: 150, cell: 2.5 },
    props: { color: "#6b665a", roughness: 0.95, metalness: 0.0 },
  },
  relief: {
    label: "起伏围场 · 斑驳沙色",
    floor: { pattern: "mottle", a: "#9c9484", b: "#857d6d", spots: 130, cell: 2.5 },
    props: { color: "#7a7364", roughness: 0.95, metalness: 0.0 },
  },
  // 仓库：工业地坪深灰 + 安全黄通道线（参考真实仓储地面画线），
  // 货箱用木箱棕——货架场景的通识配色。
  warehouse: {
    label: "仓库 · 工业地坪 + 通道线",
    floor: { pattern: "asphalt", base: "#6a6f75", line: "#d8b13a", lineEvery: 2.0, cell: 4.0 },
    props: { color: "#8c6f4d", roughness: 0.85, metalness: 0.02 },
  },
  // 赛道：沥青 + 白色分道线（真实跑道的画法），护栏素灰。
  race_track: {
    label: "赛道 · 沥青 + 分道线",
    floor: { pattern: "asphalt", base: "#55575c", line: "#e8e8e8", lineEvery: 1.5, cell: 3.0 },
    props: { color: "#4a4c50", roughness: 0.9, metalness: 0.02 },
  },
  // 公寓：室内木地板（条板 + 板缝），墙体素灰白。
  apartment: {
    label: "公寓 · 木地板",
    floor: { pattern: "planks", base: "#8a6f52", seam: "#6f583f", plankEvery: 0.12, cell: 1.2 },
    props: { color: "#b8b2a6", roughness: 0.8, metalness: 0.02 },
  },
  // 比赛场地：暖灰水泥台面 + 醒目黄标线（真实赛场的画法，与仓库的"深灰+窄黄线"、
  // 赛道的"深灰+白线"都拉开距离），障碍件压深一档 —— 场地大、障碍密，靠明度差读出结构。
  robocon_dual_track: {
    label: "RC2026障碍赛 · 赛场水泥 + 黄标线",
    floor: { pattern: "asphalt", base: "#7e7466", line: "#e0b83c", lineEvery: 2.5, cell: 5.0 },
    props: { color: "#4e5257", roughness: 0.9, metalness: 0.02 },
  },
};

const FALLBACK_KIT = {
  label: "默认 · 混凝土",
  floor: { pattern: "concrete", base: "#7f878e", seam: "#6a7178", seamEvery: 0.5, cell: 1.5 },
  props: { color: "#70787f", roughness: 0.88, metalness: 0.02 },
};

/** 地图 id → 漆装包（未知 id 落兜底，绝不 throw——新地图没配漆装也必须能渲染）。 */
export function resolveTerrainKit(mapId) {
  return TERRAIN_KITS[mapId] || FALLBACK_KIT;
}

// ── 画笔（浏览器 2D context；Node 里可注入 stub 逐调用断言）─────────────────

function fill(ctx, S, color) {
  ctx.fillStyle = color;
  ctx.fillRect(0, 0, S, S);
}

function speckle(ctx, S, rand, count, alpha) {
  // 细噪点：混凝土/沥青的"磨砂感"。半透明深浅点各半，避免整体变深/变浅。
  for (let i = 0; i < count; i += 1) {
    const x = rand() * S;
    const y = rand() * S;
    const r = 0.5 + rand() * 1.5;
    ctx.fillStyle = `rgba(${rand() > 0.5 ? "255,255,255" : "0,0,0"},${alpha * rand()})`;
    ctx.fillRect(x, y, r, r);
  }
}

export const __painters = {
  checker(ctx, S, spec) {
    fill(ctx, S, spec.a);
    ctx.fillStyle = spec.b;
    ctx.fillRect(0, 0, S / 2, S / 2);
    ctx.fillRect(S / 2, S / 2, S / 2, S / 2);
  },
  concrete(ctx, S, spec, rand) {
    fill(ctx, S, spec.base);
    speckle(ctx, S, rand, Math.round(S * 0.9), 0.07);
    const seamPx = (S * spec.seamEvery) / spec.cell;
    if (seamPx >= 4) {
      ctx.strokeStyle = spec.seam;
      ctx.lineWidth = Math.max(1, S / 256);
      ctx.beginPath();
      for (let p = seamPx; p < S; p += seamPx) {
        ctx.moveTo(p, 0); ctx.lineTo(p, S);
        ctx.moveTo(0, p); ctx.lineTo(S, p);
      }
      ctx.stroke();
    }
  },
  stripes(ctx, S, spec) {
    fill(ctx, S, spec.base);
    const periodPx = (S * spec.period) / spec.cell;
    const bandPx = Math.max(2, periodPx * 0.18);
    ctx.fillStyle = spec.stripe;
    if (spec.alongX) {
      for (let p = 0; p < S; p += periodPx) ctx.fillRect(0, p, S, bandPx);
    } else {
      for (let p = 0; p < S; p += periodPx) ctx.fillRect(p, 0, bandPx, S);
    }
    speckle(ctx, S, createPaletteRandom(7), Math.round(S * 0.5), 0.05);
  },
  mottle(ctx, S, spec, rand) {
    fill(ctx, S, spec.a);
    for (let i = 0; i < (spec.spots || 140); i += 1) {
      ctx.fillStyle = spec.b;
      ctx.globalAlpha = 0.2 + rand() * 0.25;
      ctx.beginPath();
      ctx.ellipse(rand() * S, rand() * S, 4 + rand() * 22, 3 + rand() * 14, rand() * Math.PI, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  },
  asphalt(ctx, S, spec, rand) {
    fill(ctx, S, spec.base);
    speckle(ctx, S, rand, Math.round(S * 1.2), 0.08);
    // 分道/通道线：一条贯穿 x 的实线（贴片平铺后成等距线网）。
    const linePx = (S * spec.lineEvery) / spec.cell;
    if (linePx >= 6) {
      ctx.strokeStyle = spec.line;
      ctx.lineWidth = Math.max(2, S / 170);
      ctx.setLineDash([S / 14, S / 10]);
      ctx.beginPath();
      ctx.moveTo(0, S / 2);
      ctx.lineTo(S, S / 2);
      ctx.stroke();
      ctx.setLineDash([]);
    }
  },
  planks(ctx, S, spec, rand) {
    fill(ctx, S, spec.base);
    const plankPx = (S * spec.plankEvery) / spec.cell;
    if (plankPx >= 3) {
      // 每块板轻微色差（木板的自然感），再画板缝。
      for (let p = 0; p < S; p += plankPx) {
        const shade = 0.9 + rand() * 0.2;
        ctx.fillStyle = `rgba(${shade > 1 ? "255,240,220" : "40,25,10"},${Math.abs(shade - 1) * 0.5})`;
        ctx.fillRect(p, 0, plankPx, S);
        ctx.fillStyle = spec.seam;
        ctx.fillRect(p, 0, Math.max(1, S / 340), S);
      }
    }
  },
};

/** 把 `spec` 涂到 S×S 的 2d context 上（含画笔分发）。返回使用的随机种子（测试可固定）。 */
export function paintFloorTile(ctx, S, spec, seed = 20260922) {
  const painter = __painters[spec.pattern];
  if (!painter) throw new Error(`terrain_materials: 未知地面画笔 "${spec.pattern}"`);
  painter(ctx, S, spec, createPaletteRandom(seed));
  return seed;
}
