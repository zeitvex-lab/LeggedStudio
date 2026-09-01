/**
 * Legged Studio Dashboard JavaScript
 */

const API_BASE = 'http://127.0.0.1:8765';

// ========== 初始化 ==========
document.addEventListener('DOMContentLoaded', () => {
  initNavigation();
  initClock();
  initMetrics();
  loadSystemStatus();
  loadRecentTasks();
});

// ========== 导航系统 ==========
function initNavigation() {
  const navItems = document.querySelectorAll('.nav-item');

  navItems.forEach(item => {
    item.addEventListener('click', () => {
      // 移除所有 active
      navItems.forEach(i => i.classList.remove('active'));

      // 添加当前 active
      item.classList.add('active');

      // 切换内容
      const tab = item.dataset.tab;
      switchTab(tab);

      // 更新标题
      const title = item.querySelector('span').textContent;
      document.getElementById('page-title').textContent = title;
    });
  });
}

function switchTab(tab) {
  const content = document.getElementById('content');

  switch(tab) {
    case 'pipeline':
      loadPipelineTab();
      break;
    case 'tasks':
      loadTasksTab();
      break;
    case 'models':
      loadModelsTab();
      break;
    case 'assets':
      loadAssetsTab();
      break;
    case 'urdf':
      loadUrdfTab();
      break;
    case 'tools':
      loadToolsTab();
      break;
    case 'settings':
      loadSettingsTab();
      break;
  }
}

// ========== 时钟 ==========
function initClock() {
  const clockEl = document.getElementById('clock');

  function updateClock() {
    const now = new Date();
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    const seconds = String(now.getSeconds()).padStart(2, '0');
    clockEl.textContent = `${hours}:${minutes}:${seconds}`;
  }

  updateClock();
  setInterval(updateClock, 1000);
}

// ========== 系统监控 ==========
function initMetrics() {
  updateMetrics();
  setInterval(updateMetrics, 3000);
}

async function updateMetrics() {
  try {
    // TODO: 从实际 API 获取
    const gpuUsage = Math.floor(Math.random() * 30 + 20);
    const memUsage = Math.floor(Math.random() * 20 + 40);

    document.getElementById('gpu-usage').textContent = `${gpuUsage}%`;
    document.getElementById('mem-usage').textContent = `${memUsage}%`;
  } catch (error) {
    console.error('Failed to update metrics:', error);
  }
}

// ========== 加载系统状态 ==========
async function loadSystemStatus() {
  try {
    const response = await fetch(`${API_BASE}/api/system/environment`);
    const data = await response.json();

    // 更新状态指示器
    // TODO: 根据实际状态更新 UI
  } catch (error) {
    console.error('Failed to load system status:', error);
  }
}

// ========== 加载最近任务 ==========
async function loadRecentTasks() {
  try {
    const response = await fetch(`${API_BASE}/api/pipeline/list`);
    const data = await response.json();

    // TODO: 渲染任务列表
  } catch (error) {
    console.error('Failed to load recent tasks:', error);
  }
}

// ========== Tab 内容加载 ==========
function loadPipelineTab() {
  const content = document.getElementById('content');
  content.innerHTML = `
    <div class="content-inner">
      <!-- 快速操作卡片 -->
      <div class="quick-cards">
        <div class="card card-featured">
          <div class="card-icon-lg">⚡</div>
          <h3>快速体验</h3>
          <p>加载预训练模型，立即查看 Sim2Sim 效果</p>
          <button class="btn btn-primary btn-lg" onclick="quickDemo()">开始体验</button>
        </div>

        <div class="card">
          <div class="card-icon-lg">🚀</div>
          <h3>新建训练</h3>
          <p>上传 Contract，开始完整训练流程</p>
          <button class="btn btn-secondary btn-lg" onclick="newTraining()">创建训练</button>
        </div>

        <div class="card">
          <div class="card-icon-lg">📊</div>
          <h3>模型库</h3>
          <p>浏览预训练模型和历史训练结果</p>
          <button class="btn btn-secondary btn-lg" onclick="openModels()">浏览模型</button>
        </div>
      </div>

      <!-- 系统状态 -->
      <div class="section">
        <h2 class="section-title">系统状态</h2>
        <div class="status-cards">
          <div class="status-card">
            <div class="status-card-header">
              <span class="status-card-label">控制面</span>
              <span class="badge badge-success">运行中</span>
            </div>
            <div class="status-card-body">
              <div class="status-card-metric">
                <span class="label">Python</span>
                <span class="value">3.12.2</span>
              </div>
              <div class="status-card-metric">
                <span class="label">API</span>
                <span class="value">20+ 端点</span>
              </div>
            </div>
          </div>

          <div class="status-card">
            <div class="status-card-header">
              <span class="status-card-label">MJLab Adapter</span>
              <span class="badge badge-success">就绪</span>
            </div>
            <div class="status-card-body">
              <div class="status-card-metric">
                <span class="label">PyTorch</span>
                <span class="value">2.11.0</span>
              </div>
              <div class="status-card-metric">
                <span class="label">CUDA</span>
                <span class="value">12.8</span>
              </div>
            </div>
          </div>

          <div class="status-card">
            <div class="status-card-header">
              <span class="status-card-label">训练任务</span>
              <span class="badge badge-info">0 运行中</span>
            </div>
            <div class="status-card-body">
              <div class="status-card-metric">
                <span class="label">队列</span>
                <span class="value">0 等待</span>
              </div>
              <div class="status-card-metric">
                <span class="label">今日</span>
                <span class="value">0 完成</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 最近训练 -->
      <div class="section">
        <div class="section-header">
          <h2 class="section-title">最近训练</h2>
          <button class="btn btn-sm btn-ghost" onclick="viewAllTasks()">查看全部</button>
        </div>
        <div class="task-list" id="task-list">
          <div class="empty-state">
            <p>暂无训练任务</p>
            <button class="btn btn-primary" onclick="newTraining()">开始第一个训练</button>
          </div>
        </div>
      </div>
    </div>
  `;
}

function loadTasksTab() {
  const content = document.getElementById('content');
  content.innerHTML = `
    <div class="content-inner">
      <h2>任务监控</h2>
      <p>实时监控训练任务...</p>
    </div>
  `;
}

function loadModelsTab() {
  const content = document.getElementById('content');
  content.innerHTML = `
    <div class="content-inner">
      <h2>模型管理</h2>
      <p>管理训练模型和预训练模型...</p>
    </div>
  `;
}

function loadAssetsTab() {
  const content = document.getElementById('content');
  content.innerHTML = `
    <div class="content-inner">
      <h2>机器人资产</h2>
      <p>浏览可用的机器人模型...</p>
    </div>
  `;
}

function loadUrdfTab() {
  window.open('/urdf-viewer/index.html', '_blank');
}

function loadToolsTab() {
  const content = document.getElementById('content');
  content.innerHTML = `
    <div class="content-inner">
      <h2>工具箱</h2>
      <p>STL 计算、ONNX 导出等工具...</p>
    </div>
  `;
}

function loadSettingsTab() {
  const content = document.getElementById('content');
  content.innerHTML = `
    <div class="content-inner">
      <h2>设置</h2>
      <p>系统配置...</p>
    </div>
  `;
}

// ========== 操作函数 ==========
async function quickDemo() {
  try {
    const response = await fetch(`${API_BASE}/api/pipeline/run-example`, {
      method: 'POST'
    });
    const data = await response.json();

    alert(`快速演示已启动\nPipeline ID: ${data.pipeline_id}`);

    // 跳转到任务监控
    document.querySelector('[data-tab="tasks"]').click();
  } catch (error) {
    console.error('Failed to start quick demo:', error);
    alert('启动失败：' + error.message);
  }
}

function newTraining() {
  // TODO: 打开训练创建对话框
  alert('训练创建功能开发中...');
}

function openModels() {
  document.querySelector('[data-tab="models"]').click();
}

function viewAllTasks() {
  document.querySelector('[data-tab="tasks"]').click();
}
