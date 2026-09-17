// 地形归组（G5「地形与扰动归组」）：从地图清单数据 → 分组结构的**纯函数**模块。
// 不读 DOM、不读 sim、不 fetch —— 只吃数据吐数据，所以 Node 单测能直接钉住规则。
//
// 数据源是 `assets/maps/_index.json`（schema map-library-1.0）：
//   · 顶层 `categories.order` 定义组序，`categories.definitions[key].label` 是中文组标签；
//   · 每张地图的 `category` 字段决定归组。
// 浏览器侧拿不到 _index.json 本体（后端下发的 terrain entry 只有 id/label/path，
// 且公共地图库走 /platform 静态目录），所以本模块内置一份与 _index.json 同源的
// 分类快照；`terrain_groups.test.mjs` 负责**双向核对**快照与 _index.json 不漂移。
//
// Fail-closed 规则：未声明 category、未知 category key、甚至坏数据（非对象条目）
// 一律落进「其他」兜底组 —— 分组展示可以不完美，但**任何一张地图都不能消失**。

/** 内置分类快照：与 assets/maps/_index.json 的 categories 块同源（测试钉住）。 */
export const TERRAIN_CATEGORIES = {
  order: ["basic", "stairs", "slope", "platform", "rough", "complex"],
  definitions: {
    basic: { label: "基础平地" },
    stairs: { label: "楼梯台阶" },
    slope: { label: "坡道斜面" },
    platform: { label: "高台障碍" },
    rough: { label: "崎岖起伏" },
    complex: { label: "综合场景" },
  },
  fallback: { key: "other", label: "其他" },
};

/** 内置地图分类快照：id → category（与 assets/maps/_index.json 的 maps[].category 同源）。 */
export const TERRAIN_CATEGORY_BY_ID = {
  flat: "basic",
  stairs: "stairs",
  cross_stairs: "stairs",
  high_platforms: "platform",
  cross_slope: "slope",
  race_track: "complex",
  rough: "rough",
  slope: "slope",
  relief: "rough",
  apartment: "complex",
};

/** 从 _index.json 形状的数据里读出分类定义（容错：坏/缺块回内置快照）。 */
export function categoriesFromIndex(index) {
  const cats = index && typeof index === "object" ? index.categories : null;
  if (!cats || typeof cats !== "object") return TERRAIN_CATEGORIES;
  const order = Array.isArray(cats.order) && cats.order.length
    ? cats.order.map((key) => String(key)).filter(Boolean)
    : TERRAIN_CATEGORIES.order;
  const definitions = {};
  for (const key of order) {
    const def = cats.definitions && typeof cats.definitions === "object" ? cats.definitions[key] : null;
    const label = def && typeof def === "object" && def.label ? String(def.label) : key;
    definitions[key] = { label };
  }
  const fb = cats.fallback && typeof cats.fallback === "object" ? cats.fallback : null;
  const fallback = {
    key: fb && fb.key ? String(fb.key) : TERRAIN_CATEGORIES.fallback.key,
    label: fb && fb.label ? String(fb.label) : TERRAIN_CATEGORIES.fallback.label,
  };
  return { order, definitions, fallback };
}

/**
 * 地图清单 → 有序分组结构。
 *
 * @param {Array<{id?:string, label?:string, category?:string}|*>} maps
 *        _index.json 的 maps 数组（或后端 terrain options —— 没有 category 时按 id 查快照）。
 * @param {object} [categories] categoriesFromIndex() 的产物；缺省用内置快照。
 * @returns {Array<{key:string, label:string, items:Array<object>}>}
 *          按 categories.order 的组序输出；「其他」兜底组**固定排最后**（有内容才出现）。
 *          每个item 原样保留入参对象（外加 id/label 缺省兜底），绝不丢弃。
 */
export function groupTerrains(maps, categories = TERRAIN_CATEGORIES) {
  const order = Array.isArray(categories?.order) ? categories.order : [];
  const definitions = categories?.definitions && typeof categories.definitions === "object"
    ? categories.definitions
    : {};
  const fallback = categories?.fallback && typeof categories.fallback === "object"
    ? categories.fallback
    : TERRAIN_CATEGORIES.fallback;
  const entries = Array.isArray(maps) ? maps : [];
  // 组桶按 order 初始化 → 组序由数据声明决定，与地图出现顺序无关（稳定）。
  const buckets = new Map(order.map((key) => [key, []]));
  const other = [];
  for (const item of entries) {
    const entry = item && typeof item === "object" ? item : {};
    const id = entry.id != null && String(entry.id).trim() ? String(entry.id) : "";
    const label = entry.label != null && String(entry.label).trim()
      ? String(entry.label)
      : (id || "未命名地图");
    const normalized = { ...entry, id, label };
    // category 优先取条目自身声明；没有则按 id 查内置快照（覆盖后端只下发 id/label/path 的情形）。
    let key = entry.category != null && String(entry.category).trim() ? String(entry.category).trim() : "";
    if (!key && id && TERRAIN_CATEGORY_BY_ID[id]) key = TERRAIN_CATEGORY_BY_ID[id];
    // fail-closed：未知 key 一律进兜底组，不进不存在的组，更不丢弃。
    const bucket = buckets.has(key) ? buckets.get(key) : other;
    bucket.push(normalized);
  }
  const groups = order
    .filter((key) => buckets.get(key).length)
    .map((key) => ({
      key,
      label: definitions[key]?.label || key,
      items: buckets.get(key),
    }));
  if (other.length) {
    groups.push({ key: fallback.key, label: fallback.label, items: other });
  }
  return groups;
}

/** 分组结构 → `<option>`/`<optgroup>` 的扁平描述（渲染层只管 createElement）。 */
export function flattenTerrainGroups(groups) {
  const rows = [];
  for (const group of Array.isArray(groups) ? groups : []) {
    for (const item of Array.isArray(group?.items) ? group.items : []) {
      rows.push({ group: group.label || "", value: item.path ?? item.value ?? item.id, label: item.label });
    }
  }
  return rows;
}
