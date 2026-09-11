# Himdog 框架文档

> 主要记录 `dog_policy_test`（RL 推理节点）与 `dog_nav`（任务赛导航与视觉）两个核心功能包的架构和数据流。

## 项目结构

```
himdog/src/
├── dog_control/          # 底层硬件控制节点（C++）
│   ├── src/hardware/     #   main.cpp — 电机通信、PD控制、发布 /motor_feedback
│   └── include/          #   leg_model.h — 关节映射、减速比、offset 常量
│
├── dog_policy_test/      # ★ RL 策略推理节点
│   ├── src/
│   │   ├── dog_policy_test_5.cpp   # v5 — 三节奏分离
│   │   ├── dog_policy_test_9.cpp   # v9 — 命令渐变
│   │   ├── dog_policy_test_10.cpp  # v10 — v9 + 系统监控
│   │   ├── dog_policy_test_11.cpp  # v11 — v10 + 三种控制模式（键盘/joy/导航）
│   │   ├── dog_policy_test_12.cpp  # ★ v12 — v11 + 内置模型热切换（N/M 键）
│   │   ├── imu_dump.cpp            # IMU 数据 dump 工具
│   │   ├── motor_feedback_dump.cpp # 电机反馈 dump 工具
│   │   └── print_joint.cpp         # 关节调试工具
│   ├── policy/
│   │   ├── *.onnx                  # ONNX 模型文件
│   │   ├── good/                   # 推荐模型
│   │   └── old/                    # 历史模型
│   ├── config/
│   │   ├── policy_params.yaml      # ROS2 参数配置（test_11 及之前）
│   │   └── policy_params_12.yaml   # test_12 专用配置（含模型列表）
│   ├── include/
│   ├── scripts/
│   ├── CMakeLists.txt
│   └── package.xml
│
├── dog_nav/              # ★ 任务赛导航与视觉感知节点
│   ├── src/
│   │   ├── navigation_dog.cpp      # ★ 任务赛主节点（状态机 + BFS + 横移导航 + 取放 + 吸盘串口）
│   │   ├── record_points.cpp       # ★ 雷达定位打点工具（编号直跳 / 覆盖重录 / 退出保护）
│   │   ├── test_nav_movement.cpp   # 基础动作测试（原始版，纯P）
│   │   └── test_nav_pid.cpp        # ★ RL 底盘测试（两档 + 提前量 + 死区 + 稳态确认）
│   ├── include/dog_nav/
│   │   ├── field_path_planner.hpp  # BFS 路径规划（15节点邻接图 + 归位区逐边禁用）
│   │   └── delivery_planner.hpp    # 取放计划生成（备用，当前未被主节点使用）
│   ├── config/
│   │   ├── task_race_point.yaml    # 场地坐标 + 导航参数 + 吸盘串口参数
│   │   └── contorl.yaml            # （空文件，待清理）
│   ├── msg/DogNavCommand.msg       # 导航命令（vx/vy/wz/height/model_path）
│   ├── resource/
│   │   ├── test_serial.py          # 吸盘舵机手动调试（协议参考）
│   │   ├── vision/
│   │   │   ├── model/best.rknn         # YOLO RKNN 模型（上位机）
│   │   │   ├── model/best.pt           # YOLO PyTorch 模型（电脑测试）
│   │   │   ├── d435i_stream.py         # ★ D435i 推流到 Foxglove + shm 喂帧（独占相机）
│   │   │   ├── d435i_client.py         # ★ 从 shm 取帧的客户端（solver/box_detector 用）
│   │   │   ├── box_detector_rknn.py    # 物资箱检测（RKNN，scan_all 模式）
│   │   │   ├── box_detector_pt.py      # 物资箱检测（PyTorch，RealSense）
│   │   │   ├── solver.py               # 算术题 OCR + mod4 求解 + 语音播报
│   │   │   ├── box_detector_config.json
│   │   │   ├── audio/{0-3}.mp3         # 播报音频（4 个归位区）
│   │   │   └── test_ocr_*.jpg          # OCR 测试图
│   ├── test/
│   │   ├── test_bfs.py             # 路径验证（含逐边禁用场景）
│   │   ├── test_place_turn.py      # 转身角度验证（含转圈倒车）
│   │   └── test_ocr.py             # OCR 测试
│   ├── map/scans_task.pcd          # 场地点云
│   ├── CMakeLists.txt
│   └── package.xml
│
├── dm_imu/               # DM IMU 驱动节点
└── README.md              # 本文件
```

---

## dog_policy_test 版本演进（整体结构对比）

### 总览表

| 版本 | 文件 | 关键特性 |
|------|------|---------|
| v5 | `dog_policy_test_5.cpp` | 三节奏分离（传感器回调 + policy_timer + publish_timer） |
| v9 | `dog_policy_test_9.cpp` | v5 + 命令渐变（速度指令平滑过渡） |
| v10 | `dog_policy_test_10.cpp` | v9 + **独立推理线程**（sleep_until 精确节拍）+ SystemMonitor 线程 |
| v11 | `dog_policy_test_11.cpp` | v10 + 三种控制模式（键盘/joy手柄/导航） |
| **v12** | `dog_policy_test_12.cpp` | ★ **v11 + YAML 模型列表 + N/M 键热切换（model_mutex_ 保护）** |

---


### v10：独立推理线程 + 系统监控

v10 在 v9（命令渐变）基础上做了**架构重构 + 新增监控**。

#### 架构变化：policy_timer → InferenceLoop 独立线程

v9 之前推理由 ROS `policy_timer`（wall_timer 50Hz）驱动。v10 改成**独立 `std::thread`**，用 `sleep_until` 精确控制节拍：

```
┌──────────────────────────────────────────────────────────┐
│ 传感器回调（~200Hz，被动触发，在 ROS Executor 线程上）       │
│   ImuCallback                                                   │
│     ├─ 加锁拷贝 → latest_imu_raw_                              │
│     ├─ 缓存 projected_gravity（缓存到 gravity_mutex_）          │
│     └─ ★ 倾倒检测：g_z > tipover_threshold                      │
│        → 发布 /emergency_stop → dog_control 失能所有电机         │
│        → shutdown_requested_ = true（延迟在 publish 里 shutdown）│
│   MotorFeedbackCallback ──→ 加锁拷贝 → latest_motor_raw_        │
└─────────────────────┬────────────────────────────────────┘
                      │
┌─────────────────────▼────────────────────────────────────┐
│ ★ InferenceLoop 独立线程（50Hz，sleep_until 精确节拍）          │
│   1. sleep_until(next_tick)，next_tick += 20ms                  │
│   2. 阻塞追赶保护：积压 tick 直接跳过，不补偿                    │
│   3. dt 自适应（clamp 到 0.01~0.05）                            │
│   4. scoped_lock 同时取 IMU + Motor 快照                       │
│   5. 滤波（gyro LPF + bias，motor pos/vel LPF + bias）          │
│   6. 命令渐变（ramp，用自适应 dt）                              │
│   7. 栈上构造单步 obs → 更新 6 帧历史                           │
│   8. ONNX 推理 → clip(±10) → action_delta 限制 → motor_cmd      │
│   9. RecordInferenceTime(dt) → 给 SystemMonitor（atomic）       │
└─────────────────────┬────────────────────────────────────┘
                      │
┌─────────────────────▼────────────────────────────────────────┐
│ publish_timer（200Hz / 5ms，ROS Executor 线程）                │
│   1. 安全 shutdown 检查（shutdown_requested_ → rclcpp::shutdown）│
│   2. CheckKeyRelease()：150ms 松手检测                         │
│   3. 读 last_motor_cmd_ → 输出端 LPF → 发布 /joint_states       │
│   4. 发布 /dog_state（诊断：cmd/grav/height）                   │
└──────────────────────────────────────────────────────────────┘
                      │
┌─────────────────────▼────────────────────────────────────┐
│ ★ SystemMonitor 线程（1Hz，nice=19 最低优先级）            │
│   读取：                                                     │
│     - CPU 总占用（/proc/stat 差值）                           │
│     - 内存占用（/proc/meminfo）                               │
│     - 进程 RSS（/proc/self/status）                           │
│     - CPU 温度（自动扫描 /sys/class/thermal/thermal_zone*）   │
│     - 推理耗时抖动 & 超时（atomic<double> 从推理线程采集）     │
│   超阈值 → ⚠️ 告警框，平时 5 秒一行简洁状态                    │
└────────────────────────────────────────────────────────────┘
                      │
┌─────────────────────▼────────────────────────────────────┐
│ 键盘线程（raw mode，独立线程）                              │
│   ★ 多键同时按：每键独立布尔状态 + 时间戳                     │
│   ★ 超时松手：150ms 无重复字符 → 归零对应轴                   │
│   支持 w+q（前进+左转）等组合                                │
└────────────────────────────────────────────────────────────┘
```

**四线程结构**（ROS Executor / Inference / Monitor / Keyboard）：

| 线程 | 频率 | 职责 | 优先级 |
|------|------|------|--------|
| ROS Executor | ~200Hz（回调驱动）+ 200Hz（publish_timer）+ 2Hz（print_timer） | 传感器回调 + 发布 + 松手检测 | 普通 |
| Inference | 50Hz | 滤波 + 推理 + motor_cmd | 普通 |
| SystemMonitor | 1Hz | 资源监控 + 告警 | nice=19（最低） |
| Keyboard | 轮询（5ms 间隔） | 按键状态 | 普通 |

#### SystemMonitor 设计要点

- **独立线程 nice=19**，绝不与推理线程争抢 CPU
- **lock-free 采集推理耗时**：推理线程用 `atomic<double>` 写入 `last_dt/max_dt`，Monitor 线程读取，零锁竞争
- **每秒重置 max_dt**（滑动窗口），统计 `overrun`（dt > 25ms 的次数，50Hz=20ms）
- **默认告警阈值**：CPU>85% / Mem>85% / Temp>75°C / 推理 dt>15ms / 周期超时>25ms

> **设计理由**：RK3588 上 ONNX 推理通常 5~10ms，但偶发 GC / 内存抖动可能到 20ms+，导致控制周期不稳。SystemMonitor 把这些异常显式打印出来，便于定位"卡顿是不是推理慢造成的"。

#### 倾倒保护（沿用 v7，细节增强）

- 检测在 `ImuCallback`（~200Hz），开销极小
- **触发后延迟 shutdown**：回调里只设 `shutdown_requested_=true`，真正的 `rclcpp::shutdown()` 放在 `publish_timer` 里调（避免在回调中 shutdown 导致的死锁）
- 支持**恢复**：倾倒后若连续 `kTipoverRecoveryFrames=50` 帧 g_z 恢复正常，保护解除（需手动按 y 重启 RL）

**优点**：独立推理线程节拍更精确（`sleep_until` 比 `wall_timer` 抗 ROS Executor 拥塞）；系统监控让板端资源问题可见；lock-free 采集不拖累推理。

---

### v12：内置模型热切换（★ 当前推荐版本）

基于 v11（三种控制模式），新增 **YAML 模型列表 + 运行时热切换**。架构上沿用 v10/v11 的四线程，额外增加 `model_mutex_` 保护 ONNX Session。

```
┌──────────────────────────────────────────────────────────┐
│ 传感器回调（~200Hz）— 同 v10/v11                              │
│   ImuCallback（拷贝 + 缓存 grav + 倾倒检测）                   │
│   MotorFeedbackCallback（拷贝）                                │
│   ★ NavCmdCallback（仅 control_mode_==2）                     │
│      ├─ NaN/Inf 校验丢弃                                       │
│      ├─ vx/vy/wz/height 限幅                                   │
│      └─ model_path 匹配 model_list_ → 记 nav_cmd_model_matched_idx_
└─────────────────────┬────────────────────────────────────┘
                      │
┌─────────────────────▼────────────────────────────────────┐
│ InferenceLoop 独立线程（50Hz）                                │
│   ... 滤波 / 命令渐变（按 control_mode_ 走键/joy/导航分支）...│
│   ★ 导航分支：若 nav 匹配的模型 ≠ 当前模型 → LoadModel()       │
│   ★ ONNX 推理整段包在 model_mutex_ 锁内                       │
│      （防止推理中途被键盘/导航换掉 Session）                    │
│   → 更新 last_motor_cmd_                                      │
└─────────────────────┬────────────────────────────────────┘
                      │
┌─────────────────────▼────────────────────────────────────┐
│ publish_timer（200Hz）— 同 v10/v11                            │
│   安全 shutdown / 松手检测 / 发布 /joint_states + /dog_state   │
└────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│ SystemMonitor 线程（1Hz，nice=19）— 同 v10                    │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│ 键盘线程（raw mode）                                          │
│   ... w/s/a/d/q/e/y/f/r/z/p ...                              │
│   ★ N：自动关 RL → SwitchModel(-1) → LoadModel → 提示按 y 重启 │
│   ★ M：自动关 RL → SwitchModel(+1) → LoadModel → 提示按 y 重启 │
└──────────────────────────────────────────────────────────┘
```

#### 核心功能：模型列表

在 `policy_params_12.yaml` 中配置模型列表（三个数组长度必须一致，否则 shutdown）：

```yaml
model_names:   ["good_1500", "good_3500", "46_1900", ...]
model_paths:   ["/home/zhy/.../model_1500.onnx", ...]
model_obs_dims: [46, 46, 46, ...]
default_model_index: 0   # 启动时默认加载的模型
```

读出后合并成 `std::vector<ModelEntry>`（`{name, path, one_obs_dim}`），不再单独保存原始数组。**添加新模型**：只需在 YAML 三个数组中各加一行，重新运行即可，无需改代码。

#### 运行时模型切换

| 触发 | 功能 |
|------|------|
| 按 **N** | 自动关 RL → 切到上一个模型 → 提示按 y 重启 |
| 按 **M** | 自动关 RL → 切到下一个模型 → 提示按 y 重启 |
| `/nav_cmd.model_path` | **不关 RL**，直接 LoadModel（下一拍用新模型预热 history） |

**`LoadModel(index)` 流程**（真正干活的函数）：
1. 越界 + 文件存在性检查
2. 调整 `one_step_obs_dim_` / `history_obs_dim_`（45↔46 切换）
3. **锁外**创建新 `Ort::Session`（耗时操作不在临界区）
4. **`model_mutex_` 锁内** `std::move` 替换 `ort_session_`（旧 Session 自动析构）
5. 更新 `input_shape_ = {1, history_obs_dim_}`
6. `ResetInferenceState()` → `FillStandingHistory()`（按新维度重新分配 `obs_history_`）

**`SwitchModel(direction)`**：只做环形索引（越界回绕）+ 打印横幅，然后调 `LoadModel`。

#### 安全设计

- **键盘切换会自动关 RL**（`rl_active_=false`），切完手动按 y 重启 —— 切换瞬间电机回到默认站姿，不会乱动
- **导航触发切换不关 RL**：切换瞬间 InferenceLoop 正在跑，靠 `model_mutex_` 串行化保证安全；history/actions 被清零，下一拍用新模型重新预热
- **InferenceLoop 推理整段持 `model_mutex_`**：避免推理跑到一半 Session 被换掉
- **Session 创建在锁外**：锁临界区只有 move 赋值，极短，不阻塞推理线程
- **obs_dim 切换**：`obs_history_` 是 `std::vector<float>`（非定长 array），切换时按新维度 `assign` 重分配

#### 导航模式联动

`NavCmdCallback` 收到 `/nav_cmd` 后：
1. NaN/Inf 校验丢弃
2. vx/vy/wz 限幅到 `nav_*_max_`，height 限幅到 `[nav_height_min_, nav_height_max_]`
3. 若 `model_path` 非空 → 遍历 `model_list_`，**同时比对 path 和 name**，命中记 `nav_cmd_model_matched_idx_`
4. InferenceLoop 导航分支里：若匹配模型 ≠ 当前模型 → 调 `LoadModel` 热切换
5. 0.5s 无新 `/nav_cmd` → 命令归零（`kNavCmdTimeoutSec`）

#### 运行命令

```bash
ros2 run dog_policy_test dog_policy_test_12 --ros-args \
  --params-file ./src/dog_policy_test/config/policy_params_12.yaml
```

#### 键盘快捷键（test_12 完整列表）

| 按键 | 功能 |
|------|------|
| y | 启动 RL |
| f | 关闭 RL |
| r | 重置（清零 history/actions） |
| w/s/a/d/q/e | 移动 / 转向 |
| z / p | 站起 / 蹲下 |
Y| **N / M** | **上一个 / 下一个模型** |
| Esc | 退出 |

---



## 整体数据流

```
┌─────────────────────┐     /motor_feedback (200Hz)     ┌─────────────────────────┐
│    dog_control       │ ─────────────────────────────→  │   dog_policy_test       │
│  (底层硬件控制)       │                                 │   (RL 策略推理)          │
│                     │  ←─────────────────────────────  │                         │
│                     │     /joint_states (200Hz)        │                         │
│                     │  ←─────────────────────────────  │                         │
│                     │     /emergency_stop (急停)        │                         │
└─────────────────────┘                                  └─────────────────────────┘
                                                          ↑ 键盘输入 (w/s/a/d/q/e)
                                                          ↑ IMU /imu/data
                                                          ↑ /nav_cmd (导航模式)
                                                                 ↑
┌─────────────────────┐     /lio/odom (里程计)           ┌─────────────────────────┐
│   Super-LIO         │ ─────────────────────────────→  │   dog_nav               │
│  (雷达激光惯导里程计) │                                  │   (任务赛导航)           │
└─────────────────────┘                                  │                         │
                                                          │  OCR → 两步扫描 → BFS   │
                                                          │  → 4 轮取放状态机       │
                                                          │  → 发布 /nav_cmd        │
                                                          └─────────────────────────┘
                                                                       │
                                                          popen 调用视觉脚本:
                                                          solver.py (OCR+mod4+播报)
                                                          box_detector_rknn.py (扫箱)
```

三个功能包的职责：
- **dog_control**：底层硬件，发 `/motor_feedback`，收 `/joint_states` 执行电机 PD，收到 `/emergency_stop` 失能所有电机
- **dog_policy_test**：RL 推理，收传感器 → ONNX → 发 `/joint_states`；导航模式收 `/nav_cmd` 转成速度指令
- **dog_nav**：任务赛大脑，收 `/lio/odom` 做定位反馈导航，状态机驱动 OCR/扫描/取放，发 `/nav_cmd` 指挥狗走

### /emergency_stop（dog_policy_test → dog_control）

- **消息类型**：`std_msgs::msg::Bool`
- **发送方**：dog_policy_test_7（倾倒检测触发时发送 `data = true`）
- **接收方**：dog_control/main.cpp 订阅，回调逻辑：
  1. `running_ = false` → 停止 `execute_loop` 控制循环
  2. `worker_thread_.join()` → 等待循环线程退出
  3. 遍历 12 个电机调用 `Disenable_Motor(0)` → **所有电机失能（零力矩）**
  4. `rclcpp::shutdown()` → 进程退出
- **不可恢复**：触发后 dog_control 和 dog_policy_test_7 都直接退出，需要重新 launch

### /motor_feedback 消息格式（dog_control → dog_policy_test）

- `msg.position[i]`：已减去 offset 的关节位置（站立时接近 0）
- `msg.velocity[i]`：原始电机编码器速度
- 顺序：FL, FR, RL, RR（与 IsaacGym DOF 顺序一致）

### /joint_states 消息格式（dog_policy_test → dog_control）

- `js.position[i]`：关节目标位置（js_pos 空间）
- dog_control 接收后：`motor_target = js_pos + kFixedJointCmdOffsets[idx]`

### 关节空间转换（calf 2:1 减速比）

| 方向 | hip/thigh | calf |
|------|-----------|------|
| 接收（msg → model） | `model = msg` | `model = msg / 2` |
| 发送（model → js） | `js = model` | `js = model * 2` |

---

## DOF 顺序

统一使用 IsaacGym 默认顺序：**FL, FR, RL, RR**

```
索引 0-2:   FL_hip, FL_thigh, FL_calf
索引 3-5:   FR_hip, FR_thigh, FR_calf
索引 6-8:   RL_hip, RL_thigh, RL_calf
索引 9-11:  RR_hip, RR_thigh, RR_calf
```

---

## Observation 构造（45 或 46 维）

```
[3]  command (vx, vy, wz) × kCommandScale
[3]  gyroscope (body frame) × obs_scales.ang_vel
[3]  projected_gravity (body frame)
[12] dof_pos (model deviation) × obs_scales.dof_pos
[12] dof_vel × obs_scales.dof_vel
[12] last_actions
[1]  height_command (仅 46 维模式)
```

6 帧历史拼接 → 总维度 270 (45×6) 或 276 (46×6)

---

## 键盘控制

| 按键 | 功能 | 值 |
|------|------|-----|
| y | 启动 RL 接管 | — |
| f | 关闭 RL | — |
| w/s | 前进/后退 | vx = ±0.5 |
| a/d | 左移/右移 | vy = ±0.5 |
| q/e | 左转/右转 | wz = ±0.5 |
| r | 蹲下 | height - 0.02 |
| z | 站起 | height + 0.02 |
| p | 重置机器人（清零 history 和 actions） | — |
| **N** | **上一个模型**（自动关 RL，切完按 y 重启）| — |
| **M** | **下一个模型**（自动关 RL，切完按 y 重启）| — |
| Esc | 退出程序 | — |

> ★ 支持多键同时按（如 w+q 前进+左转）；150ms 无重复字符自动归零对应轴（松手检测）
> ★ N/M 仅 test_12 支持（需配置 YAML 模型列表）

---

## 部署到板端（arm64 架构，正常电脑如x86-64 架构就不是这个压缩包）

```
# can 驱动安装
source /opt/ros/humble/setup.bash
sudo apt update
sudo apt install -y ros-humble-can-msgs

# onnx runtime 安装
cd /tmp
tar -xzf onnxruntime-linux-aarch64-1.23.1.tgz

sudo rm -rf /opt/onnxruntime
sudo mkdir -p /opt/onnxruntime
sudo cp -a onnxruntime-linux-aarch64-1.23.1/* /opt/onnxruntime/

ls /opt/onnxruntime/include/onnxruntime_cxx_api.h
ls /opt/onnxruntime/lib/libonnxruntime.so

echo "/opt/onnxruntime/lib" | sudo tee /etc/ld.so.conf.d/onnxruntime.conf
sudo ldconfig

ldconfig -p | grep onnxruntime

# 脚本权限
cd src/dog_control/script/
chmod +x can.sh imu.sh

c++ 编译
sudo apt update
sudo apt install build-essential cmake

can识别
echo "1d50 606f" | sudo tee /sys/bus/usb/drivers/gs_usb/new_id
```

---

# dog_nav — 任务赛导航与视觉

任务赛大脑功能包。基于 `/lio/odom`（Super-LIO 雷达惯导里程计）做定位反馈导航，状态机驱动 OCR 识别 → 箱子扫描 → BFS 路径规划 → 多轮取放，发 `/nav_cmd` 指挥 `dog_policy_test` 走位。

## 功能模块

| 模块 | 文件 | 说明 |
|------|------|------|
| **路径规划** | `include/dog_nav/field_path_planner.hpp` | 场地 BFS 最短路径（15 节点邻接图），归位区逐边禁用，减速带区域全连通 |
| **取放计划**（备用） | `include/dog_nav/delivery_planner.hpp` | 多轮取放计划生成 + 自动转身角度（不依赖 ROS，可单测；当前主节点未直接使用，逻辑内置在 navigation_dog） |
| **导航主节点** | `src/navigation_dog.cpp` | 状态机 + BFS + 横移螃蟹步导航 + 4 轮取放 + 吸盘舵机串口控制 |
| **打点工具** | `src/record_points.cpp` | 雷达定位打点，标定场地坐标（支持编号直跳 / 覆盖重录 / 未保存退出保护） |
| **移动测试（原始版）** | `src/test_nav_movement.cpp` | 基础动作测试，纯 P 控制 |
| **移动测试（RL 版）** | `src/test_nav_pid.cpp` | ★ RL 底盘专用：两档 + 提前量 + 死区 + 稳态确认 |
| **吸盘调试工具** | `resource/test_serial.py` | 舵机角度手动调试（串口协议参考，正式逻辑已内置在 navigation_dog） |
| **自定义消息** | `msg/DogNavCommand.msg` | 导航命令（vx/vy/wz/height/model_path） |
| **物资箱检测(RKNN)** | `resource/vision/box_detector_rknn.py` | RKNN YOLO 检测（上位机 RK3588），`--mode scan_all` |
| **物资箱检测(PyTorch)** | `resource/vision/box_detector_pt.py` | PyTorch YOLO 检测（电脑端，RealSense D435i） |
| **算术题求解** | `resource/vision/solver.py` | PaddleOCR 识别 + 计算 mod4 + 语音播报 |
| **D435i 推流** | `resource/vision/d435i_stream.py` | ★ 独占 D435i，Foxglove 推流 + shm 喂帧给视觉脚本 |
| **取帧客户端** | `resource/vision/d435i_client.py` | ★ 从 shm 取对齐帧，读不到自动回退直接开相机 |
| **路径验证** | `test/test_bfs.py` | 路径验证（含逐边禁用场景） |
| **转身验证** | `test/test_place_turn.py` | 放置转身角度验证（含转圈倒车场景） |


## 状态机（navigation_dog）

```
IDLE
  │  按 'y' 或 auto_start:=true
  ▼
OCR_SOLVE ──────── ① StartStreamer()  ← D435i 推流开启（独占相机 + shm 喂帧）
  │                ② 调用 solver.py，OCR 识别算术题 + 播报（从 shm 取帧）
  │                   → mod4 结果 → 目标归位区 zone（target_zone，用于筛"先送哪个"）
  ▼
BOX_SCAN_PHASE0 ── 在点0 远看 8 箱（box_detector 从 shm 取 N 帧，推流继续）
  │                结果存 phase0_map_
  ▼
GOTO_POINT1 ────── 0→1 横移导航（推流继续，电脑端可看画面）
  ▼
BOX_SCAN_PHASE1 ── 在点1 近看 4 箱（从 shm 取帧，推流继续）
  │  (=MERGE)       合并 Phase0+Phase1，校验：4 种类型 × 每种 2 个（失败只 WARN，不阻断）
  │                ③ StopStreamer()  ← 8 箱识别完、计划生成后，推流关闭释放相机
  ▼
GenerateDeliveryPlan() ── 生成 4 轮取放计划（每轮 = 一对取货点）
  │
  ▼ [循环 4 轮]  ← 此阶段推流已关，无画面（取放靠雷达导航+吸盘时序）
  ├─ GOTO_PICKUP ──── 横移导航到取货点（sub_step 0→2→4，成对取货）
  ├─ PICKUP ────────── 吸盘舵机动作取箱（下→真空占位→抬，6s/次）
  ├─ GOTO_TARGET ───── 横移导航到放货站位
  ├─ PLACE_AVOID ───── ★ U 型避障（横向通道被已放箱归位区挡住时，绕第二排）
  ├─ PLACE_BOX ─────── 吸盘舵机动作放箱（★ 转身动作仍 TODO）
  ▼
DONE
```

> 📹 **推流窗口**：OCR_SOLVE 开始 → 识别完 8 箱。覆盖整个"感知"阶段（OCR + 点0→点1 导航 + 两次扫描），电脑端 Foxglove 全程可见画面。取放阶段关闭（靠雷达导航，不看画面）。

### D435i 相机服务器架构（推流期间）

D435i 不能被两个进程同时打开。推流窗口内采用"相机服务器"模式：`d435i_stream.py` 独占 D435i，既推流又把对齐帧写入 `/dev/shm/d435i_frame.npz`，视觉脚本通过 `d435i_client.py` 取帧，零冲突。

```
        RK3588 (独占 D435i)                      你的电脑
┌────────────────────────────┐              ┌──────────────┐
│ d435i_stream.py            │  Foxglove WS │ Foxglove 看画面│
│  color 1080p → JPEG → 推流 ──────────────▶│ ws://IP:8765 │
│  写 /dev/shm/d435i_frame   │              └──────────────┘
│         ▲ (最新对齐帧)      │
│  ┌──────┴───────┐          │
│  │ solver.py    │box_detector│  从 shm 取帧（不抢相机）
│  │(OCR 取1帧)   │(扫描取N帧) │
│  └──────────────┘ ──────────│
│           ▲                 │
│  navigation_dog.cpp:        │
│   OCR_SOLVE → StartStreamer │
│   计划生成后 → StopStreamer │
└────────────────────────────┘
```

**安全回退**：vision 脚本读不到 shm（streamer 没跑 / import 失败）时，自动回退直接打开 D435i —— 检测/OCR 行为退回现状，比赛不受影响。推流是纯附加层。



### 启动流程

joy/imu 节点启动
./src/dog_control/scripts/imu.sh

can 
./src/dog_control/scripts/can.sh

电机启动+rl
./src/dog_policy_test/scripts/launch_policy_on_a.sh


