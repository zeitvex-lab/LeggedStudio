# Phase 1 任务清单

基于 [PROJECT_VISION_LEGGED_STUDIO.md](../PROJECT_VISION_LEGGED_STUDIO.md) 和 [REFERENCE_AND_RECOMMENDATIONS.md](../REFERENCE_AND_RECOMMENDATIONS.md)

---

## P0 核心功能（MVP）

### 1. 改进 Web 界面 ⭐⭐⭐
**参考**：
- `../references_1000framesai/`（1000frames 设计）
- `../REFERENCE_AND_RECOMMENDATIONS.md`（推荐方案）

**任务**：
- [ ] 分析 1000frames UI/UX
- [ ] 实现 Step 1-3 工作流（愿景 7 步流程）
  - Step 1: 资产验证
  - Step 2: 训练配置
  - Step 3: 训练监控
- [ ] 训练任务卡片
- [ ] 实时监控图表（Chart.js）
- [ ] 配置表单（基于 Robot Contract）

**依据**：愿景第四章"全流程 7 步"

---

### 2. ONNX 导出 ⭐⭐⭐
**参考**：
- Microduck RL（ONNX normalizer）
- UniLab（ONNX export）
- RC_WheelLeg（ONNX/TensorRT）

**任务**：
- [ ] PyTorch → ONNX 转换
- [ ] API：`POST /api/export/onnx`
- [ ] 数值一致性验证
- [ ] 下载接口

**文件**：
- `adapters/mjlab/onnx_exporter.py`
- `backend/export_api.py`

**依据**：愿景 Step 6（导出与部署）

---

### 3. 预训练模型库 ⭐⭐⭐
**目标**：10 分钟上手，快速体验

**任务**：
- [ ] 训练 3 个基础模型
  - Go2 forward walk（M-P，MVP 主线）
  - Go2 trot
  - A1 basic locomotion（参考对照）
- [ ] PolicyArtifact 元数据
- [ ] 快速演示功能

**文件**：
- `pretrained_models/`
- `pretrained_models/metadata.json`
- `backend/pretrained_api.py`

**依据**：愿景目标"10 分钟上手"

---

### 4. Robot Contract 统一 ⭐⭐
**参考**：
- RoboLab（TensorContract、Recipe）
- Microduck（61D 布局、不变量）

**任务**：
- [ ] 定义统一 Robot Contract Schema
- [ ] 观测维度、关节顺序标准化
- [ ] 验证接口（基于 URDF Studio）

**文件**：
- `contracts/robot_contract.py`（已有基础）
- `contracts/policy_artifact.py`

**依据**：愿景第六章"契约体系"

---

## P1 用户体验

### 5. 训练监控界面
- [ ] 实时奖励曲线
- [ ] 成功率趋势
- [ ] GPU/内存监控
- [ ] WebSocket 实时更新

### 6. 算法选择
- [ ] PPO/SAC/TD3 选择
- [ ] 参数调整 UI
- [ ] 预设配置

### 7. 工作流可视化
- [ ] 步骤指示器（1→2→3→...→7）
- [ ] 当前步骤高亮

---

## P2 打包与扩展

### 8. 便携打包
- [ ] 执行 `scripts/build_portable.bat`
- [ ] Python embeddable + 依赖
- [ ] 新电脑测试

### 9. Step 4-7（Phase 2）
- Step 4: 评估与 Sim2Sim（RoboGauge）
- Step 5: 导航与任务仿真
- Step 6: 高级部署
- Step 7: 部署回溯

---

## 参考资源

### 核心文档
- **项目愿景**：`../PROJECT_VISION_LEGGED_STUDIO.md`
- **参考清单**：`../REFERENCE_AND_RECOMMENDATIONS.md`
- **资产清单**：`../QUADRUPED_ASSET_INVENTORY.md`

### 推荐直接纳入
- URDF Studio 2.0（Step 1 资产工作台）
- RoboLab（编排、Artifact 语义）
- MJLab（MVP 训练后端）
- Microduck RL（训练/导出不变量）

### 设计参考
- 1000frames（`../references_1000framesai/`）
- UniLab（跨后端契约）
- RoboGauge（自动评估）

---

## 优先级

**Week 1**：
1. 分析参考资源
2. 改进 Web 界面（Step 1-3）
3. ONNX 导出

**Week 2**：
4. 预训练模型
5. Robot Contract 统一

**Week 3-4**：
6. 训练监控
7. 便携打包

---

## 6 种分类支持

根据愿景第五章和资产清单：

| 分类 | 质量范围 | 当前候选 | MVP 主线 |
|---|---|---|---|
| S-P | < 15 kg | OpenDoge, Lite3, A1, Go1 | ⚠️ 待验证 |
| S-W | < 15 kg | RC_WheelLeg（旧版） | ❌ 质量漂移 |
| M-P | 15-35 kg | **Go2**, AS2, Aliengo | ✅ **Go2** |
| M-W | 15-35 kg | Go2W, AS2W | ⚠️ 待测试 |
| L-P | ≥ 35 kg | A2, ANYmal C, B1, B2 | ⚠️ A2 候选 |
| L-W | ≥ 35 kg | A2W, B2W | ❌ 缺 actuator |

**MVP 焦点**：Go2（M-P），最干净的主线

---

**基于项目愿景和参考清单制定！** 🚀
