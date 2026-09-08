# Legged Studio 执行计划（EXECUTION_PLAN）

**版本**：2.1 ｜ **更新**：2026-09-08 ｜ **基线**：tag `v0.9.9`（commit 54e1c6f）
**取代**：[TASK_BACKLOG.md](TASK_BACKLOG.md)（1.0 粗略版）
**依据**：[00_Survey/10_final_vision.md](../../00_Survey/10_final_vision.md)（定稿形态）、docs/ECOSYSTEM_PLAN.md、docs/ROADMAP.md、REFERENCE_AND_RECOMMENDATIONS.md（P0-1~7 沿用）
**每个任务的统一格式**：做什么（含涉及文件与参考项目）→ 完成定义（DoD）→ 验收命令 → **git 节点**（commit 信息 / tag）。

> **执行方式说明**：任务不排日历时间；同一批次的任务由 agent 连续快速完成，**每批次收口时统一跑一次精简验证**（见"批次收口"），不逐任务跑全量测试。

---

## 参考项目清单（防重复造轮子，动手前先查这里）

| 需求 | 先看这些项目 | 直接可拿 |
|---|---|---|
| **地形/场景生成**（批次 4.2） | `lain_job/ArenaX`（PyQt 场地编辑器 + terrain_generator：flat/slope/stairs/noise/obstacle_mix 五种地形、11 种障碍组件参数化生成、MuJoCo XML+高度图 PNG+JSON 元数据导出、自带 tests） | `terrain_generator/`（models/scene/mujoco_xml/presets/library）可直接借鉴或移植——**不要重写地形生成器** |
| **MuJoCo 机器人模型/仿真配置**（批次 0/1 参考） | `robot_mujoco`（=MATRiX 的 robot_mujoco 模块，12 机型 jszr_robots：b2/b2w/D1/go2/go2w/h1/lite3/xg/xgb…）、`E:\Game\matrix\src\robot_mujoco`（同源）、`Downloads/MATRiX_v1.0.13`（v1.0.13 运行包+完整文档） | MJCF 写法范例（default class 按角色分层）、场景 XML（unreal.xml 的 UE→geom 导出样例）、传感器协议文档 |
| 高保真渲染/LiDAR 相机（远期） | MATRiX（Zenoh 传感器流/像素流文档） | 协议文档参考，不引入运行时依赖 |
| 契约/编排思想 | RoboLab（Recipe/PolicyArtifact）、UniLab（SimBackend/DENYLIST/owner YAML） | 报告 7 已提炼 |
| 训练 profile 范式 | LLoco（VelocityRobotProfile 差异即数据）、mjlab registry | 报告 7 已提炼 |
| 部署契约/FSM | rl_sar（双层 YAML）、microduck（publish manifest）、unitree_rl_mjlab（deploy 布局） | 报告 2/4 已提炼 |
| 资产三层数据模型 | 1000framesai（morphology+role+reindex）、StackForce（导入归一化+观测库） | 报告 6 已提炼 |
| UX 模式 | 1000framesai（demo 卡/算法 manifest）、StackForce（4 步条/映射板/错误写下一步） | 报告 3 已提炼 |
| 训练方法论/诊断 | 知识库 28 章（Ch06 奖励四层、Ch25 症状路由表） | 报告 1 已提炼 |

> 规则：批次内任务动工前，先查本表对应行；参考项目里已有实现的（如 ArenaX 地形生成），**优先移植/包装而非重写**，并在 commit 信息里注明来源项目。

---

## 版本与 git 节点总览

| 里程碑 | git tag | 内容 |
|---|---|---|
| ✅ v0.9.9（已打） | `v0.9.9` | 现状基线：16 包/55 profiles/浏览器 Sim2Sim |
| **M1 契约 v3** | `v0.10.0` | 批次 0：契约三层化 + ID 统一 + 导出双 gate + 债务清零 |
| **M2 资产检查** | `v0.11.0` | 批次 1：体检五卡 + 检查页 + 16 包迁移 |
| **M3 训练体验** | `v0.12.0` | 批次 2：奖励四层 + 分项监控/仪表盘 + 冒烟档 + SSE |
| **M4 部署向导** | `v0.13.0` | 批次 3：三步向导 + FSM/解码层模板 + 劣化档 |
| **M5 仿真扩展** | `v0.14.0` | 批次 4：场景库（ArenaX 移植）+ 导航与感知仿真 |
| **M6 环境与壳** | `v0.15.0` | 批次 5：L0-L6 体检 + 一键环境 + 托盘 + demo 卡 |
| **M7 生态起点** | `v0.16.0` | 批次 6：插件协议 v1 + tasks-core + RoboGauge |

---

## 批次 0：地基与偿债 → M1 `v0.10.0`

### T0.1 契约 v3 三层化 ★关键路径
- [ ] `contracts/schema/`：`robot-contract-3.0.schema.json`（morphology{id,legs,leg_pattern,leg_naming} / joints.actuated[{name,leg,role}] / actuator_profile{default,by_role,by_joint，含 armature} / action.reindex_from_model / observation.components[{name,width,scale,source}]）
- [ ] 同目录：`robot-package-2.0.schema.json`（+version/license/integrity/runtime_requirements）、`training-profile-1.1`、`policy-acceptance-1.1`
- [ ] `datamodel-code-generator` 生成 `contracts/generated/*_v3.py`；v2 模型保留兼容层；`json-schema-to-typescript` → `web/shared/generated/types.d.ts`（workbench.js 至少 1 处改用）
- [ ] `contracts/role_resolver.py`：leg_pattern×leg_naming 展开；`robot_id` pattern 校验
- **DoD**：Go2/A2/B2 共用一份 actuator_profile 展开成功且与现契约数值一致；roundtrip 测试过
- **git**：`feat(contracts): contract v3 with morphology/role layers + schema codegen`

### T0.2 机器人 ID 统一 + 特判清除
- [ ] `backend/simulation_api.py:526/543/563/586` 连字符集合与 per-robot 分支清除
- [ ] `web/sim2sim/app.js:419/77/2408` 规范化 hack、DEMO_MODEL_URL、机身高度三元式 → 数据驱动
- [ ] `GO2_BROWSER_SCENES`/`GO2_TERRAIN_ROOT`（simulation_api.py:188-196）→ 包配置
- **DoD**：`grep -rn "unitree-go2" backend web` = 0；16 包 browser-config 全 200
- **git**：`refactor(simulation): remove per-robot branches, drive from package config`

### T0.3 导出双 gate（DENYLIST）
- [ ] `export_api.py` 加 dummy forward；接入 `replay_diff.py`（<1e-5）
- [ ] DENYLIST：obs_groups/action_scale/joint_order/control_hz/armature 不一致=拒绝；reward_scales/ctrl_dt=警告
- **DoD**：改坏 action_scale → 导出 422+中文原因；Go2 正常导出通过
- **git**：`feat(export): mandatory dual gate with DENYLIST fail-closed semantics`

### T0.4 工程债清扫
- [ ] `httpx2`→`httpx`；删 requirements.txt；删重复 ONNX；资产清单入仓（消灭 `../` 依赖）；builder 三配置合一；workspace/imports 清理
- **DoD**：全新 clone → release-check → build:online:win 一次通过
- **git**：`chore: repo self-contained, deps dedupe, builder config merge`

### T0.5 卫生件测试
- [ ] 注册表独立实例测试；run_config 加 contract_snapshot；pytest 配置统一
- **git**：`test: registry independence + contract snapshot`

### 批次收口（M1）→ `release: v0.10.0` + `git tag -a v0.10.0`
精简验证：`npm test` 全绿 + 16 包 browser-config 全 200 + Go2 导出被坏契约正确阻断。

---

## 批次 1：资产检查页 → M2 `v0.11.0`

### T1.1 体检五卡后端
- [ ] `backend/asset_inspection.py`：质量卡（三来源对比/>20% 警告/mesh 不闭合→未知）/碰撞卡（**展开 default class 继承**——robot_mujoco/MATRiX 资产的写法）/惯量卡/电机参数卡（角色分组+armature+官方 diff，Lite3/M20 fixture）/关节卡；挂 `GET /api/assets/{id}/inspection`
- **验收**：Go2 五卡全绿；Lite3 电机卡红标已知漂移
- **git**：`feat(assets): five-card inspection engine`

### T1.2 检查页前端
- [ ] 列表分组 + 双栏检查页（白底 3D 查看器+五卡栏）+ 关节滑条联动 + 三态徽章组件；dashboard.css 收敛浅色基线
- **git**：`feat(web): asset inspection page with five cards`

### T1.3 16 包迁移契约 v3
- [ ] `tools/migrate_contract_v3.py`（角色正则推导）；人工校对 go2w/b2w/m20/zex-w/wuji_hand/microduck
- **DoD**：16 browser-config + 55 profiles 冒烟零回归
- **git**：`feat(assets): migrate all 16 packages to contract v3`

### 批次收口（M2）→ `release: v0.11.0` + tag
精简验证：`npm test` + `python tools/validate_training_smoke.py`（55/55，本批动了契约必须跑）+ 16 包 browser-config。

---

## 批次 2：训练体验 → M3 `v0.12.0`

### T2.1 奖励四层分组编辑器
- reward terms 加 layer 字段 → schema 透出；前端四层折叠组+冲突琥珀提示
- **git**：`feat(training): four-layer reward editor`

### T2.2 分项监控 + 健康仪表盘
- 解析 tensorboard event → 分项端点；四层着色小倍数图；五大仪表盘卡；中文症状路由卡（静态 JSON）
- **git**：`feat(monitor): per-term curves + health dashboard + symptom cards`

### T2.3 冒烟档
- "冒烟档"预设（64 envs×5 iters）；冒烟绿→解锁正式训练
- **git**：`feat(training): smoke preset gate`

### T2.4 SSE
- `/api/training/{id}/events`；前端 EventSource+重连
- **git**：`feat(realtime): SSE for training logs/metrics`

### 批次收口（M3）→ `release: v0.12.0` + tag
精简验证：`npm test` + 一次 go2 冒烟训练人工看分项曲线与诊断卡。

---

## 批次 3：部署向导 → M4 `v0.13.0`

### T3.1 向导 UI 三步
- 平台单选 → 双 gate 结果页（✗ 禁用步骤 3）→ 包内容勾选+zip；策略档案页
- **git**：`feat(deploy): three-step export wizard`

### T3.2 部署包内容
- deployment-contract.yaml 生成；FSM 模板（Go2 fsm.py 通用化，wheel 组处理）；动作解码层模板（槽序×reindex→电机序）；人工确认清单.md（增益 50%/急停/零点/软限位）
- **验收**：Go2 包过桌面 acceptance 回放
- **git**：`feat(deploy): contract+fsm+decoder+checklist package generation`

### T3.3 劣化参数档
- 劣化档开关（摩擦-20%/力矩×0.8）；sim2sim 可加载
- **git**：`feat(sim): degraded-parameters hardening preset`

### 批次收口（M4）→ `release: v0.13.0` + tag
精简验证：`npm test` + Go2 导出包过 acceptance 回放。

---

## 批次 4：仿真区扩展 → M5 `v0.14.0`

### T4.1 Sim2Sim 增强
- HUD 健康徽章、"推一下"扰动、确定性回放面板化
- **git**：`feat(sim2sim): disturbance + deterministic replay UI`

### T4.2 场景与地图库 ★参考 ArenaX
- [ ] **移植 `lain_job/ArenaX` 的 terrain_generator**（models/scene/mujoco_xml/presets——flat/slope/stairs/noise/obstacle_mix + 11 种参数化障碍组件已实现且带 tests），包装成本库 `backend/terrain_gen.py`，不重写
- [ ] MAPS → `workspace/scenarios/*.json`（Scenario Contract）；`_scene_geoms` if-分支改读 Contract
- [ ] 场景库卡片 UI
- **DoD**：新增场景 = 只写 JSON；ArenaX 任一预设地形可一键生成进场景库
- **git**：`feat(scenarios): scenario library ported from ArenaX terrain_generator`

### T4.3 导航与感知仿真
- 地图编辑器（canvas 俯视障碍/航点）；`backend/pathplanning.py`（A*/Dijkstra 纯 Python）；heightfield 观测项抽象（双端同步 app.js+policy_acceptance）；导航回放+遥测+报告写回 PolicyArtifact
- 参考：robot_mujoco/MATRiX 的 scene_terrain*.xml 与 unreal.xml（UE→geom 样例）
- **验收**：Go2 velocity+heightfield 在 3 张自定义地图自动导航成功
- **git**：`feat(nav): map editor + A* + heightfield observation + nav report`

### 批次收口（M5）→ `release: v0.14.0` + tag
精简验证：`npm test` + Go2 导航回放演示通过。

---

## 批次 5：环境与桌面壳 → M6 `v0.15.0`（可与 3-4 并行）

### T5.1 L0-L6 体检进壳
- preflight 分级端点（L0-L3 默认/L4-L6 显式）+ 设置页体检区
- **git**：`feat(launcher): L0-L6 tiered preflight`

### T5.2 一键环境
- 离线 wheelhouse 脚本；Configure Runtime 进度/失败直显
- **验收**：无网机器（预下 wheelhouse）安装启动成功
- **git**：`feat(launcher): offline wheelhouse provisioning`

### T5.3 托盘+任务栏进度+退出确认
- **git**：`feat(launcher): tray progress + exit guard`

### T5.4 Dashboard demo 卡
- 29 个预训练策略卡片 → 直达 sim2sim
- **git**：`feat(web): demo policy gallery`

### 批次收口（M6）→ `release: v0.15.0` + tag
精简验证：`npm test` + 无网安装演练（预下 wheelhouse）。

---

## 批次 6：生态起点 → M7 `v0.16.0`

### T6.1 插件协议 v1
- robot-package-2.0 消费；task-pack 协议+capability 交集组合；`scripts/ls_plugin.py validate` 六步校验；`scripts/new_robot_package.py` 脚手架
- **验收**：Solo12 假想包全绿（狗食测试）
- **git**：`feat(plugin): plugin protocol v1 + validate CLI + scaffold`

### T6.2 tasks-core 平台化
- local_tasks core/learning → 独立 uv 包；Go2/G1/microduck 改依赖方；迁移 parity 矩阵
- **DoD**：三包 55 profiles 零回归
- **git**：`refactor: extract tasks-core platform library`

### T6.3 第二后端
- BackendAdapter Protocol（全 JobHandle，能力显式上收）；接 RoboGauge（py311 venv）
- **验收**：Go2 artifact 在 RoboGauge 跑通一次评估
- **git**：`feat(backend): robogauge adapter via BackendAdapter protocol`

### T6.4 实验 lineage+对比视图
- lineage 落盘；实验矩阵；多 run 曲线同屏+sim2sim 录像并排
- **git**：`feat(experiments): lineage + comparison view`

### 批次收口（M7）→ `release: v0.16.0` + tag
精简验证：`npm test` + Solo12 插件包全绿 + RoboGauge 评估记录。

---

## 后续候选（本计划外，启动前另行评估）

- MATRiX 机型接入（xgb/zgws 系自研构型，走 T6.1 插件协议作示范包）
- LiDAR/SLAM 高保真感知（MATRiX 引擎对接）
- 实机 D2+ 台架/状态估计、MPC/WBC 运行时控制层
- 在线插件市场/签名、Hydra 实验矩阵
