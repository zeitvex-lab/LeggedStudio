# Changelog

本文件记录 Legged Studio 各版本的重大变更。遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式，版本号以 `VERSION` 文件为准。

## [0.17.0] - 2026-09-09

### 新增功能

- **工作台形态重构**：左侧六功能区（资产库/训练/监控/仿真/部署/设置）+ 顶部工作流进度条，首页 Dashboard 内置 demo 卡与「下一步建议」（PR #3）
- **设置区**：后端 settings API + 设置页，支持 GPU/CPU profile 切换与重装、后端端口、Python 覆盖、包镜像源、工作区清理（PR #2）
- **训练观测/动作映射板**：标准观测库（带宽度+scale）→ 策略输入槽位，维度自动校验，专家模式 dot-path（PR #2）
- **交互式导航地图编辑器**：画障碍/设航点 → A*/Dijkstra 自动求路，可保存（PR #2）
- **感知观测项通用抽象**：足端接触 → 高度场 → 深度相机（PIE 106×60），`backend/perception_observations.py`（PR #2）
- **导航评估写回策略档案**：路径完成率/跟踪误差/碰撞/稳定性写入 PolicyArtifact（PR #4）
- **部署目标平台模板实例化**：Unitree SDK2 / ROS2 按平台生成真实接口骨架（PR #5）
- **导航感知-决策闭环**：地图障碍 A*/Dijkstra 自动规划 + 反应式避障势场 `nav_avoidance.py`，评估指标写回（PR #13）
- **GPU 长训练回归基线**：`validate_training_smoke.py` 新增 `--mode longtrain` 档（默认 iters=2000）与 `--baseline` 退化判定（PR #14）

### 改进与重构

- **契约 v2/v3 收敛 loader**：`contracts/contract_loader.py` 统一加载 v3 语义权威字段 + v2 补齐数据（PR #9）
- **控制面边界收紧**：`export_api` 顶层 torch import 链懒加载化，控制面顶层无训练栈依赖（PR #6）
- **仓库自包含**：`QUADRUPED_ASSET_INVENTORY.json` 纳入 repo，`inventory.py` 降级兜底（PR #7）
- **app.js 观测注册表化**：`OBSERVATION_BUILDERS` 注册表 dispatch 替代 21 连 if（PR #8）
- **观测构造器拆独立模块**：`web/sim2sim/obs/observation_builders.js`，纯 Node 单测（PR #16）
- **sys.path 统一收敛**：`contracts/path_bootstrap.py` 单一真值源 + `native_worker._ensure_on_path` helper（PR #15、#17）
- **训练框架能力边界声明**：UI 诚实标注「可用/未接入」状态（PR #11）
- **版本元数据对齐**：`pyproject.toml`/`backend/version.py` 统一到 0.17.0（PR #12）

### 文档

- 全面更新 `PRODUCT_VISION` / `ARCHITECTURE` / `WEB_APP` / `DESKTOP_APP` / `ROBOT_PACKAGE` 至 0.17.0 真实状态（PR #10）

---

## [0.16.0] - 2026-09-06

### 新增功能

- **插件协议 ls_plugin v1**：validator CLI + scaffold + catalog（`scripts/ls_plugin.py`）
- **工作区包裹完整性守卫**：`workspace/packages` 副本 integrity guard
- **桌面版本号跟随真值源**：清除历史 0.6.1 残留，版本随 `VERSION` 文件

### 主要变更

- 完成 16 个机器人包全量迁移至契约 v3（`contract_v3.json`），以 `contracts/schema/robot-contract-3.0.schema.json` 为唯一真值源
- 资产检查五卡（质量/碰撞/惯量/电机/关节）与导入→契约 v3 闭环（PR 已合）
- 训练监控四层奖励分组 + 健康仪表盘（奖励/KL/熵/价值损失/回合长度）+ 中文症状诊断卡
- 部署双 gate（DENYLIST fail-closed + dummy shape + 数值 <1e-5）
- 浏览器 sim2sim 移除 per-robot 硬编码特判，改为契约 v3 + 包配置数据驱动

---

## [0.15.0] - 2026-08-29

### 新增功能

- **桌面启动器 L0-L6 分层体检**：GPU→框架→任务注册→场景→zero/random agent→最小训练
- **内置 demo 卡**：29 个预训练策略免训练即玩
- **托盘/taskbar 进度**与退出守卫
- **sim2sim 推挤扰动按钮**（T4.3 交互扰动）

---

## [0.14.0] - 2026-08-22

### 新增功能

- **ArenaX 地形生成器移植**：`terrain_api` + 场景库 API + 路线规划器
- **部署包生成器**：`deploy_pack.py` + 三步向导 + 劣化参数预设
- **策略档案端点**：PolicyArtifact 摘要面板（`deploy/artifact`）

---

## [0.13.0] - 2026-08-15

### 新增功能

- **模块化训练资源包**：盲走/模仿/感知三线分类 + 包卡片
- **监控分项曲线四层分组** + 健康仪表盘组件 + 中文症状诊断卡 UI

---

## [0.12.0] - 2026-08-08

### 新增功能

- **训练冒烟档**：先 64 envs 冒烟再长训（smoke preset gate）
- **SSE 实时事件流**：训练进度实时推送
- **奖励四层分组注册表** + 每项曲线 + 健康仪表盘 + 症状卡

---

## [0.11.0] - 2026-08-01

### 新增功能

- **资产检查五卡引擎**：质量/碰撞/惯量/电机/关节多来源对比
- **契约 v3**：morphology/role/reindex 三层语义 + schema codegen
- **导出双 gate**：DENYLIST fail-closed 语义（`export_gate.py`）

### 主要变更

- 16 机器人全量契约 v3 迁移 + 浏览器/前端驱动从契约 v3 + 包配置读取
- 浏览器 sim2sim per-robot 分支移除，数据驱动

---

## [0.10.0] - 2026-07-25

### 新增功能

- **G1 动作库扩展至 60 clips** + Go2 PIE 深度感知 parkour（106×60 深度相机）
- **全量训练配置验证**：54/54 profiles 通过
- **MJCF 标准化**：lite3/a1 官方 mesh 重建（视觉/碰撞分离）、TRON1 碰撞体校准、d1/go2 足端碰撞球补齐

### 主要变更

- 外部训练源（LLoco/AMP/Instinct/wuji-mjlab/unitree_rl_mjlab）全部内化为包内本地任务库
- 16 机器人浏览器场景路径/mesh 一致性修复
- sim2sim 场景路径/env 真实渲染修复

---

## [0.9.0] - 2026-07-18

### 主要变更

- 大规模重构：数据模型迁移至契约 v3、资产五卡体系建立、js/API 边界梳理
- 机器人包全量规范（16 包 / 55 profiles）
- 文档体系建立（docs/: PRODUCT_VISION / ARCHITECTURE / WEB_APP / DESKTOP_APP / ROBOT_PACKAGE）

---

## 早期版本

- 0.8.x 及更早：项目初始化、MVP（Go2 + MJLab/PPO + MuJoCo 交互评估）、Web 工作台雏形、Electron 桌面壳。
