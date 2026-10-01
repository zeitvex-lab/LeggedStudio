import test from "node:test";
import assert from "node:assert/strict";

import { taskPluginOptions, readinessLine, selectionState } from "./task_dock.js";

test("taskPluginOptions：正常载荷 → 提取 id/label/taskType", () => {
  const options = taskPluginOptions({
    plugins: [
      { plugin_id: "a", label: "A 任务", task_type: "nav" },
      { plugin_id: "b", label: "B 任务" },
    ],
  });
  assert.deepEqual(options, [
    { id: "a", label: "A 任务", taskType: "nav" },
    { id: "b", label: "B 任务", taskType: "" },
  ]);
});

test("taskPluginOptions：fail-closed——坏载荷/缺 id/缺 label 一律剔除", () => {
  assert.deepEqual(taskPluginOptions(null), []);
  assert.deepEqual(taskPluginOptions({}), []);
  assert.deepEqual(taskPluginOptions({ plugins: [null, {}, { plugin_id: "x" }, { label: "y" }] }), []);
});

test("readinessLine：ok/verified/blockers 诚实展示", () => {
  assert.equal(readinessLine({ ok: true, verified: false }), "ok=true ｜ verified=false");
  assert.equal(
    readinessLine({ ok: false, verified: false, blockers: ["传感器未实现", { code: 1 }] }),
    "ok=false ｜ verified=false ｜ 阻断: 传感器未实现 ｜ 阻断: {\"code\":1}",
  );
  assert.equal(readinessLine(null), "ok=false ｜ verified=false");
});

test("selectionState：三态（未选/错误/就绪度）", () => {
  assert.deepEqual(selectionState("", null, null), { showNote: false, text: "" });
  assert.deepEqual(selectionState("x", null, new Error("boom")), { showNote: true, text: "实例化失败: boom" });
  const s = selectionState("x", { ok: true, verified: false }, null);
  assert.equal(s.showNote, true);
  assert.match(s.text, /ok=true/);
});
