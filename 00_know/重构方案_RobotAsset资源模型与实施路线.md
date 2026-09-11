# Legged Studio 重构建议与实施方案：RobotAsset 资源模型

> **日期**：2026-09-10（rev.2 优化） ｜ **状态**：定稿 + 证据扩展
> **依据**：本目录三份调研（52 目录资产总盘点 / 技术维度盘点 / 28 章 RL 知识地图）+ 原书 28 章（`robo_know/Robotics_Tutorial/06_具身智能/RL运控/`）选择性精读 + 5 个参考项目实地分析（LLoco、1000framesai.com、unitree_rl_mjlab、kaiwu_rl、TRON1 三仓）+ **14 机型文件级资源库 [`00_resources/`](../00_resources/README.md)**（8 类 × 14 机型，含契约/训练/部署/策略/动作素材；v0.45.0 起随本仓库分发）
> **rev.2 变更**：① 一等资源由 4 份扩为 **5 份**（新增 Motion 参考动作，见 §2.1.1）② 新增「资源库映射」§2.5 与「14 机型 × 能力档位」§5.6 ③ 参考项目对照扩至 12 家（§4）④ 补 `runner_ref` 落位、6 类 SkillSpec 目录（§3）与 4 条新风险（§8）⑤ 新增 §5.7：训练配置 / 训练 / 低级仿真 / 高级仿真的"去包化"改造 ⑥ 新增 §5.8：新机器人导入流程与 CLI 契约 ⑦ 新增 §5.9：导入/导出粒度、保存语义与可复现契约
> **读者**：本项目维护者。目标是回答一个问题——**验证、训练、仿真、部署的通用资源如何抽象，以及如何分阶段落地。**

---

## 0. 一句话方案

> **通用资源 = 5 份一等资源（Morphology 形态 / Skill 技能 / Motion 参考动作 / Scenario 场景 / Policy 策略）+ 1 个纯引用组合层（Capability Pack）+ 挂在四个阶段上的质量门。**
> 资源各有一份 schema 独立演进；组合靠引用不靠拷贝；差异全部下沉为数据；事实只在内核出现一次。
> **为何 Motion 升为一等资源**：知识地图 Ch15/Ch16 把"大规模动作模仿"列为独立任务类；`00_resources/` 实测 14 机型中 `unitree_g1` 单机型就有 **152 份动作/参考文件**（AMP npz + LAFAN1/AMASS 重定向 csv）、`unitree_go2` 有 wtw/mimic 参考。参考动作是**带许可与重定向血缘的数据**，既非 Scenario 的地形、也非 Policy，须独立成资源（§2.1.1 / §2.5）。

---

## 1. 现状诊断（实测数据）

### 1.1 机器人包臃肿

| 问题 | 实测证据 |
|---|---|
| 包里塞了完整训练框架 | `unitree_go2/training/source/local_tasks/` 是一整棵源码树（core/integrations/learning/robots/runtime/workflows），192 个 `.py`；go2 一个包 389 个文件，真正机器人资产仅 ~20 个 |
| 包边界泄漏 | `unitree_go2/training/source/local_tasks/robots/unitree/` 下含 **g1 的任务代码**——vendored 源码是整树拷贝，非按机器人切分 |
| mesh 双份 | go2：`model/` 32.5 MB vs `training/` 27.8 MB，同一套几何存两遍 |
| 契约三轨 | `contract.json`(v2) + `contract_v3.json`(v3) + `robot_package.json` 并存，单一事实源被破坏 |
| 训练/仿真配置也在包内 | `assets/robots/*/training/config.json` 把「物理/任务/算法/运行」四层混装；`simulation/config.json` 把 PD/频率/场景/地形/策略混装，且与 `contract.json` 重复 |
| 产物入库 | 全包 329 个 `.pyc`（2.6 MB）；26 个策略 `.onnx` 散落各包 |
| 规模 | 15 个包合计 **~700 MB**；go2w 135.1 MB、g1 98.5 MB、zex-w 84.3 MB、microduck 55.9 MB |

### 1.2 根因

**"机器人包"的概念边界划错了**：现在一个包 = 机器人资产 + 元数据 + **训练代码 + 训练产物**。后两者不属于"资产"。包（package）是分发容器概念，被错误地用来承载抽象资源概念。

### 1.3 已有的好底子（重构是收敛，不是革命）

- `contracts/schema/` 已有 6 份 schema：robot-contract-3.0 / policy-artifact-1.1 / deployment-contract-1.0 / training-profile-1.1 / scenario-contract-1.1 + `observation_convergence.py` 校验器
- `role_resolver.py` 已实现形态/角色抽象（`{LR}_{role}_joint` 展开）——15 台机器人共享一套速度任务的地基
- `plugin_protocol.py` 已有 `match_profiles(requires_morphology / requires_roles)`——天然的技能↔形态匹配器
- `adapters/mjlab/` 已有 `generic_task_builder.py` / `env_factory.py`——通用任务构建已走了一半
- 浏览器 sim2sim（WASM + ORT-Web）+ 服务端 MuJoCo——**双物理后端已在手**
- `export_gate.py` / `deploy_pack.py` / `policy_acceptance.py`——部署门禁雏形

---

## 2. 目标架构：RobotAsset 资源模型

### 2.1 总图

```
┌─ 一等资源 ×4（各有 schema，独立演进）──────────────────────────┐
│                                                                 │
│  ① Morphology 形态资源（robot-contract-3.0 升格）                 │
│     = 事实内核（关节/角色/限位/执行器/质量，唯一）                   │
│     + 表征文件（MJCF/URDF/mesh，可派生渲染，CI 漂移检查）           │
│     + 能力声明（inspectable→trainable→simulable→deployable 四档） │
│                                                                 │
│  ② Skill 技能资源（跨机器人共享，三层细化，见 §3）                 │
│     = SkillSpec（接口语义+考卷，评审制）                          │
│     + SkillRecipe（ManagerConfigs × pipeline 拓扑，注册制）       │
│                                                                 │
│  ③ Scenario 场景资源（scenario-contract-1.1 扩展）                │
│     = 地形 × 模式(sampling/replay/interactive/eval)              │
│       × 传感器投影(特权/可部署 × DR/延迟) × 命令源 × 检查项         │
│                                                                 │
│  ④ Policy 策略资源（policy-artifact-1.1）                        │
│     = ONNX + 契约快照(obs/reindex/normalizer) + lineage/hash     │
└──────────────────────────────┬──────────────────────────────────┘
                               │ 纯引用组合，零拷贝
┌──────────────────────────────▼──────────────────────────────────┐
│  Capability Pack（capability-pack-1.0，新锚点）                   │
│  = morphology_ref × skill_ref [× scenario_ref] [× policy_ref]   │
│  + bindings（四个阶段的质量门）：                                  │
│      verify:   schema 校验 + 引用完整性 + 物理一致性               │
│      train:    管线配置（DR/蒸馏开关）→ 隔离 worker                │
│      simulate: 仿真角色装配 + sim2sim/评估门禁                     │
│      deploy:   deployment-contract 格式 + D0–D6 分级             │
└─────────────────────────────────────────────────────────────────┘
```

### 2.1.1 rev.2 增补：第 5 份一等资源与 Morphology 内核字段

> §2.1 图中"一等资源 ×4"为 rev.1 表述（不改动原图以免失配）；rev.2 升为 5 份，差异如下。

- **⑤ Motion 参考动作资源（`motion-asset-1.0`，新增）**
  `{ id, fps, coordinate_frame, dof_layout, files[{npz|csv|pkl, hash}], retarget_chain[{source_mocap, tool, params}], license, quality_flags }`
  被 `mimic_tracking` 类 Skill 以 `motion_ref` 引用；数据本体可"只登记不复制"（与 `00_resources/` 的 `motion/` 类一致）。
- **Morphology 内核字段补强**（驱动 `role_resolver` 与部署 D0 对账）：
  `actuator[{joint, type: position|velocity|hybrid|bam, kp, kd, torque_limit}]`、
  `foot_type: point|sole|wheel`、`wheel_indices: [...]`（16dof 轮足）、`mass_source: mjcf_compiled|urdf_inertial`。
  依据：TRON1 PF/SF/WF 三形态、M20/Go2W/ZEX-W 的轮组、MicroDuck 腿/轮双形态——当前 `{LR}_{role}_joint` 抽象不足以表达"同一 role、不同执行器/足型"。
- **能力声明口径修正**：四档（inspectable→trainable→simulable→deployable）不是"机器人的属性"，而是 **`(机型 × adapter × 技能)` 的属性**（B2/B2W 训练素材仅来自 IsaacLab，本地无 mjlab 任务，见 §5.6）。

### 2.2 三条结构规则（融合定稿）

1. **内核私有**：Morphology 的事实内核每台机器人一份，唯一事实源；表征文件是内核的**可再生成渲染**（ZEX-W 缺 URDF = "该表征未生成"，不是资源残缺）。
2. **画像可共享**：Skill/Scenario 是一等资源、跨资产共享，存在形态有两种——仓库级共享注册表（`registry/skills/velocity_base.json`）或资产内覆写文件。**解析规则 = 注册表 base + 资产级 override patch，加载时合并，合并结果过校验**（原书 Ch13 "flat 是 rough 的减法"、LLoco profile 覆写、unitree_rl_mjlab `# Set per-robot` 占位参数，三者是同一机制）。
3. **产物回挂**：Policy 从训练流出、经仿真验证、由部署消费，全程携带 `trained_against: 契约hash + normalizer_hash`——证据链是模型自然长出来的，不是外加流程。

### 2.3 六条不变量（防腐化规则）

1. 事实只在内核出现一次；其余位置的重复必须是**可再生成 + CI 漂移检查**的派生视图。
2. 差异数据化，共性代码化：任务差异进 Recipe JSON，机型差异进契约/Patch，共享逻辑上移共享层——**资源只放数据与声明**；算法实现（PPO / AMP 判别器 / CTS / HORA 蒸馏 / critic 结构）属 adapter 的 runner，Recipe 以 `runner_ref`（名 + 版本）引用，不内联代码。
3. 映射是数据不是代码：关节重排（reindex）、观测组件五元组、命令空间全部声明式。
4. 能力分级渐进：inspectable → trainable → simulable → deployable，每档有明确解锁条件，缺失**显式报错不静默回退**。
5. 产物可回溯：每个 Artifact 绑定 contract_hash + normalizer_hash + recipe 版本 + 评测报告。
6. 参考动作是外部数据：Motion 资源只描述动作序列与血缘/许可，被 mimic/tracking 类 Skill 以 `motion_ref` 引用（知识地图 Ch15 的"数据重定向三线"）；不并入 Scenario，也不进包体。

### 2.4 四环节 = 四个投影函数

```
Verify (内核, 表征, 画像)         → 静态校验报告（schema + 物理一致性 + 装配合法性）
Train  (内核, Recipe, 表征)       → Policy（带契约摘要 + hash 回挂）
Sim    (表征, Scenario, Policy)   → 证据数据（回放/评估矩阵/跨后端对照）
Deploy (内核, DeployProfile, Policy) → 部署包（D0 核对后放行）
```

横切方法层的归属（易错点）：**DR 和蒸馏在 Recipe 内部**（Event manager 配置 / pipeline 拓扑字段，Ch08/Ch09）；只有 **SysID 工具链、训练诊断、评估口径**三样挂在投影函数上作为共享规则（物化于 `training_invariants` / `observation_convergence` / `export_gate`）。

---

### 2.5 资源库映射：`00_resources/` 8 类 ↔ RobotAsset 5 资源

`00_resources/`（覆盖 14 机型的文件级证据库，规范见 [`_SPEC.md`](../00_resources/_SPEC.md)）是本方案的**外部证据底座**；下表锁定两者对齐关系，避免各资源重新发明字段：

> **组织方式（v3 起）**：资源库**以来源项目为单位**组织（一个来源项目 = `00_resources/<project>/`，原样保留该项目的
> 目录结构与组织思想），不再按「机型 × 类别」切成物理目录。下表左列的 8 类是脚本对每个项目内文件所做的
> **功能归类统计**（`tools/sync_resources.py` 的 `CATEGORIES`），用来回答「某个项目里的哪类文件归入哪个
> RobotAsset 资源」，**不是物理路径**。

| 资源类别（按功能归类，非物理路径） | 归入 RobotAsset | 在四投影中的角色 |
|---|---|---|
| `model/`（URDF/xacro/MJCF/scene） | Morphology 表征 | Verify 装配检查 / Sim 表征 |
| `contract/`（关节序/limits/PD/action_scale/wheel_indices/obs-act 维度） | Morphology 内核 | Train 装配 / Deploy D0 对账 |
| `training/`（env cfg/reward/command/curriculum/DR/任务注册） | SkillRecipe + Scenario + 方法层 | Train |
| `deploy/`（部署 yaml/FSM/控制频率/推理代码/**策略 onnx·pt**） | Policy + DeploymentContract | Sim 验证 / Deploy |
| `terrain_scene/` | Scenario.World | Sim |
| `motion/` | **Motion（rev.2 新增）** | Train(mimic/tracking) |
| `evaluation/` | Scenario.Checks + PolicyArtifact.eval | Sim / 评估门 |
| `misc/` | 文档（不入 schema） | — |

**由该库直接读出的关键事实（供 §5.6 / §6 使用）**：
- `unitree_b2/b2w` 训练素材仅 `robot_lab/fan_robotlab`（IsaacLab），本地无 mjlab 任务 → **trainable 依赖 IsaacLab adapter**；B2W URDF 另有 loader 阻断。
- `unitree_g1` 是唯一有大规模动作参考的机型（`motion/` 152 + `deploy/` 142，含 AMP/LAFAN1/BeyondMimic/dance）→ Motion 资源与 mimic SkillSpec 的首选样板。
- TRON1 三仓给出官方 `params.yaml`（SF obs36×5 / WF obs28×10）+ 54 个 onnx；ZEX-W 给出 12 个 onnx + 三代真机栈；microduck 给出 61D→14act、63 个 onnx——这三者是 DeployProfile 字段清单的实证样本。

---

## 3. 生态治理：同名不同质怎么不乱

技能的定义与实现分离（这是防乱的核心一刀）：

```
SkillSpec（技能规格）   ← core/ 收编，评审制，少而精
  velocity@2.0 = 命令语义 + obs/action 契约语义 + requires_morphology
               + benchmark（考卷：DR 网格 + 及格线，见 §5.3）
        ▲ implements（契约对账，fail-closed）
SkillRecipe（技能实现） ← core/+community/ 注册制，多而杂
  core/velocity-mjlab-ppo / core/velocity-mjlab-cts / community/velocity-unilab-sac …
        ▲ produces
Policy（策略产物）      ← 强制携带出身证明 {spec_ref, recipe_ref@version, trained_against, eval_report}
```

**SkillSpec 首期目录**（对齐知识地图 §1 的 6 大任务类，含依赖关系）：

| Spec | 任务类（知识地图） | requires_morphology | 备注 |
|---|---|---|---|
| `velocity@2.0` | 1 速度跟踪（Ch13/14） | 任意 P/W 足式 | 地基；导航 = `command_source:planner` 复用，无需重训 |
| `mimic_tracking@1.0` | 2 动作模仿（Ch15/16） | 四足/人形 | 需 `motion_ref`；tracking（显式跟踪）与 AMP（对抗先验）两种 Recipe |
| `parkour_perceptive@1.0` | 3 感知跑酷（Ch18） | 带相机机型 | = velocity + student(深度)；依赖 `pipeline.distill_2stage` |
| `manip_dexterous@1.0` | 4 固定基座/灵巧手（Ch17） | 灵巧手/臂 | wuji_hand in-hand SO(3)、g1-manip-challenge |
| `loco_manip@1.0` | 5 复合/全身（Ch19–21） | 带臂机型 | G1-29dof / M20_Piper / Go2+Arm |
| `dynamic_athletic@1.0` | 6 高动态竞技（Ch26–28） | 高功率机型 | 远期；网球/羽毛球 |

> **方法层（知识地图的"第 7 层"）不建 Spec**，各自落到既有落点：DR → `Recipe.event`；蒸馏 → `Recipe.pipeline.topology`；actuator 建模 → `Morphology.内核.actuator`；SysID/诊断/评估口径 → 共享规则（§2.4）。

**防乱五道闸**：

| 闸 | 机制 | 工作区先例 |
|---|---|---|
| 1. 契约防火墙 | obs/reindex/命令语义对不上**拒绝绑定**（fail-closed） | TRON1 部署端 `RL_TYPE=isaacgym\|isaaclab` 双轨切换：两套框架产物遵守同一份 params.yaml，部署代码零改动 |
| 2. 统一评测基准 | 所有实现跑同一份考卷，成绩写进产物，**效果差异变成可比较的赛马** | RoboGauge 八指标 + 四级流水线（§5.3） |
| 3. 命名空间+信任分级 | `core/*`（官方评审保底）vs `community/*`（成绩说话） | npm scope / HuggingFace 模式 |
| 4. 版本化 | Spec/Recipe/schema 独立 semver；规格升级不隐式漂移 | contracts/schema 已有版本号传统 |
| 5. 谱系回溯 | Policy 强制 lineage：哪个规格、哪个实现、什么版本、考了多少分 | kaiwu_rl 把分数写进模型目录名（`go2_moe_cts_137k_0.6713`） |

一句话：**接口归一（不合即拒）、评测同尺（同一考卷）、来源可查（谱系强制）、命名有主（core 收编）**——一千个人用一千种方法训 velocity 不是混乱，是赛马场。

---

## 4. 参考项目对照（各自借鉴什么）

| 参考项目 | 实地分析结论 | 本项目借鉴 |
|---|---|---|
| **LLoco**（`lain_job/LLoco`） | 机器人 = `*_constants.py` + `xmls/`；任务差异 = frozen dataclass Profile，通用 MDP 复用上游；新增机器人 4–6 个文件；"资产入库、产物出库" | Profile 数据化、共享/差异切分方式、产物排除策略 |
| **1000frames** | 机器人 = 元数据+URDF包+MJCF包+ONNX 四资源独立演进，靠 contract 关联；`contract.reindex` 关节重排是数据；地形模板 `<include>`+运行时替换实现"一套地形×任意机器人"；完备度分级 + 缺失显式报错 | 四资源独立演进、reindex 数据化、场景模板化、能力分级 |
| **unitree_rl_mjlab** | 「共享工厂 + `# Set per-robot` 占位 + 机器人层填表」三段式；新技能不建任务族，在共享 mdp 库加模块（trick_*）config 层换装配；**deploy.yaml 策略 IO 契约**（joint_ids_map/step_dt/PD/actions scale+offset/observations term scale+clip+history）；ONNX metadata_props 双重元数据 | Recipe base+override 机制、共享 MDP 库组织、**部署契约字段清单**（§5.4）、ONNX 元数据烘焙 |
| **kaiwu_rl** | RoboGauge 八指标（§5.3）+ 四级流水线（single→multi→level→stress）+ 训练中异步评测（分数进模型目录名）；部署侧 `policy_dir = policy.onnx + deploy.yaml` 两文件契约；FSM 全 YAML 声明式 + 多策略热切换槽位；七项跨仓对账清单 | **SkillSpec benchmark 的考卷设计**、产物两文件契约、FSM 模板、评测驱动选模 |
| **TRON1 三仓** | params.yaml 一份紧凑控制契约驱动 10 个型号变体（obs/history/action/PD/decimation）；部署端按 ROBOT_TYPE 路由、RL_TYPE 双轨 | DeployProfile 的形态（一契约驱动多变体）、契约防火墙的活证 |
| **DeepRobotics sdk_deploy** | 官方 Lite3/M20：C++ 状态机（idle/damping/standup/rl_control）+ ros2 `drdds` + `policy.onnx` | 官方部署状态机模板；Contract ↔ 部署字段对账 |
| **LeggedGym-Ex** | 三后端（IsaacGym/Genesis/IsaacSim）× 20+ 论文方法（wtw/ts/ee/cts/dreamwaq/cat/sysid/ts_depth/nav/parkour/amp/deepmimic/backflip） | `pipeline.topology` 与方法层枚举的实证来源 |
| **Dreamwaq / him_dog** | DreamWaQ 隐式教师-学生（16 latent）；HIMLoco 45↔46 维热切换 | `pipeline = latent/asymmetric` 对照；部署期维度热切换 |
| **UniLab** | MuJoCo/Motrix 双 adapter + Sim2Sim `deny/warn/allow` 契约 + off-policy（SAC/TD3/FlashSAC/HORA） | Scenario 契约与跨后端门禁的既有实现；跨算法 Recipe 样本 |
| **robo_re(robot_retargeter)** | SMPL-X → 多机型 mink IK 重定向 + LAFAN1/ACCAD 数据集 | **Motion 资源**的血缘/重定向来源 |
| **LeggedSkillDeploy / g1-manipulation-challenge** | 多技能状态机 + 技能化 ONNX（walker/reacher/croucher/rotator、dance_102…） | FSM 模板；"一个策略 = 一个技能"的切分先例 |

---

## 5. 关键设计决策

### 5.1 Recipe = 7 Manager 配置 × 管线拓扑（原书校准）

训练任务的权威分解来自 Ch04/Ch22：一个任务 = task registry 中一组配置函数，内容物是 **7 个必配 Manager**（Event → Command → Action → Observation → Termination → Reward → Curriculum）的配置，外加 Metrics/Recorder 默认值。**管线拓扑独立成字段**（Ch09 §9.6 决策树与成本表）：

```jsonc
// registry/skills/velocity_base.json（共享基座示例骨架）
{
  "schema": "skill-recipe-2.0",
  "spec_ref": "core/velocity@2.0",
  "pipeline": { "topology": "asymmetric_ac",          // direct|asymmetric_ac|rma|distill_2stage|distill_3stage
                "stages": [] },                        // 蒸馏类才填：阶段 DAG
  "managers": {
    "command":     { "type": "uniform_velocity", "resampling_time_range": [8,12], "rel_standing_envs": 0.1 },
    "action":      { "type": "joint_position", "scale": 0.25, "use_default_offset": true },
    "observation": { "groups": { "actor": ["$base_proprio"], "critic": ["$base_proprio", "$privileged"] },
                     "chain": ["noise","clip","scale","delay","history"] },
    "reward":      { "stack": ["tracking","regularization","style","contact"] },
    "termination": { "time_out": 20, "terms": ["fell_over"] },
    "event":       { "dr": ["friction","base_mass","push"] },
    "curriculum":  { "axes": ["command_range"] }
  }
}
// assets/robots/zex-w/profiles/velocity.json（资产级 patch，只写差异）
{ "override": {
    "managers.command.ranges": { "lin_vel_x": [-1.0, 1.5] },
    "managers.action.scale": { "leg": 0.25, "wheel": 20.0 },
    "managers.event.dr": ["friction","base_mass","push","com_offset","action_delay"]
} }
```

观测组件五元组（同时解决盲走/感知、训练/部署一致性、特权蒸馏三问题）：`(source, role[actor|critic|teacher|student], history, encoder, deployment_available)`；部署观测 = 过滤 `deployment_available=true ∧ role=actor`，`observation_convergence.py` 升格为该规则校验器。

### 5.2 Scenario = 仿真核 × 角色装配（放弃"按功能分仿真"）

原书证据链（Ch02/03/08/18/23/24/25）：仿真不是"遥控/感知/导航三种功能"，而是 9 个角色——训练采样器 / L0–L6 基建验证 / sim2sim 跨后端验证 / 传感器仿真（特权+可部署）/ DR 评估矩阵 / D0–D1 验收 / 诊断回放 / 真机协议替身 / 物理差异研究。统一为：

```
Scenario = World(表征+地形) × Mode(sampling|replay|interactive|headless_eval)
         × Sensors(特权 height_scan/segmentation | 可部署 depth/RGB/IMU，含 DR/延迟预算)
         × CommandSource(teleop|script|planner|dataset|perception)
         × Checks(L0-L6 探针 | sim2sim 对照 | DR 网格 | D0-D1 验收 | AGILE 质量指标)
         × Recorders(指标 + 行为回放)
```

导航 = `CommandSource: planner`（规划器输出 cmd_vel → 复用同一 velocity 策略，**无需重训**）；感知策略 = 深度图走 `Sensors → obs_component`（student 策略）而非导航栈；**外挂感知** = 传感器/感知模块出决策与指令，载体 `CommandSource: perception|script`，此时 RL 只负责运动、**可以是盲狗**（用户裁决 2026-09-12）。三条路径同一框架——判 `sim_surface=advanced` 看的是「这条策略被怎么用」，而不是「策略是否吃传感器」。

### 5.3 SkillSpec 考卷设计（借鉴 RoboGauge）

| 层 | 内容 | 来源 |
|---|---|---|
| 指标 | 8 项归一化：dof_limits / lin_vel_err / ang_vel_err / dof_power / orientation_stability / torque_smoothness / friction_margin / zmp_margin；几何平均得 quality_score | RoboGauge `base_gauge_config.py` |
| 指令剧本 | max_velocity / diagonal_velocity / target_pos_velocity（时长+reset 条件可配） | RoboGauge `velocity_goals.py` |
| 环境矩阵 | 地形(flat/wave/slope/stairs/obstacle)×难度(1–10)×材质 × DR(action_delay/base_mass/friction/观测噪声) | RoboGauge `mujoco_config.py` |
| 流水线 | single → multi(多 seed×质量×摩擦) → level(3 seed 全过升级) → stress(全矩阵，mean@50 ± var，单一 benchmark 总分) | RoboGauge 四级 pipeline |
| 及格线 | tracking>0.6、fall<10%、OOD ±20% 平缓退化（Ch08 §8.7 评估三层次） | 原书 Ch08 |

实现取舍：**不引入 IsaacGym**，用现有服务端 MuJoCo（evaluation_api 扩展）+ 浏览器 WASM 双后端执行；第一层 sim2sim 对照（同引擎 GPU/WASM 一致性）零成本具备。

### 5.4 部署契约与工程模板（借鉴 unitree_rl_mjlab + kaiwu_rl）

部署产物 = **两文件目录契约**（kaiwu policy_dir 模式）：`exported/policy.onnx` + `params/deploy.yaml`。deploy.yaml 由 `deploy_pack.py` 从 deployment-contract **生成**（不再手写），字段清单（七项对账，三仓必须一致）：

```yaml
step_dt: 0.02
joint_ids_map: [3,4,5,0,1,2,9,10,11,6,7,8]   # 策略关节序 → SDK 电机序（reindex 是数据）
default_joint_pos: [...]
stiffness: [...] / damping: [...]
actions: { scale: [...], offset: [...], clip: [...] }        # target = raw*scale + offset
observations:                                                 # term 顺序 = 拼接顺序
  base_ang_vel:      { scale: [...], clip: null, history_length: 1 }
  projected_gravity: {...}
  velocity_commands: { params: {command_name: base_velocity}, ... }
  # …（normalizer 是否烘焙进图必须显式声明，Ch23 ONNX 部署边界）
```

ONNX 侧双重元数据（借鉴 mjlab `exporter_utils.attach_metadata_to_onnx`）：joint_names / observation_names / scales / history_length / action_scale / default_joint_pos 写入 `metadata_props`。FSM 模板全 YAML 声明（`FSM._` 状态表 + transitions DSL + 超时/姿态安全兜底），多技能 = 状态节点 + policy_dir 槽位。

### 5.5 D0–D6 验收链挂点（原书 Ch23 §23.8）

| 级 | 内容 | 本项目落点 |
|---|---|---|
| D0 静态核对 | joint order/normalizer/action scale 对账（"5 分钟发现 50%+ 部署 bug"） | `export_gate` + 契约校验（已有雏形，升级为阻断性） |
| D1 仿真回放 | 固定 seed replay，eval reward ±5% | 浏览器 sim2sim 升格：`tools/sim2sim_validator.py` 纳入流水线 |
| D1+ 跨后端 | 同引擎 WASM vs 服务端对照（差异 <10% 不处理，>20% 查 obs 构建） | **双 MuJoCo 后端已在手，零成本新增** |
| D2–D6 | 影子模式/悬空/平地/任务片段/完整任务 | 真机侧，本期只做接口约定（telemetry 字段），不实现 |

---

### 5.6 14 机型 × 能力档位（依据 `00_resources/` 覆盖）

> 档位按 `(机型 × adapter × 技能)` 评估；此处给"当前已具备素材的最高档"与主要缺口，"无素材"不等于"不支持"。

| 机型 | 形态 | 素材现状（`00_resources/`） | 最高档 | 主要缺口 |
|---|---|---|---|---|
| unitree_go2 | M-P 12dof | model/contract/training/deploy 齐（17 onnx） | deployable | —（MVP 主线） |
| unitree_go2w | M-W 16dof | 288 deploy（含 tricks / legs_only onnx） | deployable | tricks 评测口径待统一 |
| unitree_go1 | S-P 12dof | LeggedSkillDeploy + playground + unilab；8 pt | trainable→deployable | 无本地 mjlab 任务（以社区源为主） |
| unitree_b2 | L-P 12dof | model + rl_sar 部署（.pt/.onnx） | trainable* | 训练仅 IsaacLab（*依赖 adapter） |
| unitree_b2w | L-W 16dof | model + rl_sar 部署 | trainable* | 同 B2 + URDF loader 阻断待修 |
| unitree_g1 | 人形 29dof | training 235 + motion 152 + deploy 142 | deployable + mimic | 动作许可/血缘待登记 |
| deeprobotics_lite3 | S-P 12dof | 官方 sdk_deploy + rl_sar | deployable | — |
| deeprobotics_m20 | M-W 16dof | m20_rl_isaacsim + sdk_deploy + Dreamwaq | deployable | 契约常量在共享文件，需显式化 |
| limx_tron1_pf/sf/wf | 双足 PF/SF/WF | 官方三仓 + 54 onnx（合计） | deployable | 足型/轮组需入内核 |
| microduck | 腿/轮双形态 14dof | 63 onnx + 61D→14act + sim2real | deployable | 语义偏 manipulation |
| wuji_hand | 灵巧手 | wuji-mjlab 训练 + deploy/reorient | deployable(manip) | 非 locomotion，走 `manip_dexterous` |
| zex-w | M-W 16dof | rc_mjlab 训练 + 三代部署 + 12 onnx | deployable | 契约 YAML 未被 C++ 读取（真值漂移） |

### 5.7 训练配置 / 训练 / 低级仿真 / 高级仿真 的"去包化"改造

**问题**：现实现仍以"机器人包"为锚——这四件事都长在 `assets/robots/<id>/` 内，`robot-package-1.1` 事实上成了资源锚点，与 §2 的 5 资源模型冲突。

| 关注点 | 现状位置（包内） | 问题 |
|---|---|---|
| 训练配置 | `assets/robots/<id>/training/config.json` + `training/profiles/*.json` | 同一任务配置被复制到 14 个包；物理/任务/算法/运行四层混装 |
| 训练 | `assets/robots/<id>/training/source/local_tasks/`（整棵源码树）+ `adapters/mjlab` | 包内含训练代码；go2 包里出现 g1 任务 |
| 低级仿真 | `assets/robots/<id>/simulation/config.json`（PD/扭矩/频率/场景/地形/策略混装）+ `simulation_api` + `web/sim2sim` | 物理事实与 `contract.json` 重复；地形/策略按机器人各存一份 |
| 高级仿真 | `navigation_api` / `map_editor_api` / `terrain_api` / `route_planner` / `scenario_maps` | 无契约、无与 locomotion policy 的标准接口；机器人无关却无共享锚点 |

**总原则**：这四件事都不是"机器人的属性"，而是 §2 的**投影函数**；`robot_package.json` 由"资源锚点"**降级为"可选分发容器"**，Capability Pack（M1）成为新的默认锚点。

#### (1) 训练配置 = 三层拆分，配置离开包
- **物理层 → Morphology 内核**：`simulation/config.json` 的 `stiffness / damping / torque_limits / armature / frictionloss / control_hz / physics_hz / decimation` 上移进 `robot-contract-3.0`（它们必须与部署 D0 对账一致，不能两处各写一份）。
- **任务层 → SkillRecipe**：`training/config.json` 的 `command_ranges / reward_scales` 与 `profiles/*.json` 的差异 → 仓库级 `registry/skills/<spec>.json`；包内只留 `assets/robots/<id>/profiles/<skill>.patch.json`（override，只写差异）。
- **运行层 → Run（非资源）**：`num_envs / max_iterations / learning_rate / seed / save_interval / terrain` → 训练时生成 `runs/<run-id>/resolved-config.json`，不落包。
- 顺带消灭重复：`terrain` 从训练配置移出 → Scenario。

#### (2) 训练 = (内核 + Recipe + 表征) → Policy 的投影
- 把 `assets/robots/*/training/source/local_tasks` 的框架部分（core/integrations/learning/runtime/workflows）提取到仓库级 `tasks/`（或并入 `adapters/mjlab`），`package_extension` entrypoint 改指共享层（= M4）。
- 包内 `.py` → 0；新增机器人 = 1 目录 + 3 JSON + 模型文件。
- **Run 是一等对象**：`runs/<run-id>/{resolved-config.json, environment-lock.json, checkpoints/, metrics/}`；包与资源里不出现训练产物。
- adapter 输入改为 `Pack(morphology_ref × skill_ref × scenario_ref) + run-spec`，输出 `policy.onnx + policy-artifact.json`；`BackendAdapter` Protocol 的 env/runner/exporter 三入口不变。

#### (3) 低级仿真 = Scenario(replay|interactive) × Morphology 表征 × Policy
- 身份重定义：低级仿真不是独立功能，而是 **`Scenario.Mode ∈ {replay, interactive}`** 且 `Checks ⊇ {D1 固定 seed 回放, WASM↔服务端对照}`。
- 场景/地形归 **Scenario**：地形 XML 从"每机器人一份"（`web/sim2sim/assets/<robot>/*.xml`）改为 **Scenario 资产 + `<include>` 占位 + 运行时替换**（1000frames 模式），机器人只提供 MJCF 表征。
- 策略归 **Policy 注册表**：`simulation/policies/*.onnx` 与各包散落的 26 个 onnx 集中为 `policies/<artifact-id>/{policy.onnx, deploy.yaml, policy-artifact.json}`。
- 执行器可替换：`simulation_api` 降级为 Scenario 的一个 executor；WASM 与服务端 MuJoCo 是同一 Scenario 的两个 executor，不是两个概念。

#### (4) 高级仿真 = Scenario(planner|perception|dataset) + 导航栈作为接口 executor
- 统一进 Scenario 扩展轴：`CommandSource ∈ {planner, perception, dataset}` + `Sensors` + `Checks`。**导航 = planner 输出 cmd_vel 复用同一 velocity 策略，无需重训**（§5.2）；**外挂感知 = perception**（传感器/感知模块做目标判定与决策，RL 只负责运动、可为盲狗）。两条都**不需要**策略吃传感器。
- 新契约 `NavigationScenario`（scenario-contract 的 profile）：地图/代价地图、规划器（A*/Dijkstra/Hybrid A*）、航点/语义目标、避障、传感器（LiDAR/深度/RGB/IMU）与频率、指标（成功率/路径长/碰撞数/耗时）。
- 上层栈**外挂**：ROS2 / Nav2 / RTAB-Map / OctoMap / VLM 作为 `adapters/nav_ros2` executor，用 D2–D6 telemetry 接口对接（§5.5），不进核心。
- 复用证据：`00_resources/{unitree-go2-slam-nav2, Odin-Nav-Stack, LightNav-0}` 已含 RTAB-Map+Nav2、Odin1+NeuPAN、LightNav(Qwen3-VL) 三条导航参考；`backend/terrain_gen`（ArenaX 移植）与 `map_editor_api` / `route_planner` 产出的地图与路线即 Scenario 资产。

#### 归属总表
| 关注点 | 现状（包内） | 目标归属 | 搬迁动作 |
|---|---|---|---|
| 训练配置 | `training/config.json` + `profiles/` | 物理→Morphology 内核；任务→SkillRecipe；运行→Run | 三层拆分；`registry/skills` + 包内 patch |
| 训练 | `training/source/local_tasks` | adapter（投影函数）+ `runs/` | 框架上移 `tasks/`；包内零代码 |
| 低级仿真 | `simulation/config.json` + `simulation_api` + `web/sim2sim` | Scenario(replay/interactive) × 表征 × Policy | 物理参数上移；地形入 Scenario；策略入 `policies/`；executor 可换 |
| 高级仿真 | `navigation/map_editor/terrain/route` API | Scenario(planner/perception/dataset) + nav 接口 executor | 建 `NavigationScenario`；nav 栈只做接口；cmd_vel 解耦 |

> 落地节奏建议：§(1) 随 M2/M3 一起做；§(2) = M4；§(3) 折入 M5 的 sim2sim 升格；§(4) 作为 Phase 2/3，先在 `scenario-contract` 下加 `NavigationScenario` profile，不改核心。

### 5.8 新机器人导入与 CLI 契约（"导入即可训练"的落点）

**现状实测**：`scripts/legged_studio_cli.py` 已是 HTTP 契约门面（与 Web 同一 API），但只覆盖 `algorithms / hardware / validate-model / validate-contract / validate-scenario / maps / simulate / train / evaluate / navigation`；且 **`train` 的输入是 Robot Contract JSON（机器人级）**，不是 Pack（§2）。技能注册仍在 Python 里（`adapters/mjlab/recipe_registry.py` 的 `TASKS` + `env_factory` 奖励表）——改技能 = 改代码。`tools/` 里 `urdf_validator / urdf_to_mjcf / stl_volume / migrate_contract_v3 / generate_contract_models / validate_training_smoke / sim2sim_validator` 齐备，但**各自为战、未串成一条 onboarding 命令**。

**分层体检**（结论：分层方向对，缺 L1、且 L0 放错位置）：
| 层 | 应然 | 现状 | 差距 |
|---|---|---|---|
| L0 资源 | 5 资源数据化 | 训练/仿真配置在包内；技能在 Python | L0 位置错（§5.7） |
| L1 装配 | Pack 纯引用 | `capability-pack-1.0` 未落地 | 缺 |
| L2 执行 | adapter 的 env/runner/exporter | `generic_task_builder` + `param_registry/catalog/descriptors/groups` 已在 | 良好 |
| L3 门禁 | verify/train/sim/deploy 四门 | `export_gate` / `policy_acceptance` / `sim2sim_validator` 雏形在 | 需串成流水线 |

**目标 CLI（每条命令输出 `--json`，并支持 `--offline` 直连内核以便 CI 无后端）**：
```
ls robot onboard <dir>     # 导入：URDF/MJCF/mesh → 校验 → 生成 contract v3 草稿 + 表征索引
ls robot verify <id>       # 物理/引用/装配一致性（fail-closed）
ls robot pack <id> --skill velocity --scenario flat   # 生成 Pack（纯引用）
ls train start --pack <pack.json> --profile fast|standard|high [--seed N]   # → run-id
ls train status|logs|stop --run <id>
ls eval run --run <id> --scenario eval_flat
ls sim replay --pack <pack> --backend wasm|server       # 低级仿真
ls sim nav --pack <pack> --map <m> --waypoints "x,y;..."  # 高级仿真
ls export onnx --run <id>                                # export gate
ls deploy pack --run <id> --target unitree_sdk2          # 先生成、不自动上机
ls {pack,run,artifact} list
```
其中 `onboard` 是新机器人**唯一必需的人工介入点**，其余命令应可全自动。

**让"导入即可训练"成立的 4 件事**：
1. **技能/奖励注册表数据化**：`recipe_registry.TASKS` + `env_factory` 奖励表 → `registry/skills/*.json` + `registry/rewards/*.json`（`skill-recipe-2.0`），Python 只做加载与合并。
2. **Morphology 自动装配**：由 `role_resolver` + `param_registry` 从 contract v3 生成 env/actuator/reward 绑定（`generic_task_builder` 已走半程）；新机器人只需 contract v3 + 表征。
3. **Pack 成为唯一训练输入**：`resolve_recipe` 改吃 Pack（`morphology_ref × skill_ref × scenario_ref`）而非 contract（= M1）。
4. **能力档位 fail-closed**：缺 `actuator/foot_type/wheel_indices` 等字段在 `verify` 阶段显式报错（§2.1.1），不静默降级。

**最低验收**：新机器人 = 1 目录 + 3 JSON + 模型文件；`onboard → verify → train start → export onnx` 全绿且**不改一行 Python**。

### 5.9 导入/导出粒度、保存语义与可复现契约

**现状实测**：只有**一种**导出单位——项目包（`backend/project_api.py` 的 `/api/project/export`）：zip 内含 `manifest.json`（`legged-studio-project-1.0`）+ `robots/<id>/**`（**整包**，含 mesh 与 vendored 代码）+ `training/config.json` + `scenarios/active.json`；导入侧白名单 `{imports, robots, training, scenarios, manifest.json}`、≤5000 文件、自动补 `contract.json`/`robot_package.json`、以 `content_sha256` 去重、同名不同内容加 `<id>_<hash10>` 后缀。**结论：粒度太粗（只能"整机器人"），缺技能/策略/场景的独立粒度，也缺环境锁 / seed / 许可。**

#### (1) 五类导出物（按粒度与收件人拆分）
| 导出物 | 内容 | 收件人场景 | 体积 |
|---|---|---|---|
| Morphology 包 | contract v3 + 表征(MJCF/URDF/mesh) + profiles patch | 要这台机器人 | 中（含 mesh） |
| Skill 包 | SkillSpec + SkillRecipe(base+override) + `runner_ref` | 要这个技能的用法 | 小（纯 JSON） |
| Scenario 包 | World/地形/传感器/命令源/Checks | 要这套评测/导航场景 | 中（地形资产） |
| Policy 包 | onnx + deploy.yaml + policy-artifact.json + normalizer | 要这个策略（sim2sim/上机） | 小 |
| Bundle（可选） | Pack（引用）+ 被引用物的离线副本 + hashes | 一键复现 | 视引用 |

**容易漏掉的第 6–11 项**：Run 记录（resolved-config / env-lock / metrics / checkpoints）、**Motion 数据**（mimic/tracking 必需，大件，默认只带引用 + hash）、**考卷与及格线**（Scenario.Checks）、**门禁配置**（DENYLIST / D0 检查项）、**依赖锁**（uv.lock / environment-lock）、**许可与出处**（license / SPDX / source）、**部署目标与 telemetry**。

#### (2) 保存语义（"改了怎么存、怎么算"）
| 对象 | 写入规则 | 定性 |
|---|---|---|
| Morphology 内核（contract v3） | **只读 + 版本化**：改动即产出新 `contract_hash`，不就地覆盖 | 真值源 |
| Skill / Scenario 画像 | **base + override patch**：用户只写 `profiles/*.patch.json`，加载时合并 | base 真值、patch 派生 |
| Run / PolicyArtifact | **不可变 + 引用 + hash**：记录当时 `contract_hash / normalizer_hash / recipe 版本 / seed`；要改 = 派生新 run | 产物 |
| deployment-contract.* | **生成物，禁止手改**（`deploy_pack.py` 已声明） | 派生自 contract v3 |
| 导入的他机包 | 落 `workspace/packages/<id>`；`content_sha256` 冲突则 `<id>_<hash10>` | 副本 |

三条规则：**内容寻址**（`_tree_hash` 已实现）、**加载即校验**（hash 不符 fail-closed）、**覆盖 = 派生，不改原物**。

#### (3) 可复现三档承诺
| 档 | 复现什么 | 必需物 | 现状 |
|---|---|---|---|
| **R1 复现"看"** | sim2sim 回放策略 | Policy 包 + Morphology 包 + Scenario 包 + ORT/MuJoCo | **可保证**（双 MuJoCo + ORT-Web 已在） |
| **R2 复现"用"** | 重跑评测得同一分数 | + Checks/及格线 + 固定 seed + 场景版本 | **可保证**（需把 seed/场景版本写进 run） |
| **R3 复现"训"** | 重新训练近似复现 | + 环境锁 + Motion/数据 + `runner_ref` 版本 + 硬件口径 | **需新增** |

**为达 R1–R3 必须补 5 件事**：
1. `PolicyArtifact.pytorch_model_path / onnx_model_path` 由**绝对路径**改为**包内相对路径 + hash**（当前是自由 `str`，跨机必断）。
2. 新增 `environment-lock.json`（uv.lock / torch / cuda / mjlab 版本），随 run / artifact 保存。
3. **seed 固化进 run** 并在 Artifact 显式记录。
4. **许可/出处**字段随每个资源（license / source / SPDX）；mesh 与第三方权重默认"引用不内嵌"，bundle 需显式声明可分发。
5. 导入侧校验：缺依赖 / 哈希不符 / 许可缺失 → **fail-closed 并给出人话报错**。

**最低验收**：`ls export bundle --pack <p> --embed-policy --offline` 产出 zip；在**无本仓库的干净机器**上可 sim2sim 回放（R1）→ 复算评测分数（R2）；R3 输出 environment-lock 与缺口清单。

---

## 6. 分阶段实施方案

> 原则：每阶段独立可验收、回退成本为零；go2 永远放最后（最大、引用最多）；每阶段结束跑全量测试基线（backend 134 + contracts 71 + obs 18）。

### M0 · 卫生基线（0.5 天，零风险）

- `git rm --cached` 清除 329 个 `.pyc` 存量（`.gitignore` 已有规则，补 `**/__pycache__/` 到 assets 层）
- 修复 `contracts/tests/test_path_bootstrap.py` 3 个 Windows 路径既有失败（或标记 `skipIf(win32)` 并记录）
- 建立基线：包体积/文件数清单（本文 §1.1 数据）+ 测试全绿截图
- **验收**：`git ls-files "*.pyc"` 为空；测试基线全绿

### M1 · 锚点：capability-pack-1.0（1–2 天，纯加法）

- 新增 `contracts/schema/capability-pack-1.0.json`：只有 `morphology_ref / skill_ref / scenario_ref / policy_ref + bindings{}`，**不动任何现有文件**
- Go2 velocity 示例 Pack 一份 + `tools/generate_packs.py`（从现有 `robot_package.json` 批量生成 15 个默认 Pack）
- **验收**：Pack schema 校验通过；`backend/plugin_protocol.py` 能列出全部 Pack
- **回退**：删新增文件即可

### M2 · Morphology 独立化（3–5 天）

- **契约单轨**：v3 为唯一入口；`contract_migration.py` 生成 v2 兼容视图（双读过渡一个版本后 v2 退役）；CI 加契约漂移检查（`tools/generate_contract_models.py` 已有同套路）
- **mesh 单副本**：zex-w 先行做样板（84.3 MB），改 MJCF 引用路径指向 `model/assets`，删 training 下 mesh 拷贝；验证后推广。预期 go2 63.8→~35 MB
- 表征标记可再生成：`robot_package.json` 加 `representations.{mjcf,urdf,meshes}` 字段（`null` = 未生成，合法状态）
- **验收**：`test_migrated_contract_v3` 全绿；zex-w/go2 sim2sim 冒烟通过；体积下降达标

### M3 · Skill 层（5–8 天）

- `training-profile-1.1` → `skill-recipe-2.0`：加 `command_space` 枚举 + 观测五元组 `role/deployment_available` + `pipeline.topology` 字段（纯加法）
- 共享注册表 `registry/skills/velocity_base.json`（从现有 go2 velocity 逆向描述，证明表达力）+ base+override **合并解析器**（放 `contracts/` 零依赖层）+ 合并结果校验
- `observation_convergence.py` 升格为四角色管线校验器
- SkillSpec 首份：`registry/specs/velocity@2.0.json`（接口语义 + 考卷引用）
- **验收**：velocity_base + zex-w patch 合并后 == 现有 zex-w velocity 任务配置（对拍）；用 Recipe 描述出 AMP/mimic 任务（不写实现，只验证 schema 表达力）

### M4 · 共享层收编（1–2 周，最重）

- `training/source/local_tasks` 框架部分（core/integrations/learning/runtime/workflows）提取为仓库级 `tasks/`（或并入 `adapters/mjlab`），`package_extension` entrypoint 改指共享层
- 包内只留机器人专属差异，且尽量数据化为 profiles patch；按形态分批：quadruped_12dof → wheel_leg_16dof → 双足/人形 → go2 最后
- 每批跑：backend 单测 + 对应包训练冒烟（`tools/` 已有训练冒烟脚本）+ sim2sim 验证
- **验收**：包内 `.py` 文件数 → 0（或仅剩入口 stub）；训练冒烟全绿；总文件数 go2 389 → ≤50

### M5 · 产物与证据链（1–2 周）

- **产物出库**：onnx 集中为顶层 `policies/` 注册表（两文件契约：onnx + deploy.yaml），契约里只留引用 + hash；ONNX 烘焙 metadata_props（§5.4）
- **评测矩阵**：`evaluation_api` 扩展为 §5.3 考卷（指标 → 指令剧本 → 环境矩阵 → stress 流水线），与 export gate 联动（达标才放行 deploy_pack）
- **sim2sim 升格验收场**：D1 固定 seed 回放 + WASM/服务端双后端对照 + DR 网格
- **deploy.yaml 生成器**：`deploy_pack.py` 从 deployment-contract 生成 §5.4 字段（含 normalizer 烘焙声明）
- **验收**：go2 全链路演示——训练 → 导出（自动评测报告）→ 浏览器回放对照 → deploy.yaml 生成 → D0 通过

---

## 7. 度量指标（重构成功的判据）

| 指标 | 现状 | 目标 |
|---|---|---|
| assets/robots 总体积 | ~700 MB | ≤ 300 MB |
| go2 包文件数 | 389 | ≤ 50 |
| `.pyc` 在库数 | 329 | 0 |
| 契约事实源 | 3 轨 | 1 轨（+派生视图） |
| 新增机型成本 | 复制 ~200 文件的树 | 1 目录 + 3 JSON + 模型文件 |
| 新增技能实现成本 | 复制源码树 | 1 份 Recipe JSON（override <100 行） |
| 策略↔机器人对账 | 无 | 全自动（reindex + hash，D0 阻断） |
| Motion 参考动作入库 | 0（散落 G1/Go2 各源） | `motion-asset-1.0` 登记 G1/Go2 参考动作 + ≥1 条经 D1 回归 |
| 机型能力档位覆盖 | 无明示 | 14 机型逐档标注（§5.6）：B2/B2W 标注 adapter 依赖 |
| 测试基线 | backend 134 + contracts 71（3 既有失败）+ obs 18 | 全绿（含 Windows 路径修复） |

---

## 8. 风险登记册

| 风险 | 影响 | 对策 |
|---|---|---|
| vendor 树收编破坏隔离 worker 的 `extension_entrypoint` 加载 | 训练全挂 | M4 保持 entrypoint 协议不变、只改指向；go2 放最后；每批冒烟 |
| mesh 去重后 MJCF 引用路径错误 | 仿真/检查空白 | zex-w 样板先行；`test_migrated_contract_v3` + sim2sim 冒烟兜底 |
| 契约单轨破坏 v2 消费方 | 前端/后端读契约失败 | 双读过渡期 + 兼容视图 + 漂移 CI，不硬切 |
| 评测矩阵范围蔓延（想对齐 IsaacGym 生态） | M5 失控 | 只用现有双 MuJoCo 后端；不引入新训练框架 |
| Skill 开放后生态混乱（同名不同质） | 长期 | §3 五道闸：契约防火墙 fail-closed + 统一考卷 + 命名空间 + 版本化 + 谱系强制 |
| 评测作弊（针对考卷过拟合） | 考卷失真 | 固定 seed + OOD ±20% 区间（Ch08）；core 规格评审制 |
| 能力档位依赖 adapter | B2/B2W 等训练素材仅在 IsaacLab，本地无 mjlab 任务 | 能力声明按 `(机型×adapter×技能)` 评估；缺 adapter 显式报错，不静默降级 |
| 足型/轮组拓扑未建模 | TRON1 PF/SF/WF、M20/Go2W/ZEX-W(16dof)、MicroDuck 双形态 | Morphology 内核增 `foot_type` / `wheel_indices` / 执行器类型（§2.1.1） |
| 参考动作许可与血缘 | LAFAN1/AMASS/ACCAD 与厂商数据许可不一 | Motion 资源强制 `license` + `retarget_chain`；未标注不入 `core` 注册表 |
| 动作数据体积 | npz/pkl 偏大（G1 单文件 >10 MB） | 数据本体只登记不复制（与 `00_resources/` 一致），按血缘回上游取 |

---

## 9. 与既有规划的关系

本方案是此前讨论（发展方向 A–E / 四主线方案）的**地基部分**：资源模型 + 证据链是「B 真机闭环主线」的第一阶段，同时为「A 任务族扩展」（AMP/mimic = 新 SkillSpec+Recipe）、「E 自研机型向导」（能力四档 + base/override）、远期「C 导航层 / D 平台化」（Scenario command_source / Pack 即 ls_plugin 分发单元）预留全部接口。地基完成后按「B 主线 + A 的 AMP/mimic 叠加」启动。

---

*本方案经多轮收敛定稿：LLoco 证明了源码层的 profile 抽象，1000frames 证明了平台层的四资源+契约关联，unitree_rl_mjlab 证明了共享工厂+占位覆写与部署契约，kaiwu_rl 证明了评测考卷与两文件产物契约，TRON1 证明了一份契约驱动多变体——本方案取五家之并集，落于本项目已有的 contract v3 + role_resolver + generic_task_builder + 双 MuJoCo 后端之上。*

*rev.2 优化再以 `00_resources/`（14 机型 × 8 类文件级证据）与三份盘点 / 28 章知识地图交叉校准：新增 Motion 一等资源（§2.1.1）、Morphology 执行器/足型内核字段、资源库映射（§2.5）、6 类 SkillSpec 目录与方法层落点（§3）、14 机型能力档位矩阵（§5.6）、参考项目扩至 12 家（§4）与 4 条新风险（§8）。*
