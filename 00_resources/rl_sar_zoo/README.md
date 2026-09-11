# rl_sar_zoo — 参考资源

> **来源**：`00_open/rl_sar_zoo/`　｜　**类型**：参考项目
> **关联机型**：unitree_go2（宇树 Go2 四足）、unitree_go2w（宇树 Go2W 轮足）、unitree_b2（宇树 B2 四足）、unitree_b2w（宇树 B2W 轮足）、unitree_g1（宇树 G1 人形）、deeprobotics_lite3（云深处 Lite3 四足）
> **定位**：RL-SAR 机型 zoo：URDF/MJCF 与策略集合
> **收录**：171 个文件 / 1.5 MB（其中推理策略/模型文件 0 个）
> **已省略**：416 个文件 / 467.8 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（119 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **关节与接口契约**（6 个）：关节与接口契约：关节序、limits、PD、action_scale、default pose、观测/动作维度
- **RL 训练工程**（15 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（24 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **地形与场景**（4 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **文档与其它**（3 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （3 个文件）
a1_description/  （12 个文件）
    (直接文件)/
    config/
    launch/
    urdf/
    xacro/
b2_description/  （15 个文件）
    (直接文件)/
    config/
    launch/
    mjcf/
    urdf/
    xacro/
b2w_description/  （15 个文件）
    (直接文件)/
    config/
    launch/
    mjcf/
    urdf/
    xacro/
d1_description/  （11 个文件）
    (直接文件)/
    config/
    launch/
    mjcf/
    urdf/
    xacro/
g1_description/  （31 个文件）
    (直接文件)/
    config/
    inspire_hand/
    launch/
    mjcf/
    urdf/
    xacro/
go2_description/  （14 个文件）
    (直接文件)/
    config/
    launch/
    mjcf/
    urdf/
    xacro/
go2w_description/  （14 个文件）
    (直接文件)/
    config/
    launch/
    mjcf/
    urdf/
    xacro/
gr1t1_description/  （12 个文件）
    (直接文件)/
    config/
    launch/
    urdf/
    xacro/
gr1t2_description/  （12 个文件）
    (直接文件)/
    config/
    launch/
    urdf/
    xacro/
l4w4_description/  （10 个文件）
    (直接文件)/
    config/
    launch/
    urdf/
    xacro/
lite3_description/  （11 个文件）
    (直接文件)/
    config/
    launch/
    urdf/
    xacro/
tita_description/  （11 个文件）
    (直接文件)/
    config/
    launch/
    urdf/
    xacro/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.xml` | 44 |
| `.urdf` | 26 |
| `.yaml` | 25 |
| `.xacro` | 24 |
| `.launch` | 21 |
| `.txt` | 12 |
| `.rviz` | 9 |
| `.md` | 5 |
| `.py` | 3 |
| `(无扩展名)` | 2 |

## 文件索引（项目内相对路径）

```text
.gitignore
README.md
VERSION
a1_description/CMakeLists.txt
a1_description/config/robot_control.yaml
a1_description/config/robot_control_ros2.yaml
a1_description/launch/a1_rviz.launch
a1_description/launch/a1_rviz.launch.py
a1_description/launch/check_joint.rviz
a1_description/launch/gazebo.launch.py
a1_description/package.ros1.xml
a1_description/package.ros2.xml
a1_description/urdf/a1_description.urdf
a1_description/xacro/gazebo.xacro
a1_description/xacro/robot.xacro
b2_description/CMakeLists.txt
b2_description/README.md
b2_description/config/config.rviz
b2_description/config/robot_control.yaml
b2_description/config/robot_control_ros2.yaml
b2_description/launch/display.launch
b2_description/launch/gazebo.launch
b2_description/mjcf/b2.xml
b2_description/mjcf/scene.xml
b2_description/mjcf/scene_terrain.xml
b2_description/package.ros1.xml
b2_description/package.ros2.xml
b2_description/urdf/b2_description.urdf
b2_description/xacro/gazebo.xacro
b2_description/xacro/robot.xacro
b2w_description/CMakeLists.txt
b2w_description/README.md
b2w_description/config/b2w.rviz
b2w_description/config/robot_control.yaml
b2w_description/config/robot_control_ros2.yaml
b2w_description/launch/display.launch
b2w_description/launch/gazebo.launch
b2w_description/mjcf/b2w.xml
b2w_description/mjcf/scene.xml
b2w_description/mjcf/scene_terrain.xml
b2w_description/package.ros1.xml
b2w_description/package.ros2.xml
b2w_description/urdf/b2w_description.urdf
b2w_description/xacro/gazebo.xacro
b2w_description/xacro/robot.xacro
d1_description/CMakeLists.txt
d1_description/config/robot_control.yaml
d1_description/config/robot_control_ros2.yaml
d1_description/launch/gazebo.launch
d1_description/mjcf/d1.xml
d1_description/mjcf/scene.xml
d1_description/package.ros1.xml
d1_description/package.ros2.xml
d1_description/urdf/d1_description.urdf
d1_description/xacro/gazebo.xacro
d1_description/xacro/robot.xacro
g1_description/CMakeLists.txt
g1_description/README.md
g1_description/config/robot_control.yaml
g1_description/config/robot_control_ros2.yaml
g1_description/copy_used_stl.py
g1_description/inspire_hand/DFQ_left_hand.urdf
g1_description/inspire_hand/DFQ_right_hand.urdf
g1_description/inspire_hand/FTP_left_hand.urdf
g1_description/inspire_hand/FTP_right_hand.urdf
g1_description/inspire_hand/config.yaml
g1_description/launch/gazebo.launch
g1_description/mjcf/g1_23dof.xml
g1_description/mjcf/g1_29dof.xml
g1_description/mjcf/g1_29dof_with_hand.xml
g1_description/mjcf/g1_joint_index_dds.md
g1_description/mjcf/scene_23dof.xml
g1_description/mjcf/scene_29dof.xml
g1_description/mjcf/scene_29dof_with_hand.xml
g1_description/package.ros1.xml
g1_description/package.ros2.xml
g1_description/urdf/g1_23dof_rev_1_0.urdf
g1_description/urdf/g1_29dof_lock_waist_rev_1_0.urdf
g1_description/urdf/g1_29dof_lock_waist_with_hand_rev_1_0.urdf
g1_description/urdf/g1_29dof_rev_1_0.urdf
g1_description/urdf/g1_29dof_rev_1_0_modify_inertia.urdf
g1_description/urdf/g1_29dof_rev_1_0_modify_inertia_lock_body.urdf
g1_description/urdf/g1_29dof_rev_1_0_with_inspire_hand_DFQ.urdf
g1_description/urdf/g1_29dof_rev_1_0_with_inspire_hand_FTP.urdf
g1_description/urdf/g1_29dof_with_hand_rev_1_0.urdf
g1_description/xacro/gazebo.xacro
g1_description/xacro/robot.xacro
go2_description/CMakeLists.txt
go2_description/config/robot_control.yaml
go2_description/config/robot_control_ros2.yaml
go2_description/launch/check_joint.rviz
go2_description/launch/gazebo.launch
go2_description/launch/go2_rviz.launch
go2_description/mjcf/go2.xml
go2_description/mjcf/scene.xml
go2_description/mjcf/scene_terrain.xml
go2_description/package.ros1.xml
go2_description/package.ros2.xml
go2_description/urdf/go2_description.urdf
go2_description/xacro/gazebo.xacro
go2_description/xacro/robot.xacro
go2w_description/CMakeLists.txt
go2w_description/config/robot_control.yaml
go2w_description/config/robot_control_ros2.yaml
go2w_description/launch/check_joint.rviz
go2w_description/launch/gazebo.launch
go2w_description/launch/go2w_rviz.launch
go2w_description/mjcf/go2w.xml
go2w_description/mjcf/scene.xml
go2w_description/mjcf/scene_terrain.xml
go2w_description/package.ros1.xml
go2w_description/package.ros2.xml
go2w_description/urdf/go2w_description.urdf
go2w_description/xacro/gazebo.xacro
go2w_description/xacro/robot.xacro
gr1t1_description/CMakeLists.txt
gr1t1_description/config/robot_control.yaml
gr1t1_description/config/robot_control_ros2.yaml
gr1t1_description/launch/display.launch
gr1t1_description/launch/gazebo.launch
gr1t1_description/launch/urdf.rviz
gr1t1_description/package.ros1.xml
gr1t1_description/package.ros2.xml
gr1t1_description/urdf/GR1T1.urdf
gr1t1_description/urdf/GR1T1_lower_limb.urdf
gr1t1_description/xacro/gazebo.xacro
gr1t1_description/xacro/robot.xacro
gr1t2_description/CMakeLists.txt
gr1t2_description/config/robot_control.yaml
gr1t2_description/config/robot_control_ros2.yaml
gr1t2_description/launch/display.launch
gr1t2_description/launch/gazebo.launch
gr1t2_description/launch/urdf.rviz
gr1t2_description/package.ros1.xml
gr1t2_description/package.ros2.xml
gr1t2_description/urdf/GR1T2.urdf
gr1t2_description/urdf/GR1T2_simple.urdf
gr1t2_description/xacro/gazebo.xacro
gr1t2_description/xacro/robot.xacro
l4w4_description/CMakeLists.txt
l4w4_description/config/robot_control.yaml
l4w4_description/config/robot_control_ros2.yaml
l4w4_description/launch/display.launch
l4w4_description/launch/gazebo.launch
l4w4_description/package.ros1.xml
l4w4_description/package.ros2.xml
l4w4_description/urdf/l4w4_description.urdf
l4w4_description/xacro/gazebo.xacro
l4w4_description/xacro/robot.xacro
lite3_description/CMakeLists.txt
lite3_description/config/robot_control.yaml
lite3_description/config/robot_control_ros2.yaml
lite3_description/launch/check_joint.rviz
lite3_description/launch/gazebo.launch
lite3_description/launch/lite3_rviz.launch
lite3_description/package.ros1.xml
lite3_description/package.ros2.xml
lite3_description/urdf/lite3.urdf
lite3_description/xacro/gazebo.xacro
lite3_description/xacro/robot.xacro
tita_description/CMakeLists.txt
tita_description/config/robot_control.yaml
tita_description/config/robot_control_ros2.yaml
tita_description/launch/check_joint.rviz
tita_description/launch/gazebo.launch
tita_description/launch/tita_rviz.launch
tita_description/package.ros1.xml
tita_description/package.ros2.xml
tita_description/urdf/tita_description.urdf
tita_description/xacro/gazebo.xacro
tita_description/xacro/robot.xacro
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `a1_description/meshes` | 6 | 8.7 MB | [`a1_description/meshes/_OMITTED.md`](./a1_description/meshes/_OMITTED.md) |
| `b2_description/meshes` | 14 | 21.3 MB | [`b2_description/meshes/_OMITTED.md`](./b2_description/meshes/_OMITTED.md) |
| `b2_description/mjcf` | 3 | 669 KB | [`b2_description/mjcf/_OMITTED.md`](./b2_description/mjcf/_OMITTED.md) |
| `b2_description/mjcf/assets` | 31 | 30.9 MB | [`b2_description/mjcf/assets/_OMITTED.md`](./b2_description/mjcf/assets/_OMITTED.md) |
| `b2w_description/meshes` | 17 | 79.4 MB | [`b2w_description/meshes/_OMITTED.md`](./b2w_description/meshes/_OMITTED.md) |
| `b2w_description/mjcf` | 3 | 689 KB | [`b2w_description/mjcf/_OMITTED.md`](./b2w_description/mjcf/_OMITTED.md) |
| `b2w_description/mjcf/assets` | 35 | 36.9 MB | [`b2w_description/mjcf/assets/_OMITTED.md`](./b2w_description/mjcf/assets/_OMITTED.md) |
| `d1_description/meshes` | 17 | 14.6 MB | [`d1_description/meshes/_OMITTED.md`](./d1_description/meshes/_OMITTED.md) |
| `d1_description/mjcf/assets` | 17 | 14.6 MB | [`d1_description/mjcf/assets/_OMITTED.md`](./d1_description/mjcf/assets/_OMITTED.md) |
| `g1_description/images` | 4 | 3.5 MB | [`g1_description/images/_OMITTED.md`](./g1_description/images/_OMITTED.md) |
| `g1_description/meshes` | 38 | 32.9 MB | [`g1_description/meshes/_OMITTED.md`](./g1_description/meshes/_OMITTED.md) |
| `g1_description/mjcf/images` | 4 | 3.5 MB | [`g1_description/mjcf/images/_OMITTED.md`](./g1_description/mjcf/images/_OMITTED.md) |
| `g1_description/mjcf/meshes` | 60 | 31.8 MB | [`g1_description/mjcf/meshes/_OMITTED.md`](./g1_description/mjcf/meshes/_OMITTED.md) |
| `go2_description/meshes` | 7 | 24.7 MB | [`go2_description/meshes/_OMITTED.md`](./go2_description/meshes/_OMITTED.md) |
| `go2_description/mjcf` | 3 | 629 KB | [`go2_description/mjcf/_OMITTED.md`](./go2_description/mjcf/_OMITTED.md) |
| `go2_description/mjcf/assets` | 16 | 27.8 MB | [`go2_description/mjcf/assets/_OMITTED.md`](./go2_description/mjcf/assets/_OMITTED.md) |
| `go2w_description/meshes` | 9 | 29.0 MB | [`go2w_description/meshes/_OMITTED.md`](./go2w_description/meshes/_OMITTED.md) |
| `go2w_description/mjcf` | 2 | 19 KB | [`go2w_description/mjcf/_OMITTED.md`](./go2w_description/mjcf/_OMITTED.md) |
| `go2w_description/mjcf/assets` | 22 | 32.7 MB | [`go2w_description/mjcf/assets/_OMITTED.md`](./go2w_description/mjcf/assets/_OMITTED.md) |
| `gr1t1_description/meshes` | 33 | 16.5 MB | [`gr1t1_description/meshes/_OMITTED.md`](./gr1t1_description/meshes/_OMITTED.md) |
| `gr1t2_description/meshes` | 34 | 13.2 MB | [`gr1t2_description/meshes/_OMITTED.md`](./gr1t2_description/meshes/_OMITTED.md) |
| `l4w4_description/meshes` | 8 | 2.0 MB | [`l4w4_description/meshes/_OMITTED.md`](./l4w4_description/meshes/_OMITTED.md) |
| `lite3_description/meshes` | 17 | 11.0 MB | [`lite3_description/meshes/_OMITTED.md`](./lite3_description/meshes/_OMITTED.md) |
| `tita_description/meshes` | 16 | 30.9 MB | [`tita_description/meshes/_OMITTED.md`](./tita_description/meshes/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
