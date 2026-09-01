# Tongling 界面设计分析与学习

**参考项目**：auto_web/online_tools (统领 AI 渗透控制台)

---

## 🎨 核心设计特点

### 1. macOS 风格的多窗口工作台 ⭐⭐⭐

**特点**：
- 顶部菜单栏（类 macOS）
- 底部程序栏（Dock）
- 可拖拽的多窗口系统
- 壁纸背景层

**实现要素**：
```html
<!-- 壁纸层 -->
<div class="mac-wallpaper-layer">
  <img class="mac-wallpaper-img" />
  <div class="mac-wallpaper-dim"></div>
</div>

<!-- 顶部菜单栏 -->
<div class="mac-menubar">
  <div class="mac-menu-left">...</div>
  <div class="mac-menubar-actions">...</div>
  <div class="mac-menubar-right">
    <span class="mac-menubar-metrics">CPU / 内存</span>
    <span class="mac-menubar-clock">时间</span>
  </div>
</div>

<!-- 底部程序栏 -->
<nav class="mac-dock">
  <button class="mac-dock-item">
    <svg>...</svg>
    <span>智能体</span>
  </button>
</nav>
```

---

### 2. 侧边栏导航 + 主内容区 ⭐⭐

**布局**：
```
┌────────────────────────────────────┐
│ 侧边栏          │   主内容区       │
│ ┌────────┐    │                   │
│ │Logo    │    │   Tab 内容        │
│ ├────────┤    │                   │
│ │工作台  │    │                   │
│ │ AI智能体│    │                   │
│ │ 接口运行│    │                   │
│ │ 任务监控│    │                   │
│ ├────────┤    │                   │
│ │扫描    │    │                   │
│ │ 扫描报告│    │                   │
│ │ 扫描图谱│    │                   │
│ ├────────┤    │                   │
│ │资源    │    │                   │
│ │ 文件管理│    │                   │
│ │ 工具目录│    │                   │
└────────────────────────────────────┘
```

---

### 3. 主题系统 ⭐⭐

**支持**：
- Dark（默认）
- Light
- Mocha
- Deep

**实现**：
```javascript
// 主题切换
var map = { mocha: 'dark', dark: 'dark', deep: 'deep', light: 'light' };
var t = localStorage.getItem('tongling_web_theme');
t = map[t] || 'dark';
document.documentElement.setAttribute('data-theme', t);
```

**CSS 变量**：
```css
[data-theme="dark"] {
  --bg-primary: #1e1e2e;
  --text-primary: #cdd6f4;
  --accent: #00e676;
}
```

---

### 4. 实时状态监控 ⭐⭐⭐

**顶部状态栏**：
- CPU 使用率
- 内存使用率
- 当前时间
- 连接状态

**实现**：
```html
<span class="mac-menubar-metrics">
  <span id="mac-metric-cpu">CPU —</span>
  <span id="mac-metric-mem">内存 —</span>
</span>
<span class="mac-menubar-clock" id="clock"></span>
```

---

### 5. SVG 图标系统 ⭐⭐

**优势**：
- 可缩放
- 可着色
- 轻量级

**示例**：
```html
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75">
  <path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3z"/>
  <path d="M5 19h14"/>
</svg>
```

---

### 6. 多语言支持 ⭐

**实现**：
```html
<span data-i18n="nav.agent">AI 智能体</span>

<script>
// i18n 切换
const translations = {
  'zh-CN': { 'nav.agent': 'AI 智能体' },
  'en-US': { 'nav.agent': 'AI Agent' }
};
</script>
```

---

## 🚀 应用到 Legged Studio

### 改进 1：专业控制台首页

**文件**：`web/dashboard.html`

```html
<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Legged Studio - 控制台</title>
  <link rel="stylesheet" href="dashboard.css">
</head>
<body>
  <!-- 壁纸层 -->
  <div class="wallpaper-layer">
    <img class="wallpaper-img" src="assets/wallpaper-robot.jpg" alt="">
    <div class="wallpaper-dim"></div>
  </div>

  <div class="layout">
    <!-- 侧边栏 -->
    <aside class="sidebar">
      <div class="sidebar-brand">
        <img src="favicon.png" width="32" height="32">
        <div>
          <strong>Legged Studio</strong>
          <span>强化学习工作台</span>
        </div>
      </div>

      <nav class="sidebar-nav">
        <div class="nav-group">
          <div class="nav-group-label">训练</div>
          <button class="nav-item active" data-tab="pipeline">
            <svg viewBox="0 0 24 24">...</svg>
            <span>训练流水线</span>
          </button>
          <button class="nav-item" data-tab="tasks">
            <svg viewBox="0 0 24 24">...</svg>
            <span>任务监控</span>
          </button>
          <button class="nav-item" data-tab="models">
            <svg viewBox="0 0 24 24">...</svg>
            <span>模型管理</span>
          </button>
        </div>

        <div class="nav-group">
          <div class="nav-group-label">资源</div>
          <button class="nav-item" data-tab="assets">
            <svg viewBox="0 0 24 24">...</svg>
            <span>机器人资产</span>
          </button>
          <button class="nav-item" data-tab="urdf">
            <svg viewBox="0 0 24 24">...</svg>
            <span>URDF 查看器</span>
          </button>
          <button class="nav-item" data-tab="tools">
            <svg viewBox="0 0 24 24">...</svg>
            <span>工具箱</span>
          </button>
        </div>

        <div class="nav-group">
          <div class="nav-group-label">系统</div>
          <button class="nav-item" data-tab="settings">
            <svg viewBox="0 0 24 24">...</svg>
            <span>设置</span>
          </button>
        </div>
      </nav>
    </aside>

    <!-- 主内容区 -->
    <main class="main">
      <!-- 顶部状态栏 -->
      <div class="topbar">
        <div class="topbar-left">
          <span class="breadcrumb">训练流水线</span>
        </div>
        <div class="topbar-right">
          <span class="status-indicator">
            <span class="status-dot status-success"></span>
            MJLab 就绪
          </span>
          <span class="status-indicator">
            <span class="status-dot status-success"></span>
            CUDA 可用
          </span>
          <span class="metric">
            <span class="metric-label">GPU</span>
            <span id="gpu-usage">—</span>
          </span>
          <span class="clock" id="clock"></span>
        </div>
      </div>

      <!-- Tab 内容 -->
      <div class="content" id="content">
        <!-- 动态加载 -->
      </div>
    </main>
  </div>

  <script src="dashboard.js"></script>
</body>
</html>
```

---

### 改进 2：训练流水线界面

**设计**：
```
┌──────────────────────────────────────────────────────────┐
│ 训练流水线                                      [新建训练] │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  进度指示器：                                            │
│  ① 配置 → ② 训练 → ③ 评估 → ④ 部署                      │
│  ✅      🔵      ⚪      ⚪                              │
│                                                          │
│  当前任务：Go2 Forward Walk                              │
│  状态：训练中 (进度 45%)                                  │
│  ┌────────────────────────────────────┐                │
│  │████████████░░░░░░░░░░░░░░░░░░░░░░░│ 45%            │
│  └────────────────────────────────────┘                │
│                                                          │
│  实时指标：                                              │
│  ┌──────────┬──────────┬──────────┐                    │
│  │Success   │Avg Reward│Episode   │                    │
│  │85%       │120.5     │500       │                    │
│  └──────────┴──────────┴──────────┘                    │
│                                                          │
│  ┌────────────────────────────────────┐                │
│  │ 奖励曲线图                         │                │
│  │                                    │                │
│  └────────────────────────────────────┘                │
│                                                          │
│  [暂停训练] [查看日志] [导出 ONNX]                      │
│                                                          │
├──────────────────────────────────────────────────────────┤
│ 最近训练                                                 │
│  go2_walk_v1   ✅ 85%   2h 前   [查看] [删除]           │
│  a1_trot_v2    ✅ 78%   5h 前   [查看] [删除]           │
│  go2_stairs    🔵 运行中        [查看] [停止]            │
└──────────────────────────────────────────────────────────┘
```

---

### 改进 3：快速体验入口

**首页卡片**：
```html
<div class="quick-start-cards">
  <div class="card card-featured">
    <div class="card-icon">⚡</div>
    <h3>快速体验</h3>
    <p>加载预训练模型，立即查看 Sim2Sim 效果</p>
    <button class="btn btn-primary">开始体验</button>
  </div>

  <div class="card">
    <div class="card-icon">🚀</div>
    <h3>新建训练</h3>
    <p>上传 Contract，开始完整训练流程</p>
    <button class="btn btn-secondary">创建</button>
  </div>

  <div class="card">
    <div class="card-icon">📊</div>
    <h3>模型库</h3>
    <p>浏览预训练模型和历史训练结果</p>
    <button class="btn btn-secondary">查看</button>
  </div>
</div>
```

---

## 📝 实施计划

### Week 1：核心界面

1. **创建专业控制台**
   - 文件：`web/dashboard.html`
   - 侧边栏导航
   - 顶部状态栏
   - Tab 系统

2. **训练流水线界面**
   - 进度指示器
   - 实时监控
   - 操作按钮

3. **CSS 主题系统**
   - 文件：`web/themes.css`
   - Dark/Light 主题
   - CSS 变量

### Week 2：高级功能

4. **SVG 图标库**
   - 统一图标风格
   - 自定义图标

5. **实时状态更新**
   - WebSocket 或轮询
   - GPU/内存监控

6. **多语言支持**
   - 中文/英文切换

---

**学习总结**：Tongling 的界面设计非常专业，特别是 macOS 风格的多窗口系统和实时状态监控。我们应该借鉴其布局结构和交互模式，但保持 Legged Studio 自己的特色。
