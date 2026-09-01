# Legged Studio

足式机器人强化学习工作台

---

## 项目愿景

详见：`../PROJECT_VISION_LEGGED_STUDIO.md`

**核心定位**：
- 🖱️ Windows 桌面应用
- 🌐 Web 界面
- 🤖 6 种分类（S/M/L × 点足/轮足）
- 🔄 全流程闭环（验证→训练→仿真→部署）
- 📊 契约驱动

---

## 参考资源

- **项目愿景**：`../PROJECT_VISION_LEGGED_STUDIO.md`
- **参考清单**：`../REFERENCE_AND_RECOMMENDATIONS.md`
- **资产清单**：`../QUADRUPED_ASSET_INVENTORY.md`
- **1000frames 参考**：`../references_1000framesai/`

---

## 快速开始

### 1. Electron 桌面启动器（推荐）
```bash
npm start
```

启动器会自动定位项目资源、Python 运行时和资产清单；进入桌面后点击“启动控制平面”即可启动后端。Windows 下即使系统设置了 `ELECTRON_RUN_AS_NODE`，启动脚本也会自动清理该变量。

首次安装依赖：

```bash
npm install
```

当前内置可训练资产：Unitree Go2（M-P，12 DOF）和 Unitree Go2W（M-W，16 DOF）。训练页从 `/api/robots/presets` 加载版本化 Contract，不再使用虚构的 URDF 路径；worker 会直接加载 canonical MJCF，执行 MuJoCo rollout 和 PPO update，并保存真实 PyTorch checkpoint 与 PolicyArtifact。详细资产和适配器说明见 [docs/GO2_TRAINING_ASSETS.md](docs/GO2_TRAINING_ASSETS.md)。

训练页支持按任务编辑奖惩项：每项可独立关闭或修改权重，配置会随训练任务保存。算法切换入口只展示已完成真实适配的算法；当前为 PPO，SAC/TD3 会明确标记为未接入。

当前 MVP 工作流已包含资产浏览、Contract 训练、任务监控、策略产物和本地评估工作台，详见 [docs/WORKFLOW_IMPLEMENTATION.md](docs/WORKFLOW_IMPLEMENTATION.md)。

### 2. 或手动启动
```bash
# 仅在无桌面环境时手动启动后端
python backend/api_complete.py

# 访问控制台
http://127.0.0.1:8765
```

---

## 桌面发布

生成 Windows 未压缩目录（用于本机验证）：

```bash
npx electron-builder --dir
```

生成 portable 发布包：

```bash
npm run build
```

打包会携带 `backend`、`contracts`、`pipeline`、适配器源码和 `QUADRUPED_ASSET_INVENTORY`，不会携带适配器虚拟环境目录。

## Phase 1 任务

见 [TODO.md](TODO.md)

**优先级**：
1. 分析 1000frames 参考设计（`../references_1000framesai/`）
2. 改进 Web 界面
3. ONNX 导出功能
4. 预训练模型库

---

## 技术文档

- `docs/` — 技术文档
- `README.md` — 本文件
- `TODO.md` — 任务清单
