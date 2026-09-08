# Legged Studio 真实盘点（基于代码核实，非文档）

**版本**：2.0（修正版）
**日期**：2026-09-08
**修正说明**：本文取代 [POSITIONING_OPTIONS.md](./POSITIONING_OPTIONS.md) 第一、二部分。上一版犯了"只看 md 不数代码"的错误，把项目说成"只有 Go2、任务只有 2 个"。实地核实 16 个机器人包后，真实图景远比那丰富——**而且项目里已经存在一套比 backend 表面 API 先进得多的自研框架 `local_tasks`**。这才是理解这个项目的关键。

---

## 第一部分：真实的资产家底（逐包核实）

### 1.1 16 个机器人包，全部带契约 + simulation 目录

| 包 | 构型 | 训练源(taskPy) | 预训练ONNX | 可训练 | 可试玩(sim2sim) |
|---|---|---:|---:|:-:|:-:|
| **unitree_go2** | 四足 M | **192** | 2 | ✅(extension) | ✅ |
| **microduck** | 双足 | 19 | **9** | ✅(extension) | ✅ |
| **unitree_g1** | 人形 | 45 | 5 | ⚠️有源无entrypoint | ✅ |
| **wuji_hand** | 灵巧手 | 72 | 0 | ⚠️有源无entrypoint | ✅(无策略) |
| unitree_go2w | 轮足 | 0 | 3 | ❌ | ✅ |
| unitree_b2 | 四足 L | 0 | 1 | ❌ | ✅ |
| unitree_b2w | 轮足 L | 0 | 1 | ❌ | ✅ |
| unitree_a1 | 四足 S | 0 | 1 | ❌ | ✅ |
| deeprobotics_lite3 | 四足 S | 0 | 1 | ❌ | ✅ |
| deeprobotics_m20 | 轮足 M | 0 | 1 | ❌ | ✅ |
| agibot_d1 | 人形 | 0 | 1 | ❌ | ✅ |
| zex-w | 轮足 | 0 | 4 | ❌ | ✅ |
| unitree_a2 | 四足 L | 0 | 0 | ❌ | ✅(无策略) |
| limx_tron1_pf | 双足点足 | 0 | 0 | ❌ | ✅(无策略) |
| limx_tron1_sf | 双足 | 0 | 0 | ❌ | ✅(无策略) |
| unitree_h1_2 | 人形 | 0 | 0 | ❌ | ✅(无策略) |

**结论**：**13 个机器人带预训练 ONNX**（velocity/locomotion/dance/backflip/jump/sit-stand/roller/roulade 等），16 个全部可在浏览器 sim2sim 试玩。这绝不是"只有 Go2"。S/M/L 四足、轮足、双足、人形、灵巧手全覆盖。

### 1.2 三个能力层级（这是最重要的结构事实）

- **第 1 层 · 可训练（带 `extension_entrypoint`）**：只有 **Go2**（`local_tasks.mjlab_extension:register`）和 **microduck**（`mjlab_microduck...:register`）。只有这两个包往里"注入"了训练任务。
- **第 2 层 · 有训练源但没接 entrypoint**：**G1(45 py)、wuji_hand(72 py)**——源码在包里，但 robot_package.json 没声明 entrypoint，所以 backend 不把它们的任务暴露给训练。
- **第 3 层 · 只能试玩**：其余 12 个，只有 MJCF + 预训练 ONNX，无训练源。

> 真实瓶颈不是"只有 Go2"，而是**"可训练"这件事被 entrypoint 卡在了 2 个包上**。G1 和 wuji_hand 的源码已经在那里，接通是低成本高回报的事。

---

## 第二部分：被埋没的核心——`local_tasks` 自研框架

这是上一轮分析（包括我的四个重构方案）**完全没有看到的最重要的东西**。在 `assets/robots/unitree_go2/training/source/local_tasks/` 里，有一套完整的、比 `backend/` 表面 API 先进一代的抽象框架（约 130 个 py 文件）。

### 2.1 框架的六层结构

```
local_tasks/
├── core/                    ← 规格层（Spec = 数据类契约）
│   ├── robot_spec.py        RobotSpec：机器人规格
│   ├── task_spec.py         TaskSpec：任务规格（command/reward/termination/randomization profile）
│   ├── training_spec.py     TrainingSpec：训练超参
│   ├── experiment_spec.py   ExperimentSpec：一次实验 = robot×task×training 的组合
│   ├── policy_contract.py   PolicyContract：观测字段/历史帧/归一化/动作scale/关节序（带校验）
│   ├── catalog.py           Catalog：任务目录注册表
│   └── compose.py           compose：把 spec 组合成可训练配置
├── learning/                ← 学习组件库
│   ├── algorithms.py / models.py / rollout.py / storage.py
│   ├── motion.py            动作数据（AMP 用）
│   └── symmetry.py          对称增强（左右镜像数据增强）
├── robots/unitree/{go2,g1}/ ← 机器人实现
│   ├── contract.py          该机器人的 PolicyContract 实例
│   ├── robot.py / experiments.py
│   ├── mdp/                 actions/commands/events/observations/rewards（Go2 有完整 MDP 库）
│   ├── tasks/               任务实现（见下）
│   ├── training/            catalog/config/runner
│   └── deploy/              ★ fsm.py + policy.py（Go2 独有）
├── workflows/               ← 工作流编排
│   ├── train.py / play.py / export.py / rollout.py / distill.py（蒸馏！）
├── runtime/                 ← policy_bundle.py / sim_to_sim.py / bundle_runtime.py
└── integrations/mjlab/      ← 唯一的后端绑定
```

### 2.2 Go2 的任务生态（catalog 实注册）

```
go2/velocity-flat   go2/velocity-rough   go2/trot
go2/jump            go2/spring-jump      go2/backflip
go2/handstand       go2/leggedstand
+ dreamwaq（盲走！）+ amp_dreamwaq（AMP 模仿！）+ parkour（带 PIE 视觉模型）
```

**你愿景里的"盲狗"（dreamwaq）和"模仿学习"（amp_dreamwaq）已经以任务形式存在于框架里**，`parkour/rl/pie_model.py` 甚至带了视觉策略。它们只是没有被 backend 的 recipe_registry 暴露出来。

### 2.3 PolicyContract 已具备工业级校验

`core/policy_contract.py` 的 `PolicyContract` 有：joint_order / action_dim / action_scale / observation_fields（每个 field 有 name+width）/ history_length / history_order / normalization，且 `__post_init__` 里做维度一致性校验（action_dim==len(joint_order)==len(action_scale)、observation_dim=sum(field.width)）。**这正是 rl_sar 双层契约 + go2w_sim2sim 维度检查要做的事，你已经实现了。**

### 2.4 deploy/fsm.py 已有安全状态机

`Go2ControllerFsm`：PASSIVE → STAND → ... → SAFETY_FALLBACK，带 `Go2SafetyLimits`、状态新鲜度检查、明确的 fallback 转移逻辑。**sim2real 最难的 FSM 安全链路，你已经在 Go2 上写出来了。**

### 2.5 框架与 backend 的关系（关键架构问题）

```
backend/  (FastAPI 表面)
  └─ recipe_registry.py   只有 4 个任务：forward_walk/trot/rough_terrain/stairs  ← 浅
  └─ adapters/mjlab/      generic_task_builder + param_registry                  ← 浅
        │
        └─ 通过 extension_entrypoint 调用 ──► local_tasks.mjlab_extension:register
                                              └─ local_tasks 框架（130 py，6 层）  ← 深
                                                  10+ 任务 + AMP + dreamwaq + parkour
                                                  + 对称增强 + 蒸馏 + FSM + 部署
```

**这就是项目最大的架构真相：你有两套任务系统并存。**
- **表面一套**（backend recipe_registry）：4 个简单 velocity 任务，被前端训练页使用，是"对外可见"的全部。
- **底层一套**（local_tasks 框架）：10+ 任务、AMP、dreamwaq、parkour、蒸馏、对称增强、FSM、部署——功能强大得多，但**几乎完全不对外可见**，前端训练页摸不到它们。

> 上一轮我提的"抽象层方案 A/B/C/D"，`local_tasks` 的 core/spec 层其实已经是"方案 A 注册表 + 方案 D PolicyContract"的一个实现了，而且比 backend 那套更干净。**重构的正确起点不是从零设计方案，而是把这套被埋没的框架提升为产品的一等公民，让 backend/前端去消费它，而不是绕过它。**

---

## 第三部分：基于真实图景的缺口（修正版）

### 3.1 真正的缺口（不是"资产少"，而是"接不通"）

| 缺口 | 真相 | 严重度 |
|---|---|---|
| **任务系统双轨制** | local_tasks 有 10+ 任务/AMP/dreamwaq/parkour，但 backend recipe_registry 只暴露 4 个 velocity 任务 | ★★★ 最高 |
| **可训练机器人只有 2 个** | G1(45py)/wuji_hand(72py) 有训练源但没接 entrypoint；12 个有契约机器人无法训练 | ★★★ 最高 |
| **训练成果触达不到 sim2sim** | 训练出 ONNX 后，sim2sim 页只对 Go2 有完整地形场景（`GO2_TERRAIN_ROOT` 硬编码），其他 12 个机器人试玩用的是各自包的预训练策略 | ★★ |
| **契约双轨制** | local_tasks 有 PolicyContract（带校验），contracts/ 有 RobotContractV2，两套不互通 | ★★ |
| **部署只在 Go2 闭环** | deploy/fsm.py 是 Go2 专属，未抽象成可复用的部署框架 | ★★ |
| **资产验证浅** | 只有质量+关节存在性；碰撞体/惯量张量/actuator 参数/默认姿态未查 | ★★ |
| **感知缺** | 仅足端接触力；parkour 的 PIE 视觉在 Go2 内但未抽象成可复用感知项 | ★ |

### 3.2 之前判断错误、需要撤回的

- ~~"任务只有 forward_walk/stairs 两个"~~ → 实际 recipe_registry 有 4 个，且 local_tasks 框架内有 10+ 个（含 dreamwaq/amp/parkour/后空翻/倒立/跳跃）。
- ~~"盲狗资源没有"~~ → `go2_skills/dreamwaq/` 和 `amp_dreamwaq/` 已存在。
- ~~"无 FSM"~~ → `deploy/fsm.py` 已有带 SAFETY_FALLBACK 的 Go2 状态机。
- ~~"只有 Go2"~~ → 16 包全契约、13 包带预训练、全可试玩。
- ~~" PolicyContract 需要新建"~~ → `core/policy_contract.py` 已实现且带维度校验。

---

## 第四部分：基于真实图景的三种定位方案（修正版）

现在三个方向的真实落点变了——**核心矛盾从"缺功能"变成"功能已存在但没接通、没抽象、没暴露"**。

### 方案 A：入门盒子（接通已有，降低门槛）

**核心动作**：把已存在但摸不到的东西接通，让新手也能用上。
1. **打通任务双轨**：让 backend recipe_registry 改为消费 local_tasks 的 catalog（10+ 任务瞬间对前端可见，含 dreamwaq/parkour），每个任务配中文说明卡。
2. **接通 G1/wuji_hand 训练**：补 entrypoint，可训练机器人 2→4。
3. **训练成果一键进 sim2sim**：训练出的 ONNX 自动注册到对应机器人的试玩列表，12 个机器人共享地形场景（拆掉 `GO2_TERRAIN_ROOT` 硬编码）。
4. **资产检查补全**（碰撞/惯量/actuator/默认姿态）+ 训练健康面板（分项 reward + 症状诊断）。
5. **一键环境**（离线 wheelhouse + preflight 报告页）。

**故意不做**：插件生态、多后端、实机推广到其他机器人。
**对你的回报**：最快得到一个"16 机器人可玩、4 机器人可训、10+ 任务"的厚道成品，技术债少还。
**周期**：5-7 周。技术形态 = 原地精修，但**主线是"接通 local_tasks"而非"新设计"**。

### 方案 B：生态平台（把 local_tasks 的 spec 层开放为插件标准）

**核心动作**：local_tasks 的 `core/spec` 层（RobotSpec/TaskSpec/ExperimentSpec/PolicyContract）已经是一个插件 API 的雏形——把它从"Go2 包内的私有框架"提升为"平台级契约标准"，第三方照它写机器人包/任务包即可接入。
1. **契约统一**：把 `contracts/RobotContractV2` 与 `local_tasks/PolicyContract` 合并为一个 JSON Schema 真值源，生成 Py/TS。
2. **local_tasks 框架独立成内核包**：从 Go2 包里抽出来，变成 `legged_studio` 的核心库（backend/前端/未来的第三方包都 import 它）。
3. **插件制度**：机器人包/任务包/算法包/部署目标 = 带 manifest 的插件，声明 entrypoint（你已经用 extension_entrypoint 实现了这个机制的雏形）。
4. **示范插件**：dreamwaq 任务包、parkour 感知包、G1/wuji_hand 机器人包，做成第三方可模仿的样板。

**对你的回报**：如果做成，你定义的 PolicyContract/spec 就是行业标准雏形；但单人撑生态风险大。
**周期**：内核抽取+统一 8-10 周，见效慢。技术形态 = 内核+插件。
**关键洞察**：你离生态比想象中近——extension_entrypoint 机制已经是插件加载，spec 层已经是插件 API，差的只是"把 Go2 私有的东西提升为平台公有的"。

### 方案 C：研究台架（以 local_tasks 为基座，沉淀方法论）

**核心动作**：local_tasks 已经是很好的研究基座（有蒸馏、对称增强、AMP、parkour 视觉），把它朝"实验基础设施"方向加深。
1. **实验可复现与对比**：ExperimentSpec 已经定义了 robot×task×training 组合——补上完整 lineage（seed/依赖锁/哈希）落盘 + 实验矩阵 + 训练曲线与 sim2sim 录像同屏对比（两对标都没做的空白点）。
2. **方法论组件化**：把 dreamwaq（盲走）/amp（模仿）/对称增强/蒸馏这些已实现的组件，配上知识库的"什么时候用"决策卡（Ch25 症状路由表做成可执行）。
3. **部署链路吃透**：把 Go2 的 deploy/fsm.py 抽象成可复用部署框架，接 unitree_sdk2 做实机，追踪 Sim2Real 七层 gap（Ch23），上 ASAP/系统辨识（Ch12）。
4. **多后端交叉验证**：local_tasks 的 `integrations/mjlab/` 已是绑定层——照它再加一个后端绑定，同一 PolicyContract 跨后端数值对比。

**对你的回报**：三个方向里**对个人技术成长回报最高**——你已经在 local_tasks 里实现了 dreamwaq/amp/蒸馏/FSM，把这些吃透并补上实验对比与实机，就是一套别人难复制的个人技术资产。
**周期**：无发布压力，滚动推进；2 周可先把"实验对比 + 任务接通"立起来。技术形态 = 绞杀者渐进，北极星是研究基础设施。

---

## 第五部分：三种方案真实起点对比（修正版）

| | A 入门盒子 | B 生态平台 | C 研究台架 |
|---|---|---|---|
| **第一动作** | 接通 local_tasks→recipe_registry | 抽取 local_tasks 为内核包 | ExperimentSpec 补 lineage+对比视图 |
| **对 local_tasks** | 消费它（让前端摸到） | 提升它为平台标准 | 以它为基座加深 |
| **可训练机器人** | 2→4（接 G1/wuji_hand） | N（插件化） | 按需 |
| **对个人成长** | 低 | 中 | **最高** |
| **对外影响力** | 中 | 高（若成生态） | 低（深度高） |
| **单人可行性** | **最好** | 最难 | 好 |
| **周期** | 5-7 周 | 8-10 周+ | 滚动 |

### 我的判断（基于真实图景，供参照）

`local_tasks` 框架的存在改变了一切——**你不是"缺功能要重构"，而是"有一座建好的桥没接到对岸"**。三个方向的真实第一动作都是"接通/提升 local_tasks"，区别只在于接通向谁：

- 想**快速出厚道成品** → A（接通给前端/用户）。
- 想**沉淀个人技术资产** → C（接通给实验，顺带把 A 的"任务接通+训练健康面板"做成外壳对外）。
- 想**赌生态** → B（提升为平台标准），但现在单人全押风险仍最大。

**A+C 组合依然是最优个人路径**：以 C 为里（实验台架 + 部署吃透），把 C 里"接通任务、训练健康、资产深查"这些**既是研究刚需又恰好入门友好**的部分，顺手打磨成 A 的外壳。B 留给"真有第二个人想在你平台上加东西"的那天——而 extension_entrypoint 机制让你那天来临时,成本很低。

---

**下一步**：你定 A / B / C / A+C，我把它展开成 Phase 0 任务清单，第一项就从"打通 local_tasks 与 recipe_registry 的双轨制"开始（这是三个方案共同的真实起点）。
