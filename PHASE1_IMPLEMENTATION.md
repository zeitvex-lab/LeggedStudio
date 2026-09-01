# Phase 1 完整实施计划

基于 1000frames 参考和项目愿景

---

## 🎯 第一步：改进 Web 控制台

### 目标
创建类似 1000frames 的专业界面，实现愿景 Step 1-3

---

## 📋 实施清单

### A. Web 界面改进（Week 1）

#### A1. 主控制台重构 ✅ 开始
**文件**：`web/dashboard.html`

**功能**：
- [ ] 快速操作区（Quick Demo / New Training / Models）
- [ ] 训练任务卡片（状态、进度、操作）
- [ ] 系统状态面板
- [ ] 导航栏（参考 1000frames）

---

#### A2. 训练配置页面
**文件**：`web/training_config.html`

**功能**：
- [ ] Robot 选择（Go2/A1/...）
- [ ] 算法选择（PPO/SAC/TD3）
- [ ] 参数配置（epochs, batch_size, lr）
- [ ] 预设模板

---

#### A3. 训练监控页面
**文件**：`web/training_monitor.html`

**功能**：
- [ ] 实时奖励曲线（Chart.js）
- [ ] 成功率趋势
- [ ] 日志实时显示
- [ ] 停止/暂停控制

---

#### A4. 结果展示页面
**文件**：`web/results.html`

**功能**：
- [ ] 训练结果摘要
- [ ] 评估指标
- [ ] Sim2Sim 对比
- [ ] ONNX 导出按钮

---

### B. 后端 API 扩展（Week 1-2）

#### B1. 预训练模型 API
**文件**：`backend/pretrained_api.py`

```python
GET  /api/pretrained/list
GET  /api/pretrained/{model_id}
POST /api/pretrained/demo
```

---

#### B2. 训练管理 API
**文件**：`backend/training_api.py`

```python
POST   /api/training/create
GET    /api/training/{id}/status
POST   /api/training/{id}/stop
GET    /api/training/list
DELETE /api/training/{id}
```

---

#### B3. ONNX 导出 API
**文件**：`backend/export_api.py`

```python
POST /api/export/onnx
GET  /api/export/{id}/download
GET  /api/export/list
```

---

### C. 预训练模型（Week 2）

#### C1. 训练基础模型
**目标**：3 个高质量模型

1. **Go2 Forward Walk**
   - 环境：MJLab
   - 算法：PPO
   - 目标：稳定前行
   
2. **Go2 Trot**
   - 环境：MJLab  
   - 算法：PPO
   - 目标：快速奔跑

3. **A1 Basic Locomotion**
   - 环境：MJLab
   - 算法：PPO
   - 目标：参考对照

**存储结构**：
```
pretrained_models/
├── go2_walk/
│   ├── model.pt
│   ├── model.onnx
│   ├── metadata.json
│   └── demo.gif
├── go2_trot/
└── a1_basic/
```

---

#### C2. 元数据标准
**文件**：`pretrained_models/metadata_schema.json`

```json
{
  "model_id": "go2_walk_v1",
  "robot": "Go2",
  "task": "forward_walk",
  "algorithm": "PPO",
  "performance": {
    "success_rate": 0.92,
    "avg_reward": 150.3,
    "forward_velocity": 1.5
  },
  "training": {
    "epochs": 1000,
    "env_count": 4096,
    "duration_hours": 2.5
  },
  "files": {
    "pytorch": "model.pt",
    "onnx": "model.onnx",
    "demo": "demo.gif"
  }
}
```

---

### D. ONNX 导出（Week 2）

#### D1. 导出器实现
**文件**：`adapters/mjlab/onnx_exporter.py`

**功能**：
- PyTorch → ONNX 转换
- 数值一致性验证
- 动态 batch 支持
- Opset 优化

**参考**：
- Microduck RL（normalizer）
- UniLab（导出流程）

---

#### D2. 验证流程
```python
1. 加载 PyTorch 模型
2. 导出 ONNX
3. 数值验证（相同输入，对比输出）
4. 性能测试（推理速度）
5. 打包下载
```

---

### E. 实时监控（Week 3）

#### E1. WebSocket 服务
**文件**：`backend/websocket.py`

**功能**：
- 训练状态推送
- 日志实时流
- 指标更新

---

#### E2. 前端集成
**文件**：`web/monitor_client.js`

**功能**：
- WebSocket 连接
- Chart.js 实时更新
- 断线重连

---

## 📅 时间表

### Week 1（Day 1-7）
- [x] 分析 1000frames 参考 ✅
- [ ] 重构主控制台（dashboard.html）
- [ ] 实现快速操作区
- [ ] 训练任务卡片
- [ ] 基础 API（训练管理）

### Week 2（Day 8-14）
- [ ] 训练配置页面
- [ ] 预训练模型 API
- [ ] 训练 3 个基础模型
- [ ] ONNX 导出实现
- [ ] 结果展示页面

### Week 3（Day 15-21）
- [ ] 训练监控页面
- [ ] WebSocket 实时更新
- [ ] Chart.js 图表
- [ ] 算法选择界面
- [ ] 测试和优化

### Week 4（Day 22-28）
- [ ] 便携打包
- [ ] 文档完善
- [ ] 新电脑测试
- [ ] Bug 修复

---

## 🎯 验收标准（MVP）

### 1. 快速体验流程
- [ ] 用户打开应用
- [ ] 点击"Quick Demo"
- [ ] 选择预训练模型（Go2 Walk）
- [ ] 3 秒内开始演示
- [ ] 查看运行效果

**目标时间**：10 分钟上手

---

### 2. 完整训练流程
- [ ] 配置新训练任务
- [ ] 选择 Robot（Go2）
- [ ] 选择算法（PPO）
- [ ] 调整参数
- [ ] 开始训练
- [ ] 实时监控
- [ ] 查看结果
- [ ] 导出 ONNX

**目标时间**：30 分钟完整体验

---

### 3. 技术指标
- [ ] 界面响应 < 100ms
- [ ] 训练启动 < 5s
- [ ] ONNX 导出 < 30s
- [ ] 数值误差 < 1e-5
- [ ] 便携包大小 < 3GB

---

## 📊 进度跟踪

**当前进度**：0/28 天

**完成任务**：1/30

**下一步**：开始重构 dashboard.html

---

**Phase 1 完整规划完成！现在开始实施！** 🚀
