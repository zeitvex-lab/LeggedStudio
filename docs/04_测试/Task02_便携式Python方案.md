# Task 0.2：便携式 Python + MJLab 验证方案

**目标**：验证 MJLab 在便携 Python 环境中可运行

**参考**：
- ComfyUI-aki-v3.2（5.6 GB 便携 Python + CUDA）
- PROJECT_VISION 第七章技术栈
- REFERENCE_AND_RECOMMENDATIONS 便携式打包

---

## 📋 方案设计

### 方案 A：使用 MJLab Adapter 环境（推荐）

**思路**：复用已创建的 `adapters/mjlab/.venv`

**优势**：
- ✅ 已经是 Python 3.12 隔离环境
- ✅ uv 管理，依赖已锁定
- ✅ 包含 MJLab + PyTorch + CUDA
- ✅ 符合进程隔离架构

**步骤**：
1. 验证当前 adapter 环境可运行
2. 测试 MJLab smoke test（64 envs, 5 iterations）
3. 记录依赖和大小
4. 确认便携化方案

**验证命令**：
```bash
cd adapters/mjlab
.venv/Scripts/python.exe preflight.py
```

---

### 方案 B：下载 Python embeddable（备选）

**思路**：从头构建便携环境

**参考**：ComfyUI 打包结构
```
ComfyUI-aki-v3.2/python/
├── python.exe          ~50 MB
├── lib/                CUDA Runtime ~2.6 GB
└── Lib/site-packages/  依赖 ~3 GB
```

**步骤**：
1. 下载 Python 3.12 embeddable
2. 安装 pip
3. 安装 PyTorch + CUDA 12.8
4. 安装 MJLab
5. 测试运行

**问题**：重复工作，adapter 已经做了这个

---

## ✅ 推荐执行（方案 A）

### Step 1：验证 MJLab Adapter 环境

```bash
cd C:\Users\31560\Documents\00_open\legged_studio\adapters\mjlab

# 1. 检查 Python 版本
.venv\Scripts\python.exe --version

# 2. 检查 MJLab
.venv\Scripts\python.exe -c "import mjlab; print('MJLab OK')"

# 3. 检查 PyTorch + CUDA
.venv\Scripts\python.exe -c "import torch; print(f'PyTorch {torch.__version__}'); print(f'CUDA: {torch.cuda.is_available()}')"

# 4. 运行 preflight
.venv\Scripts\python.exe preflight.py
```

**预期输出**：
```json
{
  "python": {"version": "3.12.x", "ok": true},
  "packages": {"mjlab": "1.6.0", "torch": "2.x", ...},
  "gpu": {"available": true, "devices": [...]}
}
```

---

### Step 2：MJLab Smoke Test

参考 Microduck AGENTS.md smoke test：
```bash
# 最小训练测试（64 envs, 5 iterations）
.venv\Scripts\python.exe -m mjlab.train \
  --task <simple_task> \
  --num-envs 64 \
  --max-iterations 5
```

**验收标准**：
- [ ] 环境创建成功
- [ ] 训练开始并运行 5 步
- [ ] GPU 被使用
- [ ] 无崩溃

---

### Step 3：记录依赖大小

```bash
# 查看 venv 大小
du -sh .venv

# 查看主要包
.venv\Scripts\pip list | grep -E "torch|mujoco|warp|mjlab"
```

**预估**（基于 ComfyUI 参考）：
```
.venv/
├── Python 3.12        ~50 MB
├── PyTorch + CUDA     ~2.6 GB
├── MJLab + deps       ~500 MB
├── Warp               ~100 MB
├── MuJoCo             ~200 MB
└── 其他               ~200 MB
─────────────────────────────
总计：~3.6 GB
```

---

### Step 4：便携化方案

#### 选项 1：直接使用 .venv（Phase 0/1）

**优势**：
- 简单直接
- 已经隔离
- uv 管理依赖

**劣势**：
- 路径依赖（需要在 legged_studio/ 目录运行）

#### 选项 2：打包为独立 runtime（Phase 2）

**参考 ComfyUI 结构**：
```
legged_studio/
└── runtime/
    └── python/          # 便携 Python
        ├── python.exe
        ├── lib/         # CUDA Runtime
        └── Lib/site-packages/
```

**实现**：
1. 复制 .venv 内容到 runtime/python
2. 修复路径引用（pyvenv.cfg）
3. 测试独立运行

---

## 📊 任务拆解

### Task 0.2.1：验证 Adapter 环境 ✅

**负责人**：待分配  
**预计**：15 分钟  
**验收**：preflight.py 通过

### Task 0.2.2：MJLab Smoke Test

**负责人**：待分配  
**预计**：30 分钟  
**验收**：训练 5 步成功

### Task 0.2.3：记录依赖清单

**负责人**：待分配  
**预计**：15 分钟  
**验收**：依赖列表 + 大小统计

### Task 0.2.4：便携化方案设计

**负责人**：待分配  
**预计**：1 小时  
**验收**：方案文档 + 可行性评估

---

## 🎯 MVP 目标（Phase 1）

**不需要**：
- ❌ 完整打包（Phase 2）
- ❌ 安装程序（Phase 2）
- ❌ 自动更新（Phase 3）

**只需要**：
- ✅ adapter 环境可运行
- ✅ smoke test 通过
- ✅ 依赖清单记录
- ✅ 便携化方案明确

---

## 🔗 相关文档

- [Microduck AGENTS.md](../../microduck_all/microduck_rl/AGENTS.md) — Smoke test 参考
- [ComfyUI 打包](../../auto_web/ComfyUI-aki-v3.2/) — 便携结构参考
- [PROJECT_VISION](../../PROJECT_VISION_LEGGED_STUDIO.md) — 技术栈
- [REFERENCE](../../REFERENCE_AND_RECOMMENDATIONS.md) — 便携式打包

---

**下一步**：执行 Task 0.2.1 验证 Adapter 环境
