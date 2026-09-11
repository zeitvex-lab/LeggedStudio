# go1 / go2 / g1：三方参数对照与标准选定

> 目的：回答"这几款机器人到底该用哪一套参数"。要求是**确定一套、不叠加、成为标准**。
>
> 日期：2026-09-10 ｜ 路径已于 2026-09-11 随 `00_resources/` v3 改为「**按项目组织**」（`00_resources/<project>/…`）
> 覆盖范围：`00_resources/` 中与 go1/go2/g1 相关的项目（`lain_job`、`LeggedSkillDeploy`、`mujoco_playground`、
> `unilab_new`、`unitree_rl_mjlab`、`rl_sar`、`kaiwu_rl` 等）中的**契约（constants / config）**、
> **部署（含 `.pt` 的部署包）**、**训练（gym / lab / mjlab / unilab / playground）** 三类证据

---

## 0. 结论速览（先看这个）

1. **没有"唯一正确的一套"**——同一个参数在部署包、训练栈之间存在**系统性分歧**，因为它们的职责不同：
   * **部署包（带 `.pt`）**给的是**某个策略实际用的值**（含手调增益）；
   * **mjlab 契约**给的是**由执行器常数推导的物理值**（带 `armature` / `velocity_limit`）；
   * **legged_gym / mujoco_playground / unilab** 又各自有一套 task 默认。
2. 我们仓库事实上已经各选了一套，但**选择依据不统一**（go1 跟部署包、go2 跟 LLoco、g1 跟 mjlab 推导），**且没有把"选了哪套、为什么"写下来** —— 这才是"多套叠加"的根源：不是数据错，而是**没有声明标准**。
3. 本文件即为该声明。**每个参数必须属于"本体参数"或"策略级参数"之一，不得两边都改。**

---

## 1. 分工原则（判据）

| 类别 | 含义 | 归属 | 典型参数 |
|---|---|---|---|
| **本体参数** | 只由机器人硬件决定，与任务/策略无关 | **机器人契约** `actuator_profile` | `effort_limit`、`armature`、`velocity_limit`、PD 基准 `stiffness`/`damping`、`default_pose`、`control` 频率 |
| **策略级参数** | 同一台机器人不同策略取不同值 | **策略契约** `policies[].contract`（部署包 yaml 的那套） | `action_scale`（0.25 / 0.5 / 逐关节）、**策略专用增益** `rl_kp` / `rl_kd`、obs scales |

**关键证据**：同一个 go1 上，`himloco` 用 `rl_kp=40`、`go1`/`moe` 用 `rl_kp=20`；同一个 go1 上 `action_scale` 有 0.25（go1/himloco/moe）与逐关节 0.125/0.25（np3o）两种。**这证明它们不是本体参数**，写成机器人常量必然与某一个策略冲突。

**由此消解的一个真实陷阱**：部署 yaml 里 `fixed_kp/fixed_kd`（站桩控制器）与 `rl_kp/rl_kd`（策略）是**两套增益**，此前若把它们一起当成"机器人增益"就会互相覆盖。

---

## 2. go1

### 2.1 三方取值

| 参数 | mjlab 契约（推导） | 部署包 LeggedSkillDeploy（带 `.pt`） | 其他训练栈 |
|---|---|---|---|
| `effort_limit` | hip/thigh **23.7**、calf **35.55** | `torque_limits` **33.5（全关节）** | — |
| 推导 `stiffness` | hip/thigh **15.895**、calf **35.764** | `rl_kp` **20**（go1/moe）或 **40**（himloco/np3o） | unilab kp **35**、playground Kp **35** |
| 推导 `damping` | hip/thigh **1.012**、calf **2.277** | `rl_kd` **0.5** 或 **1** | unilab/playground Kd **0.5** |
| `armature` | hip **0.0040263**、calf **0.0090592** | 未提供 | 未提供 |
| `action_scale` | 推导 hip **0.3728** / calf **0.2485** | **0.25**（全关节）；np3o 逐关节 `[0.125,0.25,0.25]×4` | unilab **0.25**、playground **0.5** |
| 控制 | — | `dt 0.005 × decimation 4` = **50 Hz** | playground ctrl_dt 0.02 / sim_dt 0.004 |
| `default_pose` | thigh 0.9 / calf −1.8 | thigh **0.8~1.0** / calf **−1.5** | — |

mjlab 推导式（`contract/lain_job/.../go1_constants.py`）：

```python
ROTOR_INERTIA = 0.000111842
HIP_GEAR_RATIO = 6 ; KNEE_GEAR_RATIO = 9
reflected_inertia = ROTOR_INERTIA * ratio²
STIFFNESS = reflected_inertia * (10*2π)²      # NATURAL_FREQ = 10Hz
DAMPING   = 2 * DAMPING_RATIO * reflected_inertia * (10*2π)   # RATIO = 2
GO1_ACTION_SCALE[n] = 0.25 * effort_limit / stiffness
```

### 2.2 标准选定

| 参数 | **选定** | 理由 |
|---|---|---|
| 本体：`effort` / `stiffness` / `damping` / `armature` | **mjlab 推导集** | 它是唯一**由硬件常数推导**、且带 `armature`/`velocity_limit` 的集合（"功能更多"）；部署包的 kp 20/40 是**手调值**，属策略层 |
| 策略：`rl_kp` / `rl_kd` / `action_scale` | **留在策略契约** | 同机型不同策略取 20/40、0.25/0.5/逐关节，证明非本体属性 |

**当前差异**：我们契约现为 `stiffness 20 / damping 0.5 / effort 23.7·33.5 / armature 0.01`，
即**对齐的是部署包（kp 20 / torque 33.5）而非 mjlab 推导集**。若采纳上表，会改动仿真里
的 PD 增益（`20→15.895/35.764`）与 `armature`（`0.01→0.0040/0.0091`），
**属行为变更，需显式拍板**（见 §5）。

---

## 3. go2

### 3.1 三方取值

| 参数 | mjlab 契约 | 部署包 | 其他训练栈 |
|---|---|---|---|
| `effort_limit` | hip/thigh **23.5**、calf **45** | rl_sar/LeggedSkillDeploy `torque` **33.5**；robot_lab model **23.5** | LLoco trot **23.7/23.7/35.55**；robot_lab asset **23.7/45.43**；Dreamwaq **200/320** |
| `stiffness` | hip/thigh **20**、calf **40** | `rl_kp` **20 / 25 / 40**；`fixed_kp` **80** | Dreamwaq **25**；LLoco rear_stand **40** |
| `damping` | hip/thigh **1.0**、calf **2.0** | `rl_kd` **0.5 / 1**；`fixed_kd` **3** | — |
| `armature` | **0.01 / 0.01 / 0.02** | 未提供 | LLoco cts **0.00448**、trot **0.0**；Dreamwaq **0.0** |
| `action_scale` | go2 契约**未定义** `GO2_ACTION_SCALE`；go2w mjlab 部署 **0.5** | **0.25**（多数）；himloco/robot_lab **hip 0.125 + 其余 0.25** | unilab **0.25**（footstand 0.3）；robot_lab 训练 dict 同上 |

### 3.2 标准选定

| 参数 | **选定** | 理由 |
|---|---|---|
| 本体：`effort` / `armature` | **mjlab 契约**（`23.5 / 23.5 / 45`、`0.01 / 0.01 / 0.02`） | 唯一成体系的机型契约，且带 `armature` |
| 本体：`stiffness` / `damping` | **mjlab 契约**（`20 / 20 / 40`、`1 / 1 / 2`） | 同上；比部署包的手调整数更有依据 |
| 策略：`action_scale` / `rl_kp` / `rl_kd` | **留在策略契约** | 实测同机型有 0.25 与 `hip 0.125 + 其余 0.25` 两种 |

**当前差异**：我们契约现为 `stiffness 20（含 calf）/ damping 0.5 / effort 23.7·23.7·35.55 / armature 0.01·0.02`，
即**对齐的是 LLoco trot**（`effort 23.7,23.7,35.55 / stiffness 20 / damping 0.5`）。
与选定集相比，`calf stiffness`（20 vs 40）、`calf effort`（35.55 vs 45）、`damping`（0.5 vs 1/2）不同，
**属行为变更，需显式拍板**（见 §5）。

---

## 4. g1

### 4.1 三方取值（结论：**我们的契约已经自洽，无需改动**）

我们契约的每个角色都能与一条明确来源对上：

| 我们契约的角色 | effort | stiffness | damping | armature | 对上的来源 |
|---|---|---|---|---|---|
| `hip_pitch` / `hip_yaw` / `waist_yaw` | 88 | 40.179 | 2.5579 | 0.010183 | mjlab **7520_14** |
| `hip_roll` / `knee` | 139 | 99.098 | 6.3088 | 0.025101 | mjlab **7520_22** |
| `shoulder_*` / `elbow` / `wrist_roll` | 25 | 14.251 | 0.9072 | 0.003623 | mjlab **5020** |
| `waist_roll` / `waist_pitch` / `ankle_*` | 50 | 28.501 | 1.8144 | 0.007219 | mjlab **2×5020** |
| `wrist_pitch` / `wrist_yaw` | 5 | **16.778** | **1.0681** | 0.004256 | **部署实值**（kaiwu velocity / BeyondMimic 的 `16.7783 / 1.0681`），armature 取 AMP_mjlab 的 `W4010_25 = 0.00425` |

且 `action_scale` 与之一致：`0.25×effort/stiffness` 逐角色吻合（`0.5475 / 0.3507 / 0.4386 / 0.0745`），
与 BeyondMimic 部署 yaml 的逐关节值 `[0.548, 0.548, …, 0.0745]` 同源。

### 4.2 已知分歧（**不建议照搬**）

| 分歧 | 各栈取值 | 处置 |
|---|---|---|
| `hip_pitch` 属哪个电机 | **7520_14**（stiffness 40.18）：unitree_rl_mjlab / LLoco / g1_23dof；**7520_22**（99.10）：AMP_mjlab / g1_amp / dance / humanoidverse / kaiwu velocity | 我们取 **7520_14**（与 mjlab 主仓一致，且与自身 `action_scale 0.55` 自洽）。**属物理归属，若要改成 7520_22 会同时改动 stiffness/damping/effort/action_scale 四项，必须显式拍板** |
| 腕电机 | **4010**（stiffness 0.671，mjlab）：unitree_rl_mjlab / LLoco；**5010_16**（8.611）：AMP_mjlab / humanoidverse；**16.7783**（调参实值）：kaiwu velocity / dance / g1_amp | 我们取 **16.7783 部署实值**（有部署包背书）。注意 mjlab 的 4010（0.671）与之差 25 倍——**这是最大的一处分歧**，但 16.7783 有实际部署策略验证 |
| 23dof vs 29dof | `g1_23dof_constants` 无 waist、腕由 2×5020 承担（28.50）；29dof 有 waist + 4010/5010 腕 | 我们是 **29dof**，按 29dof 定义 ✓ |

**g1 因此不需要任何数值改动**，只需把"来源"记录下来（本表即是）。

---

## 5. 汇总：确定下来的标准 + 待决项

### 5.1 已确定（可直接执行）

1. **分工原则生效**：本体参数进机器人契约；`action_scale` 与策略专用增益（`rl_kp`/`rl_kd`）留在策略契约。
2. **`g1` 按现状冻结**：其数值集已自洽且有来源（mjlab 推导 + 腕部署实值）。
3. **`fixed_kp/fixed_kd` 与 `rl_kp/rl_kd` 不得混为一谈**：前者是站桩控制器、后者是策略；部署包里两套并存。

### 5.2 待决（改则影响仿真/训练行为，需拍板）

| 机型 | 现值（=对齐的部署/训练包） | 若采纳 mjlab 本体集 | 影响面 |
|---|---|---|---|
| `go1` | kp 20 / kd 0.5 / effort 23.7·33.5 / armature 0.01 | **15.895 / 35.764**、damping 1.012 / 2.277、effort 23.7 / **35.55**、armature 0.004026 / 0.009059 | 全部 go1 策略的仿真行为 |
| `go2` | kp 20（含 calf）/ kd 0.5 / effort 23.7·23.7·35.55 | **20 / 20 / 40**、damping 1 / 1 / 2、effort **23.5 / 23.5 / 45**、armature 0.01 / 0.01 / 0.02 | 全部 go2 策略的仿真行为 |

> 注：我们现值的来源是**真实存在的**（go1 → LeggedSkillDeploy 带 `.pt` 的部署包；go2 → LLoco trot），
> 并非错误。所以这是一个**"选部署手调值 vs 选物理推导值"**的取舍，而不是"修 bug"。
>
> **建议**：采纳 mjlab 推导集作为**本体基准**，因为我们自己的训练适配器就是 `adapters/mjlab`
> （训练与仿真必须同源），而部署包的 kp/kd 属策略层、应由 `policies[].contract` 携带。
> 但需你确认后再改，因为它会改变既有策略的仿真表现。

---

## 6. 数据来源索引（便于复核）

| 机型 | 关键文件 |
|---|---|
| go1 | `00_resources/lain_job/RoboLab/backends/mjlab/mjlab/src/mjlab/asset_zoo/robots/unitree_go1/go1_constants.py`（mjlab 推导）；`00_resources/LeggedSkillDeploy/policy/issacgym/go1/{go1,himloco,moe,np3o}/config.yaml`（带 `.pt` 的部署包）；`00_resources/{mujoco_playground,unilab_new}`（其它栈） |
| go2 | `00_resources/unitree_rl_mjlab/src/assets/robots/unitree_go2/go2_constants.py`；`00_resources/rl_sar/policy/go2/*/config.yaml`；`00_resources/unitree_rl_mjlab/deploy/robots/go2/config/policy/velocity/v0/params/deploy.yaml`；`00_resources/lain_job/LLoco/src/lloco/tasks/go2_skills/shared/robot.py` |
| g1 | `00_resources/unitree_rl_mjlab/src/assets/robots/unitree_g1/g1_constants.py`；`00_open/kaiwu_rl/unitree_cpp_deploy/logs/g1/velocity/g1_moe_cts_v0.0.5.1/params/deploy.yaml`（`logs/` 未纳入 `00_resources/`）；`00_open/kaiwu_rl/unitree_cpp_deploy/.../beyondmimic/dailylife_back_2_3/param/deploy.yaml`（同上）；`00_resources/LeggedSkillDeploy/policy/unitree_rl_lab/g1/*/config.yaml` |
