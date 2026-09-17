// 地形归组单测（自包含断言，与 sensor_dock / raycast 同风格，`node web/sim2sim/terrain_groups.test.mjs` 直接跑）。
//
// 钉的是 G5「地形与扰动归组」的**规则**而不是 UI 像素：
//   · 内置分类快照与 assets/maps/_index.json **双向不漂移**（组序 / 组标签 / fallback / 每张图的 category）；
//   · 10 张地图分组正确：每张都出现、且**仅出现一次**、落在声明的组里；
//   · 未知 category **fail-closed** 落「其他」组（不消失、不进不存在的组、不抛异常）；
//   · 组序稳定：由 categories.order 声明决定，与地图出现顺序无关；「其他」固定排最后；
//   · 坏数据兜底：非对象条目 / 缺 id / 空 maps / 后端只下发 id-label-path 的 terrain options 都能分组。
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  categoriesFromIndex,
  flattenTerrainGroups,
  groupTerrains,
  TERRAIN_CATEGORIES,
  TERRAIN_CATEGORY_BY_ID,
} from "./terrain_groups.js";

const INDEX_URL = new URL("../../assets/maps/_index.json", import.meta.url);
const INDEX = JSON.parse(readFileSync(INDEX_URL, "utf-8"));

// 1) 内置快照 ↔ _index.json 双向核对（防漂移：改 _index.json 不改模块，这里就红）
{
  const cats = categoriesFromIndex(INDEX);
  assert.deepEqual(cats.order, TERRAIN_CATEGORIES.order, "categories.order 与 _index.json 不一致");
  for (const [key, def] of Object.entries(TERRAIN_CATEGORIES.definitions)) {
    assert.equal(cats.definitions[key]?.label, def.label, `组 ${key} 的中文标签与内置快照不一致`);
  }
  assert.equal(cats.fallback.key, TERRAIN_CATEGORIES.fallback.key);
  assert.equal(cats.fallback.label, TERRAIN_CATEGORIES.fallback.label);
  for (const map of INDEX.maps) {
    assert.equal(
      TERRAIN_CATEGORY_BY_ID[map.id],
      map.category,
      `地图 ${map.id} 的 category 在模块快照与 _index.json 之间不一致`,
    );
  }
  assert.equal(
    Object.keys(TERRAIN_CATEGORY_BY_ID).length,
    INDEX.maps.length,
    "内置快照的地图数与 _index.json 不一致（新图登记后要同步 terrain_groups.js）",
  );
}

// 2) 10 张地图全量分组：每张出现且仅出现一次，落在声明的组
{
  const maps = INDEX.maps.map((item) => ({ ...item }));
  const groups = groupTerrains(maps, cats());
  function cats() {
    return categoriesFromIndex(INDEX);
  }
  const flat = flattenTerrainGroups(groups);
  assert.equal(flat.length, maps.length, "分组后地图总数必须等于输入数（不丢不重）");
  const seen = new Map();
  for (const row of flat) seen.set(row.value, (seen.get(row.value) || 0) + 1);
  for (const map of maps) {
    assert.equal(seen.get(map.path), 1, `地图 ${map.id}（${map.path}）必须恰好出现一次`);
  }
  const groupOf = Object.fromEntries(
    groups.flatMap((group) => group.items.map((item) => [item.id, group.key])),
  );
  for (const map of maps) {
    assert.equal(groupOf[map.id], map.category, `地图 ${map.id} 应落组 ${map.category}`);
  }
  // 组标签是中文可读的（不是裸 key）
  for (const group of groups) {
    assert.notEqual(group.key, group.label, `组 ${group.key} 的标签应是中文，不能回退成裸 key`);
    assert.match(group.label, /[\u4e00-\u9fff]/, `组 ${group.key} 标签 "${group.label}" 应含中文`);
  }
}

// 3) 组序稳定：order 声明决定组序，与输入顺序无关；「其他」固定排最后
{
  const reversed = [...INDEX.maps].reverse();
  const forward = groupTerrains(INDEX.maps, categoriesFromIndex(INDEX)).map((group) => group.key);
  const backward = groupTerrains(reversed, categoriesFromIndex(INDEX)).map((group) => group.key);
  assert.deepEqual(backward, forward, "组序不应随输入顺序变化");
  assert.deepEqual(forward, TERRAIN_CATEGORIES.order.filter((key) => {
    return INDEX.maps.some((map) => map.category === key);
  }), "实际组序应等于 categories.order 的出现子序列");
}

// 4) 未知 / 未声明 category fail-closed 落「其他」
{
  const groups = groupTerrains([
    { id: "mystery_map", label: "来历不明", path: "mystery.xml", category: "lava" },
    { id: "no_cat", label: "没写分类", path: "no_cat.xml" },
  ], categoriesFromIndex(INDEX));
  const keys = groups.map((group) => group.key);
  assert.ok(!keys.includes("lava"), "未知 category 不能凭空造组");
  const other = groups.find((group) => group.key === "other");
  assert.ok(other, "未知/未声明 category 必须落「其他」组");
  assert.equal(other.label, "其他");
  assert.deepEqual(other.items.map((item) => item.id).sort(), ["mystery_map", "no_cat"]);
  const last = groups[groups.length - 1];
  assert.equal(last.key, "other", "「其他」组必须排最后");
}

// 5) 全未知数据也能分组：坏条目兜底成 option，不抛异常、不消失
{
  const groups = groupTerrains([null, 42, { label: "只有标签", path: "x.xml" }], categoriesFromIndex(INDEX));
  const flat = flattenTerrainGroups(groups);
  assert.equal(flat.length, 3, "坏条目也要保留（fail-closed，不丢弃）");
  assert.ok(groups.every((group) => group.key === "other"));
}

// 6) 后端 terrain options 形状（无 category 字段）按 id 查快照也能归组
{
  const options = [
    { id: "flat", label: "平地", path: "maps/flat.xml" },
    { id: "stairs", label: "楼梯", path: "maps/stairs.xml" },
    { id: "apartment", label: "公寓", path: "maps/apartment.xml" },
  ];
  const groups = groupTerrains(options, categoriesFromIndex(INDEX));
  const groupOf = Object.fromEntries(
    groups.flatMap((group) => group.items.map((item) => [item.id, group.key])),
  );
  assert.equal(groupOf.flat, "basic");
  assert.equal(groupOf.stairs, "stairs");
  assert.equal(groupOf.apartment, "complex");
  const flat = flattenTerrainGroups(groups);
  assert.deepEqual(flat.map((row) => row.value), ["maps/flat.xml", "maps/stairs.xml", "maps/apartment.xml"]);
}

// 7) 空 / 坏 categories 块回内置快照；空 maps 出空分组
{
  assert.deepEqual(categoriesFromIndex(null), TERRAIN_CATEGORIES);
  assert.deepEqual(categoriesFromIndex({}), TERRAIN_CATEGORIES);
  // 空 order 声明回内置快照（fail-closed：空组序会把全部地图推进「其他」）
  assert.deepEqual(categoriesFromIndex({ categories: { order: [], definitions: null } }).order, TERRAIN_CATEGORIES.order);
  assert.deepEqual(groupTerrains([], categoriesFromIndex(INDEX)), []);
  assert.deepEqual(groupTerrains(undefined), []);
  // categories 定义缺失某 key 时标签回退成 key 本身（不抛异常）
  const degraded = groupTerrains([{ id: "flat", label: "平地", path: "flat.xml", category: "basic" }], {
    order: ["basic"],
    definitions: {},
    fallback: TERRAIN_CATEGORIES.fallback,
  });
  assert.equal(degraded[0].label, "basic", "缺定义时标签回退为 key");
}

// 8) flattenTerrainGroups 保留 option 需要的 value/label/group 三元组
{
  const rows = flattenTerrainGroups([
    { key: "basic", label: "基础平地", items: [{ id: "flat", label: "平地", path: "flat.xml" }] },
  ]);
  assert.deepEqual(rows, [{ group: "基础平地", value: "flat.xml", label: "平地" }]);
}

console.log("terrain_groups.test.mjs: 8 组断言全部通过 ✔");
