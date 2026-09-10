# B5 报告：action_scale 从"标量"升级为"角色级"

> **日期**：2026-09-10 ｜ **范围**：14 个内置包的 `actuator_profile.by_role[].action_scale`

## 1. 问题：一个标量表达不了"同一台机器人不同部位"

`action.action_scale` 是**标量**，但真实档位按部位不同：

| 机型 | 腿上 | 轮上 | 差异 |
|---|---|---|---|
| `unitree_go2w` | 0.5 | **35.0** | 70× |
| `zex-w` | 0.25（横摆 0.125） | **5.0** | 20× |
| `unitree_g1` | 髋俯仰 0.55 / 膝 0.35 / 踝 0.44 | 腕俯仰·偏航 **0.07** | ~8× |

标量一旦被当成"所有关节的档位"：轮子要么几乎不转（给 0.5），要么腿被疯狂甩（给 35）。

## 2. `action_scale` 的语义（回答"改工作台有什么用"）

| 阶段 | 生效来源 |
|---|---|
| 新建训练 | **契约**（`adapters/mjlab/generic_task_builder.py` 直接读） |
| 训练中 | 同上，被 PPO 当作动作空间定义 |
| 导出 ONNX | 策略把自己训练时的值**烙进 metadata** |
| 导出检查 | `export_gate` 拿**训练时契约快照 vs 当前契约**对账，不一致**拒绝导出** |
| 部署 | 用策略自带的值 |

**所以工作台改它 ⇒ 影响下一次训练**；已导出的策略不受追溯影响；两者不一致由闸门拦下。

## 3. 证据表（不猜）

### A 组：均匀机型 —— 写入后**无行为变更**

角色内同一个值 = 该机型现有标量。依据：各包 `simulation/config.json` 的
`action_scale` / `action_scale_by_role` / `action_scale_by_joint` 均为同值。

`lite3 0.125`、`m20 0.25`、`b2 0.125`、`b2w 0.125`、`go2 0.25`、`microduck 1.0`、
`tron1_pf 0.25`、`tron1_sf 0.25`、`tron1_wf 0.25`、`go1 0.25`、`wuji_hand 0.5`

### B 组：分化机型 —— **有效档位改变**（有意）

| 机型 | 角色 → 档位 | 来源 |
|---|---|---|
| `unitree_g1` | 髋俯仰 .55 / 髋滚 .35 / 髋偏航 .55 / 膝 .35 / 踝 .44 / 肩·肘·腕滚 .44 / 腕俯仰·偏航 **.07** / 腰偏航 .55 / 腰滚·俯仰 .44 | 官方 `unitree_rl_mjlab` 部署 yaml 的 `actions.JointPositionAction.scale`（29 维数组，角色内一致） |
| `unitree_go2w` | hip/thigh/calf .5 / wheel **35.0** | 官方 `JointVelocityAction.scale = 35.0` + v2 `wheel_velocity_scale: 35.0` |
| `zex-w` | 横摆 .125 / 髋俯仰·膝 .25 / wheel **5.0** | 自家 v3 `deployment_contract.yaml` 的 scale 数组 `[0.125,0.25,0.25,…×4, 5.0×4]` + config `action_scale_by_role` |

## 4. 实现

- **数据**：14 包逐角色写入 `by_role[].action_scale`。
- **单一入口**：`contracts/role_resolver.py`
  - `RoleResolver.action_scale_by_joint()` → `{joint_name: scale}`
  - `action_scale_for_contract(contract)` → 角色内一致返回 `float`（**逐值等价旧行为**），
    分化时返回 `dict`（mjlab `BaseActionCfg.scale: float | dict[str, float]`）。
- **训练接线**：`adapters/mjlab/generic_task_builder.py` 的 `JointPositionActionCfg`
  改读 `_action_scale_for(contract)`，使角色级声明**真正生效**。
- **闸门补洞**：`backend/export_gate.py` 的 `actuator_profile` 指纹原本只取
  `mode/effort/armature/stiffness/damping`——**缺 `action_scale`**，即"改了角色档位
  可绕过导出闸门"。已补入。

## 5. 变更集合（测试锁死）

**有效 `action_scale` 相对旧标量发生变化的机型恰为 `{unitree_g1, unitree_go2w, zex-w}`**，
其余 11 个逐值等价。`ActionScaleRoleLevelB5Test` 断言该集合，新增变更必须先改证据表。

## 6. 未做（明确记录）

| 项 | 说明 |
|---|---|
| `env_factory.py` / `mujoco_env.py` 的 scale 读取 | 仍是标量；属于本地仿真/快照路径，需与 `run_config` 语义一起改 |
| 浏览器 sim2sim 载荷的 scale | `simulation_api.py` 仍传标量；前端按策略契约取，改动面在 JS 侧 |
| `go2w` 的 **5.0 vs 35.0 冲突** | `config.action_scale_by_role` 说 wheel=5.0，而官方 yaml 与 v2 契约均为 35.0。本次采 **35.0**（2 比 1 且官方 yaml 权威），**config 侧的 5.0 应视为过期值**，建议在 B2（契约单轨）里正式 reconcile |
| `g1` v2 备注失准 | v2 `action_scale_note` 写"腿 0.35 / 髋偏航 0.55 / 臂 0.44 / 腕 0.29"，但官方数组显示 **髋俯仰=0.55**（非 0.35）、**腕=0.07**（非 0.29）。v2 备注不可作为依据 |
| `tron1_wf` 的轮档位 | 现为 0.25（= config `action_scale_by_joint`）。但参考 `params.yaml` 只有 `action_scale_pos: 0.25` 且 `jointpos_idxs: [0,1,2,4,5,6]` **不含轮**，说明轮的档位另有来源、尚未找到。**待补证据** |

---

## 8. 补遗（§6 遗留项的取证结论）：轮足机型的"轮档位"是**独立的速度档位**

§6 里悬空的 `tron1_wf` 轮档位，在 `00_open` 下的三个 tron1 仓库里找到了；顺着这条线
做了一次系统性排查，发现**我们此前把腿的位置档位套到了轮上**——这是本报告最重要的一处修正。

### 8.1 统一模式：腿走位置、轮走独立速度档位

| 机型 | 腿（位置档位） | 轮（速度档位） | 来源（上游动作空间定义侧） |
|---|---|---|---|
| `limx_tron1_wf` | abad/hip/knee = 0.25 | **1.0** | tron1-rl-isaaclab `cfg/WF/limx_base_env_cfg.py`：`JointVelocityActionCfg(joint_names=["wheel_L_Joint","wheel_R_Joint"], scale=1.0, # 10)` |
| `deeprobotics_m20` | hipx **0.125** / hipy·knee 0.25 | **5.0** | `export_onnx_fast.py`：`_M20_ACTION_SCALE = [0.125,0.25,0.25]*4 + [5.0]*4`；`terrain_scene/.../m20.py`：腿用 `action_scale`、轮用 `vel_scale` |
| `unitree_b2w` | hip **0.125** / thigh·calf **0.25** | **5.0** | robot_lab `rough_env_cfg.py`：`joint_pos.scale={".*_hip_joint":0.125, "^(?!.*_hip_joint).*":0.25}`、`joint_vel.scale=5.0` |
| `zex-w` | abad **0.125** / hip_pitch·knee 0.25 | **5.0** | `LEG_POS_SCALE=0.25` / `WHEEL_VEL_SCALE=5.0`（与本仓库原值一致 ✓） |
| `unitree_go2w` | 0.5 | 35.0 | 已见 §7.4（任务相关） |

三处旁证互相印证：`tron1_wf` 的 `params.yaml` 里 `jointpos_idxs: [0,1,2,4,5,6]`
**恰好排除 3/7 号轮关节**；部署代码 `velocity_des = actions[i] * wheel_joint_damping`
走"力矩夹紧 + 速度给定"；`m20.py` 明文分两路（`position_target_offset[wheel_indices]=0`
与 `wheel_velocity_target = action * vel_scale`）。

这同时**独立确认了 B4 的两项判断**：`tron1_wf` 的 `wheel_indices=[3,7]`，
以及它 `morphology.actuator_type = "hybrid"`（训练侧确实同时使用
`JointPositionAction`（腿）+ `JointVelocityAction`（轮））。

### 8.2 修正

| 机型 | 角色 | 原值 | 修正为 |
|---|---|---|---|
| `limx_tron1_wf` | wheel | 0.25 | **1.0** |
| `deeprobotics_m20` | hipx | 0.25 | **0.125** |
| `deeprobotics_m20` | wheel | 0.25 | **5.0** |
| `unitree_b2w` | thigh / calf | 0.125 | **0.25** |
| `unitree_b2w` | wheel | 0.125 | **5.0** |

`zex-w` 无需改动（原值即正确）。变更集合随之从 `{g1, go2w, zex-w}` 扩为
`{m20, tron1_wf, b2w, g1, go2w, zex-w}`，测试表已同步。

### 8.3 独立交叉验证：mjlab 的档位是**推导出来的**

mjlab 的 asset_zoo 不硬编码档位，而是：

```python
GO1_ACTION_SCALE[n] = 0.25 * effort_limit / stiffness
```

用它反查本仓库各机型（只对 mode 为位置类且具备 effort/stiffness 的角色适用）：
**唯一吻合的是 `unitree_g1`**——声明值与推导值相差 ≤0.005（0.5475↔0.55、0.4386↔0.44、
0.0745↔0.07），差值恰为官方部署 yaml 的舍入精度。这等于用**两条完全独立的来源**
（官方 g1 部署 yaml × 本契约的 effort/stiffness）互证，已固化为
`ActionScaleRoleLevelB5Test.test_g1_declared_scale_matches_mjlab_derivation`。

其余机型不适用该式：`lite3`/`m20` 用 deeprobotics 自有约定、`tron1` 用固定
`action_scale_pos`、`b2`/`b2w` 用 robot_lab 的 `{hip:0.125, 其余:0.25}` 字面值、
`go2w` 为任务相关（§7.4）。**因此该式只能做 g1 的交叉验证，不能当通用不变量。**

### 8.4 仍未解

| 项 | 说明 |
|---|---|
| `unitree_b2`（无轮四足） | 本仓库为 0.125 均匀值；b2w 的腿档位是 `{hip:0.125, thigh/calf:0.25}`，b2 很可能同构，但**未找到 b2 侧的独立证据**，故未改 |
| `unitree_go1` | 本仓库 0.25 均匀值；mjlab 的 `GO1_ACTION_SCALE` 由该机型的 `GO1_ARTICULATION` 推导，与本契约的 effort/stiffness 不同源，推导值 0.2963 与声明值不可直接比较——**需要 go1 的 GO1_ARTICULATION 参数才能定论** |
| `mode` 字段口径 | 交叉校验显示 g1 的 `by_role.mode = "torque"`、`go2` 亦为 `"torque"`，而二者的动作项是位置控制。`mode` 到底表示"动作类型"还是"驱动器类型"需要确认；若为前者，g1/go2 的值存疑（本轮未动） |


---

## 7. B5/2：三端接线（仿真 / 训练 / 部署统一读契约）

### 7.1 发现：仿真与训练本来读的是两份数据

浏览器载荷（`backend/simulation_api.py`）**早就有比标量更细的两条查找路径**
（`action_scale_by_role` + `action_scale_by_joint`），但它读的是
`simulation/config.json`，而不是契约——即 B5 刚收敛掉的双真值在这里仍然活着，
且硬编码了 `wheel: 5.0` 兜底。

按"保留功能更多的一方"，**保留该机制（按角色 + 按关节）、把来源换成契约**。

### 7.2 落地

| 位置 | 改动 |
|---|---|
| `contracts/physics_binding.py` | 新增 `action_scale_facts()` 与 `payload_action_scale_view()`：从契约产出 `{scalar, by_role, by_joint}`，并在"非轮角色同值"时补 `leg` 组键、全同值时补 `joint` 兜底 |
| `backend/simulation_api.py` | `action_scale` / `by_role` / `by_joint` 三件套改由契约供给；删除硬编码 `wheel: 5.0` 兜底 |
| `adapters/mjlab/env_factory.py` | 两处 `action_scale` 改走 `action_scale_for_contract` |
| `adapters/mjlab/mujoco_env.py` | 步进由**标量**改为**逐关节**缩放（此前轮关节会按腿的档位缩放） |
| `contracts/training_invariants.py` | `action_scale` 不变量扩展到角色级/逐关节声明（防 0/负值漏到训练部署） |

### 7.3 为什么前端换源不会"静默回退"

前端按 **精确关节名 → 角色 → 分组 → `joint` 兜底** 多路查找，任一失配就静默用默认值
（表现为策略抽搐而非报错）。因此视图刻意同时提供角色键与逐关节键，使每条路径命中
同一数值。测试 `ActionScalePayloadViewB52Test` 守护该性质，并确认：

* `unitree_go2w`：`leg=0.5` / `wheel=35.0`，未被标量拍平；
* `zex-w`：腿内分化（横摆 0.125 / 其余 0.25）⇒ **不伪造 `leg` 组键**；
* `g1` / `go2` / `wuji_hand`：不声明 `wheel`，不误导前端。

### 7.4 go2w 轮档位：**它是任务相关参数，不是机器人常量**

| 来源 | 腿 | 轮 |
|---|---|---|
| `ppo/quadruped_joystick_rough/go2w.yaml`（UniLab） | 0.25（髋 0.125） | **5.0** |
| `sac/go2w_joystick_flat/base.yaml`（UniLab） | 0.5 | **10.0** |
| `Go2WMixedActionCfg`（UniLab 类默认，**被上游测试 `pytest.approx(10.0)` 守护**） | 0.25 | **10.0** |
| 官方 `unitree_rl_mjlab` 部署 yaml | 0.5 | **35.0** |
| 我们 `simulation/config.json` | 0.5 | **5.0** |

结论与处置：

1. **动作空间的真值归训练契约**（策略的动作空间由训练定义），仿真与部署必须服从，
   而不是各自为政——这也是 7.2 把仿真改读契约的理由；
2. **轮档位属任务/策略级**，机器人契约只给默认值，必须允许策略覆盖
   （`policies[].contract.action_scale` / `action_scale_by_joint` 已具备该能力）；
3. 本仓库当前默认采 **35.0**（我们的训练适配器是 mjlab，参考同为 `unitree_rl_mjlab`；
   且 v2 契约 `wheel_velocity_scale` 亦为 35.0）。**10.0 / 5.0 属 UniLab 栈的任务变体，
   已记录在此，供选任务时覆盖**——不建议再把某个任务值写成机器人常量。

