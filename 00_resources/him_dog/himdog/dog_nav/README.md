# dog_nav

四足机器人任务赛导航与视觉感知功能包，基于 ROS 2 (ament_cmake) 构建。

## 功能概览

| 模块 | 文件 | 说明 |
|------|------|------|
| **路径规划** | `field_path_planner.hpp` | 场地 BFS 最短路径（10节点图），同行/同列直达，减速带区域全连通 |
| **取放计划** | `delivery_planner.hpp` | 多轮取放计划生成，自动转身角度计算（不依赖ROS，可独立测试） |
| **导航节点** | `navigation_dog.cpp` | 状态机导航，横移螃蟹步，雷达定位反馈，4轮取放（每轮取2箱放2箱） |
| **移动测试** | `test_nav_movement.cpp` | 基础动作测试：转90°/180°、前进0.3m/1.0m |
| **自定义消息** | `DogNavCommand.msg` | 导航命令消息（vx/vy/wz/height/model_path） |
| **运动控制** | `dog_policy_test_11` | RL 策略推理节点，订阅 `/nav_cmd` |
| **物资箱检测(RKNN)** | `box_detector_rknn.py` | RKNN YOLO 物资箱类型识别（上位机 RK3588） |
| **物资箱检测(PyTorch)** | `box_detector_pt.py` | PyTorch YOLO 检测（电脑端测试，RealSense D435i） |
| **算术题求解** | `solver.py` | PaddleOCR 识别 + 计算 mod4 + 语音播报 |
| **路径验证** | `test/test_bfs.py` | Python 路径验证脚本（37 项测试） |
| **转身验证** | `test/test_place_turn.py` | 放置转身角度计算验证（67 项测试） |

## 场地布局

```
  【01】       【02】      【03】       【04】     归位区
  【点6】      【点7】      【点8】      【点9】   放置站位

  ==================================================     减速带
  【05】【点4】【06】     【07】【点5】【08】      第二排

  【09】【点2】【10】     【11】【点3】【12】      第一排

                    【点1】                        起点前

                    【0】                          起点
```

### 点位说明

| 点位 | 功能 | 说明 |
|------|------|------|
| 0 | 起点 | OCR 识别位置 |
| 1 | 第一排前 | 中转点（仅扫描时经过，取放路径不走这里） |
| 2 | 第一排左 | 左吸盘吸箱09，右吸盘吸箱10 |
| 3 | 第一排右 | 左吸盘吸箱11，右吸盘吸箱12 |
| 4 | 第二排左 | 左吸盘吸箱05，右吸盘吸箱06 |
| 5 | 第二排右 | 左吸盘吸箱07，右吸盘吸箱08 |
| 6 | 归位区左1 | 放入归位区01 (zone 1) |
| 7 | 归位区左2 | 放入归位区02 (zone 2) |
| 8 | 归位区右1 | 放入归位区03 (zone 3) |
| 9 | 归位区右2 | 放入归位区04 (zone 4) |

### 取货映射

| 站位 | 左吸盘吸取 | 右吸盘吸取 |
|------|---------|---------|
| 点2 | 箱09 | 箱10 |
| 点3 | 箱11 | 箱12 |
| 点4 | 箱05 | 箱06 |
| 点5 | 箱07 | 箱08 |

### BFS 路径图（10节点）

```
点6 ── 点7 ── 点8 ── 点9        归位区（第三排）
│      │      │      │
点4 ── 点5                      第二排
│      │
点2 ── 点3                      第一排
       │
点0 ── 点1                      起点（点1只在0→1扫描时经过）
```

关键连接：
- **同行直达**：2↔3, 4↔5, 6↔7↔8↔9
- **同列直达**：2↔4, 3↔5, 4↔6, 5↔8 等
- **减速带全连通**：点4/点5 可直达 6/7/8/9 任意点（减速带区域无障碍）
- **点1只连0/2/3**：扫描专用，取放路径不经过

## 目录结构

```
dog_nav/
├── CMakeLists.txt
├── package.xml
├── README.md
├── config/
│   └── task_race_point.yaml          # 场地坐标 + 归位区坐标
├── include/dog_nav/
│   ├── field_path_planner.hpp        # BFS 路径规划器（10节点图）
│   └── delivery_planner.hpp          # 取放计划器（多轮2箱+自动转身）
├── msg/
│   └── DogNavCommand.msg             # 导航命令消息
├── resource/vision/
│   ├── model/best.rknn               # YOLO RKNN 模型
│   ├── model/best.pt                 # YOLO PyTorch 模型
│   ├── box_detector_config.json      # 检测配置
│   ├── box_detector_rknn.py          # 物资箱检测（RKNN，上位机）
│   ├── box_detector_pt.py            # 物资箱检测（PyTorch，电脑测试）
│   ├── solver.py                     # 算术题 OCR + 播报
│   └── audio/0-3.mp3                 # 播报音频
├── src/
│   ├── navigation_dog.cpp            # 导航节点（状态机 + 横移导航 + 4轮取放）
│   └── test_nav_movement.cpp         # 移动测试（转90°/180°，前进0.3m/1.0m）
├── test/
│   ├── test_bfs.py                   # 路径验证（37项测试）
│   ├── test_place_turn.py            # 转身角度验证（67项测试）
│   ├── test_ocr.py                   # OCR 测试
│   └── convert_audio.py              # 音频转换工具
└── map/
```

## 系统架构

```
┌──────────────────────┐                    ┌──────────────────────┐
│  Super-LIO           │                    │  dog_policy_test_11  │
│  (雷达里程计)         │                    │  (RL 策略推理)        │
│                      │                    │                      │
│  /lio/odom ──────────┼──→                 │  速度限幅 + 渐变      │
│                      │   ┌──────────┐     │  NaN/超时保护         │
│                      │   │ /nav_cmd │────→│                      │
│                      │   └──────────┘     └──────────────────────┘
│                      │        ↑
│                      │   ┌──────────────────────────────────┐
│                      └──→│  navigation_dog                  │
│                          │                                  │
│                          │  ★ 雷达定位反馈导航（横移螃蟹步）   │
│                          │  ★ BFS 路径规划（10节点）          │
│                          │  ★ 4轮取放（每轮左右各1箱）         │
│                          │  ★ 自动转身（CalcPlaceTurnAngle）  │
│                          │  ★ OCR + 两步扫描                  │
│                          └──────────────────────────────────┘
```

## 任务赛完整流程

### 状态机

```
IDLE
  │  按'y'或 auto_start=true
  ▼
OCR_SOLVE ──────── ✅ 调用 solver.py，OCR识别算术题+播报，重试3次
  │
  ▼
BOX_SCAN_PHASE0 ── ✅ 在点0远看8箱
  │
  ▼
GOTO_POINT1 ────── ✅ 0→1 横移导航
  │
  ▼
BOX_SCAN_PHASE1 ── ✅ 在点1近看4箱，合并Phase0+Phase1，校验每种2个
  │
  ▼
GenerateDeliveryPlan() ── ✅ 自动生成4轮取放计划
  │
  ▼ [循环4轮]
  │
  ├─ GOTO_PICKUP ──── ✅ 横移导航到取货点(2/3/4/5)
  ├─ PICKUP ────────── ✅ 左右吸盘同时取2个箱子（吸盘控制TODO）
  ├─ GOTO_TARGET ───── ✅ 横移导航到第一个放置点
  ├─ PLACE_BOX ─────── ✅ 自动转身放箱（转身角度自动计算，动作TODO）
  ├─ GOTO_TARGET ───── ✅ 横移导航到第二个放置点
  ├─ PLACE_BOX ─────── ✅ 自动转身放箱
  │
  ▼
DONE
```

### 多轮取放

```
每轮: 到1个取货点 → 左右各取1箱 → 逐个送到对应归位区

示例（假设扫描结果: 箱09=food, 箱10=tool, 箱11=instrument, 箱12=medicine, ...）:

  第1轮: 取货点2 → 左吸箱09(food→zone1→点6), 右吸箱10(tool→zone2→点7)
    → 先送左吸盘到点6(自动转身放箱)
    → 再送右吸盘到点7(自动转身放箱)

  第2轮: 取货点3 → 左吸箱11(instrument→zone3→点8), 右吸箱12(medicine→zone4→点9)
    → 先送左吸盘到点8
    → 再送右吸盘到点9

  第3轮: 取货点4 → ...
  第4轮: 取货点5 → ...
  → DONE
```

### 横移导航（螃蟹步）

```
不转向，直接横移到达目标：
  将世界坐标误差 (dx, dy) 旋转到本体坐标系:
    vx =  dx·cos(yaw) + dy·sin(yaw)    ← 前进分量
    vy = -dx·sin(yaw) + dy·cos(yaw)    ← 横移分量

到达后原地旋转到目标朝向
```

### 自动转身放置

```
到达放置点后，根据以下信息自动计算转身角度：
  1. 放置点坐标（从YAML加载）
  2. 归位区坐标（从YAML加载）
  3. 当前朝向（从/lio/odom获取）
  4. 吸盘侧（左/右，取货时确定）

  turn = atan2(zy-py, zx-px) - (cur_yaw ± π/2)

  左吸盘有箱 → 右转让左侧对准归位区
  右吸盘有箱 → 左转让右侧对准归位区
```

## 场地坐标配置

所有点位坐标在 `config/task_race_point.yaml` 中配置：

```yaml
# 起点
start_pose: [0.0, 0.0, 0.0]

# 取货站位点（狗站在箱子之间）
pickup_positions:
  point_1: [x, y, theta]
  point_2: [x, y, theta]    # 左吸09/右吸10
  point_3: [x, y, theta]    # 左吸11/右吸12
  point_4: [x, y, theta]    # 左吸05/右吸06
  point_5: [x, y, theta]    # 左吸07/右吸08

# 放货站位点（归位区旁）
place_positions:
  point_6: [x, y, theta]    # 放zone1
  point_7: [x, y, theta]    # 放zone2
  point_8: [x, y, theta]    # 放zone3
  point_9: [x, y, theta]    # 放zone4

# 归位区坐标（不是路径节点，用于计算转身角度）
return_zones:
  zone_1: [x, y, 0]         # 归位区01坐标
  zone_2: [x, y, 0]         # 归位区02坐标
  zone_3: [x, y, 0]         # 归位区03坐标
  zone_4: [x, y, 0]         # 归位区04坐标
```

## 测试

```bash
# 路径验证（37项）
python3 test/test_bfs.py

# 转身角度验证（67项）
python3 test/test_place_turn.py

# 移动测试（上位机运行，需要/lio/odom）
ros2 run dog_nav test_nav_movement
```

## 运行方式

### 构建

```bash
colcon build --packages-select dog_nav
source install/setup.bash
colcon build --packages-select dog_policy_test
```

### 运行

```bash
# 终端 1：导航节点（按 'y' + 回车启动）
ros2 run dog_nav navigation_dog --ros-args \
  --params-file src/dog_nav/config/task_race_point.yaml

# 或自动开始
ros2 run dog_nav navigation_dog --ros-args \
  --params-file src/dog_nav/config/task_race_point.yaml \
  -p auto_start:=true

# 终端 2：运动控制节点
ros2 run dog_policy_test dog_policy_test_11 --ros-args \
  --params-file src/dog_policy_test/config/policy_params.yaml
```

### 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `odom_topic` | "/lio/odom" | 里程计话题 |
| `pos_tolerance` | 0.05 | 位置到达容差（米） |
| `yaw_tolerance` | 0.087 | 角度到达容差（弧度，~5°） |
| `nav_kp_xy` | 0.8 | 位置控制比例增益 |
| `nav_kp_yaw` | 1.5 | 角度控制比例增益 |
| `nav_max_vx` | 0.5 | 最大前进速度 |
| `nav_max_vy` | 0.3 | 最大横移速度 |
| `nav_max_wz` | 1.0 | 最大角速度 |
| `nav_timeout_sec` | 15.0 | 单段导航超时（秒） |
| `deliver_point` | -1 | 放货站位 (6-9)，-1=OCR/扫描决定 |
| `field_side` | "left" | 赛场方向 |
| `auto_start` | false | 自动开始 |

### mod4 → 归位区映射

| mod4 | 左赛场 | 右赛场 |
|------|--------|--------|
| 0 | zone 1 (点6) | zone 4 (点9) |
| 1 | zone 2 (点7) | zone 3 (点8) |
| 2 | zone 3 (点8) | zone 2 (点7) |
| 3 | zone 4 (点9) | zone 1 (点6) |

## 待实现（TODO）

- [ ] PICKUP 吸盘取箱子动作控制
- [ ] PLACE_BOX 蹲下放箱动作控制
- [ ] 填写实际场地坐标值（替换默认置零）
- [x] ~~点位导航逻辑（雷达定位反馈导航）~~
- [x] ~~横移螃蟹步导航~~
- [x] ~~多轮取放（每轮取2箱放2箱）~~
- [x] ~~自动转身角度计算~~
- [x] ~~取放计划模块化（delivery_planner.hpp）~~