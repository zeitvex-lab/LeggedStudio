# RC_WheelLeg

RC_WheelLeg 是山东华宇工学院 16DOF 串联轮足机器人项目。

当前对外入口为 `main`，`16dof` 与 `16dof-rebuild` 保留同一条 16DOF 版本演进主线。机械资料、训练、MuJoCo/Sim2Sim、导航工具和三代 ROS 2 真机工程已整理至 `v1.1.1`。

## 平台概览

- 四条轮腿
- 每条腿 3 个腿部关节
- 4 个驱动轮
- 总计 16 个执行器
- 控制路线：强化学习训练、仿真验证和真机部署

## 目录结构

```text
RC_WheelLeg/
├─ 01_doc/          # 项目技术文档和使用说明
├─ 02_mechanical/   # 当前归档 CAD 和 STEP；URDF 尚待补充
├─ 03_hardware/     # 硬件资料预留入口，当前仅有范围说明
├─ 04_firmware/     # 16DOF 固件预留入口；8DOF Keil 工程见历史 Tag
├─ 05_software/     # 训练、仿真、部署和工具
├─ 06_assets/       # 图片、视频和测试结果
├─ .gitignore
└─ README.md
```

## 当前状态

- [x] 整理 SolidWorks 机械源文件
- [x] 整理整机与关节 STEP 文件
- [x] 整理第一代 mjlab 训练任务和本地依赖
- [x] 整理第一代 MuJoCo、Sim2Sim 和 MJCF
- [x] 整理 IK 真机控制与第一代 Python Sim2Real
- [x] 整理第一份新版 MJCF 与 mjlab 训练框架
- [x] 整理第二版 Sim2Real 随机化训练配置
- [x] 整理比赛最终训练代码架构
- [x] 整理后期 MuJoCo 姿态、IK、动力学和 MPC 工具
- [x] 整理后期 Sim2Sim、路线检查与比赛 Rough ONNX 策略
- [x] 整理导航地图、打点工具、路线迭代和抽样 PCD
- [x] 整理 Python Sim2Real v2、ROS 2/C++ 初版、导航原型、Odin/TensorRT 调参版与 odom 联调版
- [ ] 核对比赛机械与仿真模型参数
- [x] 整理 MJCF 机器人描述与网格
- [ ] 补充独立 URDF，并核对其与 CAD/MJCF 的参数一致性
- [x] 整理统一训练、ROS 2 和比赛版本

机械资料入口见 [`02_mechanical/README.md`](02_mechanical/README.md)。

软件版本入口见 [`05_software/README.md`](05_software/README.md)。

## 早期真机验证

[![第一代 Sim2Real 真机验证](06_assets/images/early_sim2real_preview.jpg)](06_assets/videos/early_sim2real.mp4)

第一代 Sim2Real 真机测试记录，时长约 41 秒。点击预览图播放或下载原视频。

## 比赛最终成果媒体（v1.0.1）

[![比赛最终机器人](06_assets/images/cf94fb6d9cfa01079a4f9fe082428dc.png)](06_assets/images/cf94fb6d9cfa01079a4f9fe082428dc.png)

最终比赛视频：[`06_assets/videos/比赛视频.mp4`](06_assets/videos/比赛视频.mp4)

比赛代码最初归档于 `v1.0.0`，`v1.0.1` 补充最终机器人图片和比赛视频，`v1.1.0` 进一步把最终工程明确命名为 `sim2real_ros2_v3`。Robocon 仿生足式障碍赛成绩为 1050 分、第七名（前 5%）。更多媒体说明见 [`06_assets/README.md`](06_assets/README.md)。

## 版本管理

版本里程碑与主要变化见 [`01_doc/version_history.md`](01_doc/version_history.md)。

发布前的证据边界、静态检查结果和待确认事项见 [`01_doc/release_audit.md`](01_doc/release_audit.md)。

- `8dof` 分支和 `v0.1.0` Tag 保存第一代 8DOF 实机版本。
- `main` 是当前对外版本，`16dof` 和 `16dof-rebuild` 保存并同步第二代轮足平台的完整演进。
- 同一架构内的小步迭代使用 Commit、Tag 和 Release 保存，不复制 `old`、`new` 或 `final` 目录。
- `sim2real_ros2`、`sim2real_ros2_v2`、`sim2real_ros2_v3` 是三个明确的架构大版本，不是随意复制的临时备份目录。
- 只有需要长期并行维护的不兼容路线才建立独立分支。

## 开源边界

仓库当前尚未设置覆盖自研代码的顶层许可证；Odin 驱动和本地 mjlab 各自保留上游许可证。同步到 GitHub 公共发布前，需要由权利人确定顶层许可证，并核对第三方模型、SDK 静态库和媒体文件的再分发权限。
