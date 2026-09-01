# Phase 0 资产工作台进度

**时间**：2026-08-31 开始  
**预计**：先完成资产工作台，再进入 Go2 MVP

---

## Task 0.1：资产查询控制面 ✅

**目标**：让产品可以读取、筛选和展示机器资产事实源

**状态**：已完成（FastAPI + stdlib fallback）

### 已完成

- [x] 创建 FastAPI/stdlib 资产服务 (`backend/app.py`)
- [x] 健康检查、摘要、family 和筛选 API
- [x] 浏览器资产工作台
- [x] 项目结构创建

### 待验证

- [x] 后端独立启动测试
- [ ] Electron 集成测试
- [ ] 进程通信验证

### 验收标准

- [ ] Electron 窗口打开
- [x] Python 后端启动
- [x] 浏览器显示资产摘要和列表

---

## Task 0.2：便携式 Python + MJLab 测试 📋

**目标**：验证 MJLab 在便携环境可运行

**状态**：Python 3.12 已锁定；待冻结 MJLab adapter 依赖与 smoke

### 步骤

- [x] 锁定 Python 3.12 产品主版本
- [ ] 冻结 MJLab adapter 依赖锁
- [ ] 安装 pip
- [ ] 安装 PyTorch + CUDA 12.1
- [ ] 测试 CUDA 可用性
- [ ] 安装 MJLab 并运行 smoke test

### 验收标准

- [ ] 便携式 Python 可运行
- [ ] CUDA 可用（仅需驱动）
- [ ] MJLab 训练成功（64 envs, 5 iterations）

---

## Task 0.3：URDF/MJCF 预览原型 📋

**目标**：验证 URDF 3D 预览可行

**状态**：待实现

### 步骤

- [ ] 定义 URDF Studio adapter 边界
- [ ] 复用 `urdf_tool/URDF-Studio` parser/workspace/viewer
- [ ] 将解析结果映射到 Robot Contract
- [ ] 加载 Go2 并渲染 mesh

### 验收标准

- [ ] 导入 Go2 URDF，显示 3D 模型
- [ ] 可旋转查看
- [ ] 性能 >30 FPS

---

## Task 0.4：mesh 质量 worker 📋

**目标**：验证质量估算算法准确性

**状态**：待实现；当前只做引用完整度和声明质量审计

### 步骤

- [ ] 复用 URDF Studio geometry worker 边界并补齐 mesh signed-volume
- [ ] 测试标准几何体（球体、立方体、圆柱）
- [ ] 测试 Go2 base_link STL
- [ ] 对比 URDF 质量标签

### 验收标准

- [ ] 标准几何体误差 <1%
- [ ] Go2 质量估算合理（差异 <20%）

---

## Task 0.5：Contract Schema 设计 ✅

**目标**：定义 Robot Contract 数据结构

**状态**：基础模型已完成；Go2 完整 Contract 待补

### 步骤

- [x] 用 Pydantic 定义 RobotContract 模型
- [ ] 创建 Go2 的完整 Contract 实例（YAML）
- [x] 编写 inventory 验证和筛选工具
- [x] 自检测试

### 验收标准

- [ ] Schema 定义完整（关节映射、控制参数、坐标系）
- [ ] Go2 Contract YAML 可加载并验证通过
- [ ] 验证工具可检测缺失字段和类型错误

---

## 当前焦点

1. 验收资产工作台和 API
2. 冻结 Go2 `M-P` Robot Contract
3. 建立 MJLab 64-env smoke 与 ONNX replay

---

## 进度记录

| 日期 | 任务 | 状态 | 备注 |
|---|---|---|---|
| 2026-08-31 | Phase 0 启动 | ✅ | 创建项目结构 |
| 2026-08-31 | 资产 inventory/API/UI | ✅ | 82 个本体、28 个 family 可筛选浏览 |
| 2026-08-31 | Robot Contract 基础模型 | ✅ | S/M/L、readiness、joint mapping 自检通过 |
| 2026-08-31 | Electron 集成 | 🟡 | 已接入 app.py:8000，待 GUI 生命周期验收 |
| 2026-08-31 | Python 版本 | ✅ | 控制面与 MVP 锁定 3.12；3.13 待兼容矩阵 |
