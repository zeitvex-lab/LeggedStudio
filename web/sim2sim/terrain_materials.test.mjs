// 地形材质包测试：漆装表完整性（对 _index.json 全量）+ 画笔可复现性。
// 画笔只依赖标准 2D API，用记录型 stub context 断言调用序列——Node 里无需 canvas。
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  TERRAIN_KITS,
  resolveTerrainKit,
  paintFloorTile,
  createPaletteRandom,
  __painters,
} from "./terrain_materials.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const MAP_IDS = JSON.parse(readFileSync(join(HERE, "../../assets/maps/_index.json"), "utf8"))
  .maps.map((m) => m.id);

test("漆装表覆盖地图库全量：_index.json 的每张地图都有专属漆装", () => {
  for (const id of MAP_IDS) {
    assert.ok(TERRAIN_KITS[id], `地图 ${id} 缺漆装包`);
  }
});

test("每套漆装的字段完整：pattern 已注册、cell>0、颜色合法、props 齐全", () => {
  for (const [id, kit] of Object.entries(TERRAIN_KITS)) {
    assert.ok(__painters[kit.floor.pattern], `${id}.floor.pattern 未注册`);
    assert.ok(kit.floor.cell > 0, `${id}.floor.cell 必须为正`);
    for (const key of Object.keys(kit.floor)) {
      if (/^(a|b|base|seam|stripe|line)$/.test(key)) {
        assert.match(kit.floor[key], /^#[0-9a-f]{6}$/i, `${id}.floor.${key} 颜色非法`);
      }
    }
    assert.match(kit.props.color, /^#[0-9a-f]{6}$/i, `${id}.props.color 非法`);
    assert.ok(typeof kit.props.roughness === "number", `${id}.props.roughness 缺失`);
  }
});

test("未知地图 id 落兜底漆装（不 throw——新地图没配漆装也必须能渲染）", () => {
  const kit = resolveTerrainKit("some_future_map");
  assert.equal(kit, resolveTerrainKit("another_unknown"));
  assert.ok(kit.floor && kit.props);
  assert.notEqual(kit.floor.pattern, undefined);
});

test("flat 用 MuJoCo 经典棋盘格（用户裁决 2026-09-22）", () => {
  assert.equal(TERRAIN_KITS.flat.floor.pattern, "checker");
  // texgrid 原配色 rgb1 0.2 0.3 0.4 / rgb2 0.3 0.4 0.5
  assert.equal(TERRAIN_KITS.flat.floor.a, "#334d66");
  assert.equal(TERRAIN_KITS.flat.floor.b, "#4d6680");
});

test("棋盘画笔：底色一次 + 交错色两块（2×2 贴片）", () => {
  const calls = [];
  const ctx = recordCtx(calls);
  paintFloorTile(ctx, 128, TERRAIN_KITS.flat.floor);
  const rects = calls.filter((c) => c.op === "fillRect");
  assert.equal(rects.length, 3); // 底色 + 两块交错色
  assert.equal(rects[0].args[2], 128); // 底色铺满
  assert.equal(rects[1].args[2], 64); // 交错色半格
});

test("同一漆装两次绘制逐调用可复现（种子固定，噪点不漂移）", () => {
  const spec = TERRAIN_KITS.warehouse.floor;
  const a = [];
  const b = [];
  paintFloorTile(recordCtx(a), 128, spec);
  paintFloorTile(recordCtx(b), 128, spec);
  assert.deepEqual(a, b);
});

test("随机序列同种子一致、异种子不同（噪点可复现的根基）", () => {
  const r1 = createPaletteRandom(42);
  const r2 = createPaletteRandom(42);
  const r3 = createPaletteRandom(43);
  const seq1 = [r1(), r1(), r1()];
  const seq2 = [r2(), r2(), r2()];
  const seq3 = [r3(), r3(), r3()];
  assert.deepEqual(seq1, seq2);
  assert.notDeepEqual(seq1, seq3);
});

function recordCtx(sink) {
  const handler = {
    get(_target, op) {
      if (op === "canvas") return { width: 0, height: 0 };
      return (...args) => sink.push({ op, args });
    },
    set(_target, prop, value) {
      sink.push({ op: `set:${prop}`, args: [value] });
      return true;
    },
  };
  return new Proxy({}, handler);
}
