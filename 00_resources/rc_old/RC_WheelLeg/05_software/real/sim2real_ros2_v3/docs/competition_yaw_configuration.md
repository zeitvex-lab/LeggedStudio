# Pure Pursuit Yaw 调参记录（历史草案）

> 本文是开发期针对“未对准就前进”的调参记录，不是当前比赛快照的完整最终配置，也不是实机验收报告。运行真值以 [`../src/sim2real_bringup/config/runtime.yaml`](../src/sim2real_bringup/config/runtime.yaml) 和当前路线文件为准。

## 历史问题与调参意图

开发记录描述的现象是：绕杆或窄通道中，机器人在航向误差仍较大时开始前进，可能产生斜向接近障碍物。草案提出收紧 yaw gate，并尝试降低速度、lookahead 和航点容差。

这类参数只表示当时的调试假设，不能仅凭文档写成“不会撞杆”或“已优化完成”。是否改善需要结合对应代码、路线、定位模式和实机日志验证。

## 草案与当前归档配置

| 参数 | 旧草案记录 | 当前 v3 归档值 |
| --- | ---: | ---: |
| `nav_slalom_script_yaw_gate_deg` | `8.0` | `8.0` |
| `nav_goal_yaw_tolerance_deg` | `8.0` | `12.0` |
| `nav_local_planner_enabled` | `false` | `true` |
| `nav_astar_enabled` | `false` | `true` |
| `nav_slalom_max_vx` | `0.50` | `0.58` |
| `nav_slalom_lookahead` | `0.15` | `0.35` |
| `nav_slalom_tolerance` | `0.05` | `0.15` |

因此，旧草案只有 `nav_slalom_script_yaw_gate_deg=8.0` 与当前快照一致，其他值不能覆盖当前运行配置。

## 历史文件边界

旧记录曾引用：

```text
points_nav1007_optimized.json
tools/nav_tools/xml/A.xml
```

这两个路径都不在当前 v3 工作区中，不能作为可复制的比赛启动步骤。当前归档默认路线由 `runtime.yaml` 指向：

```text
map/routes/1hao_reall.json
```

## 当前检查方式

缺少真实 Odin `1hao.bin` 时先使用 odom fallback：

```bash
./start_sim2real.sh localization_mode:=odom \
  odin_config_file:=src/odin_ros_driver/config/control_command_odom.yaml
```

只读核对当前参数：

```bash
ros2 param get /sim2real_simple_nav_node nav_slalom_script_yaw_gate_deg
ros2 param get /sim2real_simple_nav_node nav_goal_yaw_tolerance_deg
ros2 param get /sim2real_simple_nav_node nav_local_planner_enabled
ros2 param get /sim2real_simple_nav_node nav_astar_enabled
```

监控导航输入和最终仲裁输出：

```bash
ros2 topic echo /cmd_vel_nav
ros2 topic echo /cmd_vel
ros2 topic echo /control/mode_state
```

实机调整前应保存路线、参数、日志和视频，并逐项记录修改前后结果；不要把单次主观现象直接升级为最终参数结论。
