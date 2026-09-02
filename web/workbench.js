const API = window.location.origin;
const $ = (id) => document.getElementById(id);
let presets = [], selectedPreset = null, rewardDefaults = {}, taskId = null;
let simulationSessionId = null, activeSimulationMap = null, simulationMaps = [], simulationTrail = [], simMode = 'basic';
let pollTimer = null, rewardHistory = [];

async function jsonFetch(path, options = {}) {
  const response = await fetch(`${API}${path}`, options);
  let payload = {};
  try { payload = await response.json(); } catch {}
  if (!response.ok) throw new Error(payload.detail || payload.error?.message || `HTTP ${response.status}`);
  return payload;
}
function setView(name) {
  document.querySelectorAll('.view').forEach((view) => view.classList.toggle('active-view', view.id === name));
  document.querySelectorAll('.nav-item').forEach((item) => item.classList.toggle('active', item.dataset.step === name));
  history.replaceState(null, '', `#${name}`);
  if (name === 'simulation') requestAnimationFrame(() => drawSimulationMap(simulationTrail.at(-1) || [0, 0, 0]));
}
function setBadge(element, text, state = 'pending') { if (!element) return; element.textContent = text; element.className = `badge ${state}`; }
function setStatus(element, text, state = 'pending') { if (!element) return; element.innerHTML = `<i></i>${text}`; element.className = `status-dot ${state}`; }
function applyPreset(preset) {
  selectedPreset = preset;
  $('modelPath').value = preset.asset_path || '';
  $('format').value = /\.(xml|mjcf)$/i.test(preset.asset_path || '') ? 'mjcf' : 'urdf';
  $('contractJson').value = JSON.stringify(preset.contract, null, 2);
  $('presetMeta').innerHTML = `<strong>${preset.family}</strong><br>${preset.dof} DOF / ${Number(preset.mass_kg).toFixed(1)} kg / ${preset.locomotion_type === 'W' ? '轮足' : '点足'}<br><span>${preset.contract_path}</span>`;
  $('stageRobotName').textContent = preset.family || preset.robot_id;
  $('configRobot').textContent = preset.family || preset.robot_id;
  $('configContract').textContent = preset.contract?.contract_id || 'Contract loaded';
  setBadge($('modelBadge'), '待验证');
}
async function loadPresets() {
  const payload = await jsonFetch('/api/robots/presets');
  presets = payload.presets || [];
  $('preset').innerHTML = presets.map((item) => `<option value="${item.robot_id}">${item.family} · ${item.robot_id}</option>`).join('') || '<option value="">暂无 preset</option>';
  if ($('simRobot')) $('simRobot').innerHTML = presets.map((item) => `<option value="${item.robot_id}">${item.family}</option>`).join('') || '<option value="">暂无机器人包</option>';
  if (presets[0]) applyPreset(presets[0]);
}
function renderRewards() {
  const entries = Object.entries(rewardDefaults);
  $('rewards').innerHTML = entries.length ? entries.map(([id, term]) => `<label class="reward"><input type="checkbox" data-reward="${id}" checked><span><b>${term.label || id}</b><small>${term.description || ''}</small></span><input type="number" data-weight="${id}" value="${term.default ?? 0}" step="0.0001"></label>`).join('') : '<div class="empty-state">后端未返回奖惩项</div>';
}
async function loadTrainingOptions() {
  const payload = await jsonFetch('/api/training/options');
  $('algorithm').innerHTML = (payload.algorithms || []).map((item) => `<option value="${item.id}" ${item.available ? '' : 'disabled'}>${item.label}${item.available ? '' : '（未接入）'}</option>`).join('') || '<option value="PPO">PPO</option>';
  rewardDefaults = payload.reward_terms || {};
  const hardware = payload.hardware || {};
  const torch = hardware.torch || {};
  const devices = ['auto', ...(torch.cuda_available ? ['cuda', ...(torch.devices || []).map((item) => `cuda:${item.index}`)] : []), 'cpu'];
  $('device').innerHTML = devices.map((value) => `<option value="${value}">${value === 'auto' ? '自动' : value.toUpperCase()}</option>`).join('');
  $('hardwareHint').textContent = torch.cuda_available ? `GPU 可用：${(torch.devices || []).map((item) => item.name || `CUDA:${item.index}`).join(', ') || 'CUDA runtime ready'}` : `GPU 不可用，将使用 CPU：${torch.error || 'runtime unavailable'}`;
  $('configDeviceSummary').textContent = torch.cuda_available ? 'CUDA 可用' : 'CPU';
  $('runtimeDetails').textContent = JSON.stringify({ native_mjlab: hardware.native_mjlab, torch: hardware.torch }, null, 2);
  renderRewards();
}
async function loadCapabilities() {
  try {
    const [cap, status] = await Promise.all([jsonFetch('/api/system/capabilities'), jsonFetch('/api/adapters/status')]);
    setStatus($('backendState'), '后端在线', 'ok');
    const adapters = cap.adapters || {};
    $('homeCapabilities').innerHTML = [['控制面', true, '在线'], ['MJLab 训练', adapters.native_mjlab, adapters.native_mjlab ? '可用' : '待配置'], ['MuJoCo 仿真', adapters.mujoco_simulation, adapters.mujoco_simulation ? '可用' : '缺少依赖'], ['CUDA', status.native_mjlab?.runtime?.interpreters?.some((item) => item.cuda_available), status.native_mjlab?.runtime?.interpreters?.some((item) => item.cuda_available) ? '已检测' : '未检测']].map(([label, ok, value]) => `<div class="system-row"><span>${label}</span><strong class="${ok ? 'ok' : 'warn'}">${value}</strong></div>`).join('');
  } catch (error) { setStatus($('backendState'), '后端离线', 'error'); $('homeCapabilities').innerHTML = `<div class="empty-state">${error.message}</div>`; }
}
async function loadRuns() {
  try { const payload = await jsonFetch('/api/training/list'); const tasks = payload.tasks || []; $('homeRuns').innerHTML = tasks.length ? tasks.slice(0, 8).map((item) => `<div class="run-row"><div><strong>${item.robot || '-'}</strong><small>${item.task_id}</small></div><span class="run-metric">${item.algorithm || 'PPO'}</span><span class="run-metric">${item.status}</span><span class="run-metric">${(Number(item.progress || 0) * 100).toFixed(1)}%</span></div>`).join('') : '<div class="empty-state">暂无训练任务，去训练配置创建第一条任务。</div>'; } catch (error) { $('homeRuns').innerHTML = `<div class="empty-state">任务读取失败：${error.message}</div>`; }
}
async function validateModel() {
  try {
    const contract = JSON.parse($('contractJson').value);
    $('validationLog').textContent = '正在校验 schema、关节映射与控制频率...';
    const [model, contractResult] = await Promise.all([
      jsonFetch('/api/models/validate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: $('modelPath').value.trim(), format: $('format').value, contract }) }),
      jsonFetch('/api/contracts/validate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(contract) }),
    ]);
    const valid = model.valid !== false && contractResult.valid !== false;
    setBadge($('modelBadge'), valid ? '验证通过' : '存在问题', valid ? 'ok' : 'error');
    $('stageStatus').textContent = valid ? '模型与 Contract 已通过检查' : '模型检查存在问题';
    $('viewerFormat').textContent = $('format').value.toUpperCase();
    $('validationLog').textContent = valid ? `✓ 验证通过\n格式：${$('format').value.toUpperCase()}\n机器人：${contract.robot_id || '-'}\n关节：${contractResult.actuated_joints || '-'}\n执行器：${model.stats?.actuators ?? '-'}\nMuJoCo：${model.mujoco_loadable === true ? '可加载' : '结构检查完成'}` : JSON.stringify({ model, contract: contractResult }, null, 2);
    return valid;
  } catch (error) { setBadge($('modelBadge'), '验证失败', 'error'); $('validationLog').textContent = `✕ ${error.message}`; return false; }
}
function trainingPayload() {
  const contract = JSON.parse($('contractJson').value); const reward_scales = {};
  document.querySelectorAll('[data-reward]').forEach((input) => { reward_scales[input.dataset.reward] = input.checked ? Number(document.querySelector(`[data-weight="${input.dataset.reward}"]`)?.value || 0) : 0; });
  return { contract, backend: 'native_mjlab', algorithm: $('algorithm').value, num_envs: Number($('numEnvs').value), max_iterations: Number($('maxIterations').value), learning_rate: Number($('learningRate').value), save_interval: Number($('saveInterval').value), task_name: $('taskName').value || 'forward_walk', terrain_type: $('terrain').value, device: $('device').value, reward_scales, gamma: Number($('gamma').value), gae_lambda: Number($('gaeLambda').value), num_steps: Number($('numSteps').value), num_minibatches: Number($('numMinibatches').value), alpha: Number($('alpha').value), seed: Number($('seed').value) };
}
async function startTraining() {
  if (!(await validateModel())) { setView('validate'); return; }
  try { const payload = await jsonFetch('/api/training/create', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(trainingPayload()) }); taskId = payload.task_id; setBadge($('configBadge'), '任务已创建', 'ok'); setView('training'); pollStatus(); } catch (error) { setBadge($('configBadge'), '创建失败', 'error'); alert(`训练任务创建失败\n${error.message}`); }
}
function drawChart() {
  const canvas = $('rewardChart'); if (!canvas) return; const rect = canvas.getBoundingClientRect(); const ratio = Math.max(1, devicePixelRatio || 1); const width = Math.max(320, Math.round(rect.width)); const height = Math.max(220, Math.round(rect.height)); canvas.width = width * ratio; canvas.height = height * ratio; const ctx = canvas.getContext('2d'); ctx.setTransform(ratio, 0, 0, ratio, 0, 0); ctx.clearRect(0, 0, width, height); ctx.strokeStyle = '#263541'; ctx.lineWidth = 1; for (let i = 1; i < 5; i += 1) { const y = (height / 5) * i; ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke(); } if (!rewardHistory.length) return; const values = rewardHistory.map((item) => Number(item) || 0); const min = Math.min(...values), max = Math.max(...values, min + 1); ctx.strokeStyle = '#37d6c6'; ctx.lineWidth = 2; ctx.beginPath(); values.forEach((value, index) => { const x = 14 + (index / Math.max(1, values.length - 1)) * (width - 28); const y = height - 14 - ((value - min) / (max - min)) * (height - 28); index ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }); ctx.stroke(); $('chartEmpty').style.display = 'none';
}
async function pollStatus() {
  if (!taskId) return; let terminal = false;
  try { const payload = await jsonFetch(`/api/training/${taskId}/status`); const status = payload.status || payload; const progress = Math.max(0, Math.min(1, Number(status.progress || 0))); $('trainingTaskLabel').textContent = `${status.robot || selectedPreset?.family || '-'} · ${taskId}`; $('trainingTaskMeta').textContent = `${status.algorithm || 'PPO'} · ${status.device || 'native worker'}`; $('runProgress').style.width = `${progress * 100}%`; $('runPercent').textContent = `${(progress * 100).toFixed(1)}%`; $('runStage').textContent = `${status.status || 'unknown'} · ${status.current_iteration || 0}/${status.max_iterations || '-'}`; $('metricIteration').textContent = status.current_iteration ?? '-'; $('metricReward').textContent = Number(status.reward || 0).toFixed(3); $('metricSuccess').textContent = `${(Number(status.success_rate || 0) * 100).toFixed(1)}%`; $('metricDevice').textContent = status.device || '-'; setBadge($('runBadge'), status.status === 'running' ? '训练中' : status.status === 'completed' ? '训练完成' : status.status || '未知', status.status === 'completed' ? 'ok' : status.status === 'running' ? 'warn' : status.status === 'failed' ? 'error' : 'pending'); if (status.reward !== undefined) { rewardHistory.push(Number(status.reward)); if (rewardHistory.length > 120) rewardHistory.shift(); drawChart(); } const logs = await jsonFetch(`/api/training/${taskId}/logs?lines=120`); $('runLog').textContent = (logs.logs || []).join('\n') || '暂无日志'; terminal = ['completed', 'failed', 'stopped'].includes(status.status); $('stopTraining').disabled = terminal; $('runNavigation').disabled = !['completed'].includes(status.status); $('runEvaluation').disabled = !['completed'].includes(status.status); } catch (error) { $('runLog').textContent = `状态读取失败：${error.message}`; } clearTimeout(pollTimer); if (!terminal) pollTimer = setTimeout(pollStatus, 2500);
}
async function stopTraining() { if (!taskId) return; try { await jsonFetch(`/api/training/${taskId}/stop`, { method: 'POST' }); pollStatus(); } catch (error) { alert(`停止失败\n${error.message}`); } }
async function loadSimulationMaps() { try { const payload = await jsonFetch('/api/simulation/maps'); simulationMaps = payload.maps || []; $('simMap').innerHTML = simulationMaps.map((item) => `<option value="${item.id}">${item.label}</option>`).join(''); $('navigationMap').innerHTML = simulationMaps.filter((item) => item.mode === 'navigation').map((item) => `<option value="${item.id}">${item.label}</option>`).join(''); } catch (error) { $('simFrame').textContent = `地图加载失败：${error.message}`; } }
function renderSimulationFrame(frame) { const position = Array.isArray(frame.position) ? frame.position : [0, 0, 0]; simulationTrail.push([Number(position[0] || 0), Number(position[1] || 0)]); if (simulationTrail.length > 500) simulationTrail.shift(); $('simPoseLabel').textContent = `x ${Number(position[0] || 0).toFixed(2)} · y ${Number(position[1] || 0).toFixed(2)} · step ${frame.step || 0}`; $('simClock').textContent = `t ${Number(frame.time || 0).toFixed(2)}`; $('simFrameStatus').textContent = `reward ${Number(frame.reward || 0).toFixed(4)} · ${frame.done ? 'done' : 'running'}`; $('simFrame').textContent = JSON.stringify(frame, null, 2); drawSimulationMap(position); }
function drawSimulationMap(position = [0, 0, 0]) { const canvas = $('simCanvas'); if (!canvas) return; const rect = canvas.getBoundingClientRect(); const ratio = Math.max(1, devicePixelRatio || 1); const width = Math.max(320, Math.round(rect.width || 800)); const height = Math.max(300, Math.round(rect.height || 600)); if (canvas.width !== width * ratio || canvas.height !== height * ratio) { canvas.width = width * ratio; canvas.height = height * ratio; } const ctx = canvas.getContext('2d'); ctx.setTransform(ratio, 0, 0, ratio, 0, 0); ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, width, height); const [xmin, xmax, ymin, ymax] = activeSimulationMap?.bounds || [-5, 5, -5, 5]; const pad = 35; const project = ([x, y]) => [pad + ((x - xmin) / (xmax - xmin)) * (width - pad * 2), height - pad - ((y - ymin) / (ymax - ymin)) * (height - pad * 2)]; ctx.strokeStyle = 'rgba(113,133,151,.18)'; for (let x = Math.ceil(xmin); x <= xmax; x += 1) { const [px] = project([x, 0]); ctx.beginPath(); ctx.moveTo(px, pad); ctx.lineTo(px, height - pad); ctx.stroke(); } for (let y = Math.ceil(ymin); y <= ymax; y += 1) { const [, py] = project([0, y]); ctx.beginPath(); ctx.moveTo(pad, py); ctx.lineTo(width - pad, py); ctx.stroke(); } ctx.fillStyle = 'rgba(104,123,140,.42)'; (activeSimulationMap?.obstacles || []).forEach(([x, y, w, h]) => { const [a, b] = project([x - w / 2, y + h / 2]); const [c, d] = project([x + w / 2, y - h / 2]); ctx.fillRect(a, b, c - a, d - b); }); if (simulationTrail.length > 1) { ctx.strokeStyle = '#2588df'; ctx.lineWidth = 2; ctx.beginPath(); simulationTrail.forEach((point, index) => { const [x, y] = project(point); index ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }); ctx.stroke(); } const [rx, ry] = project(position); ctx.fillStyle = '#2478c5'; ctx.beginPath(); ctx.arc(rx, ry, 7, 0, Math.PI * 2); ctx.fill(); }
function updateCommandLabels() { ['Vx', 'Vy', 'Wz'].forEach((name) => { const value = Number($(`sim${name}`).value || 0); $(`sim${name}Value`).textContent = value.toFixed(2); }); }
async function startSimulation() { try { const robot = $('simRobot').value; const map = $('simMap').value || 'flat'; const payload = await jsonFetch('/api/simulation/sessions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ robot_id: robot, map_id: map, mode: 'basic' }) }); simulationSessionId = payload.session_id; activeSimulationMap = payload.map; simulationTrail = []; $('simMapLabel').textContent = payload.map?.label || map; setStatus($('engineStatus'), '引擎运行中', 'ok'); setBadge($('simModeBadge'), '运行中', 'ok'); $('resetSimulation').disabled = false; $('closeSimulation').disabled = false; $('simStep').disabled = false; $('simStopCommand').disabled = false; renderSimulationFrame(payload.frame); refreshSimulationRender(); } catch (error) { setStatus($('engineStatus'), '启动失败', 'error'); $('simFrame').textContent = `仿真启动失败：${error.message}`; } }
async function stepSimulation() { if (!simulationSessionId) return; try { const payload = await jsonFetch(`/api/simulation/sessions/${simulationSessionId}/step`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ command: { vx: Number($('simVx').value), vy: Number($('simVy').value), wz: Number($('simWz').value) } }) }); renderSimulationFrame(payload.frame); refreshSimulationRender(); } catch (error) { $('simFrame').textContent = `仿真步进失败：${error.message}`; } }
async function refreshSimulationRender() { if (!simulationSessionId) return; try { const payload = await jsonFetch(`/api/simulation/sessions/${simulationSessionId}/render?width=960&height=640`); const image = $('simRender'); if (image && payload.image_base64) image.src = `data:image/png;base64,${payload.image_base64}`; } catch {} }
async function resetSimulation() { if (simulationSessionId) renderSimulationFrame((await jsonFetch(`/api/simulation/sessions/${simulationSessionId}/reset`, { method: 'POST' })).frame); }
async function closeSimulation() { if (!simulationSessionId) return; await jsonFetch(`/api/simulation/sessions/${simulationSessionId}`, { method: 'DELETE' }); simulationSessionId = null; activeSimulationMap = null; simulationTrail = []; $('resetSimulation').disabled = true; $('simStep').disabled = true; $('simStopCommand').disabled = true; setStatus($('engineStatus'), '等待引擎'); setBadge($('simModeBadge'), '未运行'); $('simMapLabel').textContent = '未启动场景'; drawSimulationMap(); }
async function runEvaluation() { if (!taskId) return; $('evalResult').textContent = '评估运行中...'; try { const payload = await jsonFetch('/api/evaluation/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ task_id: taskId, episodes: Number($('episodes').value) }) }); $('evalResult').textContent = JSON.stringify(payload.result, null, 2); } catch (error) { $('evalResult').textContent = `评估失败：${error.message}`; } }
async function runNavigation() { if (!taskId) return; let waypoints; try { waypoints = JSON.parse($('waypoints').value); } catch (error) { $('evalResult').textContent = `路线 JSON 无效：${error.message}`; return; } $('evalResult').textContent = '导航任务运行中...'; try { const payload = await jsonFetch('/api/navigation/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ task_id: taskId, episodes: 1, waypoints, map_id: $('navigationMap').value, control_mode: 'auto' }) }); $('evalResult').textContent = JSON.stringify(payload.result, null, 2); } catch (error) { $('evalResult').textContent = `导航失败：${error.message}`; } }
function bindEvents() {
  document.querySelectorAll('[data-step]').forEach((item) => item.addEventListener('click', () => setView(item.dataset.step)));
  document.querySelectorAll('[data-config-tab]').forEach((tab) => tab.addEventListener('click', () => { document.querySelectorAll('.config-tab').forEach((x) => x.classList.toggle('active', x === tab)); document.querySelectorAll('[data-config-pane]').forEach((pane) => pane.classList.toggle('active-pane', pane.dataset.configPane === tab.dataset.configTab)); }));
  document.querySelectorAll('[data-sim-mode]').forEach((button) => button.addEventListener('click', () => { simMode = button.dataset.simMode; document.querySelectorAll('[data-sim-mode]').forEach((x) => x.classList.toggle('active', x === button)); $('basicControls').classList.toggle('hidden', simMode !== 'basic'); $('navigationControls').classList.toggle('hidden', simMode !== 'navigation'); }));
  $('preset').addEventListener('change', (event) => applyPreset(presets.find((item) => item.robot_id === event.target.value)));
  $('validateBtn').addEventListener('click', validateModel); $('startTraining').addEventListener('click', startTraining); $('stopTraining').addEventListener('click', stopTraining); $('resetRewards').addEventListener('click', renderRewards); $('startSimulation').addEventListener('click', startSimulation); $('simStep').addEventListener('click', stepSimulation); $('resetSimulation').addEventListener('click', resetSimulation); $('closeSimulation').addEventListener('click', closeSimulation); $('simStopCommand').addEventListener('click', () => { ['simVx', 'simVy', 'simWz'].forEach((id) => { $(id).value = 0; }); updateCommandLabels(); }); $('runEvaluation').addEventListener('click', runEvaluation); $('runNavigation').addEventListener('click', runNavigation); $('clearLog').addEventListener('click', () => { $('runLog').textContent = ''; }); $('homeRefresh').addEventListener('click', () => { loadCapabilities(); loadRuns(); }); $('refreshApp').addEventListener('click', () => { loadCapabilities(); loadRuns(); }); $('copyContract').addEventListener('click', async () => { await navigator.clipboard?.writeText($('contractJson').value); });
  ['simVx', 'simVy', 'simWz'].forEach((id) => $(id).addEventListener('input', updateCommandLabels));
  document.addEventListener('keydown', (event) => { if (!simulationSessionId || ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) return; const command = { vx: 0, vy: 0, wz: 0 }; if (event.key === 'ArrowUp') command.vx = .5; if (event.key === 'ArrowDown') command.vx = -.5; if (event.key === 'ArrowLeft') command.wz = .5; if (event.key === 'ArrowRight') command.wz = -.5; if (event.key.startsWith('Arrow')) { event.preventDefault(); $('simVx').value = command.vx; $('simVy').value = command.vy; $('simWz').value = command.wz; updateCommandLabels(); stepSimulation(); } });
  window.addEventListener('resize', () => { drawSimulationMap(simulationTrail.at(-1) || [0, 0, 0]); drawChart(); });
}
document.addEventListener('DOMContentLoaded', async () => { bindEvents(); updateCommandLabels(); const hash = window.location.hash.slice(1); if (['home', 'validate', 'config', 'training', 'simulation'].includes(hash)) setView(hash); try { await Promise.all([loadPresets(), loadTrainingOptions(), loadSimulationMaps(), loadCapabilities(), loadRuns()]); } catch (error) { $('validationLog').textContent = `初始化失败：${error.message}`; } });
