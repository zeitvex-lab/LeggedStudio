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
