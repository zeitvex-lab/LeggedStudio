# RL 运控训练知识地图：机器人强化学习训练分类与"主要训练什么"

> **数据来源**：本目录 `RL运控/Ch01–Ch28`（共 28 章，约 7 万行，工程级教材，隶属 [Robotics_Tutorial](https://github.com/Michael-Jetson/Robotics_Tutorial)，作者 Pengfei Guo，达妙科技，CC BY 4.0）
> **本文定位**：把 28 章内容按"机器人强化学习到底在练哪些任务、每一类主要训练什么、用什么信号/奖励/技巧把它练出来"重新组织成一张**分类知识地图**，并对接到本地工作区的 47 个 RL 资产目录，方便按需跳读原章。
> **阅读约定**：`ChXX §y.z` = 原章节号/节号；`→[工作区]xx` = 本地资产目录；未写"原文"的具体数值均来自对应章节正文，建议回原文核对上下文再引用。

---

## 0. 28 章全书脉络（先建立全局）

整本书是一个递进体系，按工程依赖可切成 7 段：

| 段落 | 章节 | 解决什么问题 |
|---|---|---|
| 1 生态与基建 | Ch01–03 | 为什么必须用仿真训练；GPU 仿真生态（MuJoCo Warp / PhysX / Newton）、双框架（mjlab vs Isaac Lab）选型与安装分层验证、物理引擎选型调参 |
| 2 RL 工程内核 | Ch04–10 | obs/action 契约（Ch05）→ reward/curriculum/termination（Ch06）→ PPO 训练管线与超参（Ch07）→ 域随机化 DR（Ch08）→ 特权学习/蒸馏（Ch09）→ 模仿学习三技术线（Ch10）。这是全书"方法内核" |
| 3 机器人本体资产 | Ch11–12 | CAD→URDF→MJCF/USD 资产全链路；actuator 建模四层级与系统辨识（sim2real 最后的残余 gap 常在此） |
| 4 单形态实战 | Ch13–18 | 四足速度跟踪（Ch13）→ 人形速度跟踪（Ch14）→ 大规模动作模仿（Ch15）→ 多模态动作获取（Ch16）→ 机械臂/灵巧手操作（Ch17）→ 视觉感知运动控制/跑酷（Ch18） |
| 5 复合形态与全身 | Ch19–21 | 四足+机械臂 loco-manipulation（Ch19）→ 人形全身控制（Ch20）→ 轮式底盘+双臂移动操作（Ch21） |
| 6 训练工程化 | Ch22–25 | DIY 从零建环境（Ch22）→ Sim2Real 全链路与七层 gap 分类（Ch23）→ 大规模训练/性能/NaN（Ch24）→ 训练诊断与全书调参地图（Ch25） |
| 7 综合竞技项目 | Ch26–28 | 人形网球端到端：场地与球物理（Ch26）→ 感知与轨迹预测（Ch27）→ 击球控制与全身协调（Ch28） |

书上用 **累积项目 A–G** 串起动手线：A=四足速度（Ch13）、B=人形速度（Ch14）、C=动作模仿（Ch15–16）、D=固定基座操作（Ch17）、E=视觉感知/移动操作（Ch18–19）、F=人形全身（Ch20）、G=轮式双臂搬运（Ch21）。

> **一句话全貌**：Ch04–Ch10 是"怎么把任意运动任务训出来"的通用内核；Ch13–Ch21 是"不同任务族分别主要训练什么"的实例；Ch11–12 与 Ch22–25 是横切的地基与工程化；Ch26–28 是把所有能力压到一个高动态目标上的综合考卷。

---

## 1. 总分类框架：机器人 RL 训练按"任务目标"分几类

书中的全部任务可归纳为 **6 大任务类 + 1 个横切方法层**。每个任务类本质是"**MDP 的命令结构不同**"：命令是 3 维速度 → 全身参考动作 → 视觉/地形 → 物体位姿 → 目标落点 → 组合。

| # | 任务类 | 命令/目标形态 | 核心要练的能力 | 对应章节 | 代表评价/产物 |
|---|---|---|---|---|---|
| 1 | **速度跟踪与鲁棒移动**（盲走） | `(vx,vy,ωz)` 速度命令 | 跨地形稳定跟速、抗扰动，不依赖外部感知 | Ch04–08 内核 + **Ch13 四足 / Ch14 人形** | 地形越障、RoboGauge 类自动评测 |
| 2 | **动作模仿 / 风格 / 技能** | 全身参考动作序列（~100+ 维） | 忠实复现 MoCap/视频/文本指定的动作、风格、技能 | **Ch10、Ch15、Ch16** | 舞蹈、武术、跌倒恢复、风格化行走 |
| 3 | **视觉感知运动控制 / 跑酷** | 视觉流→局部"走法"决策 | 用高度图/深度预测脚下地形并安全翻越 | **Ch18**（+Ch09 蒸馏、Ch13 底层） | extreme-parkour、DARPA 隧道零跌倒 |
| 4 | **固定基座操作 / 灵巧手** | 物体位姿→末端/手部接触序列 | 狭窄几何窗口下的接触任务：够-抓-搬-转 | **Ch17** | DexPBT、lift/repose cube、掌内重定向 |
| 5 | **复合形态：移动操作 & 全身控制** | 速度命令 + 末端目标/全身任务 | 底盘与臂/下肢与上肢的动力学耦合协调 | **Ch19（四足+臂）、Ch20（人形全身）、Ch21（轮式双臂）** | HumanoidBench、VBC、WoCoCo |
| 6 | **高动态竞技（球类）** | 高速飞行的目标（球） | 感知-预测-决策-接触的强实时端到端 | **Ch26–28** | 人形网球对打、ETH 四足羽毛球 |
| — | **横切方法层**（非任务类） | 不改变"命令结构"，改变"练得成练不成" | DR、蒸馏、actuator 建模、诊断、部署 | Ch08/09/11/12/22–25 | 贯穿以上所有类 |

> 阅读要点：Ch13/14（类 1）是全书"母任务"，类 2–6 都是在这套 obs/reward/train 内核上换"命令与观测结构"。**先跑通一个 velocity 任务，再谈其他。**

---

## 2. 逐类详解：每一类"主要训练什么"

### 2.1 速度跟踪与鲁棒移动（Blind Velocity Tracking）——全书的"Hello World"

**主要训练什么**：给策略一个随时间重采样的平面速度命令 `(vx^cmd, vy^cmd, ωz^cmd)`，让它学会在**平地 / 粗糙地形 / 大扰动**上稳健地跟速、变向、刹停而不摔倒——这是一切上层导航（Nav2/状态机/比赛任务）所依赖的"地基技能"。

| 设计环节 | 具体做法（书中原文锚点） |
|---|---|
| 观测 obs | actor（部署可得）：基座线/角速度、重力投影、关节位置与速度、上一动作、命令；critic/teacher 额外加**特权信息**（接触力、地形高度等，Ch09）。粗糙地形版加 **height scan（RaycastSensor）**：网格 pattern + 对齐方式决定观测维度（Ch13 §观测/传感器） |
| 动作 act | 12–29 DOF 的位置增量（position action + per-joint action scale，人形按关节分组各自定 scale，Ch14）；策略 50 Hz ↔ 物理 200 Hz（`decimation=4`） |
| 奖励 | **四层 reward 分解**（Ch06 §6.2）：Tracking（`exp(-‖e‖²/σ²)` 指数核跟速）/ Regularization（能耗、动作变化、足滑、抖动）/ Style（姿态自然）/ Contact（脚步节奏）；`scale_by_dt` 归一化 |
| 终止与课程 | 区分 `terminated`（真失败，影响 value）与 `time_out`（截断，需 bootstrap，Ch06/07）；**curriculum 三轴**：地形难度 / 命令范围 / reward 严格度；与 DR 的区别：课程改任务难度、DR 改物理规律（Ch08） |
| 训练技巧 | PPO（RSL-RL），asymmetric actor-critic，4096 env 起步 1–4 h 单卡收敛；阶段化验证：smoke→zero agent→random agent→小训练（Ch02 L0–L6） |
| 部署产物 | flat/rough 两档 onnx 策略（rough 面向真机野地）；盲策略天然对**传感器带宽要求低**、易上真机 |

**关键判读**：flat 是 rough 的"减法版本"（去掉 height scan / 复杂 curriculum / 部分 DR）；人形版与四足版的差异在**支撑多边形小一个数量级、角动量与上肢摆动的耦合**，四足的配置直接搬到 G1 会几步摔倒（Ch14 §14.1）。

**→[工作区]落地实例**：`unitree_rl_mjlab`（宇树官方 Go1/Go2/G1 velocity，即 Ch07/Ch13 参考项目）、`m20_rl_isaacsim`（官方 Isaac Lab velocity + 地形课程）、`rc_old/RC_WheelLeg`(ZEX-W，mjlab 自研轮足三任务 `Robot-Flat/Rough/Crawl` + 自适应指令课程 + 障碍释放课程)、`go2w_sim2sim`/`LeggedSkillDeploy`（真机入口）。

---

### 2.2 动作模仿 / 风格 / 技能（Motion Imitation，三技术线）

**主要训练什么**：速度跟踪只规定"走多快"，不规定"怎么走"；本类把"身体每个关键点该在哪、朝哪、多快"以参考运动形式交给策略去**忠实复现**。书中梳理三条并行技术线（Ch10）：

| 技术线 | 训练信号 | 代表方法与章节 | 适用 |
|---|---|---|---|
| **显式跟踪 Mimic** | 关键点位置/关节角度/根轨迹的指数核跟踪误差 | BeyondMimic、PnC/PULSE（**Ch15**）；la-fan、AMASS 大规模（142K motions 需 per-GPU 分片 + 自适应采样） | 精确复现/技能学习 |
| **对抗先验 AMP/ASE** | GAN 式判别器区分"仿真状态 vs 参考状态"，判别器奖励+gradient penalty | ProtoMotions AMP/ASE/CALM（**Ch15/Ch16**，算法切换仅 ~30 行配置差异） | 风格化、多样步态、无逐帧对齐 |
| **行为克隆 BC/DAgger** | teacher 示范的监督蒸馏 loss | BC/DAgger 蒸馏链（Ch10/Ch09），把 tracker 能力灌进可部署 student | 部署轻量化 |

**必须处理的工程问题**：数据重定向（AMASS→SMPL→retarget→`.npz`→环境）、参考动作在目标机器人上的**物理可行性判定**（关节限位/力矩/接触）、tracking 漂移、判别器坍塌、灾难性遗忘（PHC 用 progressive networks 处理数千动作，单个 MLP 会遗忘）。

**动作来源（Ch16）**：MoCap（AMASS，精度 <1 mm，贵）→ 单目视频（WHAM 等，~5 cm，便宜）→ **文本/文生动作**（MDM/T2M-GPT/CALM 语言条件风格）→ 实时遥操作（HumanPlus shadowing、单 RGB 相机）。文生动作受限于物理可行性与精度，但"想象=输入"的灵活性最高。

**→[工作区]落地实例**：`robot_lab`（BeyondMimic 系）、`AMP_mjlab`（G1 舞蹈/AMP 复现）、`g1_spinkick_example`、`InstinctMJ`（Shadowing/WholeBody 参考）、`lain_job/ArenaX`（行为克隆/模仿泛化）、`mujoco_playground`（mimic 示例）。

---

### 2.3 视觉感知运动控制 / 跑酷（Perceptive Locomotion & Parkour）

**主要训练什么**："盲"策略只靠本体感知，在光滑平地够用、在"脚下地形未知"时会摔。本类让机器人用**深度相机/高度图看到地形再决定走法**：识别台阶、壕沟、斜坡、障碍的几何，把视觉特征转化为可落地的步态选择。

**标准三阶段蒸馏管线（Ch18 §18.5，源自 extreme-parkour ICRA'24）**：
1. Stage 1 **State Teacher（blind oracle）**：喂**特权 height scan**（RaycastSensor/BVH），训出教师策略上限；
2. Stage 2 **Depth Student**：把 teacher 的知识用 **DAgger 采集**蒸馏进只吃**自我中心前视深度图**的学生；
3. Stage 3 **RGB Student（可选）**：加视觉 DR 后再蒸一层。

| 关键点 | 内容 |
|---|---|
| 感知范式对比 | height scan = 特权/精确/不可部署；egocentric depth = 可部署/需 CNN/有传感器延迟与视野死角（前视相机看不到后脚下地形） |
| 视觉编码器 | CNN + SpatialSoftmax（保留位置信息，优于 Global Pooling）；时序用 ConvNet+GRU；前沿用 foundation model encoder |
| 奖励 | 前进 progress + 越障通过奖励 − 碰撞惩罚；课程按障碍难度渐进释放 |
| 与操作视觉的差异 | Ch17 看"方块在哪"（物体位姿），Ch18 看"脚下的地形是什么"（地形几何），共享 CNN+蒸馏+视觉 DR 内核，但传感器配置/部署约束完全不同 |
| 部署 | 深度延迟 30–100 ms 需延迟补偿；相机分辨率-吞吐-精度三角权衡（Isaac Lab `TiledCamera` / mjlab Warp Batch Renderer） |

**→[工作区]落地实例**：`parkour_mjlab`（Go2 感知跑酷，CNN/Transformer + height map + 记忆），`m20_rl_isaacsim` 的 Perception 任务（相机/LiDAR 感知避障），`InstinctMJ`（Perceptive 方向参考）。

---

### 2.4 固定基座操作 / 灵巧手（Fixed-base Manipulation & Dexterous Hands）

**主要训练什么**：与 locomotion"持续运动即成功"相反，操作类是"**改变世界状态才算成功**"：抬方块、翻方块、掌内转动、插入/旋拧。书中强调核心难点**不是自由度数，而是几何窗口的狭窄 + 接触的二元性（抓上/没抓上）**。

| 设计环节 | 具体做法（Ch17） |
|---|---|
| 观测 | 关节 + 末端 + **物体相对位姿** +（可选）触觉/力；视觉版按 state→depth→RGB 渐进引入，防特权泄漏，配 CNN/SpatialSoftmax |
| 动作空间 | JointPositionAction（关节空间）/ DifferentialIKAction / OSC（任务空间）三选一，按任务选型；夹爪常加 equality joint 反向耦合建模 |
| 奖励 | **staged reward**：reach→grasp→lift 分阶段，**乘法门控**（如 `r_reach×(1+r_bring)`）优于简单加权——门控编码"只有先够到才谈搬走"的因果结构；任务越接近成功 reward 越成形，缓解稀疏 |
| 训练设置 | episode 比 locomotion 短、需要大量 reset；接触参数 `condim/friction/solref` 直接影响抓取稳定性；物体位姿随机化通常用 **reset 模式** Event |
| 进阶 | 灵巧手 DexSuite（Allegro）+ **DexPBT**（基于种群的超参搜索，RSS'23）；掌内重定向类任务靠蒸馏 + 触觉/视觉闭环 |

**→[工作区]落地实例**：`wuji-mjlab`（掌内全 SO(3) 重定向、softbody 物、342→16 维蒸馏——工作区最贴近 Ch17 的单项）、`mujoco_playground`（Panda/ALOHA/LeapHand manipulation 示例）、`g1-manipulation-challenge`（纯推理评估项，非训练仓）、`unilab_new`（off-policy SAC/操控向）。

---

### 2.5 复合形态：移动操作 & 全身控制（Loco-Manipulation / Whole-Body / Wheeled）

**主要训练什么**：把"移动"和"操作"两种能力压进**一个策略**，难点全在耦合：

- **Ch19 四足+臂**（Go2+ARX L5 / B1+Z1 / ANYmal-D+DynaArm）：三类耦合——① 逆运动学耦合（底盘姿态改变臂 workspace）② 动力学耦合（臂动改变 CoM/角动量）③ 感知耦合（导航误差放大操作误差）。做法：混合动作空间（底盘速度命令 + 臂关节位置 + 末端增量，**跨量纲归一化**）；reward 用 navigation + EE tracking + grasp + stability 多目标融合；**arm-constrained 四阶段课程**（冻结臂→逐步放开→联合训练）；VBC（CoRL'24）用低层 whole-body tracker + 高层 visual policy 分层 + hot-start。
- **Ch20 人形全身**（G1 23–43 DOF / H1）：挑战是 DOF 爆炸 + 上下肢角动量耦合 + 长时程接触序列。三条技术路线对比：**上下肢解耦**（ExBody/ExBody2：velocity-landmark 解耦 tracking）/**接触阶段分解**（WoCoCo：stage-aware reward + 三阶段 DR 课程）/**mask-conditioned 统一**（HOVER：一个策略多模态切换，mask 条件观测）；评估用 **HumanoidBench 27-task**；安全兜底接 **HoST 跌倒恢复**；部署防高频抖动用低通滤波（WoCoCo 4 Hz Butterworth）。
- **Ch21 轮式底盘+双臂**：无足式平衡难题但引入**非完整约束、底盘漂移、base-arm 动力学耦合**；工业界占比最高的形态（Ridgeback+UR5、Husky 双臂、TIAGo、Stretch）。从固定底盘抓到移动搬运走**五阶段 curriculum**；诊断重点是"抓取时底盘被拉漂"。

**→[工作区]落地实例**：知识侧为主；`m20` 官方"导航+感知"链、`kungfu/Instance...`、`robot_lab` 的 BeyondMimic 全身参考可作为进入 Ch20 的前置资料；若做轮式/双臂可参考 Ch21 的 Ridgeback-UR5 示例（对应 `awesome-loco-manipulation` 类开源资产）。

---

### 2.6 高动态竞技（球类综合：网球 Ch26–28 压轴）

**主要训练什么**：把前 25 章全部能力压到"**目标在飞**"的场景：时速 20–45 m/s 的网球几百毫秒内完成感知→预测→决策→全身协调击球。书中明确说：目标在飞，会把前面每一个模块的设计缺陷都放大。

- **Ch26 场地与球物理**：球场环境是跨感知/预测/控制模块共享的**数据协议**（court-local 坐标系、ITF 尺寸）；网球必须 `freejoint`，接触参数 `condim/friction/solref/solimp` 调参；**八维发球命令**；**三层空气动力学**（真空→二次阻力→Magnus 力）逐层验证增量；球拍-机器人分段引入建模。
- **Ch27 感知与预测**：给出六个"让天真方案失败的原因"——球极小（半径 0.033 m）、极快（20–45 m/s）、抛物线（线性外推 0.5 s 后 z 向差 ~1.23 m）、会弹跳（COR≈0.73–0.76）、空气动力学残差、观测延迟（30 ms@30 m/s ≈ 0.9 m 误差，超过球拍有效击球面 ~30 cm）。解法：**6D EKF 抛体预测（含非线性 Jacobian）+ GRU 残差预测器**（物理模型做 baseline 而非端到端）+ 延迟补偿；向控制器输出 `PredictorOutput{impact_pos_c, time_to_impact, uncertainty, validity}`——**`time_to_impact` 比预测位置更接近控制需求**。
- **Ch28 击球控制**：本质是"**带速度与姿态约束的定时接触**"，比 reach/lift 更难。五类 staged reward（approach / timing / contact / outcome / regularization）；**8 阶段 curriculum 从静态球到高速发球，成功率门控 + 安全回退**；五类 DR 消融；**Lagrangian PPO 安全约束**；真机侧注意接触仅 3–5 ms、需 2000 Hz 级仿真精度（LATENT 消融：去掉 dynamics randomization 真机成功率 91%→14–29%）。

**→[工作区]落地实例**：暂无完整球类仓；可作为 Legged Studio 未来"综合技能验证"的参照（章节引用的 LATENT/HITTER/ETH 羽毛球均开源）。

---

### 2.7 横切方法层：不改变"练什么"，决定"练得成练不成"

以下工具在每一类任务里通用，是本书的"内力"章节：

| 章节 | 一句话干货 |
|---|---|
| Ch08 域随机化 | EventManager **四种触发模式**（startup/reset/interval/step）；物理一致性随机化用 **pseudo-inertia**（只改 mass 不改惯量张量会导致物理不自洽）；DR 优化的是期望而非最坏情况，范围要反映真实不确定性；分阶段 DR；ASAP delta action 用于 DR 不够时的残差建模 |
| Ch09 特权/蒸馏 | 把观测分四类角色（actor/critic/teacher/student）；**asymmetric actor-critic**（critic 看特权降方差）；RMA 两阶段（环境参数 encoder→latent，再让 adaptation module 从本体史估计 latent）；三种在线适应范式对比（RMA/causal transformer/TTT）；信息泄漏诊断 + 15 项 debug checklist |
| Ch10 模仿三线 | 见 §2.2；BC 注意 covariate shift，DAgger 迭代采集缓解 |
| Ch11 资产管线 | SolidWorks→URDF（sw2urdf）→MJCF（Menagerie 流程）/USD（`convert_urdf.py`）；collision mesh 用 V-HACD/CoACD 凸分解；**惯量参数物理一致性验证**（自由落体/静止平衡测试）；双框架行为不一致常源于惯性/坐标系 |
| Ch12 Actuator | actuator 四层级：Ideal PD → DC Motor → Actuator Network → **Delta Action Model**；扫频/阶跃/摩擦测量做系统辨识；当 DR 和视觉增强都做足后，残余 sim2real gap 主要来自**力矩跟踪与通信/控制延迟** |
| Ch22 DIY | 从零注册任务 / 建 Isaac Lab extension；smoke→zero→random 三步验证；10 类最常见环境 bug（关节名不匹配静默失败、照搬他机 reward/scale 等） |
| Ch23 Sim2Real | **七层 gap 分类**（动力学/接触/执行器/传感器/时序/软件接口/安全），各配解决工具（SysID vs DR vs Fine-tuning vs 自适应）；**D0→D6 分级验收**；ONNX 导出边界——action scale/offset、normalizer 的 running 统计是否烘焙进图必须明确，网络外的后处理逻辑一律由部署端补齐；延迟分四类补偿 |
| Ch24 大规模 | 单 GPU 4096 env 吞吐约 150–250k env-steps/s（12DOF）或 80–120k（29DOF）；多 GPU 只在"加 env 不增速/需>10k env/5+ seed/10+ 超参组合"时引入；NaN 用 `--enable-nan-guard`/`viz-nan` + 优先级排查；AGILE 四阶段工业 workflow |
| Ch25 诊断 | **五大仪表盘**（reward/KL/entropy/value_loss/episode_length）联合读，识别 9+ 种训练模式；症状→参数→章节的调参索引表；平滑性分析（L2C2/action rescaler）判可部署性 |

---

## 3. 一句话记忆表：28 章 → "在练什么/讲什么"

| 章 | 一句话（主要训练/讲授什么） |
|---|---|
| Ch01 生态系统 | GPU 仿真为何是训练基础设施；mjlab vs Isaac Lab 双框架全景（含 Newton 1.0 GA） |
| Ch02 环境搭建 | mjlab/Isaac Lab 安装与 **L0–L6 分层验证**（CUDA→import→task→scene→zero/random→16-env 小训练） |
| Ch03 物理引擎 | MuJoCo（广义坐标+凸优化接触）/PhysX（TGS）/Newton（7 求解器统一）建模差异与 `solref/solimp` 调参；sim2sim |
| Ch04 Manager 架构 | PPO 训练循环如何与 `env.step()` 交互；Manager-Based 九大 Manager 与 env.step 18 步时序（obs 在 `sim.forward()` 之后、reward 之前等） |
| Ch05 obs/action 契约 | 观测/动作接口设计（部署可得性、actor/critic 非对称、action scale 链、obs 处理管线、HOVER 多模态 mask 观测、ONNX 部署边界、四元数 wxyz 约定） |
| Ch06 reward/课程/终止 | 四层 reward 分解、指数核与梯度、`terminated` vs `time_out` 与 value bootstrap、curriculum 三轴、reward ablation |
| Ch07 训练管线 | RslRlVecEnvWrapper 四职责、PPO 超参全解析、自适应 KL 调度、MLP/RNN/CNN 选型、ONNX 导出、PPO vs SAC |
| Ch08 域随机化 | DR 四种 Event 模式、pseudo-inertia、push/impulse、分阶段 DR、评估方法论、ASAP delta action |
| Ch09 特权/蒸馏 | 非对称 AC、RMA 适应模块、teacher-student 三阶段流程、信息泄漏诊断、extreme-parkour/HOVER/VIRAL 蒸馏案例 |
| Ch10 模仿理论 | 显式 tracking / AMP 对抗 / BC 三线选型；数据管线（AMASS→SMPL→retarget） |
| Ch11 资产链路 | SW→URDF→MJCF/USD、凸分解、惯量校验、Menagerie/Asset Zoo 现成资产 |
| Ch12 Actuator | 四层级 actuator 建模、系统辨识实验（扫频/阶跃/摩擦）、ASAP delta action、`ActuatorNetMLP` |
| Ch13 四足速度 | Go1/Go2 flat+rough 全链路精读：height scan、flat=rough 减法、双框架对比、四层 reward 实战 |
| Ch14 人形速度 | G1/H1：支撑多边形 vs 四足、per-joint action scale、variable posture、人形特有失败模式、sim-to-sim |
| Ch15 动作模仿实战 | BeyondMimic 从零跑通 G1 tracking；ProtoMotions AMP/ASE/CALM；142K motions 分片与自适应采样；PHC、KungfuBot |
| Ch16 多模态动作 | 动作来源三时代：MoCap→视频→文本；CALM/MaskedMimic 条件控制；TextOp、HumanPlus（RGB 遥操）、HDMI |
| Ch17 操作/灵巧手 | YAM lift cube 四变体为主线：staged reward、三种动作空间、接触参数；DexSuite+DexPBT 灵巧手进阶 |
| Ch18 视觉运控 | height scan vs egocentric depth；三阶段蒸馏（oracle→depth student→RGB）；visual DR；extreme-parkour 精读 |
| Ch19 四足+臂 | 三重耦合建模、混合动作空间、四阶段课程、VBC 分层架构、ETH 羽毛球 constrained RL |
| Ch20 人形全身 | 三条技术路线（ExBody 解耦/WoCoCo 接触阶段/HOVER mask 条件）；HumanoidBench；HoST 跌倒恢复；KungfuBot |
| Ch21 轮式双臂 | 非完整约束与底盘漂移、混合动作空间与量纲归一化、五阶段课程、工业移动操作形态 |
| Ch22 DIY | 从零注册自定义任务、验证三步走、10 类环境 bug 诊断、Manager-Based vs Direct 选型 |
| Ch23 Sim2Real | 七层 gap 分类与四类解法、D0–D6 分级验收、延迟四分类补偿、ONNX 部署边界 |
| Ch24 大规模训练 | 多 GPU 决策标准、CUDA Graph、NaN 系统排查、性能 profile、AGILE workflow、公平实验设计 |
| Ch25 诊断地图 | 五大指标联合读、症状→调参索引、调试工作流、消融方法论、L2C2 可部署性分析 |
| Ch26 网球环境 | 环境即数据协议：court-local 坐标、球 freejoint/接触参数、八维发球、三层空气动力学、球拍引入路线 |
| Ch27 感知预测 | 六个失败原因；6D EKF + GRU 残差；分层验证；延迟补偿；`PredictorOutput` 接口 |
| Ch28 击球控制 | "带速度与姿态约束的定时接触"：五类 staged reward、8 阶段课程、五类 DR、Lagrangian PPO、网球 sim2real |

---

## 4. 本地工作区资产 → 知识库章节索引（反查用）

从工作区 47 个 RL 目录反查"我该读哪几章"：

| 本地资产 | 机器人/主题 | 优先阅读章节 |
|---|---|---|
| `unitree_rl_mjlab` | 宇树 Go1/Go2/G1 mjlab 官方 | Ch07（unitree_rl_mjlab 为参考项目）、Ch13、Ch14、Ch05/06 |
| `m20_rl_isaacsim` / `rl_training` | 云深处 M20/Lite3 官方链 | Ch13（velocity+rough）、Ch18（Perception）、Ch23（部署） |
| `rc_old/RC_WheelLeg`(ZEX-W) | 自研 16DOF 轮足 mjlab | Ch13（速度/Rough/Crawl 课程）、Ch22（自研任务注册）、Ch23（ROS2/TensorRT 部署验收） |
| `parkour_mjlab` | Go2 感知跑酷 | Ch18（三阶段蒸馏）、Ch09（privileged/蒸馏）、Ch13 |
| `wuji-mjlab` | 灵巧手掌内重定向 | Ch17（操作/灵巧手）、Ch09（蒸馏）、Ch05（手部 obs/act） |
| `AMP_mjlab` / `robot_lab` / `InstinctMJ` | 模仿/舞蹈/全身 | Ch10、Ch15、Ch20 |
| `g1_spinkick_example` | G1 特技 | Ch15（引用案例 g1_spinkick）、Ch14 |
| `kaiwu_rl` | 三件套闭环 + RoboGauge | Ch23（sim2real 验收）、Ch25（诊断/评测）、Ch07/08 |
| `Dreamwaq` | 视觉 teacher-student/特技 | Ch09（蒸馏）、Ch18（感知）、Ch12（actuator） |
| `go2w_*` / `LeggedSkillDeploy` | Go2W/Go1 部署 | Ch13/14（速度）、Ch23（部署）、Ch22 |
| `sdk_deploy` / `tron1-rl-isaaclab` | 官方 SDK 部署 / TRON1 | Ch23（D0–D6 验收）、Ch12（actuator 辨识） |
| `g1-manipulation-challenge` | G1 操作挑战（纯推理） | Ch17（操作理论）、Ch20 |
| `mujoco_playground` | 跨形态 JAX 示例库 | 按任务对应 Ch13/17/18 |
| `UFO` | 无监督技能发现 | Ch16（skill/条件控制）、Ch09（蒸馏） |

---

## 5. 使用建议（怎么读这份地图）

1. **只想快速理解"RL 到底在练什么"**：读 §1 分类表 + §2.1（母任务），其余按需。
2. **准备训一个新机器人**：Ch22（注册任务）→ Ch11（资产）→ Ch12（actuator）→ Ch13/14（复制 velocity 模板改参数）→ Ch25（不收敛时回来诊断）。
3. **准备部署上真机**：Ch08（DR）→ Ch09（蒸馏/去特权）→ Ch12（执行器辨识）→ Ch23（七层 gap + D0–D6 验收）→ Ch05（ONNX 部署边界）。
4. **对齐本地资产看**：按 §4 反查表跳章，每章精读只读"本章目标 + 路线图 + 对应小节"即可（各章头部都自带了前置自测与路线图）。

---

## 6. 口径与边界说明

- 本文是**导航型知识地图**：分类框架与"主要训练什么"的判断基于各章"定位/目标/前置自测"及正文关键小节提炼，未复述全书推导与全部配置代码；引用具体数值前请回对应章节核对语境。
- 本地资产映射基于目录名与既有盘点口径（`机器人资产总盘点.md` / `机器人资产技术维度盘点.md`）的概括，**不是对每个仓库代码的逐行实证**；如需精确到"该仓能跑哪些 task 名 / 是否有 onnx"，请以仓库 README 与源码为准。
- 书内时间线引用的论文（如 BeyondMimic、HOVER、WoCoCo、LATENT、AGILE 等）及版本号（如 RSL-RL 5.x / mjlab 1.2.0 / Isaac Lab 2.3.0 / 3.0 Beta）均为原书锚定值，用于追溯，不代表本地环境版本。
