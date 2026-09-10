const API = window.location.origin;
const $ = (id) => document.getElementById(id);
let presets = [], selectedPreset = null, selectedModelContent = null;
let urdfSceneState = null;
let importedAssetFiles = [];
let jointMetadata = new Map();
let jointDisplayUnit = 'rad';
let robotPoseDraft = [];
let robotCurrentPose = {};
let robotPackageRequest = 0;
const loadedViews = new Set();

function buildRobotWorkspace() {
  const section = $('robot') || $('validate');
  if (!section) return;
  // The 工作台形态重构 ships the robot workspace as static markup inside
  // #robot; rebuild only for the legacy path (#validate) so we don't wipe
  // the hand-authored static layout.
  if (section.id === 'robot' && section.querySelector('.robot-workspace')) return;
  const nav = document.querySelector('[data-step="robot"]') || document.querySelector('.nav-item[data-step="validate"]');
  if (nav) nav.childNodes[nav.childNodes.length - 1].textContent = '机器人';
  section.innerHTML = `
    <div class="view-heading compact robot-heading">
      <div><span class="eyebrow">02 / ROBOT WORKBENCH</span><h1>机器人</h1><p>检查模型、关节和控制接口。</p></div>
      <span id="robotState" class="badge pending">未选择</span>
    </div>
    <div class="robot-workspace">
      <aside class="robot-packages panel">
        <div class="panel-title"><div><span class="eyebrow">PACKAGE LIBRARY</span><h2>机器人包</h2></div><button class="text-button" id="refreshRobotPackages">刷新</button></div>
        <div id="robotPackageList" class="robot-package-list"><div class="empty-state">正在读取本地包...</div></div>
        <label class="file-picker compact robot-import"><span>导入文件夹</span><input id="modelFile" type="file" webkitdirectory directory multiple><small id="modelFileName">URDF / MJCF + meshes</small></label>
        <div class="robot-package-help">本地导入会保存到 workspace/packages。</div>
      </aside>
      <section class="robot-viewport panel">
        <div class="viewer-toolbar">
          <div class="viewer-identity"><span class="toolbar-title">THREE.JS VIEWER</span><span id="viewerFormat" class="toolbar-meta">等待包</span></div>
          <div class="viewer-tools" role="toolbar" aria-label="模型显示工具">
            <button class="viewer-toggle active" id="toggleVisual" type="button" aria-pressed="true" title="显示外观模型">外观</button>
            <button class="viewer-toggle" id="toggleCollision" type="button" aria-pressed="false" title="显示碰撞模型">碰撞</button>
            <button class="viewer-toggle" id="toggleInertial" type="button" aria-pressed="false" title="显示惯性张量范围">惯性</button>
            <button class="viewer-toggle" id="toggleCenterOfMass" type="button" aria-pressed="false" title="显示各连杆质心">质心</button>
            <button class="viewer-toggle active" id="toggleGrid" type="button" aria-pressed="true" title="显示地面网格">网格</button>
            <button class="viewer-toggle active" id="toggleAxes" type="button" aria-pressed="true" title="显示世界坐标轴">坐标轴</button>
            <button class="viewer-toggle" id="toggleJointAxes" type="button" aria-pressed="false" title="显示可动关节轴">关节轴</button>
            <button class="icon-button" id="fitModel" type="button" title="适配视图" aria-label="适配视图">⌖</button>
          </div>
        </div>
        <div class="model-stage robot-model-stage">
          <div id="modelPreviewEmpty" class="preview-empty">从左侧选择机器人包</div>
          <div class="viewer-gesture-hint">左键旋转 · 右键平移 · 滚轮缩放</div>
        </div>
        <div class="viewer-footer"><span id="stageStatus">选择包后加载模型</span><span id="robotDiagnostics">Three.js URDF / MJCF</span></div>
      </section>
      <section class="robot-editor panel">
        <div class="panel-title"><div><span class="eyebrow">INSPECTOR</span><h2 id="robotEditorTitle">机器人参数</h2></div><span id="robotEditorMeta" class="panel-meta">未加载</span></div>
        <div class="robot-editor-tabs" role="tablist">
          <button class="robot-tab active" data-robot-tab="joints" type="button">关节控制</button>
          <button class="robot-tab" data-robot-tab="mapping" type="button">动作映射</button>
          <button class="robot-tab" data-robot-tab="motor" type="button">电机参数</button>
          <button class="robot-tab" data-robot-tab="inertia" type="button">质量与惯量</button>
          <button class="robot-tab" data-robot-tab="inspection" type="button">体检</button>
        </div>
        <div class="robot-pane active-pane" data-robot-pane="joints">
          <div class="joint-toolbar"><button type="button" class="button ghost small" id="resetRobotPose" disabled>默认姿态</button><button type="button" class="button ghost small" id="zeroRobotPose" disabled>零姿态</button><button type="button" class="text-button" id="captureRobotPose" disabled>设为默认</button></div>
          <div class="joint-column-head"><span>关节</span><span>角度 / 位移</span></div>
          <div id="robotPoseEditor" class="robot-pose-editor"><div class="empty-state">未加载可动关节</div></div>
        </div>
        <div class="robot-pane" data-robot-pane="mapping"><div class="pane-note">动作索引必须与训练和策略输出顺序一致。</div><div id="robotJointEditor" class="robot-joint-editor"><div class="empty-state">未选择机器人包</div></div></div>
        <div class="robot-pane" data-robot-pane="motor">
          <div class="pane-note">Kp / Kd / 力矩限幅 / 速度限幅按关节组生效，保存后写入机器人包并同步到浏览器仿真配置。</div>
          <div id="controlGainsGrid" class="control-gains-grid"></div>
        </div>
        <div class="robot-pane" data-robot-pane="inertia"><div class="pane-note">来自模型 inertial 定义；勾选“惯性”可在 3D 视图查看等效惯量盒与质心。</div><div id="inertialTable" class="inertial-table"><div class="empty-state">未选择机器人包</div></div></div>
        <div class="robot-pane" data-robot-pane="inspection">
          <div class="pane-note">体检五卡：质量三来源 / 碰撞 / 惯量 / 电机参数（角色分组 + 官方 diff）/ 关节。三色徽章：✅ 通过 · ⚠ 警告 · ❌ 失败。</div>
          <div class="joint-toolbar"><button type="button" class="button primary small" id="runInspection">运行体检</button></div>
          <div id="inspectionCards" class="inspection-cards"><div class="empty-state">未运行体检——选择包后点「运行体检」</div></div>
        </div>
        <textarea id="contractJson" hidden></textarea><select id="preset" hidden></select><span id="presetMeta" hidden></span><span id="stageRobotName" hidden></span><button id="copyContract" hidden></button><input id="modelPath" type="hidden"><select id="format" hidden><option value="auto">auto</option><option value="urdf">urdf</option><option value="mjcf">mjcf</option></select><button id="validateBtn" hidden></button><pre id="validationLog" hidden></pre><span id="modelBadge" hidden></span>
        <div class="robot-actions"><button id="deleteRobotPackage" class="button ghost" disabled>删除包</button><button id="saveRobotPackage" class="button primary" disabled>保存配置</button></div>
      </section>
    </div>`;
}

function renderRobotPackageList() {
  const list = $('robotPackageList');
  if (!list) return;
  list.innerHTML = presets.length ? presets.map((item) => {
    const id = String(item.robot_id || '');
    const name = String(item.family || id || 'Unnamed package');
    const format = String(item.robot_package?.model?.format || 'MJCF').toUpperCase();
    const source = item.source === 'workspace' ? '本地包' : item.source === 'bundled' ? '内置包' : String(item.source || '未知');
    return `<button class="robot-package-item ${selectedPreset?.robot_id === id ? 'active' : ''}" data-robot-id="${escapeHtml(id)}"><span><strong>${escapeHtml(name)}</strong><small>${Number(item.dof || 0)} DOF · ${escapeHtml(format)}</small></span><span class="package-kind">${escapeHtml(source)}</span></button>`;
  }).join('') : '<div class="empty-state">暂无可用机器人包</div>';
  list.querySelectorAll('[data-robot-id]').forEach((button) => button.addEventListener('click', () => selectRobotPackage(button.dataset.robotId)));
}

/** @typedef {import("./shared/generated/types").RobotContractV3} RobotContractV3 */

/**
 * v3 契约的观测维度自洽值（Σcomponents.width）；v2 契约无 components 时返回 null。
 * 类型来自 schema 真值源生成的 web/shared/generated/types.d.ts。
 * @param {Partial<RobotContractV3>} contract
 * @returns {number|null}
 */
function observationDimensionV3(contract) {
  const components = contract?.observation?.components;
  if (!Array.isArray(components) || !components.length) return null;
  return components.reduce((sum, component) => sum + (Number(component.width) || 0), 0);
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
}

const INSPECTION_BADGES = { pass: '✅', warn: '⚠', fail: '❌' };
const INSPECTION_TITLES = { mass: '质量', collision: '碰撞', inertia: '惯量', motor: '电机参数', joints: '关节' };

function renderInspectionDiffDetails(card) {
  if (!Array.isArray(card.diffs) || !card.diffs.length) return '';
  const rows = card.diffs.map((item) => `<tr><td>${escapeHtml(item.role)}</td><td>${escapeHtml(item.param)}</td><td>${escapeHtml(item.package)}</td><td>${escapeHtml(item.official)}</td><td>${(item.delta_pct * 100).toFixed(1)}%</td></tr>`).join('');
  return `<table class="inspection-diff-table"><thead><tr><th>角色</th><th>参数</th><th>包内值</th><th>官方值</th><th>偏差</th></tr></thead><tbody>${rows}</tbody></table>`;
}

async function runPackageInspection() {
  const container = $('inspectionCards');
  if (!container) return;
  if (!selectedPreset?.robot_id) {
    container.innerHTML = '<div class="empty-state">先在左侧选择一个机器人包</div>';
    return;
  }
  container.innerHTML = '<div class="empty-state">体检运行中…</div>';
  try {
    const report = await jsonFetch(`/api/models/packages/${encodeURIComponent(selectedPreset.robot_id)}/inspection`);
    const cards = Object.entries(report.cards || {}).map(([key, card]) => `
      <div class="inspection-card status-${escapeHtml(card.status)}">
        <div class="inspection-card-head"><span class="inspection-badge">${INSPECTION_BADGES[card.status] || '·'}</span><strong>${INSPECTION_TITLES[key] || escapeHtml(key)}</strong><span class="inspection-summary">${escapeHtml(card.summary)}</span></div>
        ${renderInspectionDiffDetails(card)}
      </div>`).join('');
    container.innerHTML = `<div class="inspection-overall status-${escapeHtml(report.overall)}">整体：${INSPECTION_BADGES[report.overall] || '·'} ${escapeHtml(report.overall)}</div>${cards}`;
  } catch (error) {
    container.innerHTML = `<div class="empty-state">体检失败：${escapeHtml(error.message)}——确认后端已启动后重试</div>`;
  }
}

function renderRobotEditor(preset) {
  const contract = preset?.contract || {};
  const mappedJoints = contract.joints?.actuated_joints || [];
  const savedPose = contract.joints?.default_pose || [];
  const availableJoints = Array.from(jointMetadata.keys());
  const controlledJoints = availableJoints.length ? availableJoints : mappedJoints;
  const control = contract.control || {};
  if ($('robotEditorTitle')) $('robotEditorTitle').textContent = preset ? (preset.family || preset.robot_id) : '机器人参数';
  if ($('robotEditorMeta')) {
    const obsDimension = observationDimensionV3(contract);
    $('robotEditorMeta').textContent = preset ? `${controlledJoints.length || mappedJoints.length} joints · ${contract.contract_id || 'Contract'}${obsDimension != null ? ` · obs ${obsDimension}D` : ''}` : '未加载';
  }
  if ($('robotJointEditor')) {
    const options = availableJoints.length ? availableJoints : mappedJoints;
    $('robotJointEditor').innerHTML = mappedJoints.length ? mappedJoints.map((name, index) => `<label class="robot-joint-row"><span>${index + 1}</span><select data-joint-index="${index}" aria-label="动作 ${index + 1} 对应关节">${[...new Set([name, ...options])].map((candidate) => `<option value="${escapeHtml(candidate)}" ${candidate === name ? 'selected' : ''}>${escapeHtml(candidate)}</option>`).join('')}</select></label>`).join('') : '<div class="empty-state">Contract 未声明动作关节</div>';
  }
  if ($('robotPoseEditor')) {
    $('robotPoseEditor').innerHTML = controlledJoints.length ? `<div class="pose-unit-row"><span>${controlledJoints.length} 个可动关节</span><select id="jointDisplayUnit" aria-label="关节显示单位"><option value="rad" ${jointDisplayUnit === 'rad' ? 'selected' : ''}>rad / m</option><option value="deg" ${jointDisplayUnit === 'deg' ? 'selected' : ''}>deg / mm</option></select></div>${controlledJoints.map((name, index) => {
      const mappedIndex = mappedJoints.indexOf(name);
      const initial = Number(robotCurrentPose[name] ?? (mappedIndex >= 0 ? robotPoseDraft[mappedIndex] ?? savedPose[mappedIndex] : 0) ?? 0);
      return jointControlMarkup(name, index, initial);
    }).join('')}` : '<div class="empty-state">模型中没有可动关节</div>';
  }
  // Frequencies and action scale stay owned by the training configuration
  // (03 训练配置); this panel only edits motor-level parameters.
  const simConfig = preset?.simulation_config || {};
  const gainsSource = {
    stiffness: control.stiffness || simConfig.stiffness || null,
    damping: control.damping || simConfig.damping || null,
    torque_limits: control.torque_limits || simConfig.torque_limits || null,
  };
  gainsSource.torque_limits = gainsSource.torque_limits || simConfig.torque_limits || null;
  gainsSource.velocity_limits = control.velocity_limits || simConfig.velocity_limits || null;
  renderControlGainsGrid(gainsSource, mappedJoints, control.control_modes || simConfig.control_modes || null);
  renderInertialTable();
  $('saveRobotPackage')?.toggleAttribute('disabled', !preset);
  $('deleteRobotPackage')?.toggleAttribute('disabled', !preset || preset.source !== 'workspace');
  ['resetRobotPose', 'zeroRobotPose'].forEach((id) => $(id)?.toggleAttribute('disabled', !preset || !controlledJoints.length));
  $('captureRobotPose')?.toggleAttribute('disabled', !preset || !mappedJoints.length);
  if ($('robotState')) setBadge($('robotState'), preset ? '已加载' : '未选择', preset ? 'ok' : 'pending');
  document.querySelectorAll('[data-pose-index]').forEach((input) => input.addEventListener('input', () => {
    const name = controlledJoints[Number(input.dataset.poseIndex)];
    const value = Number(input.value || 0);
    const output = document.querySelector(`[data-pose-output="${input.dataset.poseIndex}"]`);
    if (output) output.value = displayJointValue(name, value);
    applyJointPose(name, value);
  }));
  document.querySelectorAll('[data-pose-output]').forEach((input) => input.addEventListener('input', () => {
    const index = Number(input.dataset.poseOutput), name = controlledJoints[index];
    const slider = document.querySelector(`[data-pose-index="${index}"]`);
    if (!slider) return;
    const value = internalJointValue(name, Number(input.value || 0));
    slider.value = Math.max(Number(slider.min), Math.min(Number(slider.max), value));
    input.value = displayJointValue(name, Number(slider.value));
    applyJointPose(name, Number(slider.value));
  }));
  if ($('jointDisplayUnit')) $('jointDisplayUnit').onchange = (event) => { jointDisplayUnit = event.target.value; renderRobotEditor(preset); };
  if ($('zeroRobotPose')) $('zeroRobotPose').onclick = () => setPoseControls(controlledJoints, controlledJoints.map(() => 0));
  if ($('resetRobotPose')) $('resetRobotPose').onclick = () => setPoseControls(controlledJoints, controlledJoints.map((name) => {
    const mappedIndex = mappedJoints.indexOf(name);
    return mappedIndex >= 0 ? Number(robotPoseDraft[mappedIndex] ?? savedPose[mappedIndex] ?? 0) : 0;
  }));
  if ($('captureRobotPose')) $('captureRobotPose').onclick = () => {
    robotPoseDraft = mappedJoints.map((name, index) => Number(robotCurrentPose[name] ?? robotPoseDraft[index] ?? savedPose[index] ?? 0));
    if ($('robotDiagnostics')) $('robotDiagnostics').textContent = '当前姿态已设为默认，保存配置后写入机器人包';
    setBadge($('robotState'), '有未保存更改', 'pending');
  };
}

function inferMotorSegments(mappedJoints) {
  // Morphology-agnostic: strip the leg-side prefix and trailing "joint" token
  // so each distinct body segment becomes a row. Quadrupeds yield hip/thigh/
  // calf(+wheel), bipeds yield hip_yaw/hip_roll/knee/ankle..., whatever the
  // robot actually names its joints.
  const sideHint = /^(fl|fr|rl|rr|lf|rf|lh|rh|l1|r1|l|r|hr|hl|front|rear|left|right)$/;
  const segments = [];
  const jointToSegment = {};
  for (const joint of mappedJoints) {
    let parts = String(joint).toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
    if (parts.length > 1 && ['joint', 'actuator', 'motor'].includes(parts[parts.length - 1])) parts.pop();
    if (parts.length > 1 && sideHint.test(parts[0])) parts.shift();
    const segment = parts.join('_') || String(joint).toLowerCase();
    if (!segments.includes(segment)) segments.push(segment);
    jointToSegment[joint] = segment;
  }
  return { segments, jointToSegment };
}

function resolveGainValue(map, segment, joints) {
  if (!map || typeof map !== 'object') return '';
  for (const joint of joints) {
    const value = Number(map[joint]);
    if (Number.isFinite(value)) return value;
  }
  const bySegment = Number(map[segment]);
  if (Number.isFinite(bySegment)) return bySegment;
  const jointWide = Number(map.joint);
  return Number.isFinite(jointWide) ? jointWide : '';
}

function renderControlGainsGrid(control, mappedJoints, motorModes) {
  motorModes = motorModes || {};
  const grid = $('controlGainsGrid');
  if (!grid) return;
  if (!mappedJoints.length) {
    grid.innerHTML = '<div class="empty-state">Contract 未声明动作关节</div>';
    return;
  }
  const { segments, jointToSegment } = inferMotorSegments(mappedJoints);
  const rows = [
    { key: 'stiffness', label: 'Kp', step: '0.1' },
    { key: 'damping', label: 'Kd', step: '0.01' },
    { key: 'torque_limits', label: '力矩限幅', step: '0.1' },
    { key: 'velocity_limits', label: '速度限幅', step: '0.1' },
  ];
  const jointsBySegment = {};
  for (const joint of mappedJoints) (jointsBySegment[jointToSegment[joint]] ||= []).push(joint);
  const cols = 'minmax(84px,1.3fr) repeat(4,minmax(0,1fr))';
  // Velocity-driven segments (wheels) have no stiffness: fill Kp with 0.
  const modeFor = (segment, joints) => {
    if (motorModes[segment]) return String(motorModes[segment]).toLowerCase();
    for (const joint of joints) if (motorModes[joint]) return String(motorModes[joint]).toLowerCase();
    return segment.includes('wheel') ? 'velocity' : 'position';
  };
  const header = `<div class="gains-row gains-head" style="grid-template-columns:${cols}"><span>部位</span><span>Kp</span><span>Kd</span><span>力矩限幅</span><span>速度限幅</span></div>`;
  grid.innerHTML = header + segments.map((segment) => {
    const joints = jointsBySegment[segment] || [];
    const mode = modeFor(segment, joints);
    const cells = rows.map((row) => {
      const value = row.key === 'stiffness' && mode === 'velocity'
        ? 0
        : resolveGainValue(control[row.key], segment, joints);
      return `<input data-gain-key="${row.key}" data-gain-segment="${segment}" type="number" min="0" step="${row.step}" value="${value}">`;
    }).join('');
    return `<div class="gains-row" style="grid-template-columns:${cols}" title="${escapeHtml(joints.join(', '))}"><span>${escapeHtml(segment)}</span>${cells}</div>`;
  }).join('');
}

function collectControlGains(control, mappedJoints) {
  // Expand each segment row into explicit per-joint keys so any consumer
  // (per-joint or grouped) can resolve values for any morphology.
  const collect = (key) => {
    const values = {};
    document.querySelectorAll(`[data-gain-key="${key}"]`).forEach((input) => {
      if (input.value === '') return;
      const value = Number(input.value);
      if (!Number.isFinite(value)) return;
      mappedJoints.filter((joint) => inferMotorSegments([joint]).segments[0] === input.dataset.gainSegment)
        .forEach((joint) => { values[joint] = value; });
    });
    return values;
  };
  const stiffness = collect('stiffness');
  const damping = collect('damping');
  const torqueLimits = collect('torque_limits');
  const velocityLimits = collect('velocity_limits');
  return {
    control: {
      ...(control || {}),
      ...(Object.keys(stiffness).length ? { stiffness } : {}),
      ...(Object.keys(damping).length ? { damping } : {}),
      ...(Object.keys(torqueLimits).length ? { torque_limits: torqueLimits } : {}),
      ...(Object.keys(velocityLimits).length ? { velocity_limits: velocityLimits } : {}),
    },
    simulation: {
      ...(Object.keys(stiffness).length ? { stiffness } : {}),
      ...(Object.keys(damping).length ? { damping } : {}),
      ...(Object.keys(torqueLimits).length ? { torque_limits: torqueLimits } : {}),
      ...(Object.keys(velocityLimits).length ? { velocity_limits: velocityLimits } : {}),
    },
  };
}

function renderInertialTable() {
  const table = $('inertialTable');
  if (!table) return;
  const records = typeof window.getRobotInertialData === 'function' ? window.getRobotInertialData() : [];
  if (!records.length) {
    table.innerHTML = '<div class="empty-state">模型未提供 inertial 数据</div>';
    return;
  }
  const totalMass = records.reduce((sum, record) => sum + (record.mass || 0), 0);
  const format = (value) => (Number.isFinite(value) ? Number(value).toPrecision(5).replace(/\.?0+$/, '') : 'N/A');
  const rows = records.map((record) => {
    const principal = record.principal ? record.principal.map(format).join(' / ') : 'N/A';
    const com = record.com.map(format).join(', ');
    return `<div class="inertial-row"><span class="inertial-link" title="${escapeHtml(record.link)}">${escapeHtml(record.link)}</span><span>${Number(record.mass ?? 0).toFixed(4)}</span><span>${com}</span><span>${principal}</span></div>`;
  }).join('');
  table.innerHTML = `<div class="inertial-row inertial-head"><span>连杆</span><span>质量 (kg)</span><span>质心 (m)</span><span>主惯量 I1/I2/I3 (kg·m²)</span></div>${rows}<div class="inertial-total">总质量 ${totalMass.toFixed(4)} kg</div>`;
}

function jointControlMarkup(name, index, value) {
  const metadata = jointMetadata.get(name) || {};
  const lower = Number.isFinite(metadata.lower) ? metadata.lower : -Math.PI;
  const upper = Number.isFinite(metadata.upper) ? metadata.upper : Math.PI;
  const unit = metadata.type === 'slide' || metadata.type === 'prismatic' ? (jointDisplayUnit === 'deg' ? 'mm' : 'm') : (jointDisplayUnit === 'deg' ? 'deg' : 'rad');
  const clamped = Math.max(lower, Math.min(upper, value));
  return `<div class="robot-pose-control"><div class="joint-control-head"><span title="${escapeHtml(name)}">${escapeHtml(name)}</span><small>${escapeHtml(metadata.type || 'joint')}</small></div><div class="joint-slider-line"><span>${displayJointValue(name, lower)}</span><input aria-label="${escapeHtml(name)}" data-pose-index="${index}" type="range" min="${lower}" max="${upper}" step="${Math.max((upper - lower) / 1000, 0.0001)}" value="${clamped}"><span>${displayJointValue(name, upper)}</span></div><label class="joint-value-field"><input aria-label="${escapeHtml(name)} 数值" data-pose-output="${index}" class="joint-value-input" type="number" step="${jointDisplayUnit === 'deg' ? '0.1' : '0.001'}" value="${displayJointValue(name, clamped)}"><span>${unit}</span></label></div>`;
}

function displayJointValue(name, value) {
  const slide = ['slide', 'prismatic'].includes(jointMetadata.get(name)?.type);
  const converted = jointDisplayUnit === 'deg' ? value * (slide ? 1000 : 180 / Math.PI) : value;
  return converted.toFixed(jointDisplayUnit === 'deg' ? 1 : 3);
}

function internalJointValue(name, value) {
  const slide = ['slide', 'prismatic'].includes(jointMetadata.get(name)?.type);
  return jointDisplayUnit === 'deg' ? value / (slide ? 1000 : 180 / Math.PI) : value;
}

function applyJointPose(name, value) {
  robotCurrentPose[name] = value;
  if (typeof window.setUrdfJointPositions === 'function') window.setUrdfJointPositions({ [name]: value });
}

function setPoseControls(joints, values) {
  const positions = {};
  joints.forEach((name, index) => {
    const metadata = jointMetadata.get(name) || {};
    const requested = Number(values[index] || 0);
    const value = Math.max(Number.isFinite(metadata.lower) ? metadata.lower : -Infinity, Math.min(Number.isFinite(metadata.upper) ? metadata.upper : Infinity, requested));
    const slider = document.querySelector(`[data-pose-index="${index}"]`), output = document.querySelector(`[data-pose-output="${index}"]`);
    if (slider) slider.value = value;
    if (output) output.value = displayJointValue(name, value);
    positions[name] = value;
    robotCurrentPose[name] = value;
  });
  if (typeof window.setUrdfJointPositions === 'function') window.setUrdfJointPositions(positions);
}

async function saveRobotPackage() {
  if (!selectedPreset) return;
  try {
    const contract = JSON.parse($('contractJson').value || '{}'), jointInputs = [...document.querySelectorAll('[data-joint-index]')], joints = jointInputs.map((input) => input.value.trim()).filter(Boolean);
    const previousJoints = contract.joints?.actuated_joints || [];
    const previousPose = contract.joints?.default_pose || [];
    const defaultPose = joints.map((name, index) => {
      const previousIndex = previousJoints.indexOf(name);
      return Number(robotPoseDraft[index] ?? (previousIndex >= 0 ? previousPose[previousIndex] : robotCurrentPose[name]) ?? 0);
    });
    contract.joints = { ...(contract.joints || {}), actuated_joints: joints, default_pose: defaultPose };
    contract.action = { ...(contract.action || {}), dimension: joints.length, joint_order: joints, action_scale: contract.action?.action_scale ?? 0.25 };
    const gains = collectControlGains(contract.control, joints.length ? joints : (contract.joints?.actuated_joints || []));
    contract.control = { ...contract.control, ...gains.control, control_hz: contract.control?.control_hz ?? 50, physics_hz: contract.control?.physics_hz ?? 1000, decimation: contract.control?.decimation ?? 20 };
    const result = await jsonFetch(`/api/robots/packages/${encodeURIComponent(selectedPreset.robot_id)}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ contract, simulation: { control_hz: contract.control.control_hz, physics_hz: contract.control.physics_hz, decimation: contract.control.decimation, default_pose: contract.joints.default_pose, ...gains.simulation } }) });
    $('contractJson').value = JSON.stringify(result.contract || contract, null, 2); setBadge($('robotState'), '已保存', 'ok'); $('robotDiagnostics').textContent = '配置已写入本地机器人包'; await loadPresets(selectedPreset.robot_id);
  } catch (error) { $('robotDiagnostics').textContent = `保存失败：${error.message}`; setBadge($('robotState'), '保存失败', 'error'); }
}


async function jsonFetch(path, options = {}) {
  const response = await fetch(`${API}${path}`, options);
  let payload = {};
  try { payload = await response.json(); } catch {}
  if (!response.ok) throw new Error(payload.detail?.message || payload.detail || payload.error?.message || `HTTP ${response.status}`);
  return payload;
}
function setView(name, options = {}) {
  // Inline pages hosted inside frames so the sidebar/workflow shell stays
  // identical across the functional areas. 资产库已原生并入首页
  // （#assetLibraryGrid），不再有独立 assets 视图。
  const framePages = {
    navmap: ['navMapFrame', 'navigation_editor.html?v=0.17.0&embedded=1'],
    deploy: ['deployFrame', 'deploy.html?v=0.17.0&embedded=1'],
    artifacts: ['artifactsFrame', 'artifacts.html?v=0.17.0&embedded=1'],
  };
  if (name in framePages) {
    const [frameId, page] = framePages[name];
    const frame = $(frameId);
    if (!frame) return;
    const expected = new URL(page, window.location.href).toString();
    if (frame.getAttribute('src') !== expected) frame.src = expected;
  }
  if (name === 'config' || name === 'training') {
    const frame = $(name === 'config' ? 'configFrame' : 'trainingFrame');
    if (!frame) return;
    const robot = options.robot || selectedPreset?.robot_id || 'unitree_go2';
    const page = name === 'config'
      ? `training_create.html?v=0.17.0&embedded=1&robot=${encodeURIComponent(robot)}`
      : `training_list.html?v=0.17.0&embedded=1`;
    const expected = new URL(page, window.location.href).toString();
    if (frame.getAttribute('src') !== expected) frame.src = expected;
  }
  document.querySelectorAll('.view').forEach((view) => view.classList.toggle('active-view', view.id === name));
  // 全出血视图（iframe 内嵌页与 Sim2Sim）不带 content 内边距，精确填满
  // main-area 剩余高度；首页/机器人工作台保留常规卡片留白。
  const fullBleed = ['config', 'training', 'simulation', 'navmap', 'deploy', 'artifacts'].includes(name);
  document.querySelector('.content')?.classList.toggle('content-fullbleed', fullBleed);
  // Sidebar + workflow progress both carry data-step targets.
  document.querySelectorAll('.side-item').forEach((item) => item.classList.toggle('active', item.dataset.step === name));
  history.replaceState(null, '', `#${name}`);
  if (name === 'simulation') {
    const frame = $('simBrowserFrame');
    const robot = selectedPreset?.robot_id || 'unitree_go2';
    const expected = `/web/sim2sim/index.html?embedded=1&robot=${encodeURIComponent(robot)}&view=workbench`;
    if (frame) {
      if (frame.getAttribute('src') !== expected) frame.src = expected;
      frame.hidden = false;
      requestAnimationFrame(syncSimulationFrame);
    }
  }
  void loadViewData(name);
}

function syncSimulationFrame() {
  const frame = $('simBrowserFrame');
  const stage = $('simulation');
  if (!frame || !stage || !frame.contentWindow) return;
  const rect = stage.getBoundingClientRect();
  const width = Math.max(1, Math.round(rect.width));
  const height = Math.max(1, Math.round(rect.height));
  frame.style.width = `${width}px`;
  frame.style.height = `${height}px`;
  frame.contentWindow.postMessage({ type: 'legged-studio:resize', width, height }, window.location.origin);
}
async function loadViewData(name) {
  if (loadedViews.has(name)) return;
  loadedViews.add(name);
  try {
    if (name === 'home') await Promise.all([loadCapabilities(), loadRuns(), loadDemos()]);
  } catch (error) {
    loadedViews.delete(name);
    console.error(`Failed to load ${name} data`, error);
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
  if ($('modelPreviewEmpty')) $('modelPreviewEmpty').textContent = '从左侧选择机器人包';
  if ($('stageStatus')) $('stageStatus').textContent = '选择包后加载 Three.js 模型';
  if ($('viewerFormat')) $('viewerFormat').textContent = '等待包';
}
function setInputValue(id, value) {
  const input = $(id);
  if (input && value !== undefined && value !== null) input.value = value;
}
async function applyPreset(preset) {
  if (!preset) return;
  selectedPreset = preset;
  robotPoseDraft = (preset.contract?.joints?.default_pose || []).map(Number);
  robotCurrentPose = Object.fromEntries((preset.contract?.joints?.actuated_joints || []).map((name, index) => [name, Number(robotPoseDraft[index] || 0)]));
  jointMetadata = new Map();
  $('modelPath').value = preset.asset_path || '';
  $('format').value = /\.(xml|mjcf)$/i.test(preset.asset_path || '') ? 'mjcf' : 'urdf';
  $('contractJson').value = JSON.stringify(preset.contract || {}, null, 2);
  $('presetMeta').innerHTML = `<strong>${preset.family || preset.robot_id}</strong><br>${preset.dof || 0} DOF / ${Number(preset.mass_kg || 0).toFixed(1)} kg<br><span>${preset.contract_path || ''}</span>`;
  if ($('stageRobotName')) $('stageRobotName').textContent = preset.family || preset.robot_id;
  selectedModelContent = null;
  renderRobotPackageList();
  const packageId = String(preset?.robot_id || '');
  const modelPath = String(preset?.robot_package?.model?.path || '').replace(/^\/+/, '');
  let cachedXmlText = null;
  if (packageId && modelPath) {
    try {
      const resp = await fetch(`/api/robots/presets/${encodeURIComponent(packageId)}/files/${modelPath}`, { cache: 'no-cache' });
      if (resp.ok) cachedXmlText = await resp.text();
    } catch (_) {}
  }
  loadJointMetadata(preset, cachedXmlText);
  renderRobotEditor(preset);
  if (preset?.asset_path) {
    const modelFormat = preset.robot_package?.model?.format || (/\.urdf$/i.test(preset.asset_path) ? 'urdf' : 'mjcf');
    if ($('stageStatus')) $('stageStatus').textContent = '正在加载真实模型...';
    refreshModelPreview(await loadPresetModelSource(preset, modelFormat, cachedXmlText), modelFormat, true).then(() => { if ($('stageStatus')) $('stageStatus').textContent = 'Three.js 实时模型已加载'; }).catch((error) => { if ($('robotDiagnostics')) $('robotDiagnostics').textContent = `模型加载失败：${error.message}`; });
  }
}
async function selectRobotPackage(robotId) {
  if (!robotId) return;
  const request = ++robotPackageRequest;
  if ($('stageStatus')) $('stageStatus').textContent = '正在读取机器人包...';
  if ($('robotDiagnostics')) $('robotDiagnostics').textContent = '正在读取模型清单与配置';
  try {
    const preset = await jsonFetch(`/api/robots/presets/${encodeURIComponent(robotId)}`);
    if (request !== robotPackageRequest) return;
    const index = presets.findIndex((item) => item.robot_id === robotId);
    if (index >= 0) presets[index] = preset;
    await applyPreset(preset);
  } catch (error) {
    if (request !== robotPackageRequest) return;
    if ($('stageStatus')) $('stageStatus').textContent = '机器人包加载失败';
    if ($('robotDiagnostics')) $('robotDiagnostics').textContent = error.message;
  }
}
async function loadJointMetadata(preset, cachedXmlText) {
  jointMetadata = new Map();
  const packageId = String(preset?.robot_id || '');
  const modelPath = String(preset?.robot_package?.model?.path || '').replace(/^\/+/, '');
  if (!packageId || !modelPath) return;
  try {
    let xmlText = cachedXmlText;
    if (!xmlText) {
      const response = await fetch(`/api/robots/presets/${encodeURIComponent(packageId)}/files/${modelPath}`, { cache: 'no-cache' });
      if (!response.ok) return;
      xmlText = await response.text();
    }
    const documentNode = new DOMParser().parseFromString(xmlText, 'application/xml');
    if (documentNode.querySelector('parsererror')) return;
    if (documentNode.documentElement.tagName.toLowerCase() === 'robot') {
      documentNode.querySelectorAll('robot > joint[name]').forEach((joint) => {
        const limit = joint.querySelector(':scope > limit'), type = joint.getAttribute('type') || 'revolute';
        if (['fixed', 'floating', 'planar'].includes(type)) return;
        jointMetadata.set(joint.getAttribute('name'), {
          type,
          lower: type === 'continuous' ? -Math.PI : finiteOr(limit?.getAttribute('lower'), -Math.PI),
          upper: type === 'continuous' ? Math.PI : finiteOr(limit?.getAttribute('upper'), Math.PI),
        });
      });
      return;
    }
    const defaultRanges = new Map();
    documentNode.querySelectorAll('default[class]').forEach((node) => {
      const joint = node.querySelector(':scope > joint'), parent = node.parentElement?.closest?.('default[class]');
      const inherited = parent ? defaultRanges.get(parent.getAttribute('class')) : null;
      const range = parseRange(joint?.getAttribute('range')) || inherited?.range;
      const axis = joint?.getAttribute('axis') || inherited?.axis;
      defaultRanges.set(node.getAttribute('class'), { range, axis });
    });
    const angleScale = String(documentNode.querySelector('mujoco > compiler')?.getAttribute('angle') || 'degree').toLowerCase() === 'radian' ? 1 : Math.PI / 180;
    documentNode.querySelectorAll('worldbody joint[name]').forEach((joint) => {
      const type = joint.getAttribute('type') || 'hinge';
      if (type === 'free') return;
      const className = joint.getAttribute('class') || joint.parentElement?.getAttribute('childclass');
      const range = parseRange(joint.getAttribute('range')) || defaultRanges.get(className)?.range || [-Math.PI, Math.PI];
      jointMetadata.set(joint.getAttribute('name'), { type, lower: range[0] * (type === 'hinge' ? angleScale : 1), upper: range[1] * (type === 'hinge' ? angleScale : 1) });
    });
  } catch (error) {
    console.warn('joint metadata unavailable', error);
  }
}
function parseRange(value) {
  const values = String(value || '').trim().split(/\s+/).map(Number);
  return values.length >= 2 && values.slice(0, 2).every(Number.isFinite) ? values.slice(0, 2) : null;
}
function finiteOr(value, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}
async function loadPresetModelSource(preset, modelFormat, cachedXmlText) {
  const packageId = String(preset?.robot_id || '');
  const modelPath = String(preset?.robot_package?.model?.path || '').replace(/^\/+/, '');
  if (!packageId || !modelPath) return { path: preset?.asset_path || '' };
  const baseUrl = `/api/robots/presets/${encodeURIComponent(packageId)}/files`;
  let content = cachedXmlText;
  if (!content) {
    const response = await fetch(`/api/robots/presets/${encodeURIComponent(packageId)}/files/${modelPath}`, { cache: 'no-cache' });
    if (!response.ok) throw new Error(`模型文件读取失败 (HTTP ${response.status})`);
    content = await response.text();
  }
  selectedModelContent = content;
  $('modelPath').value = preset.asset_path || modelPath;
  $('format').value = modelFormat;
  return { content, filename: modelPath, path: preset.asset_path || '', baseUrl };
}

async function loadPresets(preferredId = null) {
  const payload = await jsonFetch('/api/robots/presets');
  presets = payload.presets || [];
  if ($('preset')) $('preset').innerHTML = '<option value="">请选择本地资产文件夹</option>';
  renderRobotPackageList();
  renderAssetLibrary();
  if (preferredId && presets.some((item) => item.robot_id === preferredId)) await selectRobotPackage(preferredId);
}

/* ===== 首页资产库：机器人包卡片 + 路径导入 + 索引刷新 ===== */
function setAssetStatus(text) {
  const el = $('assetLibraryStatus');
  if (el) el.textContent = text;
}

function renderAssetLibrary() {
  const grid = $('assetLibraryGrid');
  if (!grid) return;
  if (!presets.length) {
    grid.innerHTML = '<div class="empty-state">暂无机器人包——可在上方输入路径导入，或将包放入工作区 packages/ 目录。</div>';
    return;
  }
  grid.innerHTML = presets.map((item) => {
    const id = String(item.robot_id || '');
    const family = String(item.family || id || '未命名包');
    const workspace = item.source === 'workspace';
    const profiles = Array.isArray(item.training_profiles) ? item.training_profiles : [];
    const visible = profiles.slice(0, 3);
    const chips = profiles.length
      ? `<div class="asset-chips">${visible.map((p) => `<span class="asset-chip${p.valid === false ? ' warn' : ''}" title="${escapeHtml(p.validation_errors?.length ? p.validation_errors.join('; ') : '校验通过')}">${escapeHtml(p.profile_id || '?')}${p.valid === false ? '（校验失败）' : ''}</span>`).join('')}${profiles.length > visible.length ? `<span class="asset-chip" title="其余 ${profiles.length - visible.length} 个训练档案">+${profiles.length - visible.length}</span>` : ''}</div>`
      : '<span class="asset-meta">无训练档案</span>';
    return `<article class="asset-card" data-robot="${escapeHtml(id)}">
      <div class="asset-card-head"><strong title="${escapeHtml(family)}">${escapeHtml(family)}</strong><span class="badge ${workspace ? 'ok' : ''}">${workspace ? '工作区' : '内置'}</span></div>
      <span class="asset-meta">${Number(item.dof || 0)} 自由度 · ${Number(item.mass_kg || 0).toFixed(2)} kg · ${escapeHtml(item.size_class || '-')} / ${escapeHtml(item.locomotion_type || '-')}</span>
      ${chips}
      <code title="${escapeHtml(item.asset_path || '')}">${escapeHtml(item.asset_path || '-')}</code>
      <div class="asset-actions">
        <button class="button primary" type="button" data-asset-action="config" data-robot="${escapeHtml(id)}">配置训练</button>
        <button class="button" type="button" data-asset-action="workbench" data-robot="${escapeHtml(id)}">去工作台</button>
        <a class="button" href="/api/robots/packages/${encodeURIComponent(id)}/export">导出 zip</a>
        ${workspace ? `<button class="button danger" type="button" data-asset-action="delete" data-robot="${escapeHtml(id)}">删除</button>` : ''}
      </div>
    </article>`;
  }).join('');
}

async function refreshAssetLibrary() {
  setAssetStatus('正在重建索引...');
  try {
    await jsonFetch('/api/robots/packages/refresh', { method: 'POST' });
    await loadPresets();
    setAssetStatus(`已同步 ${presets.length} 个机器人包`);
  } catch (error) {
    setAssetStatus(`刷新失败：${error.message}`);
  }
}

async function importAssetPackage() {
  const input = $('assetImportPath');
  const path = input?.value.trim() || '';
  if (!path) {
    setAssetStatus('请先输入机器人包目录的绝对路径');
    return;
  }
  setAssetStatus('正在导入...');
  try {
    const result = await jsonFetch('/api/robots/packages/import', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path }) });
    if (input) input.value = '';
    await loadPresets();
    const profiles = result.record_summary?.profiles || [];
    setAssetStatus(`已导入 ${result.robot_id}${profiles.length ? ` · 档案：${profiles.join(', ')}` : ''}`);
  } catch (error) {
    setAssetStatus(`导入失败：${error.message}`);
  }
}

async function deleteAssetPackage(robotId) {
  if (!robotId || !confirm(`确认删除工作区包 ${robotId}？（内置包不受影响）`)) return;
  try {
    await jsonFetch(`/api/robots/packages/${encodeURIComponent(robotId)}`, { method: 'DELETE' });
    await loadPresets();
    setAssetStatus(`已删除 ${robotId}`);
  } catch (error) {
    setAssetStatus(`删除失败：${error.message}`);
  }
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
function renderNextStep(adapters, cuda) {
  const body = $('homeNextStepBody');
  if (!body) return;
  const steps = [];
  if (!adapters.native_mjlab) {
    steps.push({ label: '配置运行环境', detail: 'MJLab 训练栈未就绪——请在桌面端「系统设置」中配置运行时与 PyTorch 镜像。' });
  }
  if (!adapters.mujoco_simulation) {
    steps.push({ btn: 'simulation', label: '检查仿真依赖', detail: 'MuJoCo 仿真依赖缺失——修复后再做基础仿真。' });
  }
  if (!cuda) {
    steps.push({ label: '检查 CUDA', detail: '未检测到 CUDA——GPU 训练不可用，可在桌面端「系统设置」切换 CPU 或用 GPU profile 重装。' });
  }
  if (steps.length) {
    body.innerHTML = steps.map((item) => `<div class="next-step-item"><div><strong>${item.label}</strong><span>${item.detail}</span></div>${item.btn ? `<button class="button small" data-step="${item.btn}">去处理</button>` : ''}</div>`).join('');
    body.querySelectorAll('[data-step]').forEach((btn) => btn.addEventListener('click', () => setView(btn.dataset.step)));
    return;
  }
  body.innerHTML = `<div class="next-step-item ok"><div><strong>开始训练</strong><span>运行时、仿真与 CUDA 均已就绪——选择机器人资产，进入训练配置，或直接试玩一个内置预训练 demo。</span></div><button class="button primary small" data-step="config">配置训练</button><button class="button ghost small" data-step="simulation">试玩 Demo</button></div>`;
  body.querySelectorAll('[data-step]').forEach((btn) => btn.addEventListener('click', () => setView(btn.dataset.step)));
}
async function loadCapabilities() {
  try {
    const [cap, status] = await Promise.all([jsonFetch('/api/system/capabilities'), jsonFetch('/api/adapters/status')]);
    setStatus($('backendState'), 'Control plane online', 'ok');
    const adapters = cap.adapters || {};
    const cuda = status.native_mjlab?.runtime?.interpreters?.some((item) => item.cuda_available);
    $('homeCapabilities').innerHTML = [['Control plane', true, 'online'], ['MJLab training', adapters.native_mjlab, adapters.native_mjlab ? 'ready' : 'configure runtime'], ['MuJoCo simulation', adapters.mujoco_simulation, adapters.mujoco_simulation ? 'ready' : 'missing dependency'], ['CUDA', cuda, cuda ? 'detected' : 'not detected']].map(([label, ok, value]) => `<div class="system-row"><span>${label}</span><strong class="${ok ? 'ok' : 'warn'}">${value}</strong></div>`).join('');
    renderNextStep(adapters, cuda);
  } catch (error) { setStatus($('backendState'), 'Control plane offline', 'error'); $('homeCapabilities').innerHTML = `<div class="empty-state">${error.message}</div>`; }
}
async function loadDemos() {
  // 内置 demo 卡：29 个预训练策略免训练即玩。点击跳转到 Sim2Sim 载入对应机器人。
  const host = $('homeDemos');
  if (!host) return;
  try {
    const payload = await jsonFetch('/api/pretrained/list');
    const models = payload.models || [];
    if (!models.length) {
      host.innerHTML = '<div class="empty-state">暂无预训练模型——运行生成脚本后即可免训练试玩。</div>';
      return;
    }
    host.innerHTML = models.slice(0, 8).map((model) => {
      const robot = String(model.robot || model.robot_id || 'unitree_go2');
      const rate = Number(model.success_rate ?? 0) * 100;
      const name = String(model.name || model.id || robot);
      return `<button class="demo-card" data-robot="${encodeURIComponent(robot)}" data-demo="${encodeURIComponent(model.id || '')}"><span class="demo-ico">🤖</span><strong>${escapeHtml(name)}</strong><span class="demo-robot">${escapeHtml(robot)}</span><span class="demo-metric">成功率 ${rate.toFixed(0)}%</span></button>`;
    }).join('');
    host.querySelectorAll('[data-robot]').forEach((card) => card.addEventListener('click', () => {
      const robot = decodeURIComponent(card.dataset.robot);
      setView('simulation');
      const frame = $('simBrowserFrame');
      if (frame) frame.src = `/web/sim2sim/index.html?embedded=1&robot=${encodeURIComponent(robot)}&view=workbench`;
    }));
  } catch (error) {
    host.innerHTML = `<div class="empty-state">预训练模型读取失败：${escapeHtml(error.message)}</div>`;
  }
}
async function loadRuns() {
  try { const payload = await jsonFetch('/api/training/list'); const tasks = payload.tasks || []; $('homeRuns').innerHTML = tasks.length ? tasks.slice(0, 8).map((item) => `<div class="run-row"><div><strong>${item.robot || '-'}</strong><small>${item.task_id}</small></div><span class="run-metric">${item.algorithm || 'PPO'}</span><span class="run-metric">${item.status}</span><span class="run-metric">${(Number(item.progress || 0) * 100).toFixed(1)}%</span></div>`).join('') : '<div class="empty-state">No training runs</div>'; } catch (error) { $('homeRuns').innerHTML = `<div class="empty-state">${error.message}</div>`; }
}
async function refreshModelPreview(source, format, valid) {
  const empty = $('modelPreviewEmpty');
  const urdfCanvas = $('urdfCanvas');
  if (urdfCanvas) urdfCanvas.hidden = true;
  if (!valid) { if (empty) empty.hidden = false; return; }
  if (source?.content && typeof window.renderRobotModel === 'function') {
    if (empty) empty.hidden = true;
    try {
      const summary = await window.renderRobotModel(source.content, { format, files: importedAssetFiles, filename: source.filename || '', baseUrl: source.baseUrl || '' });
      if ($('urdfCanvas')) $('urdfCanvas').hidden = false;
      jointMetadata = new Map((summary.joints || []).map((joint) => [joint.name, joint]));
      const mapped = selectedPreset?.contract?.joints?.actuated_joints || [];
      setPoseControls(Array.from(jointMetadata.keys()), Array.from(jointMetadata.keys()).map((name) => {
        const index = mapped.indexOf(name);
        return index >= 0 ? Number(robotPoseDraft[index] || 0) : 0;
      }));
      renderRobotEditor(selectedPreset);
      renderInertialTable();
      if ($('viewerFormat')) $('viewerFormat').textContent = `${String(format).toUpperCase()} · THREE.JS`;
      if ($('robotDiagnostics')) $('robotDiagnostics').textContent = `${summary.links || 0} links · ${(summary.joints || []).length} joints · ${summary.visualCount || 0} visual · ${summary.collisionCount || 0} collision · ${summary.inertialCount || 0} inertial${summary.missingMeshes ? ` · ${summary.missingMeshes} missing` : ''}`;
      return summary;
    } catch (error) {
      console.warn('Three.js robot preview unavailable', error);
      if (empty) { empty.textContent = `Three.js 加载失败：${error.message}`; empty.hidden = false; }
      throw error;
    }
  }
  if (empty) { empty.textContent = '模型源不可用'; empty.hidden = false; }
  throw new Error('Three.js viewer requires an inline URDF or MJCF source');
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
function startSimulation() {
  setView('simulation');
  const robot = selectedPreset?.robot_id || 'unitree_go2';
  const frame = $('simBrowserFrame');
  if (frame) frame.src = `/web/sim2sim/index.html?embedded=1&robot=${encodeURIComponent(robot)}&view=workbench`;
}
function bindEvents() {
  const simulation = $('simulation');
  const simulationFrame = $('simBrowserFrame');
  simulationFrame?.addEventListener('load', () => {
    syncSimulationFrame();
    setTimeout(syncSimulationFrame, 80);
  });
  window.addEventListener('resize', syncSimulationFrame);
  if (simulation && 'ResizeObserver' in window) new ResizeObserver(syncSimulationFrame).observe(simulation);
  window.addEventListener('robot-viewer-progress', (event) => {
    const detail = event.detail || {};
    if (!$('stageStatus') || !detail.total) return;
    $('stageStatus').textContent = detail.complete ? 'Three.js 视觉模型已加载' : `视觉网格后台加载 ${detail.loaded || 0}/${detail.total}`;
  });
  document.querySelectorAll('[data-step]').forEach((item) => item.addEventListener('click', () => setView(item.dataset.step)));
  // 首页资产库交互：导入 / 刷新 / 卡片动作（配置训练、去工作台、删除）。
  $('refreshAssetLibrary')?.addEventListener('click', refreshAssetLibrary);
  $('importAssetPackage')?.addEventListener('click', importAssetPackage);
  $('assetImportPath')?.addEventListener('keydown', (event) => { if (event.key === 'Enter') importAssetPackage(); });
  $('assetLibraryGrid')?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-asset-action]');
    if (!button) return;
    const robot = button.dataset.robot;
    if (button.dataset.assetAction === 'config') setView('config', { robot });
    else if (button.dataset.assetAction === 'workbench') { setView('robot'); selectRobotPackage(robot); }
    else if (button.dataset.assetAction === 'delete') deleteAssetPackage(robot);
  });
  $('preset').addEventListener('change', (event) => applyPreset(presets.find((item) => item.robot_id === event.target.value)));
  $('fitModel')?.addEventListener('click', () => window.fitRobotViewer?.());
  [['toggleVisual', 'visual'], ['toggleCollision', 'collision'], ['toggleInertial', 'inertial'], ['toggleCenterOfMass', 'centerOfMass'], ['toggleGrid', 'grid'], ['toggleAxes', 'axes'], ['toggleJointAxes', 'jointAxes']].forEach(([id, key]) => $(id)?.addEventListener('click', (event) => {
    const button = event.currentTarget;
    const pressed = button.getAttribute('aria-pressed') !== 'true';
    button.setAttribute('aria-pressed', String(pressed));
    button.classList.toggle('active', pressed);
    window.setRobotViewerVisibility?.({ [key]: pressed });
  }));
  $('modelFile').addEventListener('change', async (event) => {
    const files = Array.from(event.target.files || []);
    const model = files.find((file) => /\.(urdf|mjcf|xml)$/i.test(file.name));
    if (!model) { $('modelFileName').textContent = '文件夹中未找到 URDF/MJCF/XML 模型'; return; }
    $('modelFileName').textContent = `${files.length} 个本地资产 · ${model.webkitRelativePath || model.name}（右侧“导入到工作区”写入后端）`;
    window.importedAssetFiles = files.slice();
    selectedModelContent = await model.text();
    const format = $('format').value === 'auto' ? (/\.mjcf$/i.test(model.name) ? 'mjcf' : 'urdf') : $('format').value;
    try {
      const summary = await window.renderRobotModel(selectedModelContent, { format, files: window.importedAssetFiles, filename: model.webkitRelativePath || model.name, baseUrl: '' });
      jointMetadata = new Map((summary.joints || []).map((joint) => [joint.name, joint]));
      const mapped = selectedPreset?.contract?.joints?.actuated_joints || [];
      setPoseControls(Array.from(jointMetadata.keys()), Array.from(jointMetadata.keys()).map((name) => { const index = mapped.indexOf(name); return index >= 0 ? Number(robotPoseDraft[index] || 0) : 0; }));
      renderRobotEditor(selectedPreset);
      if ($('viewerFormat')) $('viewerFormat').textContent = `${String(format).toUpperCase()} · THREE.JS (本地)`;
      if ($('stageStatus')) $('stageStatus').textContent = `本地文件已即时渲染：${summary.links || 0} links · ${(summary.joints || []).length} joints`;
    } catch (error) { $('stageStatus').textContent = `本地渲染失败：${error.message}`; }
  });
  document.querySelectorAll('[data-robot-tab]').forEach((tab) => tab.addEventListener('click', () => { document.querySelectorAll('.robot-tab').forEach((x) => x.classList.toggle('active', x === tab)); document.querySelectorAll('[data-robot-pane]').forEach((pane) => pane.classList.toggle('active-pane', pane.dataset.robotPane === tab.dataset.robotTab)); }));
  $('runInspection')?.addEventListener('click', runPackageInspection);
  $('saveRobotPackage')?.addEventListener('click', saveRobotPackage); $('refreshRobotPackages')?.addEventListener('click', () => loadPresets(selectedPreset?.robot_id)); $('deleteRobotPackage')?.addEventListener('click', async () => { if (!selectedPreset || selectedPreset.source !== 'workspace') return; if (!confirm('删除当前机器人包？')) return; await jsonFetch('/api/project/packages/' + encodeURIComponent(selectedPreset.robot_id), { method: 'DELETE' }); selectedPreset = null; await loadPresets(); });
  $('validateBtn').addEventListener('click', validateModel); $('startSimulation')?.addEventListener('click', startSimulation); $('homeRefresh').addEventListener('click', () => { loadCapabilities(); loadRuns(); }); $('refreshApp').addEventListener('click', () => { loadCapabilities(); loadRuns(); }); $('copyContract').addEventListener('click', async () => navigator.clipboard?.writeText($('contractJson').value));
  window.addEventListener('resize', () => { drawChart(); });
}
document.addEventListener('DOMContentLoaded', async () => { buildRobotWorkspace(); resetValidationWorkspace(); bindEvents(); const hash = window.location.hash.slice(1); const initialView = ['home','robot','config','training','simulation','navmap','deploy','artifacts'].includes(hash) ? hash : 'home'; setView(initialView); try { await loadPresets(); resetValidationWorkspace(); } catch (error) { if ($('validationLog')) $('validationLog').textContent = `Initialization failed: ${error.message}`; } });
