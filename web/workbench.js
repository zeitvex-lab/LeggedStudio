const API = window.location.origin;
const $ = (id) => document.getElementById(id);
let presets = [], selectedPreset = null, selectedModelContent = null;
let rewardDefaults = {}, rewardOverrides = false, taskId = null, pollTimer = null, rewardHistory = [];
let simulationSessionId = null, activeSimulationMap = null, simulationMaps = [], simulationTrail = [];
let urdfSceneState = null;
let importedAssetFiles = [];

async function jsonFetch(path, options = {}) {
  const response = await fetch(`${API}${path}`, options);
  let payload = {};
  try { payload = await response.json(); } catch {}
  if (!response.ok) throw new Error(payload.detail?.message || payload.detail || payload.error?.message || `HTTP ${response.status}`);
  return payload;
}
function setView(name) {
  document.querySelectorAll('.view').forEach((view) => view.classList.toggle('active-view', view.id === name));
  document.querySelectorAll('.nav-item').forEach((item) => item.classList.toggle('active', item.dataset.step === name));
  history.replaceState(null, '', `#${name}`);
  if (name === 'simulation') {
    const frame = $('simBrowserFrame');
    if (frame && !frame.src) frame.src = `/web/sim2sim/index.html?embedded=1&robot=${encodeURIComponent($('simRobot')?.value || 'unitree_go2')}`;
    requestAnimationFrame(() => drawSimulationMap(simulationTrail.at(-1) || [0, 0, 0]));
  }
}
function setBadge(element, text, state = 'pending') { if (element) { element.textContent = text; element.className = `badge ${state}`; } }
function setStatus(element, text, state = 'pending') { if (element) { element.innerHTML = `<i></i>${text}`; element.className = `status-dot ${state}`; } }
function resetValidationWorkspace() {
  const preset = $('preset');
  if (preset) {
    preset.hidden = true;
    preset.innerHTML = '<option value="">请选择本地资产文件夹</option>';
    preset.closest('.field-label')?.setAttribute('hidden', 'hidden');
  }
  if ($('modelPreviewEmpty')) $('modelPreviewEmpty').textContent = '请选择本地资产文件夹';
  if ($('stageStatus')) $('stageStatus').textContent = '等待本地 URDF/MJCF 资产';
  if ($('viewerFormat')) $('viewerFormat').textContent = '等待资产';
}
function applyPreset(preset) {
  if (!preset) return;
  selectedPreset = preset;
  $('modelPath').value = preset.asset_path || '';
  $('format').value = /\.(xml|mjcf)$/i.test(preset.asset_path || '') ? 'mjcf' : 'urdf';
  $('contractJson').value = JSON.stringify(preset.contract || {}, null, 2);
  $('presetMeta').innerHTML = `<strong>${preset.family || preset.robot_id}</strong><br>${preset.dof || 0} DOF / ${Number(preset.mass_kg || 0).toFixed(1)} kg<br><span>${preset.contract_path || ''}</span>`;
  if ($('stageRobotName')) $('stageRobotName').textContent = preset.family || preset.robot_id;
  $('configRobot').textContent = preset.family || preset.robot_id;
  $('configContract').textContent = preset.contract?.contract_id || 'Contract loaded';
  const profiles = preset.training_profiles || [];
  $('profile').innerHTML = '<option value="">Generic Contract task</option>' + profiles.map((item) => `<option value="${item.profile_id}">${item.display_name || item.profile_id}</option>`).join('');
  $('profile').value = profiles[0]?.profile_id || '';
  const profileTerrain = profiles[0]?.terrain_type || (profiles[0]?.terrain?.sub_terrains?.some((item) => item !== 'flat') ? 'rough' : null);
  if (profileTerrain && ['plane', 'rough'].includes(profileTerrain)) $('terrain').value = profileTerrain;
  selectedModelContent = null;
}
async function loadPresets() {
  const payload = await jsonFetch('/api/robots/presets');
  presets = payload.presets || [];
  if ($('preset')) $('preset').innerHTML = '<option value="">请选择本地资产文件夹</option>';
  if ($('simRobot')) $('simRobot').innerHTML = presets.map((item) => `<option value="${item.robot_id}">${item.family || item.robot_id}</option>`).join('');
}
function renderRewards() {
  const entries = Object.entries(rewardDefaults);
  $('rewards').innerHTML = entries.length ? entries.map(([id, term]) => `<label class="reward"><input type="checkbox" data-reward="${id}" checked><span><b>${term.label || id}</b><small>${term.description || ''}</small></span><input type="number" data-weight="${id}" value="${term.default ?? 0}" step="0.0001"></label>`).join('') : '<div class="empty-state">No reward terms returned by MJLab</div>';
}
async function loadTrainingOptions() {
  const payload = await jsonFetch('/api/training/options');
  $('algorithm').innerHTML = (payload.algorithms || []).map((item) => `<option value="${item.id}" ${item.available ? '' : 'disabled'}>${item.label || item.id}</option>`).join('');
  rewardDefaults = payload.reward_terms || {};
  const torch = payload.hardware?.torch || {};
  const devices = ['auto', ...(torch.cuda_available ? ['cuda', ...(torch.devices || []).map((item) => `cuda:${item.index}`)] : []), 'cpu'];
  $('device').innerHTML = devices.map((value) => `<option value="${value}">${value.toUpperCase()}</option>`).join('');
  $('hardwareHint').textContent = torch.cuda_available ? 'CUDA runtime available' : `CUDA unavailable: ${torch.error || 'CPU fallback'}`;
  $('configDeviceSummary').textContent = torch.cuda_available ? 'CUDA available' : 'CPU';
  $('runtimeDetails').textContent = JSON.stringify(payload.hardware || {}, null, 2);
  renderRewards();
}
async function loadCapabilities() {
  try {
    const [cap, status] = await Promise.all([jsonFetch('/api/system/capabilities'), jsonFetch('/api/adapters/status')]);
    setStatus($('backendState'), 'Control plane online', 'ok');
    const adapters = cap.adapters || {};
    const cuda = status.native_mjlab?.runtime?.interpreters?.some((item) => item.cuda_available);
    $('homeCapabilities').innerHTML = [['Control plane', true, 'online'], ['MJLab training', adapters.native_mjlab, adapters.native_mjlab ? 'ready' : 'configure runtime'], ['MuJoCo simulation', adapters.mujoco_simulation, adapters.mujoco_simulation ? 'ready' : 'missing dependency'], ['CUDA', cuda, cuda ? 'detected' : 'not detected']].map(([label, ok, value]) => `<div class="system-row"><span>${label}</span><strong class="${ok ? 'ok' : 'warn'}">${value}</strong></div>`).join('');
  } catch (error) { setStatus($('backendState'), 'Control plane offline', 'error'); $('homeCapabilities').innerHTML = `<div class="empty-state">${error.message}</div>`; }
}
async function loadRuns() {
  try { const payload = await jsonFetch('/api/training/list'); const tasks = payload.tasks || []; $('homeRuns').innerHTML = tasks.length ? tasks.slice(0, 8).map((item) => `<div class="run-row"><div><strong>${item.robot || '-'}</strong><small>${item.task_id}</small></div><span class="run-metric">${item.algorithm || 'PPO'}</span><span class="run-metric">${item.status}</span><span class="run-metric">${(Number(item.progress || 0) * 100).toFixed(1)}%</span></div>`).join('') : '<div class="empty-state">No training runs</div>'; } catch (error) { $('homeRuns').innerHTML = `<div class="empty-state">${error.message}</div>`; }
}
async function refreshModelPreview(source, format, valid) {
  const image = $('modelPreview'), urdf = $('urdfPreview'), empty = $('modelPreviewEmpty');
  const urdfCanvas = $('urdfCanvas');
  if (urdfCanvas) urdfCanvas.hidden = true;
  if (!valid) { image.hidden = true; urdf.hidden = true; empty.hidden = false; return; }
  if (String(format).toLowerCase() === 'urdf' && source?.content && typeof window.renderUrdfModel === 'function') {
    image.hidden = true; urdf.hidden = true; empty.hidden = true;
    try { await window.renderUrdfModel(source.content, importedAssetFiles); if ($('urdfCanvas')) $('urdfCanvas').hidden = false; return; }
    catch (error) { console.warn('Three.js URDF preview unavailable', error); }
  }
  try {
    const payload = await jsonFetch('/api/models/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...source, format }) });
    if (payload.image_base64) { image.src = `data:image/png;base64,${payload.image_base64}`; image.hidden = false; urdf.hidden = true; }
    else if (payload.svg) { urdf.innerHTML = payload.svg; urdf.hidden = false; image.hidden = true; }
    empty.hidden = true;
  } catch (error) { image.hidden = true; urdf.hidden = true; empty.textContent = `Preview failed: ${error.message}`; empty.hidden = false; }
}

async function importAssetFolder(files, model) {
  const entries = [];
  for (const file of files) {
    const path = file.webkitRelativePath || file.name;
    const bytes = new Uint8Array(await file.arrayBuffer());
    let binary = '';
    for (let index = 0; index < bytes.length; index += 0x8000) binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
    entries.push({ path, content: btoa(binary), encoding: 'base64' });
  }
  return jsonFetch('/api/models/import', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ files: entries, model_filename: model.webkitRelativePath || model.name, format: /\.urdf$/i.test(model.name) ? 'urdf' : 'mjcf' }) });
}
async function validateModel() {
  try {
    const contract = JSON.parse($('contractJson').value);
    $('validationLog').textContent = 'Validating model XML, resources and contract...';
    const source = selectedModelContent ? { content: selectedModelContent, filename: $('modelFile').files?.[0]?.name || 'model.xml' } : { path: $('modelPath').value.trim() };
    const [model, contractResult] = await Promise.all([
      jsonFetch('/api/models/validate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...source, format: $('format').value, contract }) }),
      jsonFetch('/api/contracts/validate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(contract) }),
    ]);
    const valid = model.valid !== false && contractResult.valid !== false;
    setBadge($('modelBadge'), valid ? 'Validation passed' : 'Validation failed', valid ? 'ok' : 'error');
    $('stageStatus').textContent = valid ? 'Real model validated' : 'Model has validation errors';
    $('viewerFormat').textContent = (model.format || $('format').value).toUpperCase();
    $('validationLog').textContent = JSON.stringify({ model, contract: contractResult }, null, 2);
    await refreshModelPreview(source, model.format || $('format').value, valid);
    return valid;
  } catch (error) { setBadge($('modelBadge'), 'Validation error', 'error'); $('validationLog').textContent = error.message; return false; }
}
function trainingPayload() {
  const contract = JSON.parse($('contractJson').value), reward_scales = {};
  document.querySelectorAll('[data-reward]').forEach((input) => { reward_scales[input.dataset.reward] = input.checked ? Number(document.querySelector(`[data-weight="${input.dataset.reward}"]`)?.value || 0) : 0; });
  return { contract, backend: 'native_mjlab', algorithm: $('algorithm').value, num_envs: Number($('numEnvs').value), max_iterations: Number($('maxIterations').value), learning_rate: Number($('learningRate').value), save_interval: Number($('saveInterval').value), task_name: $('taskName').value || 'forward_walk', profile_id: $('profile').value || null, terrain_type: $('terrain').value, device: $('device').value, reward_scales, reward_overrides: rewardOverrides, gamma: Number($('gamma').value), gae_lambda: Number($('gaeLambda').value), num_steps: Number($('numSteps').value), num_minibatches: Number($('numMinibatches').value), alpha: Number($('alpha').value), seed: Number($('seed').value) };
}
async function startTraining() { if (!(await validateModel())) { setView('validate'); return; } try { const payload = await jsonFetch('/api/training/create', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(trainingPayload()) }); taskId = payload.task_id; setBadge($('configBadge'), 'Task created', 'ok'); setView('training'); pollStatus(); } catch (error) { setBadge($('configBadge'), 'Create failed', 'error'); alert(error.message); } }
function drawChart() { const canvas = $('rewardChart'); if (!canvas) return; const rect = canvas.getBoundingClientRect(), ratio = Math.max(1, devicePixelRatio || 1), width = Math.max(320, Math.round(rect.width)), height = Math.max(220, Math.round(rect.height)); canvas.width = width * ratio; canvas.height = height * ratio; const ctx = canvas.getContext('2d'); ctx.setTransform(ratio, 0, 0, ratio, 0, 0); ctx.clearRect(0, 0, width, height); if (!rewardHistory.length) return; const min = Math.min(...rewardHistory), max = Math.max(...rewardHistory, min + 1); ctx.strokeStyle = '#37d6c6'; ctx.lineWidth = 2; ctx.beginPath(); rewardHistory.forEach((value, index) => { const x = 14 + index / Math.max(1, rewardHistory.length - 1) * (width - 28), y = height - 14 - (value - min) / (max - min) * (height - 28); index ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }); ctx.stroke(); $('chartEmpty').style.display = 'none'; }
async function pollStatus() { if (!taskId) return; let terminal = false; try { const payload = await jsonFetch(`/api/training/${taskId}/status`), status = payload.status || payload, progress = Math.max(0, Math.min(1, Number(status.progress || 0))); $('trainingTaskLabel').textContent = `${status.robot || selectedPreset?.family || '-'} · ${taskId}`; $('trainingTaskMeta').textContent = `${status.algorithm || 'PPO'} · ${status.device || 'native worker'}`; $('runProgress').style.width = `${progress * 100}%`; $('runPercent').textContent = `${(progress * 100).toFixed(1)}%`; $('runStage').textContent = `${status.status || 'unknown'} · ${status.current_iteration || 0}/${status.max_iterations || '-'}`; $('metricIteration').textContent = status.current_iteration ?? '-'; $('metricReward').textContent = Number(status.reward || 0).toFixed(3); $('metricSuccess').textContent = `${(Number(status.success_rate || 0) * 100).toFixed(1)}%`; $('metricDevice').textContent = status.device || '-'; if (status.reward !== undefined) { rewardHistory.push(Number(status.reward)); if (rewardHistory.length > 120) rewardHistory.shift(); drawChart(); } const logs = await jsonFetch(`/api/training/${taskId}/logs?lines=120`); $('runLog').textContent = (logs.logs || []).join('\n') || 'No worker output'; terminal = ['completed', 'failed', 'stopped'].includes(status.status); $('stopTraining').disabled = terminal; $('runNavigation').disabled = !terminal || status.status !== 'completed'; $('runEvaluation').disabled = !terminal || status.status !== 'completed'; } catch (error) { $('runLog').textContent = error.message; } clearTimeout(pollTimer); if (!terminal) pollTimer = setTimeout(pollStatus, 2500); }
async function stopTraining() { if (taskId) { await jsonFetch(`/api/training/${taskId}/stop`, { method: 'POST' }); pollStatus(); } }
async function loadSimulationMaps() { try { const payload = await jsonFetch('/api/simulation/maps'); simulationMaps = payload.maps || []; $('simMap').innerHTML = simulationMaps.map((item) => `<option value="${item.id}">${item.label}</option>`).join(''); $('navigationMap').innerHTML = simulationMaps.filter((item) => item.mode === 'navigation').map((item) => `<option value="${item.id}">${item.label}</option>`).join(''); } catch (error) { $('simFrame').textContent = error.message; } }
function renderSimulationFrame(frame) { const position = Array.isArray(frame.position) ? frame.position : [0, 0, 0]; simulationTrail.push([Number(position[0] || 0), Number(position[1] || 0)]); if (simulationTrail.length > 500) simulationTrail.shift(); $('simPoseLabel').textContent = `x ${Number(position[0] || 0).toFixed(2)} · y ${Number(position[1] || 0).toFixed(2)} · step ${frame.step || 0}`; $('simClock').textContent = `t ${Number(frame.time || 0).toFixed(2)}`; $('simFrameStatus').textContent = `reward ${Number(frame.reward || 0).toFixed(4)} · ${frame.done ? 'done' : 'running'}`; $('simFrame').textContent = JSON.stringify(frame, null, 2); drawSimulationMap(position); }
function drawSimulationMap(position = [0, 0, 0]) { const canvas = $('simCanvas'); if (!canvas) return; const rect = canvas.getBoundingClientRect(), ratio = Math.max(1, devicePixelRatio || 1), width = Math.max(320, Math.round(rect.width || 800)), height = Math.max(300, Math.round(rect.height || 600)); canvas.width = width * ratio; canvas.height = height * ratio; const ctx = canvas.getContext('2d'); ctx.setTransform(ratio, 0, 0, ratio, 0, 0); ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, width, height); const [xmin, xmax, ymin, ymax] = activeSimulationMap?.bounds || [-5, 5, -5, 5], pad = 35, project = ([x, y]) => [pad + (x - xmin) / (xmax - xmin) * (width - pad * 2), height - pad - (y - ymin) / (ymax - ymin) * (height - pad * 2)]; ctx.strokeStyle = 'rgba(113,133,151,.18)'; for (let x = Math.ceil(xmin); x <= xmax; x += 1) { const [px] = project([x, 0]); ctx.beginPath(); ctx.moveTo(px, pad); ctx.lineTo(px, height - pad); ctx.stroke(); } for (let y = Math.ceil(ymin); y <= ymax; y += 1) { const [, py] = project([0, y]); ctx.beginPath(); ctx.moveTo(pad, py); ctx.lineTo(width - pad, py); ctx.stroke(); } ctx.fillStyle = 'rgba(104,123,140,.42)'; (activeSimulationMap?.obstacles || []).forEach(([x, y, w, h]) => { const [a, b] = project([x - w / 2, y + h / 2]), [c, d] = project([x + w / 2, y - h / 2]); ctx.fillRect(a, b, c - a, d - b); }); if (simulationTrail.length > 1) { ctx.strokeStyle = '#2588df'; ctx.lineWidth = 2; ctx.beginPath(); simulationTrail.forEach((point, index) => { const [x, y] = project(point); index ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }); ctx.stroke(); } const [rx, ry] = project(position); ctx.fillStyle = '#2478c5'; ctx.beginPath(); ctx.arc(rx, ry, 7, 0, Math.PI * 2); ctx.fill(); }
async function refreshSimulationRender() { if (!simulationSessionId) return; try { const payload = await jsonFetch(`/api/simulation/sessions/${simulationSessionId}/render?width=960&height=640`); if ($('simRender') && payload.image_base64) { $('simRender').src = `data:image/png;base64,${payload.image_base64}`; $('simRender').hidden = false; } } catch (error) { $('simFrame').textContent = `Render failed: ${error.message}`; } }
async function startSimulation() {
  setView('simulation');
}
async function stepSimulation() { if (!simulationSessionId) return; try { const payload = await jsonFetch(`/api/simulation/sessions/${simulationSessionId}/step`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ command: { vx: Number($('simVx').value), vy: Number($('simVy').value), wz: Number($('simWz').value) } }) }); renderSimulationFrame(payload.frame); refreshSimulationRender(); } catch (error) { $('simFrame').textContent = error.message; } }
async function resetSimulation() { if (simulationSessionId) { const payload = await jsonFetch(`/api/simulation/sessions/${simulationSessionId}/reset`, { method: 'POST' }); renderSimulationFrame(payload.frame); refreshSimulationRender(); } }
async function closeSimulation() { if (!simulationSessionId) return; await jsonFetch(`/api/simulation/sessions/${simulationSessionId}`, { method: 'DELETE' }); simulationSessionId = null; activeSimulationMap = null; simulationTrail = []; $('simRender').hidden = true; $('resetSimulation').disabled = true; $('simStep').disabled = true; $('simStopCommand').disabled = true; setStatus($('engineStatus'), 'Waiting for engine'); setBadge($('simModeBadge'), 'Stopped'); drawSimulationMap(); }
async function runEvaluation() { if (!taskId) return; $('evalResult').textContent = 'Running evaluation...'; try { const payload = await jsonFetch('/api/evaluation/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ task_id: taskId, episodes: Number($('episodes').value) }) }); $('evalResult').textContent = JSON.stringify(payload.result, null, 2); } catch (error) { $('evalResult').textContent = error.message; } }
async function runNavigation() { if (!taskId) return; try { const waypoints = JSON.parse($('waypoints').value); const payload = await jsonFetch('/api/navigation/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ task_id: taskId, episodes: 1, waypoints, map_id: $('navigationMap').value, control_mode: $('navigationMode').value }) }); $('evalResult').textContent = JSON.stringify(payload.result, null, 2); } catch (error) { $('evalResult').textContent = error.message; } }
function bindEvents() {
  document.querySelectorAll('[data-step]').forEach((item) => item.addEventListener('click', () => setView(item.dataset.step)));
  document.querySelectorAll('[data-config-tab]').forEach((tab) => tab.addEventListener('click', () => { document.querySelectorAll('.config-tab').forEach((x) => x.classList.toggle('active', x === tab)); document.querySelectorAll('[data-config-pane]').forEach((pane) => pane.classList.toggle('active-pane', pane.dataset.configPane === tab.dataset.configTab)); }));
  document.querySelectorAll('[data-sim-mode]').forEach((button) => button.addEventListener('click', () => { document.querySelectorAll('[data-sim-mode]').forEach((x) => x.classList.toggle('active', x === button)); $('basicControls').classList.toggle('hidden', button.dataset.simMode !== 'basic'); $('navigationControls').classList.toggle('hidden', button.dataset.simMode !== 'navigation'); }));
  $('preset').addEventListener('change', (event) => applyPreset(presets.find((item) => item.robot_id === event.target.value)));
  $('modelFile').addEventListener('change', async (event) => {
    const files = Array.from(event.target.files || []);
    const model = files.find((file) => /\.(urdf|mjcf|xml)$/i.test(file.name));
    if (!model) { $('modelFileName').textContent = '文件夹中未找到 URDF/MJCF/XML 模型'; return; }
    $('modelFileName').textContent = `${files.length} 个资产 · ${model.name}`;
    try {
      const imported = await importAssetFolder(files, model);
      selectedModelContent = await model.text();
      importedAssetFiles = files.slice();
      $('modelPath').value = imported.model_path || '';
      $('format').value = imported.format || (/\.urdf$/i.test(model.name) ? 'urdf' : 'mjcf');
      if (imported.contract_draft) $('contractJson').value = JSON.stringify(imported.contract_draft, null, 2);
      await validateModel();
    } catch (error) { $('validationLog').textContent = `资产导入失败: ${error.message}`; }
  });
  $('profile').addEventListener('change', (event) => { const profile = selectedPreset?.training_profiles?.find((item) => item.profile_id === event.target.value); const terrain = profile?.terrain_type || (profile?.terrain?.sub_terrains?.some((item) => item !== 'flat') ? 'rough' : null); if (terrain && ['plane', 'rough'].includes(terrain)) $('terrain').value = terrain; });
  $('validateBtn').addEventListener('click', validateModel); $('startTraining').addEventListener('click', startTraining); $('stopTraining').addEventListener('click', stopTraining); $('resetRewards').addEventListener('click', renderRewards); $('startSimulation').addEventListener('click', startSimulation); $('simStep').addEventListener('click', stepSimulation); $('resetSimulation').addEventListener('click', resetSimulation); $('closeSimulation').addEventListener('click', closeSimulation); $('simStopCommand').addEventListener('click', () => ['simVx', 'simVy', 'simWz'].forEach((id) => { $(id).value = 0; })); $('runEvaluation').addEventListener('click', runEvaluation); $('runNavigation').addEventListener('click', runNavigation); $('clearLog').addEventListener('click', () => { $('runLog').textContent = ''; }); $('homeRefresh').addEventListener('click', () => { loadCapabilities(); loadRuns(); }); $('refreshApp').addEventListener('click', () => { loadCapabilities(); loadRuns(); }); $('copyContract').addEventListener('click', async () => navigator.clipboard?.writeText($('contractJson').value));
  ['simVx', 'simVy', 'simWz'].forEach((id) => $(id).addEventListener('input', () => { const name = id.slice(3); $(`${id}Value`).textContent = Number($(id).value).toFixed(2); }));
  window.addEventListener('resize', () => { drawSimulationMap(simulationTrail.at(-1) || [0, 0, 0]); drawChart(); });
}
document.addEventListener('DOMContentLoaded', async () => { const stage = document.querySelector('.sim-stage'); if (stage && $('simRender')?.parentElement !== stage) stage.prepend($('simRender')); resetValidationWorkspace(); bindEvents(); const hash = window.location.hash.slice(1); if (['home', 'validate', 'config', 'training', 'simulation'].includes(hash)) setView(hash); try { await Promise.all([loadPresets(), loadTrainingOptions(), loadSimulationMaps(), loadCapabilities(), loadRuns()]); resetValidationWorkspace(); } catch (error) { if ($('validationLog')) $('validationLog').textContent = `Initialization failed: ${error.message}`; } });
