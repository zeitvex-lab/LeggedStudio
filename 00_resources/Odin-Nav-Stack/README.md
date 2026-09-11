# Odin-Nav-Stack — 参考资源

> **来源**：`00_open/Odin-Nav-Stack/`　｜　**类型**：参考项目
> **关联机型**：unitree_go2（宇树 Go2 四足）
> **定位**：Odin1 深度相机 + NeuPAN 局部规划的导航栈
> **收录**：104 个文件 / 14.7 MB（其中推理策略/模型文件 1 个）
> **已省略**：3 个文件 / 66.6 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **部署与推理**（85 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **文档与其它**（19 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （5 个文件）
docker/  （4 个文件）
    (直接文件)/
docs/  （3 个文件）
    (直接文件)/
ros_ws/  （85 个文件）
    (直接文件)/
    src/
scripts/  （7 个文件）
    (直接文件)/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.cpp` | 15 |
| `.txt` | 11 |
| `.yaml` | 11 |
| `.xml` | 10 |
| `.launch` | 10 |
| `(无扩展名)` | 9 |
| `.h` | 9 |
| `.py` | 9 |
| `.md` | 8 |
| `.sh` | 4 |
| `.srv` | 2 |
| `.rviz` | 2 |
| `.yml` | 1 |
| `.cn` | 1 |
| `.global` | 1 |

## 文件索引（项目内相对路径）

```text
.dockerignore
.gitignore
.gitmodules
LICENSE
README.md
docker/Dockerfile.cn
docker/Dockerfile.global
docker/docker-compose.yml
docker/entrypoint.sh
docs/DOCKER_SETUP.md
docs/TUNING_GUIDE.md
docs/TUNING_GUIDE_中文版.md
ros_ws/.catkin_workspace
ros_ws/.gitignore
ros_ws/src/CMakeLists.txt
ros_ws/src/fake360/CMakeLists.txt
ros_ws/src/fake360/include/fake360.h
ros_ws/src/fake360/launch/fake360.launch
ros_ws/src/fake360/package.xml
ros_ws/src/fake360/src/fake360.cpp
ros_ws/src/fish2pinhole/CMakeLists.txt
ros_ws/src/fish2pinhole/README.md
ros_ws/src/fish2pinhole/launch/calib.yaml
ros_ws/src/fish2pinhole/launch/cloud_crop.launch
ros_ws/src/fish2pinhole/launch/undistort.launch
ros_ws/src/fish2pinhole/package.xml
ros_ws/src/fish2pinhole/src/cloud_crop_node.cpp
ros_ws/src/fish2pinhole/src/fish2pinhole_node.cpp
ros_ws/src/map_planner/.gitignore
ros_ws/src/map_planner/CMakeLists.txt
ros_ws/src/map_planner/include/goal_state_machine.h
ros_ws/src/map_planner/include/map_planner.h
ros_ws/src/map_planner/launch/whole.launch
ros_ws/src/map_planner/maps/README.md
ros_ws/src/map_planner/maps/empty.yaml
ros_ws/src/map_planner/package.xml
ros_ws/src/map_planner/src/goal_state_machine.cpp
ros_ws/src/map_planner/src/map_planner.cpp
ros_ws/src/map_planner/srv/PlanPath.srv
ros_ws/src/model_planner/.gitignore
ros_ws/src/model_planner/CMakeLists.txt
ros_ws/src/model_planner/config/global_planner.yaml
ros_ws/src/model_planner/config/local_planner.yaml
ros_ws/src/model_planner/include/model_planner/astar.h
ros_ws/src/model_planner/include/model_planner/costmap.h
ros_ws/src/model_planner/include/model_planner/dwa_planner.h
ros_ws/src/model_planner/include/model_planner/global_planner.h
ros_ws/src/model_planner/include/model_planner/local_costmap.h
ros_ws/src/model_planner/include/model_planner/local_planner.h
ros_ws/src/model_planner/launch/model_planner.launch
ros_ws/src/model_planner/maps/README.md
ros_ws/src/model_planner/package.xml
ros_ws/src/model_planner/rviz/planner.rviz
ros_ws/src/model_planner/src/global_planner/astar.cpp
ros_ws/src/model_planner/src/global_planner/costmap.cpp
ros_ws/src/model_planner/src/global_planner/global_planner.cpp
ros_ws/src/model_planner/src/global_planner/global_planner_node.cpp
ros_ws/src/model_planner/src/local_planner/dwa_planner.cpp
ros_ws/src/model_planner/src/local_planner/local_costmap.cpp
ros_ws/src/model_planner/src/local_planner/local_planner.cpp
ros_ws/src/model_planner/src/local_planner/local_planner_node.cpp
ros_ws/src/navigation_planner/CMakeLists.txt
ros_ws/src/navigation_planner/config/base_local_planner_params.yaml
ros_ws/src/navigation_planner/config/costmap_common_params.yaml
ros_ws/src/navigation_planner/config/dwa_local_planner_params.yaml
ros_ws/src/navigation_planner/config/global_costmap_params.yaml
ros_ws/src/navigation_planner/config/global_planner_params.yaml
ros_ws/src/navigation_planner/config/local_costmap_params.yaml
ros_ws/src/navigation_planner/config/move_base_params.yaml
ros_ws/src/navigation_planner/launch/navigation_planner.launch
ros_ws/src/navigation_planner/package.xml
ros_ws/src/odin_vlm_terminal/CMakeLists.txt
ros_ws/src/odin_vlm_terminal/launch/odin_vlm_terminal.launch
ros_ws/src/odin_vlm_terminal/package.xml
ros_ws/src/odin_vlm_terminal/scripts/ros_vlm_terminal.py
ros_ws/src/pcd2pgm/.gitignore
ros_ws/src/pcd2pgm/CMakeLists.txt
ros_ws/src/pcd2pgm/launch/pcd2pgm.launch
ros_ws/src/pcd2pgm/maps/README.md
ros_ws/src/pcd2pgm/package.xml
ros_ws/src/pcd2pgm/src/pcd2pgm_node.cpp
ros_ws/src/pointcloud_saver/CMakeLists.txt
ros_ws/src/pointcloud_saver/launch/pointcloud_saver.launch
ros_ws/src/pointcloud_saver/package.xml
ros_ws/src/pointcloud_saver/scripts/pointcloud_saver_node.py
ros_ws/src/pointcloud_saver/srv/SaveMap.srv
ros_ws/src/unitree_control/CMakeLists.txt
ros_ws/src/unitree_control/package.xml
ros_ws/src/unitree_control/src/unitree_vel_controller.cpp
ros_ws/src/yolo_ros/CMakeLists.txt
ros_ws/src/yolo_ros/config/yolo_visualization.rviz
ros_ws/src/yolo_ros/launch/yolo_detection.launch
ros_ws/src/yolo_ros/package.xml
ros_ws/src/yolo_ros/scripts/models/yolov5s.pt
ros_ws/src/yolo_ros/scripts/object_query_node.py
ros_ws/src/yolo_ros/scripts/tf_relay_node.py
ros_ws/src/yolo_ros/scripts/yolo_detector.py
scripts/VLN.py
scripts/bag_record.sh
scripts/map_recording.sh
scripts/pcd_convert.py
scripts/point_record.py
scripts/run_yolo_detector.sh
scripts/str_cmd_control.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `img` | 2 | 47.5 MB | [`img/_OMITTED.md`](./img/_OMITTED.md) |
| `ros_ws/src/map_planner/maps` | 1 | 19.1 MB | [`ros_ws/src/map_planner/maps/_OMITTED.md`](./ros_ws/src/map_planner/maps/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
