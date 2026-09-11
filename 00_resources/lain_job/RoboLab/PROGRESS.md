# RoboLab Progress

状态日期：2026-08-27

本文是 RoboLab 的单一进度与阶段记录。当前状态和验收证据放在前面；历史变更只保留阶段级摘要，避免重复记录同一事实。

## 当前状态

- 当前阶段：`P7 WebUI 实现（进行中）`
- 仓库已以新的根提交重新开始；旧项目保存在 `robolab-old` 分支。
- 第一训练主线：Isaac Gym SDK + legged_gym + 隔离的 legacy rsl_rl。
- 第二训练后端：MJLab + 隔离的 modern rsl_rl。
- 共享可视化：Viser，通过框架无关的 `SceneFrame`/`TrainingFrame` 协议连接两个后端。
- P0–P5 已完成；P6 正在扩展论文方法和机器人目录。
- 当前方法注册表实际包含 5 个方法：`ppo`、`ppo_ee`、`dreamwaq`、`teacher_student`、`cts`；CTS 已进入代码与训练产物，但尚未完成正式方法验收。
- 当前仓库验证：`PYTHONPATH=src pytest -q` 为 **33 passed, 1 skipped, 1 failed**。唯一失败是 `tests/test_methods.py` 仍断言旧的四方法列表，未纳入已注册的 `cts`；这属于测试基线回归，不能记作全绿。
- 暂不支持：Isaac Lab、Genesis、远程训练平台和实机控制；WebUI 列为 P7，尚未实现。
- 主要参考实现：`/home/lxy/LeggedGym-Ex`，提交 `f313dca`。

## 架构与边界

```text
Recipe (Robot + Task + Method + Framework)
                    │
                    ▼
RoboLab core (registry / config / artifact / evaluation contracts)
              ┌─────┴─────┐
              ▼           ▼
       Isaac Gym       MJLab
       adapter         adapter
              └─────┬─────┘
                    ▼
       run: config / checkpoint / metrics / artifact
```

- `src/robolab/core/` 只放框架无关契约；后端私有 simulator、tensor 和环境对象不得成为公共 API。
- `src/robolab/frameworks/<framework>/` 是后端依赖与训练生命周期边界；适配器提供 `validate`、`smoke`、`train`、`play`、`evaluate` 等动作，不建立统一的物理仿真器 ABC；两个后端在独立环境中运行。
- Robot/Task 描述跨框架语义（joint order、控制周期、观测/动作签名），后端差异放在 binding 中。
- Method 与 Robot/Task 解耦；方法网络、runner、storage、导出器和输入签名独立注册。
- 方法扩展置于各自隔离目录；不得修改默认 PPO 路径或公共 `rsl_rl` 行为。
- 机器人资源唯一存放于 `resources/robots/<robot>/`；地形存放于 `resources/terrains/`；后端不维护重复资产。
- Isaac Gym SDK 位于 `/home/lxy/SDK/isaacgym/python`，通过 `ROBO_ISAACGYM_SDK_PATH` 接入，不纳入仓库。
- 训练源码 bundle 受 RoboLab 管理：`backends/isaacgym/` 与 `backends/mjlab/`，来源、许可证和补丁写入相应 metadata；不使用 Git submodule。
- Isaac Gym bundle 使用 legacy `rsl_rl 1.0.2`，MJLab bundle 使用 modern `rsl-rl-lib 5.4.2`；两者不能共享同一 `PYTHONPATH`。
- `vendor-lock/` 已记录来源、许可证和补丁，但上游 revision 尚未全部核验，因此当前不宣称可复现锁定基线。
- 配置采用 Python dataclass 表达结构、默认值和校验，YAML 只承载 Recipe 覆盖；不把可变配置隐式写回后端源码。
- 跨框架衔接依靠 `PolicyArtifact`、resolved config 和独立评测结果；不要求同一环境对象跨后端运行。
- 训练、复现和独立评测必须通过 `robolab workflow`；Agent 操作规则见 `AGENTS.md` 与 `skills/*/SKILL.md`。
- 运行产物写入 `logs/`，记录 resolved config、依赖/源码版本、seed、指标和 checkpoint；不提交 Git。

## 资源现状

`resources/robots/` 已包含并带来源 `NOTICE.md`：

- Unitree A1（Isaac Gym/MJLab 已接入）
- ANYmal B、ANYmal C、Cassie
- Unitree Go2（保留默认 `go2.urdf`/`go2.xml`）
- Unitree G1（保留 `g1_12dof`、`g1_23dof`、`g1_29dof` URDF/XML）
- Booster K1（保留 `K1_22dof`）
- LimX TRON1PF、LimX TRON1SF（各保留默认模型）
- Bipedal Walker（保留 `walker3d_hip3d.urdf`）

新迁移机器人目前只有规范资源，尚未全部建立 RoboLab binding、任务和训练配置。G1 12/23/29 的 mesh 引用已核对完整；被精简的变体仍在本机临时备份中。

## 阶段表

| 阶段 | 状态 | 交付与完成标准 |
|---|---|---|
| P0 项目基线与技术验证 | ✅ | 核心契约、来源/许可证记录、Isaac Gym/MJLab import、模型加载和 GPU step smoke |
| P1 Isaac Gym PPO 纵向闭环 | ✅ | A1 真实 velocity PPO、checkpoint resume/play、有效 locomotion |
| P2 MJLab 训练框架接入 | ✅ | Go1 原生 train/play/evaluate；A1 MJCF、joint/obs/action/control 对齐 |
| P3 共用 Viser | ✅ | 两后端输出规范化状态并由网页端 Viser 展示、交互和地形切换 |
| P4 Method 插件与首个论文复现 | ✅ | PPO-EE 隔离插件完成训练、评测与 Viser 链路；不宣称论文级 SOTA |
| P5 Agent Skill 与 Workflow | ✅ | `skills/*/SKILL.md` + `robolab workflow list/run`；覆盖 train/reproduce/evaluate/export，checkpoint export 已验证；不复制后端业务 |
| P6 方法与机器人扩展 | ✅ | 五个 Method 已注册；机器人资源目录、双后端和共享 Viser 链路作为 P7 输入基线 |
| P7 WebUI 实现 | 🔄 | 已实现 URDF/MJCF 几何解析、collision/visual 数据、关节映射、控制与电机参数、ZIP 安全上传、派生机器人包、Recipe/RobotProfile 持久化、训练前兼容性检查、训练日志和 TensorBoard/Viser 进程入口；真实 mesh 3D 渲染和完整 Viser 参数启动待完成 |
| P8 发布与部署准备 | ⬜ | PolicyArtifact manifest、导出和部署输入契约 |

## P6 验收矩阵

| 工作项 | 状态 | 证据与结论 |
|---|---|---|
| DreamWaQ（Isaac Gym A1） | ✅ 工程移植完成 | `logs/long1024_dreamwaq_v5_contact_order_1500/model_1500.pt`；1024 env × 1500 iter；独立评测 1024 env × 256 steps：mean reward `0.0192431`、forward tracking error `0.1483 m/s`、done `3`。修复了 17 维 contact label 顺序（`thigh→calf→foot→base→hip`）。这是 A1 工程移植，不是 LeggedGym-Ex Go2 rough-terrain 的严格论文复现 |
| Teacher–Student（Isaac Gym A1） | ⚠️ 工程链路可运行，待固定指令对照验收 | 当前主证据为 `logs/long1024_teacher_student_v3/model_1500.pt`；1024 env × 1500 iter；独立评测 1024 env × 1024 steps：mean reward `0.0209128`、forward tracking error `0.121685 m/s`、done `1070`。v3 已明显优于历史 v1/v2（`0.5513/0.6026 m/s`），但评测指令均值接近零，尚未完成非零固定指令下的 Teacher-vs-Student 对照；因此暂不标记正式完成 |
| Teacher–Student 当前剩余问题 | 🔄 | 需要补充固定指令档位（至少 `±0.25/±0.5/±1.0 m/s`）的 teacher 与 student 独立评测，并记录 teacher/student tracking error、动作差和 latent 蒸馏误差；同时确认 A1 的 17 维 contact label 顺序与观测字段语义 |
| CTS（Isaac Gym A1） | ⚠️ 修正后工程训练通过，待固定非零指令验收 | 新 checkpoint [`logs/20260826-a1-cts-corrected-1024x1500/model_1500.pt`](logs/20260826-a1-cts-corrected-1024x1500/model_1500.pt)；1024 env × 1500 iter。独立 student evaluate（1024 env × 1024 steps）记录于 [`evaluation_1024env_1024steps.json`](logs/20260826-a1-cts-corrected-1024x1500/evaluation_1024env_1024steps.json)：mean reward `0.0179199`、forward tracking error `0.146777 m/s`、done `1051`。注意 legged_gym 会将 reward scale 乘 `dt=0.02`，所以 `0.0163` 即时训练 reward 对应约 `0.82` 的未缩放综合奖励，并非接近零；但当前仍是 A1 plane 工程 recipe，需固定非零指令 teacher/student 对照后再宣称收敛 |
| CTS checkpoint sweep / Viser smoke | ✅ 已完成回归证据 | [`checkpoint_sweep_256env_512steps.json`](logs/20260826-a1-cts-corrected-1024x1500/checkpoint_sweep_256env_512steps.json) 显示 300/600/900/1200/1500 轮 tracking error `0.4845/0.4261/0.3078/0.2725/0.1421 m/s`；最终 checkpoint 的 32-step Viser play smoke 通过，zero-command error `0.06685 m/s`、done `0`。这证明训练趋势和回放链路有效，但不替代固定非零指令验收。 |
| CTS 当前剩余问题 | 🔄 | 严格对照 `/home/lxy/LeggedGym-Ex` 后确认此前 1500 轮 checkpoint 建立在三项错误语义上：actor 观测顺序曾为 `gravity→ang_vel→commands`（上游是 `commands→gravity→ang_vel`）；17 维 contact label 曾直接使用 Isaac Gym 原生刚体顺序（上游固定为 `thigh→calf→foot→base→hip`）；99-D teacher 的 36 维地形输入曾误用 foot clearance 且 normal 符号相反（上游是每足 9 点原始高度 + `(dx,dy,-1)` normal）。三项现已修正；同时将 A1 配置的 `num_privileged_obs` 明确为上游独立的 99-D teacher encoder 输入，critic 仍为 5×96=480-D。4 env × 1 iter contract smoke 已通过。旧 `model_1500.pt` 不可用于验证修复；需从头重训，再做 teacher/student 对照。当前 A1 仍是 plane/无 81-D measured-height 的工程 recipe，不是 Go2 rough-terrain 严格复现；若要严格复现需另建 rough CTS 配置。 |
| Method 正式验收标准 | ✅ 标准已固化 | 训练基准为 1024 env × 1500 iter，独立评测默认 1024 env × 1024 steps；CTS 最终 checkpoint 的默认 Viser play 使用 `plane` 地形并同时打开 4 个机器人（`--num-envs 4`）。heightfield 上传问题已修复。DreamWaQ v5 的已记录独立评测为 1024 env × 256 steps，详见上行 |

## 已完成的纵向链路

CTS 最终 checkpoint 的默认 Viser 验收是在 `plane` 地形同时打开 4 个机器人：

```bash
PYTHONPATH=src python -m robolab.cli isaacgym play --task a1_cts --method cts --checkpoint logs/20260826-a1-cts-corrected-1024x1500/model_1500.pt --num-envs 4 --device cuda:0 --steps 0 --visualize
```

```text
合法机器人资源
  → 后端 load/reset/step
  → 观测/动作/奖励/终止契约
  → 真实 PPO 训练
  → checkpoint resume/play
  → 独立 evaluate
  → SceneFrame/TrainingFrame
  → 共用 Viser 回放与交互
```

P1 A1 PPO 最终证据：`logs/20260825-1024env_a1_isaacgym/model_1500.pt`，1024 env、seed 0、1500 iter；512 步 play 的前向速度绝对跟踪误差 `0.0833 m/s`。

P2 Go1 最终证据：`logs/20260825-go1-flat-mjlab-1000/model_999.pt`，1024 env、1000 iter；独立 evaluate 误差 `0.1433 m/s`。A1 MJCF binding 的 actor obs `[45]`、action `[12]`、control dt `0.02s` 已对齐。

P4 PPO-EE 最终证据：`logs/20260825-a1-ee-1024x1500/model_1500.pt`；1024 env、1500 iter；独立评测 tracking error `0.1046 m/s`，estimator MAE/MSE `0.0691/0.0182`。该结果证明插件链路可运行，不代表论文级数值复现。

## 变更记录（阶段摘要）

| 日期 | 摘要 |
|---|---|
| 2026-08-24 | 建立 RoboLab 核心契约、双后端隔离架构、来源/许可证记录和资源唯一归属；完成 Isaac Gym A1、MJLab Go1 的 GPU load/reset/step smoke，接通 A1 PPO 初始训练链。 |
| 2026-08-25 | 完成 A1 PPO 1024×1500 训练和有效 tracking；完成 MJLab Go1/A1 闭环；建立双后端 `SceneFrame`/`TrainingFrame` 与 Viser bridge，支持回放、指标面板、交互命令和地形切换。 |
| 2026-08-25 | 完成 PPO-EE 隔离 Method 插件、CLI/workflow 接入、1024×1500 训练、独立评测和 Viser 验证；完成 `skills/*/SKILL.md` 与 `src/robolab/workflows/`，固定 Agent → Skill → Workflow → backend runtime 调用关系。 |
| 2026-08-26 | 完成 DreamWaQ A1 v5 contact label 顺序修复、1024×1500 训练和独立评测；确认其为 A1 工程移植而非 Go2 rough-terrain 严格复现。 |
| 2026-08-26 | 从 LeggedGym-Ex 迁移 Go2、G1、K1、TRON1PF、TRON1SF 和 Bipedal Walker 公开资源，补充来源 NOTICE，并精简为默认模型；G1 保留 12/23/29 三个常用版本。 |
| 2026-08-26 | Teacher–Student v3 完成 1024×1500 训练；独立评测 tracking error `0.121685 m/s`，确认此前 v1/v2 的 `0.5513/0.6026 m/s` 为历史退化结果；当前转入固定非零指令的 Teacher-vs-Student 对照验收。 |
| 2026-08-26 | 接入 CTS A1 工程迁移：独立 plugin、policy、PPO、teacher/student 分组 storage、runner 与任务已完成；4 env × 1 iter 训练 smoke 和 16-step 独立 student evaluate 均通过，尚未进行正式收敛训练。 |
| 2026-08-26 | CTS A1 完成 1024×1500 正式训练和 1024 env × 1024 steps 独立 student evaluate；tracking error `0.491534 m/s`，训练链路完整但未通过收敛验收。 |
| 2026-08-26 | CTS 严格对照 LeggedGym-Ex：修正 actor observation 顺序、contact-state 语义索引和 `num_privileged_obs` contract；新增 4 env × 1 iter 训练 smoke，形状/更新链路通过。此前 checkpoint 因输入语义错误作废，待重新收敛训练。 |
| 2026-08-26 | CTS teacher terrain contract 再次对齐上游：改为每足 9 点原始 heightfield 高度与 `(dx,dy,-1)` 法向，移除错误的 foot-clearance/反向 normal；新增 geometry smoke 通过。 |
| 2026-08-26 | CTS 修正后重新完成 1024×1500 训练；独立 1024 env × 1024 steps evaluate：tracking error `0.146777 m/s`、mean reward `0.0179199`、done `1051`。旧错误语义结果 `0.491534 m/s` 不再作为当前基准。 |
| 2026-08-27 | CTS corrected checkpoint sweep（256 env × 512 steps）显示误差持续下降：300/600/900/1200/1500 轮分别为 `0.4845/0.4261/0.3078/0.2725/0.1421 m/s`；32-step Viser play smoke 通过，zero-command 下误差 `0.06685 m/s`、done `0`。当前训练不是完全未收敛；仍需固定非零指令验收。 |
| 2026-08-27 | 主分支方法注册表新增 `cts` 后，现有 `tests/test_methods.py` 仍期待旧四方法列表；全量 pytest 结果为 33 passed、1 skipped、1 failed。需同步测试断言后才能恢复全绿。 |

## 更新规则

1. 同一时间只允许一个阶段处于“进行中”。
2. 工作项只有在实现、测试和可定位证据齐全后才能标记完成。
3. 真实训练、GPU smoke、play 和独立评测分别记录，不能互相替代。
4. 论文复现不得用随机策略、零动作或仅能加载的 checkpoint 代替。
5. 新需求先归入阶段，再更新当前状态、验收矩阵和阶段摘要；不再追加重复的逐命令流水。
