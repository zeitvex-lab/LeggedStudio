# Legged Studio 重构建议与抽象层方案

**版本**：1.0
**日期**：2026-09-08
**依据**：本报告基于五路证据交叉分析——
1. `legged_studio/` 实际源码（backend/contracts/adapters/web/electron 全量探查）
2. `robo_know/Robotics_Tutorial/06_具身智能/` 知识库（28 章 RL 运控教材 + 总大纲）
3. `1000framesai.com`（Locomotion Platform，商业 SaaS 对标）与 `sim.stackforce.cc`（StackForce SimReady，工具型对标）的完整站点逆向
4. `00_open/` 下 24 个参考项目（mjlab 系、legged_gym 系、IsaacLab 系、rl_sar、microduck 全家桶等）的架构范式对比
5. 你此前的 `PROJECT_VISION_LEGGED_STUDIO.md` 与 `REFERENCE_AND_RECOMMENDATIONS.md`

---

## 第一部分：现状诊断

### 1.1 你已经做对的事（不要轻易推翻）

Legged Studio 的**领域设计方向是正确的**，这一点先确认，因为重构不是重写：

- **契约驱动**：`contracts/robot_contract_v2.py`、`scenario_contract.py`、`policy_artifact.py` 的版本化 JSON + Pydantic 校验，和知识库 Ch05 的"obs/action 是训练与部署之间的契约"、rl_sar 的双层 YAML 契约在思想上一致。这是全项目最有价值的资产。
- **控制面/训练栈隔离**：`adapters/mjlab/` 有独立 pyproject/uv.lock/venv，控制面 pyproject 不含 torch，训练通过子进程跑。这正是 REFERENCE 文档第 4.1 节"保持控制面与执行环境隔离"的落地，也是 microduck-studio `jobs.py` 的同款做法。
- **数据驱动的机器人包发现**：`robot_packages.py` 用 `package_index.json` + 能力清单（capabilities manifest），而不是硬编码注册表。这和 1000framesai 的 `robots_list_auth.json`（joint_order + morphology）思路一致。
- **浏览器 Sim2Sim 已跑通**：`web/sim2sim/` 用 MuJoCo WASM + onnxruntime-web + three.js，和 1000framesai 的 `/sim2sim/` 是同一技术路线，且已支持多地形。这是相对 StackForce 的差异化能力（StackForce 的 Sim2Sim 还要你上传 ONNX）。
- **文档诚实**：README 有"能力边界（诚实声明）"，REFERENCE 文档建立了 L1-L4 证据等级。这在 RL 工具项目里很少见。

### 1.2 真正的结构性问题（按根因归类，而非按文件罗列）

下面 7 个问题，每个都附"为什么这是问题"的跨证据论证。

---

#### 问题 1：三个 god file 吸干了分层红利

- `backend/simulation_api.py` **1050 行**、`backend/training_api.py` **924 行**、`web/sim2sim/app.js` **5832 行**。
- 外加 `backend/api_complete.py` 690 行里塞着约 40 个未 router 化的端点 + 静态文件 MIME 特例（478-517 行为 onnxruntime 文件逐一路由）。

**为什么这是根因问题**：知识库 Ch04（Manager-Based 架构精读）的核心论点是——legged_gym 的 2000 行 `LeggedRobot` 上帝类之所以是灾难，不是因为行数，而是因为**奖励/观测/终止/DR 全耦合导致任何修改都要读懂全局**。教材给出的量化收益是"加 reward 项 15min→2min、换机器人 3 天→30min"。你现在三个 god file 正在自家后端的 API 层、前端仿真层复刻同样的耦合：`simulation_api.py` 同时负责会话生命周期、场景几何生成（`_scene_geoms` 按 map_id 程序化拼 geom）、策略验收子进程调度、浏览器资产打包、帧渲染——五件事互相 import 彼此的局部变量。

**后果**：你没法把"场景"做成 Scenario Contract 驱动的数据（愿景 Step 4/5），因为场景现在是 `if map_id == "stairs": ...` 的代码。

---

#### 问题 2：机器人身份存在两套命名 + Go2 硬编码特例

- 包 ID 用下划线（`unitree_go2`），但 `simulation_api.py:526` 硬编码集合 `{"unitree-go2", "zex-w", ...}` 用连字符，前端 `app.js:419-422` 被迫写注释解释"normalized key 与 option value 不匹配否则下拉空白"。
- `simulation_api.py:188-196` 有 `GO2_BROWSER_SCENES` / `GO2_TERRAIN_ROOT` 全局常量；`app.js:77` `DEMO_MODEL_URL` 写死 Go2 ONNX；`app.js:2408-2409` 按 `robot === "microduck" ? ... : robot === "zex-w" ? ...` 写死机身高度。

**为什么这是根因问题**：你自己在 README 行 68 写了"契约驱动、禁止按 robot_id 特判"作为核心约束，而代码在违反它。知识库 Ch22（DIY 实战）把"passive/actuated joint 必须由命名或显式映射解析，禁止散落硬编码索引"列为平台级不变量；Microduck AGENTS.md 同样把"布局版本化、训练/部署一致"列为 mandatory。1000framesai 的解法是 `morphology` 字段（`quadruped_12dof` / `wheel_leg_16dof_v1`）——机器人差异全部下沉到数据，代码里没有 `if robot == "go2"`。

**后果**：每加一个新机器人，你要改后端 Python、前端 JS、打包配置三处，且改完不知道哪里还藏着第四个特判。这正是愿景"6 种产品分类"无法落地的直接原因。

---

#### 问题 3：契约是"后端定义、前端约定俗成"，没有单一真值源

- contracts 目录是纯 Pydantic，前端 JS 靠手写字段名对齐；没有自动生成 TS 类型。
- `contracts/policy_artifact.py:175` 在函数体内 `import torch`——契约层（README 宣称"仅 Pydantic 即可运行"）出现 torch。
- 机器人 ID 双命名（问题 2）本质上也是契约没有 machine-readable 地约束 `robot_id` 格式（`pattern="^[a-z0-9_]+$"` 之类）。

**为什么这是根因问题**：REFERENCE 文档第 4.3 节已经给出正确答案："建议使用版本化 JSON Schema 作为 canonical source，再生成 Python/Pydantic 与 TypeScript 类型。不要分别手写 YAML、Python dataclass、TypeScript interface 和 C++ 常量。" RC_WheelLeg 的教训（YAML 明示不被 C++ 读取）和 RoboLab 的教训（Artifact 硬编码维度）都证明：**契约一旦靠人肉同步，就会漂移**。rl_sar 之所以优雅，是因为 `base.yaml` + `config.yaml` 就是运行时真值，C++ 代码按 YAML 里的观测名列表从状态字典取值，不存在第二份约定。

---

#### 问题 4：前端是三套渲染栈 + 无构建多页应用，已超出可维护边界

- 三处独立 three.js：`web/urdf-viewer.js`（991 行原生 JS）、`web/sim2sim/app.js`（5832 行）、`web/urdf-viewer/`（完整 Vite+React+R3F 子项目但**主工作台没有引用，疑似死代码**）。
- 前端零构建：原生 HTML/JS 多页，`training_create.html` 单文件 125 KB（内联脚本），API base 在 `dashboard.js:6` 写死 `http://127.0.0.1:8765`、`training-common.js:21` 又一份、`workbench.js` 用 `window.location.origin`——非默认端口部署时 dashboard 直接挂。
- 通信全部轮询（`dashboard.js:180` setInterval），无 WebSocket/SSE，尽管 FastAPI 愿景里写了 SSE。

**为什么这是根因问题**：1000framesai 证明了"原生 ES Modules + 无打包器"是可行路线，但它的前提是**严格的模块化纪律**：`shared/api.js` 统一 API 客户端、每页一个 `app.js`、三层（Three 渲染 / MuJoCo 物理 / ORT 推理）解耦。你的 `web/sim2sim/app.js` 5832 行恰恰是 1000framesai 模式没守住的样子。而 StackForce 证明了另一条路（Next.js + React + R3F），代价是构建复杂度和混淆。你现在三条路同时走，三套之间没有共享状态层和 API 层。

---

#### 问题 5：控制面边界渗漏——"隔离"只靠依赖不安装，不靠代码边界

- `backend/export_api.py:12` 顶层 `from adapters.mjlab.onnx_exporter import export_policy_to_onnx`（onnx_exporter 顶层 import torch/onnx），靠 `api_complete.py:49-53` try/except 兜底。
- `backend/simulation_api.py:34` 顶层导入 `adapters.mjlab.mujoco_env`。
- `backend/api_complete.py:40`、`native_worker.py` 6 处、`train_worker.py`、`replay_diff.py` 等 **10+ 处 `sys.path.insert`**。tools/README 自己都提到 velocity_env_cfg 解析错文件的模块冲突，要靠 `_smoke_one.py` 子进程隔离补救。

**为什么这是根因问题**：REFERENCE 文档 4.1 节写得很明确："不要在 FastAPI 主进程直接 import 所有训练框架……每个 adapter 只通过版本化 JSON 消息、文件 Artifact 和日志事件与控制面通信。"robot_lab 的解法是 `register_task(env_cfg="module:Class")` **字符串延迟解析** + 顶层 `scripts/train.py` re-exec 到 `.venvs/<framework>/bin/python`。microduck-studio 的 `protocol.py` 用 JSON-RPC over unix socket，连 import 的机会都没有。sys.path.insert 泛滥是"同仓库同环境 import 隔离"这条路走不通的确证——只要 backend 能 `from adapters.mjlab import ...`，总有一天会 import 到 torch。

---

#### 问题 6：构建与运行时不自包含、有残留

- `package.json` 的 extraResources 引用仓库外文件 `../QUADRUPED_ASSET_INVENTORY.json`（96-102 行）——构建依赖兄弟目录。
- electron-builder 配置三处分裂：`package.json` 内嵌 + `packaging/electron-builder.embedded.js` + `packaging/electron-builder.online.js`。
- `workspace/imports/` 残留 99 个 hex 导入包（测试/冒烟残留，无清理机制）；`web/sim2sim/models/` 有两份字节级重复的 ONNX。
- `pyproject.toml:30` dev 依赖写成 `httpx2`（不存在的包）；`backend/requirements.txt` 与 pyproject 双份维护。

这些是机械性问题，但会直接破坏 Phase 0 验收门"在全新 Windows 用户目录完成离线安装与启动"。

---

#### 问题 7：训练监控与全流程闭环还差关键三件套

对照愿景 7 步与知识库方法论，缺：

1. **分项 reward 曲线**。知识库 Ch06 反复强调"只看 total reward 是 reward hacking 温床——reward 上升可能只是 penalty 在降"。你当前 metrics 端点返回聚合曲线，没有按 reward term 分解。StackForce 和 1000framesai 都把"19 项/14 项 reward 权重"做成一等公民。
2. **部署前 dummy 前向维度检查**。go2w_sim2sim 在 C++ 里启动时用假观测过一遍网络校验维度，能拦 90% 的 obs 错位。你的 Step 6 导出目前没有这道门。
3. **ONNX 数值一致性 gate**。愿景成功标准写了"ONNX 数值一致性 <1e-5（需固定输入 replay）"，`adapters/mjlab/replay_diff.py` 已存在但未接入导出流水线成为强制 gate。microduck 的做法（归一化 bake 进 ONNX + publish 前形状冒烟门）是参照。

---

### 1.3 问题之间的关系（先看懂全局再动手）

```
契约无单一真值源(问题3)
    ├──→ 机器人 ID 双命名(问题2) ──→ 前端 if-else 特判 ──→ god file(问题1)
    ├──→ 前后端字段漂移 ──→ 前端三处手写 API base(问题4)
    └──→ 控制面/adapter 靠人肉维持边界(问题5) ──→ sys.path hack(问题5)
                                    └──→ 打包要 try/except 兜底(问题6)

缺 reward 分项/维度检查/数值 gate(问题7)
    └──→ 愿景 Step 4/6/7 无法 L4 验收 ──→ MVP 只能停在"能跑"
```

**结论**：问题 3（契约真值源）是总开关。先修它，问题 2/4/5 才有修的标准；否则你拆 god file 只是把混乱搬家。

---

## 第二部分：抽象层设计——四种方案

你要求"多给我几种不同的方案"。下面四种方案都回答同一个问题：**task / robot / policy / env / runner / deploy 这几层怎么切，彼此之间用什么契约连接**。每种方案给出：结构图、核心抽象、证据来源、适合你项目的程度、代价。

---

### 方案 A：注册表驱动范式（mjlab 范式 · 最小改动 · 推荐 MVP 主线）

**一句话**：把你已有的 `recipe_registry.py` + `algorithms/registry.py` 升级为一等公民的显式任务注册表，机器人以包注入，契约四元组 `(env_cfg, play_env_cfg, rl_cfg, runner_cls)` 即"一次训练的全部输入"。

**证据来源**：mjlab_new 的 `mjlab/tasks/registry.py`（`register_mjlab_task` / `list_tasks` / `load_env_cfg` / `load_rl_cfg` / `load_runner_cls`）、InstinctMJ 的工厂函数惰性注册、AMP_mjlab 的 `TrainConfig.from_task`。知识库 Ch04/Ch22 把这套称为"配置即环境"——新环境 = 填六个 Cfg + 注册，不继承基类。

**分层结构**：

```
contracts/                    ← 唯一真值源（见第三部分，方案 A 依赖它）
  robot_contract_v2.py         Robot Contract（机器人生成）
  task_spec.py                 TaskSpec = (task_id, env_cfg_path, rl_cfg_path, runner)
  policy_artifact.py           PolicyArtifact（训练产物）
  scenario_contract.py         Scenario（评估场景）

backend/
  registry/
    task_registry.py           显式注册表：task_id → TaskSpec（存路径字符串，不存实例）
    robot_registry.py          robot_id → RobotPackage（你已有，保留）
  services/
    training_service.py        无 HTTP 的纯业务逻辑：解析 TaskSpec → 调 adapter
    simulation_service.py      场景由 ScenarioContract 驱动，不再 if map_id
    export_service.py
  api/                         薄路由层：每个文件 < 200 行，只做请求校验 + 调 service
    training_api.py  simulation_api.py  export_api.py  ...

adapters/mjlab/                唯一训练后端（MVP）
  tasks/<robot>/<task>/        机器人×任务矩阵（借鉴 unitree_rl_mjlab）
    env_cfg.py                 dataclass 工厂：make_xxx_env_cfg()
    __init__.py                注册点：register_task("Mjlab-Velocity-Flat-Unitree-Go2", ...)
  worker/                      子进程入口（native_worker/train_worker 已有）

assets/robots/<robot_pkg>/     机器人即包：contract.json + robot_package.json + 资产
```

**核心抽象（四个）**：

1. **TaskSpec**（新增）：`{task_id, family, env_cfg: "module:factory", rl_cfg: "module:Class", runner: "module:Class", required_capabilities: [...]}`。用字符串延迟解析（robot_lab 的 `framework_required` 思路），注册表进程不需要 import torch。
2. **RobotPackage**（你已有）：保持数据驱动，但补上 `morphology` 字段（抄 1000framesai：`quadruped_12dof` / `wheel_leg_16dof_v1` / `biped_14dof`），把 Go2/microduck/zex-w 的机身高度、缩放、场景差异全部下沉到这个字段驱动的数据文件，删掉代码里的三元表达式。
3. **PolicyArtifact**（已有，强化）：导出时强制写入 obs/action 布局版本 + 归一化参数 + 数值验证报告，对齐 rl_sar 的 `<policy>/config.yaml`。
4. **ScenarioContract**（已有，激活）：把 `_scene_geoms` 的 if-else 改成读 Scenario JSON 里的 geom 列表，地图变成 `workspace/scenarios/*.json` 数据。

**任务 ID 即导航坐标**：沿用 mjlab 的 `框架-任务-地形-机器人` 命名（`Mjlab-Velocity-Flat-Unitree-Go2-v0`）。这个 ID 本身就是可解析的组合坐标，前端导航树、CLI、API 路径、日志目录全部从它派生，消灭命名第二真值源（顺带修掉问题 2 的 ID 双命名：`robot_id` 在契约里加 `pattern="^[a-z0-9_]+$"` 强制下划线）。

**适合度**：★★★★★（MVP 主线）。你的 recipe_registry/algorithms registry 已经是它的雏形，改动是"升级"不是"替换"。
**代价**：跨后端（Isaac Gym/UniLab）出现时注册表要再抽象一层——但那正是方案 B 解决的问题，方案 A 不堵死它。
**何时用**：现在，Phase 0/1。

---

### 方案 B：Framework 适配层范式（robot_lab 范式 · 为多后端做准备）

**一句话**：在方案 A 的注册表之下、adapter 之上，插入一层**同名抽象符号层**，业务代码只 import `legged_studio.framework`，由它在 import 时按后端解析，多框架依赖互斥用 re-exec 到独立 venv 解决。

**证据来源**：robot_lab 的 `framework/{isaaclab,mjlab}/` 双后端适配层（`detect.py` import 时选后端、两边导出同名 `ActionTermCfg`/`register_task`/`mdp` 符号）+ 顶层 `scripts/train.py` 的 re-exec 调度器（`.venvs/<framework>/bin/python`）。LeggedGym-Ex 的 `simulator/` ABC + `SIMULATOR` 环境变量是同思想的 legged_gym 版本。unilab 的 `base/registry.py` EnvFactory Protocol + `_SUPPORTED_SIM_BACKENDS` 枚举是更正式的协议版。

**分层结构**：

```
legged_studio/framework/       ← 同名符号层（新增）
  __init__.py                  detect_backend() → 转发到对应实现
  base.py                      Protocol: EnvFactory / TaskRegistry / Exporter / Sim2SimRunner
  mjlab_impl/                  实现 1（映射到 adapters/mjlab）
  isaacgym_impl/               实现 2（Phase 3，可选/legacy）
  unilab_impl/                 实现 3（Phase 2/3）

backend/services/
  training_service.py          只 import legged_studio.framework，不 import adapters.mjlab

runtime/venvs/
  mjlab-py312/                 每个后端一个锁死的 venv（REFERENCE 5.1 节）
  robogauge-py311/
  isaacgym-py38/
```

**核心抽象**：`EnvFactory Protocol`——

```
class BackendAdapter(Protocol):
    name: str
    capabilities: set[Capability]      # TRAIN / EXPORT_ONNX / SIM2SIM / DEPLOY
    python_env: Path                   # 该后端的隔离 venv
    def list_tasks(self) -> list[TaskSpec]: ...
    def launch_train(self, spec, overrides) -> JobHandle: ...   # 返回子进程句柄，不 import torch
    def launch_export(self, artifact) -> JobHandle: ...
    def launch_sim2sim(self, artifact, scenario) -> JobHandle: ...
```

关键约束：**所有方法返回 JobHandle（子进程句柄）而非 Python 对象**。控制面永远拿不到 torch tensor，只拿到 stdout 日志路径 + 状态码 + artifact 文件路径。这就把 REFERENCE 4.1 的"只通过版本化 JSON 消息、文件 Artifact 和日志事件通信"落到了类型签名上——从制度上消灭问题 5 的边界渗漏，因为协议返回类型里没有可以渗漏 torch 的地方。

**适合度**：★★★★（Phase 2/3 必需，MVP 可先做接口不实现多后端）。
**代价**：多一层间接，调试时栈变深；需要严格约束"framework 层不得泄漏后端专有类型"。
**何时用**：当你真要接第二个后端（RoboGauge 评估服务或 UniLab）时。MVP 阶段先定义 Protocol 但不实现多后端，避免过早抽象。

---

### 方案 C：Hydra 组合配置范式（unilab 范式 · 为实验矩阵/多算法）

**一句话**：如果你的核心诉求是"算法 × 任务 × 后端"三维实验矩阵（对比 PPO/SAC、调参、批量 seed），用 Hydra 的 defaults 组合替代单注册表，配置即文件树、可被外部工具枚举。

**证据来源**：unilab_new 的 `conf/<algo>/{config.yaml, task/<task>/<backend>.yaml}`——`defaults: [task: go1_joystick_flat/mujoco]` 一行切换任务和后端；CLI override 直接改任意字段。知识库 Ch24 的实验管理也建议"多 seed/超参搜索时引入组合配置"。

**分层结构**：

```
conf/
  config.yaml                  defaults: [algo: ppo, task: velocity_flat, robot: unitree_go2, backend: mjlab]
  algo/{ppo,sac,td3}.yaml
  task/{velocity_flat,velocity_rough,standup,navigation}.yaml
  robot/{unitree_go2,go2w,a2,microduck}.yaml    ← 引用 Robot Contract
  backend/{mjlab,isaacgym,unilab}.yaml          ← 引用 BackendAdapter + venv 路径
```

**核心抽象**：配置是**文件树的组合产物**，不是代码里的 dataclass 继承。前端的"训练配置"页面对应这棵树的可视化：选算法节点、选任务节点、选机器人节点、选后端节点，Hydra 负责合并成 resolved-config，存进 `runs/<run-id>/resolved-config.json`（你的 REFERENCE 4.3 产物目录已有这个设计）。

**适合度**：★★★（Phase 3 实验管理功能）。
**代价**：Hydra 是重依赖，且它的"组合"与方案 A 的"显式注册表"在哲学上冲突（一个靠文件树约定、一个靠代码注册）；引入它意味着 training 子系统的配置体系换代。对你的 Electron 桌面形态，Hydra 的 CLI 优先设计与"Web 表单优先"也有摩擦。
**何时用**：仅当"实验矩阵/批量对比"成为核心卖点时。否则方案 A 的注册表 + 前端表单已够用。**不建议 MVP 采用。**

---

### 方案 D：部署契约 + FSM 范式（rl_sar 范式 · Step 6/7 部署与实机闭环）

**一句话**：这是**部署侧**的抽象，与方案 A/B 的训练侧抽象正交、可叠加。机器人契约与策略契约分离，运行时按声明式观测名列表取值，FSM 状态机管安全，同一策略两种 IO 后端（仿真/实机）。

**证据来源**：rl_sar 的 `policy/<robot>/base.yaml`（机器人契约）+ `<policy>/config.yaml`（策略契约）双层分离；运行时按 YAML 里 `observations` 名字列表从 SDK 状态字典取值（**观测是声明式数据不是代码**）；`fsm_robot/fsm_<robot>.hpp` 每机器人特化 Passive→FixStand→RLBase。microduck_rl 的 `export.py`（归一化 bake 进 ONNX）+ `publish/manifest.py`（schema 版本化 + 形状冒烟门）。go2w_sim2sim 的启动时 dummy 前向维度检查。知识库 Ch23 的"ONNX 是发动机不是汽车"——真实闭环 = 传感器→预处理→状态估计→obs 拼接→ONNX→action 后处理→安全过滤→SDK。

**分层结构（部署侧）**：

```
deploy/
  contracts/
    <robot>.deployment.yaml      ← Deployment Contract（机器人侧真值）
        joint_mapping: {policy_index → motor_id}
        default_pose / kp / kd / torque_limits
        control_rate / safety_rates / watchdog_ms
    <policy>.policy.yaml         ← Policy Contract（策略侧真值）
        observations: [base_lin_vel, base_ang_vel, gravity, cmd, joint_pos_err, joint_vel, prev_action]
        obs_scales / history_len / action_scale / clip
  runtime/
    fsm/                         Passive → FixStand → RL → Recover → EStop（安全链路独立于策略）
    io/
      sim_mujoco.py              仿真 IO 后端
      unitree_sdk2.py            实机 IO 后端（Phase 3）
    checks/
      dummy_forward.py           启动时假观测过网络校验维度（go2w_sim2sim 模式）
      onnx_replay.py             固定输入数值一致性 <1e-5 gate（激活你已有的 replay_diff.py）
```

**核心抽象**：

1. **观测声明式**：Policy Contract 的 `observations` 列表是部署端拼观测向量的唯一依据。前端可据此渲染观测流水线图（1000framesai 的算法 manifest 也是这个思路，obs_dim/history_len/action_dim 全在 manifest 里）。
2. **部署前双 gate**：`dummy_forward`（维度对）+ `onnx_replay`（数值对），不过 gate 不生成部署包。这直接补上问题 7 的第 2、3 件。
3. **FSM 是安全链路**：知识库 Ch23 强调"action clip ≠ 急停；安全系统不能依赖策略正确性"。部署契约必须含 FSM 定义与命令超时，"一键生成部署包"不等于"一键上机"。

**适合度**：★★★★★（Step 6/7 的唯一正确形态，且与训练侧方案 A/B 正交叠加）。
**代价**：实机 SDK（unitree_sdk2）与 FSM 代码是每机器人一份的特化工作量，无法完全通用——rl_sar 也是这么做的（每机器人一个 hpp），承认这一点比假装能通用更安全。
**何时用**：Step 6 导出（MVP 内）先做契约 YAML + 双 gate + 仿真 IO；实机 IO 与 FSM 模板留到 Phase 3。

---

### 四种方案的关系与选择建议

```
训练/编排侧（三选一为主）          部署侧（正交叠加）
┌─────────────────────────┐      ┌──────────────────────────┐
│ 方案A 注册表 (MVP 主线)   │      │ 方案D 部署契约+FSM        │
│ 方案B Framework适配层     │  +   │  (Step 6/7 必做)          │
│  (Phase 2/3 多后端时叠加) │      │                          │
│ 方案C Hydra矩阵           │      │                          │
│  (Phase 3 实验管理时可选) │      │                          │
└─────────────────────────┘      └──────────────────────────┘
```

**推荐路径**：**MVP = 方案 A + 方案 D 的仿真部分**；接第二后端时叠加方案 B 的 Protocol；做实验矩阵时再评估方案 C。不要一次上四种——方案 A 和 C 在配置哲学上互斥，B 和 A 是演进关系而非并列。

---

## 第三部分：统一真值源——所有方案的共同前提

四个方案都依赖一个前提：**契约必须有一个 machine-readable 的 canonical source，生成一切下游类型**。这是问题 3 的解，也是问题 2/4/5 的修法标准。

**做法**（采纳 REFERENCE 4.3 的建议并具体化）：

1. **JSON Schema 为 canonical source**：`contracts/schema/robot-contract-v2.json`、`task-spec-v1.json`、`policy-artifact-v1.json`、`scenario-contract-v1.json`、`deployment-contract-v1.json`。
2. **代码生成**：
   - Python：`datamodel-code-generator` → Pydantic 模型（替换手写 `robot_contract_v2.py` 等）。
   - TypeScript：`json-schema-to-typescript` → `web/shared/types.ts`（哪怕前端不引框架，也用 TS 类型 + JSDoc 让编辑器检查字段名，消灭"前端约定俗成"）。
3. **契约里加硬约束**：`robot_id: {pattern: "^[a-z0-9_]+$"}`（强制下划线，修 ID 双命名）；`schema_version` 必填；obs/action `dimension` 与 `components.length` 一致性校验。
4. **契约层纯净化**：删掉 `policy_artifact.py:175` 的 `import torch`——归一化参数以 numpy/list 形式入契约，torch 转换放到 adapter 层。
5. **ONNX 元数据盖章同一契约键**：`onnx_exporter.py` 已在往 `metadata_props` 写契约键，保持，并以 JSON Schema 校验这些键。

这一项做完，前后端字段漂移、ID 双命名、控制面渗漏（契约层不再 import torch）三个问题同时有了强制防线。

---

## 第四部分：前端优化方向（对标两个网站后的具体清单）

### 4.1 先决策：一条路走到底

你有三套渲染栈并存。二选一（不要继续三条并行）：

- **路线 1（推荐）：1000framesai 模式**——原生 ES Modules、无打包器、自托管 vendor。前提是把 `app.js` 5832 行拆成模块：`shared/api.js`（统一客户端 + Idempotency-Key）、`shared/types.ts`（契约生成）、`sim2sim/{scene,physics,policy,ui,terrain}.js` 五层分离。删掉未被引用的 `web/urdf-viewer/` React 子项目（死代码）。这条路构建轻、与 Electron/静态 mount 天然契合。
- **路线 2：StackForce 模式**——全面转向 Vite + React + R3F，以 `web/urdf-viewer/` 为种子重构整个 web。代价是构建链、SSE/状态管理（Zustand，愿景里写了）、打包全都要上。仅当你计划做复杂交互（观测映射板、奖励编辑器重度动态）时才值得。

无论哪条，**立即做三件事**：
1. 统一 API base：全部页面改用 `window.location.origin` + 统一 `shared/api.js`，删掉 `dashboard.js:6` 和 `training-common.js:21` 的硬编码 `127.0.0.1:8765`（问题 4，非默认端口直接挂）。
2. 轮询改 SSE：FastAPI 愿景已写 SSE，训练日志/指标流从 `training-common.js` 的轮询改为 `/api/training/{id}/events` SSE 流。
3. 删重复资产：`web/sim2sim/models/` 两份字节级相同的 ONNX 删一。

### 4.2 抄两个对标的 UX（已被验证有效）

来自网站逆向的高价值 UX，按实现成本排序：

1. **编号工作流条**（StackForce 4 步条）：`导入机器人 → 策略映射 → 导出训练工程 → 一键 Sim2Sim`，未解锁步骤禁用 + tooltip 说明原因。你的 workbench 5 步导航已有雏形，补上"前置条件检查 + 禁用原因提示"。
2. **Dashboard 下一步入口卡片 + 快速体验**：1000framesai 首页的"4 个内置 Demo + 当前训练进度 + 下一步卡片"。你的 dashboard 已有卡片，加"未训练也能玩"的 bundled Go2 demo 入口（1000framesai 未登录 fallback 到 bundled ONNX 的策略）。
3. **观测/动作映射板**（StackForce 步骤 2，最痛的一页）：左侧观测库（base_lin_vel/ang_vel/gravity/cmd/joint_pos_err/joint_vel/prev_action）→ 右侧 ONNX 输入槽位，维度自动校验。这正好消费方案 D 的 Policy Contract 声明式观测列表。
4. **奖励权重在线编辑器**：两家都有，StackForce 19 项带中文说明。以知识库 Ch06 的"奖励四层分解"（Tracking/Regularization/Style/Contact）为分组，每项给中文名 + 一句话作用 + 滑条。后端数据来自 `adapters/mjlab/shared_rewards.py` + `param_registry.py`（你已有参数内省，把它接到这个 UI）。
5. **错误信息里写下一步**：StackForce 的"ONNX policy path is not attached yet. Train the exported task, then export policy.onnx."——把"该做什么"写进错误。

### 4.3 补上训练监控三件套（问题 7）

- **分项 reward 曲线**：metrics 端点按 reward term 分解返回，前端 Recharts 多线图。知识库 Ch06 的硬性要求。
- **部署前检查页**：方案 D 的 `dummy_forward` + `onnx_replay` 双 gate 结果可视化，不过 gate 禁用"生成部署包"按钮。
- **训练诊断面板**（远期）：知识库 Ch25 的五大仪表盘（Reward/KL/Entropy/Value Loss/Episode Length）与症状路由表，可直接做成"训练健康"页。

---

## 第五部分：后端/工程优化方向

1. **拆 god file（问题 1）**：`simulation_api.py` 按"会话管理 / 场景构建 / 策略验收 / 资产打包 / 渲染"拆成 5 个 service 模块 + 1 个薄路由；`training_api.py` 按"创建 / 监控 / 产物 / 配置内省"拆 4 个；`api_complete.py` 里 40 个散装端点 router 化。静态文件 MIME 特例（478-517 行）改用一个通用的 content-type middleware 或正确配置 StaticFiles。
2. **消灭 sys.path.insert（问题 5）**：10+ 处全删。backend 对 adapter 一律通过 `subprocess` + 版本化 JSON（方案 B 的 JobHandle），或把需要共享的纯逻辑（如 ContractMujocoEnv 这类不依赖 torch 的）下沉到 `contracts/` 或独立的 `shared/` 包，让 import 合法化而不是 hack 化。
3. **构建自包含（问题 6）**：把 `QUADRUPED_ASSET_INVENTORY.json/md` 移入仓库内（或构建时生成进 `assets/`），删除对 `../` 兄弟目录的依赖；electron-builder 三份配置合并为一份模板 + 环境变量切换；修 `pyproject.toml` 的 `httpx2` 拼写；删 `backend/requirements.txt` 或改为由 pyproject 生成。
4. **workspace 卫生**：`imports/` 的 99 个 hex 残留加启动时 TTL 清理或显式"清理临时导入"按钮；`.gitignore` 已排除 workspace，保持。
5. **测试补齐**：前端零测试 → 至少给 `shared/api.js` 和契约解析加 Vitest/Playwright smoke；后端把 `pytest`（pyproject 已声明）与 `unittest`（实际在用）统一为 pytest；contracts 目录仅 1 个测试文件，为 5 个契约各补 roundtrip 测试（REFERENCE P0-1 验收门要求）。

---

## 第六部分：落地路线图（与愿景 Phase 对齐）

### Phase 0（现在 · 2 周）：修真值源 + 拆最大的雷

| 序号 | 任务 | 对应问题 | 验收 |
|---|---|---|---|
| P0-1 | JSON Schema canonical + 生成 Python/TS 类型；robot_id 加 pattern 强制下划线 | 问题 3/2 | 5 契约 roundtrip 测试过；前后端共用一份类型 |
| P0-2 | 删 Go2/microduck/zex-w 硬编码，差异下沉到 RobotPackage 的 morphology 数据 | 问题 2 | 代码里 grep 不到 `== "unitree-go2"` / `=== "microduck"` 特判 |
| P0-3 | 拆 `web/sim2sim/app.js` 为 scene/physics/policy/ui/terrain 五模块；统一 API base + 删死代码 `web/urdf-viewer/` | 问题 4 | 单文件 < 800 行；非默认端口页面正常 |
| P0-4 | 消灭 backend 对 adapter 的 torch import + 10+ 处 sys.path.insert | 问题 5 | 控制面 venv 无 torch 时全部测试通过 |
| P0-5 | 构建自包含（资产入库、配置合一、修 httpx2） | 问题 6 | 全新 Windows 目录离线启动过 |
| P0-6 | 轮询改 SSE；删重复 ONNX；workspace imports 清理 | 问题 4/6 | 训练日志实时推送 |

### Phase 1（MVP · 6-8 周）：方案 A 注册表 + Go2 纵向切片 + 方案 D 仿真侧

- 升级 recipe/algorithm registry 为显式 TaskSpec 注册表（方案 A），任务 ID 用 `Mjlab-Velocity-Flat-Unitree-Go2` 坐标。
- 拆 `simulation_api.py`/`training_api.py`，场景改由 ScenarioContract 驱动。
- 观测映射板 + 奖励编辑器（消费 param_registry + Policy Contract）。
- Step 6：Deployment Contract YAML + `dummy_forward` + `onnx_replay` 双 gate（方案 D 仿真部分），分项 reward 曲线。
- 验收门沿用 REFERENCE 8.3（不变）：同一 Go2 Contract 贯穿资产/训练/ONNX replay/部署包。

### Phase 2（8-10 周）：方案 B 接口 + 评估/Sim2Sim

- 定义 `BackendAdapter` Protocol（方案 B），接 RoboGauge 为第二 adapter（独立 py311 venv）。
- Step 4/5：ScenarioContract 驱动评估 + 导航；microduck 式 publish manifest。

### Phase 3（4-6 周）：方案 D 实机侧 + 可选方案 C

- 实机 IO 后端（unitree_sdk2）+ FSM 模板 + Step 7 回溯。
- 若实验矩阵成刚需，评估方案 C（Hydra）；否则保持方案 A 注册表。

---

## 第七部分：一页速查

| 维度 | 现状 | 建议 | 主要证据来源 |
|---|---|---|---|
| 总开关 | 契约前后端人肉对齐 | JSON Schema canonical → 生成 Py/TS | REFERENCE 4.3、rl_sar |
| 训练侧抽象 | recipe registry 雏形 | **方案 A** 显式 TaskSpec 注册表 | mjlab registry、知识库 Ch04 |
| 多后端 | 无 | **方案 B** BackendAdapter Protocol（Phase 2） | robot_lab framework、unilab |
| 实验矩阵 | 无 | 方案 C Hydra（Phase 3 可选，慎入） | unilab |
| 部署侧抽象 | ONNX 导出已有 | **方案 D** 双层契约 + FSM + 双 gate | rl_sar、microduck、go2w_sim2sim |
| 机器人差异 | Go2 硬编码 + ID 双命名 | morphology 数据下沉 + ID pattern | 1000framesai、知识库 Ch22 |
| 前端 | 三套渲染 + god file | 一条路走到底 + 五层拆分 + SSE | 1000framesai、StackForce |
| 控制面边界 | sys.path hack 渗漏 | JobHandle 子进程 + 纯逻辑下沉 | robot_lab re-exec、microduck-studio |
| 训练监控 | 聚合曲线 | 分项 reward + 部署双 gate | 知识库 Ch06、go2w_sim2sim |

---

**一句话总结**：Legged Studio 的方向（契约驱动 + 控制面隔离 + 浏览器 Sim2Sim）已经被两个商业/工具对标和 24 个参考项目验证为正确，缺的不是方向而是**执行纪律**——先把契约做成单一真值源（修总开关），MVP 走"方案 A 注册表 + 方案 D 仿真侧"，前端收拢到一条路并拆开 god file，多后端和实验矩阵留到 Phase 2/3 再叠加方案 B/C。
