# unitree_go2_edu_movement — 参考资源

> **来源**：`00_open/unitree_go2_edu_movement/`　｜　**类型**：目标驱动视觉伺服参考（Python / DDS）
> **关联机型**：unitree_go2（宇树 Go2 四足）
> **定位**：Go2 EDU 视觉对接流水线（unitree_sdk2py）：AprilTag 位姿解算 + 滑窗滤波 + 梯形速度规划 + 三模式停靠判据，含前视鱼眼内参与 DDS 收发范式
> **收录**：31 个文件 / 475 KB（其中推理策略/模型文件 0 个）
> **已省略**：0 个文件 / 0 B（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **部署与推理**（2 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **文档与其它**（29 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （7 个文件）
auto_yolo_v2/  （8 个文件）
    (直接文件)/
mobile_manipulation/  （9 个文件）
    (直接文件)/
trapezoidal_movement/  （7 个文件）
    (直接文件)/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 26 |
| `.md` | 3 |
| `(无扩展名)` | 1 |
| `.sh` | 1 |

## 文件索引（项目内相对路径）

```text
.gitignore
auto_yolo_v2/CLAUDE.md
auto_yolo_v2/arm_controller.py
auto_yolo_v2/base_controller.py
auto_yolo_v2/camera_streamer.py
auto_yolo_v2/debug_streamer.py
auto_yolo_v2/dog_detection_worker.py
auto_yolo_v2/main_state_machine.py
auto_yolo_v2/vision_core.py
dock_control.py
go2_io.py
main.py
mobile_manipulation/arm_control.py
mobile_manipulation/camera_subsystem.py
mobile_manipulation/dock_control.py
mobile_manipulation/go2_io.py
mobile_manipulation/pink_detector.py
mobile_manipulation/pipeline.py
mobile_manipulation/pose_filter.py
mobile_manipulation/run.sh
mobile_manipulation/vision_pose.py
old_pipeline.py
pose_filter.py
trapezoidal_movement/POSE_CONTROL_README.md
trapezoidal_movement/README.md
trapezoidal_movement/camera_intrinsics.py
trapezoidal_movement/control_pose.py
trapezoidal_movement/tag_approach_trapezoidal.py
trapezoidal_movement/tag_approach_trapezoidal_v2.py
trapezoidal_movement/tag_approach_trapezoidal_v3.py
vision_pose.py
```

## 导入边界与关键数值（人工补充，重新同步时需重做）

- **收录口径**：上游很小（31 文件 / 475 KB），**全量收录**（工具内置跳过的 `.vscode/` 除外）。
- **许可**：上游**无 LICENSE** → 仅作内部参考。运行依赖 `unitree_sdk2py`(CycloneDDS) / OpenCV 鱼眼去畸变 / `pyapriltags` / `ultralytics`（YOLO 权重运行时下载，未随仓）。
- **最能直接用于本工作台契约交叉校验的数值**：
  - **Go2 前视鱼眼内参**（1920×1080）：`fx 1248.95 / fy 1247.95 / cx 957.86 / cy 530.82`，畸变 `D = [-0.0463, -0.2155, 0.4554, -0.3779]`；臂载相机（1280×720）`fx 1020.78`。
  - 速度上限 `max_vx 0.55 / max_vy 0.30 / max_vyaw 0.6`；控制增益 `k_dist 1.4 / k_lat 1.0 / k_yaw 1.6`；`target_dist 1.0 m`；**到达容差 3 cm / 3 cm / 2.5°**。
  - 状态机阈值：丢帧 `short_loss 0.7 s` / `long_loss 2.5 s`；`yaw_first 15°`；位姿跳变门 `yaw > 70° 且 dist > 0.35 m`；滤波 `SLERP/LERP EMA α = 0.25`；主循环 30 Hz。
  - 坐标约定 **base FLU（x 前、y 左、yaw 逆时针）** —— 与 `backend/camera_projection.py` / `backend/height_scan.py` 的约定一致。
  - DDS 话题：`rt/sportmodestate`（`position[0..1]` + `imu_state.rpy[2]` 取 yaw）、`rt/lowstate`、`rt/lowcmd`、`rt/wirelesscontroller`；取图走 `VideoClient.GetImageSample`（非 ROS 图像话题）；启动序列 MotionSwitcher → `normal` → `StandUp` → `BalanceStand`。
  - 梯形规划：`v = min(accel·cruise, sqrt(2·decel·remaining))`；P1 `MAX_VX 0.7`；P2 `MAX_VX 0.3 / KP_VY 1.9 / KP_VYAW 1.5`；`fronto_yaw = atan2(R[0,2], R[2,2])`。
- **注意**：`trapezoidal_movement/README.md`(58 KB) 是 SDK 文档原文；`trapezoidal_movement/` 内有硬编码 `/home/unitree/...` 路径；检测对象为 golf ball / 粉色方块（与项目球类任务同族，可作目标判定参考）。
