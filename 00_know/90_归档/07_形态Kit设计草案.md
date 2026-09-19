# 形态 Kit 设计草案（待决策）

> **这份文档的地位**：它是**待你拍板的方案**，不是架构定稿。
> 架构层（统一什么 / 不统一什么）在 [`06_统一架构方案.md`](./06_统一架构方案.md) §2；状态在 [`05_任务清单.md`](./05_任务清单.md)。
> 你决策后：**结论并入 `06` §2.1**，**执行项进 `05` P 组**，本文件随后删除或归档（避免第二份真相）。
>
> 起草时间 2026-09-19；所有数字都是当轮实测（命令写在表下）。

---

## 0. 一页结论

1. **Kit 不是从零设计的东西 —— 它已经在跑。** `adapters/mjlab/velocity_task_kit/` 就是形态 Kit 的雏形，**5 个包已在用**（lite3 / m20 / b2 / b2w / go2w），而且它的 docstring 里写着本草案要立的那条原则：
   > "把跨包逐字重复的框架层上移为唯一真值；包内只留任务特有部分（奖励表 / 传感器 / 终止 / 常量）与入口 stub。"
2. **所以本草案做的是三件事**：**命名升格**（`velocity_task_kit` → 形态 Kit）、**范围界定**（谁归哪个形态、谁不迁）、**迁移顺序**（轻 → 重，每步可回滚）。
3. **不要迁的名单同样重要**：冻结 5 包（`tron1_pf/sf/wf` + `microduck` + `wuji_hand`，共 151 py）与人形 `g1`（86 py，`06` §2.1 已判"Kit 暂不建"）。
4. **最重的是 go2（178 py 在 `source/local_tasks/`）**，它必须**先做一次只读审计再动**，不能作为第一批。
5. **三件待你拍板的事在 §9**（落点位置 / 迁移顺序 / go2 的处置方式）。

---

## 1. 现状取证（2026-09-19 实测）

### 1.1 迁移面清单（14 包）

| 包 | 形态 | 包内 py | 已用 `velocity_task_kit` | 建议归属 | 备注 |
|---|---|:---:|:---:|---|---|
| `unitree_go2` | 四足 | **182** | 否 | 四足 Kit | **178 在 `source/local_tasks/`**；另 runner/config/catalog/`__init__` 各 1 |
| `unitree_go1` | 四足 | 3 | 否 | 四足 Kit | 与 b2 同构，**最小迁移样本** |
| `unitree_b2` | 四足 | 3 | **是** | 四足 Kit | 试点包之一 |
| `deeprobotics_lite3` | 四足 | 4 | **是** | 四足 Kit | 试点包（与 b2 逐字重复的那份是 Kit 的起源） |
| `unitree_go2w` | 轮足 | 7 | **是** | 轮足 Kit | 第二批三包组 |
| `unitree_b2w` | 轮足 | 7 | **是** | 轮足 Kit | 第二批三包组 |
| `deeprobotics_m20` | 轮足 | 18 | **是** | 轮足 Kit | 包内多 2 行 `m20_rewards` 属任务 wiring（**留包**） |
| `zex-w` | 轮足 | 21 | 否 | 轮足 Kit | 结构不同（`source/{mjcf,robot}/`，上游 `rc_mjlab` 直搬）——**单独一轮** |
| `unitree_g1` | 人形 | 86 | 否 | **暂不归** | `06` §2.1：人形 Kit 暂不建 |
| `microduck` | 轮足 | 37 | 否 | **冻结** | `05` P 组冻结指令 |
| `wuji_hand` | 人形 | 105 | 否 | **冻结** | 同上（且是人形） |
| `limx_tron1_pf` | 四足 | 3 | 否 | **冻结** | 同上 |
| `limx_tron1_sf` | 四足 | 3 | 否 | **冻结** | 同上 |
| `limx_tron1_wf` | 轮足 | 3 | 否 | **冻结** | 同上 |
| **合计** | | **482** | **5 / 14** | | 冻结 151 + 人形 191 不参与 |

```bash
# 复现：包内 py 数 / 是否引用 Kit / 冻结名单见 05 P 组头
find assets/robots/<id>/training -name '*.py' | wc -l
grep -rl velocity_task_kit assets/robots/<id>/training/source
```

**这张表说明**：真正要迁的只有 **8 个包**，其中 **5 个已经在 Kit 上了**（合计 39 py，属"收尾"），
真正的未知只有 **go2（178 py）** 与 **zex-w（21 py，形态不同）**，加一个最轻的 **go1（3 py）**。

### 1.2 已有 Kit 长什么样（读 `adapters/mjlab/velocity_task_kit/`，1971 行）

| 件 | 内容 | 对 Kit 设计的含义 |
|---|---|---|
| `__init__.py` | 装配骨架（sim 上限 / 实体挂载 / 高度扫描重指 / viewer / play 收尾 / PPO runner）+ `XmlActuatorCfg` 执行器包装机制 + `ppo_runner_cfg_ex`（轮足三包扩展版） | **"框架层"的边界它已经划好了**：装配与运行器属 Kit，任务参数属包 |
| `mdp/`（10 文件） | `curriculums / feet_rewards / observations / posture_rewards / randomization / rewards / terminations / tracking_rewards / velocity_command / wheel_rewards` + `__init__` 命名空间组合真值 | 奖励库 / 观测组装 / 课程 / 终止 / 命令生成 —— **正是 `06` §2.1 列的 5 项 Kit 职责** |
| `velocity_env_cfg.py`（381 行） | velocity 基座 cfg 工厂；twist 命令类**参数化**（默认 = kit 族语义，m20 stub 显式传自己的类） | "形态默认 + 包可覆盖"的接口范式已经存在 |

**它已经遵守的两条纪律**（值得在升格时保留为硬规则）：
1. **逐个函数标注来源**（"哪一包的哪一段原样上移"）+ **默认参数即各包出现过的字面常量** ⇒ 调用方按原顺序调用就能复现原构建序列；
2. **上游 API 适配的裁决语义原样保留**（B22/B26/B28/B31/B35），**注释随任务特有部分留在包内**。

### 1.3 两个物理约束（决定 Kit 放哪，见 §4）

| 约束 | 来源 | 对方案的影响 |
|---|---|---|
| 包侧 stub 必须**自举仓库根**：worker / schema-dump / 冒烟三处只把 `training/source`（或包根）放进 `sys.path` | `velocity_task_kit/__init__.py` docstring（assets 源树与 workspace 镜像副本深度不同，按文件位置探测） | Kit 与包之间**不是普通 import 关系**，位置一变，自举逻辑与全部 stub 都要跟着改 |
| **不引入** `00_resources/mjlab-skillkit/` 的 `adapters/`、`agents/` 目录；只对照其 dict-based manager / 迁移配方 / preserve-layout 写法 | 同上 docstring（既有裁决） | Kit 归属 `adapters/mjlab/` 这条边界**已经定过**，本草案不重开 |

---

## 2. 形态归类（谁归谁）

| 形态 | Kit | 归属包 | 迁移量 |
|---|---|---|---|
| **四足** | `quadruped_kit` | go2 / go1 / b2 / lite3 | 4 包，**192 py**（go2 占 178） |
| **轮足** | `wheel_leg_kit` | go2w / b2w / m20 / zex-w | 4 包，**53 py** |
| **人形** | **暂不建** | g1（86 py）**只登记不迁** | 0 |
| — | — | 冻结 5 包：tron1×3 / microduck / wuji_hand | 0 |

**三条归类规则**（沿用既有裁决，不在本草案重开）：

1. **不按"腿数"分** —— 按形态能力分：`m20` 归**轮足**（不是四足），`g1` 归**人形**（`06` §2.1 / `05` P 组头）。
2. **冻结包不参与任何 Kit 动作** —— 维持现状（含质量攻关与新规模训练）。
3. **人形 Kit 暂不建** —— g1 的框架迁移走 `05` P3/P4（上游策略移植），不并入本轮。

---

## 3. Kit 的构成（提供什么 / 不提供什么）

### 3.1 提供（七项，全部有现存载体）

| # | Kit 提供 | 现存载体 | 备注 |
|---|---|---|---|
| 1 | 奖励函数库 | `mdp/{rewards,feet_rewards,posture_rewards,tracking_rewards,wheel_rewards}.py` | 任务特有奖励项**留包** |
| 2 | 观测组装 | `mdp/observations.py` | 契约 `observation.components` 是声明真值，Kit 是装配实现 |
| 3 | 课程 | `mdp/curriculums.py` | |
| 4 | 终止条件 | `mdp/terminations.py` | |
| 5 | 命令生成 | `mdp/velocity_command.py` | 命令**档位**契约在 `registry/motion_commands.json` |
| 6 | 训练循环接线 | `__init__.py` 的装配骨架 + `ppo_runner_cfg(_ex)` | 算法切换点 = `AlgorithmPlugin`（§2.5） |
| 7 | 域随机化 | `mdp/randomization.py` | 教程 Ch08 的四类 Event 模式 |

### 3.2 不提供（三条边界，与 `06` §2.1 一致）

| 不提供 | 归谁 |
|---|---|
| **任何物理数值**（PD / 限位 / 质量 / 惯量 / 频率） | **契约真值 → MJCF**（执行真值），`tools/bake_mjcf_physics.py` + `validate_mjcf_contract.py` 守门 |
| **半自主参数的取值**（`action_scale` 等） | 数值住契约；**Kit 只给"起点公式 + 诊断表"**（`06` §2.3） |
| **状态与进度** | `05`（Kit 不写状态） |

### 3.3 三层接口（覆盖关系）

```
形态默认（Kit 给：函数默认值 = 该形态出现过的字面常量）
   ↑ 可覆盖
包覆盖（包内 stub / 任务特有模块：如 m20 的 m20_rewards 两行、zex-w 的 robot 常量表）
   ↑ 可覆盖
profile 覆盖（training/profiles/<id>.json，52 个：地形偏好 / 课程档位 / 算法选择）
```

> **注意**：算法**选择**属 profile（`algorithm` + `algorithm_plugin`），**接入点**属 Kit —— 两者别混（`06` §2.5 的"三个能"）。

---

## 4. 落点方案（三选一）

| 方案 | 形态 | 优点 | 代价 / 否决理由 |
|---|---|---|---|
| **A. 顶层 `kits/{quadruped,wheel_leg}_kit/`** | 仓库一等公民，语义最显眼 | `06` §2.1 目标落点原样 | ①与 **§1.3 约束二**冲突（既有裁决：Kit 归属 `adapters/mjlab/` 边界）；②包侧 stub 的自举（沿目录向上找 `adapters/mjlab`）与全部 5 包 stub 都要改；③跨边界引入第二处"Kit 位置"概念 |
| **B. `adapters/mjlab/kits/{quadruped,wheel_leg}_kit/`**（**推荐**） | 位置仍在 `adapters/mjlab/` 内，名字体现"形态" | ①自举逻辑**不变**（仍能沿目录向上找到 `adapters/mjlab`）；②与既有裁决不冲突；③`kits/` 一级目录让"形态 Kit"可枚举 | 需要一次**引用路径平移**（5 包 stub 的 import 语句 + `algorithms/registry.py` 的引用），一次 `sed` 可完成且**有测试兜底**（见 §5 步 0） |
| C. 原地升格（保留 `velocity_task_kit/` 之名，只写文档） | 零改动 | 零风险 | 名字不承载"形态"语义 —— 下一个形态（人形/新形态）来了会再纠结一次；等于**没解决命名问题** |

**推荐 B**，理由就是上表那三条；A 的唯一优势（"一等公民"）可通过 `README`/`02 §8` 登记补偿。

---

## 5. 迁移三步（每步含判据与回滚点）

> 顺序原则：**先把自己已经在用的收尾，再动最小的新包，最后动最重的**。每步独立成一次提交，可单独回退。

### 步 0 · 升格与命名（不迁任何包）

- **做什么**：`velocity_task_kit/` → `kits/quadruped_kit/` + `kits/wheel_leg_kit/`（按形态拆；**先做包装而非重写**，两 Kit 共同部分可暂留 `kits/_shared/` 或直接双份并在 DoD 里登记"合并待办"——按 §9 待决② 你定）。
- **判据**：`tools/audit_training_entrypoints.py`（150 条）、`audit_obs_group_names`、`validate_mjcf_contract`、包级冒烟全绿；**5 个已用包只改 import 行**，`git diff --stat` 应只显示引用路径。
- **回滚点**：纯路径平移，`git revert` 即可。

### 步 1 · 最小新包：`unitree_go1`（3 py）

- **做什么**：按 b2 的既有形态迁入（两者同构）。
- **判据**：包内 py → 0/仅 stub；`16×5` 冒烟 + 语义等价 dump（构建序列逐项比对）；**不改 Python** 完成一次 `onboard → verify → 冒烟`。
- **回滚点**：单包，回退该包的 stub 与 Kit 引用。

### 步 2 · `zex-w`（21 py，结构不同）

- **做什么**：它的 `source/{mjcf,robot}/` 是上游 `rc_mjlab` 直搬（`05` P5 已记录"包内 27 py 与上游逐字一致"），**先判定"哪些属框架层、哪些属任务特有"**再迁；这也是**验证 Kit 边界是否经得起"非本仓风格包"**的一步。
- **判据**：同步 1 + `audit_porting_admission`。
- **回滚点**：单包。

### 步 3 · `unitree_go2`（178 py，最重）—— **先审计，后迁移，分批**

- **前置（必做）**：一次**只读审计**，产出 `local_tasks/` 178 py 的分类清单（框架层 / 任务特有 / 算法（已迁插件的残影）/ 死代码），**先删死代码与重复**，再谈迁移。
- **判据**：每批迁完跑一次 §6 的全套；go2 的 18 个 profile 逐个抽验（不要求全跑，但**抽验清单要写进提交信息**）。
- **回滚点**：按批回退。

### 不迁名单（明确写死，避免反复讨论）

- 冻结 5 包：`limx_tron1_pf` / `limx_tron1_sf` / `limx_tron1_wf` / `microduck` / `wuji_hand`；
- `unitree_g1`（人形 Kit 暂不建，`06` §2.1）。

---

## 6. DoD（怎么算"这个包迁完了"）

| # | 判据 | 怎么验 |
|---|---|---|
| 1 | **包内 py → 0 或仅入口 stub**（模块名与符号名不变，`audit_training_entrypoints.py` 静态解析不受影响） | `find assets/robots/<id>/training -name '*.py'` + 该门禁 |
| 2 | **语义等价**：迁前迁后**构建序列逐项一致**（Kit 承诺"默认参数即原字面常量"，可直接 dump 对比） | 语义等价 dump（步 0 建立基线，之后每包对比） |
| 3 | **不改 Python 完成一次移植**：`onboard → verify → 冒烟` 全绿 | 两入口同一 `package_id`（`05` I3 已达成） |
| 4 | **产物不退化**：同一 profile 迁前迁后的策略在无头验收里行为一致（帧级回放或验收报告） | `tools/replay_gate.py --auto` / `sim2sim_headless` 基线 |
| 5 | **门禁全绿**：`audit_training_entrypoints` / `audit_obs_group_names` / `validate_mjcf_contract` / `audit_sim2sim_consistency` / `validate_packs` | 现有 CI 口径 |

---

## 7. 风险与回滚

| 风险 | 缓解 |
|---|---|
| **"两 Kit 共同部分"分叉**（四足与轮足各抄一份，之后各自漂移） | 步 0 显式决定：共享部分放 `kits/_shared/` **或**双份 + 登记合并待办（§9 待决②）；**不允许默默双份** |
| **go2 的 178 py 里有与算法插件层的耦合残影**（4 族已迁 `algorithms/`，`local_tasks` 留薄 re-export） | 步 3 前置于**只读审计**，先删死代码；审计结论写进 `05` P1 |
| **自举路径假设被破坏**（包侧 stub 靠"沿目录向上找 `adapters/mjlab`"） | 方案 B 不改位置，自举逻辑与 5 包 stub 的探测方式都不变；步 0 的判据里含"只改 import 行" |
| **迁移期间训练产物谱系断裂**（同一个 profile 前后产出两套 onnx） | 判据 4（产物不退化）+ 每步独立提交 + 产物按 §5 抽验清单登记 |

---

## 8. 不做什么（引用既有裁决，不重开）

- ❌ 不建人形 Kit（`06` §2.1）；
- ❌ 不迁冻结包（`05` P 组）；
- ❌ 不引入 `mjlab-skillkit` 的 `adapters/`、`agents/`（既有裁决，只对照写法）；
- ❌ 不在 Kit 里放任何物理数值（`06` §2.1/§2.3 的边界）；
- ❌ 不重命名逻辑关节（`06` §2.2 勘误 2：保留上游物理原名，为上游对照服务）。

---

## 9. 待你拍板的三件事

| # | 待决 | 选项 | 我的建议 |
|---|---|---|---|
| ① | **落点** | A 顶层 `kits/` / **B `adapters/mjlab/kits/`** / C 原地升格 | **B**（理由见 §4：自举不变 + 不重开既有边界 + 名字体现形态） |
| ② | **两 Kit 的共同部分** | B1 抽 `kits/_shared/` / B2 先双份 + 登记合并待办 | **B2 先行**（步 0 先做"不改行为"的平移，共享抽取留给步 1 之后 —— 那时边界已被 go1 验证过） |
| ③ | **go2 的处置** | C1 先只读审计再决定分批 / C2 与 go1+zex-w 同批 | **C1**（178 py + 与插件层的历史耦合，先审计能避免抱着猜测改） |

**拍板之后**：我把结论并入 `06` §2.1、执行项拆进 `05` P 组（含每步的提交边界），然后本文件按 `00_know` 纪律归档或删除。

---

## 附：本草案用到的既有裁决索引（避免重复讨论）

| 事项 | 出处 |
|---|---|
| 形态归类按能力不按腿数（m20 轮足 / g1 人形） | `06` §2.1、`05` P 组头 |
| 人形 Kit 暂不建 | `06` §2.1 |
| 冻结包不参与 Kit 动作 | `05` P 组 |
| Kit 不给物理数值 / 半自主参数只给方法 | `06` §2.1、§2.3 |
| 保留上游物理关节原名 | `06` §2.2 勘误 2 |
| 算法选择属 profile、接入点属 Kit | `06` §2.5 |
| 不引入 skillkit 的 adapters/agents | `velocity_task_kit/__init__.py` docstring |
| "框架层上移 + 包内只留任务特有 + 入口 stub" | 同上（B8 训练去包化） |
