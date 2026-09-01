# Legged Studio - 当前进度分析

**更新时间**：2026-08-31 17:55  
**协作**：Claude (本会话) + Codex (并行会话)

---

## ✅ 已完成工作

### 1. Phase 0 启动（Claude + Codex）

#### Task 0.1：Electron + FastAPI 通信（Claude）✅
- `electron/main.js` — Electron 主进程
- `backend/server.py` — FastAPI 最小服务
- 完整测试文档（QUICKSTART.md + TEST_TASK_0_1.md）
- **状态**：代码完成，等待手动测试

#### Task 0.5：Contract Schema（Codex）✅
- `contracts/models.py` — 完整 Pydantic 模型
- `contracts/selfcheck.py` — 验证工具
- `backend/app.py` — Asset Inventory API
- **状态**：已完成

### 2. 进程隔离架构（Codex）✅

#### 根环境（薄控制面）
```toml
# legged_studio/pyproject.toml
[project]
name = "legged-studio"
requires-python = ">=3.12, <3.13"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.31.0",
    "pydantic>=2.0.0",
]
```

**特点**：
- ✅ 仅 FastAPI + Pydantic（控制面）
- ✅ 无训练依赖（MJLab/PyTorch/CUDA）
- ✅ 轻量、快速安装

#### MJLab Adapter（独立环境）
```toml
# legged_studio/adapters/mjlab/pyproject.toml
[project]
name = "legged-studio-mjlab-adapter"
requires-python = ">=3.12,<3.13"
dependencies = [
  "mjlab==1.6.0",
  "onnxruntime>=1.20,<2",
]

[project.optional-dependencies]
cu128 = ["torch>=2.7.0"]  # CUDA 12.8
cpu = ["torch>=2.7.0"]
```

**特点**：
- ✅ 独立 Python 3.12 环境
- ✅ 完整训练依赖（MJLab/PyTorch/Warp）
- ✅ CUDA 12.8 支持
- ✅ 与控制面隔离

### 3. Python 版本统一✅

**决策**：统一使用 Python 3.12.x

**理由**：
- ✅ Microduck RL 要求 `>=3.12, <3.13`
- ✅ 系统已安装 3.12.2
- ✅ PyTorch + CUDA 12.1/12.8 稳定支持
- ✅ 避免 3.13 兼容性问题

**文档**：`PYTHON_VERSION_DECISION.md`

---

## 🔄 进行中工作（Codex）

### MJLab Adapter 环境安装

**命令**（正在执行）：
```bash
uv sync --project legged_studio/adapters/mjlab --python 3.12 --extra cu128
```

**状态**：
- 🔵 后台下载中（160 个包）
- 🔵 主要耗时：PyTorch + CUDA wheels（数 GB）
- 🔵 已运行约 2-3 分钟
- 🔵 进程响应正常

**预计完成时间**：5-10 分钟（取决于网络）

---

## 📊 Phase 0 整体进度

| 任务 | 负责人 | 状态 | 说明 |
|---|---|---|---|
| Task 0.1 | Claude | ✅ 代码完成 | 等待手动测试 |
| Task 0.2 | - | 📋 待分配 | 便携式 Python + MJLab |
| Task 0.3 | - | 📋 待分配 | Three.js URDF 渲染 |
| Task 0.4 | - | 📋 待分配 | STL 体积计算 |
| Task 0.5 | Codex | ✅ 已完成 | Contract Schema |
| **架构设计** | Codex | ✅ 已完成 | 进程隔离架构 |

**完成度**：2.5 / 5（50%，含架构设计）

---

## 🏗️ 进程隔离架构优势

### 设计原则

```
legged_studio/                  # 薄控制面（FastAPI + Pydantic）
├── backend/                    # HTTP API
├── contracts/                  # 契约模型
└── adapters/                   # 隔离的训练环境
    ├── mjlab/                  # MJLab adapter（独立 3.12 + CUDA）
    ├── isaac_gym/              # 未来：Isaac Gym adapter
    └── unilab/                 # 未来：UniLab adapter
```

### 优势

1. **快速安装**
   - 控制面：仅 3 个包（FastAPI/uvicorn/pydantic）
   - 用户无需训练时，不安装 10+ GB 的 CUDA 依赖

2. **环境隔离**
   - MJLab adapter 崩溃不影响控制面
   - 可运行多个 adapter（不同 Python 版本/依赖）

3. **按需加载**
   - 仅使用 MJLab 时，才安装 MJLab adapter
   - 其他 adapter 独立安装

4. **版本锁定**
   - 每个 adapter 独立 `pyproject.toml`
   - MJLab 1.6.0 锁定，不影响其他 adapter

---

## 🎯 下一步行动

### 立即（等待 MJLab 安装完成）

Codex 正在执行：
```bash
uv sync --project legged_studio/adapters/mjlab --python 3.12 --extra cu128
```

**完成后验证**：
1. 检查 `.venv` 是否创建
2. 检查 PyTorch + CUDA 是否可用
3. 运行 `import mjlab` 测试

### 并行（Claude 可做）

1. **Task 0.1 手动测试**（用户执行）
   ```powershell
   cd backend
   pip install -r requirements.txt
   python server.py
   ```

2. **准备 Task 0.2**
   - 便携式 Python 打包方案
   - 参考 ComfyUI-aki

3. **文档更新**
   - 更新 README.md（进程隔离说明）
   - 更新 PHASE0_PROGRESS.md

---

## 📁 当前项目结构

```
legged_studio/
├── adapters/
│   └── mjlab/
│       ├── pyproject.toml       ✅ MJLab adapter 配置
│       ├── .venv/               🔵 正在安装中
│       └── __init__.py          ✅
├── backend/
│   ├── server.py                ✅ Task 0.1 最小服务
│   ├── app.py                   ✅ Asset API
│   └── requirements.txt         ✅
├── contracts/
│   ├── models.py                ✅ Contract 模型
│   ├── selfcheck.py             ✅ 验证工具
│   └── __init__.py              ✅
├── electron/
│   └── main.js                  ✅ Electron 主进程
├── pyproject.toml               ✅ 根环境（薄控制面）
├── PYTHON_VERSION_DECISION.md   ✅ 版本决策文档
├── PHASE0_PROGRESS.md           ✅ 进度跟踪
└── ... (其他文档)
```

---

## 🔍 关键发现

### Python 版本决策修正

Codex 已修正 `PYTHON_VERSION_DECISION.md`：

**修正前**：
> BAM 库限制 Python 3.12

**修正后**：
> BAM 当前组合要求 `<3.13`（不接受 3.13）
> Legged Studio 选择 `>=3.12` 来自 Microduck 项目和统一基线

**更准确的理解**：
- BAM 不限制 3.12，而是不支持 3.13
- 选择 3.12 是主动决策，不是被迫

---

## 💡 协作亮点

1. **架构设计优秀**
   - Codex 实现了"薄控制面 + 隔离 adapter"
   - 符合最佳实践

2. **文档完整**
   - Python 版本决策有详细记录
   - 进程隔离有清晰说明

3. **技术选型合理**
   - uv 管理依赖
   - CUDA 12.8 最新支持
   - PyTorch 2.7.0+

---

## 📖 相关文档

- [PYTHON_VERSION_DECISION.md](PYTHON_VERSION_DECISION.md) — Python 版本决策
- [PHASE0_PROGRESS.md](PHASE0_PROGRESS.md) — Phase 0 进度
- [COORDINATION.md](COORDINATION.md) — Claude + Codex 协作
- [SUMMARY.md](SUMMARY.md) — 工作总结

---

**当前状态**：MJLab adapter 环境安装中，预计 5-10 分钟完成。控制面已就绪，Task 0.1 可随时测试。🚀
