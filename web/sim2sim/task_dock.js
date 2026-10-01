// 任务插件坞：**同一 sensor-dock 模式**（单一悬浮坞 + 下拉选择 + 就绪度诚实显示）。
//
// **为什么单独一个模块**：任务清单来自 `/api/task-plugins`（后端注册表），就绪度来自
// instantiate——都是**数据**，纯函数能在 Node 里断言；DOM 层只负责填充与展示。
//
// **归属**：`data-surface="advanced"`——任务插件是高级仿真模块；基础仿真（策略验证）
// 不显示，与传感器坞同一分层纪律（sensor_dock.js::dockVisible）。

/**
 * 从 `/api/task-plugins` 载荷提取下拉选项（纯函数）。
 * 失败/空注册表返回 []——调用方据此显示"不可用"，不编造选项。
 */
export function taskPluginOptions(payload) {
  const plugins = (payload && Array.isArray(payload.plugins)) ? payload.plugins : [];
  return plugins
    .filter((p) => p && p.plugin_id && p.label)
    .map((p) => ({ id: p.plugin_id, label: p.label, taskType: p.task_type || "" }));
}

/**
 * 就绪度一行摘要（纯函数）：ok/verified/blockers 三态诚实展示——
 * "声明可实例化"不等于"能跑"（传感器插件止步 registered 的既有纪律）。
 */
export function readinessLine(readiness) {
  const r = readiness || {};
  const parts = [`ok=${!!r.ok}`, `verified=${!!r.verified}`];
  const blockers = Array.isArray(r.blockers) ? r.blockers : [];
  for (const b of blockers) {
    parts.push(`阻断: ${typeof b === "string" ? b : JSON.stringify(b)}`);
  }
  return parts.join(" ｜ ");
}

/**
 * 选中项变化后的 UI 状态（纯函数）：note 文本与可见性。
 */
export function selectionState(pluginId, readiness, error) {
  if (error) return { showNote: true, text: `实例化失败: ${error.message}` };
  if (!pluginId) return { showNote: false, text: "" };
  return { showNote: true, text: readinessLine(readiness) };
}
