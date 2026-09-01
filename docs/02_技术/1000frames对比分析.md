# Legged Studio vs 1000frames - 设计对比与改进

**对比时间**：2026-08-31  
**参考**：https://1000framesai.com/

---

## 📊 功能对比

| 功能 | 1000frames | Legged Studio | 状态 |
|---|---|---|---|
| **训练流水线** | ✅ 完整 | ✅ 完整 | 相当 |
| **Sim2Sim** | ✅ 可视化 | ✅ 已实现 | 相当 |
| **Contract/配置** | ✅ URDF/STEP | ✅ Contract Schema | 相当 |
| **算法适配** | ✅ 多算法 | 🔵 待实现 | 需改进 |
| **远程训练** | ✅ 云端 | 🔵 本地 | 需改进 |
| **快速体验** | ✅ 预训练模型 | 🔵 示例 Contract | 可改进 |
| **状态监控** | ✅ 实时 | ✅ API 状态 | 相当 |
| **ONNX 导出** | ✅ | ❌ | 需添加 |
| **URDF 可视化** | ✅ | ✅ Three.js | 相当 |

---

## 🎯 核心学习点

### 1. 四步工作流设计 ⭐

**1000frames 模式**：
```
Step 1: 机器人配置（URDF/STEP）
Step 2: 算法适配（选择算法、调整参数）
Step 3: 训练任务（提交、监控、查看日志）
Step 4: 上线检查（Sim2Sim 验证、ONNX 导出）
```

**Legged Studio 当前**：
```
验证 → 训练 → 评估 → Sim2Sim
```

**改进建议**：
- ✅ 已有类似流程
- 🔵 需要添加算法选择界面
- 🔵 需要 ONNX 导出功能
- 🔵 需要更清晰的 UI 步骤指引

---

### 2. 快速体验策略 ⭐⭐⭐

**1000frames**：
- 提供预训练权重
- 跳过训练直接体验 Sim2Sim
- 降低上手门槛

**Legged Studio 改进**：
```python
# 添加预训练模型下载
/api/pretrained/list          # 列出预训练模型
/api/pretrained/download/{id} # 下载模型
/api/pretrained/quick-demo    # 快速演示

# 示例模型
- Go2 Forward Walk (5MB)
- Go2 Trot (5MB)
- A1 Basic Locomotion (5MB)
```

---

### 3. 状态优先的控制台 ⭐⭐

**1000frames 控制台**：
- 首屏显示系统状态
- 训练状态、算法状态、远程资源
- 实时更新

**Legged Studio 改进**：
```
控制台首页应该显示：
┌─────────────────────────────────────┐
│ 系统状态                             │
│ ✅ MJLab Adapter: 就绪               │
│ ✅ CUDA: 可用                        │
│ 🔵 训练任务: 1 个运行中               │
│ ⚪ 队列: 0 个等待                    │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ 快速操作                             │
│ [新建训练] [查看任务] [快速体验]      │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ 最近训练                             │
│ go2_walk_v1   85% 成功率  2h 前      │
│ a1_trot_v2    78% 成功率  5h 前      │
└─────────────────────────────────────┘
```

---

### 4. 渐进式复杂度 ⭐⭐

**用户路径**：
```
新手路径：
  快速体验 → 加载预训练模型 → Sim2Sim 查看

进阶路径：
  上传 Contract → 使用默认参数训练 → 评估

高级路径：
  自定义算法 → 调整奖励函数 → Resume 训练
```

**Legged Studio 实现**：
- ✅ 已有示例 Contract
- 🔵 需要预训练模型库
- 🔵 需要算法选择界面
- 🔵 需要高级参数调整

---

### 5. ONNX 导出 ⭐⭐⭐

**重要性**：实机部署必需

**实现方案**：
```python
# 添加 ONNX 导出 API
POST /api/pipeline/export-onnx
{
  "checkpoint": "path/to/model.pt",
  "format": "onnx",
  "opset_version": 17
}

# 返回
{
  "onnx_path": "path/to/model.onnx",
  "file_size": "5.2 MB",
  "input_shape": [1, 48],
  "output_shape": [1, 12]
}
```

---

## 🚀 改进优先级

### P0（立即实现）

#### 1. 改进控制台首页
- 显示系统状态
- 显示训练任务列表
- 快速操作入口

#### 2. ONNX 导出功能
```python
# adapters/mjlab/onnx_exporter.py
def export_to_onnx(checkpoint_path, output_path):
    """导出 PyTorch 模型为 ONNX"""
    pass
```

#### 3. 预训练模型库
```
pretrained_models/
├── go2_forward_walk.onnx
├── go2_trot.onnx
└── a1_basic.onnx
```

---

### P1（短期改进）

#### 4. 算法选择界面
```javascript
// 算法选择
const ALGORITHMS = [
  { id: 'ppo', name: 'PPO', description: '通用强化学习' },
  { id: 'sac', name: 'SAC', description: '连续控制' },
  { id: 'td3', name: 'TD3', description: '确定性策略' }
]
```

#### 5. 训练监控界面
- 实时奖励曲线
- 成功率趋势
- 资源使用情况

---

### P2（长期优化）

#### 6. 云端训练支持
- 远程 GPU 调度
- 分布式训练

#### 7. 高级参数调整
- 奖励函数编辑器
- 超参数搜索

---

## 📝 UI/UX 改进建议

### 1. 工作流可视化
```
[1. 配置] → [2. 训练] → [3. 评估] → [4. 部署]
   ✅          🔵          ⚪          ⚪
```

### 2. 状态指示器
```
训练中：  🔵 运行中 (进度 45%)
已完成：  ✅ 成功 (Success Rate 85%)
失败：    ❌ 失败 (查看日志)
等待：    ⚪ 队列中 (前面 2 个任务)
```

### 3. 操作-结果可见性
```
[开始训练] → 生成 checkpoint
[评估模型] → 生成 eval_results.json
[导出 ONNX] → 生成 model.onnx
```

---

## 💡 设计哲学对比

### 1000frames
- **B2B 定位**：面向专业团队
- **技术术语**：ONNX、URDF、worker
- **状态透明**：实时监控
- **快速反馈**：预训练模型

### Legged Studio
- **开源工具**：面向研究者和学生
- **本地优先**：不依赖云服务
- **完整文档**：教育友好
- **模块化**：易于扩展

---

## ✅ 立即行动项

### 1. 创建控制台首页
文件：`web/console.html`

### 2. 实现 ONNX 导出
文件：`adapters/mjlab/onnx_exporter.py`

### 3. 添加预训练模型
目录：`pretrained_models/`

### 4. 更新 API 文档
文件：`backend/README.md`

---

## 🎯 目标

**短期**（1 周）：
- ✅ 控制台首页
- ✅ ONNX 导出
- ✅ 预训练模型库

**中期**（1 月）：
- 算法选择界面
- 训练监控可视化
- 完善文档

**长期**（3 月）：
- 云端训练支持
- 社区模型库
- 插件系统

---

**学习总结**：1000frames 的核心优势在于**降低专业工具的使用门槛**，通过清晰的工作流、快速体验、状态透明化实现。Legged Studio 应该吸收这些经验，同时保持开源、本地优先的特色。
