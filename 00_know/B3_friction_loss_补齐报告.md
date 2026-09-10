# B3 关节摩擦（friction_loss）补齐报告

> **日期**：2026-09-10 ｜ **范围**：14 个内置机器人包的 `actuator_profile.friction_loss`
> **原则**：每个值都有来源，不猜。**静/动摩擦（Fs/Fd/Va）本次不动**（待定）。

## 1. 为什么要分三类

摩擦值与其它物理量不同：**它既可能来自模型本身，也可能在模型里被漏掉**。
MuJoCo 对未声明的 `<joint>` 取 `frictionloss = 0`，但"0"有两种含义：

* 参考实现**显式写着 0**（真的按无摩擦建模）；
* 参考实现**根本没提**（建模时没考虑，是个缺口）。

这两者物理含义完全不同，所以补值必须区分来源，不能一律填 0 或一律填参考值。

取值方法：用 **MuJoCo 编译 `model/robot.xml` 读 `dof_frictionloss`**（会自动解析
MJCF 的 `default class` 继承，正则做不到），再对照 `resources/` 里的参考项目。
（注：`adapter/mjlab/.venv` 才有 mujoco；主 venv 没有。）

## 2. 逐包结果

| 包 | 活跃模型编译值 | resources 参考 | 本次写入 | 类别 |
|---|---|---|---|---|
| `unitree_go2` | 0.2（全 12） | URDF `friction=0.2` ✓ | 0.2（既有） | — |
| `unitree_go2w` | 0.2（全 16） | — | 0.2（既有） | — |
| `limx_tron1_sf` | ankle 0.01 | `SF_TRON1A/xml/robot.xml` ankle 0.01 ✓ | 0.01（既有，by_joint） | — |
| `limx_tron1_wf` | wheel 0.01 | — | 0.01（既有，by_joint） | — |
| `unitree_go1` | 0.2（全 12） | URDF 写 0.0（不一致） | **0.2** | A |
| `zex-w` | 0.01（全 16） | `wheelleg.xml` 0.01 ✓ 互相印证 | **0.01** | A |
| `microduck` | 0.0048（全 14） | 参考按组 0.1/0.006/0.032/0.013/0.0048/0（比活跃模型细） | **0.0048** | A |
| `deeprobotics_lite3` | **0**（未声明） | `jszr_robots/lite3/lite3.xml` = 0.2；URDF `friction=0.1`（**两参考不一致**） | **0.2** | **B** |
| `unitree_g1` | **0**（未声明） | 官方 `unitree_rl_mjlab`/`LeggedSkillDeploy`/`rl_sar_zoo` = 0.2（多数）；另有 0.3、0.1 | **0.2** | **B** |
| `deeprobotics_m20` | 0（未声明） | `M20_Piper.xml` **显式** `frictionloss="0"` | **0.0** | C |
| `limx_tron1_pf` | 0（未声明） | 无任何声明 | **0.0** | C |
| `unitree_b2` | 0（未声明） | 无任何声明 | **0.0** | C |
| `unitree_b2w` | 0（未声明） | 无任何声明 | **0.0** | C |
| `wuji_hand` | 0（未声明） | 无任何声明 | **0.0** | C |

## 3. 三类的影响（务必知悉）

### A 组 —— 幂等，零风险
`go1` / `zex-w` / `microduck` 的值**就是活跃模型编译出来的值**。写进契约后再回灌到
仿真（浏览器 `applyTable(frictionloss, model.dof_frictionloss)`、`scene_builder`
`joint.frictionloss`），得到的数字与模型自带的一致 → **物理不变**。

### B 组 —— ⚠️ 会改变仿真物理
`lite3` / `g1` 的活跃模型**没有声明摩擦**，而参考项目普遍声明 0.2。写入后：

* 这两个机器人的仿真里，关节**多出 0.2 的库仑摩擦**（原先为 0）；
* 行为上表现为低速/静止时更"涩"，摆动相更不易漂移。

**这是有意为之的修正**（真实机器人有摩擦，0 是"没建模"的产物），但要知道：

* `lite3` 的两个参考互相冲突（MJCF 0.2 vs URDF 0.1）——本次采用 **MJCF 的 0.2**，
  理由是我们仿真走 MJCF，且 0.2 与 go2/go1/go2w 的取法一致；
* `g1` 的参考有 0.2 / 0.3 / 0.1 三种，本次采用**官方 mjlab 系的 0.2**（多数派）；
* **若 `lite3` / `g1` 存在验收报告，结论可能变化，建议重新生成。**

### C 组 —— 幂等，但语义是"显式化"
`m20` / `tron1_pf` / `b2` / `b2w` / `wuji_hand` 模型与参考都没有关节摩擦，真值是 0。
显式写入 0 的好处是：今后"忘记声明"与"声明为 0"不再混淆，且能被测试守护。
其中 `m20` 的证据最强——参考模型里明确写着 `frictionloss="0"`。

## 4. 仍未做的（本次明确不动）

| 项 | 说明 |
|---|---|
| **静摩擦 `Fs` / 动摩擦 `Fd` / 激活速度 `Va`** | 契约里**没有字段**。参考真值在 `unitree_g1/.../unitree_actuators.py`（如 `N7520_14p3`: `Fs=1.6, Fd=0.16`），可直接取用 |
| **力矩-速度曲线 `X1/X2/Y1/Y2`** | 契约里没有字段。它决定"高速段力矩衰减"，Go2HV 等型号已有真值 |
| **传动比 `gear_ratio`** | 只在参考注释里（如 `ratio 4.5 / 48/22+1`），未入契约 |
| 接触摩擦（geom `friction`） | 属模型层，不该进契约 |

## 5. 复现方式

扫描脚本已删除，结论固化于上表。复现要点：用含 mujoco 的解释器
（`adapters/mjlab/.venv/Scripts/python.exe`）编译各包 `model/robot.xml`，
读 `model.dof_frictionloss[dof]`（关节名经 `model.dof_jntid` + `mj_id2name` 映射）。
参考值检索：在 `resources/<robot>/` 下搜 `frictionloss=`（注意 `[1-9]` 这种正则会在
`0.2` 上假阴性，要用 `frictionloss` 全量搜再筛值）。
