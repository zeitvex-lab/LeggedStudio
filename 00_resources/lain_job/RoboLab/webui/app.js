const $ = (id) => document.getElementById(id);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const post = (url, body) => fetch(url, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
const state = {
  name: "unitree_a1",
  model: "resources/robots/unitree_a1/urdf/unitree_a1.urdf",
  trainingModel: "resources/robots/unitree_a1/urdf/unitree_a1.urdf",
  inspection: null,
  jointConfig: {},
  mapping: {},
  methods: [],
  taskSpecs: [],
  runId: null,
  activeRunDir: null,
  useStandingPose: false,
  derivedProfile: null,
  saveTimer: null,
  viewer: null,
  previewRevision: 0,
};

// Keep the preview pose separate from the editable recipe values.  The joint
// sliders retain the Task defaults even when the standing-pose override is
// disabled, but the viewer must then explicitly show the URDF zero pose.
function applyPreviewPose() {
  const viewer = state.viewer;
  const joints = viewer?.robot?.joints || {};
  Object.entries(joints).forEach(([name, joint]) => {
    if (!joint?.setJointValue) return;
    const configured = state.jointConfig[name];
    const value = state.useStandingPose ? Number(configured?.default || 0) : 0;
    // URDF zero is a geometric reference and can sit outside a declared
    // operating limit (A1 calf joints are one example).  Ignore limits only
    // for this explicit zero-pose preview; Task standing poses remain clamped.
    viewer.setJoint(name, value, { ignoreLimits: !state.useStandingPose });
  });
  viewer?.robot?.updateMatrixWorld?.(true);
}

function renderTaskOptions() {
  const selectedMethod = $("method")?.value;
  const selectedFramework = $("framework")?.value;
  const compatible = state.taskSpecs.filter((spec) => spec.frameworks.includes(selectedFramework) && spec.methods.includes(selectedMethod));
  $("task").innerHTML = compatible.map((spec) => `<option value="${escapeHtml(spec.task_id)}">${escapeHtml(spec.display_name)} (${escapeHtml(spec.task_id)})</option>`).join("");
  const preferred = compatible.find((spec) => spec.robot_id === state.name) || compatible[0];
  if (preferred) $("task").value = preferred.task_id;
}

async function syncSelectedTaskModel() {
  const spec = state.taskSpecs.find((item) => item.task_id === $("task")?.value);
  const defaults = spec?.defaults?.[$("framework")?.value] || {};
  const control = defaults.control || {};
  if (defaults.num_envs != null) $("envs").value = defaults.num_envs;
  if (defaults.max_iterations != null) $("iterations").value = defaults.max_iterations;
  if (defaults.checkpoint_interval != null && $("checkpointInterval")) $("checkpointInterval").value = defaults.checkpoint_interval;
  if (defaults.seed != null) $("seed").value = defaults.seed;
  if (control.kp != null) $("kp").value = control.kp;
  if (control.kd != null) $("kd").value = control.kd;
  if (control.action_scale != null) $("scale").value = control.action_scale;
  if (control.decimation != null) $("decimation").value = control.decimation;
  if (control.target_height != null) $("height").value = control.target_height;
  const model = spec?.models?.[$("framework")?.value];
  const previewModel = spec?.preview_models?.[$("framework")?.value] || model;
  if (model) state.trainingModel = model;
  if (previewModel && previewModel !== state.model) {
    state.name = spec.robot_id;
    state.jointConfig = {};
    state.mapping = {};
    await inspectModel(previewModel);
  }
  Object.entries(defaults.joint_defaults || {}).forEach(([name, value]) => {
    if (state.jointConfig[name]) state.jointConfig[name].default = Number(value);
  });
  Object.values(state.jointConfig).forEach((value) => {
    value.kp = Number(control.kp ?? value.kp);
    value.kd = Number(control.kd ?? value.kd);
    value.action_scale = Number(control.action_scale ?? value.action_scale);
  });
  // Always apply a pose after Task defaults are merged.  This is deliberately
  // unconditional: disabling the override must actively restore every joint
  // to zero rather than leaving the previous standing pose on screen.
  applyPreviewPose();
  renderJoints();
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  }[c]));
}

function setPage(name) {
  $$(".pill[data-page]").forEach((button) => button.classList.toggle("active", button.dataset.page === name));
  $$(".section").forEach((section) => section.classList.toggle("active", section.dataset.section === name));
}

function defaultJointConfig(joint) {
  return {
    default: 0,
    soft_lower: joint.lower ?? -3.14,
    soft_upper: joint.upper ?? 3.14,
    kp: Number($("kp").value),
    kd: Number($("kd").value),
    action_scale: Number($("scale").value),
    direction: 1,
    zero_offset: 0,
    peak_torque: joint.effort ?? 40,
    efficient_rpm_min: 0,
    efficient_rpm_max: 3000,
  };
}

async function inspectModel(path) {
  $("modelStatus").textContent = "正在解析模型…";
  const response = await fetch(`/api/model?path=${encodeURIComponent(path)}`);
  const data = await response.json();
  if (!response.ok) {
    $("modelStatus").textContent = `✕ ${data.error}`;
    return;
  }
  state.model = path;
  state.inspection = data;
  data.joints.filter((joint) => joint.type !== "fixed").forEach((joint) => {
    state.jointConfig[joint.name] ??= defaultJointConfig(joint);
    state.mapping[joint.name] ??= joint.name;
  });
  await renderInspection();
  renderJoints();
  renderMapping();
  scheduleSave();
}

async function renderInspection() {
  const model = state.inspection;
  if (!model) return;
  const structuralLinks = model.links.filter((link) => link.role !== "auxiliary");
  const collisionLinks = structuralLinks.filter((link) => link.collision_count > 0).length;
  $("modelStatus").textContent = `✓ ${model.name} · ${model.format.toUpperCase()} 解析完成`;
  $("modelCounts").textContent = `${model.summary.links} / ${model.summary.joints}`;
  $("collisionStatus").textContent = `${collisionLinks} / ${structuralLinks.length}`;
  $("warningCount").textContent = `${model.summary.warnings} 项`;
  const modelNotes = model.notes || [];
  $("warnings").textContent = model.warnings.length
    ? model.warnings.join("\n")
    : (modelNotes.length
      ? `未发现结构性问题。以下为可选几何提示（不阻断训练）：\n${modelNotes.join("\n")}`
      : "未发现结构性问题；官方模型中的转子、传感器和装饰 link 允许缺少惯量或碰撞体。");
  const geometryCount = model.links.reduce((sum, link) => sum + (link.geometry || []).length, 0);
  const geometryInfo = $("geometryInfo");
  if (geometryInfo) geometryInfo.textContent = `几何体：${geometryCount} 个 visual/collision；mesh 可用 ${model.links.flatMap((link) => link.geometry || []).filter((item) => item.mesh).length} 个`;
  const children = new Map();
  model.joints.forEach((joint) => {
    if (!children.has(joint.parent)) children.set(joint.parent, []);
    children.get(joint.parent).push(joint);
  });
  const childNames = new Set(model.joints.map((joint) => joint.child));
  const roots = model.links.map((link) => link.name).filter((name) => !childNames.has(name));
  const node = (link, incomingJoint = null, depth = 0, seen = new Set()) => {
    if (seen.has(link) || depth > 30) return "";
    const nextSeen = new Set(seen); nextSeen.add(link);
    const descendants = children.get(link) || [];
    return `<li class="robot-tree-item">
      ${incomingJoint ? `<div class="robot-tree-edge"><span>${escapeHtml(incomingJoint.name)}</span><small>${escapeHtml(incomingJoint.type)}</small></div>` : ""}
      <details ${depth < 3 ? "open" : ""} class="robot-tree-branch">
        <summary><i></i><button type="button" data-tree-link="${escapeHtml(link)}">${escapeHtml(link)}</button><em>${descendants.length}</em></summary>
        ${descendants.length ? `<ul>${descendants.map((joint) => node(joint.child, joint, depth + 1, nextSeen)).join("")}</ul>` : ""}
      </details>
    </li>`;
  };
  $("structure").innerHTML = `<ul class="robot-tree">${roots.map((root) => node(root)).join("") || model.links.map((link) => node(link.name)).join("")}</ul>`;
  $("robotName").textContent = state.name;
  renderOverlays();
  await renderRobotViewport();
}

async function renderRobotViewport() {
  const viewport = document.querySelector(".viewport");
  if (!viewport || !state.model) return;
  const modelAtStart = state.model;
  const revision = ++state.previewRevision;
  if (!window.RoboThreeViewer) {
    await new Promise((resolve) => window.addEventListener("robolab-viewer-ready", resolve, { once: true }));
  }
  try {
    state.viewer ||= new window.RoboThreeViewer(viewport);
    state.viewer.setFov($("cameraFov")?.value || 48);
    const cssGrid = viewport.querySelector(".grid"); if (cssGrid) cssGrid.style.display = "none";
    window.robolabInspectionLinks = state.inspection.links;
    const loaded = await state.viewer.load(modelAtStart);
    // A model/task can change while the URDF request is in flight.  Do not let
    // an older request put its pose back after a newer one has been selected.
    if (!loaded || revision !== state.previewRevision || modelAtStart !== state.model) return;
    applyPreviewPose();
    state.viewer.setUp($("upAxis")?.value || "+Z");
    const svg = viewport.querySelector(".robot"); if (svg) svg.style.display = "none";
    const fallback = $("meshCanvas"); if (fallback) fallback.style.display = "none";
    const assetNote = state.trainingModel && state.trainingModel !== state.model ? ` · 预览 ${state.model.split(".").at(-1).toUpperCase()} / 训练 ${state.trainingModel.split(".").at(-1).toUpperCase()}` : "";
    $("modelStatus").textContent = `✓ ${state.inspection.name} · 3D 已加载 · ${loaded.links.length} links · 可动轴 ${loaded.axes} · 惯量 ${loaded.inertia}${assetNote}`;
  } catch (error) {
    console.error(error);
    $("modelStatus").textContent = `⚠ 3D 加载失败：${error.message}`;
    renderModelMeshes();
  }
}

async function renderModelMeshes() {
  const viewport = document.querySelector(".viewport");
  if (!viewport || !state.inspection) return;
  let canvas = document.getElementById("meshCanvas");
  if (!canvas) { canvas = document.createElement("canvas"); canvas.id = "meshCanvas"; canvas.style = "position:absolute;inset:0;width:100%;height:100%;pointer-events:none"; viewport.prepend(canvas); }
  const rect = viewport.getBoundingClientRect(); canvas.width = Math.max(1, Math.floor(rect.width * devicePixelRatio)); canvas.height = Math.max(1, Math.floor(rect.height * devicePixelRatio));
  const ctx = canvas.getContext("2d"); ctx.clearRect(0, 0, canvas.width, canvas.height);
  const vec = (text, fallback = [0, 0, 0]) => { const value = String(text || "").trim().split(/\s+/).map(Number); return value.length === 3 && value.every(Number.isFinite) ? value : fallback; };
  const pose = (xyz, rpy) => { const [r, p, y] = vec(rpy), cr = Math.cos(r), sr = Math.sin(r), cp = Math.cos(p), sp = Math.sin(p), cy = Math.cos(y), sy = Math.sin(y); return { R: [[cy*cp,cy*sp*sr-sy*cr,cy*sp*cr+sy*sr],[sy*cp,sy*sp*sr+cy*cr,sy*sp*cr-cy*sr],[-sp,cp*sr,cp*cr]], t: vec(xyz) }; };
  const mulV = (R, v) => R.map((row) => row[0]*v[0]+row[1]*v[1]+row[2]*v[2]);
  const compose = (a, b) => ({ R: a.R.map((row) => [0,1,2].map((j) => row[0]*b.R[0][j]+row[1]*b.R[1][j]+row[2]*b.R[2][j])), t: mulV(a.R,b.t).map((x,i)=>x+a.t[i]) });
  const identity = pose("0 0 0", "0 0 0"), world = {};
  const pending = [...state.inspection.joints]; let progress = true;
  state.inspection.links.forEach((link) => { if (!pending.some((joint) => joint.child === link.name)) world[link.name] = identity; });
  while (pending.length && progress) { progress = false; for (let i=pending.length-1;i>=0;i--) { const joint=pending[i]; if (world[joint.parent]) { world[joint.child]=compose(world[joint.parent],pose(joint.xyz,joint.rpy)); pending.splice(i,1); progress=true; } } }
  const instances = state.inspection.links.flatMap((link) => (link.geometry || []).filter((item) => item.kind === "visual" && item.resolved_mesh && item.resolved_mesh.toLowerCase().endsWith(".stl")).map((item) => ({ link: link.name, item })));
  const paths = [...new Set(instances.map((instance) => instance.item.resolved_mesh))].slice(0, 32);
  const fetched = await Promise.all(paths.map(async (path) => [path, await fetch(`/api/mesh?path=${encodeURIComponent(path)}`).then((response) => response.ok ? response.json() : null).catch(() => null)])); const meshMap = new Map(fetched);
  const points = instances.flatMap(({link,item}) => { const mesh=meshMap.get(item.resolved_mesh); if (!mesh) return []; const transform=compose(world[link]||identity,pose(item.xyz,item.rpy)), s=vec(item.scale,[1,1,1]); return mesh.vertices.map((point) => { const scaled=point.map((x,i)=>x*s[i]); const rotated=mulV(transform.R,scaled); return { point: rotated.map((x,i)=>x+transform.t[i]), mesh }; }); });
  if (!points.length) { const svg = document.querySelector(".viewport .robot"); if (svg) svg.style.display = "block"; return; }
  const all = points.map((item) => item.point); const min = [0, 1, 2].map((i) => Math.min(...all.map((p) => p[i]))); const max = [0, 1, 2].map((i) => Math.max(...all.map((p) => p[i]))); const span = Math.max(max[0] - min[0], max[2] - min[2], 0.001); const scale = Math.min(canvas.width, canvas.height) * 0.72 / span;
  ctx.fillStyle = "#8ab4e8"; ctx.globalAlpha = 0.28; for (const item of points) { const x = canvas.width / 2 + (item.point[0] - (min[0] + max[0]) / 2) * scale; const y = canvas.height * .52 - (item.point[2] - (min[2] + max[2]) / 2) * scale; ctx.fillRect(x, y, Math.max(1, scale * .008), Math.max(1, scale * .008)); }
  const svg = document.querySelector(".viewport .robot"); if (svg) svg.style.display = "none";
}

function renderOverlays() {
  const viewport = document.querySelector(".viewport");
  if (!viewport) return;
  let layer = document.getElementById("modelOverlays");
  if (!layer) { layer = document.createElement("div"); layer.id = "modelOverlays"; layer.style = "position:absolute;inset:0;pointer-events:none"; viewport.append(layer); }
  const links = state.inspection?.links || [];
  const collision = document.querySelector('[data-toggle="collision"]')?.checked;
  const axis = document.querySelector('[data-toggle="axis"]')?.checked;
  const inertia = document.querySelector('[data-toggle="inertia"]')?.checked;
  state.viewer?.setVisibility("visual", document.querySelector('[data-toggle="visual"]')?.checked ?? true);
  state.viewer?.setVisibility("collision", collision);
  state.viewer?.setVisibility("axis", axis);
  state.viewer?.setVisibility("inertia", inertia);
  layer.innerHTML = state.viewer ? "" : `${collision ? `<div style="position:absolute;left:28%;top:41%;width:44%;height:22%;border:2px dashed #ff9f43;border-radius:10px;color:#ffb547;padding:5px">collision</div>` : ""}${axis ? `<div style="position:absolute;left:49%;top:40%;height:28%;border-left:2px solid #42a5ff;box-shadow:8px 0 #42a5ff,-8px 0 #42a5ff"></div>` : ""}`;
}

function actuatedJoints() {
  return (state.inspection?.joints || []).filter((joint) => joint.type !== "fixed");
}

function renderJoints() {
  const joints = actuatedJoints();
  $("joints").innerHTML = joints.map((joint) => {
    const config = state.jointConfig[joint.name] || defaultJointConfig(joint);
    return `<div class="joint" data-joint-row="${escapeHtml(joint.name)}">
      <strong title="${escapeHtml(joint.name)}">${escapeHtml(joint.name)}</strong>
      <span class="value">${config.default.toFixed(2)} rad</span>
      <div class="row"><label>站立角</label><input data-field="default" type="range" class="slider" min="${joint.lower ?? -3.14}" max="${joint.upper ?? 3.14}" step="0.01" value="${config.default}"></div>
      <div class="row"><label>软限位</label><input data-field="soft_lower" type="number" step="0.01" value="${config.soft_lower}"><input data-field="soft_upper" type="number" step="0.01" value="${config.soft_upper}"></div>
      <div class="row"><label>KP / KD</label><input data-field="kp" type="number" value="${config.kp}"><input data-field="kd" type="number" value="${config.kd}"></div>
      <div class="row"><label>峰值扭矩</label><input data-field="peak_torque" type="number" value="${config.peak_torque}"><span>Nm</span></div>
      <div class="row"><label>高效转速</label><input data-field="efficient_rpm_min" type="number" value="${config.efficient_rpm_min}"><input data-field="efficient_rpm_max" type="number" value="${config.efficient_rpm_max}"></div>
    </div>`;
  }).join("") || "当前模型没有可控关节";
}

function renderMapping() {
  const joints = actuatedJoints();
  const options = joints.map((joint) => `<option value="${escapeHtml(joint.name)}">${escapeHtml(joint.name)}</option>`).join("");
  $("mappingList").innerHTML = joints.map((joint, index) => `<div class="joint" data-map-row="${escapeHtml(joint.name)}">
    <strong>${index}. ${escapeHtml(joint.name)}</strong>
    <div class="row"><label>模型关节</label><select data-map>${options}</select></div>
    <div class="row"><label>方向 / 零偏</label><select data-direction><option value="1">+1</option><option value="-1">-1</option></select><input data-offset type="number" step="0.01" value="0"></div>
  </div>`).join("") || "当前模型没有可映射关节";
  $$('[data-map-row]').forEach((row) => {
    const semantic = row.dataset.mapRow;
    row.querySelector("[data-map]").value = state.mapping[semantic] || semantic;
    const config = state.jointConfig[semantic];
    row.querySelector("[data-direction]").value = String(config?.direction ?? 1);
    row.querySelector("[data-offset]").value = config?.zero_offset ?? 0;
  });
}

function normalizeJoint(name) {
  return name.toLowerCase().replace(/joint|motor|_/g, "").replace(/front/g, "f").replace(/rear/g, "r").replace(/left/g, "l").replace(/right/g, "r");
}

function autoMap() {
  const joints = actuatedJoints();
  for (const semantic of joints) {
    const exact = joints.find((candidate) => normalizeJoint(candidate.name) === normalizeJoint(semantic.name));
    state.mapping[semantic.name] = exact?.name || semantic.name;
  }
  renderMapping();
  scheduleSave();
}

function recipe() {
  const trainingJoints = Object.fromEntries(Object.entries(state.jointConfig).map(([name, value]) => [name, {
    default: value.default,
    kp: value.kp,
    kd: value.kd,
    action_scale: value.action_scale,
  }]));
  return {
    schema_version: 1,
    name: state.name,
    robot: state.name,
    model: state.trainingModel || state.model,
    preview_model: state.model,
    robot_profile: state.derivedProfile,
    model_summary: state.inspection?.summary,
    framework: $("framework").value,
    task: $("task").value,
    method: $("method").value,
    num_envs: Number($("envs").value),
    iterations: Number($("iterations").value),
    checkpoint_interval: Number($("checkpointInterval")?.value || 300),
    use_standing_pose: Boolean($("useStandingPose")?.checked),
    seed: Number($("seed").value),
    run_dir: $("runDir").value,
    checkpoint: $("checkpoint")?.value || "",
    resume_from: $("resumeFrom")?.value || "",
    control_group: $("controlGroup").value,
    mapping: state.mapping,
    joints: trainingJoints,
    asset_authoring: { joints: state.jointConfig },
    control: {
      kp: Number($("kp").value), kd: Number($("kd").value),
      action_scale: Number($("scale").value), decimation: Number($("decimation").value),
      target_height: Number($("height").value),
    },
  };
}

async function save() {
  $("saveState").textContent = "● 保存中…";
  const response = await post("/api/project", recipe());
  $("saveState").textContent = response.ok ? "● 已自动保存" : "● 保存失败";
}

function scheduleSave() {
  clearTimeout(state.saveTimer);
  $("saveState").textContent = "● 有未保存修改";
  state.saveTimer = setTimeout(save, 500);
}

async function startTrain() {
  await save();
  const check = await post("/api/compatibility", recipe()).then((response) => response.json());
  renderCompatibility(check);
  if (!check.ok) { alert("兼容性检查未通过，请先修复问题。"); return; }
  const result = await post("/api/train", recipe()).then((response) => response.json());
  if (!result.ok) { alert(result.error || "训练启动失败"); return; }
  state.runId = result.run_id;
  state.activeRunDir = result.run_dir || null;
  $("log").textContent = `训练已进入队列\nrun_id: ${result.run_id}\n日志: ${result.log}`;
  $("runStatus").textContent = "● queued";
  setPage("runs");
  pollRun();
}

function renderCompatibility(result) {
  const box = $("compatibility");
  if (!box) return;
  const details = [...(result.warnings || []), ...(result.model_warnings || [])];
  box.textContent = result.ok
    ? `✓ 兼容性通过 · ${result.actuated_joints} 个可控关节 · 警告 ${details.length} 项\n${details.length ? details.map((item, index) => `${index + 1}. ${item}`).join("\n") : "未发现模型警告"}`
    : `✕ ${result.issues.join("；")}\n${details.join("\n")}`;
  box.style.color = result.ok ? "#80e4ab" : "#ff8f8f";
}

function renderRunPaths(checkpoint = "") {
  if (!$("runPaths")) return;
  const fullCheckpoint = checkpoint || $("checkpoint")?.value || "";
  const shortCheckpoint = fullCheckpoint.split(/[\\/]/).filter(Boolean).at(-1) || "本次运行尚未生成";
  const toolHost = window.location.hostname || "127.0.0.1";
  const paths = $("runPaths");
  paths.textContent = `Run：${state.activeRunDir || $("runDir").value}\nCheckpoint：${shortCheckpoint}\nTensorBoard：http://${toolHost}:6006/?darkMode=true#timeseries\nViser：http://${toolHost}:8080`;
  paths.title = fullCheckpoint ? `当前 checkpoint：${fullCheckpoint}` : "当前训练尚未生成 checkpoint";
}

function renderProgress(result) {
  const box = $("trainingProgress");
  if (!box) return;
  const current = Number(result.current_iteration || 0);
  const total = Number(result.max_iterations || $("iterations")?.value || 0);
  const percent = total ? Math.min(100, Math.max(0, current / total * 100)) : 0;
  const rewards = result.reward_history || [];
  const latest = result.reward_latest;
  const recent = result.reward_mean_recent;
  const low = rewards.length ? Math.min(...rewards) : 0;
  const high = rewards.length ? Math.max(...rewards) : 1;
  const span = Math.max(high - low, 1e-9);
  const points = rewards.map((value, index) => `${rewards.length === 1 ? 0 : index / (rewards.length - 1) * 280},${58 - (value - low) / span * 52}`).join(" ");
  box.innerHTML = `<div style="display:flex;justify-content:space-between;margin-bottom:6px"><span>训练进度</span><strong>${current} / ${total || "?"}</strong></div><div style="height:10px;background:#17191d;border-radius:6px;overflow:hidden"><div style="height:100%;width:${percent}%;background:#1685ff;transition:width .3s"></div></div><div style="margin-top:7px;color:#9ca3af">${rewards.length ? `Mean reward：${Number(latest).toFixed(3)} · 近10轮均值：${Number(recent).toFixed(3)} · 样本 ${rewards.length}` : "等待首个 reward"}</div>${rewards.length > 1 ? `<svg viewBox="0 0 280 64" style="display:block;width:100%;height:64px;margin-top:7px;background:#15171a;border-radius:5px"><polyline fill="none" stroke="#32c77a" stroke-width="2" points="${points}"/></svg>` : ""}`;
}

async function pollRun() {
  if (!state.runId) return;
  const result = await post("/api/run/status", { run_id: state.runId }).then((response) => response.json());
  if (result.run_dir) state.activeRunDir = result.run_dir;
  $("runStatus").textContent = `● ${result.status}`;
  const latest = state.activeRunDir ? await fetch(`/api/run/latest?run_dir=${encodeURIComponent(state.activeRunDir)}`).then((response) => response.json()).catch(() => ({})) : {};
  if (result.checkpoint && $("checkpoint")) $("checkpoint").value = result.checkpoint;
  renderRunPaths(result.checkpoint || latest.checkpoint);
  renderProgress(result);
  $("log").textContent = result.log || "等待进程输出…";
  $("log").scrollTop = $("log").scrollHeight;
  if (["queued", "running", "stopping"].includes(result.status)) setTimeout(pollRun, 1500);
}

async function uploadModel(file) {
  let content = await file.text();
  if (file.name.toLowerCase().endsWith(".zip")) {
    content = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(file); });
  }
  const result = await post("/api/upload", { filename: file.name, content }).then((response) => response.json());
  if (!result.ok) { alert(result.error); return; }
  state.name = file.name.replace(/\.(urdf|xml)$/i, "");
  state.trainingModel = result.path;
  state.jointConfig = {};
  state.mapping = {};
  await inspectModel(result.path);
}

function bindEvents() {
  $$(".pill[data-page]").forEach((button) => button.addEventListener("click", () => setPage(button.dataset.page)));
  document.addEventListener("click", async (event) => {
    const treeLink = event.target.closest("[data-tree-link]");
    if (treeLink) { state.viewer?.focusLink(treeLink.dataset.treeLink); return; }
    const robot = event.target.closest("[data-robot]");
    if (!robot) return;
    $$('[data-robot]').forEach((item) => item.classList.remove("selected"));
    robot.classList.add("selected");
    state.name = robot.dataset.robot;
    state.trainingModel = robot.dataset.model;
    state.jointConfig = {};
    state.mapping = {};
    await inspectModel(robot.dataset.model);
    renderTaskOptions();
    await syncSelectedTaskModel();
  });
  $("joints").addEventListener("input", (event) => {
    const row = event.target.closest("[data-joint-row]");
    if (!row || !event.target.dataset.field) return;
    state.jointConfig[row.dataset.jointRow][event.target.dataset.field] = Number(event.target.value);
    if (event.target.dataset.field === "default") row.querySelector(".value").textContent = `${Number(event.target.value).toFixed(2)} rad`;
    if (event.target.dataset.field === "default" && state.useStandingPose) state.viewer?.setJoint(row.dataset.jointRow, Number(event.target.value));
    scheduleSave();
  });
  $("mappingList").addEventListener("input", (event) => {
    const row = event.target.closest("[data-map-row]");
    if (!row) return;
    const semantic = row.dataset.mapRow;
    if (event.target.matches("[data-map]")) state.mapping[semantic] = event.target.value;
    if (event.target.matches("[data-direction]")) state.jointConfig[semantic].direction = Number(event.target.value);
    if (event.target.matches("[data-offset]")) state.jointConfig[semantic].zero_offset = Number(event.target.value);
    scheduleSave();
  });
  $("useStandingPose")?.addEventListener("change", (event) => {
    state.useStandingPose = Boolean(event.target.checked);
    applyPreviewPose();
    scheduleSave();
  });
  $$('[data-toggle]').forEach((input) => input.addEventListener("change", renderOverlays));
  ["kp", "kd", "scale", "decimation", "height", "framework", "task", "method", "envs", "iterations", "checkpointInterval", "seed", "runDir", "controlGroup", "resumeFrom"].forEach((id) => $(id)?.addEventListener("change", scheduleSave));
  $("applyAllBtn").onclick = () => { actuatedJoints().forEach((joint) => Object.assign(state.jointConfig[joint.name], { kp: Number($("kp").value), kd: Number($("kd").value), action_scale: Number($("scale").value) })); renderJoints(); scheduleSave(); };
  $("autoMapBtn").onclick = autoMap;
  $("saveBtn").onclick = save;
  $("newBtn").onclick = () => { state.name = `robot_${new Date().toISOString().slice(0, 10)}`; $("robotName").textContent = state.name; scheduleSave(); };
  $("uploadBtn").onclick = () => $("fileInput").click();
  $("fileInput").onchange = (event) => event.target.files[0] && uploadModel(event.target.files[0]);
  $("deriveBtn").onclick = async () => { const result = await post("/api/derive", recipe()).then((response) => response.json()); if (result.ok) { state.derivedProfile = `${result.directory}/robot-profile.json`; scheduleSave(); alert(`已生成：${result.directory}`); } else alert(result.error); };
  $("trainBtn").onclick = startTrain;
  if (!$("stopTrainBtn")) { const button = document.createElement("button"); button.id = "stopTrainBtn"; button.className = "btn"; button.textContent = "■ 停止训练"; button.style.background = "#9b3a3a"; $("trainBtn").after(button); }
  if (!$("stopRunBtn")) { const button = document.createElement("button"); button.id = "stopRunBtn"; button.className = "btn"; button.textContent = "■ 停止训练"; button.style.background = "#9b3a3a"; $("viserBtn").after(button); }
  const stopTraining = async () => {
    if (!state.runId) { alert("当前没有可停止的训练任务"); return; }
    const result = await post("/api/run/stop", { run_id: state.runId }).then((response) => response.json());
    if (!result.ok) alert(result.error || "停止训练失败");
    else { $("runStatus").textContent = `● ${result.status}`; $("log").textContent += "\n已请求停止训练，正在等待进程退出…"; }
  };
  $("stopTrainBtn").onclick = stopTraining;
  $("stopRunBtn").onclick = stopTraining;
}

async function init() {
  $$('[data-toggle]').forEach((toggle) => { toggle.checked = toggle.dataset.toggle === "visual"; });
  const inertiaToggle = document.querySelector('[data-toggle="inertia"]');
  if (inertiaToggle && inertiaToggle.parentElement.lastChild) inertiaToggle.parentElement.lastChild.nodeValue = "惯量盒";
  const treeStyle = document.createElement("style"); treeStyle.textContent = `.robot-tree,.robot-tree ul{list-style:none;margin:0;padding-left:0}.robot-tree ul{position:relative;margin-left:12px;padding-left:18px;border-left:1px solid #49515d}.robot-tree-item{position:relative;margin:4px 0}.robot-tree ul>.robot-tree-item:before{content:"";position:absolute;left:-18px;top:16px;width:15px;border-top:1px solid #49515d}.robot-tree-branch summary{display:flex;align-items:center;gap:7px;min-height:28px;cursor:pointer;list-style:none}.robot-tree-branch summary::-webkit-details-marker{display:none}.robot-tree-branch summary>i{width:8px;height:8px;border-radius:50%;background:#1685ff;box-shadow:0 0 0 3px #1685ff22}.robot-tree-branch summary:before{content:"▸";color:#7d8794;font-size:10px}.robot-tree-branch[open]>summary:before{transform:rotate(90deg)}.robot-tree-branch summary button{border:0;background:transparent;color:#dce4ee;padding:3px 5px;cursor:pointer;text-align:left}.robot-tree-branch summary button:hover{color:#65b3ff;background:#1685ff18;border-radius:4px}.robot-tree-branch summary em{margin-left:auto;color:#687382;font-style:normal;font-size:10px}.robot-tree-edge{display:flex;align-items:center;gap:6px;color:#69aff4;font-size:11px;margin-left:13px;height:19px}.robot-tree-edge:before{content:"◆";font-size:6px;color:#ffb547}.robot-tree-edge small{color:#697380;font-size:9px;border:1px solid #404752;border-radius:7px;padding:0 4px}`; document.head.append(treeStyle);
  const [robots, methods, taskSpecs] = await Promise.all([
    fetch("/api/robots").then((response) => response.json()),
    fetch("/api/methods").then((response) => response.json()),
    fetch("/api/tasks").then((response) => response.json()).catch(() => []),
  ]);
  state.methods = methods;
  state.taskSpecs = taskSpecs;
  // Task is a registry selection, never a free-form string.  Keep the
  // existing markup compatible with cached pages by upgrading the input.
  const taskInput = $("task");
  if (taskInput && taskInput.tagName !== "SELECT") {
    const taskSelect = document.createElement("select");
    taskSelect.id = "task";
    taskInput.replaceWith(taskSelect);
  }
  $("robotTree").innerHTML = robots.map((robot, index) => {
    const model = robot.models[0] || "";
    return `<div class="${index === 0 ? "selected" : ""}" data-robot="${escapeHtml(robot.id)}" data-model="${escapeHtml(model)}">▾ <b>${escapeHtml(robot.name)}</b><br><span style="padding-left:19px;color:#8e97a5">└ ${escapeHtml(model || "未找到模型")}</span></div>`;
  }).join("");
  $("method").innerHTML = methods.map((method) => `<option value="${escapeHtml(method.method_id)}">${escapeHtml(method.display_name || method.method_id)}</option>`).join("");
  // Legacy pages used $("method").value = "cts"; task selection is now
  // registry-driven and defaults to the portable PPO method.
  if (methods.some((method) => method.method_id === "ppo")) $("method").value = "ppo";
  renderTaskOptions();
  // Keep the page markup compact while still exposing status affordances in older cached HTML.
  if (!$("checkBtn")) { const button = document.createElement("button"); button.id = "checkBtn"; button.className = "btn"; button.textContent = "兼容性检查"; $("trainBtn").parentElement.prepend(button); }
  if (!$("compatibility")) { const box = document.createElement("div"); box.id = "compatibility"; box.className = "log"; box.textContent = "训练前会检查模型、关节映射、backend 与算法契约。"; $("trainBtn").parentElement.parentElement.append(box); }
  if (!$("geometryInfo")) { const info = document.createElement("div"); info.id = "geometryInfo"; info.style = "margin-top:8px;color:#9ca3af"; info.textContent = "几何体：—"; $("modelStatus").after(info); }
  if (!$("checkpoint")) { const row = document.createElement("div"); row.className = "row"; row.innerHTML = '<label>Checkpoint</label><input id="checkpoint" placeholder="logs/.../model_1500.pt">'; $("runDir").closest(".row").after(row); }
  if (!$("resumeFrom")) { const row = document.createElement("div"); row.className = "row"; row.innerHTML = '<label>显式 Resume</label><input id="resumeFrom" placeholder="仅填写时续训">'; $("checkpoint").closest(".row").after(row); }
  if (!$("checkpointInterval")) { const row = document.createElement("div"); row.className = "row"; row.innerHTML = '<label>每隔多少轮保存</label><input id="checkpointInterval" type="number" value="300" min="1">'; $("iterations").closest(".row").after(row); }
  if (!$("useStandingPose")) { const row = document.createElement("div"); row.className = "row"; row.innerHTML = '<label>使用站立角覆盖</label><input id="useStandingPose" type="checkbox"><span style="color:#9ca3af">默认关闭，仅当前机器人/Task</span>'; $("height").closest(".row").after(row); }
  if (!$("seedHelp")) { const help = document.createElement("div"); help.id = "seedHelp"; help.style = "color:#9ca3af;margin:-4px 0 8px 113px"; help.textContent = "随机数种子：相同配置与 Seed 用于复现实验；可用 0、1、2… 做多次独立训练。"; $("seed").closest(".row").after(help); }
  if (!$("resetPoseBtn")) { const button = document.createElement("button"); button.id = "resetPoseBtn"; button.className = "btn"; button.textContent = "恢复 Task 默认站立角"; $("applyAllBtn").after(button); button.onclick = async () => { await syncSelectedTaskModel(); renderJoints(); }; }
  if (!$("trainingProgress")) { const box = document.createElement("div"); box.id = "trainingProgress"; box.className = "log"; box.style.marginTop = "10px"; box.textContent = "训练尚未启动"; $("runPaths").after(box); }
  if (!$("upAxis")) { const select = document.createElement("select"); select.id = "upAxis"; select.style.maxWidth = "82px"; select.innerHTML = '<option>+Z</option><option>+Y</option><option>+X</option><option>-Z</option><option>-Y</option><option>-X</option>'; $("task").after(select); }
  const savedFov = Number(localStorage.getItem("robolab-camera-fov"));
  if ($("cameraFov") && savedFov >= 15 && savedFov <= 100) $("cameraFov").value = String(savedFov);
  if ($("cameraFovValue")) $("cameraFovValue").textContent = `${$("cameraFov").value}°`;
  $("fileInput").accept = ".urdf,.xml,.zip";
  bindEvents();
  $("framework").addEventListener("change", async () => { renderTaskOptions(); await syncSelectedTaskModel(); });
  $("method").addEventListener("change", async () => { renderTaskOptions(); await syncSelectedTaskModel(); });
  $("task").addEventListener("change", syncSelectedTaskModel);
  $("upAxis").addEventListener("change", () => state.viewer?.setUp($("upAxis").value));
  $("cameraFov")?.addEventListener("input", () => {
    const fov = state.viewer?.setFov($("cameraFov").value) ?? Number($("cameraFov").value);
    $("cameraFovValue").textContent = `${fov}°`;
    localStorage.setItem("robolab-camera-fov", String(fov));
  });
  $("checkBtn").onclick = async () => renderCompatibility(await post("/api/compatibility", recipe()).then((response) => response.json()));
  $("tensorboardBtn").onclick = async () => { const popup = window.open("about:blank", "_blank"); const result = await post("/api/tool/start", { tool: "tensorboard", framework: $("framework").value, run_dir: state.activeRunDir || $("runDir").value }).then((response) => response.json()); if (result.error) { popup?.close(); alert(result.error); } else { renderRunPaths(); const url = new URL(result.url || "http://127.0.0.1:6006/?darkMode=true#timeseries"); url.hostname = window.location.hostname || "127.0.0.1"; if (popup) popup.location = url.toString(); } };
  $("viserBtn").onclick = async () => { const popup = window.open("about:blank", "_blank"); const result = await post("/api/tool/start", { tool: "viser", ...recipe(), run_dir: state.activeRunDir || $("runDir").value }).then((response) => response.json()); if (result.error) { popup?.close(); alert(result.error); } else { if (result.checkpoint && $("checkpoint")) $("checkpoint").value = result.checkpoint; renderRunPaths(result.checkpoint); const url = new URL(result.url || "http://127.0.0.1:8080"); url.hostname = window.location.hostname || "127.0.0.1"; if (popup) popup.location = url.toString(); } };
  const initial = robots.find((robot) => robot.id === "unitree_a1") || robots[0];
  if (initial?.models[0]) {
    state.name = initial.id;
    await inspectModel(initial.models[0]);
    await syncSelectedTaskModel();
  }
  // A shared base directory can contain checkpoints from unrelated historical
  // runs. Do not present one as belonging to the current session.
  renderRunPaths($("resumeFrom")?.value || "");
}

init();
