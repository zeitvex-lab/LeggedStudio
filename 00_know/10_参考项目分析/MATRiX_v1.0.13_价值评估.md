# MATRiX 生态价值评估与提取记录（v1.0.13 运行时 + MC v0.6.4 + RoamerX Open）

> **本篇是 MATRiX 生态的单一归档文档**（按约定不另开新文档），覆盖三份外部发行物：
>
> | # | 发行物 | 来源 | 体量 | 本地位置（均已 `.gitignore`） |
> |---|---|---|---|---|
> | A | MATRiX v1.0.13 Linux 运行时 | GitHub `zsibot/matrix` release `v1.0.13`（三分卷） | 4,251,475,324 B | `matrix-v1.0.13/` |
> | B | MATRiX Robot MC v0.6.4 | GitHub `GENISOM-AI/MATRiX_Robot_MC` release `v0.6.4` | 900,690,534 B（sha256 校验通过） | `matrix-robot-mc-v0.6.4/` |
> | C | GENISOM RoamerX Open | GitHub `zsibot/genisom_roamerx_open`（`main`，`--depth 1`） | 131 MB | `genisom-roamerx-open/` |
>
> **许可**：A 的文档/源码仓 BSD-3-Clause (ZsiBot)；**A、B 内的二进制、模型、地图 DLC 与第三方组件许可另行声明，再分发前必须逐项核实**；C 为 BSD-3-Clause (ZsiBot)，可复用但须保留版权。
> **核对日期**：2026-09-12　**核对方式**：解压实物 + MuJoCo 加载实测 + 容器分帧实测 + sha256 校验 + 只读静态分析
> **明确不做**：不绕过 B 的模型加密（理由与替代路径见 §6.1）

---

## 1. 它是什么

MATRiX 是「UE5 渲染 + MuJoCo 物理 + Zenoh 数据传输」的高保真机器人仿真平台。本次拿到的是 **Linux 运行时发行包**（非源码）：

```text
MATRiX_v1.0.13/
├── UeSim.sh                     # 启动脚本，exec UeSim/Binaries/Linux/UeSim UeSim "$@"
├── UeSim/                       # 4.7G
│   ├── Binaries/Linux/          # UeSim 主程序 + libmujoco.so.3.3.0 / libzenohc.so / libonnxruntime.so.1
│   ├── Content/Paks/            # 1.5G（pakchunk0-Linux.pak 1.29G）
│   ├── Content/model/           # 485M：9 族机器人 MJCF + config/（传感器与主配置）
│   └── Plugins/                 # MatrixMotionControl / RobotSensorSimulation / MujocoSceneImporter
├── Engine/                      # UE5 引擎
├── Tools/                       # 10 个 Python 工具，5582 行
├── docs/                        # 15 篇文档，116KB
└── demo_gif/                    # 90M 演示素材
```

默认配置（`UeSim/Content/model/config/config.json`）：`mujoco_model=model/xgb/xgb.xml`、`inside_mc=true`（内置运控）、`network_mode=standalone`、`zenoh_router=tcp/0.0.0.0:7447`、`state_port=mujoco/state`、`cmd_port=mujoco/cmd`、`main_body=base_link`。

### 1.1 三份发行物的关系（生态闭环）

```text
A  MATRiX/UeSim ── 仿真 + 传感器 + 渲染
     ├─ 传感器：Zenoh `rt/**` @ :7447（/front_lidar、/front_lidar/imu、/odom/mujoco_odom…）
     └─ 运控接口：共享内存 ABI / UDP / LCM
                       │
B  MC v0.6.4 ── 机器人运控（加密策略 + 导出规格 + 依赖 deb）
     └─ 依赖：deps/robot-forward_0.2.9、mujoco_3.3.0、onnx_1.51.0、ecal、lcm、robots_dog_msgs
                       │  RMW_IMPLEMENTATION=rmw_zenoh_cpp、ROS_DOMAIN_ID=89
C  RoamerX Open ── SLAM / 定位 / 代价地图 / 规划 / 控制（ROS2 Humble）
```

三者是**配套**的：C 的中文文档要求的 `robot-forward` 恰好是 B 里的 `deps/robot-forward_0.2.9_amd64.deb`；C 要求修改的 `sdk_config.yaml` 就是 B 的 `config/sdk_config.yaml`（`target_ip/target_port: 43988`）。

## 2. 实测结论

### 2.1 MJCF 模型：全部可用（实测通过）

用 `mujoco 3.11.0`（`/tmp/mjlab_cpu_venv`）逐个加载 + 200 步零力矩步进，14 个入口全部通过：

| 模型 | nq / nv / nu | nbody | 备注 |
|---|---|---:|---|
| `go2`（含 scene / auto_scene） | 19 / 18 / 12 | 18 | 与项目已有 Go2 资产重叠，可交叉校验 |
| `go2w` | 23 / 22 / 16 | 18 | 轮足 |
| `xgb`（发行默认，`<mujoco model="DOG">`） | 19 / 18 / 12 | 14 | 自研四足，ABAD/HIP/KNEE ×4 |
| `xg2` | 19 / 18 / 12 | 14 | 四足 |
| `xgw` / `xgw2` | 23 / 22 / 16 | 18 / 19 | 轮足 |
| `zgwt`（含 auto_scene） | 23 / 22 / 16 | 18 | 轮足 |
| `zgws` | 23 / 22 / 16 | 18 | 轮足，含月面地形变体 |
| `zgwsarm` | 29 / 28 / 22 | 24 | 轮足 + 6 轴机械臂（`ROBOT_ARM_JOINT1..6`） |

- `<compiler angle="radian" meshdir="assets/">` + STL 相对路径 → **整目录可搬迁**，可直接落进 `assets/`。
- MJCF 内 `<sensor>` 只有 `<jointpos>`（关节位置）；IMU / 相机 / 雷达全部由 UE 侧 `RobotSensorSimulation` 插件产生，**MuJoCo 只负责物理**。这与本项目「MJCF 物理 + 浏览器渲染」的分工不同。

### 2.2 UeSim 本体：本容器/CI 跑不起来

```text
$ ./UeSim.sh -windowed -ResX=640 -ResY=480
Refusing to run with the root privileges.
libc++abi: __cxa_guard_acquire detected recursive initialization
exit=134（核心转储）
```

环境侧事实：无 `/dev/dri`、无 `nvidia-smi`、无 `vulkaninfo`。**结论：必须 GPU 物理机/工作站，云开发容器与 CI 均不可运行**，因此它不能进入项目的自动验收链路。

### 2.3 内置运控模型：加密，不可复用

`UeSim/Plugins/MatrixMotionControl/Source/ThirdParty/MatrixMC/models/`：**165 个文件 / 952MB**，覆盖 7 族（xg 46、zg_wheels 40、xg_wheel 24、xg_wheel2 24、xg2 21、zgws_arm 5、xxg 4）。命名即动作库：

```text
crawl  stair  climb  jump  backflip  flipover  frontflip  sideflip  handstand
tuoluo  skwalk  snow  dsb  hload  slim  moonwalk  mimic        （policy_* / odom_* 成对）
```

但**全部加密**，三条证据：

1. 165 个文件只有 6 种 8 字节魔数（如 `3c1f706db84416e3` 占 102 个），**不是 ONNX protobuf**（ONNX 以 `\x08` 开头）；
2. 实测 `sha256` 与同目录 `models.json` 记录的 `plaintext_source_sha256` **不一致**（`xg/policy_mix_walk` 实测 `fd4b66cd…` vs 记录明文 `bdb332b6…`）；
3. 该 json 自带 `"encrypted_model_counts"` 与 `source_repository: GENISOM-AI/MATRiX_Robot_MC`（发布包不含独立运控）。

⇒ 按项目**规则 S**（无训练源码的策略不登记部署），这批模型**不入策略库**，仅作能力与命名参考。

### 2.4 传感器语料：容器可验证，载荷未解码

`UeSim/Plugins/RobotSensorSimulation/Data/` 两份录制数据：

| 文件 | 大小 | 魔数 | 版本 | 帧大小 | 正体偏移 | 帧数 | 时长@10Hz |
|---|---:|---|---:|---:|---:|---:|---:|
| `Airy_2026-07-03_frame0225.airybin` | 63,652,192 | `ARY1` | 1 | 1,720,320 | 352 | 37 | 3.7 s |
| `Mid360_2025-11-28_2s_valid.mid360bin` | 12,717,276 | `M3D1` | 2 | 264,936 | 348 | 48 | 4.8 s |

- 分帧自洽：`body_offset + frames × frame_size == file_size`（352+37×1720320=63652192；348+48×264936=12717276）。
- **载荷未解码**：把正体按 float32 列统计，两文件均以非有限/非规格化值为主（Airy 仅 77.8% 有限、Mid360 97.1%），说明记录内**整型与浮点字段混排**，而发行包未给出布局文档 → 不写猜测性解析器，只固化可验证的容器事实。

### 2.5 MC v0.6.4：可校验、结构清楚、规格含金量高

```text
$ sha256sum -c  ← 5ac4d58793045936f4e1fe78e311473af7cd5f99aed8b9b1779d944dc5ded72b  → 成功
$ tar -tzf | grep -E "^/|\.\./"   → 无绝对路径/上跳条目
$ tar -xzf …                       → 3.9s，865M，225 条目
```

| 目录 | 内容 | 体量 |
|---|---|---|
| `deps/` | 7 个 .deb：`robot-forward_0.2.9`、`mujoco_3.3.0`、`onnx_1.51.0`、`ecal_5.13.3`、`lcm_1.5.1`、`zsibot_common_0.6.3`、`robots_dog_msgs_0.9.2_humble` | 52M |
| `build/export/mc/bin/` | `librobot.so`、`libbiomimetics.so`、`libdynacore_*.so` 等运行时 | 10 个 .so |
| `build/export/config/` | **39 个 yaml**：每机型 `*-rl_onnx_config` / `-rl_rknn_config` / `-motion_config` / `-mimic_config` / `-dance_config` / `-user-parameters` | — |
| `build/export/onnx_model_crypto/` | 165 个加密模型（目录名自带 `crypto`，与 §2.3 结论一致） | — |
| `build/export/robot_urdf/` | `zgwsarm` URDF | — |
| `config/sdk_config.yaml` | `target_ip` / `target_port: 43988`（即 C 的文档要求修改的文件） | — |

**两类 yaml 的真实内容（已逐字核对，修正了我的初始预期）**：

1. `*-rl_onnx_config.yaml` **不是** obs/action 规格，而是**行为名 → 模型路径的注册表**。以 `xg` 为例，它暴露了完整行为清单：
   ```text
   backflip  jump  upright  gait  mix_walk  gait_walk  flipover  mix_backflip
   frontflip  sideflip  balancestand  tracking  walkpos  ik  crawl  moonwalk  measured
   ```
   并且能看到两条结构线索：`policy_*` 与 `odom_*` **成对**（策略与估计器分离）；`policy_him_hs1_encoder_path` + `policy_him_hs1_actor_path` 是 **HIM 非对称 encoder/actor 拆分**（与本项目 go1 所用的 HIMLoco 同族）。
2. `*-user-parameters.yaml` 是**参数真值**（以 `xg` 为例）：

   | 类别 | 关键值 |
   |---|---|
   | 关节 Kp/Kd | `Kp_joint [3,4,3]` / `Kd_joint [1,1,1]`；摆动相同 |
   | WBC 增益 | `Kp_body [100,100,200]`、`Kp_foot [800,100,100]`、`Kp_ori [500,500,500]` |
   | MPC / CM-PC | `horizon 14`、`fmax 120`、`Q_rpy/Q_xyz/Q_*d` 权重、`preview_time 0.5` |
   | 指令上限 | `cmpc_x_vel 3.0`、`cmpc_y_vel 1.0`、`cmpc_yaw_vel 3.0` |
   | 形态 | `body_height 0.32`、`leg_height 0.1`、`body_half_length 0.175`、`drop_height -0.13` |
   | **关节限位** | `JPos_limit_low [-0.48,-1.15,-2.7]` / `JPos_limit_high [0.48,2.97,-0.65]`、`jointVelocityLimit 24.0` |
   | 零位/符号 | `*_side_sign`（abad/hip/knee/wheel）、`abad/hip/knee_offset`、`*_stand_pos` / `*_liedown_pos` / `*_default_pos` |
   | 步态 | `gait_type 4`、`gait_period_time 0.2`、`gait_switching_phase 0.5`、`gait_max/min_stance_time 0.25/0.1` |
   | 爬行 | `min/max_crawl_x_vel ±1.0`、`±1.0`、`±3.0` |

   **交叉验证（两份独立发行物互证）**：`JPos_limit_low/high = [-0.48,-1.15,-2.7] / [0.48,2.97,-0.65]` 与 A 的 `xgb.xml` 关节 `range="-0.48 0.48"`、`"-1.15 2.97"`、`"-2.7 -0.65"` **逐项一致**；MJCF 侧另有 `actuatorfrcrange="±28"`、`frictionloss="0.2"`。三者合起来就是一套完整的 actuator/限位参数集。

### 2.6 RoamerX Open：生产级 ROS2 导航栈（只能静态分析）

| 子树 | 内容 | 体量 |
|---|---|---|
| `src/navigation/src/` | 15 个 `navigo_*` 包 + `robot_navigo` 集成层 | — |
| `src/localization/` | `fast_gicp`、`ndt_omp`、`localization`（IMU+Lidar UKF 融合） | — |
| `src/slam/src/` | `robot_slam`（FAST-LIO 类：`ikd_tree`、`mtk_iekf`）+ `pcd2grid` | — |
| `src/interface/robots_dog_msgs/` | **55 msg + 14 srv + 10 action** | — |
| `map/` | `map.pgm`(419K) + `map.yaml` + `map.txt` | 420K |
| `script/` | `start_navigation.sh` / `stop_navigation.sh` / `cleanup_backend.sh` + 依赖安装（ros2/gazebo/手柄/fishros） | 36K |

**Nav2 全量分叉**（包名与插件名同步改写）：`navigo_core←nav2_core`、`navigo_util←nav2_util`、`navigo_costmap_2d←nav2_costmap_2d`、`navigo_map_server←nav2_map_server`、`navigo_bt_navigator/behavior_tree/behaviors←nav2_*`、`navigo_path_planner←nav2_planner`、`navigo_navfn_planner←nav2_navfn_planner`、`navigo_path_controller←nav2_controller`、`navigo_mppi_controller←nav2_mppi_controller(1.1.18)`、`navigo_waypoint_follower`、`navigo_velocity_optimizer←nav2_velocity_smoother`、`navigo_collision_monitor←nav2_collision_monitor`、`robot_navigo←nav2_bringup`（另加 udp/lcm/自定义节点）。

**对外接口**（对项目参考价值最高的一块）：

- 输入：`/front_lidar`、`/front_lidar/imu`、`/odom/mujoco_odom`、`/scan`；输出 `cmd_vel`（内部 `cmd_vel_nav`）
- Action：`/navigate_to_pose`、`/navigate_through_poses`、`FollowPath`、`FollowWaypoints`、`ComputePathThroughPoses`、`ComputePathsToPoses`、`ExploreThroughPoses`、`BackUp`
- Service：`/map_server/load_map`、`/load_map_service`（`LoadMap`，PCD 路径）
- 自定义消息（地图/障碍/规划的序列化参考）：`ElectronicMap`、`ElectronicObstacle`、`ObstacleInstance2D`、`ObstacleScan`、`PlannerDebugInfo`、`PredictedPath(Array)`、`UniBestNav`、`Trajectory(Point)`、`SlamState`、`Relocalization`、`Localization`
- 双协议控制：UDP（`robot_navigo/udp/*`、`vel_cmd_udp_publisher.cpp`）与 LCM（`lcm-types/{cpp,java}`、`vel_cmd_lcm_publisher.cpp`）

**与 A 的适配配方**（`README_matrix和zsibot_roamerx_lite适配.md`）：

```text
export RMW_IMPLEMENTATION=rmw_zenoh_cpp ; export ROS_DOMAIN_ID=89 ; export SDK_CLIENT_IP=127.0.0.1
ros2 run rmw_zenoh_cpp rmw_zenohd                       # 中枢
sudo /opt/robot/robot-forward/install/robot_forward     # 需 root
slam/src/config/config.yaml: lid_topic=/front_lidar, imu_topic=/front_lidar/imu
```
这套话题正好对上 A 的 `sensors/mid360_slam.json`（`/front_lidar` + `/front_lidar/imu` + `/odom`）。

**两处必须注意的错配**：① C 的中文文档面向**旧版 MATRiX 源码树布局**（`matrix/run_sim.sh`、`./open_sim_launcher`、`matrix/src/robot_mc/...`），而 A 的 v1.0.13 文档明确声明这些路径**已不存在**；② 文档里仍是旧仓名 `zsibot_roamerx_lite`，实际仓已是 `genisom_roamerx_open`。

**可跑性**：❌ 本容器 `Debian 13 (trixie)`、无 `/opt/ros`、无 `ros2`；ROS2 Humble 属 Ubuntu 22.04，构建还需 colcon + PCL/OpenCV/OMPL/BehaviorTree.CPP/Gazebo → **只能静态分析**。

## 3. 资产清单（可评估项）

| 类别 | 内容 | 数量/体量 |
|---|---|---|
| 机器人模型 | go2、go2w、xgb、xg2、xgw、xgw2、zgws、zgwsarm、zgwt | 9 族，485M |
| 传感器声明 | `config/config.json` + `config/sensors/*.json`（上游 9 个预设文件） | 本项目收录 **4 套 / 13 条** |
| 传感器语料 | Airy / Mid360 录制帧 | 2 份，76M |
| 传感器预设参数 | `config/jszr_params/lidar_process_params.yaml` 等 | — |
| 地图机制 | `Content/model/MapDataTable.json`（空表）+ `Saved/DLCs/*.pak` + UPDATE LIST 目录 | 基础包为空目录 |
| 感知工具 | `visualize_lidar_camera_projection.py`(1825 行)、`zenoh_sensor_receiver.py`(1048 行)、`visualize_zenoh_bbox*.py`、`zenoh_topic_monitor.py`、云台 UDP 工具 | 10 个，5582 行 |
| 文档 | USAGE / MOTION_CONTROL / LidarCameraProjection / MAP_DLC / ZenohBBox2D / RoamerX_Lite 集成 / PixelStreaming | 15 篇，116KB |
| 传输与远端渲染 | Zenoh router(7447) + Pixel Streaming 2 WebServer 脚本 | — |
| 运控 | 内置 MC（加密模型 + `libonnxruntime.so.1`）+ `matrix_mc_udp_test.py` + 云台 JSON 协议(44KB) | 952M（加密） |
| **B** 运控发行包 | `deps/`(7 deb) + `build/export/mc/bin`(10 so) + `build/export/config`(**39 yaml**) + `onnx_model_crypto`(165 加密) + `robot_urdf` + `sdk_config.yaml` | 865M |
| **C** 导航栈 | 15 `navigo_*` + `robot_navigo` + `fast_gicp/ndt_omp/localization` + `robot_slam` + `robots_dog_msgs`(55/14/10) + `map/` | 131M |

## 4. 对项目的价值映射

### 4.1 高级仿真（重点）

现状（改动前）：`web/advanced_sim.html` 用**文案**描述「外部传感器（深度相机 / 雷达 / 点云）」，机读词汇只有 `backend/perception_observations.py` 的 4 个派生源（`proprio / foot_contact / heightfield / depth_camera`）、策略侧靠 `sim_surface=advanced` 过滤。**缺：传感器清单契约、多传感器语料、点云→观测的对齐基准。**

> **该缺口已闭合**：传感器清单契约 = `backend/sensor_suite.py` + `/api/sensors/*`；多传感器语料 = `tools/matrix_sensor_corpus.py`；点云 → 观测对齐 = 187 格 height scan 契约（`backend/height_scan.py`）。
> 另：**「感知两条路径」分层**（A 类感知入观测 / B 类感知在策略外、盲狗 RL 同样合格）见 [`任务清单.md`](../50_方案与清单/任务清单.md) H 节与 [`最终愿景.md`](../50_方案与清单/最终愿景.md) §高级仿真——`sim_surface=advanced` 的判定依据是「这条策略被怎么用」，不是「策略是否吃传感器」。

| # | MATRiX 资产 | 对高级仿真的价值 | 落地 |
|---|---|---|---|
| 1 | `config.json` + `sensors/*.json` | 声明式传感器 schema（类型/挂载体/外参/频率/话题/内参）→ 把「外部传感器」从文案变成契约 | **本次已落地**（`backend/sensor_suite.py` + `/api/sensors/*` + 高级仿真页面板） |
| 2 | Airy / Mid360 录制帧 | 无需 GPU 的离线语料：点云解析与「雷达高度扫描 ↔ heightfield 逐格对齐」回归的样本源 | **本次已登记**（`tools/matrix_sensor_corpus.py` 固化容器事实 + 自检） |
| 3 | `visualize_lidar_camera_projection.py`（1825 行）+ 投影文档 | 现成的雷达→相机投影实现：XCDR1 订阅、内外参、`sensor_sync_mode` 配对、坐标约定、标定 JSON | 待接入（本次只登记契约字段） |
| 4 | `visualize_zenoh_bbox.py`/`_2d.py` + ZenohBBox2D 文档 | 目标级感知可视化与判定（3D/2D bbox）→ 对应高级仿真「目标判定」 | 待接入 |
| 5 | `zenoh_sensor_receiver.py` + 主题监控 | 传感器数据的实际编码与频率（IMU 500Hz、odom/GPS 100Hz、相机与雷达 10Hz）→ 写 obs 契约时的权威默认值 | **本次已落地**（套件频率即采用该口径） |
| 6 | 动作库命名（stair/climb/flipover/handstand/mimic…）与 `policy_*`/`odom_*` 分离 | 目标驱动任务分类法与「估计器网络独立于策略」的路线参照（与 HIMLoco 一致） | 参考（不导入加密模型） |
| 7 | `MapDataTable.json` + DLC pak 增量分发 | 大场景按需下载、不进仓的清单式分发思路 | 参考（对照 `backend/scenario_maps.py`） |
| 8 | Pixel Streaming 2 | 远端渲染补位：浏览器 WASM 跑不动的高保真场景可放服务器推流 | 远期 |
| 9 | **B** `*-rl_onnx_config.yaml` 行为清单 | 目标驱动任务分类法（`backflip / frontflip / sideflip / flipover / moonwalk / tracking / walkpos / ik / crawl / balancestand`）+ `policy_*`/`odom_*` 成对 + HIM `encoder`/`actor` 拆分 → 高级仿真 `task_type` / 特技触发与「估计器」设计的参照 | 参考（不入库） |
| 10 | **B** `*-user-parameters.yaml` | 关节限位 / 零位 / 符号 / Kp-Kd / 最大速度指令 / 步态调度的**参数真值** → 传感器驱动任务的动作空间与安全边界 | **建议做三方对照**（§4.3 T1） |
| 11 | **C** costmap / BT / MPPI / velocity_smoother / collision_monitor | 目标驱动导航任务的成熟结构与参数（避障、多点巡航、速度平滑） | 参考设计 |
| 12 | **C** `ElectronicMap`/`ElectronicObstacle`/`ObstacleInstance2D` + `map.pgm|yaml` + `pcd2grid` | 地图与障碍的**序列化格式**、PCD→2D 栅格流程 → 对照 `scenario_maps.py` / `route_planner.py` | 参考 |
| 13 | **C** SLAM（FAST-LIO + NDT/GICP）+ UKF 定位 | 高级仿真「外部传感器 → 状态估计」链路参照，且可作学习型估计器的**几何基线** | 需 ROS2，不进 CI |

### 4.2 高级仿真之外

| 资产 | 价值 | 约束 |
|---|---|---|
| 9 族 MJCF | `go2`/`go2w` 交叉校验；`xgb/xg2/xgw/xgw2/zgws/zgwsarm/zgwt` 为新机型候选；`scene_terrain_moon_dynamic.xml` 为低重力地形素材 | 新机型须过规则 T（有训练源）才可入库 |
| M20 之外的轮足/机械臂形态 | `zgwsarm`（4 足 + 6 轴臂）与项目现有形态互补 | 同上 |
| 内置运控 UDP 协议 + 云台 JSON 协议 | 真机/外部运控接口参考 | 许可需核实 |

### 4.3 对训练的价值

先对齐项目训练侧的判据（计划 §P0–P9 与规则 T/S/C/X）：**新增可训练任务必须有训练源码**（`assets/robots/<id>/training/source/<task>/` 的 env_cfg / mdp / runner），否则只能落 profile、不能登记部署。

**结论：A/B/C 三份发行物都不含训练源码 → 不能新增任何可训练任务；但它们能补上训练侧最缺的三类输入：参数真值、行为规格、任务判据。**

| # | 训练侧输入 | 来源 | 具体用途 | 合规 |
|---|---|---|---|---|
| T1 | **actuator / 限位 / 零位真值** | B `*-user-parameters.yaml`：Kp/Kd（关节/WBC/FSM）、`JPos_limit_low/high`、`jointVelocityLimit`、`*_side_sign`、`*_offset`、`stand/liedown/default` 姿态、`body_height`、步态周期 | 与 A 的 MJCF（`range` / `axis` / `pos` / `actuatorfrcrange` / `frictionloss`）和项目 `contracts/` + [`30_参数标准/机器人参数单一真值表.md`](../30_参数标准/机器人参数单一真值表.md) 做**三方对照**；不一致即暴露真值表缺陷。纯离线、可单测 | ✅ 只读参数 |
| T2 | **观测/动作口径旁证** | B `*-rl_onnx_config.yaml` + A 的 IC 文档（内外参、FLU 坐标、传感器频率） | 推 `obs_dim`/`action_dim` 量级与归一化惯例（如 `cmpc_x_vel 3.0` 对应命令上限、`ang_vel` 缩放）→ 用于 P5/P6 契约自查 | ⚠️ 仅旁证，不可当规格来源 |
| T3 | **任务分类与触发枚举** | B 行为清单 + A 动作库命名 | 细化 `task_type`（velocity/stand/balance/imitation/acrobatics/parkour…）与 `trick_triggers`（backflip/frontflip/sideflip/flipover/jump/moonwalk）取值域，避免自造类别 | ✅ |
| T4 | **估计器路线与基线** | B 的 `policy_*`/`odom_*` 成对 + `encoder`/`actor` 拆分；C 的 FAST-LIO / NDT / GICP + UKF | 对应 `perception_observations.py` 的 `obs_source: estimator/proxy/history`：B 给「学习型估计器与策略分离」的工程范式（与项目 go1 的 HIMLoco **同族**），C 给**几何/滤波基线**——学习型估计器的对照基准 | ✅ |
| T5 | **任务判据与课程** | C 的 costmap / BT / collision_monitor / waypoint_follower + 障碍消息 + `map/` 场景 | 为目标驱动任务写成功判据（到达 / 避障 / 超时）与课程（静态→动态障碍、单点→多点巡航），与计划 §3 无头验收判据对齐 | ✅ 设计参考 |
| T6 | **模型与物理素材** | A 的 9 族 MJCF（含月面低重力地形、轮足/机械臂形态） | 新机型候选与地形课程素材 | ⚠️ 新机型须过规则 T（有训练源）才可入库 |
| T7 | **不可用于训练** | B 的 165 个加密策略、A 的 UeSim 运行时、C 的 ROS2 运行时 | 不能当教师/目标策略（规则 S）；不能进 CI 与自动验收（GPU / ROS2 依赖） | ❌ |

**训练侧可立即做的三件事**（都不引依赖、不违反规则）：

1. **T1 三方对照校验器**：把 B 的 `JPos_limit_*`、`*_side_sign`、`*_default_pos`、`*_offset` 与 A 的 MJCF `range`/`axis`/`pos` 及项目 `contracts/` 对齐，做成只读校验（`tools/` 校验器 + 测试）→ 直接产出「参数单一真值表」的证据链。
2. **T3 枚举收敛**：用 B 的行为清单补齐 `task_type` / `trick_triggers` 的取值域，替代拍脑袋发明分类。
3. **T4 基线登记**：在无头验收器里为估计器类观测（`base_lin_vel` 的 estimator/proxy/history）登记基线口径，把 C 的几何滤波量级作为参照。

**不能做**：用 B 的加密策略当训练目标/教师（§6.1）；把 A/C 拉进 CI；用 B 的导出配置替代训练源码去登记部署策略（违反规则 T/S）。

## 5. 本次落地的提取（代码改动）

| 文件 | 改动 | 作用 |
|---|---|---|
| `backend/sensor_suite.py`（新增） | **4 套预设 / 12 条传感器声明**（default / lidar_dual / mid360_slam / zg）+ `/api/sensors/kinds`、`/api/sensors/presets`、`/api/sensors/presets/{name}` | 把 MATRiX 的传感器声明变成控制面契约；每 kind 标注 `proprioceptive` / `exteroceptive`。**已剔除 5 项非 RL 口径声明**：4 个平台成像变体（`fisheye` / `infrared` / `panorama` / `ptzrgb`，鱼眼 210°/红外/全景/云台）与 `gps`（只服务室外全局定位，无消费方）；平台侧要投影/可视化直接读上游 `sensors/*.json`，kinds 收敛为 **imu / odom / rgb / depth / lidar 五类** |
| `backend/api_complete.py` | 注册 `sensor_suite_router` | 端点生效 |
| `backend/perception_observations.py` | 新增 `lidar_height_scan`（width=180，`align_with=heightfield`）；`sensor` 注释补 `lidar` | 雷达点云→高度扫描的观测入口，网格与内置 heightfield 同规格，便于逐格对齐回归 |
| `tools/matrix_sensor_corpus.py`（新增） | 容器探测（魔数/版本/帧大小/正体偏移/帧数/时长）+ `--selftest` + `--json`，退出码 0/1/2 | 语料可验证、缺失可降级；不写猜测性载荷解析 |
| `web/advanced_sim.html` | 新增「外部传感器套件」面板，读 `/api/sensors/presets(+/default)` | 高级仿真页从文案升级为数据驱动 |
| `backend/test_perception_observations.py` | 新增 `MatrixSensorSuiteTests` / `MatrixSensorCorpusTests` / `SensorKindCoverageTests`（模块共 19 例） | 该测试模块已在 `.cnb.yml` 的 unit-tests 清单中，改动即被 CI 覆盖 |
| `.gitignore` | 新增 `matrix-v1.0.13/`、`matrix-robot-mc-*/`、`genisom-roamerx-open/`、`amithyst-matrix/` | 外部发行物与参考仓永不入库 |
| `backend/height_scan.py`（新增） | 上游 **187 点**高度扫描网格契约（17×11 / 0.1 m / x 主序，机身系）+ 点云与射线两条取数路径 + `align_height_scans` + `/api/perception/height-scan/{grid,selftest,selftest-map}` | 把「外部雷达 ↔ 内置 heightfield」的逐格对齐回归变成可跑代码；`selftest-map` 直接用 `backend/terrain_gen` 的 5 种地形 |
| `backend/perception_observations.py` | `heightfield` / `lidar_height_scan` 宽度 **180 → 187**，补网格 meta（shape/order/spacing/来源） | 修正目录与真实网格不一致：仓内训练源多处声明 `terrain_dim = 187`（go2 `contract.py:22`、m20 `constants.py:159`） |
| `web/advanced_sim.html` | 新增「高度扫描对齐」「相机投影与目标判定」两个面板 | 高级仿真页可直接看到自检结论 |
| `backend/camera_projection.py`（新增） | 内参解析（MATRiX 惯例：fov 为水平视场、fx=0/cx<0 表示未标定 → 按针孔与像素质心推导）、FLU→光学系外参、点云/目标框投影、深度反投影、到达与可见性判定 + `/api/perception/projection/{sensors,selftest,project}`；另含 **MuJoCo 原生 `<camprojection>` 交叉校验**（`mujoco_camera_pose` + `/mujoco-check`） | 把 §4.1 #3（LiDAR→相机投影）与 #4（目标判定/bbox）落成可离线单测的几何层；投影数学经**引擎独立实现**验证：默认挂载 7 点 max 1.5e-5 px、yaw=90 挂载 3 点 max 1.9e-4 px（阈值取 MuJoCo sensordata 的 float32 ULP），并报告主点约定差异（MuJoCo `res/2` vs 本模块 `(W−1)/2`） |
| `backend/perception_observations.py` | 新增观测项 `base_pos_odom`（odom，3 维）；补训练侧高频缺口 **`joint_torque`(12，`jointactuatorfrc`)、`contact_force`(4，netforce)、`wheel_vel`(4，`.*_wheel_joint`，轮足专属)**；`gps_position` 与硬件 `gps` 声明按同一口径剔除 | 回答「odom 能否接入」并补齐观测目录与训练源的差距（观测项 10 → 13，其中 3 项是「引擎/训练源已有、仅缺登记」） |

## 6. 未提取 / 不建议

1. **不导入加密运控模型**（165 件）——违反规则 S，且无法校验输入输出维度。
2. **不随项目分发 `UeSim` 二进制、`Engine/`、`Content/Paks/`**——许可未核实且体量 4.7G。
3. **不写点云载荷解析器**——载荷布局无文档且实测为非纯 float 排布（见 2.4），猜测实现会污染 obs 契约。
4. **不把 UeSim 纳入自动验收**——需 GPU + 非 root，容器与 CI 均不满足（见 2.2）。
5. **不绕过 B 的模型加密（明确拒绝，非「暂缓」）**：`onnx_model_crypto/` 是厂商有意设置的加密保护，破解属规避技术保护措施并违反其发布条款，本项目不参与（含分析加密算法、寻密钥、内存转储等间接手段）。替代路径见下表。
6. **不把 C 的 ROS2 运行时引入项目依赖**——Humble/Ubuntu 22.04 专属，且与项目「控制面不 import 训练栈、CI 无 GPU」的约束冲突；只取设计与参数参考。

### 6.1 关于「解密模型」的替代路径

| 需求 | 合规做法 |
|---|---|
| 知道模型吃什么 / 吐什么 | 用 B 的 **明文导出规格** `build/export/config/<机型>/*-rl_onnx_config.yaml`（行为→模型注册表）与 `*-user-parameters.yaml`（限位/增益/指令上限），配合 A 的传感器与坐标文档做契约对照 |
| 需要权重本身 | 向 ZsiBot / GENISOM 申请授权或索取明文 ONNX 版本（其 README 指向独立发布渠道 `GENISOM-AI/MATRiX_Robot_MC`） |
| 需要可入库、可验收的策略 | 在项目自己的训练流水线（`assets/robots/*/training/source`）重训等价策略——符合规则 S，产物可审计、可复现、可登记 |

## 7. 复现命令

```bash
# 1) 校验分卷
cd matrix-v1.0.13 && sha256sum -c SHA256SUMS

# 2) 解压
cat MATRiX_v1.0.13.tar.gz.part-* | tar -xzf - -C extracted

# 3) 语料容器探测（含合成自检，不需要发行包）
python3 tools/matrix_sensor_corpus.py --selftest
python3 tools/matrix_sensor_corpus.py --json

# 4) MJCF 加载实测（需要 mujoco）
/tmp/mjlab_cpu_venv/bin/python - <<'EOF'
import os, mujoco
base = "matrix-v1.0.13/extracted/MATRiX_v1.0.13/UeSim/Content/model"
for rel in ("xgb/xgb.xml", "go2/go2.xml", "zgwsarm/zgwsarm.xml"):
    os.chdir(os.path.join(base, os.path.dirname(rel)))
    m = mujoco.MjModel.from_xml_path(os.path.basename(rel)); d = mujoco.MjData(m)
    for _ in range(200): mujoco.mj_step(m, d)
    print(rel, "nq=", m.nq, "nu=", m.nu)
EOF

# 5) 契约与测试
curl -s localhost:8765/api/sensors/presets | head -c 400
python -m unittest backend.test_perception_observations
```

```bash
# 6) B：下载 + 校验 + 解压（sha256 由 GitHub API 的 asset digest 给出）
cd matrix-robot-mc-v0.6.4
echo "5ac4d58793045936f4e1fe78e311473af7cd5f99aed8b9b1779d944dc5ded72b  MATRiX_Robot_MC-v0.6.4-linux-x86_64.tar.gz" | sha256sum -c -
tar -xzf MATRiX_Robot_MC-v0.6.4-linux-x86_64.tar.gz
cat MATRiX_Robot_MC-v0.6.4-linux-x86_64/build/export/config/xg/xg-user-parameters.yaml

# 7) C：只读克隆 + 静态核对（本机无 ROS2，不能构建）
git clone --depth 1 --single-branch https://github.com/zsibot/genisom_roamerx_open.git genisom-roamerx-open
grep -n "RMW_IMPLEMENTATION\|ROS_DOMAIN_ID" genisom-roamerx-open/README_matrix和zsibot_roamerx_lite适配.md | head
grep -rn "lid_topic\|imu_topic" genisom-roamerx-open/src/slam/src/config/config.yaml
```

## 8. 结论

MATRiX 生态（A 运行时 / B 运控 / C 导航栈）对项目的**可迁移价值是「声明、规格与语料」，不是「运行时」**：

- **对高级仿真**：A 的传感器 schema 与语料容器事实**已落地**（`backend/sensor_suite.py` + `/api/sensors/*` + 高级仿真页面板 + `tools/matrix_sensor_corpus.py`）；C 的 costmap/BT/MPPI/障碍消息与 SLAM 链路、A 的投影与 bbox 工具是下一步的参照与接入对象；`lidar_height_scan ↔ heightfield` 的逐格对齐回归已具备入口与语料。
- **对训练**：三份发行物**都不含训练源码**，因此不能新增可训练任务或登记部署策略（规则 T/S）；它们的价值在于三类输入——B 的 `user-parameters`（限位/零位/增益真值，可与 A 的 MJCF 与项目契约三方对照）、B 的行为清单（`task_type` / `trick_triggers` 枚举）、C 的导航与 SLAM 栈（任务判据、课程、估计器基线）。
- **不可复用或不该复用**：UE5/ROS2 运行时（GPU / Ubuntu 22.04 门槛，进不了 CI）、B 的加密策略（明确不解密）、点云载荷（无公开布局）。

已完成与下一步：

- ① ~~把 A 的投影（LiDAR→相机）与 bbox 工具接进高级仿真（§4.1 #3/#4）~~ —— **已落地**（`backend/camera_projection.py` + 页面面板，6 例几何自检；内参推导 / 光轴→主点 / 视场边缘 / 遮挡剔除 / 框投影 / 深度往返 / 到达与可见性）。
- ② ~~用 A 的语料做 `lidar_height_scan ↔ heightfield` 对齐回归~~ —— **已落地**（`backend/height_scan.py`，网格修正为 187，合成 4 例 + 项目地形 5 种全部在坡度推导上界内；语料载荷未解码前，点云侧先用合成/地形采样点验证链路）。
- ③ **待做**：T1 参数三方对照校验器（B 的 `user-parameters` ↔ A 的 MJCF ↔ 项目 `contracts/` + 真值表，离线可单测）。
