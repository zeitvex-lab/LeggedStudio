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
          <button class="robot-tab" data-robot-tab="scaling" type="button">动作缩放</button>
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
          <div class="pane-note">按关节组编辑，全部写入契约真值（训练、浏览器仿真与工作台同源）：Kp / Kd / 力矩限幅 / 速度限幅 / 转子惯量 / 摩擦损耗。「未声明」= 契约未给该关节值，留空即不覆盖。</div>
          <div id="controlGainsGrid" class="control-gains-grid"></div>
          <details class="advanced-params" id="motorAdvanced">
            <summary>高级参数<span class="advanced-hint">T-N 曲线 / 执行器模型</span></summary>
            <div class="advanced-body">
              <div class="advanced-head"><span>T-N 曲线</span><span class="advanced-unit">rpm:Nm</span></div>
              <div class="pane-note">每部位一行，格式 <code>转速:扭矩</code>、逗号分隔（例 <code>0:60, 120:60, 188:0</code>）。**留空 = 不声明**；未修改即不写入。转速须升序、扭矩须非增。</div>
              <div id="tnCurveGrid" class="control-gains-grid"></div>
              <div class="advanced-foot">
                <label for="actuatorModel">执行器模型</label>
                <select id="actuatorModel">
                  <option value="ideal_pd">ideal_pd（现役；T-N 曲线不生效）</option>
                  <option value="dc_motor">dc_motor（按 T-N 曲线削顶）</option>
                </select>
                <span id="tnCurveMeta" class="pane-meta"></span>
              </div>
            </div>
          </details>
        </div>
        <div class="robot-pane" data-robot-pane="scaling">
          <div class="pane-note">动作缩放 = 策略输出（−1..1）× 该值 → 关节指令。标量是缺省，逐部位值覆盖它（契约真值 展开序 default &lt; 角色 &lt; 关节）。轮足机型的轮档位常与腿不同，改完点「保存配置」。</div>
          <div class="action-scale-toolbar"><label for="actionScaleScalar">标量缺省</label><input id="actionScaleScalar" type="number" min="0" step="0.01"><span id="actionScaleMeta" class="pane-meta"></span></div>
          <div id="actionScaleGrid" class="control-gains-grid"></div>
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
 * 真值契约的观测维度自洽值（Σcomponents.width）；v2 契约无 components 时返回 null。
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

// 契约枚举的中文口径（P=四足点足/W=轮足/B=双足/H=手部；S/M/L=按质量分档）。
const SIZE_LABEL = { S: '小型', M: '中型', L: '大型' };
const LOCOMOTION_LABEL = { P: '四足点足', W: '轮足', B: '双足', H: '手部' };

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
    // 族通用就绪：导入/选中一台包后，直接回答"能不能用族架构训、能训哪几档"
    const readiness = report.family_readiness || {};
    const readyBadge = readiness.verdict === 'ready' ? '✅' : (readiness.verdict === 'not_ready' ? '❌' : '⚠');
    const blocked = (readiness.checks || []).filter((item) => item.status !== 'pass');
    const terrains = (readiness.trainable_terrain_profiles || []).join(' / ') || '（无可训档）';
    const readinessBlock = `
      <div class="inspection-card status-${readiness.verdict === 'ready' ? 'pass' : 'fail'}">
        <div class="inspection-card-head"><span class="inspection-badge">${readyBadge}</span><strong>族通用就绪</strong>
          <span class="inspection-summary">${escapeHtml(readiness.verdict === 'ready'
            ? `可用 ${readiness.family || '本族'} 通用架构训练；可训地形档：${terrains}`
            : `未就绪${blocked.length ? '：' + blocked.map((item) => item.id).join('、') : ''}`)}</span></div>
        ${blocked.length ? `<div class="inspection-diff">${blocked.map((item) => `${INSPECTION_BADGES[item.status] || '·'} ${escapeHtml(item.id)}：${escapeHtml(item.summary)}`).join('<br>')}</div>` : ''}
      </div>`;
    container.innerHTML = `<div class="inspection-overall status-${escapeHtml(report.overall)}">整体：${INSPECTION_BADGES[report.overall] || '·'} ${escapeHtml(report.overall)}</div>${readinessBlock}${cards}`;
  } catch (error) {
    container.innerHTML = `<div class="empty-state">体检失败：${escapeHtml(error.message)}——确认后端已启动后重试</div>`;
  }
}

// D2：reindex_from_model 可见可比对——契约真值 里"模型关节序 → 动作序"的重排
// 数组与当前动作映射并排展示；长度不一致或非排列时给出红字提示。
function renderReindexCompare(preset, mappedJoints) {
  const host = $('reindexCompare');
  if (!host) return;
  if (!preset?.robot_id) { host.hidden = true; return; }
  jsonFetch(`/api/robots/packages/${encodeURIComponent(preset.robot_id)}/contract-v3`).then((payload) => {
    const reindex = payload?.contract?.action?.reindex_from_model;
    if (!Array.isArray(reindex) || !reindex.length) {
      host.innerHTML = '契约真值 未声明 <code>reindex_from_model</code>——动作序与模型关节序一致，无需重排。';
      host.hidden = false;
      return;
    }
    const isPermutation = reindex.length === new Set(reindex).size
      && reindex.every((v) => Number.isInteger(v) && v >= 0 && v < reindex.length);
    const lengthNote = mappedJoints.length === reindex.length
      ? `与当前动作数 ${mappedJoints.length} 一致`
      : `<b class="text-danger">长度不一致（动作 ${mappedJoints.length} vs reindex ${reindex.length}）——改完映射记得保存</b>`;
    const permNote = isPermutation ? '是有效排列' : '<b class="text-danger">不是有效排列（索引越界或重复）</b>';
    host.innerHTML = `<b>reindex_from_model</b>（模型关节序 → 动作序）：${reindex.map((v, i) => `${i}→${v}`).join(' · ')}<br>${lengthNote} · ${permNote}`;
    host.hidden = false;
  }).catch(() => { host.hidden = true; });
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
    renderReindexCompare(preset, mappedJoints);
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
  // D8：物理量一律取契约真值 派生视图（preset.physics，与浏览器仿真载荷同源同形状）。
  // 此前读 preset.simulation_config.stiffness/damping/torque_limits —— B3 已把这组
  // 重复键从 sim config 移除（物理真值只留契约真值），继续读会整片显示空白；
  // 而 armature 在这条链路上从来读不到（也从未生效过）。
  const physics = preset?.physics || {};
  const simConfig = preset?.simulation_config || {};
  const gainsSource = {
    stiffness: physics.stiffness || control.stiffness || null,
    damping: physics.damping || control.damping || null,
    torque_limits: physics.torque_limits || control.torque_limits || null,
    // D9：速度限幅也回到契约真值（此前读 sim config 的 velocity_limits，而 14 包
    // 实测都没有这个键 → 输入框永远空白，用户改了还只写进第二个家）。
    velocity_limits: physics.velocity_limits || control.velocity_limits || null,
    // 常量表（转子惯量 / 摩擦损耗）：键为逐关节 + __default__ 兜底
    armature: physics.armature || null,
    friction_loss: physics.frictionloss || null,
    physics_source: physics.source || null,
  };
  renderActionScaleGrid(preset?.action_scale || null, mappedJoints);
  renderTnCurveGrid(preset?.t_n_curve || null, mappedJoints);
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
  if (Number.isFinite(jointWide)) return jointWide;
  // 契约常量表（armature / frictionloss）用 __default__ 作模型 default 层兜底，
  // 与后端 physics_binding 的展开语义一致（default < by_role < by_joint）。
  const fallback = Number(map.__default__);
  return Number.isFinite(fallback) ? fallback : '';
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
    // D8：契约真值 的物理常量（此前不可见、且 Python 侧因大小写不匹配从未生效）
    { key: 'armature', label: '转子惯量', step: '0.001' },
    { key: 'friction_loss', label: '摩擦损耗', step: '0.01' },
  ];
  const jointsBySegment = {};
  for (const joint of mappedJoints) (jointsBySegment[jointToSegment[joint]] ||= []).push(joint);
  const cols = 'minmax(84px,1.3fr) repeat(6,minmax(0,1fr))';
  // Velocity-driven segments (wheels) have no stiffness: fill Kp with 0.
  const modeFor = (segment, joints) => {
    if (motorModes[segment]) return String(motorModes[segment]).toLowerCase();
    for (const joint of joints) if (motorModes[joint]) return String(motorModes[joint]).toLowerCase();
    return segment.includes('wheel') ? 'velocity' : 'position';
  };
  const header = `<div class="gains-row gains-head" style="grid-template-columns:${cols}"><span>部位</span><span>Kp</span><span>Kd</span><span>力矩限幅</span><span>速度限幅</span><span>转子惯量</span><span>摩擦损耗</span></div>`;
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
  const armature = collect('armature');
  const frictionLoss = collect('friction_loss');
  return {
    control: {
      ...(control || {}),
      ...(Object.keys(stiffness).length ? { stiffness } : {}),
      ...(Object.keys(damping).length ? { damping } : {}),
      ...(Object.keys(torqueLimits).length ? { torque_limits: torqueLimits } : {}),
      ...(Object.keys(velocityLimits).length ? { velocity_limits: velocityLimits } : {}),
      // D8：这两项只写契约真值（保存链把它们映射进 actuator_profile.by_role/by_joint），
      // 不进 simulation —— B3 已把物理键从 sim config 移除，写回去等于开倒车。
      ...(Object.keys(armature).length ? { armature } : {}),
      ...(Object.keys(frictionLoss).length ? { friction_loss: frictionLoss } : {}),
    },
    simulation: {
      ...(Object.keys(stiffness).length ? { stiffness } : {}),
      ...(Object.keys(damping).length ? { damping } : {}),
      ...(Object.keys(torqueLimits).length ? { torque_limits: torqueLimits } : {}),
      ...(Object.keys(velocityLimits).length ? { velocity_limits: velocityLimits } : {}),
    },
  };
}

// ---- D10「动作缩放」卡片（action_scale）----------------------------------------
// 数据源：preset.action_scale = contracts.physics_binding.payload_action_scale_view
// 的输出（与浏览器载荷**同一实现**）。标量走契约 `action.action_scale`（缺省层），
// 逐部位/逐关节走 `actuator_profile`（展开序 default < 角色 < 关节）。
// 存在的理由：轮足机型的轮档位远大于腿（go2w 实测：UniLab 默认 10 / rough 5 /
// 官方部署 35），只在别处改必然漂移——这里让它成为可编辑的一等参数。
function renderActionScaleGrid(actionView, mappedJoints) {
  const grid = $('actionScaleGrid');
  if (!grid) return;
  const scalarInput = $('actionScaleScalar');
  const meta = $('actionScaleMeta');
  const scalar = actionView ? Number(actionView.action_scale) : NaN;
  if (scalarInput) scalarInput.value = Number.isFinite(scalar) ? scalar : '';
  if (!mappedJoints.length) {
    grid.innerHTML = '<div class="empty-state">Contract 未声明动作关节</div>';
    if (meta) meta.textContent = '';
    return;
  }
  const { segments, jointToSegment } = inferMotorSegments(mappedJoints);
  const merged = { ...(actionView?.action_scale_by_role || {}), ...(actionView?.action_scale_by_joint || {}) };
  const jointsBySegment = {};
  for (const joint of mappedJoints) (jointsBySegment[jointToSegment[joint]] ||= []).push(joint);
  const cols = 'minmax(84px,1.3fr) repeat(1,minmax(0,1fr))';
  const header = `<div class="gains-row gains-head" style="grid-template-columns:${cols}"><span>部位</span><span>动作缩放</span></div>`;
  grid.innerHTML = header + segments.map((segment) => {
    const joints = jointsBySegment[segment] || [];
    const value = resolveGainValue(merged, segment, joints);
    const cell = `<input data-action-scale-segment="${escapeHtml(segment)}" type="number" min="0" step="0.01" value="${value}">`;
    return `<div class="gains-row" style="grid-template-columns:${cols}" title="${escapeHtml(joints.join(', '))}"><span>${escapeHtml(segment)}</span>${cell}</div>`;
  }).join('');
  if (meta) {
    meta.textContent = !actionView
      ? '契约未声明动作缩放，仅显示标量缺省'
      : (actionView.wheel_scale_declared ? '轮组档位已单独声明' : '轮组档位未单独声明（沿用标量）');
  }
}

function collectActionScale(mappedJoints) {
  const byJoint = {};
  document.querySelectorAll('[data-action-scale-segment]').forEach((input) => {
    if (input.value === '') return;
    const value = Number(input.value);
    if (!Number.isFinite(value)) return;
    const segment = input.dataset.actionScaleSegment;
    mappedJoints.filter((joint) => inferMotorSegments([joint]).segments[0] === segment)
      .forEach((joint) => { byJoint[joint] = value; });
  });
  const input = $('actionScaleScalar');
  const scalar = input && input.value !== '' && Number.isFinite(Number(input.value)) ? Number(input.value) : null;
  return { by_joint: byJoint, scalar };
}

// ---- P1「高级参数」：T-N 曲线（默认收起，不修改不起作用）--------------------
// 数据源：preset.t_n_curve = contracts.physics_binding.t_n_curve_facts（契约真值 单一真值）。
// 语义：**声明 ≠ 生效**——只有 actuator_model=dc_motor 时 T-N 曲线才被消费；ideal_pd（缺省）
// 一律忽略。面板只在"用户真的改过某一行"时才把它提交上去（空串 = 显式清除）。
function resolveTextValue(map, segment, joints) {
  if (!map || typeof map !== 'object') return '';
  for (const joint of joints) {
    if (map[joint]) return String(map[joint]);
  }
  if (map[segment]) return String(map[segment]);
  if (map.joint) return String(map.joint);
  return map.__default__ ? String(map.__default__) : '';
}

function renderTnCurveGrid(tnCurveView, mappedJoints) {
  const grid = $('tnCurveGrid');
  if (!grid) return;
  const meta = $('tnCurveMeta');
  const modelSelect = $('actuatorModel');
  const view = tnCurveView || {};
  if (modelSelect) {
    modelSelect.value = view.actuator_model === 'dc_motor' ? 'dc_motor' : 'ideal_pd';
    modelSelect.dataset.tnCurveOriginal = modelSelect.value;
  }
  if (!mappedJoints.length) {
    grid.innerHTML = '<div class="empty-state">Contract 未声明动作关节</div>';
    if (meta) meta.textContent = '';
    return;
  }
  const { segments, jointToSegment } = inferMotorSegments(mappedJoints);
  const merged = { ...(view.text_by_role || {}), ...(view.text_by_joint || {}) };
  const jointsBySegment = {};
  for (const joint of mappedJoints) (jointsBySegment[jointToSegment[joint]] ||= []).push(joint);
  const cols = 'minmax(84px,1.3fr) repeat(1,minmax(0,1fr))';
  const header = `<div class="gains-row gains-head" style="grid-template-columns:${cols}"><span>部位</span><span>rpm:Nm</span></div>`;
  grid.innerHTML = header + segments.map((segment) => {
    const joints = jointsBySegment[segment] || [];
    const text = resolveTextValue(merged, segment, joints);
    const cell = `<input data-tn-curve-segment="${escapeHtml(segment)}" data-t_n_curve-original="${escapeHtml(text)}" type="text" placeholder="例如 0:60, 120:60, 188:0" value="${escapeHtml(text)}">`;
    return `<div class="gains-row" style="grid-template-columns:${cols}" title="${escapeHtml(joints.join(', '))}"><span>${escapeHtml(segment)}</span>${cell}</div>`;
  }).join('');
  // 派生提示：把"填了会得到什么"直接显示出来（mjlab DC 模型需要的是两个标量）
  const derived = Object.entries(view.derived || {});
  if (meta) {
    if (view.error) {
      meta.textContent = `T-N 曲线非法：${view.error}`;
    } else if (!view.declared) {
      meta.textContent = '未声明 T-N 曲线（不改动 = 现役 ideal_pd 行为）';
    } else {
      const shown = derived.slice(0, 3).map(([key, value]) => (
        `${key}: 堵转 ${value.saturation_effort} Nm / 空载 ${value.no_load_rpm.toFixed(0)} rpm（${value.velocity_limit_rad_s.toFixed(1)} rad/s）`
      ));
      meta.textContent = `${view.actuator_model === 'dc_motor' ? '已启用' : '已声明但未启用（ideal_pd）'}· ${shown.join('；')}`;
    }
  }
}

function collectTnCurvePayload() {
  // 只提交"用户改过"的行与开关：未修改 → 不出现，后端就不会动契约（"不修改不起作用"）。
  const t_n_curve = {};
  document.querySelectorAll('[data-tn-curve-segment]').forEach((input) => {
    const text = String(input.value || '').trim();
    const original = String(input.dataset.tnCurveOriginal || '').trim();
    if (text === original) return;         // 没动过
    t_n_curve[input.dataset.tnCurveSegment] = text;   // 空串 = 清除该部位声明
  });
  const modelSelect = $('actuatorModel');
  const model = modelSelect && modelSelect.value !== modelSelect.dataset.tnCurveOriginal
    ? modelSelect.value
    : null;
  return { t_n_curve, actuator_model: model };
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
    // D10：「动作缩放」卡片——标量写 v2 的 action.action_scale（后端同步进 v3
    // action.action_scale），逐关节值随 control.action_scale 进 v3 actuator_profile。
    const scales = collectActionScale(joints.length ? joints : (contract.joints?.actuated_joints || []));
    if (Object.keys(scales.by_joint).length) contract.control = { ...contract.control, action_scale: scales.by_joint };
    if (scales.scalar != null) contract.action = { ...contract.action, action_scale: scales.scalar };
    // P1 高级参数：T-N 曲线走独立顶层键（只有契约真值 语义）；执行器模型是契约 control 字段。
    // 两者都只在"用户改过"时出现——默认保存不会写入任何东西。
    const advanced = collectTnCurvePayload();
    if (advanced.actuator_model) contract.control = { ...contract.control, actuator_model: advanced.actuator_model };
    // P2：不再提交 control_hz/physics_hz/decimation——它们是契约真值 的字段，而这里手上只有
    // v2 契约的旧值（go2 实测 v2=1000/20 vs v3=500/10）；送上去只会把 v3 改回旧值。
    // 后端也已拒绝从这条链改写控制三件套。
    const result = await jsonFetch(`/api/robots/packages/${encodeURIComponent(selectedPreset.robot_id)}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ contract, simulation: { default_pose: contract.joints.default_pose, ...gains.simulation }, ...(Object.keys(advanced.t_n_curve).length ? { t_n_curve: advanced.t_n_curve } : {}) }) });
    $('contractJson').value = JSON.stringify(result.contract || contract, null, 2); setBadge($('robotState'), '已保存', 'ok'); $('robotDiagnostics').textContent = '配置已写入本地机器人包'; await loadPresets(selectedPreset.robot_id);
  } catch (error) { $('robotDiagnostics').textContent = `保存失败：${error.message}`; setBadge($('robotState'), '保存失败', 'error'); }
}


/**
 * JSON 请求 —— **委托** `web/shared/api.js`（HTTP 错误 / 超时 / JSON 解析的唯一实现）。
 *
 * 这里曾自带一份：与 training-common.js、workbench.js 各写一遍意味着"超时"和
 * "非 JSON 响应"只在其中一处被处理。保留本函数的签名与"空响应回 `{}`"的兜底语义。
 */
async function jsonFetch(path, options = {}) {
  const payload = await LSApi.fetchJson(`${API}${path}`, options);
  return payload === null ? {} : payload;
}
function setView(name, options = {}) {
  // Inline pages hosted inside frames so the sidebar/workflow shell stays
  // identical across the functional areas. 资产库已原生并入首页
  // （#assetLibraryGrid），不再有独立 assets 视图。
  const framePages = {
    navmap: ['navMapFrame', 'advanced_sim.html?v=0.46.0&embedded=1'],
    deploy: ['deployFrame', 'deploy.html?v=0.44.0&embedded=1'],
    artifacts: ['artifactsFrame', 'artifacts.html?v=0.44.0&embedded=1'],
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
    // C2：带 task_id 时直接打开该 Run 的档案页（training_monitor）。
    const page = name === 'config'
      ? `training_create.html?v=0.44.0&embedded=1&robot=${encodeURIComponent(robot)}`
      : options.task_id
        ? `training_monitor.html?v=0.44.0&embedded=1&task_id=${encodeURIComponent(options.task_id)}`
        : `training_list.html?v=0.44.0&embedded=1`;
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
      // 保留裸 fetch：读的是模型源文件（URDF/MJCF）的**原始文本**而非 JSON——这不是
      // LSApi（JSON 请求唯一实现）的职责边界，接过去反而要绕过它的非 JSON 报错。
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
      // 同上：模型 XML 是原始文本（非 JSON），保持裸 fetch。
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
    // 同上：模型 XML 是原始文本（非 JSON），保持裸 fetch。
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
      <span class="asset-meta" title="形态口径：S/M/L=小型/中型/大型；P=四足点足 W=轮足 B=双足 H=手部">${Number(item.dof || 0)} 自由度 · ${Number(item.mass_kg || 0).toFixed(2)} kg · ${escapeHtml(SIZE_LABEL[item.size_class] || item.size_class || '-')} · ${escapeHtml(LOCOMOTION_LABEL[item.locomotion_type] || item.locomotion_type || '-')}</span>
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
  // 确认走共享反馈（LSFeedback.confirm）：危险动作红色确认键 + 初始焦点在「取消」；
  // 原生 confirm 会阻塞整个页面（轮询/渲染全停），且样式与措辞无从收敛。
  if (!robotId || !(await LSFeedback.confirm(`确认删除工作区包 ${robotId}？（内置包不受影响）`, { danger: true }))) return;
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
// C4：下一步建议的输入状态（体检层 + 项目状态），由 loadCapabilities / loadRuns
// 各自更新后统一渲染——建议随状态变化，而不是罗列功能。
const nextStepState = { adapters: {}, cuda: false, layers: null, runs: [] };
function renderNextStep() {
  const body = $('homeNextStepBody');
  if (!body) return;
  const { adapters, cuda, layers, runs } = nextStepState;
  const steps = [];
  // C3：与 L0–L6 体检同源——第一个失败层直接给出"哪一层、怎么办"
  const failing = (layers?.layers || []).find((layer) => layer.status === 'fail');
  if (failing) {
    steps.push({ label: `修复体检 ${failing.id}（${failing.name}）`, detail: failing.action });
  }
  if (!adapters.native_mjlab) {
    steps.push({ label: '配置运行环境', detail: 'MJLab 训练栈未就绪——请在桌面端「系统设置」中配置运行时与 PyTorch 镜像。' });
  }
  if (!adapters.mujoco_simulation) {
    steps.push({ btn: 'simulation', label: '检查仿真依赖', detail: 'MuJoCo 仿真依赖缺失——修复后再做基础仿真。' });
  }
  // L0 三态（cuda / cpu-only / unavailable）：处置措辞来自体检层自身，避免前端
  // 再复述一遍设备策略导致两边漂移。
  const l0 = (layers?.layers || []).find((layer) => layer.id === 'L0');
  if (!cuda) {
    const cpuOnly = l0?.mode === 'cpu-only';
    steps.push({
      label: cpuOnly ? '无 GPU（CPU 训练链路就绪）' : '无 GPU 且训练栈未供应',
      detail: l0?.action || 'CPU 可以跑通仿真与最小训练冒烟，适合验证流程；正式训练建议使用 NVIDIA GPU（吞吐高约一个量级）。可在桌面端「系统设置 · 计算设备」切换 CPU/GPU profile。',
    });
  }
  if (steps.length) {
    body.innerHTML = steps.map((item) => `<div class="next-step-item"><div><strong>${item.label}</strong><span>${item.detail}</span></div>${item.btn ? `<button class="button small" data-step="${item.btn}">去处理</button>` : ''}</div>`).join('');
    body.querySelectorAll('[data-step]').forEach((btn) => btn.addEventListener('click', () => setView(btn.dataset.step)));
    return;
  }
  // C4：环境就绪后按**项目状态**给下一步（有无训练记录 / 运行中 / 最近失败）。
  const isRunning = (item) => /run|pend|sched/i.test(String(item.status || ''));
  const isFailed = (item) => /fail|error|crash|cancel/i.test(String(item.status || ''));
  if (!runs.length) {
    body.innerHTML = `<div class="next-step-item ok"><div><strong>第一次训练</strong><span>运行时与仿真均已就绪——选一个机器人资产进入训练配置（会先跑 64 envs 冒烟门），或先试玩内置 demo。</span></div><button class="button primary small" data-step="config">配置训练</button><button class="button ghost small" data-step="simulation">试玩 Demo</button></div>`;
  } else if (runs.some(isRunning)) {
    body.innerHTML = `<div class="next-step-item ok"><div><strong>训练进行中</strong><span>有 ${runs.filter(isRunning).length} 个任务在跑——打开 Run 档案看实时指标与日志。</span></div><button class="button primary small" data-step="training">查看 Run 档案</button></div>`;
  } else if (isFailed(runs[0])) {
    body.innerHTML = `<div class="next-step-item"><div><strong>最近一次训练异常</strong><span>「${escapeHtml(runs[0].robot || '')} ${escapeHtml(runs[0].task_id || '')}」状态 ${escapeHtml(runs[0].status)}——打开 Run 档案看失败原因与日志。</span></div><button class="button primary small" data-step="training">排查 Run 档案</button></div>`;
  } else {
    body.innerHTML = `<div class="next-step-item ok"><div><strong>从产物到部署</strong><span>最近的训练已正常结束——在策略档案里查看/导出产物，或继续发起下一次训练。</span></div><button class="button primary small" data-step="artifacts">策略档案</button><button class="button ghost small" data-step="config">再训一次</button></div>`;
  }
  body.querySelectorAll('[data-step]').forEach((btn) => btn.addEventListener('click', () => setView(btn.dataset.step)));
}
async function loadCapabilities() {
  try {
    // C3：体检数据与 L0–L6 六层体检同源（/api/health/layers）；失败时静默降级，
    // 不影响原有四行系统状态。
    const [cap, status, layers] = await Promise.all([
      jsonFetch('/api/system/capabilities'),
      jsonFetch('/api/adapters/status'),
      jsonFetch('/api/health/layers').catch(() => null),
    ]);
    setStatus($('backendState'), 'Control plane online', 'ok');
    const adapters = cap.adapters || {};
    const cuda = status.native_mjlab?.runtime?.interpreters?.some((item) => item.cuda_available);
    const systemRows = [['Control plane', true, 'online'], ['MJLab training', adapters.native_mjlab, adapters.native_mjlab ? 'ready' : 'configure runtime'], ['MuJoCo simulation', adapters.mujoco_simulation, adapters.mujoco_simulation ? 'ready' : 'missing dependency'], ['CUDA', cuda, cuda ? 'detected' : 'not detected']].map(([label, ok, value]) => `<div class="system-row"><span>${label}</span><strong class="${ok ? 'ok' : 'warn'}">${value}</strong></div>`).join('');
    const layerRows = (layers?.layers || []).map((layer) => {
      const cls = layer.status === 'pass' ? 'ok' : layer.status === 'fail' ? 'error' : 'warn';
      const label = layer.status === 'pass' ? '通过' : layer.status === 'fail' ? '异常' : layer.status === 'warn' ? '注意' : layer.status === 'blocked' ? '受阻' : '未执行';
      return `<div class="system-row" title="${escapeHtml(layer.reason)}"><span>${layer.id} ${layer.name}</span><strong class="${cls}">${label}</strong></div>`;
    }).join('');
    $('homeCapabilities').innerHTML = systemRows + layerRows;
    Object.assign(nextStepState, { adapters, cuda, layers });
    renderNextStep();
  } catch (error) { setStatus($('backendState'), 'Control plane offline', 'error'); $('homeCapabilities').innerHTML = `<div class="empty-state">${error.message}</div>`; }
}
async function loadDemos() {
  // 内置 demo 卡：预训练策略免训练即玩。数据源 = /api/health/demo-cards
  // （扫各包 simulation/config.json 的 policies + demo_policies，无 per-robot 分支），
  // 卡片携带 play_url，点击直接带 policy 进基础仿真。
  const host = $('homeDemos');
  if (!host) return;
  try {
    const payload = await jsonFetch('/api/health/demo-cards');
    const cards = payload.cards || [];
    if (!cards.length) {
      host.innerHTML = '<div class="empty-state">暂无内置策略——导入机器人包或导出策略后即可免训练试玩。</div>';
      return;
    }
    host.innerHTML = cards.slice(0, 8).map((card) => {
      const robot = String(card.robot_id || 'unitree_go2');
      const name = String(card.label || card.id || robot);
      const dims = card.obs_dim ? `obs ${card.obs_dim} · act ${card.action_dim ?? '-'}` : '内置策略';
      const playUrl = String(card.play_url || `/web/sim2sim/index.html?robot=${encodeURIComponent(robot)}`);
      return `<button class="demo-card" data-play="${encodeURIComponent(playUrl)}"><span class="demo-ico">🤖</span><strong>${escapeHtml(name)}</strong><span class="demo-robot">${escapeHtml(robot)}</span><span class="demo-metric">${escapeHtml(dims)}</span></button>`;
    }).join('');
    host.querySelectorAll('[data-play]').forEach((card) => card.addEventListener('click', () => {
      const playUrl = decodeURIComponent(card.dataset.play);
      setView('simulation');
      const frame = $('simBrowserFrame');
      const separator = playUrl.includes('?') ? '&' : '?';
      if (frame) frame.src = `${playUrl}${separator}embedded=1&view=workbench`;
    }));
  } catch (error) {
    host.innerHTML = `<div class="empty-state">内置策略读取失败：${escapeHtml(error.message)}</div>`;
  }
}
const RUN_STATUS_LABELS = { pending: '等待中', running: '运行中', completed: '已完成', failed: '失败', stopped: '已停止' };
/** 与 training-common.js 的 statusInfo 同口径：旧 worker 会写 train_completed 这类状态名。 */
function runStatusLabel(status) {
  const key = String(status || '').toLowerCase();
  if (RUN_STATUS_LABELS[key]) return RUN_STATUS_LABELS[key];
  if (key.endsWith('completed')) return '已完成';
  if (key.includes('fail') || key.includes('error')) return '失败';
  if (key.includes('stop') || key.includes('cancel')) return '已停止';
  return String(status || '-');
}
async function loadRuns() {
  try {
    const payload = await jsonFetch('/api/training/list');
    const tasks = payload.tasks || [];
    // C4：runs 也是下一步建议的输入。
    Object.assign(nextStepState, { runs: tasks });
    renderNextStep();
    // C2：每行可点——一键跳到该 Run 的档案页（training_monitor）。
    $('homeRuns').innerHTML = tasks.length ? tasks.slice(0, 8).map((item) => `<button class="run-row" type="button" data-run-id="${escapeHtml(item.task_id || '')}" title="打开 Run 档案"><div><strong>${escapeHtml(item.robot || '-')}</strong><small>${escapeHtml(item.task_id || '')}</small></div><span class="run-metric">${escapeHtml(item.algorithm || 'PPO')}</span><span class="run-metric">${escapeHtml(runStatusLabel(item.status))}</span><span class="run-metric">${(Number(item.progress || 0) * 100).toFixed(1)}%</span></button>`).join('') : '<div class="empty-state">暂无训练任务</div>';
    $('homeRuns').querySelectorAll('[data-run-id]').forEach((row) => row.addEventListener('click', () => {
      if (!row.dataset.runId) return;
      setView('training', { task_id: row.dataset.runId });
    }));
  } catch (error) { $('homeRuns').innerHTML = `<div class="empty-state">${error.message}</div>`; }
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
  $('saveRobotPackage')?.addEventListener('click', saveRobotPackage); $('refreshRobotPackages')?.addEventListener('click', () => loadPresets(selectedPreset?.robot_id)); $('deleteRobotPackage')?.addEventListener('click', async () => { if (!selectedPreset || selectedPreset.source !== 'workspace') return; if (!(await LSFeedback.confirm('删除当前机器人包？', { danger: true }))) return; await jsonFetch('/api/project/packages/' + encodeURIComponent(selectedPreset.robot_id), { method: 'DELETE' }); selectedPreset = null; await loadPresets(); });
  $('validateBtn').addEventListener('click', validateModel); $('startSimulation')?.addEventListener('click', startSimulation); $('homeRefresh').addEventListener('click', () => { loadCapabilities(); loadRuns(); }); $('refreshApp').addEventListener('click', () => { loadCapabilities(); loadRuns(); }); $('copyContract').addEventListener('click', async () => navigator.clipboard?.writeText($('contractJson').value));
}
document.addEventListener('DOMContentLoaded', async () => { buildRobotWorkspace(); resetValidationWorkspace(); bindEvents(); const hash = window.location.hash.slice(1); const initialView = ['home','robot','config','training','simulation','navmap','deploy','artifacts'].includes(hash) ? hash : 'home'; setView(initialView); try { await loadPresets(); resetValidationWorkspace(); } catch (error) { if ($('validationLog')) $('validationLog').textContent = `Initialization failed: ${error.message}`; } });
