# 系统架构（Architecture）

**口径**：本文描述 0.9.0 的**真实**架构，所有数字可在代码中核查。能力声明分三级：**已验证**（有测试/冒烟证据）、**已内化**（代码存在且冒烟通过）、**规划中**（有接口或文档，未实现）。

---

## 1. 进程模型

```
Electron launcher（薄壳：生命周期/端口/运行时配置，不含业务）
  └─► FastAPI control plane（backend/api_complete.py，Python 3.12 轻量 venv）
        ├─ contracts/        契约模型与校验（Pydantic，无 torch）
        ├─ backend/          REST API：training / simulation / models / project /
        │                    evaluation / navigation / export / pretrained / robots
        ├─ assets/robots/    16 个内置机器人包（数据 + 训练源码）
        ├─ web/              静态工作台 + 浏览器 sim2sim（WASM，不走后端推理）
        └─ subprocess ──► 隔离 MJLab adapter venv（Torch + Warp + MuJoCo-Warp + RSL-RL）
                            adapters/mjlab/：launcher → native_worker / train_worker
```

**核心约束（已验证）**：控制面 venv 不装 Torch/Warp；训练一律由 adapter 子进程执行，控制面只通过版本化 JSON 任务状态与 artifact 清单与其通信。

**已知边界渗漏（技术债，见 §7）**：`backend/export_api.py` 顶层 import `adapters.mjlab.onnx_exporter`（其顶层 import torch），靠 `api_complete.py` 的 try/except 兜底；`backend/simulation_api.py` import 不依赖 torch 的 `ContractMujocoEnv`。"控制面不 import 训练栈"目前靠**依赖不安装**保障，不是代码边界。

---

## 2. 训练体系：三种来源，一条入口

训练入口统一为「训练 profile」（`training/profiles/*.json`，schema `training-profile-1.0`，字段见 [ROBOT_PACKAGE.md](ROBOT_PACKAGE.md) §3）。前端训练页通过 `profileSelect` 选择 profile（`web/training_create.html`），后端 `/api/training/profile-schema` 返回该 profile 的内省配置树。**16 包共 55 个 profile 全部通过 `tools/validate_training_smoke.py`（128 envs × 30 步）冒烟验证（已验证）**。

三种实现来源，由浅入深：

| 来源 | 机制 | 覆盖 |
|---|---|---|
| ① generic builder | `adapters/mjlab/generic_task_builder.py` 按 Contract 从零构环境 | 无本地源码的包：A1、B2、B2W、D1、TRON1 PF/SF |
| ② 精简本地源 | 包内 `training/source/<r>_velocity/`（env_cfg + robot_constants） | A2、H1_2、Go2W、ZEX-W、Lite3、B2 等 velocity |
| ③ 完整本地任务框架 | 包内大型 `training/source/` 库 + `extension_entrypoint` 注册 | Go2（local_tasks，192 py）、G1（amp/tracking/velocity）、microduck（mjlab_microduck，18 profiles）、wuji_hand（wuji_tasks）、M20（velocity + dreamwaq） |

profile 的 `entrypoints.env` / `entrypoints.runner` / `entrypoints.runner_class`（`module:callable` 字符串，延迟加载）是三种来源的统一接缝——**这就是本项目的"插件机制"**，只是目前仅对包内源码开放。

### 2.1 local_tasks 框架（Go2 包内，项目最深的一套抽象）

`assets/robots/unitree_go2/training/source/local_tasks/`（192 个 py），六层：

```
core/         RobotSpec / TaskSpec / TrainingSpec / ExperimentSpec /
              PolicyContract(观测字段/历史/归一化/动作scale，带维度校验) / Catalog / compose
learning/     algorithms / models / rollout / storage / motion / symmetry(左右镜像增强)
robots/       go2(mdp库+tasks+training+deploy) / g1(tasks+training)
workflows/    train / play / export / rollout / distill(蒸馏)
runtime/      policy_bundle / sim_to_sim / bundle_runtime
integrations/mjlab/   唯一后端绑定层
```

Go2 任务 catalog（`robots/unitree/go2/tasks/catalog.py`）：velocity-flat / velocity-rough / trot / jump / spring-jump / backflip / handstand / leggedstand，另有 dreamwaq（盲走）、amp_dreamwaq（AMP 模仿）、walk-these-ways、parkour（PIE 深度视觉，`rl/pie_model.py`）。

**注意**：这套框架目前**只被 Go2 使用**。它的 core/spec 层（尤其 PolicyContract + Catalog）质量高于 backend 表面契约，是后续统一契约/插件化的候选基座，但当前属于"已内化、未平台化"。

### 2.2 算法覆盖

- **PPO**：唯一已验证可运行算法（RSL-RL 系）。
- **AMP / DreamWaQ / DeepMimic 跟踪**：以"任务 + 自定义 runner_class"形式实现（G1 amp、go2 amp-dreamwaq、M20 dreamwaq、g1-tracking），不是通用算法注册项。
- **SAC / TD3**：注册表占位 `available=False`（`adapters/mjlab/algorithms/registry.py`），off_policy.py 有实现骨架，未验收。

---

## 3. 资产家底（16 包，2026-09 核实）

| 包 | 构型 | 训练源 | Profiles | 预训练 ONNX |
|---|---|---|---:|---:|
| unitree_go2 | 四足 M | local_tasks（192 py） | 12 | 2 |
| microduck | 双足 | mjlab_microduck | 18 | 9 |
| unitree_g1 | 人形 | g1_amp/tracking/velocity | 5 | 5 |
| wuji_hand | 灵巧手 | wuji_tasks（72 py） | 2 | 0 |
| deeprobotics_m20 | 轮足 M | m20_velocity + m20_dreamwaq | 2 | 1 |
| deeprobotics_lite3 | 四足 S | lite3_velocity | 1 | 1 |
| unitree_go2w | 轮足 M | go2w_velocity | 2 | 3 |
| unitree_a2 | 四足 L | a2_velocity | 2 | 0 |
| unitree_h1_2 | 人形 | h1_2_velocity | 2 | 0 |
| zex-w | 轮足 | robot/ + mjcf/ | 3 | 4 |
| agibot_d1 | 人形 | d1_velocity | 1 | 1 |
| unitree_a1 | 四足 S | a1_velocity | 1 | 1 |
| unitree_b2 | 四足 L | b2_velocity | 1 | 1 |
| unitree_b2w | 轮足 L | b2w_velocity | 1 | 1 |
| limx_tron1_pf | 双足点足 | pf_velocity | 1 | 0 |
| limx_tron1_sf | 双足球足 | sf_velocity | 1 | 0 |

合计：**55 profiles / 29 个预训练 ONNX / 16 包全契约、全浏览器可仿真**。S/M/L 四足、轮足、双足、人形、灵巧手全覆盖；任务谱系含 velocity、trot、jump/backflip/spring-jump（ aerial）、handstand/leggedstand（balance）、dreamwaq（盲走）、AMP/DeepMimic（模仿）、parkour（视觉）、reorient（灵巧手）、roller/roulade/ball-kick 等微duck 技能。

**机器人包运行时**：读取的是 `workspace/packages/<id>/` 副本（`package_index.json` 持久索引驱动，非文件系统扫描）；源树 → 副本为单向 refresh（`POST /api/robots/packages/refresh`），改包后必须刷新。

---

## 4. 契约体系

当前并存两套，职责不同：

| 契约 | 位置 | 覆盖 | 状态 |
|---|---|---|---|
| **RobotContractV2**（robot-contract-2.0） | `contracts/robot_contract_v2.py` | 尺寸/质量、关节（actuated/passive）、观测/动作布局、控制频率、joint_ids_map 桥接 | 已验证（validator + fixture + 测试） |
| **PolicyContract**（local_tasks） | `local_tasks/core/policy_contract.py` | 观测字段级（name+width）、历史帧长度/顺序/重置、归一化、action_scale、关节序 | 已内化（带维度一致性校验），仅 Go2/G1 用 |
| **ONNX metadata_props 盖章** | `native_worker.py::export_runner_policy_onnx` | joint_names/kp/kd/default_pos/observation_names/action_scale/clip_actions | 已验证，浏览器加载时校验（`validatePolicyMetadata`） |
| Scenario / PolicyArtifact / policy-acceptance / simulation-config / training-profile | contracts/ 与包内 schema | 场景、训练产物、验收报告、仿真配置、训练档案 | 已验证 |

**已知债**：契约真值源是 Pydantic 手写模型，无 JSON Schema canonical，前端 TS 类型靠手写字段名对齐（无自动生成）；RobotContractV2 与 PolicyContract 不互通。两套契约的统一是后续契约 v3 工作的起点。

---

## 5. 数据流（一次训练的完整链路）

```
选包(profileSelect) → /api/training/profile-schema（内省配置树 → 五分类编辑器）
  → POST /api/training/create（TrainingManager 落 task_dir）
  → TrainingLauncher：adapter venv 子进程（native_worker）
      ├─ 加载包 extension_entrypoint / entrypoints.env·runner
      ├─ ManagerBasedRlEnv 训练（tensorboard 日志 + checkpoint）
      └─ 训练完成：导出 exported/policy.onnx + metadata_props 盖章
  → 前端轮询 metrics（/api/training/...：迭代/奖励/成功率/速度/ETA + 指标小倍数网格 + tensorboard event 文件索引）
  → 验收：POST /api/simulation/policies/acceptance → policy_acceptance.py
      （adapter venv，mujoco+onnxruntime，逐指令模式 → *.acceptance.json）
  → 试玩：浏览器 sim2sim（browser-config 下发 MJCF+网格+策略+健康检查；
      WASM 虚拟 FS 本地跑物理与 ORT 推理；元数据校验 + 确定性回放 ?replay=）
  → 导出：部署配置 + ONNX（数值一致性 replay 为 replay_diff.py 工具，未接入强制 gate——规划中）
```

---

## 6. 前端形态

- **无构建原生 JS/HTML/CSS 多页**（版本查询参数缓存失效，全离线 vendored：three.js 25MB、MuJoCo WASM、onnxruntime-web）。
- 两种界面形态并存（刻意保留）：主工作台壳（`workbench.html` 五步导航 + 内嵌视图）与传统多页控制台（`dashboard.html` 等，供直达链接）。
- 浏览器 sim2sim 为项目最重的单文件（`app.js` ~5800 行，观测构造器 × 机器人布局 + 物理循环 + UI），优化记录见 [../web/sim2sim/optimizations.md](../web/sim2sim/optimizations.md)。
- `web/urdf-viewer/`（React/R3F 子项目）是**原型**，主工作台使用的是 `web/urdf-viewer.js`（原生版），两者不可混淆。

---

## 7. 已知技术债清单（按影响排序）

| # | 债 | 证据 | 影响 |
|---|---|---|---|
| 1 | 机器人 id 命名双轨（包 id 下划线 `unitree_go2`，浏览器特判连字符 `unitree-go2`） | `simulation_api.py:526`、`app.js:419-422` | 新机器人接入要踩两次坑 |
| 2 | 浏览器特例硬编码（Go2 地形根、per-robot 机身高度三元式） | `simulation_api.py:188-196`、`app.js:77,2408` | 违反"契约驱动禁特判"自定约束 |
| 3 | god file（simulation_api 1050 / training_api 924 / api_complete 40 个散装端点 / app.js 5832） | 各文件 | 修改成本高、回归面大 |
| 4 | 控制面边界靠依赖不安装而非代码边界（export_api 顶层 import torch 链） | `export_api.py:12` | venv 配置错误时静默降级 |
| 5 | sys.path.insert 遍布 worker/工具（靠 `_smoke_one.py` 子进程隔离补救） | 10+ 处 | 模块名冲突风险 |
| 6 | 契约无单一真值源（Pydantic 手写 ↔ 前端手写，无 Schema 生成） | contracts/ | 前后端漂移靠人肉纪律 |
| 7 | electron-builder 配置三处分裂 + 构建引用仓库外 `../QUADRUPED_ASSET_INVENTORY.json` | package.json:96-102 | 仓库不自包含 |
| 8 | 杂项：`httpx2` 拼写、requirements.txt 与 pyproject 双份、workspace/imports 99 个 hex 残留、sim2sim models 重复 ONNX、__pycache__ 入打包 filter | 各处 | 机械性，易修 |

---

## 8. 能力边界（诚实声明，与根 README 同口径）

- **已验证**：55/55 profile 冒烟（128 envs × 30 步）、16 机器人浏览器 sim2sim 编译、键盘遥控、CUDA 选择（RTX 4060 验证环境）、02 界面碰撞体可视化、控制面单测、adapter 测试。
- **已内化未达 L4**：GPU 长训练验收、ONNX 数值一致性强制 gate、实机控制与安全门禁、复杂导航规划闭环（当前导航为已训 checkpoint 的航点回放；交互式地图编辑器已提供画障碍/设航点 → A*/Dijkstra 自动求路，见 `backend/map_editor_api.py` 与 `web/navigation_editor.html`）。
- **规划中**：UniLab/RoboLab adapter（框架选择 UI 已有 planned 占位）、SAC/TD3（注册占位）、sim2real 实机 SDK（Go2 deploy/fsm.py 已有硬件无关状态机骨架）。感知观测项已抽象为通用编目（`backend/perception_observations.py`：足端接触 → 高度场 → 深度相机），供配置编辑器按 id 接入策略输入，而非包内特例。
