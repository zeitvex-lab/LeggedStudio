# Legged Studio 执行计划（EXECUTION_PLAN）

**版本**：2.0 ｜ **创建**：2026-09-08 ｜ **基线**：tag `v0.9.9`（commit 54e1c6f）
**取代**：[TASK_BACKLOG.md](TASK_BACKLOG.md)（1.0 粗略版，本版细化到可执行任务 + git 节点 + 验收命令）
**依据**：[00_Survey/10_final_vision.md](../../00_Survey/10_final_vision.md)（定稿形态）、docs/ECOSYSTEM_PLAN.md、docs/ROADMAP.md、REFERENCE_AND_RECOMMENDATIONS.md（P0-1~7 沿用）
**每个任务的统一格式**：做什么（含涉及文件）→ 完成定义（DoD）→ 验收命令 → **git 节点**（commit 信息 / tag）。

---

## 版本与 git 节点总览

| 里程碑 | git tag | 内容 |
|---|---|---|
| ✅ v0.9.9（已打） | `v0.9.9` | 现状基线：16 包/55 profiles/浏览器 Sim2Sim |
| **M1 契约 v3** | `v0.10.0` | 批次 0 全部：契约三层化 + ID 统一 + 导出双 gate + 债务清零 |
| **M2 资产检查** | `v0.11.0` | 批次 1：体检五卡 + 检查页 + 16 包迁移 |
| **M3 训练体验** | `v0.12.0` | 批次 2：奖励四层 + 分项监控/仪表盘 + 冒烟档 + SSE |
| **M4 部署向导** | `v0.13.0` | 批次 3：三步向导 + FSM/解码层模板 + 劣化档 |
| **M5 仿真扩展** | `v0.14.0` | 批次 4：场景库 + 导航与感知仿真 |
| **M6 环境与壳** | `v0.15.0` | 批次 5：L0-L6 体检 + 一键环境 + 托盘 + demo 卡 |
| **M7 生态起点** | `v0.16.0` | 批次 6：插件协议 v1 + tasks-core + RoboGauge |

每个 M 合并时打 tag（`git tag -a vX.Y.Z -m "..."`），M 内子任务用约定式 commit（`feat:`/`fix:`/`chore:`/`refactor:`）。**版本号规则**：M 内小步 0.x.Y+1，M 完成升 0.x+1.0。

---

## 批次 0：地基与偿债 → M1 `v0.10.0`

### T0.1 契约 v3 三层化 ★关键路径（3-5 天）
- [ ] 建 `contracts/schema/`：`robot-contract-3.0.schema.json`（morphology{id,legs,leg_pattern,leg_naming} / joints.actuated[{name,leg,role}] / actuator_profile{default,by_role,by_joint，含 armature} / action.reindex_from_model / observation.components[{name,width,scale,source}]）
- [ ] 同目录：`robot-package-2.0.schema.json`（+version/license/integrity/runtime_requirements）、`training-profile-1.1`、`policy-acceptance-1.1`
- [ ] `datamodel-code-generator` 生成 `contracts/generated/*_v3.py`（Pydantic）；旧 v2 模型保留兼容层（v2 输入自动升级 v3）
- [ ] `json-schema-to-typescript` → `web/shared/generated/types.d.ts`；`workbench.js` 至少 1 处改用
- [ ] `contracts/role_resolver.py`：leg_pattern×leg_naming → 逐关节展开；`robot_id` 加 pattern 校验
- **DoD**：Go2/A2/B2 用同一份 actuator_profile.by_role 展开成功且数值与现契约一致；5 契约 roundtrip 测试过
- **验收**：`python -m unittest contracts/tests/ -v` + 新增 `test_role_resolver.py` 全绿
- **git**：`feat(contracts): contract v3 with morphology/role layers + schema codegen`（2-3 个 commit：schema、codegen、resolver）

### T0.2 机器人 ID 统一 + 特判清除（1 天）
- [ ] `backend/simulation_api.py:526` 连字符集合 → 下划线；删 543/563/586 的 per-robot 分支
- [ ] `web/sim2sim/app.js:419-422` 规范化 hack 删除；`:77` DEMO_MODEL_URL、`:2408` 机身高度三元式 → 读包配置
- [ ] `GO2_BROWSER_SCENES`/`GO2_TERRAIN_ROOT`（simulation_api.py:188-196）→ 包内 `simulation/config.json` 字段
- **DoD**：`grep -rn "unitree-go2" backend web | wc -l` = 0；16 包 `GET /api/simulation/browser-config/{id}` 全 200
- **验收**：`npm test` 全绿 + 16 包 browser-config 循环脚本
- **git**：`refactor(simulation): remove per-robot branches, drive from package config`

### T0.3 导出双 gate（DENYLIST）（2 天）
- [ ] `backend/export_api.py` 加 `dummy_forward` 步骤（契约→假观测→ONNX 前向→维度比对）
- [ ] 接入 `adapters/mjlab/replay_diff.py`：导出前固定输入回放，max|Δ|<1e-5
- [ ] DENYLIST 表：`obs_groups/action_scale/joint_order/control_hz/armature` 不一致=拒绝；`reward_scales/ctrl_dt`=警告；导出响应带逐项结果
- **DoD**：人为改坏 action_scale → 导出 422 + 中文原因；Go2 正常导出通过
- **验收**：新增 `backend/test_export_gate.py`
- **git**：`feat(export): mandatory dual gate with DENYLIST fail-closed semantics`

### T0.4 工程债清扫（半天批量）
- [ ] `httpx2`→`httpx`；删 `backend/requirements.txt`；删 `web/sim2sim/models/models_go2_*.onnx` 重复
- [ ] `QUADRUPED_ASSET_INVENTORY.*` 复制入仓 `assets/inventory/`，package.json extraResources 改指仓内
- [ ] electron-builder 三配置合一（`packaging/base.js` + online/embedded 差异变量）
- [ ] workspace/imports 清理脚本 + 启动时 TTL
- **DoD**：全新 clone → `npm ci && npm run release-check && npm run build:online:win` 一次通过
- **git**：`chore: repo self-contained, deps dedupe, builder config merge`

### T0.5 卫生件测试（1 天）
- [ ] `test_registry_independence.py`：两次 load_env_cfg 返回独立实例
- [ ] run_config 增加 `contract_snapshot` 字段并断言
- [ ] pytest 配置统一（保留 unittest 兼容）
- **git**：`test: registry independence + contract snapshot`
- **M1 收口**：全测试绿 → `build:online:win` → `verify_windows_online.ps1` → commit `release: v0.10.0` → `git tag -a v0.10.0`

---

## 批次 1：资产检查页 → M2 `v0.11.0`（约 2-3 周）

### T1.1 体检五卡后端（4 天）
- [ ] `backend/asset_inspection.py`（新）：质量卡（三来源对比，>20% 警告，mesh 不闭合→"未知"）／碰撞卡（geom 覆盖率/重叠/primitive 统计，**需展开 default class 继承**——MATRiX 资产接入的教训）／惯量卡／电机参数卡（角色分组+armature+官方 diff，Lite3/M20 漂移 fixture）／关节卡
- [ ] 挂载 `GET /api/assets/{id}/inspection`
- **验收**：Go2 五卡全绿；Lite3 电机卡红标已知漂移
- **git**：`feat(assets): five-card inspection engine`

### T1.2 检查页前端（3 天）
- [ ] 资产列表分组（S/M/L×P/W+双足/人形/灵巧手）；检查页双栏（白底 3D 查看器+五卡滚动栏）；关节滑条联动 3D
- [ ] 三态徽章组件 + [生成契约 v3] 蓝主按钮；dashboard.css 面板变量收敛到浅色基线
- **验收**：对照 10 号报告线框；视觉全站浅色+蓝
- **git**：`feat(web): asset inspection page with five cards`

### T1.3 16 包迁移契约 v3（3 天）
- [ ] `tools/migrate_contract_v3.py`：自动推导角色（正则 hip/thigh/calf/wheel）+ 生成 by_role
- [ ] 人工校对异构包：go2w/b2w/m20（wheel）、zex-w、wuji_hand（gripper）、microduck（biped）
- **DoD**：迁移后 16 browser-config + 55 profiles 冒烟零回归
- **验收**：`python tools/validate_training_smoke.py`（55/55）
- **git**：`feat(assets): migrate all 16 packages to contract v3`
- **M2 收口**：`release: v0.11.0` + tag

---

## 批次 2：训练体验 → M3 `v0.12.0`（约 3 周）

### T2.1 奖励四层分组（3 天）
- [ ] `shared_rewards.py`/各包 reward_terms 加 `layer` 字段 → profile-schema 透出
- [ ] training_create 奖励 tab：四层折叠组（中文名+说明+滑条+迷你曲线）；tracking 超阈值琥珀提示
- **验收**：Go2/M20/Lite3 三包归层正确
- **git**：`feat(training): four-layer reward editor`

### T2.2 分项监控 + 健康仪表盘（5 天）
- [ ] 后端：解析训练 tensorboard event → `GET /api/training/{id}/metrics/terms`
- [ ] 前端：四层着色小倍数图 + 筛选/平滑/窗口；五大仪表盘卡（奖励/KL/熵/价值/回合长）
- [ ] 诊断卡（静态路由表 JSON：症状→按"接口→reward→PPO"排序步骤→跳转链接）
- **验收**：一次 go2 训练出 8+ 分项曲线；人为调坏触发对应卡
- **git**：`feat(monitor): per-term curves + health dashboard + symptom cards`

### T2.3 冒烟档（1 天）
- [ ] 创建表单加"冒烟档"预设（64 envs×5 iters）；冒烟绿→解锁正式训练
- **git**：`feat(training): smoke preset gate`

### T2.4 SSE（2 天）
- [ ] `/api/training/{id}/events` SSE（日志+指标）；training-common.js 改 EventSource+重连
- **验收**：日志延迟<1s；断连不白屏
- **git**：`feat(realtime): SSE for training logs/metrics`
- **M3 收口**：`release: v0.12.0` + tag

---

## 批次 3：部署向导 → M4 `v0.13.0`（约 2 周）

### T3.1 向导 UI 三步（3 天）
- 平台单选 → 双 gate 结果页（DENYLIST ✗ 时步骤 3 禁用）→ 包内容勾选+zip；策略档案页（PolicyArtifact 列表+gate 记录）
- **git**：`feat(deploy): three-step export wizard`

### T3.2 部署包内容（4 天）
- [ ] deployment-contract.yaml 生成（关节映射/频率/PD/armature/限位）
- [ ] FSM 模板：`local_tasks/.../deploy/fsm.py` 通用化（morphology 参数化，wheel 组处理）
- [ ] 动作解码层模板（槽序×reindex→电机序）
- [ ] 人工确认清单.md（增益 50%/急停/零点/软限位）
- **验收**：Go2 包过桌面 acceptance 回放；四件齐全
- **git**：`feat(deploy): contract+fsm+decoder+checklist package generation`

### T3.3 劣化参数档（1 天，可选）
- [ ] 场景/训练参数"劣化档"开关（摩擦-20%/力矩×0.8）；sim2sim 可加载
- **git**：`feat(sim): degraded-parameters hardening preset`
- **M4 收口**：`release: v0.13.0` + tag

---

## 批次 4：仿真区扩展 → M5 `v0.14.0`（约 3-4 周）

### T4.1 Sim2Sim 增强（2 天）
- HUD 健康徽章、"推一下"扰动、确定性回放面板化
- **git**：`feat(sim2sim): disturbance + deterministic replay UI`

### T4.2 场景与地图库（4 天）
- [ ] MAPS → `workspace/scenarios/*.json`（Scenario Contract 驱动）；`_scene_geoms` if-分支改读 Contract
- [ ] 场景库卡片 UI（缩略图/导入导出/Scenario 徽章）
- **验收**：新增场景 = 只写 JSON
- **git**：`feat(scenarios): scenario-contract driven map library`

### T4.3 导航与感知仿真（10 天，中期主体）
- [ ] 地图编辑器（canvas 俯视：障碍/航点）
- [ ] `backend/pathplanning.py`：A*/Dijkstra（纯 Python）
- [ ] 感知观测项第一步：heightfield 扫描（从 Go2 包抽象到共享 obs 库，双端同步：app.js+policy_acceptance）
- [ ] 导航回放+遥测条+报告（完成率/误差/碰撞/稳定性）写回 PolicyArtifact
- **验收**：Go2 velocity+heightfield 在 3 张自定义地图自动导航成功
- **git**：`feat(nav): map editor + A* + heightfield observation + nav report`
- 参考：MATRiX v1.0.13 的 unreal.xml（UE 场景→geom 样例）与 Zenoh 传感器协议文档（字段/坐标系参考，不引入运行时依赖）
- **M5 收口**：`release: v0.14.0` + tag

---

## 批次 5：环境与桌面壳 → M6 `v0.15.0`（约 2 周，可与 3-4 并行）

### T5.1 L0-L6 体检进壳（2 天）
- preflight 分级端点（L0-L3 默认/L4-L6 显式）+ 设置页体检区 UI
- **git**：`feat(launcher): L0-L6 tiered preflight`

### T5.2 一键环境（3 天）
- 离线 wheelhouse 打包脚本；Configure Runtime 进度/失败直显（联动控制台页）
- **验收**：无网机器（预下 wheelhouse）安装启动成功
- **git**：`feat(launcher): offline wheelhouse provisioning`

### T5.3 托盘+任务栏进度+退出确认（2 天）
- 训练中托盘 tooltip + 任务栏进度（Electron setProgressBar）；退出确认列运行任务
- **git**：`feat(launcher): tray progress + exit guard`

### T5.4 Dashboard demo 卡（1 天）
- 29 个预训练策略卡片网格 → 直达 sim2sim 对应回放
- **git**：`feat(web): demo policy gallery`
- **M6 收口**：`release: v0.15.0` + tag

---

## 批次 6：生态起点 → M7 `v0.16.0`（Phase 2，约 4-6 周）

### T6.1 插件协议 v1（ECOSYSTEM_PLAN E1）
- robot-package-2.0 消费（索引加 version/license/integrity）；task-pack 协议+组合解析（capability 交集）
- `scripts/ls_plugin.py validate`（manifest→contract→MJCF→entrypoint→probe→冒烟六步）；`scripts/new_robot_package.py` 脚手架
- **验收**：Solo12 假想包全绿（狗食测试）
- **git**：`feat(plugin): plugin protocol v1 + validate CLI + scaffold`

### T6.2 tasks-core 平台化（E2）
- local_tasks core/learning → 独立 uv 包 `tasks-core`；Go2/G1/microduck 改依赖方；迁移 parity 矩阵
- **验收**：三包 55 profiles 零回归
- **git**：`refactor: extract tasks-core platform library`

### T6.3 第二后端（E4）
- BackendAdapter Protocol（全 JobHandle，能力显式上收）；接 RoboGauge（py311 venv，artifact 消费侧）
- **验收**：Go2 artifact 在 RoboGauge 跑通一次评估
- **git**：`feat(backend): robogauge adapter via BackendAdapter protocol`

### T6.4 实验 lineage+对比视图（可选，方案三联动）
- lineage 落盘、实验矩阵、多 run 曲线同屏+sim2sim 录像并排
- **git**：`feat(experiments): lineage + comparison view`
- **M7 收口**：`release: v0.16.0` + tag

---

## 挂起项（有明确触发条件才做）

| 项 | 触发条件 |
|---|---|
| MATRiX 机型接入（xgb/zgws 系 8 种自研构型） | T6.1 完成后作为第三方包示范（走插件协议而非直接入 assets） |
| 在线插件市场/签名 | 第一个真实第三方贡献者出现 |
| 实机 D2+ 台架/状态估计 | 实机硬件到位 |
| MPC/WBC 运行时控制层 | RL 主线 M6 后 |
| LiDAR/SLAM 高保真（MATRiX 对接） | T4.3 导航闭环稳定后 |
| Hydra 实验矩阵 | T6.4 后批量实验成刚需 |

---

## 每批收口的标准动作（checklist）

```bash
npm test                          # 全绿
node scripts/release-check.js     # 通过
python tools/validate_training_smoke.py   # 55/55（改训练/契约链路时必跑）
npm run build:online:win          # 打包成功
powershell scripts/verify_windows_online.ps1   # 验证通过
git add -A && git commit -m "release: vX.Y.Z"
git tag -a vX.Y.Z -m "<里程碑内容>"
# 可选分发：git push origin main --tags
```

## 自动提醒任务

- 已创建 Windows 计划任务 **"LeggedStudio Daily Check"**：**每天 01:30** 运行 `scripts/daily_check.bat` → 追加一行状态到 `logs/daily_check.log`（日期时间 + 工作区是否干净 + 测试是否通过 + 最新 tag），提醒当天应推进的批次。
