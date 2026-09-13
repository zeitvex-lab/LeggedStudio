# 关节摩擦：引擎/训练侧对照（源码级）

> **日期**：2026-09-10 ｜ **目的**：回答"大部分模型没摩擦，训练是怎么做的"
> **证据**：MuJoCo **3.11.0**（`adapters/mjlab/.venv`）+ 已安装 mjlab 源码 + `00_resources/` 参考项目

## 0. 结论先说

**官方管线不依赖关节摩擦。** mjlab 的 velocity 基类任务里**没有**关节摩擦随机化事件，
摩擦随机化只落在**足端接触**（`geom_friction`），打滑由奖励惩罚（`foot_slip = -0.1`）。
所以"参考模型不写 `frictionloss`"在这个生态里是**可以接受的默认**，不会导致训练失败。

## 1. 引擎侧：0 与"留空"完全等价，且 0 = "这一项不存在"

MuJoCo 3.11.0 `src/engine/engine_core_constraint.c`：

```c
static int mj_instantiateFriction(const mjModel* m, mjData* d, int count_only, int* nnz) {
  // disabled: return
  if (mjDISABLED(mjDSBL_FRICTIONLOSS)) {
    return 0;
  }
  for (int i=0; i < nv; i++) {
    // no friction loss: skip
    if (!m->dof_frictionloss[i]) {
      continue;
    }
    mj_addConstraint(m, d, jac, 0, 0, m->dof_frictionloss[i],
                     1, mjCNSTR_FRICTION_DOF, i, ...);
```

- 默认值来自 `mjs_defaultJoint`（=0），编译时原样搬运：`m->dof_frictionloss[dofadr] = pj->frictionloss;`
- **`0` 直接 `continue`** → 该 DOF 不生成任何摩擦约束 → 引擎层面**看不出"留空"与"给 0"的区别**
- 实测印证：本仓库 7 个包模型未写 `frictionloss`，编译后 `dof_frictionloss` 全为 `0.0`

**`frictionloss` 是约束不是力矩**：上下界 `±dof_frictionloss`，求解参数走 `dof_solref`/`dof_solimp`
（`mjspec.h` 里为 `solref_friction`/`solimp_friction`）；`mj_makeImpedance` 对摩擦类**强制 K=0**；
`mj_diagApprox` 用 `dof_invweight0` 归一。**所以"给 0.2"≠"精确减 0.2 N·m"**，
实际表现还取决于约束软硬。

不对称点（源码如此）：**DOF 侧判据是 `!frictionloss`（负值也会生成约束），tendon 侧是 `> 0`**。

## 2. mjlab 侧："留空"与"给 0"**不**等价

`mjlab/utils/spec.py`：

```python
def apply_target_overrides(spec, target_name, transmission_type, *,
                           armature: float | None, frictionloss: float | None,
                           viscous_damping: float | None) -> None:
  """Apply joint- or tendon-level overrides. ``None`` preserves the XML value."""
  ...
  if frictionloss is not None:
    target.frictionloss = frictionloss
```

| 输入 | 行为 | 编译后 |
|---|---|---|
| 留空 / `None` | 不碰，继承模型 XML | XML 有值 → 用 XML；没写 → 0 |
| 显式 `0.0` | 强制清零 | 抹掉 XML 里可能有的摩擦 |
| 显式非零 | 覆盖 | 该值 |

**"留空"= 不表态听模型的；"给 0"= 明确要求没有摩擦。** 引擎看不出，覆盖层看得出。

## 3. 训练侧：官方只随机化**接触**摩擦

`mjlab/tasks/velocity/velocity_env_cfg.py`（基类）的 `events` 段唯一摩擦项：

```python
"foot_friction": EventTermCfg(
  mode="startup",
  func=dr.geom_friction,          # ← 接触摩擦，不是 dof_frictionloss
  params={
    "asset_cfg": SceneEntityCfg("robot", geom_names=()),   # 逐机器人覆盖
    "operation": "abs",
    "ranges": (0.3, 1.2),
    "shared_random": True,        # 所有足端 geom 共享同一摩擦
  },
),
```

配套奖励：`foot_slip` 权重 `-0.1`、`foot_clearance` `-2.0`、`foot_swing_height` `-0.25`。
**即：打滑用"接触摩擦 + 足端奖励"处理，不用关节摩擦。**

## 4. 关节摩擦 DR 存在，但官方没挂

`mjlab/envs/mdp/dr/joint.py`：

```python
@requires_model_fields("dof_frictionloss")
def joint_friction(env, env_ids, ranges, asset_cfg=..., distribution="uniform",
                   operation: Operation | str = "abs", axes=None, shared_random=False) -> None:
  """Randomize joint friction loss (dof_frictionloss)."""
dof_frictionloss = joint_friction   # raw alias
```

`operation` 的三种语义（`mjlab/envs/mdp/dr/_types.py`，**决定"名义 0 能否被救"**）：

| operation | `combine(base, random)` | 名义值 = 0 时 | 能否弥补"模型没写摩擦" |
|---|---|---|---|
| `abs`（**默认**） | `random`（忽略 base） | 结果 = 随机值 | ✅ **能** |
| `add` | `base + random` | 结果 = 随机值 | ✅ 能 |
| `scale` | `base × random`（`uses_defaults=True`） | **0 × 任意 = 0** | ❌ **永远救不回来** |

> ⚠️ **`scale` 陷阱**：若对"名义值为 0"的模型挂 `scale` 型 `joint_friction`，
> 会得到**零摩擦训练且不报错**。修"缺摩擦"必须用 `abs` 或 `add`。

## 5. 参考项目的实际用法

| 项目 | 做法 | 含义 |
|---|---|---|
| 官方 mjlab velocity（基类） | 仅 `geom_friction` `abs (0.3,1.2)` | **不管关节摩擦** |
| `zex-w` RC 任务 | `dr.joint_friction`, `scale (0.7,1.3)` | 名义 0.01 上做比例扰动 |
| `zex-w` 另一变体 | `cfg.events.pop("joint_friction", None)` | **显式取消**该事件 |
| `unitree_rl_lab`（IsaacLab 版） | `randomize_rigid_body_material`, `static/dynamic_friction_range=(0.3,1.2)` | 也是**接触**摩擦 |
| `lain_job/LLoco` | 把 `dof_frictionloss / dof_armature / dof_damping / restitution` 作为 **DR 标签**送 critic | 摩擦当"环境参数"用 |

LLoco 这一条说明：在这些项目里，摩擦是**域随机化的一个维度**，策略学到的是
"对摩擦变化不敏感"，而不是"摩擦值取得对不对"。

## 6. 本仓库 14 包：谁缺摩擦

编译值为 0 的 **7 个**（细节与来源见 [`B3_friction_loss_补齐报告.md`](./B3_friction_loss_补齐报告.md)）：

| 包 | 活跃模型 | 参考项目 | 处置 |
|---|---|---|---|
| `deeprobotics_lite3` | 0 | MJCF 参考 0.2 | 已补 0.2 |
| `unitree_g1` | 0 | 多数参考 0.2 | 已补 0.2 |
| `deeprobotics_m20` | 0 | `M20_Piper.xml` **显式 0** | 写 0.0 |
| `limx_tron1_pf` | 0 | 无 | 写 0.0 |
| `unitree_b2` | 0 | 无 | 写 0.0 |
| `unitree_b2w` | 0 | 无 | 写 0.0 |
| `wuji_hand` | 0 | 无 | 写 0.0 |

另外已填非零：`go2`/`go2w` 0.2、`go1` 0.2、`zex-w` 0.01、`microduck` 0.0048、
`tron1_sf`/`tron1_wf` ankle/wheel 0.01（其余 0）。

## 7. 对本仓库的含义

1. **给 5 个包写 `0.0` 与官方做法一致**——官方本就不给关节摩擦做任何处理，缺了不会训练失败。
2. **`scale` 陷阱要写成守卫**：若将来给"名义 0"的包挂 `scale` 型 `joint_friction` DR，
   须报错（或在文档中显式记录"只有 `abs`/`add` 能覆盖缺失的名义值"）。
3. **lite3/g1 补 0.2 的影响面比最初估计小**：官方管线不会因它改变 DR（不 DR 关节摩擦），
   受影响的是**仿真物理本身**（sim2sim、接触密集行为），以及既有验收报告。
4. **"要不要让关节摩擦被 DR 覆盖"是训练配方决策，不是契约决策**：若要，应在
   机器人包的 env cfg 里加 `dr.joint_friction(operation="abs", ranges=(0.0, 0.2))`，
   而不是继续改契约数据。
