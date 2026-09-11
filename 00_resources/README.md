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

- 收录项目 **61** 个　·　文件 **39161** 个　·　体积 **1276.5 MB**
- 省略文件 **17878** 个（**12001.9 MB**），均在原目录留有 `_OMITTED.md` 占位登记
- 通用知识库 **1** 个　·　文件 437 个
- 生成时间：2026-09-11 15:44

## 项目清单（有什么 · 能帮什么 · 关联哪些机器人）

| 项目 | 收录 | 省略 | 体积 | 策略 | 关联机型 | 索引 |
|---|---:|---:|---:|---:|---|---|
| `walk-these-ways` | 103 | 28 | 35.1 MB | 4 | `unitree_go1` | [README](./walk-these-ways/README.md) |
| `HIMLoco` | 74 | 92 | 11.2 MB | 0 | `unitree_go1` | [README](./HIMLoco/README.md) |
| `urdf_tool` | 9115 | 2581 | 120.3 MB | 0 | — | [README](./urdf_tool/README.md) |
| `sdk_deploy` | 8007 | 4460 | 75.9 MB | 2 | `deeprobotics_lite3`、`deeprobotics_m20` | [README](./sdk_deploy/README.md) |
| `wandb` | 7474 | 20 | 90.9 MB | 0 | — | [README](./wandb/README.md) |
| `g1-mujoco-ros2-nav-sim-G1-MuJoCo-ROS2-` | 2201 | 966 | 71.1 MB | 3 | `unitree_g1` | [README](./g1-mujoco-ros2-nav-sim-G1-MuJoCo-ROS2-/README.md) |
| `unilab_new` | 1131 | 21 | 8.1 MB | 0 | `unitree_go2`、`unitree_go2w`、`unitree_go1`、`unitree_g1`、`microduck`、`deeprobotics_m20`、`deeprobotics_lite3` | [README](./unilab_new/README.md) |
| `microduck_all` | 982 | 832 | 64.6 MB | 55 | `microduck` | [README](./microduck_all/README.md) |
| `lain_job` | 962 | 626 | 47.7 MB | 4 | `unitree_go2`、`unitree_go1`、`unitree_g1`、`deeprobotics_m20` | [README](./lain_job/README.md) |
| `rc_old` | 954 | 223 | 40.5 MB | 18 | `zex-w`、`unitree_go1`、`unitree_g1` | [README](./rc_old/README.md) |
| `uni_rl` | 781 | 1573 | 32.2 MB | 5 | `unitree_go2`、`unitree_go2w`、`unitree_go1`、`unitree_b2`、`unitree_b2w`、`unitree_g1` | [README](./uni_rl/README.md) |
| `mjlab_new` | 407 | 106 | 3.9 MB | 0 | `unitree_go1`、`unitree_go2`、`unitree_go2w`、`unitree_g1` | [README](./mjlab_new/README.md) |
| `unitree_rl_mjlab` | 403 | 393 | 22.4 MB | 2 | `unitree_go2`、`unitree_go2w`、`unitree_g1` | [README](./unitree_rl_mjlab/README.md) |
| `unitree_rl_mjlab_go2w` | 384 | 180 | 18.5 MB | 3 | `unitree_go2w`、`unitree_go2`、`unitree_g1` | [README](./unitree_rl_mjlab_go2w/README.md) |
| `mjswan` | 380 | 91 | 22.7 MB | 11 | `unitree_go2`、`unitree_go1`、`unitree_g1` | [README](./mjswan/README.md) |
| `robot_lab` | 370 | 539 | 3.5 MB | 0 | `unitree_go1`、`unitree_go2`、`unitree_go2w`、`unitree_b2`、`unitree_b2w`、`unitree_g1`、`deeprobotics_lite3`、`deeprobotics_m20` | [README](./robot_lab/README.md) |
| `fan_robotlab` | 308 | 539 | 3.4 MB | 0 | `unitree_go1`、`unitree_go2`、`unitree_go2w`、`unitree_b2`、`unitree_b2w`、`unitree_g1`、`deeprobotics_lite3`、`deeprobotics_m20` | [README](./fan_robotlab/README.md) |
| `LeggedGym-Ex` | 306 | 148 | 16.2 MB | 0 | `unitree_go2`、`unitree_go1`、`unitree_g1`、`limx_tron1_pf`、`limx_tron1_sf` | [README](./LeggedGym-Ex/README.md) |
| `gym_ex` | 306 | 148 | 16.2 MB | 0 | `unitree_go2`、`unitree_go1`、`unitree_g1`、`limx_tron1_pf`、`limx_tron1_sf` | [README](./gym_ex/README.md) |
| `kaiwu_rl` | 284 | 49 | 28.3 MB | 7 | `unitree_go2`、`unitree_g1` | [README](./kaiwu_rl/README.md) |
| `mujoco_playground` | 244 | 53 | 6.7 MB | 6 | `unitree_go1`、`unitree_g1` | [README](./mujoco_playground/README.md) |
| `InstinctMJ` | 221 | 85 | 1.9 MB | 0 | `unitree_g1` | [README](./InstinctMJ/README.md) |
| `him_dog` | 212 | 161 | 28.1 MB | 15 | `unitree_go1`、`unitree_go2` | [README](./him_dog/README.md) |
| `wuji-mjlab` | 187 | 61 | 1.1 MB | 0 | `wuji_hand` | [README](./wuji-mjlab/README.md) |
| `LightNav-0` | 183 | 9 | 1.4 MB | 0 | `unitree_go2` | [README](./LightNav-0/README.md) |
| `robot-descriptions-quadruped` | 181 | 65 | 11.8 MB | 8 | `unitree_go1`、`unitree_go2`、`unitree_b2`、`unitree_b2w`、`deeprobotics_lite3`、`deeprobotics_m20` | [README](./robot-descriptions-quadruped/README.md) |
| `microduck_rl` | 176 | 55 | 1.8 MB | 0 | `microduck` | [README](./microduck_rl/README.md) |
| `rl_sar` | 171 | 0 | 30.3 MB | 22 | `unitree_go2`、`unitree_go2w`、`unitree_b2`、`unitree_b2w`、`unitree_g1`、`deeprobotics_lite3` | [README](./rl_sar/README.md) |
| `rl_sar_zoo` | 171 | 416 | 1.5 MB | 0 | `unitree_go2`、`unitree_go2w`、`unitree_b2`、`unitree_b2w`、`unitree_g1`、`deeprobotics_lite3` | [README](./rl_sar_zoo/README.md) |
| `fan_rlsar` | 165 | 0 | 22.0 MB | 16 | `unitree_go2`、`unitree_go2w`、`unitree_b2`、`unitree_b2w`、`unitree_g1`、`deeprobotics_lite3` | [README](./fan_rlsar/README.md) |
| `LeggedSkillDeploy` | 159 | 232 | 43.6 MB | 31 | `unitree_go2`、`unitree_go2w`、`unitree_go1`、`unitree_g1`、`deeprobotics_m20` | [README](./LeggedSkillDeploy/README.md) |
| `UFO` | 155 | 39 | 1.2 MB | 0 | `unitree_g1` | [README](./UFO/README.md) |
| `robo_re` | 154 | 1393 | 100.2 MB | 0 | `unitree_g1` | [README](./robo_re/README.md) |
| `go2w_sim2sim` | 149 | 95 | 110.4 MB | 35 | `unitree_go2w` | [README](./go2w_sim2sim/README.md) |
| `AMP_mjlab` | 142 | 39 | 23.5 MB | 0 | `unitree_g1` | [README](./AMP_mjlab/README.md) |
| `deep_rl` | 133 | 3 | 39.7 MB | 0 | `deeprobotics_lite3`、`deeprobotics_m20` | [README](./deep_rl/README.md) |
| `rl_training` | 133 | 3 | 39.7 MB | 0 | `deeprobotics_lite3`、`deeprobotics_m20` | [README](./rl_training/README.md) |
| `Odin-Nav-Stack` | 104 | 3 | 14.7 MB | 1 | `unitree_go2` | [README](./Odin-Nav-Stack/README.md) |
| `go2_rl_robotlab` | 104 | 27 | 12.8 MB | 2 | `unitree_go2` | [README](./go2_rl_robotlab/README.md) |
| `tron1-robot-description` | 99 | 127 | 730 KB | 0 | `limx_tron1_pf`、`limx_tron1_sf`、`limx_tron1_wf` | [README](./tron1-robot-description/README.md) |
| `go2_rl_gym` | 87 | 29 | 12.3 MB | 3 | `unitree_go2` | [README](./go2_rl_gym/README.md) |
| `m20_rl_isaacsim` | 87 | 76 | 3.7 MB | 4 | `deeprobotics_m20`、`deeprobotics_lite3` | [README](./m20_rl_isaacsim/README.md) |
| `robot_mujoco` | 80 | 368 | 1.9 MB | 0 | `unitree_go1`、`unitree_go2`、`unitree_go2w`、`unitree_b2`、`unitree_b2w`、`unitree_g1`、`deeprobotics_lite3` | [README](./robot_mujoco/README.md) |
| `tron1-rl-isaaclab` | 80 | 12 | 310 KB | 0 | `limx_tron1_pf`、`limx_tron1_sf`、`limx_tron1_wf` | [README](./tron1-rl-isaaclab/README.md) |
| `tron1-rl-deploy-python` | 76 | 1 | 31.4 MB | 54 | `limx_tron1_pf`、`limx_tron1_sf`、`limx_tron1_wf` | [README](./tron1-rl-deploy-python/README.md) |
| `jie_3d_nav` | 69 | 5 | 2.0 MB | 0 | — | [README](./jie_3d_nav/README.md) |
| `1000framesai.com` | 66 | 40 | 6.6 MB | 1 | `unitree_go2` | [README](./1000framesai.com/README.md) |
| `sim.stackforce.cc` | 64 | 168 | 4.0 MB | 0 | `unitree_go2` | [README](./sim.stackforce.cc/README.md) |
| `parkour_mjlab` | 62 | 88 | 13.0 MB | 2 | `unitree_go2`、`unitree_g1` | [README](./parkour_mjlab/README.md) |
| `microduck-simulator` | 58 | 147 | 7.4 MB | 9 | `microduck` | [README](./microduck-simulator/README.md) |
| `references_1000framesai` | 58 | 34 | 7.4 MB | 1 | `unitree_go2` | [README](./references_1000framesai/README.md) |
| `unitree-go2-slam-nav2` | 53 | 0 | 144 KB | 0 | `unitree_go2` | [README](./unitree-go2-slam-nav2/README.md) |
| `Dreamwaq` | 51 | 64 | 551 KB | 0 | `unitree_go2`、`deeprobotics_m20` | [README](./Dreamwaq/README.md) |
| `humanoid-motion-planning` | 50 | 48 | 460 KB | 0 | `unitree_g1` | [README](./humanoid-motion-planning/README.md) |
| `legged_sim` | 38 | 9 | 106 KB | 0 | `unitree_g1` | [README](./legged_sim/README.md) |
| `mjlab-skillkit` | 38 | 0 | 171 KB | 0 | — | [README](./mjlab-skillkit/README.md) |
| `unitree_go2_nav` | 38 | 17 | 182 KB | 0 | `unitree_go2` | [README](./unitree_go2_nav/README.md) |
| `zsi_rl` | 28 | 38 | 89 KB | 0 | `unitree_go2` | [README](./zsi_rl/README.md) |
| `microduck-studio` | 27 | 2 | 87 KB | 0 | `microduck` | [README](./microduck-studio/README.md) |
| `deep_robotics_model` | 19 | 299 | 349 KB | 0 | `deeprobotics_lite3`、`deeprobotics_m20` | [README](./deep_robotics_model/README.md) |
| `g1-manipulation-challenge` | 14 | 49 | 3.6 MB | 4 | `unitree_g1` | [README](./g1-manipulation-challenge/README.md) |
| `unitree_mujoco` | 11 | 20 | 148 KB | 0 | `unitree_go1`、`unitree_go2`、`unitree_g1` | [README](./unitree_mujoco/README.md) |
| `g1_spinkick_example` | 9 | 3 | 1.2 MB | 1 | `unitree_g1` | [README](./g1_spinkick_example/README.md) |

## 项目定位说明

- **`1000framesai.com`**：1000frames.ai 站点镜像资源
- **`AMP_mjlab`**：AMP 动作先验训练（mjlab，G1）
- **`Dreamwaq`**：DreamWaQ 盲式运动控制实现
- **`InstinctMJ`**：InstinctMJ：G1 人形 mjlab 工程
- **`LeggedGym-Ex`**：legged_gym 扩展版：多机型训练环境与任务
- **`LeggedSkillDeploy`**：多机型技能部署包（策略 + 部署配置）
- **`LightNav-0`**：LightNav 视觉导航（Qwen3-VL 系）
- **`Odin-Nav-Stack`**：Odin1 深度相机 + NeuPAN 局部规划的导航栈
- **`UFO`**：UFO：G1 人形工程
- **`deep_rl`**：云深处 RL 训练工程
- **`deep_robotics_model`**：云深处机型模型与描述文件
- **`fan_rlsar`**：RL-SAR 的个人分支（多机型实验）
- **`fan_robotlab`**：robot_lab 的个人分支（多机型实验）
- **`g1-manipulation-challenge`**：G1 操作挑战赛工程
- **`g1-mujoco-ros2-nav-sim-G1-MuJoCo-ROS2-`**：G1 MuJoCo + ROS2 导航仿真
- **`g1_spinkick_example`**：G1 回旋踢示例（mjlab）
- **`go2_rl_gym`**：Go2 的 legged_gym + rsl_rl 训练/回放工程（IsaacGym 系）
- **`go2_rl_robotlab`**：基于 robot_lab 的 Go2 训练工程（IsaacLab）
- **`go2w_sim2sim`**：Go2W 轮足 sim2sim 部署工程（MuJoCo）
- **`gym_ex`**：legged_gym 系实验工程（多机型）
- **`him_dog`**：him_dog 四足工程
- **`humanoid-motion-planning`**：人形运动规划算法
- **`jie_3d_nav`**：JIE 3D 导航栈（jie_octomap + octo_planner）：感知与规划参考
- **`kaiwu_rl`**：开悟 RL 工程（Go2/G1）
- **`lain_job`**：LLoco 技能式 RL 任务与部署（多机型）
- **`legged_sim`**：G1 仿真环境与场景
- **`m20_rl_isaacsim`**：M20 轮足 IsaacSim RL 工程
- **`microduck-simulator`**：MicroDuck 仿真器
- **`microduck-studio`**：MicroDuck Studio（编辑/可视化）
- **`microduck_all`**：MicroDuck 综合工程
- **`microduck_rl`**：MicroDuck RL 训练
- **`mjlab-skillkit`**：mjlab 技能包（adapters / agents / shared）：Isaac Lab → mjlab 移植参考
- **`mjlab_new`**：mjlab 新版：机型资产 + MuJoCo RL 任务
- **`mjswan`**：mjlab 可视化/仿真套件
- **`mujoco_playground`**：DeepMind MuJoCo Playground：Go1/G1 环境与策略
- **`parkour_mjlab`**：Go2/G1 的 parkour 任务（mjlab）
- **`rc_old`**：ZEX-W 轮足旧版工程（含 Go1/G1 分支）
- **`references_1000framesai`**：1000frames.ai 参考素材（机型描述/示例）
- **`rl_sar`**：RL-SAR：仿真到实机部署框架（多机型、含策略与 C++ 部署）
- **`rl_sar_zoo`**：RL-SAR 机型 zoo：URDF/MJCF 与策略集合
- **`rl_training`**：云深处 RL 训练任务与配置
- **`robo_re`**：G1 人形 RL 工程
- **`robot-descriptions-quadruped`**：四足机型描述汇总（URDF/xacro/MJCF）
- **`robot_lab`**：robot_lab：IsaacLab 版多机型训练框架
- **`robot_mujoco`**：多机型 MuJoCo 资产与场景
- **`sdk_deploy`**：云深处 SDK 与部署代码
- **`sim.stackforce.cc`**：stackforce 仿真站点参考资源
- **`tron1-rl-deploy-python`**：TRON1 Python 部署与策略文件
- **`tron1-rl-isaaclab`**：TRON1 IsaacLab RL 训练工程
- **`tron1-robot-description`**：TRON1 机型描述（URDF/xacro）
- **`uni_rl`**：多机型统一 RL 训练框架（宇树全系）
- **`unilab_new`**：统一多机型 RL 实验框架（训练/评估/部署）
- **`unitree-go2-slam-nav2`**：Go2 的 SLAM + Nav2 导航栈（ROS2）
- **`unitree_go2_nav`**：Go2 导航相关脚本与配置
- **`unitree_mujoco`**：宇树官方 MuJoCo 仿真器与机型 XML（Go1/Go2/G1）
- **`unitree_rl_mjlab`**：宇树官方 mjlab 版 RL 工程：训练任务 + MuJoCo 部署（Go2/Go2W/G1）
- **`unitree_rl_mjlab_go2w`**：Go2W 专用 mjlab RL 工程（含 Go2/G1 资产）
- **`urdf_tool`**：URDF 资产查看与验证工具集（robot_viewer / URDF-Studio）
- **`wandb`**：Weights & Biases 客户端（Go core + Python SDK）：训练任务跟踪与可视化参考
- **`wuji-mjlab`**：无极灵巧手 mjlab 训练工程
- **`zsi_rl`**：Go2 的 RL 示例工程
- **`HIMLoco`**：InternRobotics HIMLoco：四足高动态运动/越障 RL 训练工程（legged_gym + rsl_rl）
- **`walk-these-ways`**：Improbable AI walk-these-ways：Go1 快速步态 RL 训练与部署（go1_gym / go1_gym_deploy）

## 机型 → 项目反查

- **unitree_go1**（宇树 Go1 四足）：[`unitree_mujoco`](./unitree_mujoco/README.md)、[`LeggedGym-Ex`](./LeggedGym-Ex/README.md)、[`gym_ex`](./gym_ex/README.md)、[`mjlab_new`](./mjlab_new/README.md)、[`unilab_new`](./unilab_new/README.md)、[`uni_rl`](./uni_rl/README.md)、[`lain_job`](./lain_job/README.md)、[`mjswan`](./mjswan/README.md)、[`mujoco_playground`](./mujoco_playground/README.md)、[`LeggedSkillDeploy`](./LeggedSkillDeploy/README.md)、[`robot_lab`](./robot_lab/README.md)、[`fan_robotlab`](./fan_robotlab/README.md)、[`robot_mujoco`](./robot_mujoco/README.md)、[`robot-descriptions-quadruped`](./robot-descriptions-quadruped/README.md)、[`him_dog`](./him_dog/README.md)、[`rc_old`](./rc_old/README.md)、[`HIMLoco`](./HIMLoco/README.md)、[`walk-these-ways`](./walk-these-ways/README.md)
- **unitree_go2**（宇树 Go2 四足）：[`go2_rl_gym`](./go2_rl_gym/README.md)、[`go2_rl_robotlab`](./go2_rl_robotlab/README.md)、[`unitree-go2-slam-nav2`](./unitree-go2-slam-nav2/README.md)、[`unitree_go2_nav`](./unitree_go2_nav/README.md)、[`references_1000framesai`](./references_1000framesai/README.md)、[`1000framesai.com`](./1000framesai.com/README.md)、[`sim.stackforce.cc`](./sim.stackforce.cc/README.md)、[`Odin-Nav-Stack`](./Odin-Nav-Stack/README.md)、[`LightNav-0`](./LightNav-0/README.md)、[`zsi_rl`](./zsi_rl/README.md)、[`unitree_rl_mjlab`](./unitree_rl_mjlab/README.md)、[`unitree_rl_mjlab_go2w`](./unitree_rl_mjlab_go2w/README.md)、[`unitree_mujoco`](./unitree_mujoco/README.md)、[`LeggedGym-Ex`](./LeggedGym-Ex/README.md)、[`gym_ex`](./gym_ex/README.md)、[`mjlab_new`](./mjlab_new/README.md)、[`unilab_new`](./unilab_new/README.md)、[`uni_rl`](./uni_rl/README.md)、[`lain_job`](./lain_job/README.md)、[`kaiwu_rl`](./kaiwu_rl/README.md)、[`mjswan`](./mjswan/README.md)、[`parkour_mjlab`](./parkour_mjlab/README.md)、[`Dreamwaq`](./Dreamwaq/README.md)、[`LeggedSkillDeploy`](./LeggedSkillDeploy/README.md)、[`robot_lab`](./robot_lab/README.md)、[`fan_robotlab`](./fan_robotlab/README.md)、[`rl_sar`](./rl_sar/README.md)、[`rl_sar_zoo`](./rl_sar_zoo/README.md)、[`fan_rlsar`](./fan_rlsar/README.md)、[`robot_mujoco`](./robot_mujoco/README.md)、[`robot-descriptions-quadruped`](./robot-descriptions-quadruped/README.md)、[`him_dog`](./him_dog/README.md)
- **unitree_go2w**（宇树 Go2W 轮足）：[`go2w_sim2sim`](./go2w_sim2sim/README.md)、[`unitree_rl_mjlab`](./unitree_rl_mjlab/README.md)、[`unitree_rl_mjlab_go2w`](./unitree_rl_mjlab_go2w/README.md)、[`mjlab_new`](./mjlab_new/README.md)、[`unilab_new`](./unilab_new/README.md)、[`uni_rl`](./uni_rl/README.md)、[`LeggedSkillDeploy`](./LeggedSkillDeploy/README.md)、[`robot_lab`](./robot_lab/README.md)、[`fan_robotlab`](./fan_robotlab/README.md)、[`rl_sar`](./rl_sar/README.md)、[`rl_sar_zoo`](./rl_sar_zoo/README.md)、[`fan_rlsar`](./fan_rlsar/README.md)、[`robot_mujoco`](./robot_mujoco/README.md)
- **unitree_b2**（宇树 B2 四足）：[`uni_rl`](./uni_rl/README.md)、[`robot_lab`](./robot_lab/README.md)、[`fan_robotlab`](./fan_robotlab/README.md)、[`rl_sar`](./rl_sar/README.md)、[`rl_sar_zoo`](./rl_sar_zoo/README.md)、[`fan_rlsar`](./fan_rlsar/README.md)、[`robot_mujoco`](./robot_mujoco/README.md)、[`robot-descriptions-quadruped`](./robot-descriptions-quadruped/README.md)
- **unitree_b2w**（宇树 B2W 轮足）：[`uni_rl`](./uni_rl/README.md)、[`robot_lab`](./robot_lab/README.md)、[`fan_robotlab`](./fan_robotlab/README.md)、[`rl_sar`](./rl_sar/README.md)、[`rl_sar_zoo`](./rl_sar_zoo/README.md)、[`fan_rlsar`](./fan_rlsar/README.md)、[`robot_mujoco`](./robot_mujoco/README.md)、[`robot-descriptions-quadruped`](./robot-descriptions-quadruped/README.md)
- **unitree_g1**（宇树 G1 人形）：[`unitree_rl_mjlab`](./unitree_rl_mjlab/README.md)、[`unitree_rl_mjlab_go2w`](./unitree_rl_mjlab_go2w/README.md)、[`unitree_mujoco`](./unitree_mujoco/README.md)、[`LeggedGym-Ex`](./LeggedGym-Ex/README.md)、[`gym_ex`](./gym_ex/README.md)、[`mjlab_new`](./mjlab_new/README.md)、[`unilab_new`](./unilab_new/README.md)、[`uni_rl`](./uni_rl/README.md)、[`lain_job`](./lain_job/README.md)、[`kaiwu_rl`](./kaiwu_rl/README.md)、[`mjswan`](./mjswan/README.md)、[`mujoco_playground`](./mujoco_playground/README.md)、[`parkour_mjlab`](./parkour_mjlab/README.md)、[`LeggedSkillDeploy`](./LeggedSkillDeploy/README.md)、[`robot_lab`](./robot_lab/README.md)、[`fan_robotlab`](./fan_robotlab/README.md)、[`rl_sar`](./rl_sar/README.md)、[`rl_sar_zoo`](./rl_sar_zoo/README.md)、[`fan_rlsar`](./fan_rlsar/README.md)、[`robot_mujoco`](./robot_mujoco/README.md)、[`robo_re`](./robo_re/README.md)、[`InstinctMJ`](./InstinctMJ/README.md)、[`AMP_mjlab`](./AMP_mjlab/README.md)、[`humanoid-motion-planning`](./humanoid-motion-planning/README.md)、[`legged_sim`](./legged_sim/README.md)、[`g1-manipulation-challenge`](./g1-manipulation-challenge/README.md)、[`UFO`](./UFO/README.md)、[`g1-mujoco-ros2-nav-sim-G1-MuJoCo-ROS2-`](./g1-mujoco-ros2-nav-sim-G1-MuJoCo-ROS2-/README.md)、[`g1_spinkick_example`](./g1_spinkick_example/README.md)、[`rc_old`](./rc_old/README.md)
- **deeprobotics_lite3**（云深处 Lite3 四足）：[`unilab_new`](./unilab_new/README.md)、[`robot_lab`](./robot_lab/README.md)、[`fan_robotlab`](./fan_robotlab/README.md)、[`rl_sar`](./rl_sar/README.md)、[`rl_sar_zoo`](./rl_sar_zoo/README.md)、[`fan_rlsar`](./fan_rlsar/README.md)、[`robot_mujoco`](./robot_mujoco/README.md)、[`robot-descriptions-quadruped`](./robot-descriptions-quadruped/README.md)、[`sdk_deploy`](./sdk_deploy/README.md)、[`deep_robotics_model`](./deep_robotics_model/README.md)、[`deep_rl`](./deep_rl/README.md)、[`rl_training`](./rl_training/README.md)、[`m20_rl_isaacsim`](./m20_rl_isaacsim/README.md)
- **deeprobotics_m20**（云深处 M20 轮足）：[`unilab_new`](./unilab_new/README.md)、[`lain_job`](./lain_job/README.md)、[`Dreamwaq`](./Dreamwaq/README.md)、[`LeggedSkillDeploy`](./LeggedSkillDeploy/README.md)、[`robot_lab`](./robot_lab/README.md)、[`fan_robotlab`](./fan_robotlab/README.md)、[`robot-descriptions-quadruped`](./robot-descriptions-quadruped/README.md)、[`sdk_deploy`](./sdk_deploy/README.md)、[`deep_robotics_model`](./deep_robotics_model/README.md)、[`deep_rl`](./deep_rl/README.md)、[`rl_training`](./rl_training/README.md)、[`m20_rl_isaacsim`](./m20_rl_isaacsim/README.md)
- **limx_tron1_pf**（逐际动力 TRON1-PF）：[`LeggedGym-Ex`](./LeggedGym-Ex/README.md)、[`gym_ex`](./gym_ex/README.md)、[`tron1-robot-description`](./tron1-robot-description/README.md)、[`tron1-rl-isaaclab`](./tron1-rl-isaaclab/README.md)、[`tron1-rl-deploy-python`](./tron1-rl-deploy-python/README.md)
- **limx_tron1_sf**（逐际动力 TRON1-SF）：[`LeggedGym-Ex`](./LeggedGym-Ex/README.md)、[`gym_ex`](./gym_ex/README.md)、[`tron1-robot-description`](./tron1-robot-description/README.md)、[`tron1-rl-isaaclab`](./tron1-rl-isaaclab/README.md)、[`tron1-rl-deploy-python`](./tron1-rl-deploy-python/README.md)
- **limx_tron1_wf**（逐际动力 TRON1-WF）：[`tron1-robot-description`](./tron1-robot-description/README.md)、[`tron1-rl-isaaclab`](./tron1-rl-isaaclab/README.md)、[`tron1-rl-deploy-python`](./tron1-rl-deploy-python/README.md)
- **microduck**（MicroDuck 双足）：[`unilab_new`](./unilab_new/README.md)、[`microduck_all`](./microduck_all/README.md)、[`microduck_rl`](./microduck_rl/README.md)、[`microduck-simulator`](./microduck-simulator/README.md)、[`microduck-studio`](./microduck-studio/README.md)
- **wuji_hand**（无极灵巧手）：[`wuji-mjlab`](./wuji-mjlab/README.md)
- **zex-w**（ZEX-W 轮足）：[`rc_old`](./rc_old/README.md)

## 通用知识库（非机型专属）

| 知识库 | 来源 | 文件数 | 说明 | 索引 |
|---|---|---:|---|---|
| `Robotics_Tutorial` | `00_open/robo_know/Robotics_Tutorial` | 437 | 达妙科技（Pengfei Guo）《Robotics Tutorial》：数学基础 / C++ 工程 / SLAM / 移动机器人规控 / 运动控制 / 具身智能 六大方向的系统化教学文档 | [README](./knowledge_base/Robotics_Tutorial/README.md) |

## 未纳入的项目（非目标机型 / 非机型资源）

- `auto_web`（约 90943 文件）— 通用 Web 项目素材（其中 `auto_web/wandb` 已单独纳入为训练平台参考）
- `ComfyUI`（约 1112 文件）— 通用 AI 生成工具
- `InvokeAI`（约 4261 文件）— 通用 AI 生成工具
- `langflow`（约 10280 文件）— 通用工作流工具
- `n8n`（约 28022 文件）— 通用工作流工具
- `awesome-robot-descriptions`（约 87 文件）— 机器人描述汇总（仅索引/网格）
- `dm_dog`（约 285 文件）— 非目标机型（A1/DM 系列）
- `min_dog`（约 132 文件）— 非目标机型
- `archive`（约 6 文件）— 历史归档
- `tools`（约 2 文件）— 工作区脚本
- `robo_know`（约 468 文件）— 机器人通用知识文档（其中 Robotics_Tutorial 已单独纳入 knowledge_base/）

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
- 资源模型与重构路线：[`00_know/重构方案_RobotAsset资源模型与实施路线.md`](../00_know/重构方案_RobotAsset资源模型与实施路线.md)
- 项目总入口：[`README.md`](../README.md)　｜　归一化资产包：[`assets/robots/`](../assets/robots/)
