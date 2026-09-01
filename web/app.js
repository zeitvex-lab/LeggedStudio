const state = { summary: null, records: [], loading: false };

const $ = (id) => document.getElementById(id);
const labels = {
  readiness: { direct_mujoco_candidate: "直接候选", morphology_only: "仅形态", adapter_required: "需适配器", repair_required: "需修复", supporting: "辅助记录" },
  locomotion: { point_foot: "点足", wheeled_leg: "轮足", active_wheel_foot: "主动轮足", unknown: "未知" },
  role: { robot: "机器人", scene: "场景", task_fragment: "任务片段", supporting: "辅助" },
};
const readinessOrder = ["direct_mujoco_candidate", "morphology_only", "adapter_required", "repair_required", "supporting"];

function text(value, fallback = "--") { return value === null || value === undefined || value === "" ? fallback : String(value); }
function formatMass(record) {
  const value = record.classification_mass_kg ?? record.explicit_mass_kg;
  return value === null || value === undefined ? "--" : `${Number(value).toFixed(2)} kg`;
}
function readinessClass(value) {
  if (value === "repair_required") return "danger";
  if (value === "adapter_required" || value === "morphology_only") return "warning";
  return "";
}
function displayReadiness(value) { return labels.readiness[value] || text(value); }
function displayLocomotion(value) { return labels.locomotion[value] || text(value); }
function uniqueValues(key) { return [...new Set(state.records.map((record) => record[key]).filter(Boolean))].sort(); }

function setConnection(status, label) {
  const pill = $("connection-pill");
  pill.className = `status-pill status-${status}`;
  pill.textContent = label;
}

function populateFilters() {
  const definitions = [["readiness-filter", uniqueValues("readiness"), displayReadiness], ["size-filter", uniqueValues("size_class_by_mass"), (v) => `Size ${v}`], ["locomotion-filter", uniqueValues("locomotion"), displayLocomotion]];
  definitions.forEach(([id, values, formatter]) => {
    const select = $(id);
    const current = select.value;
    select.innerHTML = '<option value="">全部</option>';
    values.forEach((value) => { const option = document.createElement("option"); option.value = value; option.textContent = formatter(value); select.append(option); });
    select.value = values.includes(current) ? current : "";
  });
}

function filteredRecords() {
  const query = $("search-input").value.trim().toLowerCase();
  const readiness = $("readiness-filter").value;
  const size = $("size-filter").value;
  const locomotion = $("locomotion-filter").value;
  return state.records.filter((record) => {
    const haystack = [record.family, record.model_name, record.path, record.format].join(" ").toLowerCase();
    return (!query || haystack.includes(query)) && (!readiness || record.readiness === readiness) && (!size || record.size_class_by_mass === size) && (!locomotion || record.locomotion === locomotion);
  });
}

function renderSummary() {
  const summary = state.summary || {};
  $("metric-families").textContent = text(summary.family_count);
  $("metric-robots").textContent = text(summary.robot_records);
  $("metric-direct").textContent = text(summary.readiness?.direct_mujoco_candidate);
  $("metric-repair").textContent = text(summary.readiness?.repair_required);
  $("readiness-total").textContent = `${text(summary.quadruped_xml_records, "0")} records`;
  $("schema-version").textContent = `schema ${text(summary.schema_version || state.inventorySchema)}`;
  const readiness = summary.readiness || {};
  const total = Object.values(readiness).reduce((sum, value) => sum + Number(value || 0), 0) || 1;
  $("readiness-bars").innerHTML = readinessOrder.map((key, index) => {
    const count = Number(readiness[key] || 0); const pct = Math.round((count / total) * 100);
    const colors = ["green", "blue", "amber", "red", "gray"];
    return `<div><div class="bar-label"><span>${displayReadiness(key)}</span><b>${count} <small>${pct}%</small></b></div><div class="bar-track"><div class="bar-fill ${colors[index]}" style="width:${pct}%"></div></div></div>`;
  }).join("");
  const counts = {};
  state.records.forEach((record) => { const key = record.locomotion || "unknown"; counts[key] = (counts[key] || 0) + 1; });
  $("taxonomy-list").innerHTML = Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([key, count]) => `<div class="taxonomy-item"><span>${displayLocomotion(key)}</span><strong>${count}</strong></div>`).join("") || '<div class="empty-state">暂无构型数据</div>';
}

function renderTable() {
  const records = filteredRecords();
  $("result-count").textContent = `${records.length} 条记录`;
  const body = $("asset-table-body");
  if (!records.length) { body.innerHTML = '<tr><td colspan="8" class="empty-state">没有符合当前筛选条件的资产</td></tr>'; return; }
  body.innerHTML = records.map((record) => {
    const missing = Number(record.missing_mesh_ref_count || 0);
    const mesh = missing ? `<span class="mesh-warn">缺 ${missing}</span>` : `<span class="mesh-ok">${text(record.mesh_ref_count, "0")} / 完整</span>`;
    return `<tr><td class="family-cell"><strong>${text(record.family)}</strong><span title="${text(record.path)}">${text(record.model_name)} · ${text(record.path)}</span></td><td><span class="format-tag">${text(record.format).toUpperCase()}</span></td><td><span class="role-tag">${labels.role[record.role] || text(record.role)}</span></td><td>${formatMass(record)}</td><td>${text(record.movable_joint_count ?? record.joint_count)}</td><td>${displayLocomotion(record.locomotion)}</td><td><span class="readiness-tag ${readinessClass(record.readiness)}">${displayReadiness(record.readiness)}</span></td><td>${mesh}</td></tr>`;
  }).join("");
}

function render() { renderSummary(); populateFilters(); renderTable(); }
function showError(message) { $("error-message").textContent = message; $("error-panel").hidden = false; setConnection("error", "离线"); }
function hideError() { $("error-panel").hidden = true; }

async function loadData() {
  if (state.loading) return;
  state.loading = true; setConnection("loading", "连接中"); hideError();
  try {
    const responses = await Promise.all([fetch("/api/summary", { headers: { Accept: "application/json" } }), fetch("/api/assets?limit=500", { headers: { Accept: "application/json" } })]);
    const failed = responses.find((response) => !response.ok);
    if (failed) throw new Error(`后端返回 HTTP ${failed.status}`);
    const [summary, assets] = await Promise.all(responses.map((response) => response.json()));
    if (!assets || !Array.isArray(assets.records)) throw new Error("资产接口返回格式无效");
    state.summary = summary; state.records = assets.records; state.inventorySchema = summary.schema_version || "unknown";
    $("last-updated").textContent = new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
    setConnection("ok", "已连接"); render();
  } catch (error) {
    state.summary = null; state.records = []; render(); showError(error instanceof Error ? error.message : "无法读取后端资产数据");
  } finally { state.loading = false; }
}

["readiness-filter", "size-filter", "locomotion-filter"].forEach((id) => $(id).addEventListener("change", renderTable));
$("search-input").addEventListener("input", renderTable);
$("clear-filters").addEventListener("click", () => { $("search-input").value = ""; ["readiness-filter", "size-filter", "locomotion-filter"].forEach((id) => { $(id).value = ""; }); renderTable(); });
$("refresh-button").addEventListener("click", loadData);
$("retry-button").addEventListener("click", loadData);
loadData();
