/**
 * Legged Studio Dashboard V2 - JavaScript
 * 修复：连接到图形化训练界面
 */

// Same-origin first (served by the control plane at any port); fall back to the
// well-known desktop port only for file:// usage — matches training-common.js.
const API_BASE = (location.protocol === 'http:' || location.protocol === 'https:')
  ? location.origin
  : 'http://127.0.0.1:8765';

// ========== 初始化 ==========
document.addEventListener('DOMContentLoaded', () => {
  console.log('[Dashboard] Initializing...');
  loadSystemStatus();
  loadQuickDemos();
  loadTrainingStats();
  loadRecentTrainings();
  loadPretrainedModels();
});

// ========== 系统状态 ==========
// U11：三行系统状态的值一律来自 /api/system/environment 的真值字段
// （control_plane.python_version / gpu.mode / adapters.mjlab.version），
// 不再硬编码占位；任一字段拿不到时如实显示「未检测」。
const UNKNOWN_TEXT = '未检测';

function setSystemRow(valueId, statusId, text, dot) {
  const valueEl = document.getElementById(valueId);
  if (!valueEl) return;
  const known = text != null && String(text).trim() !== '';
  valueEl.textContent = known ? String(text) : UNKNOWN_TEXT;

  const statusEl = document.getElementById(statusId);
  if (!statusEl) return;
  statusEl.className = 'system-status' + (known && dot ? ' success' : '');
  statusEl.textContent = known && dot ? '✓' : '·';
}

async function loadSystemStatus() {
  try {
    const response = await fetch(`${API_BASE}/api/system/environment`);
    const data = await response.json();

    const badge = document.getElementById('systemBadge');
    const hint = document.getElementById('systemHint');

    if (data.control_plane && data.control_plane.status === 'running') {
      badge.textContent = '运行中';
      badge.className = 'status-badge running';
      hint.textContent = '所有系统就绪';
    }

    if (data.control_plane && data.control_plane.python_version) {
      setSystemRow('pythonVersion', 'pythonStatus',
        data.control_plane.python_version, data.control_plane.python_target_match !== false);
    } else {
      setSystemRow('pythonVersion', 'pythonStatus', null, false);
    }

    // GPU：mode 与 /api/health/layers 的 L0 同源（gpu_probe 三态）。
    // 行标签已写「CUDA / GPU」，值只放设备名，避免窄面板里挤成长串。
    const gpu = data.gpu || {};
    let cudaText = null;
    if (gpu.mode === 'cuda' && gpu.devices && gpu.devices.length > 0) {
      cudaText = gpu.devices[0].name || 'CUDA';
    } else if (gpu.mode === 'cpu-only') {
      cudaText = '无 GPU（CPU 训练链路可用）';
    } else if (gpu.mode === 'unavailable') {
      cudaText = '不可用';
    }
    setSystemRow('cudaVersion', 'cudaStatus', cudaText, gpu.mode === 'cuda');

    // MJLab：适配器 venv 的 dist-info 实装版本。
    const mjlab = (data.adapters && data.adapters.mjlab) || {};
    setSystemRow('mjlabVersion', 'mjlabStatus', mjlab.version || null, mjlab.status === 'installed');

  } catch (error) {
    // 整个端点不可达时：三行全部如实「未检测」，不编值。
    console.error('[Dashboard] Failed to load system status:', error);
    setSystemRow('pythonVersion', 'pythonStatus', null, false);
    setSystemRow('cudaVersion', 'cudaStatus', null, false);
    setSystemRow('mjlabVersion', 'mjlabStatus', null, false);
  }
}

// ========== 预训练模型 ==========
async function loadPretrainedModels() {
  try {
    const response = await fetch(`${API_BASE}/api/pretrained/list`);
    const data = await response.json();

    if (data.success && data.models && data.models.length > 0) {
      document.getElementById('pretrainedModels').textContent = data.count;
    }

  } catch (error) {
    console.error('[Dashboard] Failed to load pretrained models:', error);
  }
}

// ========== 训练统计 ==========
async function loadTrainingStats() {
  try {
    const response = await fetch(`${API_BASE}/api/training/list`);
    const data = await response.json();

    const tasks = data.tasks || [];
    const total = tasks.length;
    const running = tasks.filter(t => t.status === 'running').length;
    const completed = tasks.filter(t => t.status === 'completed').length;

    document.getElementById('totalTrainings').textContent = total;
    document.getElementById('runningTrainings').textContent = running;
    document.getElementById('completedTrainings').textContent = completed;

  } catch (error) {
    console.error('[Dashboard] Failed to load training stats:', error);
  }
}

// ========== 最近训练 ==========
async function loadRecentTrainings() {
  try {
    const response = await fetch(`${API_BASE}/api/training/list`);
    const data = await response.json();

    const listEl = document.getElementById('trainingList');

    if (!data.tasks || data.tasks.length === 0) {
      listEl.innerHTML = `
        <div class="empty-state">
          <p>暂无训练任务</p>
          <button class="btn primary" onclick="openTraining()">开始第一个训练</button>
        </div>
      `;
      return;
    }

    listEl.innerHTML = data.tasks.slice(0, 5).map(t => `
      <div class="training-item" style="display: flex; justify-content: space-between; align-items: center; padding: 16px; background: var(--surface-raised); border-radius: var(--radius); margin-bottom: 12px;">
        <div>
          <strong>${t.task_id}</strong><br>
          <span style="color: var(--muted); font-size: 12px;">${t.status} - ${t.robot || 'Unknown'}</span>
        </div>
        <div>
          <button class="btn" onclick="viewTraining('${t.task_id}')">查看详情</button>
        </div>
      </div>
    `).join('');

  } catch (error) {
    console.error('[Dashboard] Failed to load recent trainings:', error);
  }
}

// ========== 刷新仪表盘 ==========
function refreshDashboard() {
  console.log('[Dashboard] Refreshing...');
  loadSystemStatus();
  loadQuickDemos();
  loadTrainingStats();
  loadRecentTrainings();
  loadPretrainedModels();
}

// ========== 快速体验卡（U12：真源化） ==========
// 数据源与首页 workbench 同源：/api/health/demo-cards
// （扫各机器人包 simulation/config.json 声明的 policies + demo_policies）。
// 端点不可达或包未声明策略时如实显示空态 + 提示——不再硬编码三张假卡。
function escapeDashboardHtml(value) {
  return String(value ?? '').replace(/[&<>"]/g, (char) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[char]
  ));
}

async function loadQuickDemos() {
  const host = document.getElementById('quickList');
  if (!host) return;
  try {
    const response = await fetch(`${API_BASE}/api/health/demo-cards`);
    const data = await response.json();
    const cards = data.cards || [];

    if (!cards.length) {
      host.innerHTML = `
        <div class="empty-state">
          <p>暂无内置策略</p>
          <small>导入机器人包并在其 simulation/config.json 声明 policies 后，即可免训练试玩。</small>
        </div>
      `;
      return;
    }

    host.innerHTML = cards.slice(0, 6).map((card) => {
      const robot = String(card.robot_id || '');
      const name = String(card.label || card.id || robot || '策略');
      const dims = card.obs_dim ? `obs ${card.obs_dim} · act ${card.action_dim ?? '-'}` : robot || '内置策略';
      const playUrl = String(card.play_url || `/web/sim2sim/index.html?robot=${encodeURIComponent(robot)}`);
      return `
        <div class="quick-item" data-play="${escapeDashboardHtml(playUrl)}">
          <div class="quick-icon">🤖</div>
          <div class="quick-info">
            <strong>${escapeDashboardHtml(name)}</strong>
            <span>${escapeDashboardHtml(dims)}</span>
          </div>
        </div>
      `;
    }).join('');

    host.querySelectorAll('[data-play]').forEach((item) => item.addEventListener('click', () => {
      const playUrl = item.dataset.play || '';
      // file:// 直开时相对路径落不到控制面端口——统一解析到 API_BASE（与 training-common.js 同约定）。
      const target = /^https?:/.test(playUrl) ? playUrl : API_BASE + playUrl;
      window.open(target, '_blank');
    }));
  } catch (error) {
    console.error('[Dashboard] Failed to load demo cards:', error);
    host.innerHTML = `
      <div class="empty-state">
        <p>内置策略读取失败</p>
        <small>${escapeDashboardHtml(error.message)}——确认控制面已启动后点「刷新」重试。</small>
      </div>
    `;
  }
}

// ========== 快速演示 ==========
async function quickDemo() {
  try {
    const response = await fetch(`${API_BASE}/api/pretrained/list`);
    const data = await response.json();

    if (!data.success || !data.models || data.models.length === 0) {
      alert('暂无预训练模型\n\n请在机器人包的 simulation/config.json 中配置 policies，或运行 tools/generate_pretrained_index.py 重建索引');
      return;
    }

    const model = data.models.find((m) => m.play_url) || data.models[0];
    const rate = model.success_rate != null ? `\n成功率: ${(model.success_rate * 100).toFixed(1)}%` : '';

    if (confirm(`打开基础仿真试玩？\n\n模型: ${model.name}\n机器人: ${model.robot}${rate}`)) {
      // C1：免训练即玩，直达浏览器基础仿真（不经训练配置、不跑服务端回合）。
      const playUrl = model.play_url || `/web/sim2sim/index.html?robot=${encodeURIComponent(model.robot)}`;
      window.open(playUrl, '_blank');
    }
  } catch (error) {
    console.error('[Dashboard] Demo failed:', error);
    alert('演示失败: ' + error.message);
  }
}

// U12：卡片点击已由 loadQuickDemos 的 data-play 处理器直达对应策略；
// 旧入口保留为兜底（不指向具体模型，走「选一个可玩策略」的通用路径）。
function loadPretrainedModel(modelId) {
  quickDemo();
}

// ========== 导航功能 ==========
function openTraining() {
  window.location.href = 'workbench.html';
}

function openRobots() {
  window.location.href = 'workbench.html#robot';
}

function openAlgorithms() {
  window.location.href = 'workbench.html#training';
}

function viewAllTrainings() {
  window.location.href = 'training_list.html';
}

function viewTraining(taskId) {
  window.location.href = `training_monitor.html?task_id=${taskId}`;
}

// ========== 定时刷新 ==========
setInterval(() => {
  loadTrainingStats();
}, 10000);

console.log('[Dashboard] Loaded - Connected to API');
