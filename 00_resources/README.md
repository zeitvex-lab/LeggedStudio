# 00_resources/ — 参考资源整合库（以「项目」为单位）

> **组织方式**：一个来源项目 = 一个目录 `00_resources/<project>/`，**原样保留该项目的目录结构与组织思想**。
> 项目内有用的内容（源码 / 配置 / 文档 / 数据 / **推理策略 onnx·pt·engine**）完整拷贝；
> 网格、CAD、二进制、媒体、归档、日志与超大的无用文件不拷贝，但在**原目录**留下 `_OMITTED.md`
> 占位登记（文件名 / 体积 / 类型 / 源路径）——真要用到时按登记的源路径回到 `00_open/` 取用，结构不丢。
>
> - 规范：[`_SPEC.md`](./_SPEC.md)　｜　机器可读索引：[`_index.json`](./_index.json)
> - 通用知识库（非机型专属）：[`knowledge_base/`](./knowledge_base/)
> - 与 `assets/robots/` 的关系：本目录是**只读参考底座**（原始素材取证，保留来源项目路径与全部变体），
>   `assets/robots/<id>/` 是**归一化后的可执行资产包**（按 contract v3 收敛为单一事实源）。
>   **禁止**把 `00_resources/` 内容直接当作运行时资产加载。

## 总览

- 收录项目 **89** 个　·　文件 **52817** 个　·　体积 **1712.3 MB**
- 省略文件 **22067** 个（**15656.9 MB**），均在原目录留有 `_OMITTED.md` 占位登记
- 通用知识库 **1** 个　·　文件 436 个
- 生成时间：2026-09-23 00:18

## 项目清单（有什么 · 能帮什么 · 关联哪些机器人）

| 项目 | 收录 | 省略 | 体积 | 策略 | 关联机型 | 索引 |
|---|---:|---:|---:|---:|---|---|
| `urdf_tool` | 8999 | 2581 | 116.3 MB | 0 | — | [README](./urdf_tool/README.md) |
| `sdk_deploy` | 8006 | 4460 | 74.1 MB | 2 | `deeprobotics_lite3`、`deeprobotics_m20` | [README](./sdk_deploy/README.md) |
| `wandb` | 7425 | 20 | 88.6 MB | 0 | — | [README](./wandb/README.md) |
| `Link-U-OS` | 4085 | 684 | 22.6 MB | 3 | — | [README](./Link-U-OS/README.md) |
| `PaddleX` | 2957 | 0 | 20.7 MB | 0 | — | [README](./PaddleX/README.md) |
| `g1-mujoco-ros2-nav-sim-G1-MuJoCo-ROS2-` | 2197 | 966 | 69.8 MB | 3 | `unitree_g1` | [README](./g1-mujoco-ros2-nav-sim-G1-MuJoCo-ROS2-/README.md) |
| `unilab_new` | 1131 | 21 | 7.9 MB | 0 | `unitree_go2`、`unitree_go2w`、`unitree_go1`、`unitree_g1`、`microduck`、`deeprobotics_m20`、`deeprobotics_lite3` | [README](./unilab_new/README.md) |
| `microduck_all` | 980 | 832 | 63.7 MB | 55 | `microduck` | [README](./microduck_all/README.md) |
| `lain_job` | 961 | 626 | 47.5 MB | 4 | `unitree_go2`、`unitree_go1`、`unitree_g1`、`deeprobotics_m20` | [README](./lain_job/README.md) |
| `newton` | 961 | 189 | 24.9 MB | 1 | — | [README](./newton/README.md) |
| `rc_old` | 952 | 223 | 40.2 MB | 18 | `zex-w`、`unitree_go1`、`unitree_g1` | [README](./rc_old/README.md) |
| `uni_rl` | 781 | 1573 | 31.9 MB | 5 | `unitree_go2`、`unitree_go2w`、`unitree_go1`、`unitree_b2`、`unitree_b2w`、`unitree_g1` | [README](./uni_rl/README.md) |
| `habitat-sim` | 745 | 167 | 37.9 MB | 0 | `unitree_go2`、`limx_tron1_pf`、`limx_tron1_sf`、`limx_tron1_wf` | [README](./habitat-sim/README.md) |
| `genesis-world` | 707 | 348 | 12.2 MB | 0 | — | [README](./genesis-world/README.md) |
| `MGDP` | 573 | 794 | 117.5 MB | 8 | `unitree_go1`、`unitree_go2`、`deeprobotics_lite3` | [README](./MGDP/README.md) |
| `robosuite_new` | 535 | 806 | 10.2 MB | 0 | `wuji_hand`、`unitree_g1` | [README](./robosuite_new/README.md) |
| `Gymnasium` | 457 | 255 | 2.7 MB | 0 | `unitree_go1`、`unitree_go2`、`unitree_go2w`、`unitree_b2`、`unitree_b2w`、`unitree_g1`、`deeprobotics_lite3`、`deeprobotics_m20`、`limx_tron1_pf`、`limx_tron1_sf`、`limx_tron1_wf`、`microduck`、`wuji_hand`、`zex-w` | [README](./Gymnasium/README.md) |
| `robo_know` | 437 | 1 | 46.3 MB | 0 | — | [README](./robo_know/README.md) |
| `mjlab_new` | 407 | 106 | 3.8 MB | 0 | `unitree_go1`、`unitree_go2`、`unitree_go2w`、`unitree_g1` | [README](./mjlab_new/README.md) |
| `unitree_rl_mjlab` | 402 | 393 | 22.3 MB | 2 | `unitree_go2`、`unitree_go2w`、`unitree_g1` | [README](./unitree_rl_mjlab/README.md) |
| `unitree_rl_mjlab_go2w` | 383 | 180 | 18.4 MB | 3 | `unitree_go2w`、`unitree_go2`、`unitree_g1` | [README](./unitree_rl_mjlab_go2w/README.md) |
| `mjswan` | 379 | 91 | 22.6 MB | 11 | `unitree_go2`、`unitree_go1`、`unitree_g1` | [README](./mjswan/README.md) |
| `robot_lab` | 368 | 539 | 3.2 MB | 0 | `unitree_go1`、`unitree_go2`、`unitree_go2w`、`unitree_b2`、`unitree_b2w`、`unitree_g1`、`deeprobotics_lite3`、`deeprobotics_m20` | [README](./robot_lab/README.md) |
| `taggy` | 329 | 0 | 2.4 MB | 0 | `unitree_go2` | [README](./taggy/README.md) |
| `fan_robotlab` | 307 | 539 | 3.0 MB | 0 | `unitree_go1`、`unitree_go2`、`unitree_go2w`、`unitree_b2`、`unitree_b2w`、`unitree_g1`、`deeprobotics_lite3`、`deeprobotics_m20` | [README](./fan_robotlab/README.md) |
| `gym_ex` | 306 | 148 | 16.2 MB | 0 | `unitree_go2`、`unitree_go1`、`unitree_g1`、`limx_tron1_pf`、`limx_tron1_sf` | [README](./gym_ex/README.md) |
| `LeggedGym-Ex` | 305 | 148 | 16.2 MB | 0 | `unitree_go2`、`unitree_go1`、`unitree_g1`、`limx_tron1_pf`、`limx_tron1_sf` | [README](./LeggedGym-Ex/README.md) |
| `LainLab` | 295 | 303 | 49.1 MB | 8 | `unitree_go2`、`unitree_g1` | [README](./LainLab/README.md) |
| `26Raicom` | 287 | 12 | 12.7 MB | 2 | `unitree_go2` | [README](./26Raicom/README.md) |
| `kaiwu_rl` | 279 | 49 | 16.5 MB | 4 | `unitree_go2`、`unitree_g1` | [README](./kaiwu_rl/README.md) |
| `genesislab` | 276 | 2 | 1.1 MB | 0 | `unitree_go2`、`unitree_g1` | [README](./genesislab/README.md) |
| `mujoco_playground` | 243 | 53 | 6.7 MB | 6 | `unitree_go1`、`unitree_g1` | [README](./mujoco_playground/README.md) |
| `InstinctMJ` | 220 | 85 | 1.9 MB | 0 | `unitree_g1` | [README](./InstinctMJ/README.md) |
| `him_dog` | 209 | 161 | 28.1 MB | 15 | `unitree_go1`、`unitree_go2` | [README](./him_dog/README.md) |
| `Gymnasium-Robotics` | 199 | 181 | 1.2 MB | 0 | `wuji_hand` | [README](./Gymnasium-Robotics/README.md) |
| `engineai_rl_workspace` | 196 | 92 | 1.4 MB | 1 | — | [README](./engineai_rl_workspace/README.md) |
| `wuji-mjlab` | 186 | 61 | 1.1 MB | 0 | `wuji_hand` | [README](./wuji-mjlab/README.md) |
| `LightNav-0` | 182 | 9 | 1.3 MB | 0 | `unitree_go2` | [README](./LightNav-0/README.md) |
| `robot-descriptions-quadruped` | 180 | 65 | 11.8 MB | 8 | `unitree_go1`、`unitree_go2`、`unitree_b2`、`unitree_b2w`、`deeprobotics_lite3`、`deeprobotics_m20` | [README](./robot-descriptions-quadruped/README.md) |
| `microduck_rl` | 175 | 55 | 1.7 MB | 0 | `microduck` | [README](./microduck_rl/README.md) |
| `rl_sar` | 170 | 0 | 30.2 MB | 22 | `unitree_go2`、`unitree_go2w`、`unitree_b2`、`unitree_b2w`、`unitree_g1`、`deeprobotics_lite3` | [README](./rl_sar/README.md) |
| `rl_sar_zoo` | 170 | 416 | 1.5 MB | 0 | `unitree_go2`、`unitree_go2w`、`unitree_b2`、`unitree_b2w`、`unitree_g1`、`deeprobotics_lite3` | [README](./rl_sar_zoo/README.md) |
| `fan_rlsar` | 165 | 0 | 22.0 MB | 16 | `unitree_go2`、`unitree_go2w`、`unitree_b2`、`unitree_b2w`、`unitree_g1`、`deeprobotics_lite3` | [README](./fan_rlsar/README.md) |
| `LeggedSkillDeploy` | 158 | 232 | 43.5 MB | 31 | `unitree_go2`、`unitree_go2w`、`unitree_go1`、`unitree_g1`、`deeprobotics_m20` | [README](./LeggedSkillDeploy/README.md) |
| `wbc-mjlab` | 156 | 42 | 59.6 MB | 1 | `unitree_g1` | [README](./wbc-mjlab/README.md) |
| `mujoco_ros2_control` | 155 | 9 | 1.1 MB | 0 | — | [README](./mujoco_ros2_control/README.md) |
| `UFO` | 154 | 39 | 1.1 MB | 0 | `unitree_g1` | [README](./UFO/README.md) |
| `robo_re` | 154 | 1393 | 99.9 MB | 0 | `unitree_g1` | [README](./robo_re/README.md) |
| `AMP_mjlab` | 134 | 39 | 23.5 MB | 0 | `unitree_g1` | [README](./AMP_mjlab/README.md) |
| `go2w_sim2sim` | 134 | 95 | 103.0 MB | 35 | `unitree_go2w` | [README](./go2w_sim2sim/README.md) |
| `deep_rl` | 133 | 3 | 38.1 MB | 0 | `deeprobotics_lite3`、`deeprobotics_m20` | [README](./deep_rl/README.md) |
| `rl_training` | 132 | 3 | 38.1 MB | 0 | `deeprobotics_lite3`、`deeprobotics_m20` | [README](./rl_training/README.md) |
| `go2_rl_robotlab` | 103 | 27 | 12.8 MB | 2 | `unitree_go2` | [README](./go2_rl_robotlab/README.md) |
| `Odin-Nav-Stack` | 99 | 3 | 14.6 MB | 1 | `unitree_go2` | [README](./Odin-Nav-Stack/README.md) |
| `tron1-robot-description` | 98 | 127 | 710 KB | 0 | `limx_tron1_pf`、`limx_tron1_sf`、`limx_tron1_wf` | [README](./tron1-robot-description/README.md) |
| `walk-these-ways` | 95 | 28 | 581 KB | 1 | `unitree_go1` | [README](./walk-these-ways/README.md) |
| `limxsdk-lowlevel` | 90 | 12 | 388 KB | 0 | `limx_tron1_pf`、`limx_tron1_sf`、`limx_tron1_wf` | [README](./limxsdk-lowlevel/README.md) |
| `go2_rl_gym` | 81 | 29 | 625 KB | 0 | `unitree_go2` | [README](./go2_rl_gym/README.md) |
| `m20_rl_isaacsim` | 80 | 76 | 3.6 MB | 4 | `deeprobotics_m20`、`deeprobotics_lite3` | [README](./m20_rl_isaacsim/README.md) |
| `robot_mujoco` | 79 | 368 | 1.9 MB | 0 | `unitree_go1`、`unitree_go2`、`unitree_go2w`、`unitree_b2`、`unitree_b2w`、`unitree_g1`、`deeprobotics_lite3` | [README](./robot_mujoco/README.md) |
| `tron1-rl-isaaclab` | 79 | 12 | 300 KB | 0 | `limx_tron1_pf`、`limx_tron1_sf`、`limx_tron1_wf` | [README](./tron1-rl-isaaclab/README.md) |
| `tron1-rl-deploy-ros2` | 78 | 1 | 23.4 MB | 40 | `limx_tron1_pf`、`limx_tron1_sf`、`limx_tron1_wf` | [README](./tron1-rl-deploy-ros2/README.md) |
| `tron1-rl-deploy-python` | 75 | 1 | 31.4 MB | 54 | `limx_tron1_pf`、`limx_tron1_sf`、`limx_tron1_wf` | [README](./tron1-rl-deploy-python/README.md) |
| `HIMLoco` | 72 | 92 | 11.2 MB | 0 | `unitree_go1` | [README](./HIMLoco/README.md) |
| `jie_3d_nav` | 68 | 5 | 2.0 MB | 0 | — | [README](./jie_3d_nav/README.md) |
| `1000framesai.com` | 66 | 40 | 6.6 MB | 1 | `unitree_go2` | [README](./1000framesai.com/README.md) |
| `parkour_mjlab` | 64 | 88 | 32.6 MB | 5 | `unitree_go2`、`unitree_g1` | [README](./parkour_mjlab/README.md) |
| `sim.stackforce.cc` | 64 | 168 | 3.9 MB | 0 | `unitree_go2` | [README](./sim.stackforce.cc/README.md) |
| `go2_unitree_ros2` | 61 | 0 | 835 KB | 0 | `unitree_go2` | [README](./go2_unitree_ros2/README.md) |
| `references_1000framesai` | 58 | 34 | 7.4 MB | 1 | `unitree_go2` | [README](./references_1000framesai/README.md) |
| `microduck-simulator` | 57 | 147 | 7.4 MB | 9 | `microduck` | [README](./microduck-simulator/README.md) |
| `Dreamwaq` | 50 | 64 | 538 KB | 0 | `unitree_go2`、`deeprobotics_m20` | [README](./Dreamwaq/README.md) |
| `unitree-go2-slam-nav2` | 49 | 0 | 119 KB | 0 | `unitree_go2` | [README](./unitree-go2-slam-nav2/README.md) |
| `humanoid-motion-planning` | 48 | 48 | 441 KB | 0 | `unitree_g1` | [README](./humanoid-motion-planning/README.md) |
| `matrix_zsibot` | 46 | 0 | 770 KB | 0 | `unitree_go2`、`unitree_go2w`、`unitree_g1` | [README](./matrix_zsibot/README.md) |
| `legged_gym` | 41 | 73 | 313 KB | 1 | — | [README](./legged_gym/README.md) |
| `legged_sim` | 38 | 9 | 103 KB | 0 | `unitree_g1` | [README](./legged_sim/README.md) |
| `mjlab-skillkit` | 37 | 0 | 161 KB | 0 | — | [README](./mjlab-skillkit/README.md) |
| `unitree_go2_nav` | 37 | 17 | 174 KB | 0 | `unitree_go2` | [README](./unitree_go2_nav/README.md) |
| `humanoid-gym` | 33 | 89 | 2.4 MB | 1 | — | [README](./humanoid-gym/README.md) |
| `unitree_go2_edu_movement` | 31 | 0 | 475 KB | 0 | `unitree_go2` | [README](./unitree_go2_edu_movement/README.md) |
| `zsi_rl` | 28 | 38 | 87 KB | 0 | `unitree_go2` | [README](./zsi_rl/README.md) |
| `microduck-studio` | 26 | 2 | 71 KB | 0 | `microduck` | [README](./microduck-studio/README.md) |
| `deep_robotics_model` | 18 | 299 | 339 KB | 0 | `deeprobotics_lite3`、`deeprobotics_m20` | [README](./deep_robotics_model/README.md) |
| `tdt-nav-kit` | 18 | 6 | 246 KB | 0 | `unitree_go2`、`limx_tron1_pf`、`limx_tron1_sf`、`limx_tron1_wf` | [README](./tdt-nav-kit/README.md) |
| `g1-manipulation-challenge` | 13 | 49 | 3.6 MB | 4 | `unitree_g1` | [README](./g1-manipulation-challenge/README.md) |
| `unitree_mujoco` | 10 | 20 | 140 KB | 0 | `unitree_go1`、`unitree_go2`、`unitree_g1` | [README](./unitree_mujoco/README.md) |
| `g1_spinkick_example` | 8 | 3 | 1.2 MB | 1 | `unitree_g1` | [README](./g1_spinkick_example/README.md) |
| `robot-joystick` | 2 | 3 | 11 KB | 0 | `limx_tron1_pf`、`limx_tron1_sf`、`limx_tron1_wf` | [README](./robot-joystick/README.md) |

## 项目定位说明

- **`1000framesai.com`**：1000frames.ai 站点镜像资源
- **`26Raicom`**：2026 睿抗（RAICOM）多模态巡检赛道全国一等奖代码：8 阶段全流程——PID 黑线循迹 + 白线触发前跳、三路 TOF 迷宫五阶段状态机、IMU 俯仰闭环上/下台阶、D1 七自由度机械臂 DLS 逆运动学抓取（D435i 红圆 + 深度）、YOLO+ORB+模板兜底标志识别；含赛规 PDF、场地立体图与硬件健壮性方案（看门狗 / 热插拔 / USB 带宽）
- **`AMP_mjlab`**：AMP 动作先验训练（mjlab，G1）
- **`Dreamwaq`**：DreamWaQ 盲式运动控制实现
- **`Gymnasium`**：Farama RL 环境标准 API（Env/Space/Wrapper/Vector）——训练适配器协议与环境接口设计参考
- **`Gymnasium-Robotics`**：Farama Gymnasium-Robotics：基于 MuJoCo 的机器人环境集合（Fetch / Shadow 灵巧手 / Adroit / Franka Kitchen / MaMuJoCo / D4RL Maze）；含多目标 GoalEnv API（observation / achieved_goal / desired_goal）与 92 触点触觉观测——灵巧手操作任务、目标条件观测与迷宫导航场景参考
- **`HIMLoco`**：InternRobotics HIMLoco：四足高动态运动/越障 RL 训练工程（legged_gym + rsl_rl）
- **`InstinctMJ`**：InstinctMJ：G1 人形 mjlab 工程
- **`LainLab`**：LainLab：mjlab 1.6 多厂商资产/任务/部署层（go2 skills 全套 + OpenDoge 自研；Apache-2.0）
- **`LeggedGym-Ex`**：legged_gym 扩展版：多机型训练环境与任务
- **`LeggedSkillDeploy`**：多机型技能部署包（策略 + 部署配置）
- **`LightNav-0`**：LightNav 视觉导航（Qwen3-VL 系）
- **`Link-U-OS`**：Link-U OS（智元/灵犀具身智能 OS 开源版，GitHub: Link-U-OS/Link-U-OS）：面向具身智能的操作系统栈——AimRT 通信中间件（RPC/Topic，Protobuf 与 ROS2 消息双格式）、Bazel 多仓构建与 x86_64→aarch64 一键交叉编译、Docker 开发环境、AimStudio 图形化部署工具，以及基于 MuJoCo/Isaac Gym 的人形站立·行走 RL 训练-仿真验证-实机部署全链；本目录同时收下 `.gitmodules` 点名的 13 个外链子仓（rl_training / rl_deploy / aimrt / aimrt_comm / aimrt_sensor / aimrt_protocol / aimrt_viz / aimrt_process_manager / aimrt_health_monitor / aimrt_prebuilt / rules_ros2 / integration / AimStudio）
- **`MGDP`**：MGDP：通用深度感知四足运动控制（IsaacGym + Warp 深度传感器，跨机型迁移）
- **`Odin-Nav-Stack`**：Odin1 深度相机 + NeuPAN 局部规划的导航栈
- **`PaddleX`**：PaddleX 3.x：飞桨低代码视觉工具链（200+ 预训练模型 / 33 条模型产线 / 39 个单功能模块），覆盖目标检测、开集检测、语义与实例分割、关键点、OCR 与文档解析；含高性能推理、服务化与端侧部署——B 类外挂感知（目标判定 / 标志识别 / 视觉触发）与「模型产线」资源组织形态参考
- **`UFO`**：UFO：G1 人形工程
- **`deep_rl`**：云深处 RL 训练工程
- **`deep_robotics_model`**：云深处机型模型与描述文件
- **`engineai_rl_workspace`**：EngineAI RL Workspace（深圳众擎机器人；GitHub 上可访问的快照为 MeredithRowe/engineai_rl_workspace 的 community 分支，上游 engineai-robotics/engineai_rl_workspace 已不可公开访问）：通用腿足 RL 框架（engineai_gym 环境 / engineai_rl 算法·网络·runner / engineai_rl_workspace 实验与脚本 / engineai_rl_lib 参考状态），训练与播放共用一套 runner 逻辑、run 记录与代码快照可复现、.pt→.onnx/.mnn 格式转换；含 PM01/SA01 双足与 quadruped 资产、actuator_nets 执行器网络
- **`fan_rlsar`**：RL-SAR 的个人分支（多机型实验）
- **`fan_robotlab`**：robot_lab 的个人分支（多机型实验）
- **`g1-manipulation-challenge`**：G1 操作挑战赛工程
- **`g1-mujoco-ros2-nav-sim-G1-MuJoCo-ROS2-`**：G1 MuJoCo + ROS2 导航仿真
- **`g1_spinkick_example`**：G1 回旋踢示例（mjlab）
- **`genesis-world`**：Genesis World：Python 原生多物理仿真平台（统一多物理引擎 + Nyx 渲染 + Quadrants 编译）；URDF / MJCF / OBJ / GLB / USD 资产解析、并行与异构环境、相机与传感器、可微物理——第三物理引擎候选，与传感器/场景/可微训练参考
- **`genesislab`**：GenesisLab：基于 Genesis 物理引擎的轻量腿足 RL 任务套件（RSL-RL / rl_games 集成）；envs / managers / components / engine 模块化分层，含 Go2 速度跟踪任务与 imitation tracking——第二训练后端（Genesis）候选与「任务套件如何与引擎解耦」的参考
- **`go2_rl_gym`**：Go2 的 legged_gym + rsl_rl 训练/回放工程（IsaacGym 系）
- **`go2_rl_robotlab`**：基于 robot_lab 的 Go2 训练工程（IsaacLab）
- **`go2_unitree_ros2`**：Unitree SDK2 的 ROS2 封装参考：低层 /lowcmd（200Hz + CRC32）与 Sport API /api/sport/request 双通道、运动/关节状态与手柄读取、IMU 发布
- **`go2w_sim2sim`**：Go2W 轮足 sim2sim 部署工程（MuJoCo）
- **`gym_ex`**：legged_gym 系实验工程（多机型）
- **`habitat-sim`**：Meta habitat-sim 具身 AI 仿真引擎（C++：nav PathFinder/相机+鱼眼传感器栈/场景元数据）——H 组高级仿真、导航与传感器参考
- **`him_dog`**：him_dog 四足工程
- **`humanoid-gym`**：roboterax/humanoid-gym：人形（XBot-L）RL 训练 + Sim2Real 工程（`humanoid/` 下的 envs / algorithms / scripts 与 reward、terrain 组织、参考动作）；EngineAI RL Workspace 自述其 reward 与 terrain 生成部分受该库启发 ⇒ 人形任务的奖励/地形写法对照源
- **`humanoid-motion-planning`**：人形运动规划算法
- **`jie_3d_nav`**：JIE 3D 导航栈（jie_octomap + octo_planner）：感知与规划参考
- **`kaiwu_rl`**：开悟 RL 工程（Go2/G1）
- **`lain_job`**：LLoco 技能式 RL 任务与部署（多机型）
- **`legged_gym`**：leggedrobotics/legged_gym：腿足 RL 训练的**上游范式**（`legged_robot` / `legged_robot_config` / `_get_envs` 任务注册 / `terrain` 生成 / MDP 组织），本库多个训练工程 （go2_rl_gym / LeggedGym-Ex / gym_ex / HIMLoco / EngineAI RL Workspace …）的共同祖先 —— 用于回答"某个写法/约定是哪来的"，并与各分支做差异对照
- **`legged_sim`**：G1 仿真环境与场景
- **`limxsdk-lowlevel`**：limxdynamics 官方低层 SDK（limxsdk：硬件接口/消息定义）
- **`m20_rl_isaacsim`**：M20 轮足 IsaacSim RL 工程
- **`matrix_zsibot`**：ZsiBot MATRiX 仿真平台源码快照的实现类子集（UE5 + MuJoCo + CARLA）：传感器声明、自定义/拼接场景、多机器人端口、相机与渲染协议、实景扫描 3DGS→PLY→MuJoCo proxy 流水线、G1 材质桥
- **`microduck-simulator`**：MicroDuck 仿真器
- **`microduck-studio`**：MicroDuck Studio（编辑/可视化）
- **`microduck_all`**：MicroDuck 综合工程
- **`microduck_rl`**：MicroDuck RL 训练
- **`mjlab-skillkit`**：mjlab 技能包（adapters / agents / shared）：Isaac Lab → mjlab 移植参考
- **`mjlab_new`**：mjlab 新版：机型资产 + MuJoCo RL 任务
- **`mjswan`**：mjlab 可视化/仿真套件
- **`mujoco_playground`**：DeepMind MuJoCo Playground：Go1/G1 环境与策略
- **`mujoco_ros2_control`**：ros2_control × MuJoCo 系统接口：SystemInterface 插件 + MJCF/URDF 自动转换 + 插件体系 + 3D LiDAR 扩展；让同一套 ros2_control 控制器在仿真与真机间切换——部署侧控制器接口形态、MJCF/URDF 转换与 LiDAR 传感器参考
- **`newton`**：Newton（Linux Foundation；Disney Research / Google DeepMind / NVIDIA 发起）：NVIDIA Warp 之上的 GPU 可微物理引擎，以 MuJoCo Warp 为首要后端；含 solver 抽象、执行器与控制器、IMU / 接触 / tiled_camera / raytrace 传感器、USD 解析与确定性测试——物理后端抽象、传感器建模与跨引擎一致性校验的上游参考
- **`parkour_mjlab`**：Go2/G1 的 parkour 任务（mjlab）：Go2 PIE 深度跑酷训练 + sim2sim + 发布策略
- **`rc_old`**：ZEX-W 轮足旧版工程（含 Go1/G1 分支）
- **`references_1000framesai`**：1000frames.ai 参考素材（机型描述/示例）
- **`rl_sar`**：RL-SAR：仿真到实机部署框架（多机型、含策略与 C++ 部署）
- **`rl_sar_zoo`**：RL-SAR 机型 zoo：URDF/MJCF 与策略集合
- **`rl_training`**：云深处 RL 训练任务与配置
- **`robo_know`**：Robotics Tutorial 知识库：28 章 RL 运控教程（观测/动作/奖励/算法/仿真/部署全链，含 mjlab+Isaac Lab 双框架对比）
- **`robo_re`**：G1 人形 RL 工程
- **`robosuite_new`**：robosuite：MuJoCo 操作仿真框架（arenas/robots/objects/tasks 模块化 MJCF 组合 + OSC 控制器 + 遥操作）——wuji 灵巧手操作任务与资源组合模型参考
- **`robot-descriptions-quadruped`**：四足机型描述汇总（URDF/xacro/MJCF）
- **`robot-joystick`**：limxdynamics 官方摇杆上位机（预编译，命令源参考）
- **`robot_lab`**：robot_lab：IsaacLab 版多机型训练框架
- **`robot_mujoco`**：多机型 MuJoCo 资产与场景
- **`sdk_deploy`**：云深处 SDK 与部署代码
- **`sim.stackforce.cc`**：stackforce 仿真站点参考资源
- **`taggy`**：Go2 的 ROS2 bringup / 控制 / Gazebo 仿真（Taggy 巡逻机器人原型）：/cmd_vel↔Sport 桥接、unitree_go 与 unitree_api 消息定义、D435i 传感器 launch 与 Gazebo 世界
- **`tdt-nav-kit`**：TDT 二维栅格导航算法组件（A*/Kinodynamic A* 前端 + Minimum-Snap/OSQP 轨迹后端，C++）——H 组导航规划参考
- **`tron1-rl-deploy-python`**：TRON1 Python 部署与策略文件
- **`tron1-rl-deploy-ros2`**：limxdynamics TRON1 RL 部署（ROS2 controller + hw，含 gazebo sim 与 gym/lab 双关节序参数表）
- **`tron1-rl-isaaclab`**：TRON1 IsaacLab RL 训练工程
- **`tron1-robot-description`**：TRON1 机型描述（URDF/xacro）
- **`uni_rl`**：多机型统一 RL 训练框架（宇树全系）
- **`unilab_new`**：统一多机型 RL 实验框架（训练/评估/部署）
- **`unitree-go2-slam-nav2`**：Go2 的 SLAM + Nav2 导航栈（ROS2）
- **`unitree_go2_edu_movement`**：Go2 EDU 视觉对接流水线（unitree_sdk2py）：AprilTag 位姿解算 + 滑窗滤波 + 梯形速度规划 + 三模式停靠判据，含前视鱼眼内参与 DDS 收发范式
- **`unitree_go2_nav`**：Go2 导航相关脚本与配置
- **`unitree_mujoco`**：宇树官方 MuJoCo 仿真器与机型 XML（Go1/Go2/G1）
- **`unitree_rl_mjlab`**：宇树官方 mjlab 版 RL 工程：训练任务 + MuJoCo 部署（Go2/Go2W/G1）
- **`unitree_rl_mjlab_go2w`**：Go2W 专用 mjlab RL 工程（含 Go2/G1 资产）
- **`urdf_tool`**：URDF 资产查看与验证工具集（robot_viewer / URDF-Studio）
- **`walk-these-ways`**：Improbable AI walk-these-ways：Go1 快速步态 RL 训练与部署（go1_gym / go1_gym_deploy）
- **`wandb`**：Weights & Biases 客户端（Go core + Python SDK）：训练任务跟踪与可视化参考
- **`wbc-mjlab`**：WBC-Mjlab：mjlab 全身运动跟踪（WBC）共享 MDP，一策略多技能；含 G1 任务/动作库/导出
- **`wuji-mjlab`**：无极灵巧手 mjlab 训练工程
- **`zsi_rl`**：Go2 的 RL 示例工程

## 机型 → 项目反查

- **unitree_go1**（宇树 Go1 四足）：[`unitree_mujoco`](./unitree_mujoco/README.md)、[`LeggedGym-Ex`](./LeggedGym-Ex/README.md)、[`gym_ex`](./gym_ex/README.md)、[`mjlab_new`](./mjlab_new/README.md)、[`unilab_new`](./unilab_new/README.md)、[`uni_rl`](./uni_rl/README.md)、[`lain_job`](./lain_job/README.md)、[`mjswan`](./mjswan/README.md)、[`mujoco_playground`](./mujoco_playground/README.md)、[`MGDP`](./MGDP/README.md)、[`LeggedSkillDeploy`](./LeggedSkillDeploy/README.md)、[`robot_lab`](./robot_lab/README.md)、[`fan_robotlab`](./fan_robotlab/README.md)、[`robot_mujoco`](./robot_mujoco/README.md)、[`robot-descriptions-quadruped`](./robot-descriptions-quadruped/README.md)、[`him_dog`](./him_dog/README.md)、[`HIMLoco`](./HIMLoco/README.md)、[`walk-these-ways`](./walk-these-ways/README.md)、[`Gymnasium`](./Gymnasium/README.md)、[`rc_old`](./rc_old/README.md)
- **unitree_go2**（宇树 Go2 四足）：[`go2_rl_gym`](./go2_rl_gym/README.md)、[`go2_rl_robotlab`](./go2_rl_robotlab/README.md)、[`unitree-go2-slam-nav2`](./unitree-go2-slam-nav2/README.md)、[`unitree_go2_nav`](./unitree_go2_nav/README.md)、[`references_1000framesai`](./references_1000framesai/README.md)、[`1000framesai.com`](./1000framesai.com/README.md)、[`sim.stackforce.cc`](./sim.stackforce.cc/README.md)、[`Odin-Nav-Stack`](./Odin-Nav-Stack/README.md)、[`LightNav-0`](./LightNav-0/README.md)、[`zsi_rl`](./zsi_rl/README.md)、[`unitree_rl_mjlab`](./unitree_rl_mjlab/README.md)、[`unitree_rl_mjlab_go2w`](./unitree_rl_mjlab_go2w/README.md)、[`unitree_mujoco`](./unitree_mujoco/README.md)、[`LeggedGym-Ex`](./LeggedGym-Ex/README.md)、[`gym_ex`](./gym_ex/README.md)、[`mjlab_new`](./mjlab_new/README.md)、[`unilab_new`](./unilab_new/README.md)、[`uni_rl`](./uni_rl/README.md)、[`lain_job`](./lain_job/README.md)、[`LainLab`](./LainLab/README.md)、[`kaiwu_rl`](./kaiwu_rl/README.md)、[`mjswan`](./mjswan/README.md)、[`parkour_mjlab`](./parkour_mjlab/README.md)、[`MGDP`](./MGDP/README.md)、[`Dreamwaq`](./Dreamwaq/README.md)、[`LeggedSkillDeploy`](./LeggedSkillDeploy/README.md)、[`robot_lab`](./robot_lab/README.md)、[`fan_robotlab`](./fan_robotlab/README.md)、[`rl_sar`](./rl_sar/README.md)、[`rl_sar_zoo`](./rl_sar_zoo/README.md)、[`fan_rlsar`](./fan_rlsar/README.md)、[`robot_mujoco`](./robot_mujoco/README.md)、[`robot-descriptions-quadruped`](./robot-descriptions-quadruped/README.md)、[`him_dog`](./him_dog/README.md)、[`tdt-nav-kit`](./tdt-nav-kit/README.md)、[`Gymnasium`](./Gymnasium/README.md)、[`habitat-sim`](./habitat-sim/README.md)、[`26Raicom`](./26Raicom/README.md)、[`go2_unitree_ros2`](./go2_unitree_ros2/README.md)、[`taggy`](./taggy/README.md)、[`unitree_go2_edu_movement`](./unitree_go2_edu_movement/README.md)、[`matrix_zsibot`](./matrix_zsibot/README.md)、[`genesislab`](./genesislab/README.md)
- **unitree_go2w**（宇树 Go2W 轮足）：[`go2w_sim2sim`](./go2w_sim2sim/README.md)、[`unitree_rl_mjlab`](./unitree_rl_mjlab/README.md)、[`unitree_rl_mjlab_go2w`](./unitree_rl_mjlab_go2w/README.md)、[`mjlab_new`](./mjlab_new/README.md)、[`unilab_new`](./unilab_new/README.md)、[`uni_rl`](./uni_rl/README.md)、[`LeggedSkillDeploy`](./LeggedSkillDeploy/README.md)、[`robot_lab`](./robot_lab/README.md)、[`fan_robotlab`](./fan_robotlab/README.md)、[`rl_sar`](./rl_sar/README.md)、[`rl_sar_zoo`](./rl_sar_zoo/README.md)、[`fan_rlsar`](./fan_rlsar/README.md)、[`robot_mujoco`](./robot_mujoco/README.md)、[`Gymnasium`](./Gymnasium/README.md)、[`matrix_zsibot`](./matrix_zsibot/README.md)
- **unitree_b2**（宇树 B2 四足）：[`uni_rl`](./uni_rl/README.md)、[`robot_lab`](./robot_lab/README.md)、[`fan_robotlab`](./fan_robotlab/README.md)、[`rl_sar`](./rl_sar/README.md)、[`rl_sar_zoo`](./rl_sar_zoo/README.md)、[`fan_rlsar`](./fan_rlsar/README.md)、[`robot_mujoco`](./robot_mujoco/README.md)、[`robot-descriptions-quadruped`](./robot-descriptions-quadruped/README.md)、[`Gymnasium`](./Gymnasium/README.md)
- **unitree_b2w**（宇树 B2W 轮足）：[`uni_rl`](./uni_rl/README.md)、[`robot_lab`](./robot_lab/README.md)、[`fan_robotlab`](./fan_robotlab/README.md)、[`rl_sar`](./rl_sar/README.md)、[`rl_sar_zoo`](./rl_sar_zoo/README.md)、[`fan_rlsar`](./fan_rlsar/README.md)、[`robot_mujoco`](./robot_mujoco/README.md)、[`robot-descriptions-quadruped`](./robot-descriptions-quadruped/README.md)、[`Gymnasium`](./Gymnasium/README.md)
- **unitree_g1**（宇树 G1 人形）：[`unitree_rl_mjlab`](./unitree_rl_mjlab/README.md)、[`unitree_rl_mjlab_go2w`](./unitree_rl_mjlab_go2w/README.md)、[`unitree_mujoco`](./unitree_mujoco/README.md)、[`LeggedGym-Ex`](./LeggedGym-Ex/README.md)、[`gym_ex`](./gym_ex/README.md)、[`mjlab_new`](./mjlab_new/README.md)、[`unilab_new`](./unilab_new/README.md)、[`uni_rl`](./uni_rl/README.md)、[`lain_job`](./lain_job/README.md)、[`LainLab`](./LainLab/README.md)、[`kaiwu_rl`](./kaiwu_rl/README.md)、[`mjswan`](./mjswan/README.md)、[`mujoco_playground`](./mujoco_playground/README.md)、[`parkour_mjlab`](./parkour_mjlab/README.md)、[`LeggedSkillDeploy`](./LeggedSkillDeploy/README.md)、[`robot_lab`](./robot_lab/README.md)、[`fan_robotlab`](./fan_robotlab/README.md)、[`rl_sar`](./rl_sar/README.md)、[`rl_sar_zoo`](./rl_sar_zoo/README.md)、[`fan_rlsar`](./fan_rlsar/README.md)、[`robot_mujoco`](./robot_mujoco/README.md)、[`robo_re`](./robo_re/README.md)、[`InstinctMJ`](./InstinctMJ/README.md)、[`AMP_mjlab`](./AMP_mjlab/README.md)、[`humanoid-motion-planning`](./humanoid-motion-planning/README.md)、[`legged_sim`](./legged_sim/README.md)、[`g1-manipulation-challenge`](./g1-manipulation-challenge/README.md)、[`UFO`](./UFO/README.md)、[`g1-mujoco-ros2-nav-sim-G1-MuJoCo-ROS2-`](./g1-mujoco-ros2-nav-sim-G1-MuJoCo-ROS2-/README.md)、[`g1_spinkick_example`](./g1_spinkick_example/README.md)、[`wbc-mjlab`](./wbc-mjlab/README.md)、[`Gymnasium`](./Gymnasium/README.md)、[`robosuite_new`](./robosuite_new/README.md)、[`rc_old`](./rc_old/README.md)、[`matrix_zsibot`](./matrix_zsibot/README.md)、[`genesislab`](./genesislab/README.md)
- **deeprobotics_lite3**（云深处 Lite3 四足）：[`unilab_new`](./unilab_new/README.md)、[`MGDP`](./MGDP/README.md)、[`robot_lab`](./robot_lab/README.md)、[`fan_robotlab`](./fan_robotlab/README.md)、[`rl_sar`](./rl_sar/README.md)、[`rl_sar_zoo`](./rl_sar_zoo/README.md)、[`fan_rlsar`](./fan_rlsar/README.md)、[`robot_mujoco`](./robot_mujoco/README.md)、[`robot-descriptions-quadruped`](./robot-descriptions-quadruped/README.md)、[`sdk_deploy`](./sdk_deploy/README.md)、[`deep_robotics_model`](./deep_robotics_model/README.md)、[`deep_rl`](./deep_rl/README.md)、[`rl_training`](./rl_training/README.md)、[`m20_rl_isaacsim`](./m20_rl_isaacsim/README.md)、[`Gymnasium`](./Gymnasium/README.md)
- **deeprobotics_m20**（云深处 M20 轮足）：[`unilab_new`](./unilab_new/README.md)、[`lain_job`](./lain_job/README.md)、[`Dreamwaq`](./Dreamwaq/README.md)、[`LeggedSkillDeploy`](./LeggedSkillDeploy/README.md)、[`robot_lab`](./robot_lab/README.md)、[`fan_robotlab`](./fan_robotlab/README.md)、[`robot-descriptions-quadruped`](./robot-descriptions-quadruped/README.md)、[`sdk_deploy`](./sdk_deploy/README.md)、[`deep_robotics_model`](./deep_robotics_model/README.md)、[`deep_rl`](./deep_rl/README.md)、[`rl_training`](./rl_training/README.md)、[`m20_rl_isaacsim`](./m20_rl_isaacsim/README.md)、[`Gymnasium`](./Gymnasium/README.md)
- **limx_tron1_pf**（逐际动力 TRON1-PF）：[`LeggedGym-Ex`](./LeggedGym-Ex/README.md)、[`gym_ex`](./gym_ex/README.md)、[`tron1-robot-description`](./tron1-robot-description/README.md)、[`tron1-rl-isaaclab`](./tron1-rl-isaaclab/README.md)、[`tron1-rl-deploy-python`](./tron1-rl-deploy-python/README.md)、[`tron1-rl-deploy-ros2`](./tron1-rl-deploy-ros2/README.md)、[`limxsdk-lowlevel`](./limxsdk-lowlevel/README.md)、[`robot-joystick`](./robot-joystick/README.md)、[`tdt-nav-kit`](./tdt-nav-kit/README.md)、[`Gymnasium`](./Gymnasium/README.md)、[`habitat-sim`](./habitat-sim/README.md)
- **limx_tron1_sf**（逐际动力 TRON1-SF）：[`LeggedGym-Ex`](./LeggedGym-Ex/README.md)、[`gym_ex`](./gym_ex/README.md)、[`tron1-robot-description`](./tron1-robot-description/README.md)、[`tron1-rl-isaaclab`](./tron1-rl-isaaclab/README.md)、[`tron1-rl-deploy-python`](./tron1-rl-deploy-python/README.md)、[`tron1-rl-deploy-ros2`](./tron1-rl-deploy-ros2/README.md)、[`limxsdk-lowlevel`](./limxsdk-lowlevel/README.md)、[`robot-joystick`](./robot-joystick/README.md)、[`tdt-nav-kit`](./tdt-nav-kit/README.md)、[`Gymnasium`](./Gymnasium/README.md)、[`habitat-sim`](./habitat-sim/README.md)
- **limx_tron1_wf**（逐际动力 TRON1-WF）：[`tron1-robot-description`](./tron1-robot-description/README.md)、[`tron1-rl-isaaclab`](./tron1-rl-isaaclab/README.md)、[`tron1-rl-deploy-python`](./tron1-rl-deploy-python/README.md)、[`tron1-rl-deploy-ros2`](./tron1-rl-deploy-ros2/README.md)、[`limxsdk-lowlevel`](./limxsdk-lowlevel/README.md)、[`robot-joystick`](./robot-joystick/README.md)、[`tdt-nav-kit`](./tdt-nav-kit/README.md)、[`Gymnasium`](./Gymnasium/README.md)、[`habitat-sim`](./habitat-sim/README.md)
- **microduck**（MicroDuck 双足）：[`unilab_new`](./unilab_new/README.md)、[`Gymnasium`](./Gymnasium/README.md)、[`microduck_all`](./microduck_all/README.md)、[`microduck_rl`](./microduck_rl/README.md)、[`microduck-simulator`](./microduck-simulator/README.md)、[`microduck-studio`](./microduck-studio/README.md)
- **wuji_hand**（无极灵巧手）：[`wuji-mjlab`](./wuji-mjlab/README.md)、[`Gymnasium`](./Gymnasium/README.md)、[`robosuite_new`](./robosuite_new/README.md)、[`Gymnasium-Robotics`](./Gymnasium-Robotics/README.md)
- **zex-w**（ZEX-W 轮足）：[`Gymnasium`](./Gymnasium/README.md)、[`rc_old`](./rc_old/README.md)

## 通用知识库（非机型专属）

| 知识库 | 来源 | 文件数 | 说明 | 索引 |
|---|---|---:|---|---|
| `Robotics_Tutorial` | `00_open/robo_know/Robotics_Tutorial` | 436 | 达妙科技（Pengfei Guo）《Robotics Tutorial》：数学基础 / C++ 工程 / SLAM / 移动机器人规控 / 运动控制 / 具身智能 六大方向的系统化教学文档 | [README](./knowledge_base/Robotics_Tutorial/README.md) |

## 回溯与恢复
1. 项目目录内的路径 = `00_open/<project>/` 下的原始相对路径，**可直接一一对应**。
2. 目录里出现 `_OMITTED.md` 即表示该目录有文件被省略，表内「源路径」列就是可直接取用的位置。
3. 需要恢复某类文件（如全部网格）时：调整 `tools/sync_resources.py` 的 `OMIT_EXTS`
   后重跑 `python legged_studio/tools/sync_resources.py --only <project>`。

## 关键约定
1. **以项目为单位**，不再按机型复制多份；机型归属见各项目 README 与下方反查表。
2. **推理策略文件（`.onnx/.pt/.pth/.engine/.plan/.ckpt/.safetensors`）不限大小一律保留**。
3. 普通文件 **> 20MB 视为「大文件」省略**（含 `.csv/.npz/.npy/.pkl` 等数据）。
4. `build/ dist/ outputs/ logs/`、虚拟环境、`node_modules`、缓存目录**整目录跳过**（不登记）。
5. 类别计数为**功能导向的启发式**归类（路径关键词），仅用于索引，不代表文件归属的唯一解释。

## 关联文档
- 资源模型与重构路线（归档）：[`00_know/90_归档/方案_重构方案_RobotAsset.md`](../00_know/90_归档/方案_重构方案_RobotAsset.md)
- 项目总入口：[`README.md`](../README.md)　｜　归一化资产包：[`assets/robots/`](../assets/robots/)
