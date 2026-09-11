# 任务赛使用手册 —— 建图 / 打点 / 导航（双馆分离）

> 本文档说明 Mid-360 雷达 + Super-LIO 定位 + dog_nav 导航的完整使用流程。
> **左右馆是两场独立的比赛**，各自独立建图、独立打点，一次只跑一个馆。

---

## 0. 数据流总览

```
┌──────────────┐   /livox/lidar + /livox/imu   ┌──────────────┐   /lio/odom   ┌──────────┐
│ Livox Mid-360│ ────────────────────────────▶ │  Super-LIO   │ ────────────▶│ dog_nav  │
│ livox_ros_   │                               │ (IESKF/      │  (世界坐标)  │ 导航/打点 │
│ driver2      │                               │  FAST-LIO2)  │              │          │
└──────────────┘                               └──────────────┘              └──────────┘
   原始数据采集                                    雷达+IMU 融合定位             只读 odom 消息
```

| 阶段 | 节点 | 作用 |
|---|---|---|
| 驱动 | `livox_ros_driver2` | 出 `/livox/lidar`(CustomMsg, 10Hz) + `/livox/imu`(≈200Hz) |
| 建图 | `super_lio_node` | 雷达惯性里程计，边走边建图，关掉时存 `map.pcd` |
| 重定位 | `relocation_node` | 加载已建地图，把狗"摆进"地图坐标系，`/lio/odom` 变绝对坐标 |
| 打点 | `record_points_2` | 在地图坐标系里打 3 个锚点，推理出其余 6 个，写 yaml |
| 导航 | `navigation_dog_2` | 读 yaml 点集 + `/lio/odom`，跑取货→放货→归位 |

---

## 1. 前置准备（每次都要检查）

### 1.1 雷达广播码
`livox_ros_driver2/launch_ROS2/msg_MID360_launch.py` 里的
`cmdline_bd_code = 'livox0000000001'` 是**占位符**，要换成雷达机身上印的 15 位真实码。

### 1.2 用对启动文件
- 建图/重定位用 **`msg_MID360_launch.py`**（出 Livox `CustomMsg`）。
- **别用** `rviz_MID360_launch.py`（出 PointCloud2，Super-LIO 吃不了）。

### 1.3 网络配置
Mid-360：雷达 IP `192.168.124.36`，主机 IP `192.168.124.100`（见 `livox_ros_driver2/config/MID360_config.json`）。

---

## 2. 三个阶段

| 阶段 | 做几次 | 频率 |
|---|---|---|
| ① 建图 | 每个馆各一次 | 场地固定后只做一次，地图存着 |
| ② 打点 | 每个馆各一次 | 场地/箱子位置变了重打 |
| ③ 导航 | 当天跑哪个馆就起哪个馆 | 每次比赛 |

> **核心规则：同一场比赛，三条命令的"馆"必须一致。**
> 左馆重定位加载 `map_left.pcd`，导航就得读 `task_race_2_left.yaml`，别混了。

---

## 3. 左馆完整流程

### ① 建图（只做一次）

```bash
# 终端1 - 雷达驱动
ros2 launch livox_ros_driver2 msg_MID360_launch.py

# 终端2 - 建图节点（存成左馆地图）
ros2 launch super_lio Livox_mid360.py map_name:=map_left.pcd

# 终端3（可选）- rviz 看建图质量
rviz2
```

→ **牵着狗把左馆整个走一遍**（取货区、放货区、归位区都覆盖到）。
→ 关掉终端2 时自动存 `map/map_left.pcd`。

### ② 重定位 + 打点（场地变了重做）

```bash
# 终端1 - 雷达驱动
ros2 launch livox_ros_driver2 msg_MID360_launch.py

# 终端2 - 重定位节点（加载左馆地图）
ros2 launch super_lio relocation.py  lio.map.map_name:=map_left.pcd

# 终端3 - 打点工具（输出到左馆 yaml）
ros2 run dog_nav record_points_2  output_path:=src/dog_nav/config/task_race_2_left.yaml
```

**起打点工具前，先在 rviz 确认重定位收敛了**（狗在地图里的位置看起来对、`/lio/odom` 坐标合理），没收敛打出来的点全是错的。

**打点操作**（只需打 3 个锚点）：
```
抬到 点1（枢纽） → 按 s
抬到 点2（取货锚，第一排左，吸09+10） → 按 s
抬到 点6（放货锚，归位区01旁）       → 按 s
按 i  → 查看推理出的 点3/4/5/7/8/9
按 w  → 写入 task_race_2_left.yaml
按 q  → 退出
```

### ③ 比赛跑导航

```bash
# 终端1 - 雷达驱动
ros2 launch livox_ros_driver2 msg_MID360_launch.py

# 终端2 - 重定位节点（加载左馆地图）
ros2 launch super_lio relocation.py --ros-args \
  -p lio.map.map_name:=map_left.pcd

# 终端3 - 导航节点（读左馆点集）
ros2 run dog_nav navigation_dog_2 --ros-args \
  --params-file src/dog_nav/config/task_race_2_left.yaml
```

---

## 4. 右馆完整流程

**把上面第 3 节所有命令里的 `left` 换成 `right` 即可。**

### ① 建图
```bash
ros2 launch livox_ros_driver2 msg_MID360_launch.py
ros2 launch super_lio Livox_mid360.py --ros-args \
  -p lio.map.map_name:=map_right.pcd
# 牵狗走遍右馆 → 存 map/map_right.pcd
```

### ② 重定位 + 打点
```bash
ros2 launch livox_ros_driver2 msg_MID360_launch.py
ros2 launch super_lio relocation.py --ros-args \
  -p lio.map.map_name:=map_right.pcd
ros2 run dog_nav record_points_2 --ros-args \
  -p output_path:=src/dog_nav/config/task_race_2_right.yaml
# 打 点1/2/6 → i → w
```

### ③ 比赛跑导航
```bash
ros2 launch livox_ros_driver2 msg_MID360_launch.py
ros2 launch super_lio relocation.py --ros-args \
  -p lio.map.map_name:=map_right.pcd
ros2 run dog_nav navigation_dog_2 --ros-args \
  --params-file src/dog_nav/config/task_race_2_right.yaml
```

---

## 5. 文件结构（建好之后）

```
<super_lio 工作目录>/map/
  ├── map_left.pcd          # 左馆地图
  └── map_right.pcd         # 右馆地图

src/dog_nav/config/
  ├── task_race_2_left.yaml    # 左馆点集（含 3 锚点 + 6 推理点）
  └── task_race_2_right.yaml   # 右馆点集
```

---

## 6. 打点工具操作速查（record_points_2）

只需打 **3 个锚点**，其余 6 个自动推理：

| 锚点 | 作用 |
|---|---|
| 点1 | 枢纽（起点前，不取货） |
| 点2 | 取货锚（第一排左，吸09+10） |
| 点6 | 放货锚（归位区01旁，放zone1） |

**推理规则**：
```
取货点（从点2）：                放货点（从点6）：
  点3 = 点2 + (1.2, 0)            点7 = 点6 + (0.4, 0)
  点4 = 点2 + (0, 0.6)            点8 = 点6 + (0.8, 0)
  点5 = 点2 + (1.2, 0.6)          点9 = 点6 + (1.2, 0)
  θ 继承点2                       θ、y 继承点6
```

| 按键 | 作用 |
|---|---|
| `s` | 保存当前 odom 位姿为当前目标点 |
| `i` | 触发推理并打印结果 |
| 数字+回车 | 跳转到指定编号 |
| `n` / `p` | 下一个 / 上一个点 |
| `l` | 列出所有点（✅记录 / 🧮推理 / ❌未记录） |
| `u` | 撤销上一个手打点（推理点随锚点自动重算） |
| `w` | 输出 YAML（终端 + 写文件） |
| `r` | 清空重来 |
| `q` | 退出（有未保存改动会二次确认） |

> **手打覆盖优先**：某个点一旦手打，推理不会再覆盖它。比如觉得点3 推理位置不准，直接抬过去对准按 `s`，它从"🧮推理"变"✅记录"，之后改锚点也不动它。

---

## 7. 常见坑

| 现象 | 原因 / 解决 |
|---|---|
| 雷达连不上 | 广播码没换（见 1.1）；或网络不对（见 1.3） |
| Super-LIO 收不到点云 | 用错启动文件了，要用 `msg_MID360_launch.py`（见 1.2） |
| 打出来的点每次都不一样 | 没用重定位，纯里程计的原点是开机位置 → 必须先 `relocation.py` |
| 打点坐标对不上地图 | 重定位没收敛就打点了；或重定位加载的图和打点时不是同一张 |
| 两个馆坐标互相串 | 三条命令的馆没对齐（左图配了右点集） |
| 点3-9 推理位置偏 | 锚点（点2/点6）没打准，或箱子实际间距不是 0.6m；改 `record_points_2.cpp` 顶部的 `kPickupDx/kPickupDy/kPlaceDx` 常量 |

---

## 8. 坐标系约定

- **x**：右为正
- **y**：前为正
- **theta**：朝向角，度
- 原点 = 重定位进地图后的坐标原点（取决于 `map.pcd` 建图时的起始位置）
- 两馆各自独立，坐标互不相关
