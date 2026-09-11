# Deep Robotics M20 — Isaac Sim 导航仿真平台使用说明

---

## 目录

1. [平台概述](#1-平台概述)
2. [文件结构说明](#2-文件结构说明)
3. [环境依赖](#3-环境依赖)
4. [快速启动](#4-快速启动)
5. [控制模式详解](#5-控制模式详解)
   - [键盘模式（--keyboard）](#51-键盘模式---keyboard)
   - [自主导航模式（--nav）](#52-自主导航模式---nav)
   - [外部速度模式（--cmd_vel）](#53-外部速度模式---cmd_vel)
6. [ROS2 传感器话题](#6-ros2-传感器话题)
7. [地图与路径规划](#7-地图与路径规划)
8. [关键参数速查表](#8-关键参数速查表)
9. [常见问题排查](#9-常见问题排查)

---

## 1. 平台概述

本平台基于 **NVIDIA Isaac Sim + IsaacLab** 构建，为 Deep Robotics M20 轮腿机器人提供仿真推理与导航验证环境。核心功能包括：

- 加载训练好的 **ONNX 策略模型**，在仿真中实时推理
- 通过 **ROS2 Bridge** 向外发布相机、激光雷达、IMU 和里程计数据
- 支持三种互斥控制模式：**键盘遥控 / A\* 自主导航 / 外部 cmd\_vel 接入**
- 内置 **Hybrid A\*** 全局规划器 + **Pure Pursuit** 局部路径跟踪控制器

---

## 2. 文件结构说明

| 文件 | 职责 |
|------|------|
| `m20_nav_app.py` | 主入口脚本，包含 CLI 解析、主循环、路径规划器、路径跟踪控制器 |
| `m20_perception_env_cfg.py` | 仿真场景配置（仓库 USD 加载、传感器挂载、随机化关闭） |
| `m20_sensors_cfg.py` | 传感器挂载点坐标与相机/激光雷达/IMU 参数配置 |
| `ros2_bridge_graph_m20.py` | Isaac Sim OmniGraph ROS2 Bridge 构建（话题、TF、传感器发布） |
| `ros2_cmd_vel_bridge.py` | `/cmd_vel` ROS2 订阅器，线程安全，带超时自动清零 |
| `__init__.py` | 向 Gymnasium 注册四个仿真环境 ID |

---

## 3. 环境依赖

| 组件 | 版本要求 |
|------|----------|
| Isaac Sim | 5.1.x（含 `isaacsim.ros2.bridge`） |
| IsaacLab | 与 Isaac Sim 配套 |
| ROS2 | Humble 或 Jazzy（需要 `rclpy`） |
| Python 包 | `onnxruntime`, `numpy`, `torch`, `Pillow`, `PyYAML` |
| 可选（加速） | `cupy`（GPU 加速地图膨胀/距离变换） |
| 地图文件 | ROS 标准 `.yaml` + `.pgm` 占用栅格地图 |
| 策略文件 | `.onnx` 格式导出的策略网络 |

---

## 4. 快速启动

---

## 4.1 一键启动脚本（推荐）

为了简化环境加载与启动流程，项目提供了 `start_m20_nav.sh` 一键启动脚本。

### 使用方法

在 **Isaac Lab 根目录** 下执行：

```bash
chmod +x start_m20_nav.sh
./start_m20_nav.sh
```

### 脚本功能说明

该脚本自动完成以下步骤：

1. **加载 ROS2 环境**
   - 自动 source Jazzy 工作空间：
     - `jazzy_ws`
     - `isaac_sim_ros_ws`

2. **路径检查**
   - 检查主程序 `m20_nav_app.py` 是否存在
   - 检查 ONNX 模型路径是否正确

3. **启动仿真**
   - 默认启动：
     - `Flat-Deeprobotics-M20-v0` 环境
     - `--cmd_vel` 控制模式
     - 启用 ROS2 Bridge
     - 实时运行模式

### 默认启动等效命令

```bash
python scripts/reinforcement_learning/rsl_rl/m20_nav_app.py \
    --task=Flat-Deeprobotics-M20-v0 \
    --onnx=exported/m20_new_policy.onnx \
    --cmd_vel \
    --enable_ros2_bridge \
    --real-time
```

### 自定义修改

你可以直接编辑 `start_m20_nav.sh`：

- 修改任务环境（如切换到感知导航）：
```bash
--task=PerceptionFixedObstacle-Deeprobotics-M20-v0
```

- 修改控制模式：
```bash
--nav
# 或
--keyboard
```

- 添加导航目标：
```bash
--goal_x 5.0 --goal_y -3.0
```

### 常见错误

- **找不到脚本路径**
  - 请确保在 Isaac Lab 根目录执行

- **ONNX 文件不存在**
  - 检查 `exported/m20_new_policy.onnx` 是否存在

- **ROS2 未加载**
  - 确认工作空间路径正确



所有模式均通过 `m20_nav_app.py` 启动，使用 `--task` 指定仿真环境：

```bash
# 通用格式
python m20_nav_app.py \
  --task PerceptionFixedObstacle-Deeprobotics-M20-v0 \
  --onnx /path/to/policy.onnx \
  [控制模式参数] \
  [其他参数]
```

> **注意**：`--keyboard`、`--nav`、`--cmd_vel` 三者**互斥**，只能选其一。

---

## 5. 控制模式详解

### 5.1 键盘模式 `--keyboard`

纯手动遥控，用于建图阶段或策略行为观察。

```bash
python m20_nav_app.py \
  --task PerceptionFixedObstacle-Deeprobotics-M20-v0 \
  --onnx /path/to/policy.onnx \
  --keyboard
```

**键位映射（Isaac Sim 窗口获得焦点时生效）：**

| 按键 | 功能 |
|------|------|
| `↑` / `W` | 前进 |
| `↓` / `S` | 后退 |
| `←` / `A` | 左平移（侧移） |
| `→` / `D` | 右平移（侧移） |
| `N` | 左转（yaw+） |
| `M` | 右转（yaw-） |
| 松键 | 速度归零 |

---

### 5.2 自主导航模式 `--nav`

加载 YAML 占用栅格地图，使用 **Hybrid A\*** 规划从当前位置到目标点的路径，并由 **Waypoint Follower** 实时跟踪执行。键盘可随时接管。

```bash
python m20_nav_app.py \
  --task PerceptionFixedObstacle-Deeprobotics-M20-v0 \
  --onnx /path/to/policy.onnx \
  --nav \
  --map_yaml /path/to/map.yaml \
  --goal_x 5.0 \
  --goal_y -3.0 \
  --inflation_radius 0.8
```

**运行时键盘指令：**

| 按键 | 功能 |
|------|------|
| `K` | **规划并立即执行**（以当前位置为起点，重新规划到目标点并启动） |
| `G` | **仅规划**（不启动自动跟踪，可预览路径） |
| `C` 或 `Space` | **取消自动导航**，切换为键盘手动接管 |
| `↑↓←→` / `N` / `M` | 键盘手动接管（松键后若仍有路径可按 `K` 恢复） |

**自动导航控制参数（在脚本顶部修改）：**

```python
AUTO_MAX_VX           = 2.00   # 最大前进速度 (m/s)
AUTO_MAX_VY           = 1.00   # 最大侧移速度 (m/s)
AUTO_MAX_WZ           = 1.50   # 最大偏航角速度 (rad/s)
AUTO_REACH_TOL        = 0.40   # 到达判定半径 (m)
AUTO_SLOWDOWN_RADIUS  = 0.80   # 减速区半径 (m)
AUTO_KP_FWD           = 1.000  # 前向速度比例增益
AUTO_KP_YAW           = 1.20   # 偏航角速度比例增益
AUTO_STUCK_DIST       = 0.30   # 卡死检测位移阈值 (m)
AUTO_STUCK_STEPS      = 180    # 卡死检测步数
```

---

### 5.3 外部速度模式 `--cmd_vel`

订阅 ROS2 `/cmd_vel` 话题并注入到策略命令管理器，用于接入外部导航栈（如 Nav2）或进行速度响应测试。

```bash
python m20_nav_app.py \
  --task PerceptionFixedObstacle-Deeprobotics-M20-v0 \
  --onnx /path/to/policy.onnx \
  --cmd_vel \
  --cmd_vel_topic /cmd_vel \
  --max_lin_x 2.0 \
  --max_lin_y 1.0 \
  --max_ang_z 1.5
```

**测试发布速度指令：**

```bash
# 前进 0.5 m/s，同时左转 1.0 rad/s
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist \
  '{linear: {x: 0.5}, angular: {z: 1.0}}'

# 停止
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist '{}'
```

> **超时机制**：若超过 `1.2 秒` 未收到新消息，速度自动清零。可在 `ros2_cmd_vel_bridge.py` 中修改 `timeout_s` 参数。

---

## 6. ROS2 传感器话题

启动后（`--enable_ros2_bridge` 默认开启），以下话题自动发布：

| 话题 | 消息类型 | 说明 |
|------|----------|------|
| `/clock` | `rosgraph_msgs/Clock` | 仿真时钟 |
| `/odom` | `nav_msgs/Odometry` | 机器人里程计 |
| `/m20/front_camera/rgb` | `sensor_msgs/Image` | 前向 RGB 相机（360×360） |
| `/m20/front_camera/camera_info` | `sensor_msgs/CameraInfo` | 相机内参 |
| `/m20/front_lidar/points` | `sensor_msgs/PointCloud2` | 前向 LiDAR 点云 |
| `/m20/rear_lidar/points` | `sensor_msgs/PointCloud2` | 后向 LiDAR 点云 |
| `/m20/imu/data` | `sensor_msgs/Imu` | IMU 数据 |
| `/tf` | `tf2_msgs/TFMessage` | 传感器静态 TF |

**传感器外参（相对 base\_link）：**

| 传感器 | 位置 (x, y, z) m |
|--------|-----------------|
| 前向相机 | (0.376, 0.0, 0.037) |
| 前向 LiDAR | (0.350, 0.0, 0.113) |
| 后向 LiDAR | (-0.350, 0.0, 0.113) |
| IMU | (0.063, -0.027, -0.044) |

---

## 7. 地图与路径规划

### 地图格式（ROS 标准）

`map.yaml` 示例：

```yaml
image: full_warehouse.pgm
resolution: 0.05          # 米/像素
origin: [-10.0, -10.0, 0.0]  # [x, y, yaw]
negate: 0
occupied_thresh: 0.65
free_thresh: 0.196
```

### A\* 规划器关键参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--inflation_radius` | 0.8 m | 障碍物膨胀半径，需 ≥ 机器人半径 |
| `ASTAR_CLEARANCE_SAFE_DIST` | 1.8 m | 保持与障碍物的安全距离 |
| `ASTAR_CLEARANCE_COST_WEIGHT` | 6.0 | 靠近障碍物的代价权重（越大路径越保守） |
| `ASTAR_ALLOW_DIAGONAL` | True | 允许对角线移动（更短路径） |
| `OCC_MAP_TREAT_UNKNOWN_AS_OCCUPIED` | True | 未知区域视为障碍 |

---

## 8. 关键参数速查表

### 启动参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--task` | — | Gym 环境 ID（必填） |
| `--onnx` | — | ONNX 策略文件路径 |
| `--onnx_cpu` | False | 强制使用 CPU 推理 |
| `--num_envs` | 1 | 并行环境数量 |
| `--real-time` | False | 启用实时步长限速 |
| `--max_lin_x` | 2.0 | 最大线速度 x (m/s) |
| `--max_lin_y` | 1.0 | 最大线速度 y (m/s) |
| `--max_ang_z` | 1.5 | 最大角速度 z (rad/s) |
| `--video` | False | 录制仿真视频 |

### 注册的 Gym 环境 ID

| 环境 ID | 说明 |
|---------|------|
| `Flat-Deeprobotics-M20-v0` | 平地环境 |
| `Rough-Deeprobotics-M20-v0` | 崎岖地形环境 |
| `RoughFixedObstacle-Deeprobotics-M20-v0` | 崎岖地形 + 固定障碍物 |
| `PerceptionFixedObstacle-Deeprobotics-M20-v0` | 仓库场景 + 传感器（推荐用于导航测试） |

---

## 9. 常见问题排查

**Q: 启动时报 `extension not found: isaacsim.ros2.bridge`**  
A: 确认 Isaac Sim 已启用 ROS2 扩展，在 Isaac Sim 扩展管理器中搜索并启用 `isaacsim.ros2.bridge`。

**Q: `--nav` 模式启动后机器人不动**  
A: 需要先按 `K` 键触发规划并启动。确认 `--map_yaml` 路径正确，且目标点 `(goal_x, goal_y)` 在地图可达范围内。

**Q: A\* 规划失败，报目标点在障碍物内**  
A: 减小 `--inflation_radius`，或检查目标坐标是否正确（世界坐标系 vs 地图坐标系）。

**Q: `/cmd_vel` 模式下机器人没有响应**  
A: 检查话题名称是否匹配（`--cmd_vel_topic`），以及 `rclpy` 是否已正确安装在当前 Python 环境中。

**Q: 传感器话题发布了但没有数据**  
A: 确认仿真已经开始播放（点击 Isaac Sim 界面的 Play 按钮），LiDAR 需要 RTX 渲染器支持，确认 GPU 驱动正常。

**Q: 策略推理结果异常（机器人乱抖）**  
A: 检查 ONNX 模型与当前环境配置的观测维度是否匹配，确认策略是用 `PerceptionFixedObstacle` 任务对应的 obs 空间训练的。