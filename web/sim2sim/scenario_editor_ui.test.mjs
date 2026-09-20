// Scenario 编辑器 **DOM 接线**的防漂移测试（`node web/sim2sim/scenario_editor_ui.test.mjs`）。
//
// 为什么值得单独一条：`scenario_editor_ui.js` 里全是 `$("scXxx")`，而 id 定义在
// `web/advanced_sim.html`。**两边一旦对不上，只有人点开页面才会发现**（节点为 null →
// TypeError，静默或半死）。这类"两个文件靠字符串对齐"的耦合，本仓的一贯做法是**写成测试**
// （同 terrain_groups ↔ assets/maps/_index.json 的核对）。这里做三件事：
//   1. `ui.js` 引用的每个 id 都必须在 HTML 里存在；
//   2. HTML 必须真的加载该模块（否则编辑器根本不会跑）；
//   3. 反向抽查：编辑器声明的四段（场景/地图/传感器/任务/判据）标题都在页面上。
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { SCENARIO_STEPS } from "./scenario_editor.js";

const HTML = readFileSync(new URL("../advanced_sim.html", import.meta.url), "utf-8");
const UI = readFileSync(new URL("./scenario_editor_ui.js", import.meta.url), "utf-8");

const htmlIds = new Set([...HTML.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1]));

// 1) JS 里 `$("...")` 引用的 id 必须都在 HTML 里
{
  const referenced = new Set([...UI.matchAll(/\$\("([^"]+)"\)/g)].map((match) => match[1]));
  assert.ok(referenced.size >= 20, `应从 ui.js 抽出至少 20 个 id，实际 ${referenced.size}`);
  const missing = [...referenced].filter((id) => !htmlIds.has(id));
  assert.deepEqual(missing, [], `advanced_sim.html 缺少这些 id（ui.js 会取到 null）：${missing.join(", ")}`);
}

// 1b) 动态拼的 id（`scCheck_${key}` / `scRecorder_${key}`）必须与模块导出的候选集合一致
{
  for (const prefix of ["scCheck_", "scRecorder_"]) {
    assert.ok(UI.includes(`${prefix}\${key}`), `ui.js 应动态生成 ${prefix}<key>`);
  }
  const staticIds = ["scChecks", "scRecorders"];
  for (const id of staticIds) {
    assert.ok(htmlIds.has(id), `动态勾选组的宿主 #${id} 必须在 HTML 里`);
  }
}

// 2) HTML 必须挂上模块脚本
{
  assert.match(HTML, /<script type="module" src="sim2sim\/scenario_editor_ui\.js"><\/script>/,
    "advanced_sim.html 必须加载 scenario_editor_ui.js（type=module）");
  assert.ok(htmlIds.has("advSimFrame"), "必须有仿真视口 #advSimFrame");
}

// 3) 四段标题齐（S5 要求的 地图 / 传感器 / 任务 / 判据，外加场景身份）
{
  for (const title of ["场景", "地图", "传感器", "任务", "判据"]) {
    assert.ok(HTML.includes(`<h3>${title}</h3>`), `编辑器缺少「${title}」段`);
  }
}

// 4) 启动按钮默认禁用（未校验前不许点 —— 与 bindingGate 的默认取向一致）
{
  assert.match(HTML, /id="scStart" disabled/, "启动按钮必须默认 disabled，由闸门打开");
}

// 5) 步骤条：宿主存在，且**步骤表的每个 id 都能在 HTML 里找到对应段落**
//    （这是"加一段 = 步骤表加一条 + HTML 加一段"的唯一可自动核对处；对不上＝那一段永远不显示）
{
  assert.ok(htmlIds.has("scSteps"), "编辑器必须有步骤条宿主 #scSteps");
  assert.ok(htmlIds.has("scStepHint"), "必须有步骤说明位 #scStepHint");
  const sectionSteps = new Set([...HTML.matchAll(/data-step="([^"]+)"/g)].map((match) => match[1]));
  const missing = SCENARIO_STEPS.map((step) => step.id).filter((id) => !sectionSteps.has(id));
  assert.deepEqual(missing, [], `步骤表里的这些段在 HTML 里没有 data-step：${missing.join(", ")}`);
  assert.match(UI, /#scSteps \[data-step\]/, "selectStep 应按 data-step 切换激活态");
}

console.log("scenario_editor_ui.test.mjs: 6 组断言全部通过 ✔");
