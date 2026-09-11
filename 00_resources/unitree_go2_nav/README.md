# unitree_go2_nav — 参考资源

> **来源**：`00_open/unitree_go2_nav/`　｜　**类型**：参考项目
> **关联机型**：unitree_go2（宇树 Go2 四足）
> **定位**：Go2 导航相关脚本与配置
> **收录**：38 个文件 / 182 KB（其中推理策略/模型文件 0 个）
> **已省略**：17 个文件 / 50.2 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（15 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **关节与接口契约**（1 个）：关节与接口契约：关节序、limits、PD、action_scale、default pose、观测/动作维度
- **RL 训练工程**（6 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **文档与其它**（16 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （4 个文件）
go2_description/  （19 个文件）
    (直接文件)/
    config/
    launch/
    urdf/
    xacro/
unitree_go2_nav/  （11 个文件）
    (直接文件)/
    config/
    launch/
    src/
unitree_go2_nav_interfaces/  （4 个文件）
    (直接文件)/
    msg/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.xacro` | 6 |
| `.xml` | 5 |
| `(无扩展名)` | 4 |
| `.yaml` | 4 |
| `.py` | 4 |
| `.txt` | 3 |
| `.rviz` | 3 |
| `.md` | 2 |
| `.launch` | 2 |
| `.cpp` | 2 |
| `.dot` | 1 |
| `.urdf` | 1 |
| `.msg` | 1 |

## 文件索引（项目内相对路径）

```text
.gitignore
.gitmodules
README.md
framesF.dot
go2_description/CMakeLists.txt
go2_description/README.md
go2_description/config/go2.rviz
go2_description/config/joint_names_go2_description.yaml
go2_description/config/robot_control.yaml
go2_description/launch/check_joint.rviz
go2_description/launch/gazebo.launch
go2_description/launch/go2_rviz.launch
go2_description/launch/load_go2.launch.py
go2_description/launch/simulate_go2.launch.xml
go2_description/launch/world_go2.launch.xml
go2_description/package.xml
go2_description/urdf/go2_description.urdf
go2_description/xacro/const.xacro
go2_description/xacro/gazebo.xacro
go2_description/xacro/leg.xacro
go2_description/xacro/materials.xacro
go2_description/xacro/robot.xacro
go2_description/xacro/transmission.xacro
unitree_go2_nav/CMakeLists.txt
unitree_go2_nav/LICENSE
unitree_go2_nav/config/mapping.rviz
unitree_go2_nav/config/nav2_params copy.yaml
unitree_go2_nav/config/nav2_params.yaml
unitree_go2_nav/launch/demo.py
unitree_go2_nav/launch/mapping.launch.py
unitree_go2_nav/launch/navigation.launch.py
unitree_go2_nav/package.xml
unitree_go2_nav/src/navToPose.cpp
unitree_go2_nav/src/odomTf.cpp
unitree_go2_nav_interfaces/CMakeLists.txt
unitree_go2_nav_interfaces/LICENSE
unitree_go2_nav_interfaces/msg/NavToPose.msg
unitree_go2_nav_interfaces/package.xml
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `go2_description/dae` | 7 | 24.7 MB | [`go2_description/dae/_OMITTED.md`](./go2_description/dae/_OMITTED.md) |
| `go2_description/images` | 1 | 379 KB | [`go2_description/images/_OMITTED.md`](./go2_description/images/_OMITTED.md) |
| `go2_description/meshes` | 7 | 24.7 MB | [`go2_description/meshes/_OMITTED.md`](./go2_description/meshes/_OMITTED.md) |
| `go2_description/urdf` | 2 | 414 KB | [`go2_description/urdf/_OMITTED.md`](./go2_description/urdf/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
