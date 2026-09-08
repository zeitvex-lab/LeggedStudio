# Legged Studio 任务清单（Task Backlog）

**版本**：1.0 ｜ **日期**：2026-09-08
**依据**：[00_Survey/10_final_vision.md](../00_Survey/10_final_vision.md)（定稿形态）+ 当前代码实况（v0.9.9，tag `v0.9.9`）+ `REFERENCE_AND_RECOMMENDATIONS.md` 沿用任务（P0-1~7）
**用法**：每项含【现状 → 目标】与验收标准。按批次顺序执行，批内可并行。勾选框跟踪进度。

---

## 批次 0：地基与偿债（契约 + 债务清扫，约 3-4 周）

> 全部后续工作的公共前提。对应愿景"近期"段 + ROADMAP G1-G6 + 报告 6/7。

### T0.1 契约 v3：构型/角色/armature 三层化 ★最高优先
- [ ] `contracts/schema/` 新增 JSON Schema 真值源：robot-contract-3.0（morphology/roles/actuator_profile.by_role/armature/action.reindex_from_model/observation.components 带宽度+scale）、robot-package-2.0（version/license/runtime_requirements/integrity）、training-profile-1.1、policy-acceptance-1.1
- [ ] `datamodel-code-generator` 生成 Pydantic（替换手写模型，旧模型保留兼容层）；`json-schema-to-typescript` 生成 `web/shared/generated/types.d.ts`
- [ ] `robot_id` 加 `pattern="^[a-z0-9_]+$"` 强制
- [ ] 角色解析器 `role_resolver`：由 leg_pattern×leg_naming 展开逐关节数值
- **验收**：Go2/A2/B2 三个同构四足共用一份 actuator_profile 展开成功；5 契约 roundtrip 测试过；前端至少 1 处改用生成类型
- 依据：报告 6 §4.2、REFERENCE P0-1

### T0.2 机器人 ID 统一 + 特判清除
- [ ] 修 `backend/simulation_api.py:526` 连字符集合 `{unitree-go2,...}` → 下划线；逐处清除 543/563/586 分支
- [ ] 修 `web/sim2sim/app.js:419-422` 命名规范化 hack
- [ ] `GO2_BROWSER_SCENES`/`GO2_TERRAIN_ROOT`（simulation_api.py:188-196）下沉到包 `simulation/config.json`
- [ ] `app.js:77` DEMO_MODEL_URL、`app.js:2408` 机身高度三元式 → 数据驱动
- **验收**：`grep -rn "unitree-go2\|=== \"microduck\"\|=== \"zex-w\"" backend web` 零命中；16 包 browser-config 全过
- 依据：报告 6 §4.4 特判消灭表

### T0.3 导出双 gate（DENYLIST 语义）
- [ ] `dummy_forward` 检查：契约 → 假观测 → ONNX 前向 → 维度校验（go2w_sim2sim 模式）
- [ ] 接入 `adapters/mjlab/replay_diff.py` 到导出链路：固定输入数值回放，max|Δ|<1e-5
- [ ] DENYLIST 字段表（obs_groups/action_scale/joint_order/control_hz/armature 不一致=拒绝；reward_scales/ctrl_dt=警告），导出 API 返回逐项结果
- **验收**：人为改坏 action_scale → 导出被拒 + 中文原因；55 profiles 导出冒烟全过
- 依据：报告 7 §5（UniLab DENYLIST）、报告 2 §5

### T0.4 工程债清扫（机械性，1 天批量）
- [ ] `pyproject.toml` `httpx2` → `httpx`；删除 `backend/requirements.txt`（或改为生成物）
- [ ] 删除 `web/sim2sim/models/models_go2_*.onnx` 重复文件（保留一份）
- [ ] `QUADRUPED_ASSET_INVENTORY.json/md` 复制入仓 `assets/`，改 package.json extraResources 指向仓内（消灭 `../` 依赖）；electron-builder 三份配置合一（模板+变量）
- [ ] `workspace/imports/` 99 个 hex 残留：加启动清理 + TTL 策略
- **验收**：全新 clone → release-check 通过 → build:online:win 成功（仓库自包含）

### T0.5 卫生件测试
- [ ] 注册表"独立实例"测试：两次 load_env_cfg 返回独立对象（LLoco 同款）
- [ ] 训练配置内省 snapshot 测试：`contract_snapshot` 字段写入 run_config
- [ ] pytest 统一（后端 unittest 迁移或共存配置）
- **验收**：`npm test` 覆盖以上三项且全绿

---

## 批次 1：资产检查页（愿景第一步，约 2-3 周）

### T1.1 体检五卡后端
- [ ] 质量卡：三来源对比（urdf_inertial / mesh_computed / manual）已有 `mass_estimator.py`，补差异 >20% 警告阈值 + mesh 不闭合降级"未知"（fail-closed，不输出伪精确值）
- [ ] 碰撞卡：碰撞体覆盖率/重叠检测/primitive vs mesh 统计（MuJoCo 编译后 geom 枚举）
- [ ] 惯量卡：连杆惯量张量提取 + 可视化数据（现有惯量盒可视化扩展）
- [ ] 电机参数卡：按角色分组（Kp/Kd/力矩限/速度限/armature）+ **官方部署值 diff**（Lite3/M20 漂移案例做成 fixture）
- [ ] 关节卡：默认站姿/限位/关节序合法性（validator.py 扩展）
- **验收**：Go2 五卡全绿；Lite3 电机卡出现已知漂移红标
- 依据：10 号报告资产库区、报告 2 §6

### T1.2 检查页前端
- [ ] 资产列表分组 UI（S/M/L×P/W + 双足/人形/灵巧手）
- [ ] 检查页双栏布局：3D 查看器（白底，现有 urdf-viewer 分层开关保留）+ 右侧五卡滚动栏
- [ ] 底部关节滑条面板：拖动实时联动 3D 姿态
- [ ] [生成契约 v3] 蓝色主按钮 + 三态徽章系统组件
- **验收**：按 10 号报告线框还原；深浅色收敛到浅色基线（dashboard.css 面板变量迁移）

### T1.3 16 包迁移到契约 v3
- [ ] 迁移脚本：现有 contract.json + simulation/config.json → v3（角色自动推导：hip/thigh/calf/wheel 正则）
- [ ] 人工校对 3 个异构包（go2w/b2w/m20 轮足、zex-w）
- **验收**：16 包 browser-config + 55 profiles 冒烟零回归

---

## 批次 2：训练体验（约 3 周）

### T2.1 奖励四层分组编辑器
- [ ] 后端：reward terms 带 `layer` 字段（Tracking/Regularization/Style/Contact）注入 profile-schema
- [ ] 前端：训练配置页奖励 tab 改四层可折叠组，每项中文名+一句话+滑条+迷你形状曲线
- [ ] 冲突提示：tracking 总权重超阈值 → 组头琥珀提示
- **验收**：四层分组渲染正确；Go2/M20/Lite3 三包奖励项正确归层
- 依据：报告 1 §4（知识库 Ch06 四层分解）

### T2.2 分项 reward 监控 + 健康仪表盘
- [ ] 后端：解析训练 tensorboard event 文件 → 按 reward term 分项 metrics 端点（worker 已落盘 event）
- [ ] 前端：监控页分项小倍数图（按四层着色）+ 筛选/平滑/窗口控件（现有 UI 扩展）
- [ ] 五大仪表盘卡（奖励/KL/熵/价值损失/回合长度）三态判定
- [ ] 中文症状诊断卡（静态路由表：Ch25 症状→排查步骤→跳转链接）
- **验收**：跑一次 go2 velocity 训练可见 8+ 条分项曲线；人为调坏参数能触发对应诊断卡
- 依据：报告 1 §9（Ch25 路由表）

### T2.3 冒烟档按钮
- [ ] 训练创建表单加"冒烟档"预设（64 envs × 5 iters，microduck-studio smoke_argv 同款）
- [ ] 冒烟结果 → 绿灯后才解锁"正式训练"
- **验收**：冒烟档单次 <5 分钟出结果
- 依据：报告 4 §4

### T2.4 SSE 推送（替换轮询）
- [ ] 后端：训练日志/指标 SSE 端点（`/api/training/{id}/events`）
- [ ] 前端：training-common.js 轮询改 EventSource，断线重连
- **验收**：日志延迟从轮询间隔降到 <1s；断后端页面不白屏
- 依据：报告 3 §2.4、前端缺口清单

---

## 批次 3：部署向导（约 2 周）

### T3.1 部署区向导 UI（三步）
- [ ] 步骤 1 目标平台单选（Unitree SDK2/ROS2 模板/其他蓝图）
- [ ] 步骤 2 双 gate 结果页（逐项 ✅⚠❌ + DENYLIST 阻断时步骤 3 禁用）
- [ ] 步骤 3 包内容清单勾选 + zip 下载
- [ ] 策略档案页（PolicyArtifact 列表：训练元数据/obs 动作规范/评估结果/gate 记录）
- **验收**：按 10 号报告线框还原；阻断场景演示通过
- 依据：10 号报告部署区

### T3.2 部署包内容生成
- [ ] deployment-contract YAML 生成（关节映射/控制频率/PD/armature/限位）
- [ ] FSM 模板：Go2 `deploy/fsm.py` 通用化（morphology 参数化，wheel 组处理轮关节）
- [ ] 动作解码层模板：策略槽序 × reindex → SDK 电机序
- [ ] 人工确认清单 markdown（增益 50%/急停/零点/软限位四条保命经验内置）
- **验收**：Go2 导出包在桌面 acceptance 回放通过；包内四件齐全
- 依据：报告 2 §3/§6、DEEPROBOTICS_PORTING 保命清单

### T3.3 "劣化参数"加固档（可选预跑）
- [ ] 训练/仿真参数加"劣化档"开关（摩擦 -20%、力矩 ×0.8）
- [ ] sim2sim 支持加载劣化档场景
- **验收**：Go2 劣化档下 sim2sim 可运行
- 依据：报告 2 §8（CSDN 文章实战规范）

---

## 批次 4：仿真区扩展（约 3-4 周）

### T4.1 Sim2Sim 回放页改造（对齐现状→愿景）
- [ ] 现有全屏舞台保留；HUD 加策略健康检查徽章（acceptance 结果）
- [ ] "推一下"扰动按钮 + 恢复过程可视化
- [ ] 确定性回放入口 UI 化（`?replay=` 参数面板化）
- **验收**：现有功能零回归 + 三项新增可用
- 依据：10 号报告仿真区

### T4.2 场景与地图库（Scenario Contract 激活）
- [ ] scenario_maps.py 的 MAPS 迁移为 workspace/scenarios/*.json（Scenario Contract 驱动）
- [ ] 场景库 UI：卡片网格 + 缩略图 + 导入导出
- [ ] `_scene_geoms` 的 if-map_id 分支改为读 Contract geom 列表
- **验收**：新增一个自定义场景 = 只写 JSON 不改代码
- 依据：10 号报告场景库、问题 1 的场景特判

### T4.3 导航与任务仿真（外部感知，中期主体）
- [ ] 地图编辑器：障碍绘制/航点设置（canvas 2D 俯视图起步）
- [ ] A*/Dijkstra 路径规划模块（纯 Python，无重依赖）
- [ ] 感知观测项抽象第一步：heightfield 扫描观测项（从 Go2 包抽象到共享库）
- [ ] 导航回放：策略沿航点走完 + 遥测条 + 导航报告（完成率/误差/碰撞/稳定性）写回 PolicyArtifact
- **验收**：Go2 velocity 策略 + 高度场观测在 3 个自定义地图自动导航成功
- 依据：10 号报告导航子区、navigation_api 现有航点回放扩展

---

## 批次 5：环境与桌面壳（约 2 周，可与批次 2-3 并行）

### T5.1 L0-L6 体检进桌面壳设置页
- [ ] 后端：preflight 分级端点（L0-L3 默认执行，L4-L6 显式触发）
- [ ] 壳设置页体检区 UI（每层 ✅⚠❌ + 展开原因）
- **验收**：干净机器体检 10 秒内完成 L0-L3
- 依据：10 号报告桌面壳、报告 1 §9

### T5.2 一键环境收尾
- [ ] 离线 wheelhouse 打包脚本（国内镜像固定）
- [ ] Configure Runtime 安装进度/失败原因直显（控制台页联动）
- **验收**：无网机器（预下载 wheelhouse）完成安装启动
- 依据：REFERENCE 8.3 验收门

### T5.3 托盘与任务栏进度
- [ ] 训练运行中：托盘 tooltip + Windows 任务栏进度条（electron ProgressBar API）
- [ ] 退出确认框列出运行中任务
- **验收**：训练中关窗口 → 确认框出现 → 取消后训练继续
- 依据：10 号报告桌面壳

### T5.4 Dashboard demo 卡
- [ ] workbench 首页 demo 卡网格：29 个预训练策略按机器人分组，点击直达 sim2sim 对应回放
- **验收**：未训练新用户 3 次点击内看到机器狗跑动
- 依据：报告 3 §2.1

---

## 批次 6：插件化与多后端（Phase 2，视前面进度启动）

### T6.1 插件协议 v1（ECOSYSTEM_PLAN E1 精简版）
- [ ] robot-package-2.0 manifest 消费（version/license/integrity 字段进索引）
- [ ] task-pack 目录协议 + 组合解析（robot∩task capability 交集）
- [ ] `scripts/ls_plugin.py validate` 校验 CLI（manifest→contract→MJCF→entrypoint→probe→冒烟六步）
- [ ] `scripts/new_robot_package.py` 脚手架
- **验收**：用脚手架做一个 Solo12 假想包全绿
- 依据：ECOSYSTEM_PLAN E1、报告 7 §5

### T6.2 local_tasks → tasks-core 平台化（E2）
- [ ] core/learning 层抽独立 uv 包（spec/PolicyContract/Catalog/symmetry/distill）
- [ ] Go2/G1/microduck 改为依赖方；迁移 parity 矩阵
- **验收**：三包 55 profiles 零回归；tasks-core 独立测试绿
- 依据：ECOSYSTEM_PLAN E2

### T6.3 第二后端 adapter（E4）
- [ ] BackendAdapter Protocol（list_tasks/launch_train/launch_export/launch_sim2sim，全返回 JobHandle）
- [ ] 先接 RoboGauge（artifact 消费侧，py311 独立 venv）
- **验收**：Go2 artifact 在 RoboGauge 跑通一次评估
- 依据：ECOSYSTEM_PLAN E4、报告 7 UniLab 两原则

### T6.4 实验 lineage 与对比视图（方案三联动，可选）
- [ ] ExperimentSpec 补 lineage 落盘；实验矩阵（robot×task×seed）
- [ ] 多 run 曲线同屏 + sim2sim 录像并排对比
- **验收**：3 seed 结论一键复现
- 依据：报告 1 §10、报告 3 §2.9 空白点

---

## 挂起项（明确不做/待触发）

| 项 | 触发条件 |
|---|---|
| 在线插件市场/签名体系 | 出现第一个真实第三方贡献者 |
| 实机 D2+ 台架工具/状态估计 | 有实机硬件到位 |
| MPC/WBC 运行时控制层 | RL 主线闭环后的第二支柱 |
| LiDAR/SLAM 高保真感知 | 导航闭环稳定后 |
| 方案 C Hydra 实验矩阵 | T6.4 完成且批量实验成刚需 |

---

## 执行纪律（沿用既有文化）

1. 每批结束跑 `npm test` + `node scripts/release-check.js` + 55 profiles 冒烟（改训练链路时）
2. 每项能力落地必须有证据（测试/冒烟脚本/可复现命令），文档能力分级同步（已验证/已内化/规划中）
3. 涉及 16 包/契约的改动必须过 T1.3 零回归验收
4. 批次 0 未完成前不启动批次 6（插件协议对着未地基化的契约设计必返工）

**当前起点建议**：T0.1（契约 v3 Schema）——它解锁 T0.2/T1.1/T3.2，是全图的关键路径。
