# RoboLab

> Isaac Gym-first legged-robot reinforcement learning, reproducible research and reusable Skills.

RoboLab 是一个面向足式机器人的强化学习训练、论文复现和能力复用项目。项目同时整合 **Isaac Gym** 与 **MJLab** 两套训练框架：先以 Isaac Gym 作为主线，是为了继承其简单、直接、层次清楚的工程特点，避免一开始陷入过于复杂的框架耦合；MJLab 则作为重要的现代化训练框架逐步接入。两套框架共享统一的机器人、任务、策略输入输出、评测和可视化契约，并把经过验证的机器人能力封装成可重复执行的 Workflow，再由 Agent Skill 提供使用说明。

MJLab 源码作为后端 bundle 管理在 `backends/mjlab/`，与 RoboLab 核心包保持边界。
这样可以固定经过验证的上游版本，同时避免把第三方框架的全部内部结构变成 RoboLab
的公共 API。

## 项目目标

RoboLab 优先解决三件事：

1. 让一个真实的足式机器人任务能够从配置直接完成训练、回放、评测和导出；
2. 将代表性的论文方法整理为可验证、可比较、可一键复现的 Method；
3. 为 Agent 提供可发现的仓库 Skill，并将实际执行交给可测试的 Workflow。

目标工作流如下：

```text
Robot + Task + Method + Recipe
              │
              ▼
       Isaac Gym / MJLab training
              │
       checkpoint / logs
              │
       shared Viser visualization
              │
              ▼
      cross-framework evaluation
              │
              ▼
       PolicyArtifact / Agent Skill
```

Isaac Gym 运行在独立的 Python 3.8
环境中，避免 legacy SDK 与 RoboLab（Python ≥3.10）发生依赖冲突：

```bash
PYTHONPATH=src conda run -n robolab-isaacgym python -m robolab.cli isaacgym list
PYTHONPATH=src conda run -n robolab-isaacgym python -m robolab.cli isaacgym smoke \
  --task a1 --num-envs 1 --device cuda:0
```

该命令通过 `Isaac Gym SDK → legged_gym → rsl_rl` 创建指定任务环境，执行 reset 和一次
零动作 step，并输出观测、动作、reward 和 done 的形状。

Isaac Gym 的 PPO 训练入口如下；根据需要调整迭代次数并指定运行目录：

```bash
PYTHONPATH=src conda run -n robolab-isaacgym python -m robolab.cli isaacgym train \
  --task a1 --num-envs 64 --device cuda:0 \
  --max-iterations 1 --run-dir artifacts/isaacgym-smoke
```

训练完成后可以从 checkpoint 恢复训练，或在隔离 worker 中运行 play：

```bash
PYTHONPATH=src conda run -n robolab-isaacgym python -m robolab.cli isaacgym train \
  --task a1 --num-envs 64 --max-iterations 100 \
  --resume-from logs/<run>/model_<iteration>.pt --run-dir logs/resume
PYTHONPATH=src conda run -n robolab-isaacgym python -m robolab.cli isaacgym play \
  --task a1 --checkpoint logs/<run>/model_<iteration>.pt --steps 256
```

P4 的 PPO-EE（Explicit State Estimator，论文 arXiv:2202.05481）通过显式 method 插件
运行，和默认 PPO 共用 CLI 但不修改默认 `rsl_rl`。正式复现产物位于
`logs/20260825-a1-ee-1024x1500/`：

```bash
PYTHONPATH=src conda run -n robolab-isaacgym python -m robolab.cli isaacgym evaluate \
  --task a1_ee --method ppo_ee --num-envs 64 --steps 1024 --device cuda:0 \
  --checkpoint logs/20260825-a1-ee-1024x1500/model_1500.pt
```

该独立评测同时输出速度跟踪误差和 estimator 的 MAE/MSE；它验证的是插件、训练、恢复、
评测和可视化链路可运行，不宣称论文级 SOTA 数值复现。

P6 已加入 DreamWaQ（arXiv:2210.17002）Isaac Gym A1 方法插件，参考
`/home/lxy/LeggedGym-Ex` 的 VAE、混合隐式/显式 latent、privileged critic 与辅助重建训练
结构。只有显式指定 `--method dreamwaq` 才会注册 `a1_dreamwaq`；默认 `ppo` 与 `ppo_ee`
路径不受影响。当前已通过 2 环境 GPU smoke、1 iteration 训练和 8 步独立 evaluate，属于
工程实现与链路验证，不宣称论文级数值复现。

同阶段加入 Teacher–Student privileged-information distillation（参考同一项目的
`ActorCriticTS`/`PPO_TS` 结构）。它也只有在 `--method teacher_student` 时注册对应 A1
任务；部署/回放使用 history encoder student，不会让 privileged teacher 输入泄漏到默认路径。

P6 正式 Method 验收标准已经固化：DreamWaQ 与 Teacher–Student 均使用 1024 个并行环境
训练 1500 iterations、seed 0；独立评测使用 1024 个并行环境和 1024 steps。DreamWaQ 与
Teacher–Student 的 Viser play 加载最终 `model_1500.pt`，并按 `plane → rough → stairs → obstacles`
顺序完成 terrain 切换；CTS 则使用下方的 plane/4-robot play。低于该配置的运行只作为
smoke/工程回归，不作为方法收敛评估。

CTS 的默认 Viser play 验收使用 `plane` 地形并同时打开 4 个机器人：

```bash
PYTHONPATH=src python -m robolab.cli isaacgym play \
  --task a1_cts --method cts \
  --checkpoint logs/20260826-a1-cts-corrected-1024x1500/model_1500.pt \
  --num-envs 4 --device cuda:0 --steps 0 --visualize
```

维度审计说明：此前的 DreamWaQ 长训练错误使用了 3 维 explicit target 和 48 维 critic，
Teacher–Student 又复用了该错误环境，因此此前两个 `1024x1500` checkpoint 均判定无效。
修正版 DreamWaQ 使用 actor `45 + 16 + 24 = 85`、history `225`、critic `240`；
Teacher–Student 使用 history `900`、teacher input `24`、latent `24`、critic `240`。
旧 checkpoint 不兼容 v2 架构，必须重新训练。

使用 MJLab 的网页端 Viser 持续查看 Isaac Gym 产生的 A1 状态（共享 `SceneFrame`，监听
`http://localhost:8080`）。下面是可直接运行的完整示例；其中 `--steps 0` 表示持续运行，
按 `Ctrl-C` 停止：

```bash
cd /home/lxy/RoboLab

conda run --no-capture-output -n robolab-isaacgym env \
  PYTHONPATH=/home/lxy/RoboLab/src \
  ROBO_MJLAB_PYTHON=/home/lxy/miniconda3/envs/robolab-mjlab16/bin/python \
  ROBO_ISAACGYM_PYTHON=/home/lxy/miniconda3/envs/robolab-isaacgym/bin/python \
  ROBO_ISAACGYM_SDK_PATH=/home/lxy/SDK/isaacgym/python \
  ROBO_LEGGED_GYM_PATH=/home/lxy/RoboLab/backends/isaacgym/legged_gym \
  ROBO_ISAACGYM_RSL_RL_PATH=/home/lxy/RoboLab/backends/isaacgym/rsl_rl \
  python -u -m robolab.cli isaacgym play \
  --task a1 \
  --checkpoint /home/lxy/RoboLab/logs/20260825-1024env_a1_isaacgym/model_1500.pt \
  --num-envs 1 \
  --device cuda:0 \
  --seed 0 \
  --steps 0 \
  --visualize
```

启动成功后终端应显示 `MJLab Viser bridge active at http://localhost:8080`，然后打开
`http://localhost:8080`。

打开网页后，可在 `Policy / Commands` 面板中切换 A1 checkpoint，使用速度范围滑块和
`vx`、`vy`、`vw` 滑块输入速度指令，查看 12 维 actor 网络输出，并选择 `plane`、
`rough`、`stairs` 或 `obstacles` 地形预览。地形预览切换不会重启正在运行的 Isaac Gym
仿真。

MJLab 检查命令为：

```bash
PYTHONPATH=src conda run -n robolab-mjlab16 \
  python -m robolab.cli mjlab list
PYTHONPATH=src conda run -n robolab-mjlab16 \
  python -m robolab.cli mjlab smoke \
  --task Mjlab-Velocity-Flat-Unitree-Go1 --device cuda:0
```

该命令创建指定 MJLab 任务，执行 reset 和一次零动作 step，并输出 actor/critic 观测、
动作、reward 和 termination 的形状。MJLab 的训练、回放和评测命令如下：

```bash
PYTHONPATH=src conda run -n robolab-mjlab16 python -m robolab.cli mjlab train \
  --task Mjlab-Velocity-Flat-Unitree-Go1 --num-envs 1024 --device cuda:0 \
  --max-iterations 1000 --run-dir logs/go1_mjlab
PYTHONPATH=src conda run -n robolab-mjlab16 python -m robolab.cli mjlab play \
  --task Mjlab-Velocity-Flat-Unitree-Go1 --checkpoint logs/<run>/model_<iteration>.pt
PYTHONPATH=src conda run -n robolab-mjlab16 python -m robolab.cli mjlab evaluate \
  --task Mjlab-Velocity-Flat-Unitree-Go1 --checkpoint logs/<run>/model_<iteration>.pt
```

统一 Workflow 的目标命令（当前规划接口，迁移完成前不视为已实现）：

```bash
robolab train <recipe> --framework isaacgym
robolab train <recipe> --framework mjlab
robolab play <checkpoint> --framework mjlab
robolab evaluate <checkpoint> --framework mjlab
robolab export <checkpoint>
robolab reproduce <method> --robot <robot> --task <task>
robolab workflow run <workflow>
```

P5 明确区分两个概念：Agent Skill 是仓库内的 `SKILL.md` 操作说明；Workflow 是实际执行
Python。四个 Agent Skill 位于 `skills/`，根级 `AGENTS.md` 负责按请求路由；可执行实现位于
`src/robolab/workflows/`。正式入口只有 `robolab workflow list/run`；Agent Skill 本身不
提供 Python 包或第二套执行入口。

Workflow 目标示例：

```bash
PYTHONPATH=src python -m robolab.cli workflow list
PYTHONPATH=src python -m robolab.cli workflow run train \
  --framework isaacgym --task a1_ee --method ppo_ee \
  --num-envs 2 --device cuda:0 --max-iterations 1
PYTHONPATH=src python -m robolab.cli workflow run evaluate \
  --framework isaacgym --task a1_ee --method ppo_ee \
  --checkpoint logs/<run>/model_1.pt --num-envs 64 --steps 512
PYTHONPATH=src python -m robolab.cli workflow run export \
  --checkpoint logs/<run>/model_1.pt
```

`export` 当前生成可追溯的 `policy_artifact.json` manifest；实际 ONNX/TorchScript 部署导出
留到 P8，不在 Agent Skill 或 Workflow 层伪造部署能力；P7 将先实现 WebUI。

## 训练框架策略

### Isaac Gym + legged_gym：第一主线

Isaac Gym 本身是 GPU 物理仿真 SDK 和 Python API，不是完整的 locomotion 训练业务。
足式机器人训练通常由 `legged_gym` 负责环境、任务、奖励和训练入口，再由
`rsl_rl` 提供 PPO。因此 RoboLab 的第一条可运行主线明确采用：

```text
Isaac Gym SDK → legged_gym environment/task → rsl_rl PPO → RoboLab adapter
```

它负责优先建立可控、可调试、可复现的训练闭环：

- GPU 并行环境和高吞吐采样；
- PPO 及论文方法训练；
- terrain、传感器和训练期 domain randomization；
- checkpoint、训练日志和性能指标生成。

选择这条路线的首要原因不是功能最多，而是 Isaac Gym/legged_gym 的环境、任务、
算法和 runner 入口已经被大量足式机器人工作验证，适合先跑通真实训练业务。
RoboLab 会把 `legged_gym` 当作 Isaac Gym 后端的兼容实现和参考基线，不把它的
全局配置、import 时切换模拟器和内部对象直接提升为 RoboLab 核心 API。第一条
Robot、Task、Method、Run、Workflow 和 Agent Skill 边界由真实训练链路驱动，避免建立脱离业务的大型抽象。
Isaac Gym 已被 NVIDIA 标记为 legacy software，因此必须固定可复现的 Python、
CUDA、PyTorch 和 Isaac Gym 运行环境，不依赖它继续发布新版本。

### MJLab：第二训练框架与现代化路线

MJLab 不是只负责回放的附属适配器，而是第二套一等训练框架。它提供 ManagerBased
环境、Task Registry、MDP、RSL-RL wrapper/runner、train/play/evaluate 和自身任务配置。
RoboLab 在同一 Robot/Task/Method 契约下接入其完整训练、回放和评测生命周期。

接入 MJLab 时会主动规避其当前任务、Manager、配置和执行入口容易交织的复杂性：保留值得使用的现代能力，但不把 RoboLab 核心业务建立在 MJLab 的内部对象和目录组织之上。

MJLab 的优先职责包括：

- 加载相同机器人和策略；
- 对齐 joint order、control frequency、observation 和 action；
- 完成自己的 play、训练和独立 evaluate；
- 暴露不同物理引擎下的策略退化和模型差异；
- 为两套训练框架提供现代化的 Viser 可视化能力。

Isaac Gym 与 MJLab 的依赖环境可以彼此隔离。二者通过固定配置、checkpoint、策略输入输出、评测结果和事件数据衔接，不强求在同一 Python 进程中运行。

### 共享 Viser 可视化层

Viser 不属于某一个训练框架的私有实现。RoboLab 会把它设计为共享的可视化层：Isaac Gym 和 MJLab 各自负责产生规范化状态、观测、动作、奖励和训练指标，再由共同的 Viser 适配层提供机器人场景、训练曲线、命令、接触和回放展示。

共享的是可视化协议和上层组件，不是强行共享两个物理引擎的内部对象。这样可以保留 MJLab 更现代的交互体验，同时不把 Isaac Gym 的训练核心改造成 MJLab 的内部结构。

当前不考虑 Isaac Lab 和 Genesis 后端。RoboLab 不为未进入计划的框架预先建立实现或复杂兼容层。

## 核心对象

- **Robot**：模型、关节顺序、执行器、控制参数、传感器和默认状态；
- **Task**：command、observation、action、reward、termination 和 curriculum；
- **Method**：网络、runner、algorithm、storage、loss、checkpoint 和 export 逻辑；
- **Recipe**：一次可重放训练所需的 Robot、Task、Method、seed、资源和覆盖参数；
- **Run**：真实执行产生的 resolved config、日志、checkpoint、指标和环境信息；
- **TrainingFramework**：Isaac Gym 或 MJLab 的训练执行、环境能力和依赖边界；
- **Workflow**：可测试的 Python 执行层，负责参数校验、调用后端 runtime、记录产物和返回结构化结果；
- **Agent Skill**：包含 `SKILL.md` 的仓库能力说明，告诉 Agent 何时使用 Workflow、如何检查环境、如何解释输出和处理失败；
- **PolicyArtifact**：固定策略文件及其 observation/action/control/lineage 信息。

这些对象只在真实业务需要时实现，不先建立脱离训练流程的大型 schema 系统。

## 论文方法与一键复现

论文复现是 RoboLab 的核心能力，不是示例代码集合。Method 应当与具体机器人尽量分离，并明确声明其所需的 observation、privileged information、motion data、network、runner 和评测方式。

首批候选方法包括：

- PPO locomotion baseline；
- Periodic Gait Reward / Walk These Ways；
- Teacher–Student；
- Explicit Estimator；
- DreamWaQ；
- Constraints as Terminations；
- DeepMimic；
- Adversarial Motion Priors。

每次 `reproduce` 必须生成可定位的 resolved config、源码版本、依赖环境、seed、checkpoint、训练曲线和评测报告。能够启动脚本但不能复现结果，不算完成。

## Agent Skill 与 Workflow

Agent Skill 是 RoboLab 相对普通训练仓库的主要差异化入口。它不是训练代码，也不是 Python
插件，而是面向 Agent 的仓库操作手册。实际执行由 `src/robolab/workflows/` 提供；不建设
marketplace、WebUI 或远程执行平台。

推荐结构：

```text
skills/
├── train/SKILL.md
├── reproduce/SKILL.md
├── evaluate/SKILL.md
└── export/SKILL.md
```

每个 `SKILL.md` 至少说明：触发条件、前置检查、推荐 Workflow/CLI、参数选择、产物位置、
失败诊断和禁止事项。调用关系固定为：

```text
Agent → skills/<name>/SKILL.md → Workflow/CLI → Isaac Gym/MJLab runtime
```

典型 Agent Skill 包括：

- 新机器人模型检查与接入；
- velocity locomotion 训练；
- 指定论文的一键复现；
- checkpoint 的 MJLab sim-to-sim；
- 独立批量评测；
- JIT/ONNX 策略导出。

Agent Skill 必须调用同一套 Workflow 和核心训练/评测实现，不能复制另一套业务逻辑。

## 参考项目：LeggedGym-Ex

本地参考仓库位于 `/home/lxy/LeggedGym-Ex`，当前基于提交 `f313dca`。它已经实现 Isaac Gym、Genesis 和 Isaac Lab 多后端、真实 RSL-RL 训练入口，以及多个论文方法，对 RoboLab 有较高参考价值。

RoboLab 主要借鉴：

- 训练优先的任务组织方式；
- Robot/Task 注册和 RSL-RL runner 闭环；
- 多种 locomotion、模仿学习和 sim-to-real 方法；
- 多后端任务 smoke test；
- joint order、domain randomization、策略导出等实践。

RoboLab 不直接继承以下设计：

- import 阶段使用全局变量选择模拟器；
- 包含大量职责的巨型 Simulator 基类；
- 全局可变配置实例；
- 机器人、论文方法和 runner 的多层复制；
- 通过任务名字符串拆分推断 Method，或使用 `eval()` 解析 policy/algorithm 类；
- 不同论文方法返回不同长度 tuple，迫使 play/train 写大量 `if/elif`；
- Viser 直接读取 `env.simulator` 私有状态，或在可视化层重复实现完整仿真逻辑；
- 未经授权核对直接复制机器人模型、mesh 或动作数据。

## 从 LeggedGym-Ex 吸收的设计

经过对本地代码的进一步对照，下面这些模式会进入 RoboLab 的设计，但以更严格的边界重新实现：

- **Task Registry**：一个任务名必须能找到 Robot、Task 和训练配置，并能统一创建环境；注册项需要重复检查、可列出和可定位版本；
- **Method/Runner Registry**：论文方法通过独立的 runner、algorithm、policy 和 storage 注册表装配，不能在每个机器人目录复制一份算法；
- **可复用 Robot 基础配置**：平地/崎岖地形、控制周期、默认姿态、joint order、PD 参数和随机化可以组合复用，但 RoboLab 使用不可变的 resolved 配置，避免全局配置实例被训练和 play 修改；
- **清晰的训练生命周期**：环境创建、策略/算法创建、rollout storage、`learn()`、日志、checkpoint、resume 和最终保存是明确的步骤，训练入口必须真正走完这条生命周期；
- **方法专用导出器**：普通 PPO、Teacher–Student、Estimator、AMP 等方法可以有不同的输入签名和导出逻辑，导出器必须声明输入输出，而不是假设所有策略只有一个 observation tensor；
- **参考运动数据管线**：AMP/DeepMimic 类方法需要统一的动作文件格式、时间采样、插值、批量预加载和来源信息；
- **隔离式训练 smoke test**：Isaac Gym 的 PhysX/图形资源可能要求任务在独立进程运行，因此批量 smoke test 使用子进程、超时、逐任务结果和最终汇总；
- **Viser 的独立适配层**：LeggedGym-Ex 中的 MJCF 运动学解析、mesh 缓存、terrain 显示、命令滑块和状态更新很有价值。RoboLab 会将它提炼为框架无关的 `VisualizerAdapter`，供 Isaac Gym 与 MJLab 共同使用。

这些模式的共同要求是：吸收行为和接口语义，不直接复制大段实现；每一项都必须由至少一条真实训练或评测链路证明价值。

RoboLab 会用显式注册的类引用替代 `eval()` 和任务名推断；用统一的 `StepBatch` 承载 observation、privileged observation、history、motion feature、reward、done 和 metrics；用 `SceneFrame`/`TrainingFrame` 向 Viser 提供数据。这样可以保留 LeggedGym-Ex 的扩展能力，而不继承其条件分支和内部状态耦合。

## 开发原则

1. 训练是真实主业务，CLI 必须最终调用 Isaac Gym 或 MJLab 的真实训练循环；
2. 先完成一条纵向闭环，再扩展算法、机器人和 Agent Skill；
3. Isaac Gym 先建立简单清晰的主线，MJLab 作为第二训练框架接入；不追求两套框架内部实现相同，只要求公共契约和结果可比较；
4. Robot、Task、Method、Workflow 和 Agent Skill 分离，但不为抽象而抽象；
5. observation/action 顺序、单位、scale 和控制频率必须固定；
6. 论文复现必须包含训练和独立评测证据；
7. 训练框架基线按后端 bundle 纳入版本控制；保留来源、许可证和显式补丁；
8. 不在训练闭环稳定前开发 WebUI、远程 Worker 和复杂平台控制面；
9. 项目状态只在 [PROGRESS.md](PROGRESS.md) 更新，不再维护多套计划文档。

## 目标仓库结构

```text
RoboLab/
├── README.md
├── PROGRESS.md
├── pyproject.toml
├── src/robolab/
│   ├── core/                         # contracts / registry / recipe / run / artifact
│   ├── robots/
│   │   └── unitree_a1/
│   │       ├── spec.py
│   │       ├── configs.py
│   │       └── bindings/
│   │           ├── isaacgym.py
│   │           └── mjlab.py
│   ├── tasks/velocity/               # spec / observations / rewards / terminations
│   ├── methods/
│   │   ├── registry.py
│   │   ├── ppo/
│   │   └── papers/
│   ├── frameworks/
│   │   ├── isaacgym/                 # runtime / worker / adapter
│   │   └── mjlab/                    # runtime / adapter
│   ├── training/
│   ├── evaluation/
│   ├── deployment/
│   ├── visualization/viser/
│   └── workflows/                   # Python 执行层：调用 runtime，不是 Agent 提示词
├── skills/                           # Agent-facing SKILL.md，不放训练实现
│   ├── train/SKILL.md
│   ├── reproduce/SKILL.md
│   ├── evaluate/SKILL.md
│   └── export/SKILL.md
├── configs/
│   ├── robots/
│   ├── tasks/
│   ├── methods/
│   ├── recipes/
│   └── deployment/
├── resources/
│   ├── robots/
│   │   ├── unitree_a1/
│   │   ├── anymal_b/
│   │   ├── anymal_c/
│   │   └── cassie/                    # 唯一规范 URDF / meshes / LICENSE / NOTICE
│   └── actuator_nets/                 # 机器人配置显式引用的执行器网络
├── backends/
│   ├── isaacgym/                      # legged_gym + rsl_rl 1.0.2 bundle
│   │   ├── legged_gym/
│   │   ├── rsl_rl/
│   │   ├── backend.toml
│   │   └── patches/
│   └── mjlab/                         # MJLab + rsl-rl-lib 5.4.2 bundle
│       ├── mjlab/
│       ├── rsl_rl/
│       └── backend.toml
├── third_party/                      # only additional approved snapshots/notices
├── vendor-lock/                      # source / revision / license / patch metadata
└── tests/
```

这是 RoboLab 的参考目录结构。所有自有代码都属于 `robolab`；后端边界为
`robolab.frameworks.isaacgym` 与
`robolab.frameworks.mjlab`，不另设 `robolab_isaacgym` 顶层包。上游框架源码保留在本地
后端训练源码位于 `backends/` 并受 Git 追踪；RoboLab 只在 `vendor-lock/` 记录来源、版本、许可证和补丁。

## 许可证与第三方代码

RoboLab 自身的许可证尚未确定。在许可证确定前，不应把当前仓库当作已经获得某种开源授权的发布物。

LeggedGym-Ex 根目录采用 BSD 3-Clause License。该许可证允许使用、修改、再分发和商业使用，也允许闭源分发，但复制其代码时必须保留原版权声明、许可证条件和免责声明；二进制分发时需要在随附文档或材料中重现这些内容；不得使用原作者或贡献者的名字为衍生产品背书。

LeggedGym-Ex 同时包含或引用 NVIDIA、ETH Zurich、机器人厂商、动作数据和其他论文实现。根目录 BSD-3-Clause 不会自动替这些第三方资产授予权利。任何进入 RoboLab 的上游代码、机器人模型、mesh、动作数据和预训练权重都必须单独记录来源并核对其许可证或使用条款。Isaac Gym 本身还受 NVIDIA 的独立许可协议约束，不能仅凭 LeggedGym-Ex 的 BSD 许可证重新分发 Isaac Gym。

### 本地 Isaac Gym/legged_gym 材料

Isaac Gym SDK + legged_gym 工作区至少包含：

- Isaac Gym Python 包和对应的 CUDA/PyTorch 版本；
- A1 的资产、关节顺序、默认姿态、PD/力矩参数和 terrain 配置；
- 已调通的 PPO 训练入口、checkpoint/resume 和 play 脚本；
- 该工作区的来源、提交版本及 NVIDIA Isaac Gym 许可文件。

Isaac Gym SDK 应在独立环境中本地安装，不提交到 RoboLab。legged_gym 基线必须
来自明确授权的公共上游，或来自你专门提供给 RoboLab 使用的独立副本；私人仓库、
私人配置、资产、权重和训练结果不作为参考来源。不要把 NVIDIA SDK、预训练权重
或未经审查的机器人资产提交到 RoboLab 主分支。
