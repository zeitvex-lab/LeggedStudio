# 生态平台实施方案（Ecosystem Plan）

**版本**：1.0（2026-09-08）
**定位**：[ROADMAP.md](ROADMAP.md) 路线 B 的展开。目标：让第三方开发者照标准发布机器人包 / 任务包 / 感知包 / 部署目标，用户一键安装组合。
**核心判断**：这个项目离生态比想象中近——`extension_entrypoint` 机制已经是插件加载，55 个 profile 已经在用统一的 entrypoints 接缝，`robot_package.json` 的 capabilities 已经是能力门控。**要做的不是发明新机制，而是把现有机制正式化、文档化、可验证化。**

---

## 0. 生态平台的成功定义

先说清楚什么叫做成了（避免"为平台而平台"）：

| 里程碑 | 判据 |
|---|---|
| E1 完成 | 一个**没读过源码**的外部开发者，按文档 + 脚手架，半天内做出一个可训练、可试玩的新机器人包，并通过校验 CLI |
| E2 完成 | Go2 的 local_tasks core 变成平台库，Go2 包是"照新标准写的第一个示范包"，二者不再耦合 |
| E3 完成 | 插件 ZIP 可离线分发：导出 → 传给别人 → 导入 → 校验 → 训练，全程不碰源码树 |
| E4 完成 | 第二个训练后端（UniLab 或 RoboGauge）以 adapter 形式接入，同一机器人包/任务包不改代码可在两个后端上跑通冒烟 |
| 长期 | 出现第一个**非本人**制作的插件 |

**明确不做**：在线插件市场/服务器、签名与信任体系、沙箱执行（继续用子进程隔离）、依赖解析器（继续用 uv lock）——这些是"有了第三方生态之后"的问题，不是现在的问题。

---

## 1. 现有基础盘点（已经是插件雏形的机制）

| 现有机制 | 位置 | 离插件协议差什么 |
|---|---|---|
| 包清单 + capabilities 门控 | `robot_package.json`（robot-package-1.0）；`backend/robot_packages.py` 枚举透传、browser-config 422 门控 | 无版本协商、无 license 字段、无 hash/出处、无 runtime_requirements（microduck 有但非标准） |
| 扩展入口 | `extension_entrypoint: "module:register"` + `extension_root`，worker 延迟加载（`native_worker.py::_load_package_extension`，不按 robot 分支） | 未文档化为公开协议；注册返回值无 schema；无沙箱外的安全性约定 |
| 训练 profile | `training-profile-1.0`：`entrypoints.env/runner/runner_class` + runner 默认值 + command_ranges | 未暴露"这个 profile 需要哪些 capability/依赖"的声明；UI 表单靠 param_registry 内省，非声明式 |
| 契约 | `contracts/robot_contract_v2.py`（Pydantic）+ ONNX metadata 盖章 | 无 JSON Schema 真值源，前端手写字段名，第三方语言无法校验 |
| 导入导出 | 项目 ZIP（`/api/project/export|import`）、机器人包导入、`package_index.json` 持久索引 | 包 ZIP 无版本/哈希/出处元数据；无"包目录"（catalog）格式 |
| 校验工具 | `tools/validate_training_smoke.py`（55/55 冒烟）、`policy_acceptance.py --probe`、`contracts/validator.py` | 分散、未串成"第三方包一键自检" |

---

## 2. 总体架构：内核 + 插件

```
┌────────────────────────────────────────────────────────────┐
│ Legged Studio 内核（本仓库）                                 │
│                                                            │
│  contracts/schema/     JSON Schema 真值源（生态的"宪法"）      │
│  tasks-core/           平台任务库（local_tasks core 抽出）     │
│                        RobotSpec/TaskSpec/ExperimentSpec/   │
│                        PolicyContract/Catalog/compose       │
│  backend/              控制面：插件注册表/安装/校验/门控         │
│  adapters/<backend>/   后端适配器（mjlab 第一个，unilab 第二个） │
│  web/                  schema 驱动的配置 UI                   │
└────────────────────────────────────────────────────────────┘
        ▲ manifest+ZIP 进            ▼ artifact+ZIP 出
┌────────────────────────────────────────────────────────────┐
│ 插件（独立分发单元，目录即插件）                                │
│  robot pack     机器人：MJCF+网格+contract+simulation 配置     │
│  task pack      任务：mdp 实现 + profiles（依赖 tasks-core）   │
│  backend pack   训练后端 adapter（锁 uv.lock，Phase 4 开放）   │
│  deploy pack    部署目标：契约模板 + FSM 模板 + 代码生成         │
└────────────────────────────────────────────────────────────┘
```

**设计原则**（沿用项目既有约束）：
1. **数据驱动，禁止按 robot_id 分支**——插件差异全部进 manifest。
2. **进程隔离**——插件代码只在 adapter 子进程执行，控制面永不 import 插件的训练栈。
3. **能力分级诚实**——插件声明的能力必须能被校验 CLI 验证，不能自封。

---

## 3. 分阶段实施

### Phase E0：生态地基（2-3 周）＝ ROADMAP 共同地基 G1-G6

生态平台的宪法先行，不另起炉灶：

| 任务 | 产出 | 生态意义 |
|---|---|---|
| 契约 Schema 化 | `contracts/schema/robot-contract-2.0.schema.json` + policy-acceptance / training-profile / robot-package 四个 schema 文件；`datamodel-code-generator` 生成 Pydantic、`json-schema-to-typescript` 生成 `web/shared/generated/types.d.ts` | 第三方语言（含 JS 前端、将来的 C++ 部署模板）都校验同一份 schema；robot_id 强制 `^[a-z0-9_]+$`（灭双命名债） |
| per-robot 硬编码下沉 | `simulation_api.py` 连字符集合、Go2 地形根、机身高度特判全部入包配置 | 第三方机器人不再需要改内核代码 |
| 包导入导出自包含 | `QUADRUPED_ASSET_INVENTORY.json` 入仓、构建配置合一 | 分发不再依赖开发者机器的目录布局 |

**验收**：契约 roundtrip 测试过；16 包 browser-config 全过；release-check 通过。

---

### Phase E1：插件协议 v1（3-4 周）——本方案的核心交付

#### 1.1 manifest 升级：robot-package-2.0

在现有 robot-package-1.0 基础上**只增不改**（向后兼容，1.0 包继续可读）：

```jsonc
{
  "schema_version": "robot-package-2.0",
  "package_id": "my_robot",                      // ^[a-z0-9_]+$（schema 强制）
  "display_name": "My Robot",
  "version": "1.0.0",                            // ★新增：semver
  "license": {                                   // ★新增：分发合规门（参考审计的风险清单）
    "code": "MIT",
    "assets": "CC-BY-4.0",                       // mesh/URDF 逐项标明
    "upstream": ["https://github.com/..."],      // 署名链
    "redistribution_allowed": true
  },
  "capabilities": ["generic_mjlab", "mujoco_sim", "mjlab_source_profiles"],
  "runtime_requirements": {                      // ★从 microduck 的私有字段转正
    "python": ">=3.12,<3.13",
    "mjlab": ">=1.6,<2.0",
    "torch": ">=2.7",
    "tasks_core": ">=0.1,<0.2"                   // ★依赖平台任务库的版本
  },
  "model": { "format": "mjcf", "path": "model/robot.xml", "assets_path": "model/assets" },
  "contract_path": "contract.json",
  "extension": {                                 // ★从顶层字段收编为对象（兼容旧字段）
    "entrypoint": "my_robot_tasks.extension:register",
    "root": "training/source"
  },
  "simulation_config_path": "simulation/config.json",
  "integrity": {                                 // ★新增：导入/分发时校验
    "algorithm": "sha256",
    "manifest_hash": "...",                      // 除本字段外全包哈希
    "created_by": "legged-studio 0.9.0"
  }
}
```

#### 1.2 task-pack 协议（新）

任务包目前只能寄生在机器人包的 `training/source/` 里（如 local_tasks 寄生在 Go2 包）。协议 v1 让任务成为独立分发单元：

```
my_task_pack/
  plugin.json                 # task-package-1.0
  mdp/                        # actions/observations/rewards/events/commands（可复用组件）
  tasks/
    <robot>/<task>/profile.json   # 引用 robot pack（不内嵌）
  motions/                    # 参考动作 NPZ（自描述 schema，见 ROBOT_PACKAGE §1）
```

```jsonc
// plugin.json (task-package-1.0)
{
  "schema_version": "task-package-1.0",
  "task_pack_id": "blind_walk",
  "version": "1.0.0",
  "license": { "code": "Apache-2.0" },
  "requires": {
    "tasks_core": ">=0.1,<0.2",
    "backends": ["native_mjlab"],
    "robot_capability": "generic_mjlab"       // 声明适配哪类机器人（能力交集门控）
  },
  "provides": {
    "profiles": ["tasks/<robot>/<task>/profile.json"],
    "obs_terms": ["mdp/observations.py"],     // 可被其他任务包复用的观测项
    "reward_terms": ["mdp/rewards.py"]
  },
  "ui": {                                     // ★schema 驱动 UI（见 1.4）
    "config_schema": "schemas/blind_walk.config.schema.json",
    "display_groups": [...]
  }
}
```

**组合规则**：训练解析时 `robot pack ∩ task pack`——机器人提供资产/契约/执行器，任务包提供 mdp/profile，二者通过 contract 的关节序与 capability 交集匹配，不匹配 fail-closed 并给出中文原因。

#### 1.3 解析与校验链（内核侧改动点）

| 内核文件 | 改动 |
|---|---|
| `backend/robot_packages.py` | 支持 robot-package-2.0 字段透传（version/license/integrity/runtime_requirements）；索引 `package_index.json` 增加 version/hash/provenance 字段 |
| 新增 `backend/plugin_registry.py` | 统一注册表：robot packs + task packs + (未来 backend/deploy packs)；提供组合解析 `resolve(robot_id, profile_id) -> ResolvedPlan`（哪些 entrypoint、哪些 capability 检查、依赖满足与否） |
| `adapters/mjlab/native_worker.py` | `_load_package_extension` 泛化为"加载任一 plugin 的 entrypoint"（机制已具备，改数据来源）；加载后校验 register 返回值符合 schema |
| 新增 `scripts/ls_plugin.py` | **第三方一键自检 CLI**（E1 的关键交付）：`validate <pack_dir>` 串起——manifest schema 校验 → contract schema 校验 → MJCF `MjModel.from_xml_path` 编译 → entrypoint 子进程 import 解析 → `--probe` 物理包络 → （有 profile 时）`validate_training_smoke` 单包冒烟。输出 pass/fail 报告，即第三方包的"质检证" |
| 新增 `scripts/new_robot_package.py` | 脚手架生成器：交互式生成符合 2.0 的包骨架（含正确关节序模板、capabilities、校验脚本调用示例）——E1 验收"外部开发者半天出包"靠它 |

#### 1.4 schema 驱动 UI

现状：`param_registry`/`config_introspect` 从 adapter 内省配置树 → `/api/training/profile-schema` → 五分类编辑器。升级：

- profile/任务包的 `ui.config_schema`（JSON Schema form 格式）优先；无 schema 时回退现有内省（兼容 55 个存量 profile）。
- 前端 `training_create.html` 的表单渲染器读 schema 生成控件——**新任务包零前端代码获得配置 UI**。这是"图形化、易扩展"的制度化。

**E1 验收**：(a) 用脚手架 + 文档做出一个假机器人（如改缩放的 Solo12），`ls_plugin.py validate` 全绿、冒烟通过、浏览器可试玩；(b) 55 个存量 profile 在新解析链上零回归（跑全量 smoke）；(c) 协议文档发布到 `docs/PLUGIN_SPEC.md`。

---

### Phase E2：tasks-core 平台化（2-3 周）

把 Go2 包内的 `local_tasks` core/learning 层抽出为可独立安装的平台库：

```
tasks-core/                  # 新的独立 uv 包（仓库内 monorepo 目录）
  src/ls_tasks_core/
    spec/                    # RobotSpec/TaskSpec/TrainingSpec/ExperimentSpec/PolicyContract/Catalog
    learning/                # algorithms/models/rollout/storage/motion/symmetry
    workflows/               # train/play/export/rollout/distill（后端无关部分）
  pyproject.toml             # 独立版本号、semver；依赖仅 numpy/pydantic（不依赖 mjlab）
```

- **依赖方向**：`tasks-core 不依赖 mjlab`（spec 层是纯数据契约）；mjlab 绑定留在各包的 `integrations/mjlab/`（现有结构已如此，顺势保留）。
- **分发**：adapter venv 按 `runtime_requirements.tasks_core` 安装固定版本；插件包**不 vendor** 内核库（与 unitree_rl_mjlab_go2w 反模式相反——参考项目审计的结论：框架当外部依赖，项目只含 tasks+assets）。
- **迁移**：Go2 包改为依赖 tasks-core，`local_tasks` 里 Go2 专属部分（robots/go2/…）留在包内；迁移后 Go2 就是"照新标准写的示范包"。G1 amp/tracking、microduck 同批迁移。
- **版本纪律**：tasks-core 0.x 期间允许破坏性变更，但每次变更必须同步更新 schema 与迁移说明；1.0 起承诺 semver。

**E2 验收**：Go2/G1/microduck 三包在新 tasks-core 上 55 profile 冒烟零回归；tasks-core 有独立测试（PolicyContract 校验、Catalog 组合、symmetry 单测从 Go2 包迁出）。

---

### Phase E3：分发与目录（2 周）

- **包 ZIP 格式 v1**：manifest `integrity.manifest_hash` + 导入时校验（hash 不符拒绝导入）；导入路径沿用 `robot_packages.py::upsert_package`，增加 version/provenance 记录。
- **目录格式（catalog）**：`catalog.json` = `[{package_id, version, manifest_hash, url, summary, license}]` 的清单文件，支持"从本地目录/URL 安装"。MVP 就是一个可分享的 JSON 文件——不做服务器。
- **工作区卫生**：`workspace/imports/` 的 TTL 清理（99 个 hex 残留问题的制度化修复），导入包有明确"试用/已安装"状态。
- **许可合规门**：`ls_plugin.py validate` 强制检查 `license` 字段完整性（参考 DEEPROBOTICS_PORTING 的署名链教训——这是对外分发的法律底线）。

**E3 验收**：把 Go2 包导出 ZIP → 删除 → 从 ZIP 重装 → 55 冒烟 + 浏览器试玩零差异；用 catalog.json 装/卸一个第三方包全程无源码操作。

---

### Phase E4：第二后端验证抽象（3-4 周，可与 E3 并行准备）

- 定义 `BackendAdapter` 协议（`list_tasks / launch_train / launch_export / launch_sim2sim / preflight`，全部返回 JobHandle/JSON，不 import 训练栈——现有 mjlab adapter 已天然符合，抽接口即可）。
- 第二后端选 **RoboGauge**（评估服务，独立 py311 venv，风险低）或 **UniLab**（训练框架，Hydra 配置，验证 task-pack 的 backend 维度）。推荐先 RoboGauge：它只消费 artifact，不动训练链。
- framework 选择 UI 已有 planned 占位（`/api/training/options` 的 `frameworks` 数组），接入即亮灯。

**E4 验收**：同一 Go2 velocity artifact 在 mjlab 训练 → RoboGauge 评估（或 UniLab 冒烟）打通；`/api/training/options` 显示两个可用 backend。

---

## 4. 关键设计决策记录（为什么这样做）

| 决策 | 选择 | 理由 |
|---|---|---|
| 插件粒度 | 目录即插件（ZIP 分发），不是 pip 包 | 与现有包机制/工作区一致；用户不碰 Python 环境 |
| manifest 演进 | 2.0 只增不改，读旧写新 | 55 个存量 profile / 16 包零迁移成本 |
| 任务与机器人分离 | task pack 独立，靠 capability 交集组合 | 盲走/parkour 这类任务天然跨机器人（dreamwaq 已在 Go2/M20 双包出现，正是分离需求的证据） |
| tasks-core 独立包 | monorepo 内独立 uv 包，semver | spec 层是生态 API；包内 vendor 框架是已被审计点名的反模式 |
| UI | schema 驱动优先，内省兜底 | 存量 55 profile 不用补 schema 也能继续工作 |
| 信任模型 | hash 完整性 + license 门，无签名/市场 | 单人维护阶段的正确量级；协议留 version 字段未来可升 |
| 第一个第三方插件 | 自己用协议写一个"外来"机器人（Solo12 或 ANYmal-B） | 狗食自己吃：协议粗糙处第一时间暴露 |

---

## 5. 风险与对策

| 风险 | 对策 |
|---|---|
| 协议设计错误后改动成本大 | E1 只承诺 0.x（manifest version 字段允许破坏性升级），E3 后才冻结 1.0；每步都有"外来包"实测 |
| 单人维护面扩大 | 内核改动集中在 `plugin_registry.py` + schema；插件全部走标准子进程路径，不给内核加运行时分支 |
| 第三方包质量参差 | `ls_plugin.py validate` 是唯一准入：不过校验的包不进索引（fail-closed，沿用项目既有验收文化） |
| 许可合规 | license 字段强制 + 校验门 + 审计清单（DEEPROBOTICS_PORTING 风险节）作为模板 |
| 前端复杂度 | schema 驱动 UI 反而降低复杂度（删手写表单），不引框架（维持原生 ESM 路线） |

---

## 6. 时间线总览

```
E0 地基（2-3周）: Schema化 + 硬编码下沉 + 构建自包含
E1 插件协议 v1（3-4周）: manifest 2.0 + task-pack + ls_plugin 校验CLI + 脚手架 + schema UI
E2 tasks-core 平台化（2-3周）: spec/learning 抽独立包，Go2 改示范包
E3 分发（2周）: ZIP hash + catalog.json + 许可门
E4 第二后端（3-4周）: BackendAdapter 协议 + RoboGauge/UniLab 接入
─────────────────────────────────────────────────────
约 3 个月后：外部开发者可照 docs/PLUGIN_SPEC.md + 脚手架，
半天产出可训练、可试玩、可分发的机器人/任务包。
```

每阶段结束都更新 [ARCHITECTURE.md](ARCHITECTURE.md) 的能力分级与本文档的状态标注——生态平台的每一项承诺都必须落在"已验证"栏里才作数。
