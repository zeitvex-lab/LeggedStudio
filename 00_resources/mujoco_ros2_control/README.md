# mujoco_ros2_control — 参考资源

> **来源**：`00_open/mujoco_ros2_control/`　｜　**类型**：部署与控制器接口参考（ros2_control）
> **关联机型**：（无，通用）
> **定位**：ros2_control × MuJoCo 系统接口：SystemInterface 插件 + MJCF/URDF 自动转换 + 插件体系 + 3D LiDAR 扩展；让同一套 ros2_control 控制器在仿真与真机间切换——部署侧控制器接口形态、MJCF/URDF 转换与 LiDAR 传感器参考
> **收录**：156 个文件 / 1.1 MB（其中推理策略/模型文件 0 个）
> **已省略**：9 个文件 / 3.1 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（4 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **关节与接口契约**（1 个）：关节与接口契约：关节序、limits、PD、action_scale、default pose、观测/动作维度
- **RL 训练工程**（1 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（113 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **文档与其它**（37 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （11 个文件）
.github/  （8 个文件）
    (直接文件)/
    workflows/
doc/  （7 个文件）
    (直接文件)/
docker/  （3 个文件）
    (直接文件)/
mujoco_extensions/  （11 个文件）
    doc/
    mujoco_3d_lidar/
mujoco_ros2_control/  （30 个文件）
    (直接文件)/
    docs/
    include/
    mujoco_ros2_control/
    resources/
    scripts/
    src/
    tests/
mujoco_ros2_control_demos/  （28 个文件）
    (直接文件)/
    config/
    demo_resources/
    doc/
    launch/
mujoco_ros2_control_msgs/  （13 个文件）
    (直接文件)/
    msg/
    srv/
mujoco_ros2_control_plugins/  （26 个文件）
    (直接文件)/
    doc/
    include/
    src/
    test/
mujoco_ros2_control_tests/  （19 个文件）
    (直接文件)/
    config/
    launch/
    src/
    test/
    test_resources/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.xml` | 23 |
| `.cpp` | 23 |
| `.py` | 21 |
| `.rst` | 14 |
| `.hpp` | 14 |
| `.yaml` | 11 |
| `(无扩展名)` | 9 |
| `.txt` | 8 |
| `.md` | 6 |
| `.yml` | 6 |
| `.msg` | 5 |
| `.srv` | 5 |
| `.urdf` | 3 |
| `.toml` | 2 |
| `.sh` | 2 |

## 文件索引（项目内相对路径）

```text
.clang-format
.dockerignore
.gitattributes
.github/dependabot.yml
.github/markdown-link-check.json
.github/workflows/ci.yaml
.github/workflows/coverage.yml
.github/workflows/docs.yaml
.github/workflows/format.yml
.github/workflows/pre-release.yml
.github/workflows/ros-deb-builder.yaml
.gitignore
.pre-commit-config.yaml
LICENSE
README.md
codecov.yml
colcon_defaults.yaml
doc/.gitignore
doc/COLCON_IGNORE
doc/README.md
doc/conf.py
doc/development.rst
doc/index.rst
doc/pixi.toml
docker-compose.yml
docker/Dockerfile
docker/Dockerfile.pixi
docker/entrypoint.sh
mujoco_extensions/doc/mujoco_extensions.rst
mujoco_extensions/mujoco_3d_lidar/.gitignore
mujoco_extensions/mujoco_3d_lidar/CHANGELOG.rst
mujoco_extensions/mujoco_3d_lidar/CMakeLists.txt
mujoco_extensions/mujoco_3d_lidar/README.md
mujoco_extensions/mujoco_3d_lidar/example/lidar.xml
mujoco_extensions/mujoco_3d_lidar/example/scene.xml
mujoco_extensions/mujoco_3d_lidar/include/mujoco_3d_lidar/3dlidar.h
mujoco_extensions/mujoco_3d_lidar/package.xml
mujoco_extensions/mujoco_3d_lidar/src/3dlidar.cpp
mujoco_extensions/mujoco_3d_lidar/src/register.cpp
mujoco_ros2_control/CHANGELOG.rst
mujoco_ros2_control/CMakeLists.txt
mujoco_ros2_control/README.md
mujoco_ros2_control/docs/hardware_interface.rst
mujoco_ros2_control/docs/modeling_tips.rst
mujoco_ros2_control/docs/tools.rst
mujoco_ros2_control/include/mujoco_ros2_control/data.hpp
mujoco_ros2_control/include/mujoco_ros2_control/mujoco_simulation.hpp
mujoco_ros2_control/include/mujoco_ros2_control/mujoco_system_interface.hpp
mujoco_ros2_control/include/mujoco_ros2_control/sim_display_text.hpp
mujoco_ros2_control/include/mujoco_ros2_control/utils.hpp
mujoco_ros2_control/mujoco_ros2_control/__init__.py
mujoco_ros2_control/mujoco_ros2_control/urdf_to_mujoco_utils.py
mujoco_ros2_control/mujoco_system_interface_plugin.xml
mujoco_ros2_control/package.xml
mujoco_ros2_control/resources/scene.xml
mujoco_ros2_control/scripts/find_missing_inertias.py
mujoco_ros2_control/scripts/make_mjcf_from_robot_description.py
mujoco_ros2_control/scripts/requirements.txt
mujoco_ros2_control/scripts/robot_description_to_mjcf.sh
mujoco_ros2_control/src/mujoco_ros2_control_node.cpp
mujoco_ros2_control/src/mujoco_simulation.cpp
mujoco_ros2_control/src/mujoco_system_interface.cpp
mujoco_ros2_control/src/render_loop_exit.hpp
mujoco_ros2_control/tests/CMakeLists.txt
mujoco_ros2_control/tests/test_headless_init.cpp
mujoco_ros2_control/tests/test_mujoco_simulation.cpp
mujoco_ros2_control/tests/test_mujoco_system_interface.cpp
mujoco_ros2_control/tests/test_plugin.cpp
mujoco_ros2_control/tests/test_urdf_to_mujoco_utils.py
mujoco_ros2_control_demos/CHANGELOG.rst
mujoco_ros2_control_demos/CMakeLists.txt
mujoco_ros2_control_demos/README.md
mujoco_ros2_control_demos/config/controllers.yaml
mujoco_ros2_control_demos/config/controllers_base_velocity.yaml
mujoco_ros2_control_demos/config/mujoco_pid.yaml
mujoco_ros2_control_demos/config/mujoco_ros2_control_plugins.yaml
mujoco_ros2_control_demos/config/mujoco_ros2_control_plugins_base_velocity.yaml
mujoco_ros2_control_demos/config/start_positions.xml
mujoco_ros2_control_demos/config/test_robot.rviz
mujoco_ros2_control_demos/demo_resources/mjcf_generation/test_inputs.xml
mujoco_ros2_control_demos/demo_resources/mobile_base/mobile_base.urdf
mujoco_ros2_control_demos/demo_resources/mobile_base/mobile_base.xml
mujoco_ros2_control_demos/demo_resources/pid_control/test_robot_pid.xml
mujoco_ros2_control_demos/demo_resources/robot/test_robot.urdf
mujoco_ros2_control_demos/demo_resources/robot/test_robot.xml
mujoco_ros2_control_demos/demo_resources/scenes/scene.xml
mujoco_ros2_control_demos/demo_resources/scenes/scene_info.xml
mujoco_ros2_control_demos/demo_resources/scenes/scene_mobile_base.xml
mujoco_ros2_control_demos/demo_resources/scenes/scene_pid.xml
mujoco_ros2_control_demos/doc/tutorials.rst
mujoco_ros2_control_demos/launch/01_basic_robot.launch.py
mujoco_ros2_control_demos/launch/02_mjcf_generation.launch.py
mujoco_ros2_control_demos/launch/03_pid_control.launch.py
mujoco_ros2_control_demos/launch/04_transmissions.launch.py
mujoco_ros2_control_demos/launch/05_base_velocity_plugin.launch.py
mujoco_ros2_control_demos/launch/demo.launch.py
mujoco_ros2_control_demos/package.xml
mujoco_ros2_control_msgs/CHANGELOG.rst
mujoco_ros2_control_msgs/CMakeLists.txt
mujoco_ros2_control_msgs/msg/ExternalWrench.msg
mujoco_ros2_control_msgs/msg/ExternalWrenchArray.msg
mujoco_ros2_control_msgs/msg/FreeJointState.msg
mujoco_ros2_control_msgs/msg/FreeJointStateArray.msg
mujoco_ros2_control_msgs/msg/SimulationState.msg
mujoco_ros2_control_msgs/package.xml
mujoco_ros2_control_msgs/srv/ApplyExternalWrench.srv
mujoco_ros2_control_msgs/srv/ResetWorld.srv
mujoco_ros2_control_msgs/srv/SetFreeJointState.srv
mujoco_ros2_control_msgs/srv/SetPause.srv
mujoco_ros2_control_msgs/srv/StepSimulation.srv
mujoco_ros2_control_plugins/CHANGELOG.rst
mujoco_ros2_control_plugins/CMakeLists.txt
mujoco_ros2_control_plugins/README.md
mujoco_ros2_control_plugins/doc/plugins.rst
mujoco_ros2_control_plugins/include/mujoco_ros2_control_plugins/mujoco_ros2_control_plugins_base.hpp
mujoco_ros2_control_plugins/mujoco_ros2_control_plugins.xml
mujoco_ros2_control_plugins/package.xml
mujoco_ros2_control_plugins/src/base_velocity_plugin.cpp
mujoco_ros2_control_plugins/src/base_velocity_plugin.hpp
mujoco_ros2_control_plugins/src/camera_plugin.cpp
mujoco_ros2_control_plugins/src/camera_plugin.hpp
mujoco_ros2_control_plugins/src/external_wrench_plugin.cpp
mujoco_ros2_control_plugins/src/external_wrench_plugin.hpp
mujoco_ros2_control_plugins/src/free_joint_state_publisher_plugin.cpp
mujoco_ros2_control_plugins/src/free_joint_state_publisher_plugin.hpp
mujoco_ros2_control_plugins/src/heartbeat_publisher_plugin.cpp
mujoco_ros2_control_plugins/src/heartbeat_publisher_plugin.hpp
mujoco_ros2_control_plugins/src/mujoco_3d_lidar_plugin.cpp
mujoco_ros2_control_plugins/src/mujoco_3d_lidar_plugin.hpp
mujoco_ros2_control_plugins/src/rangefinder_lidar_plugin.cpp
mujoco_ros2_control_plugins/src/rangefinder_lidar_plugin.hpp
mujoco_ros2_control_plugins/test/test_3d_lidar_plugin.cpp
mujoco_ros2_control_plugins/test/test_base_velocity_plugin.cpp
mujoco_ros2_control_plugins/test/test_camera_plugin.cpp
mujoco_ros2_control_plugins/test/test_external_wrench_plugin.cpp
mujoco_ros2_control_plugins/test/test_free_joint_state_publisher_plugin.cpp
mujoco_ros2_control_tests/CHANGELOG.rst
mujoco_ros2_control_tests/CMakeLists.txt
mujoco_ros2_control_tests/config/site_velocity_controllers.yaml
mujoco_ros2_control_tests/launch/site_velocity_test_launch.py
mujoco_ros2_control_tests/launch/test_launch.py
mujoco_ros2_control_tests/package.xml
mujoco_ros2_control_tests/src/test_plugin.cpp
mujoco_ros2_control_tests/src/test_plugin.xml
mujoco_ros2_control_tests/test/robot_launch_mjcf_generation_from_robot_description_test.py
mujoco_ros2_control_tests/test/robot_launch_mjcf_generation_test.py
mujoco_ros2_control_tests/test/robot_launch_pid_test.py
mujoco_ros2_control_tests/test/robot_launch_test.py
mujoco_ros2_control_tests/test/robot_launch_transmission_pid_test.py
mujoco_ros2_control_tests/test/robot_launch_transmission_test.py
mujoco_ros2_control_tests/test/site_velocity_launch_test.py
mujoco_ros2_control_tests/test/test_world_reset_dispatch.cpp
mujoco_ros2_control_tests/test_resources/robot/site_velocity_robot.urdf
mujoco_ros2_control_tests/test_resources/robot/site_velocity_robot.xml
mujoco_ros2_control_tests/test_resources/scenes/site_velocity_scene.xml
pixi.toml
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `.` | 1 | 776 KB | [`_OMITTED.md`](./_OMITTED.md) |
| `doc` | 1 | 50 KB | [`doc/_OMITTED.md`](./doc/_OMITTED.md) |
| `mujoco_extensions/mujoco_3d_lidar/docs` | 3 | 1018 KB | [`mujoco_extensions/mujoco_3d_lidar/docs/_OMITTED.md`](./mujoco_extensions/mujoco_3d_lidar/docs/_OMITTED.md) |
| `mujoco_ros2_control/docs/images` | 3 | 1.3 MB | [`mujoco_ros2_control/docs/images/_OMITTED.md`](./mujoco_ros2_control/docs/images/_OMITTED.md) |
| `mujoco_ros2_control/resources` | 1 | 15 KB | [`mujoco_ros2_control/resources/_OMITTED.md`](./mujoco_ros2_control/resources/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
