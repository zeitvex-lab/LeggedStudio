/* Asset import, inspection report, and training-config exchange. */
(function () {
  const $ = (id) => document.getElementById(id);
  let selectedFiles = [];
  let importedModelPath = '';
  let importedRecipe = null;

  async function jsonPost(path, body) {
    const response = await fetch(`${window.location.origin}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
    return payload;
  }

  function renderReport(model, contract, valid) {
    const panel = $('validationReport'); if (!panel) return; panel.hidden = false;
    const stats = model.stats || {};
    $('validationSummary').textContent = `${valid ? '通过' : '存在问题'} · ${(model.format || 'unknown').toUpperCase()} · SHA ${(model.sha256 || '').slice(0, 12)}`;
    $('validationStats').innerHTML = [['Link / Body', stats.links ?? 0], ['Joints', stats.joints ?? 0], ['Actuated', stats.actuated_joints ?? 0], ['Actuators', stats.actuators ?? 'n/a'], ['Mass (kg)', stats.total_mass_kg == null ? 'n/a' : Number(stats.total_mass_kg).toFixed(3)], ['MuJoCo', model.mujoco_loadable === true ? 'loadable' : model.mujoco_loadable === false ? 'failed' : 'n/a']].map(([label, value]) => `<div><span>${label}</span><strong>${value}</strong></div>`).join('');
    const diagnostics = [...(model.errors || []).map((text) => ({ level: 'error', text })), ...(model.warnings || []).map((text) => ({ level: 'warning', text })), ...((contract.errors || []).map((text) => ({ level: 'error', text: `Contract: ${text}` }))), ...((contract.warnings || []).map((text) => ({ level: 'warning', text: `Contract: ${text}` })))];
    const inspection = model.inspection || {};
    if (inspection.mesh_files?.length) diagnostics.push({ level: inspection.missing_meshes?.length ? 'error' : 'ok', text: `资源引用 ${inspection.mesh_files.length} 个，缺失 ${inspection.missing_meshes?.length || 0} 个` });
    if (inspection.inertial?.missing_links?.length) diagnostics.push({ level: 'warning', text: `缺少惯量的 link：${inspection.inertial.missing_links.slice(0, 8).join(', ')}` });
    if (!diagnostics.length) diagnostics.push({ level: 'ok', text: '未发现结构、资源或契约诊断' });
    $('validationDiagnostics').innerHTML = diagnostics.map((item) => `<li class="diagnostic-${item.level}"><b>${item.level === 'error' ? '错误' : item.level === 'warning' ? '警告' : '通过'}</b><span>${item.text}</span></li>`).join('');
    const joints = inspection.joints || [];
    $('validationJoints').innerHTML = joints.length ? joints.map((joint) => `<div class="joint-row"><code>${joint.name || '<unnamed>'}</code><span>${joint.type || 'joint'}${joint.parent ? ` · ${joint.parent} → ${joint.child}` : ''}</span></div>`).join('') : '<div class="empty-state">未发现关节</div>';
  }

  async function validate(event) {
    event.preventDefault(); event.stopImmediatePropagation();
    const log = $('validationLog');
    try {
      const contract = JSON.parse($('contractJson').value);
      const modelFile = selectedFiles.find((file) => /\.(urdf|xml|mjcf)$/i.test(file.name));
      const body = { format: $('format').value, filename: modelFile?.name || $('modelPath').value.trim() || 'model.xml', contract };
      if (modelFile) body.content = await modelFile.text(); else body.path = importedModelPath || $('modelPath').value.trim();
      log.textContent = '正在解析模型、检查资源引用、拓扑、惯量和关节限制...';
      const [model, contractResult] = await Promise.all([jsonPost('/api/models/validate', body), jsonPost('/api/contracts/validate', contract)]);
      const valid = model.valid !== false && contractResult.valid !== false;
      if (typeof setBadge === 'function') setBadge($('modelBadge'), valid ? '验证通过' : '存在问题', valid ? 'ok' : 'error');
      if ($('stageStatus')) $('stageStatus').textContent = valid ? '模型与 Contract 已通过检查' : '模型检查存在问题';
      if ($('viewerFormat')) $('viewerFormat').textContent = (model.format || $('format').value).toUpperCase();
      log.textContent = `${valid ? '✓ 验证通过' : '✕ 验证失败'}\n格式：${(model.format || 'unknown').toUpperCase()}\n机器人：${contract.robot_id || '-'}\n关节：${model.stats?.actuated_joints ?? '-'}\n执行器：${model.stats?.actuators ?? '-'}\nMuJoCo：${model.mujoco_loadable === true ? '可加载' : model.mujoco_loadable === false ? '编译失败' : '结构检查完成'}`;
      renderReport(model, contractResult, valid);
    } catch (error) { if (typeof setBadge === 'function') setBadge($('modelBadge'), '验证失败', 'error'); log.textContent = `✕ ${error.message}`; }
  }

  async function encodeFile(file) {
    if (/\.(urdf|xml|mjcf|xacro)$/i.test(file.name)) return { path: file.webkitRelativePath || file.name, content: await file.text(), encoding: 'utf-8' };
    const bytes = new Uint8Array(await file.arrayBuffer()); let binary = '';
    for (let index = 0; index < bytes.length; index += 0x8000) binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
    return { path: file.webkitRelativePath || file.name, content: btoa(binary), encoding: 'base64' };
  }

  async function importAssets() {
    const status = $('assetImportStatus');
    try {
      if (!selectedFiles.length) throw new Error('请先选择 URDF/MJCF 文件或资产目录');
      const modelFile = selectedFiles.find((file) => /\.(urdf|xml|mjcf)$/i.test(file.name));
      if (!modelFile) throw new Error('资产目录中未找到 URDF/MJCF 主模型文件');
      if (status) status.textContent = `正在导入 ${selectedFiles.length} 个文件...`;
      const payload = await jsonPost('/api/models/import', { files: await Promise.all(selectedFiles.map(encodeFile)), model_filename: modelFile.webkitRelativePath || modelFile.name, format: $('format').value });
      if (payload.valid === false && !payload.imported) throw new Error((payload.errors || []).join('; ') || '资产导入失败');
      importedModelPath = payload.model_path;
      window.__leggedStudioImportedRobot = payload.contract_draft;
      $('modelPath').value = payload.model_path;
      $('contractJson').value = JSON.stringify(payload.contract_draft, null, 2);
      $('stageRobotName').textContent = payload.contract_draft?.family || modelFile.name;
      const simRobot = $('simRobot');
      if (simRobot && payload.contract_draft?.robot_id && !simRobot.querySelector(`option[value="${payload.contract_draft.robot_id}"]`)) { const option = document.createElement('option'); option.value = payload.contract_draft.robot_id; option.textContent = `${payload.contract_draft.family || payload.contract_draft.robot_id} (导入)`; simRobot.appendChild(option); }
      $('presetMeta').innerHTML = `<strong>Imported asset</strong><br>${selectedFiles.length} files · ${payload.stats?.links || 0} links / ${payload.stats?.joints || 0} joints<br><span>${payload.model_path}</span>`;
      if (status) status.textContent = `已导入：${payload.model_path}`;
      selectedFiles = [];
      if ($('modelFile')) $('modelFile').value = '';
    } catch (error) { if (status) status.textContent = `导入失败：${error.message}`; }
  }

  function configPayload() {
    const base = typeof window.trainingPayload === 'function' ? window.trainingPayload() : { contract: JSON.parse($('contractJson').value), backend: 'native_mjlab', algorithm: $('algorithm').value, task_name: $('taskName').value, terrain_type: $('terrain').value, num_envs: Number($('numEnvs').value), max_iterations: Number($('maxIterations').value), learning_rate: Number($('learningRate').value), save_interval: Number($('saveInterval').value), device: $('device').value, gamma: Number($('gamma').value), gae_lambda: Number($('gaeLambda').value), num_steps: Number($('numSteps').value), num_minibatches: Number($('numMinibatches').value), alpha: Number($('alpha').value), seed: Number($('seed').value), reward_scales: {} };
    const reward_scales = {};
    document.querySelectorAll('[data-reward]').forEach((input) => { const weight = document.querySelector(`[data-weight="${input.dataset.reward}"]`); reward_scales[input.dataset.reward] = input.checked ? Number(weight?.value || 0) : 0; });
    base.reward_scales = reward_scales;
    base.schema_version = 'training-config-1.0';
    const currentRecipe = importedRecipe || {};
    base.recipe = { ...currentRecipe, schema_version: 'training-recipe-1.0', task_name: base.task_name, algorithm: base.algorithm, backend: 'native_mjlab', reward_scales, environment: { ...(currentRecipe.environment || {}), num_envs: base.num_envs, max_iterations: base.max_iterations, episode_length_s: Number(base.episode_length_s || currentRecipe.environment?.episode_length_s || 20), terrain_type: base.terrain_type }, algorithm_config: { ...(currentRecipe.algorithm_config || {}), learning_rate: base.learning_rate, num_steps: base.num_steps, num_minibatches: base.num_minibatches, gamma: base.gamma, gae_lambda: base.gae_lambda, clip_param: Number($('clipParam')?.value || 0.2), entropy_coef: Number($('entropyCoef')?.value || base.alpha || 0.01), save_interval: base.save_interval, device: base.device }, seed: Number(base.seed || 0) };
    return base;
  }
  function setConfig(payload) {
    const recipe = payload.recipe || {};
    importedRecipe = recipe;
    const environment = recipe.environment || {};
    const algorithmConfig = recipe.algorithm_config || {};
    const value = (key, fallback) => payload[key] !== undefined ? payload[key] : recipe[key] !== undefined ? recipe[key] : environment[key] !== undefined ? environment[key] : algorithmConfig[key] !== undefined ? algorithmConfig[key] : fallback;
    if (payload.contract) $('contractJson').value = JSON.stringify(payload.contract, null, 2);
    [['algorithm', value('algorithm', 'PPO')], ['taskName', value('task_name', 'forward_walk')], ['terrain', value('terrain_type', 'plane')], ['numEnvs', value('num_envs', 4096)], ['maxIterations', value('max_iterations', 1000)], ['learningRate', value('learning_rate', 0.0003)], ['saveInterval', value('save_interval', 100)], ['device', value('device', 'auto')], ['gamma', value('gamma', 0.99)], ['gaeLambda', value('gae_lambda', 0.95)], ['numSteps', value('num_steps', 24)], ['numMinibatches', value('num_minibatches', 4)], ['alpha', value('alpha', 0.01)], ['seed', value('seed', 0)]].forEach(([id, next]) => { if ($(id)) $(id).value = next; });
    Object.entries(payload.reward_scales || recipe.reward_scales || {}).forEach(([id, weightValue]) => { const checkbox = document.querySelector(`[data-reward="${id}"]`); const weight = document.querySelector(`[data-weight="${id}"]`); if (checkbox) checkbox.checked = Number(weightValue) !== 0; if (weight) weight.value = weightValue; });
  }
  function exportConfig() { const blob = new Blob([JSON.stringify(configPayload(), null, 2)], { type: 'application/json' }); const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = `legged-studio-training-${Date.now()}.json`; link.click(); URL.revokeObjectURL(link.href); }
  async function exportProject() {
    const response = await fetch(`${window.location.origin}/api/project/export`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ training_config: configPayload(), scenario: { map_id: $('simMap')?.value || 'flat', mode: 'basic' } }) });
    if (!response.ok) throw new Error(`项目包导出失败：HTTP ${response.status}`);
    const blob = await response.blob(); const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = 'legged-studio-project.lsproj.zip'; link.click(); URL.revokeObjectURL(link.href);
  }
  async function importProject(file) {
    const bytes = new Uint8Array(await file.arrayBuffer()); let binary = '';
    for (let index = 0; index < bytes.length; index += 0x8000) binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
    const payload = await jsonPost('/api/project/import', { archive_base64: btoa(binary) });
    if (!payload.success) throw new Error(payload.error || '项目包导入失败');
    if (payload.training_config && Object.keys(payload.training_config).length) setConfig(payload.training_config);
    (payload.robots || []).forEach((robot) => { const select = $('simRobot'); if (!select || !robot.robot_id || select.querySelector(`option[value="${robot.robot_id}"]`)) return; const option = document.createElement('option'); option.value = robot.robot_id; option.textContent = `${robot.family || robot.robot_id} (项目包)`; select.appendChild(option); });
    const imports = payload.manifest?.imports || [];
    if ($('projectPackageStatus')) $('projectPackageStatus').textContent = `已导入项目包：${imports.length} 个资产包`;
  }
  function mountProjectControls() {
    const home = $('home'); if (!home || $('projectPackageTools')) return;
    const section = document.createElement('section'); section.id = 'projectPackageTools'; section.className = 'panel project-package-tools'; section.innerHTML = '<div class="panel-title"><div><span class="eyebrow">PROJECT PACKAGE</span><h2>机器人资产与实验包</h2></div><span id="projectPackageStatus" class="panel-meta">ZIP 包含资产、训练配置和场景</span></div><div class="project-package-actions"><button id="exportProjectPackage" class="button secondary">导出项目包</button><label class="button ghost">导入项目包<input id="importProjectPackage" type="file" accept=".zip,.lsproj.zip" hidden></label></div>';
    home.insertBefore(section, $('homeRuns')?.previousElementSibling || home.lastElementChild);
    $('exportProjectPackage').addEventListener('click', () => exportProject().catch((error) => { $('projectPackageStatus').textContent = error.message; }));
    $('importProjectPackage').addEventListener('change', (event) => { const file = event.target.files?.[0]; if (file) importProject(file).catch((error) => { $('projectPackageStatus').textContent = error.message; }); });
  }
  function patchTrainingPayload() {
    if (typeof window.trainingPayload !== 'function' || window.__leggedStudioTrainingPatched) return;
    const original = window.trainingPayload;
    window.trainingPayload = function () {
      const payload = original();
      payload.terrain = { terrain_type: payload.terrain_type, generator: payload.terrain_type === 'rough' ? 'ROUGH_TERRAINS_CFG' : null };
      payload.command_ranges = { lin_vel_x: [-1, 1], lin_vel_y: [-1, 1], ang_vel_yaw: [-1, 1] };
      payload.curriculum = { terrain_levels: payload.terrain_type === 'rough' };
      payload.reward_params = {};
      return payload;
    };
    window.__leggedStudioTrainingPatched = true;
  }
  function mountControls() {
    mountProjectControls(); patchTrainingPayload();
    const picker = $('modelFile');
    if (picker) picker.multiple = true;
    picker?.addEventListener('change', (event) => { selectedFiles = Array.from(event.target.files || []); if ($('modelFileName')) $('modelFileName').textContent = selectedFiles.length ? `${selectedFiles.length} 个文件：${selectedFiles[0].webkitRelativePath || selectedFiles[0].name}` : '未选择文件'; });
    const form = picker?.closest('.form-panel');
    if (form && !$('importModel')) {
      const folderRow = document.createElement('div'); folderRow.className = 'import-folder-row'; folderRow.innerHTML = '<label class="button ghost">选择资产目录<input id="assetFolder" type="file" webkitdirectory directory multiple hidden></label><span id="assetFolderName" class="panel-meta">可选：包含 mesh 的目录</span>'; form.insertBefore(folderRow, $('validateBtn'));
      const row = document.createElement('div'); row.className = 'import-actions'; row.innerHTML = '<button id="importModel" class="button secondary">导入资产到工作区</button><span id="assetImportStatus" class="panel-meta">保存模型、mesh 和相对路径</span>'; form.insertBefore(row, $('validateBtn'));
      $('assetFolder').addEventListener('change', (event) => { const folderFiles = Array.from(event.target.files || []); selectedFiles = [...selectedFiles.filter((file) => !folderFiles.some((item) => item.name === file.name && item.size === file.size)), ...folderFiles]; $('assetFolderName').textContent = folderFiles.length ? `${folderFiles.length} 个目录文件` : '可选：包含 mesh 的目录'; });
      $('importModel').addEventListener('click', importAssets);
    }
    const actions = $('startTraining')?.parentElement;
    if (actions && !$('exportTrainingConfig')) { const label = document.createElement('label'); label.className = 'config-file-button button ghost'; label.textContent = '导入配置'; label.innerHTML += '<input id="trainingConfigFile" type="file" accept="application/json,.json" hidden>'; const button = document.createElement('button'); button.id = 'exportTrainingConfig'; button.className = 'button ghost'; button.textContent = '导出配置'; actions.insertBefore(label, $('startTraining')); actions.insertBefore(button, $('startTraining')); $('exportTrainingConfig').addEventListener('click', exportConfig); $('trainingConfigFile').addEventListener('change', async (event) => { const file = event.target.files?.[0]; if (!file) return; try { setConfig(JSON.parse(await file.text())); } catch (error) { alert(`配置导入失败：${error.message}`); } }); }
    $('validateBtn')?.addEventListener('click', validate, true);
    const simStart = $('startSimulation');
    if (simStart && !simStart.dataset.projectPatched) {
      simStart.dataset.projectPatched = 'true';
      simStart.addEventListener('click', () => { if (window.__leggedStudioImportedRobot && $('simRobot')?.value === window.__leggedStudioImportedRobot.robot_id) window.__leggedStudioSimulationContract = window.__leggedStudioImportedRobot; }, true);
    }
    if (!window.__leggedStudioFetchPatched) {
      const originalFetch = window.fetch.bind(window);
      window.fetch = (input, init = {}) => {
        const url = String(input); if (url.endsWith('/api/simulation/sessions') && init.method === 'POST' && window.__leggedStudioSimulationContract) { const body = JSON.parse(init.body || '{}'); body.contract = window.__leggedStudioSimulationContract; init = { ...init, body: JSON.stringify(body) }; }
        return originalFetch(input, init);
      };
      window.__leggedStudioFetchPatched = true;
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mountControls); else mountControls();
}());
