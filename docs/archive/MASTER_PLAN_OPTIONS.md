# Legged Studio 总体重构方案（四选一）

**版本**：1.0
**日期**：2026-09-08
**前置文档**：[REFACTORING_PROPOSALS.md](./REFACTORING_PROPOSALS.md)（现状诊断与抽象层细节）
**本文目的**：针对完整产品愿景（环境一键配置 → 资产验证 → 图形化训练 → sim2sim/导航 → sim2real），给出四种**总体形态**候选，供决策。

---

## 愿景需求清单（作为四个方案的统一评分表）

| # | 需求 | 简称 |
|---|---|---|
| R1 | Windows 桌面程序，内置或一键配置环境，常用设置图形化 | 环境与设置 |
| R2 | Web 界面训练，前期 mjlab，后期可扩展其他框架 | 可扩展训练后端 |
| R3 | 训练前导入 URDF/MJCF：3D 查看、质量/碰撞体/惯量/电机参数/关节位置检查 | 资产验证 |
| R4 | 预设小/中/大型四足 + 四轮足参数，引入有参考价值的双足/人形 | 机器人生态预设 |
| R5 | 内置盲狗（盲走/本体感知）训练资源 + 常用感知资源 | 任务与感知资源 |
| R6 | 训练相关高度抽象、图形化、模块化、易理解、易扩展 | 图形化抽象 |
| R7 | 一键导入导出标准与复现（契约/artifact） | 标准与复现 |
| R8 | 方便导入自有机器人资产：验证→训练→仿真→部署 | 自有资产全流程 |
| R9 | sim2sim 仿真 + 简单手动操作 + 高级自动导航 | 仿真与导航 |
| R10 | 标准 sim2real 部署链路 | sim2real |

---

## 方案一：原地精修（保守派）

**一句话**：技术栈一行不动，只做结构性修复与分层，最快出可卖的产品。

### 形态

```
现有结构不变（Electron + FastAPI + 原生 MPA + adapters/mjlab 子进程）
只做六件事：
1. contracts/ 变 JSON Schema 真值源 → 生成 Pydantic + TS 类型
2. backend 拆 god file → services/ 业务层 + api/ 薄路由
3. recipe_registry 升级显式 TaskSpec 注册表（方案 A）
4. 前端 app.js 拆五模块 + shared/api.js + SSE
5. 机器人差异下沉 morphology 数据（R4 预设 = 内置 robot packages + recipe JSON）
6. 部署侧补 Deployment Contract + dummy forward + onnx replay 双 gate（方案 D 仿真侧）
```

### 愿景覆盖

- R1：保留现有 `stage:runtime` + 在线下载脚本，补 uv 离线 wheelhouse 锁定；设置页小改。
- R2：mjlab 唯一后端；第二后端靠"方案 B 接口"事后补，会有阵痛。
- R3/R8：现有 workbench 验证页增强（mesh 质量、actuator 表），资产包导入沿用 package_index。
- R4/R5：预设 = `assets/robots/` 内置包 + recipe 数据；盲狗资源 = 内置 motion/terrain 资产目录。
- R6：表单式图形化（param_registry 驱动），不做节点/流水线式编辑。
- R9：现有浏览器 sim2sim 增强；导航沿用 scenario_maps + navigation_api。
- R10：Step 6 部署包 + 双 gate；实机 FSM 模板 Phase 3。

### 评估

| 维度 | 评价 |
|---|---|
| 启动成本 | **最低**（不重写） |
| 到 MVP 时间 | **4-6 周** |
| 扩展性 | 中：加第二后端/感知模块要靠约定，无制度保障 |
| 长期上限 | 中低：两年后可能仍要面对方案二/三 |
| 风险 | **低** |
| 适合 | 想最快验证产品价值、单人节奏 |

---

## 方案二：内核 + 插件平台（扩展性派）

**一句话**：把"高度抽象、模块化、易扩展"做成产品的第一公民——内核只做四件事，其余一切（后端、机器人、任务、感知、导航、部署目标）都是带 manifest 的插件。

### 形态

```
kernel/                        ← 内核（稳定 API，语义化版本）
  schema_registry/             契约注册中心：所有插件的输入输出必须用注册 schema 描述
  capability/                  能力清单：插件声明 capabilities + 所需 runtime + 入口
  orchestrator/                Job 编排器：进程隔离、事件协议（SSE）、取消/恢复/崩溃回收
  store/                       资产/artifact 存储：哈希寻址 + lineage

plugins/                       ← 一切都是插件
  backend-mjlab/               训练后端插件（第一个）
  backend-isaaclab/            （后期）
  pack-robot-quad-s/  pack-robot-quad-m/  pack-robot-quad-l/
  pack-robot-wheel/   pack-robot-biped-ref/   ← R4：每个预设档一个机器人包
  pack-task-blind-walk/        ← R5：盲狗资源（本体感知 obs 库 + 地形 + DR 预设）
  pack-perception/             ← R5：heightfield/raycast/lidar 感知模块
  plugin-navigation/           ← R9：自动导航
  deploy-unitree-sdk2/  deploy-rlsar-template/   ← R10：部署目标插件

runtimes/                      托管运行时：按插件 manifest 的 runtime 声明自动 provisioning
                               （每个插件一把 uv lock，离线 wheelhouse，参考 ComfyUI-aki/pinokio）

apps/web                       前端 = 插件市场的宿主：页面由插件 schema 驱动渲染
                               （训练配置表单、观测映射板、奖励编辑器全部由插件声明生成）
```

### 关键机制

- **插件 manifest**（借鉴 1000framesai 算法 manifest + robot_lab `register_task(env_cfg="module:Class")` 延迟解析）：

```json
{
  "id": "pack-task-blind-walk", "type": "task_pack", "version": "1.0.0",
  "requires": {"kernel": ">=0.9", "backend": ["mjlab"]},
  "provides": {"tasks": ["BlindWalk-Flat-*", "BlindWalk-Rough-*"], "obs_terms": [...], "terrains": [...]},
  "runtime": {"python": "3.12", "lock": "uv.lock", "wheelhouse": "offline/"},
  "ui": {"config_schema": "schemas/blind_walk_config.json", "reward_groups": [...]}
}
```

- **前端图形化（R6）**：插件在 manifest 里给 `config_schema`，前端据此自动生成表单/映射板——新插件零前端代码即可获得 UI。这是"高度抽象、图形化"的制度化实现，而不是每加一个功能写一页 HTML。
- **环境一键配置（R1）**：runtime manager 读插件的 runtime 声明，自动创建隔离 venv、按 lock 安装、做 preflight（GPU/驱动/端口），用户只见"安装插件 → 一键配置 → 就绪"。
- **标准与复现（R7）**：契约注册中心强制所有 artifact 带 schema_version + 哈希 + lineage，导入导出 = artifact 包 + manifest。

### 愿景覆盖

全部 R1-R10 都有制度化的落点，尤其 R2/R4/R5/R6 是这套架构的原生能力。

### 评估

| 维度 | 评价 |
|---|---|
| 启动成本 | **高**：内核 API 设计错了代价大 |
| 到 MVP 时间 | 内核 6-8 周 + mjlab 插件迁移 2-3 周 |
| 扩展性 | **最高**：新后端/新任务/新感知 = 新插件 |
| 长期上限 | **最高**：可做生态/插件市场 |
| 风险 | 中高：单人开发时"为平台而平台"的过度设计风险 |
| 适合 | 把项目当长期平台/生态做 |

---

## 方案三：产品级全栈重写（理想派）

**一句话**：按最终产品形态一次到位——monorepo、React SPA、领域服务化、事件总线、托管运行时，全部重来。

### 形态

```
legged-studio/  (monorepo)
  packages/contracts/      JSON Schema 真值源 → 生成 TS + Pydantic + 文档
  apps/web/                React SPA：Vite + R3F + Zustand + Recharts
                           页面 = 7 步流程（StackForce 工作流条 + 1000framesai 控制台）
  apps/desktop/            Electron 薄壳：窗口/进程生命周期/升级，不含业务
  services/control_plane/  FastAPI 领域模块化：
                             assets(资产验证) / training / evaluation /
                             navigation / deployment / settings
  services/orchestrator/   Job 队列 + SSE 事件总线 + 进程 supervisor（崩溃回收）
  runtimes/                托管运行时（mjlab-py312 等：uv lock + 离线 wheelhouse + preflight）
  packs/                   内置资产包：S/M/L 四足、轮足、双足/人形参考、盲狗与感知资源
```

### 愿景覆盖

- R1：settings 一等公民页面 + runtime manager 内建（仿 ComfyUI-aki 启动器体验）。
- R3：资产验证页用 URDF Studio 的 parser/workspace 能力为基线重写为 React 组件。
- R6：React 组件化天然支撑复杂图形化（观测映射板、奖励编辑器、导航地图编辑器）。
- R9：sim2sim 页重写为"Three 渲染 / MuJoCo WASM 物理 / ORT 推理"三层组件；导航独立模块。
- R2/R10：control_plane 的领域服务 + orchestrator 为多后端和部署链路预留接口。

### 评估

| 维度 | 评价 |
|---|---|
| 启动成本 | **最高**：前端、后端、打包全部重写 |
| 到 MVP 时间 | **3-4 个月**，期间旧功能冻结 |
| 扩展性 | 高（但没有方案二的插件制度，靠代码分层） |
| 长期上限 | 高：产品质量上限最高 |
| 风险 | **高**：单人重写烂尾风险真实存在；5800 行 app.js 里沉淀的领域知识（地形、遥控、WASM 物理）重写即重新踩坑 |
| 适合 | 有整块时间、追求产品完成度、能接受数月无新版本 |

---

## 方案四：绞杀者渐进（推荐 · 务实派）

**一句话**：新内核先行，旧功能逐步绞杀替换（Strangler Fig）——以方案一的低风险启动，以方案二的内核形态为北极星，每个阶段都有可用产品。

### 演进路线

```
Phase A（2-3 周）：抽"内核三件套"作为新骨架，与现有 backend 并存
  ├─ packages/contracts     JSON Schema 真值源（生成 Pydantic + TS）
  ├─ services/registry      TaskSpec/RobotPack/AlgorithmManifest 注册表 + 能力清单
  └─ services/orchestrator  Job 编排器（子进程 + SSE 事件 + 状态机）
  现有 api_complete.py 保留运行；新 API 全部挂新骨架。

Phase B（4-6 周）：Go2 纵向切片走新骨架（MVP）
  资产验证 → 训练 → 监控(SSE) → ONNX + 双 gate → 部署包
  旧 sim2sim 页保持可用（不重写，只拆模块止血）。

Phase C（持续）：按价值排序逐页绞杀旧前端
  训练配置(表单由 schema 驱动) → sim2sim 五层拆分 → 资产验证 → 导航
  每替换一页，旧页面对应路由下线；环境管理器独立成 runtime 服务。
```

### 与方案一/二/三的关系

- 启动方式 = 方案一（不重写、低风险）；
- 目标架构 = 方案二的内核 + 插件形态（插件 manifest 在 Phase C 后期引入，一开始注册表条目就是"内部插件"，API 稳定后再开放）；
- 避免方案三的"数月无新版本"风险；
- 任何阶段停下，手里都是一个比现在更好的可用产品。

### 愿景覆盖节奏

| 阶段 | 落地的需求 |
|---|---|
| Phase A | R7（契约真值源）打底 |
| Phase B | R2/R3/R8/R10 仿真侧 + R1 环境锁定 |
| Phase C 前半 | R6（schema 驱动表单）、R4（预设包数据化）、R9 sim2sim 增强 |
| Phase C 后半 | R5（盲狗/感知资源包）、R9 导航、R10 实机、R1 runtime manager 完整版 |

### 评估

| 维度 | 评价 |
|---|---|
| 启动成本 | 低（同方案一） |
| 到 MVP 时间 | 6-9 周 |
| 扩展性 | 高（演进到插件制度，且插件 API 是从真实使用中长出来的，不是凭空设计） |
| 长期上限 | 高 |
| 风险 | 低中：主要风险是新旧并存期的双份维护纪律 |
| 适合 | 单人长期投入、既要快速出活又要平台上限 |

---

## 四方案对比总表

| 维度 | 一：原地精修 | 二：内核+插件 | 三：全栈重写 | 四：绞杀者渐进 |
|---|---|---|---|---|
| 启动成本 | ★ 最低 | ★★★ 高 | ★★★★ 最高 | ★★ 低 |
| MVP 时间 | 4-6 周 | 9-11 周 | 12-16 周 | 6-9 周 |
| 扩展性（R2/R4/R5/R6） | 中 | **最高** | 高 | 高（渐进到位） |
| 产品上限 | 中低 | 高 | **最高** | 高 |
| 重写风险 | 无 | 中 | **高** | 低 |
| 插件/生态能力 | 无 | 原生 | 无（靠分层） | 后期获得 |
| 前端形态 | 原生 MPA（修补） | schema 驱动 + 模块化 | React SPA 全新 | 先修补后逐页替换 |
| 单人可执行性 | **最好** | 中 | 最差 | **好** |

## 我的推荐

**方案四（绞杀者渐进），北极星定为方案二的内核+插件形态。**

理由：
1. 你最大的资产是已跑通的 Go2 纵向切片和 5800 行 app.js 里沉淀的 WASM 物理/地形/遥控领域知识——方案三会把它扔进重写风险，方案四把它变成"最后才需要动的稳定存量"。
2. 愿景里的 R2/R4/R5/R6 本质上都是"插件化"诉求，但插件 API 凭空设计必错（方案二的风险）；方案四让注册表条目先在内部当"准插件"用，API 从真实使用中长出来再开放。
3. 单人开发，每个阶段都有可用产品是保命线。

前端路线建议随方案四定为：**保持原生 ES Modules 不引框架**（1000framesai 已验证可行），把纪律补齐（模块化 + shared/api.js + SSE + schema 驱动表单）；仅当 Phase C 后期"观测映射板/导航地图编辑器"的交互复杂度真的撑不住时，再单页点状引入 React（ Islands 式），不全站重写。
