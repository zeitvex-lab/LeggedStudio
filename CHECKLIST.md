# Phase 1 实施清单

**当前进度**：5/28 任务（18%）

---

## ✅ 已完成（Week 1 - Part 1）

- [x] 分析 1000frames 参考资料
- [x] 新版 Web 控制台（dashboard_v2）
- [x] Robot Contract V2 系统
- [x] Policy Artifact 标准
- [x] Contract Validator

---

## 🔄 进行中（Week 1 - Part 2）

### 优先级 P0

#### 1. MJLab Adapter
- [ ] `adapters/mjlab_new/training_adapter.py`
- [ ] `adapters/mjlab_new/launcher.py`
- [ ] `adapters/mjlab_new/train_worker.py`

#### 2. ONNX 导出
- [ ] `adapters/mjlab_new/onnx_exporter.py`
- [ ] `backend/export_api.py`

#### 3. 训练管理 API
- [ ] `backend/training_manager.py`
- [ ] `backend/training_api.py`

---

## 📅 待办（Week 2+）

### Week 2
- [ ] Go2 预训练模型（forward walk）
- [ ] Go2 预训练模型（trot）
- [ ] Sim2Sim 验证
- [ ] 训练监控界面

### Week 3
- [ ] WebSocket 实时更新
- [ ] 算法选择界面
- [ ] 预训练模型 API

### Week 4
- [ ] 便携打包
- [ ] 完整测试
- [ ] 文档完善

---

## 🎯 当前焦点

**本周目标**：完成 MJLab Adapter + ONNX 导出 + 训练管理 API

**下一步**：开始实现 MJLab Adapter

---

详见：
- [PROGRESS_REPORT.md](PROGRESS_REPORT.md) — 进度报告
- [IMPLEMENTATION_DETAILED.md](IMPLEMENTATION_DETAILED.md) — 详细计划
- [TODO.md](TODO.md) — 总体任务
