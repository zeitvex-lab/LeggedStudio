# tron1-robot-description — 参考资源

> **来源**：`00_open/tron1-robot-description/`　｜　**类型**：参考项目
> **关联机型**：limx_tron1_pf（逐际动力 TRON1-PF）、limx_tron1_sf（逐际动力 TRON1-SF）、limx_tron1_wf（逐际动力 TRON1-WF）
> **定位**：TRON1 机型描述（URDF/xacro）
> **收录**：99 个文件 / 730 KB（其中推理策略/模型文件 0 个）
> **已省略**：127 个文件 / 278.0 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（92 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **文档与其它**（7 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （5 个文件）
pointfoot/  （90 个文件）
    PF_P441A/
    PF_P441B/
    PF_P441C/
    PF_P441C2/
    PF_TRON1A/
    PF_TRON1B/
    SF_TRON1A/
    SF_TRON1B/
    WF_TRON1A/
    WF_TRON1B/
wheellegged/  （4 个文件）
    WL_P311D/
    WL_P311E/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.xacro` | 70 |
| `.urdf` | 12 |
| `.xml` | 11 |
| `.md` | 2 |
| `.srdf` | 2 |
| `.txt` | 1 |
| `(无扩展名)` | 1 |

## 文件索引（项目内相对路径）

```text
CMakeLists.txt
LICENSE
README.md
README_cn.md
package.xml
pointfoot/PF_P441A/urdf/robot.urdf
pointfoot/PF_P441A/xacro/const.xacro
pointfoot/PF_P441A/xacro/gazebo.xacro
pointfoot/PF_P441A/xacro/leg.xacro
pointfoot/PF_P441A/xacro/materials.xacro
pointfoot/PF_P441A/xacro/robot.xacro
pointfoot/PF_P441A/xacro/ros2_control_interface.xacro
pointfoot/PF_P441A/xacro/transmission.xacro
pointfoot/PF_P441A/xml/robot.xml
pointfoot/PF_P441B/urdf/robot.urdf
pointfoot/PF_P441B/xacro/const.xacro
pointfoot/PF_P441B/xacro/gazebo.xacro
pointfoot/PF_P441B/xacro/leg.xacro
pointfoot/PF_P441B/xacro/materials.xacro
pointfoot/PF_P441B/xacro/robot.xacro
pointfoot/PF_P441B/xacro/ros2_control_interface.xacro
pointfoot/PF_P441B/xacro/transmission.xacro
pointfoot/PF_P441B/xml/robot.xml
pointfoot/PF_P441C/urdf/robot.urdf
pointfoot/PF_P441C/xacro/const.xacro
pointfoot/PF_P441C/xacro/gazebo.xacro
pointfoot/PF_P441C/xacro/leg.xacro
pointfoot/PF_P441C/xacro/materials.xacro
pointfoot/PF_P441C/xacro/robot.xacro
pointfoot/PF_P441C/xacro/ros2_control_interface.xacro
pointfoot/PF_P441C/xacro/transmission.xacro
pointfoot/PF_P441C/xml/robot.xml
pointfoot/PF_P441C2/urdf/robot.urdf
pointfoot/PF_P441C2/xacro/const.xacro
pointfoot/PF_P441C2/xacro/gazebo.xacro
pointfoot/PF_P441C2/xacro/leg.xacro
pointfoot/PF_P441C2/xacro/materials.xacro
pointfoot/PF_P441C2/xacro/robot.xacro
pointfoot/PF_P441C2/xacro/ros2_control_interface.xacro
pointfoot/PF_P441C2/xacro/transmission.xacro
pointfoot/PF_P441C2/xml/robot.xml
pointfoot/PF_TRON1A/urdf/robot.urdf
pointfoot/PF_TRON1A/xacro/const.xacro
pointfoot/PF_TRON1A/xacro/gazebo.xacro
pointfoot/PF_TRON1A/xacro/leg.xacro
pointfoot/PF_TRON1A/xacro/materials.xacro
pointfoot/PF_TRON1A/xacro/robot.xacro
pointfoot/PF_TRON1A/xacro/ros2_control_interface.xacro
pointfoot/PF_TRON1A/xacro/transmission.xacro
pointfoot/PF_TRON1A/xml/robot.xml
pointfoot/PF_TRON1B/urdf/robot.urdf
pointfoot/PF_TRON1B/xacro/const.xacro
pointfoot/PF_TRON1B/xacro/gazebo.xacro
pointfoot/PF_TRON1B/xacro/leg.xacro
pointfoot/PF_TRON1B/xacro/materials.xacro
pointfoot/PF_TRON1B/xacro/robot.xacro
pointfoot/PF_TRON1B/xacro/ros2_control_interface.xacro
pointfoot/PF_TRON1B/xacro/transmission.xacro
pointfoot/PF_TRON1B/xml/robot.xml
pointfoot/SF_TRON1A/urdf/robot.urdf
pointfoot/SF_TRON1A/xacro/const.xacro
pointfoot/SF_TRON1A/xacro/gazebo.xacro
pointfoot/SF_TRON1A/xacro/leg.xacro
pointfoot/SF_TRON1A/xacro/materials.xacro
pointfoot/SF_TRON1A/xacro/robot.xacro
pointfoot/SF_TRON1A/xacro/ros2_control_interface.xacro
pointfoot/SF_TRON1A/xacro/transmission.xacro
pointfoot/SF_TRON1A/xml/robot.xml
pointfoot/SF_TRON1B/urdf/robot.urdf
pointfoot/SF_TRON1B/xacro/const.xacro
pointfoot/SF_TRON1B/xacro/gazebo.xacro
pointfoot/SF_TRON1B/xacro/leg.xacro
pointfoot/SF_TRON1B/xacro/materials.xacro
pointfoot/SF_TRON1B/xacro/robot.xacro
pointfoot/SF_TRON1B/xacro/ros2_control_interface.xacro
pointfoot/SF_TRON1B/xacro/transmission.xacro
pointfoot/SF_TRON1B/xml/robot.xml
pointfoot/WF_TRON1A/urdf/robot.urdf
pointfoot/WF_TRON1A/xacro/const.xacro
pointfoot/WF_TRON1A/xacro/gazebo.xacro
pointfoot/WF_TRON1A/xacro/leg.xacro
pointfoot/WF_TRON1A/xacro/materials.xacro
pointfoot/WF_TRON1A/xacro/robot.xacro
pointfoot/WF_TRON1A/xacro/ros2_control_interface.xacro
pointfoot/WF_TRON1A/xacro/transmission.xacro
pointfoot/WF_TRON1A/xml/robot.xml
pointfoot/WF_TRON1B/urdf/robot.urdf
pointfoot/WF_TRON1B/xacro/const.xacro
pointfoot/WF_TRON1B/xacro/gazebo.xacro
pointfoot/WF_TRON1B/xacro/leg.xacro
pointfoot/WF_TRON1B/xacro/materials.xacro
pointfoot/WF_TRON1B/xacro/robot.xacro
pointfoot/WF_TRON1B/xacro/ros2_control_interface.xacro
pointfoot/WF_TRON1B/xacro/transmission.xacro
pointfoot/WF_TRON1B/xml/robot.xml
wheellegged/WL_P311D/srdf/robot.srdf
wheellegged/WL_P311D/urdf/robot.urdf
wheellegged/WL_P311E/srdf/robot.srdf
wheellegged/WL_P311E/urdf/robot.urdf
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `pointfoot/PF_P441A/meshes` | 9 | 14.5 MB | [`pointfoot/PF_P441A/meshes/_OMITTED.md`](./pointfoot/PF_P441A/meshes/_OMITTED.md) |
| `pointfoot/PF_P441B/meshes` | 9 | 23.5 MB | [`pointfoot/PF_P441B/meshes/_OMITTED.md`](./pointfoot/PF_P441B/meshes/_OMITTED.md) |
| `pointfoot/PF_P441C/meshes` | 9 | 22.0 MB | [`pointfoot/PF_P441C/meshes/_OMITTED.md`](./pointfoot/PF_P441C/meshes/_OMITTED.md) |
| `pointfoot/PF_P441C2/meshes` | 9 | 15.0 MB | [`pointfoot/PF_P441C2/meshes/_OMITTED.md`](./pointfoot/PF_P441C2/meshes/_OMITTED.md) |
| `pointfoot/PF_TRON1A/meshes` | 9 | 17.1 MB | [`pointfoot/PF_TRON1A/meshes/_OMITTED.md`](./pointfoot/PF_TRON1A/meshes/_OMITTED.md) |
| `pointfoot/PF_TRON1B/meshes` | 9 | 17.1 MB | [`pointfoot/PF_TRON1B/meshes/_OMITTED.md`](./pointfoot/PF_TRON1B/meshes/_OMITTED.md) |
| `pointfoot/SF_TRON1A/meshes` | 9 | 18.6 MB | [`pointfoot/SF_TRON1A/meshes/_OMITTED.md`](./pointfoot/SF_TRON1A/meshes/_OMITTED.md) |
| `pointfoot/SF_TRON1B/meshes` | 9 | 18.6 MB | [`pointfoot/SF_TRON1B/meshes/_OMITTED.md`](./pointfoot/SF_TRON1B/meshes/_OMITTED.md) |
| `pointfoot/WF_TRON1A/meshes` | 9 | 19.1 MB | [`pointfoot/WF_TRON1A/meshes/_OMITTED.md`](./pointfoot/WF_TRON1A/meshes/_OMITTED.md) |
| `pointfoot/WF_TRON1B/meshes` | 9 | 19.1 MB | [`pointfoot/WF_TRON1B/meshes/_OMITTED.md`](./pointfoot/WF_TRON1B/meshes/_OMITTED.md) |
| `pointfoot/meshes_camera` | 1 | 15.1 MB | [`pointfoot/meshes_camera/_OMITTED.md`](./pointfoot/meshes_camera/_OMITTED.md) |
| `wheellegged/WL_P311D/meshes` | 18 | 36.9 MB | [`wheellegged/WL_P311D/meshes/_OMITTED.md`](./wheellegged/WL_P311D/meshes/_OMITTED.md) |
| `wheellegged/WL_P311E/meshes` | 18 | 41.3 MB | [`wheellegged/WL_P311E/meshes/_OMITTED.md`](./wheellegged/WL_P311E/meshes/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
