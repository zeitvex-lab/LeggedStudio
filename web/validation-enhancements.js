/* Browser-side validation enhancements inspired by URDF-Studio and robot_viewer. */
(function () {
  const $ = (id) => document.getElementById(id);
  let selectedFile = null;
  async function request(body) {
    const response = await fetch(`${window.location.origin}/api/models/validate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
    return payload;
  }
  function report(model, contract, valid) {
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
      const body = { format: $('format').value, filename: selectedFile?.name || $('modelPath').value.trim() || 'model.xml', contract };
      if (selectedFile) body.content = await selectedFile.text(); else body.path = $('modelPath').value.trim();
      log.textContent = '正在解析模型、检查资源引用、拓扑、惯量和关节限制...';
      const [model, contractResult] = await Promise.all([request(body), fetch(`${window.location.origin}/api/contracts/validate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(contract) }).then((response) => response.json())]);
      const valid = model.valid !== false && contractResult.valid !== false;
      if (typeof setBadge === 'function') setBadge($('modelBadge'), valid ? '验证通过' : '存在问题', valid ? 'ok' : 'error');
      if ($('stageStatus')) $('stageStatus').textContent = valid ? '模型与 Contract 已通过检查' : '模型检查存在问题';
      if ($('viewerFormat')) $('viewerFormat').textContent = (model.format || $('format').value).toUpperCase();
      log.textContent = `${valid ? '✓ 验证通过' : '✕ 验证失败'}\n格式：${(model.format || 'unknown').toUpperCase()}\n机器人：${contract.robot_id || '-'}\n关节：${model.stats?.actuated_joints ?? '-'}\n执行器：${model.stats?.actuators ?? '-'}\nMuJoCo：${model.mujoco_loadable === true ? '可加载' : model.mujoco_loadable === false ? '编译失败' : '结构检查完成'}`;
      report(model, contractResult, valid);
    } catch (error) { if (typeof setBadge === 'function') setBadge($('modelBadge'), '验证失败', 'error'); log.textContent = `✕ ${error.message}`; }
  }
  function init() {
    $('modelFile')?.addEventListener('change', (event) => { selectedFile = event.target.files?.[0] || null; if ($('modelFileName')) $('modelFileName').textContent = selectedFile ? `${selectedFile.name} · ${Math.round(selectedFile.size / 1024)} KB` : '未选择文件；也可以使用项目内模型路径'; if (selectedFile && $('format')?.value === 'auto') $('viewerFormat').textContent = /\.urdf$/i.test(selectedFile.name) ? 'URDF' : 'MJCF'; });
    $('validateBtn')?.addEventListener('click', validate, true);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
}());
