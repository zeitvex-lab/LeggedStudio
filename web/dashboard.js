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
  loadTrainingStats();
  loadRecentTrainings();
  loadPretrainedModels();
});

// ========== 系统状态 ==========
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

    if (data.control_plane) {
      document.getElementById('pythonVersion').textContent =
        data.control_plane.python_version;
    }

  } catch (error) {
    console.error('[Dashboard] Failed to load system status:', error);
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
  loadTrainingStats();
  loadRecentTrainings();
  loadPretrainedModels();
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
