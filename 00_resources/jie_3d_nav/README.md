# jie_3d_nav — 参考资源

> **来源**：`00_open/jie_3d_nav/`　｜　**类型**：导航与感知参考
> **关联机型**：（无，通用）
> **定位**：JIE 3D 导航栈（jie_octomap + octo_planner）：感知与规划参考
> **收录**：69 个文件 / 2.0 MB（其中推理策略/模型文件 0 个）
> **已省略**：5 个文件 / 1.6 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **RL 训练工程**（4 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（1 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **评测与测试**（5 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（59 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （4 个文件）
jie_map_msgs/  （6 个文件）
    (直接文件)/
    srv/
jie_octomap/  （50 个文件）
    (直接文件)/
    config/
    jie_octomap/
    launch/
    rviz/
    scripts/
    src/
    web/
    worlds/
octo_planner/  （9 个文件）
    (直接文件)/
    config/
    launch/
    src/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 24 |
| `.cpp` | 11 |
| `(无扩展名)` | 6 |
| `.srv` | 4 |
| `.yaml` | 4 |
| `.js` | 4 |
| `.txt` | 3 |
| `.xml` | 3 |
| `.md` | 2 |
| `.rviz` | 2 |
| `.world` | 2 |
| `.sh` | 1 |
| `.rules` | 1 |
| `.html` | 1 |
| `.css` | 1 |

## 文件索引（项目内相对路径）

```text
.gitignore
README.en.md
README.md
install_deps_humble.sh
jie_map_msgs/CMakeLists.txt
jie_map_msgs/package.xml
jie_map_msgs/srv/ExportNavigationSnapshot.srv
jie_map_msgs/srv/GetNavigationMapMeta.srv
jie_map_msgs/srv/LoadNavigationMapPackage.srv
jie_map_msgs/srv/SaveNavigationMapPackage.srv
jie_octomap/CMakeLists.txt
jie_octomap/config/loc_control_command.yaml
jie_octomap/config/slam_control_command.yaml
jie_octomap/jie_octomap/__init__.py
jie_octomap/jie_octomap/map_package_manager.py
jie_octomap/jie_octomap/map_save_gui.py
jie_octomap/jie_octomap/map_viewer_gui.py
jie_octomap/jie_octomap/pcd_map_import_gui.py
jie_octomap/jie_octomap/ros_map_import_gui.py
jie_octomap/launch/import_gazebo_world.launch.py
jie_octomap/launch/import_pcd_map.launch.py
jie_octomap/launch/import_ros_map.launch.py
jie_octomap/launch/map_manager.launch.py
jie_octomap/launch/octomap_open3d.launch.py
jie_octomap/launch/octomap_test.launch.py
jie_octomap/launch/odin1_loc.launch.py
jie_octomap/launch/odin1_slam.launch.py
jie_octomap/launch/web_octomap.launch.py
jie_octomap/package.xml
jie_octomap/rviz/octomap_test.rviz
jie_octomap/rviz/odin1_loc.rviz
jie_octomap/scripts/99-odin-usb.rules
jie_octomap/scripts/map_package_manager
jie_octomap/scripts/map_save_gui
jie_octomap/scripts/map_viewer_gui
jie_octomap/scripts/no_cache_http_server.py
jie_octomap/scripts/open3d_octomap_viewer.py
jie_octomap/scripts/pcd_file_publisher.py
jie_octomap/scripts/pcd_map_import_gui
jie_octomap/scripts/ros_map_import_gui
jie_octomap/scripts/save_bin_map_gui.py
jie_octomap/scripts/web_click_selector.py
jie_octomap/scripts/world_file_picker_gui.py
jie_octomap/scripts/world_selector_gui.py
jie_octomap/src/occupancy_grid_to_octomap_node.cpp
jie_octomap/src/octomap_open3d_viewer_node.cpp
jie_octomap/src/octomap_test.cpp
jie_octomap/src/octomap_to_cloud_node.cpp
jie_octomap/src/octomap_to_occupied_markers_node.cpp
jie_octomap/src/pcd_to_octomap_node.cpp
jie_octomap/src/rviz_click_selector_node.cpp
jie_octomap/src/world_to_octomap_node.cpp
jie_octomap/web/index.html
jie_octomap/web/main.js
jie_octomap/web/styles.css
jie_octomap/web/vendor/jsm/controls/OrbitControls.js
jie_octomap/web/vendor/roslib.min.js
jie_octomap/web/vendor/three.module.js
jie_octomap/worlds/2_storey.world
jie_octomap/worlds/field.world
octo_planner/CMakeLists.txt
octo_planner/config/nav_params.yaml
octo_planner/config/nav_params_home.yaml
octo_planner/launch/nav.launch.py
octo_planner/launch/web_test.launch.py
octo_planner/package.xml
octo_planner/src/d1_controller.cpp
octo_planner/src/jie_path_node.cpp
octo_planner/src/test_map_to_odom_tf_node.cpp
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `media` | 5 | 1.6 MB | [`media/_OMITTED.md`](./media/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
