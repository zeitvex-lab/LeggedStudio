# 路线图（Roadmap）

**口径**：基于 2026-09-08 对代码的逐包核实（见 [ARCHITECTURE.md](ARCHITECTURE.md)），取代本目录此前的三份分析文档（REFACTORING_PROPOSALS / MASTER_PLAN_OPTIONS / POSITIONING_OPTIONS——其中"任务只有 2 个/只有 Go2 可训练/local_tasks 前端摸不到"等结论**已被证伪**，详见 §1.3）。

---

## 1. 现状盘点（修正版）

### 1.1 已拥有的（真实家底）

- **16 机器人包全契约、全浏览器 sim2sim 试玩、29 个预训练 ONNX**：S/M/L 四足、轮足、双足（microduck/TRON1）、人形（G1/H1_2/D1）、灵巧手（wuji_hand）全覆盖。
- **55 个训练 profile 全量冒烟通过**（128 envs × 30 步）：velocity × 12 机型、Go2 六技能 + dreamwaq/amp-dreamwaq/wtw/parkour(PIE 深度)、G1 AMP + DeepMimic 跟踪（60 clips）、M20 DreamWaQ、microduck 18 技能、wuji reorient。
- **一套统一训练入口**：profile（`entrypoints.env/runner/runner_class` 延迟加载）→ 隔离 adapter 子进程 → ONNX + metadata 盖章 → 验收器 → 浏览器确定性回放。**这就是插件机制的雏形，且已被 55 个 profile 验证。**
- **三层实现来源**（generic builder / 精简本地源 / local_tasks 全框架），由同一入口消费。
- **Go2 的 local_tasks 框架**（192 py）：Spec 层（RobotSpec/TaskSpec/ExperimentSpec/PolicyContract 带维度校验）+ learning 组件（symmetry/motion/distill）+ workflows + 硬件无关 FSM（deploy/fsm.py，含 SAFETY_FALLBACK）。
- **桌面分发链路**：便携 EXE / Online 7z / 嵌入式 CUDA 三种形态 + release-check + Windows 验证脚本。
- **诚实的能力分级文化**：README/文档区分已验证/已内化/规划中，55/55、16/16 等数字可核查。

### 1.2 真实缺口

| 缺口 | 说明 |
|---|---|
| 契约双轨 + 无单一真值源 | RobotContractV2 与 local_tasks/PolicyContract 并存不互通；Pydantic 手写 ↔ 前端手写字段名，无 Schema→TS 生成 |
| 机器人 id 双命名 | 包 id 下划线 vs 浏览器特判连字符（`simulation_api.py:526`），新包接入必踩 |
| 浏览器 per-robot 硬编码 | GO2 地形根、机身高度三元式特判，违反自定"契约驱动禁特判"约束 |
| god file | simulation_api 1050 / training_api 924 / api_complete 40 个散装端点 / sim2sim app.js 5832 |
| 导出数值 gate 未强制 | replay_diff.py 存在但不在导出链路上强制执行 |
| 导航浅 | 航点回放（无 A*/地图编辑器/传感器仿真） |
| 感知未抽象 | PIE 深度在 Go2 包内，未成为可复用感知观测项 |
| 部署链未产品化 | Go2 FSM 骨架已有，实机 SDK/安全门禁/回溯未闭环（L4） |
| 前端工程纪律 | API base 三处硬编码、三套 three.js 并存、urdf-viewer React 原型未定去留 |

### 1.3 此前分析文档的错误结论（撤回记录）

| 曾结论 | 事实 |
|---|---|
| "任务只有 forward_walk/stairs" | recipe_registry 有 4 个通用任务；**55 个 profile** 横跨 10+ 任务类型 |
| "可训练只有 Go2 + microduck" | entrypoint 注册的框架包是 2 个，但**55 个 profile 覆盖 16 包全部可训**（generic/精简源/框架三来源） |
| "local_tasks 前端摸不到（任务双轨制）" | 前端 profileSelect 消费全部 55 profile，local_tasks 的任务经 profile 正常暴露 |
| "盲狗资源没有 / 无 FSM" | dreamwaq/amp_dreamwaq 已内化；Go2 deploy/fsm.py 已有 |
| "RL 运控知识库的能力大多缺失" | 知识库方法论大部分已落地（DR/课程/symmetry/distill/AMP），缺的集中在：分项 reward 监控、部署 gate、导航规划、感知抽象 |

> 教训已写入 [README.md](README.md) 的文档维护约定：**代码 > 文档**，硬数字必须能数出来。

---

## 2. 三条发展路线（互斥的北极星，按需选择）

三条路线的**起点相同**（§3 的地基项），分歧在第一优先级投入方向。不做具体方案排序推荐——这是产品定位决策，取决于你对"入门工具 / 生态平台 / 个人技术资产"的价值排序（此前的 POSITIONING_OPTIONS.md 保留其分析价值，但其"缺口"部分以本文 §1.2 为准）。

### 路线 A：入门与轻度使用工具（对外发布优先）

北极星：让不懂 RL 环境配置的人 30 分钟跑通"导入→训练→试玩"。
- 一键环境（离线 wheelhouse + preflight 报告页，替代半自动脚本）
- 训练可理解性：**分项 reward 曲线**（当前监控是聚合指标 + 小倍数网格，reward hacking 不可见——知识库 Ch06 硬要求）、训练健康面板与中文症状诊断（Ch25 路由表）
- 资产验证补全：碰撞体/惯量张量/actuator 参数/默认姿态/限位可视化检查
- 开箱试玩强化：预训练 ONNX 首页直达（29 个现成策略是天然素材库）
- 技术债清理以"不挡新手"为界（id 双命名、god file 拆分）

### 路线 B：生态平台（标准与插件优先）

北极星：第三方能照标准发布机器人包/任务包/感知包/部署目标。
详细实施已展开为 [ECOSYSTEM_PLAN.md](ECOSYSTEM_PLAN.md)（E0 地基 → E1 插件协议 v1 → E2 tasks-core 平台化 → E3 分发 → E4 第二后端）。要点：
- **契约统一为单一真值源**：以 local_tasks/PolicyContract 的字段级表达为参考，与 RobotContractV2 合并为 JSON Schema canonical → 生成 Pydantic/TS（这是生态的"宪法"）
- **把 profile entrypoints 机制正式化为插件协议**：manifest 2.0 声明 capabilities/runtime_requirements/license/integrity（robot_package.json 已有 capabilities 门控雏形，worker 的 `module:register` 延迟加载已是插件机制）
- local_tasks 的 core/learning 从 Go2 包抽出为平台库（tasks-core 独立 uv 包），Go2 变成第一个"照新标准写的示范包"
- 第二后端 adapter（先 RoboGauge 或 UniLab）验证抽象
- 前端 schema 驱动表单（新包零前端代码获得 UI）

### 路线 C：研究台架（个人技术资产优先）

北极星：可复现、可对比、可沉淀的腿足 RL 实验基础设施。
- **实验可复现**：ExperimentSpec 补完整 lineage（seed/依赖锁/哈希/resolved-config 落盘）+ 实验矩阵（algo×task×robot×seed）
- **对比视图**：训练曲线 + sim2sim 录像同屏对比（对标网站都未做，差异化空白）
- **方法论组件化**：把已内化的 dreamwaq/AMP/symmetry/distill/CaT 约束配上"什么时候用"决策卡（知识库 Ch25 可执行化）
- **部署吃透**：Go2 FSM 抽象为通用部署框架 + unitree_sdk2 实机 + Sim2Real 七层 gap 追踪（Ch23）+ ASAP/系统辨识（Ch12）
- **多后端交叉验证**：sim2sim 的正确研究用途——同策略跨后端数值对比

---

## 3. 共同地基（无论选哪条路线都先做，预计 2-3 周）

按依赖顺序：

| # | 任务 | 消除的债（ARCHITECTURE.md §7） | 验收 |
|---|---|---|---|
| G1 | 机器人 id 统一为下划线 + 契约 `pattern="^[a-z0-9_]+$"`，删除浏览器连字符特判集合 | 债 1 | 代码 grep 不到连字符 robot 特判；16 包 browser-config 全过 |
| G2 | per-robot 硬编码下沉数据：地形根、机身高度等入包 `simulation/config.json` / robot_package.json | 债 2 | simulation_api 无 per-robot 分支 |
| G3 | 契约 JSON Schema 化第一步：RobotContractV2 + policy-acceptance 出 Schema 文件 + 生成 TS 类型（前端只读引用） | 债 6 | 契约 roundtrip 测试；前端至少 1 处改用生成类型 |
| G4 | 导出强制双 gate：dummy forward 维度检查 + replay_diff 数值对比（<1e-5）接入导出链路 | 缺口"gate 未强制" | 无 gate 不生成部署包 |
| G5 | 机械债清扫：httpx2 拼写、requirements 双份、重复 ONNX、workspace/imports 清理、构建配置合一 + 资产清单入仓 | 债 7/8 | release-check 通过且仓库自包含 |
| G6 | API base 统一（`window.location.origin` + shared/api.js）+ 死代码定夺（web/urdf-viewer React 原型去留） | 债 9（前端纪律） | 非默认端口页面正常 |

**明确不做的**（范围纪律）：多机器人协同、视觉端到端、云端分布式、移动端（沿用 PROJECT_VISION 边界）。

---

## 4. 路线各自的第二阶段示例

- **A**：分项 reward 监控（native_worker 已有 tensorboard event——解析 event 分项上报）→ 训练健康页 → 资产深查页 → 一键环境。
- **B**：契约统一完成 → profile 插件协议 v1（manifest + capabilities + UI schema）→ local_tasks 抽平台库 → UniLab adapter spike。
- **C**：lineage 落盘 → 实验矩阵 + 对比视图 → FSM 通用化 + 实机 spike → Ch25 决策卡。

## 5. 里程碑验收原则（沿用既有文化）

- 每项能力落地必须带证据：冒烟脚本、测试文件或可复现命令。
- 文档同步更新且数字可核查（`find ... | wc -l` 级别）。
- 能力分级口径不变：已验证 / 已内化 / 规划中，禁止越级表述。
