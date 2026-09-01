const API = 'http://127.0.0.1:8765';
const $ = (id) => document.getElementById(id);
let presets = [];
let selectedPreset = null;
let rewardDefaults = {};
let taskId = null;
let pollTimer = null;

function setStep(name) {
  document.querySelectorAll('.step-panel').forEach((panel) => panel.classList.toggle('active-panel', panel.id === name));
  document.querySelectorAll('.step').forEach((step) => step.classList.toggle('active', step.dataset.step === name));
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function pill(element, text, state = 'pending') {
  element.textContent = text;
  element.className = `pill ${state}`;
}

async function jsonFetch(path, options = {}) {
  const response = await fetch(`${API}${path}`, options);
  let payload = {};
  try { payload = await response.json(); } catch { /* preserve HTTP error */ }
  if (!response.ok) throw new Error(payload.detail || payload.error?.message || `HTTP ${response.status}`);
  return payload;
}

function applyPreset(preset) {
  selectedPreset = preset;
  $('modelPath').value = preset.asset_path || '';
  $('contractJson').value = JSON.stringify(preset.contract, null, 2);
  $('presetMeta').innerHTML = `<strong>${preset.family}</strong><br>${preset.dof} DOF / ${Number(preset.mass_kg).toFixed(1)} kg / ${preset.locomotion_type === 'W' ? '轮足' : '点足'}<br><span>${preset.contract_path}</span>`;
  pill($('modelBadge'), '待验证', 'pending');
}

async function loadPresets() {
  const payload = await jsonFetch('/api/robots/presets');
  presets = payload.presets || [];
  $('preset').innerHTML = presets.map((item) => `<option value="${item.robot_id}">${item.family} · ${item.robot_id}</option>`).join('') || '<option value="">暂无 preset</option>';
  if (presets[0]) applyPreset(presets[0]);
}

async function loadTrainingOptions() {
  const payload = await jsonFetch('/api/training/options');
  $('algorithm').innerHTML = (payload.algorithms || []).map((item) => `<option value="${item.id}" ${item.available ? '' : 'disabled'}>${item.label}${item.available ? '' : '（未接入）'}</option>`).join('');
  rewardDefaults = payload.reward_terms || {};
  renderRewards();
}

function renderRewards() {
  const entries = Object.entries(rewardDefaults);
  $('rewards').innerHTML = entries.length ? entries.map(([id, term]) => `<label class="reward"><input type="checkbox" data-reward="${id}" checked><span><b>${term.label}</b><small>${term.description || ''}</small></span><input type="number" data-weight="${id}" value="${term.default ?? 0}" step="0.0001"></label>`).join('') : '<div class="muted">后端未返回奖惩项</div>';
}

async function validateModel() {
  const log = $('validationLog');
  try {
    const contract = JSON.parse($('contractJson').value);
    log.textContent = '正在校验 schema、关节映射与控制频率...';
    let payload;
    try {
      payload = await jsonFetch('/api/contracts/validate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(contract) });
    } catch (error) {
      // Complete API versions before contract endpoint can still validate via pipeline.
      const contractPath = selectedPreset?.contract_path || $('modelPath').value;
      payload = await jsonFetch('/api/pipeline/validate-contract', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ contract_path: contractPath.startsWith('/') || /^[A-Za-z]:[\\/]/.test(contractPath) ? contractPath : `../${contractPath}` }) });
    }
    const valid = payload.valid !== false;
    pill($('modelBadge'), valid ? '验证通过' : '存在问题', valid ? 'ok' : 'error');
    log.textContent = valid ? `✓ Contract 有效\n格式: ${$('format').value.toUpperCase()}\n机器人: ${payload.robot_id || contract.robot_id || selectedPreset?.robot_id || '-'}\n关节: ${payload.actuated_joints || contract.actuated_joint_names?.length || '-'}\n控制频率: ${payload.control_hz || contract.control_hz || '-'} Hz` : JSON.stringify(payload, null, 2);
    if (valid) $('configBadge').textContent = '已就绪';
  } catch (error) {
    pill($('modelBadge'), '验证失败', 'error');
    log.textContent = `✕ ${error.message}`;
  }
}

function trainingPayload() {
  const contract = JSON.parse($('contractJson').value);
  const reward_scales = {};
  document.querySelectorAll('[data-reward]').forEach((input) => {
    const id = input.dataset.reward;
    const weight = Number(document.querySelector(`[data-weight="${id}"]`)?.value || 0);
    reward_scales[id] = input.checked ? weight : 0;
  });
  return { contract, algorithm: $('algorithm').value, num_envs: Number($('numEnvs').value), max_iterations: Number($('maxIterations').value), learning_rate: Number($('learningRate').value), save_interval: 100, episode_length_s: 20, task_name: $('taskName').value || 'forward_walk', terrain_type: $('terrain').value, device: $('device').value, reward_scales };
}

async function startTraining() {
  try {
    const payload = await jsonFetch('/api/training/create', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(trainingPayload()) });
    taskId = payload.task_id;
    pill($('configBadge'), '任务已创建', 'ok');
    $('metricTask').textContent = taskId;
    $('stopTraining').disabled = false;
    $('runEvaluation').disabled = true;
    setStep('simulation');
    pollStatus();
  } catch (error) {
    pill($('configBadge'), '创建失败', 'error');
    alert(`训练任务创建失败\n${error.message}`);
  }
}

async function pollStatus() {
  if (!taskId) return;
  try {
    const payload = await jsonFetch(`/api/training/${taskId}/status`);
    const status = payload.status || payload;
    const progress = Math.max(0, Math.min(1, Number(status.progress || 0)));
    $('runProgress').style.width = `${progress * 100}%`;
    $('runPercent').textContent = `${(progress * 100).toFixed(1)}%`;
    $('runStage').textContent = `${status.status || 'unknown'} · ${status.current_iteration || 0}/${status.max_iterations || '-'}`;
    $('metricIteration').textContent = status.current_iteration ?? '-';
    $('metricReward').textContent = Number(status.reward || 0).toFixed(2);
    $('metricSuccess').textContent = `${(Number(status.success_rate || 0) * 100).toFixed(1)}%`;
    pill($('runBadge'), status.status === 'running' ? '训练中' : status.status === 'completed' ? '训练完成' : status.status, status.status === 'completed' ? 'ok' : status.status === 'running' ? 'warn' : 'pending');
    if (status.status === 'completed') { $('stopTraining').disabled = true; $('runEvaluation').disabled = false; $('enterNavigation').disabled = false; pill($('evalBadge'), '可评估', 'ok'); }
    const logs = await jsonFetch(`/api/training/${taskId}/logs?lines=80`);
    $('runLog').textContent = (logs.logs || []).join('\n') || '暂无日志';
  } catch (error) { $('runLog').textContent = `状态读取失败: ${error.message}`; }
  clearTimeout(pollTimer);
  pollTimer = setTimeout(pollStatus, 3000);
}

async function stopTraining() {
  if (!taskId) return;
  try { await jsonFetch(`/api/training/${taskId}/stop`, { method: 'POST' }); pollStatus(); } catch (error) { alert(`停止失败\n${error.message}`); }
}

async function runEvaluation() {
  if (!taskId) return;
  $('evalResult').textContent = '评估运行中...';
  try {
    const payload = await jsonFetch('/api/evaluation/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ task_id: taskId, episodes: Number($('episodes').value) }) });
    const result = payload.result;
    $('evalResult').className = 'result';
    $('evalResult').innerHTML = `<strong>${result.robot}</strong><p>${result.episodes} episodes · ${result.evaluated_env}</p><div class="metrics"><div><span>平均奖励</span><b>${Number(result.avg_reward).toFixed(3)}</b></div><div><span>奖励标准差</span><b>${Number(result.std_reward).toFixed(3)}</b></div><div><span>平均前进速度</span><b>${Number(result.avg_forward_velocity).toFixed(3)}</b></div><div><span>成功率</span><b>${(Number(result.success_rate) * 100).toFixed(1)}%</b></div></div>`;
    pill($('evalBadge'), '评估完成', 'ok');
  } catch (error) { $('evalResult').textContent = `评估失败: ${error.message}`; pill($('evalBadge'), '评估失败', 'error'); }
}

async function checkBackend() { try { await jsonFetch('/health'); pill($('backendState'), '后端在线', 'ok'); } catch { pill($('backendState'), '后端离线', 'error'); } }

document.addEventListener('DOMContentLoaded', async () => {
  document.querySelectorAll('.step,[data-next],[data-prev]').forEach((button) => button.addEventListener('click', () => setStep(button.dataset.step || button.dataset.next || button.dataset.prev)));
  $('preset').addEventListener('change', (event) => applyPreset(presets.find((item) => item.robot_id === event.target.value)));
  $('validateBtn').addEventListener('click', validateModel); $('startTraining').addEventListener('click', startTraining); $('stopTraining').addEventListener('click', stopTraining); $('runEvaluation').addEventListener('click', runEvaluation); $('resetRewards').addEventListener('click', renderRewards);
  checkBackend();
  const hashStep = window.location.hash.slice(1);
  if (['model', 'training', 'simulation', 'navigation'].includes(hashStep)) setStep(hashStep);
  try { await Promise.all([loadPresets(), loadTrainingOptions()]); } catch (error) { $('validationLog').textContent = `初始化失败: ${error.message}`; }
});
