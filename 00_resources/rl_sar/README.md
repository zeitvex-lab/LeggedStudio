# rl_sar — 参考资源

> **来源**：`00_open/rl_sar/`　｜　**类型**：参考项目
> **关联机型**：unitree_go2（宇树 Go2 四足）、unitree_go2w（宇树 Go2W 轮足）、unitree_b2（宇树 B2 四足）、unitree_b2w（宇树 B2W 轮足）、unitree_g1（宇树 G1 人形）、deeprobotics_lite3（云深处 Lite3 四足）
> **定位**：RL-SAR：仿真到实机部署框架（多机型、含策略与 C++ 部署）
> **收录**：171 个文件 / 30.3 MB（其中推理策略/模型文件 22 个）
> **已省略**：0 个文件 / 0 B（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（3 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（61 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（63 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **动作与运动数据**（5 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **评测与测试**（2 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（37 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （10 个文件）
.github/  （3 个文件）
    (直接文件)/
    ISSUE_TEMPLATE/
docker/  （5 个文件）
    (直接文件)/
policy/  （53 个文件）
    a1/
    b2/
    b2w/
    d1/
    g1/
    go2/
    go2w/
    gr1t1/
    gr1t2/
    l4w4/
    lite3/
    tita/
scripts/  （6 个文件）
    (直接文件)/
src/  （94 个文件）
    rl_sar/
    robot_joint_controller/
    robot_msgs/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.hpp` | 33 |
| `.yaml` | 32 |
| `.cpp` | 18 |
| `.pt` | 16 |
| `.h` | 11 |
| `.sh` | 8 |
| `.xml` | 8 |
| `(无扩展名)` | 7 |
| `.onnx` | 6 |
| `.py` | 5 |
| `.msg` | 5 |
| `.md` | 4 |
| `.txt` | 4 |
| `.cc` | 4 |
| `.yml` | 3 |

## 文件索引（项目内相对路径）

```text
.gitattributes
.github/ISSUE_TEMPLATE/bug_report.yml
.github/ISSUE_TEMPLATE/config.yml
.github/LICENSE_HEADER.txt
.gitignore
.gitmodules
.pre-commit-config.yaml
CONTRIBUTORS.md
LICENSE
README.md
README_CN.md
VERSION
build.sh
docker/.dockerignore
docker/Dockerfile
docker/README.md
docker/docker-compose.yml
docker/entrypoint.sh
policy/a1/base.yaml
policy/a1/legged_gym/config.yaml
policy/a1/legged_gym/model.onnx
policy/a1/legged_gym/model.pt
policy/a1/robot_lab/config.yaml
policy/b2/base.yaml
policy/b2/robot_lab/config.yaml
policy/b2/robot_lab/policy.onnx
policy/b2/robot_lab/policy.pt
policy/b2w/base.yaml
policy/b2w/robot_lab/config.yaml
policy/b2w/robot_lab/policy.onnx
policy/b2w/robot_lab/policy.pt
policy/d1/base.yaml
policy/d1/robot_lab/config.yaml
policy/d1/robot_lab/policy.onnx
policy/d1/robot_lab/policy.pt
policy/g1/base.yaml
policy/g1/robomimic/charleston/config.yaml
policy/g1/robomimic/charleston/dance_0605_aligned.pt
policy/g1/robomimic/locomotion/config.yaml
policy/g1/robomimic/locomotion/policy_29dof.pt
policy/g1/whole_body_tracking/dance_102/G1_Take_102.bvh_60hz.csv
policy/g1/whole_body_tracking/dance_102/config.yaml
policy/g1/whole_body_tracking/dance_102/policy.pt
policy/g1/whole_body_tracking/gangnam_style/G1_gangnam_style_V01.bvh_60hz.csv
policy/g1/whole_body_tracking/gangnam_style/config.yaml
policy/g1/whole_body_tracking/gangnam_style/policy.pt
policy/go2/base.yaml
policy/go2/himloco/config.yaml
policy/go2/himloco/himloco.pt
policy/go2/robot_lab/config.yaml
policy/go2/robot_lab/policy.pt
policy/go2w/base.yaml
policy/go2w/robot_lab/config.yaml
policy/go2w/robot_lab/policy.onnx
policy/go2w/robot_lab/policy.pt
policy/gr1t1/base.yaml
policy/gr1t1/legged_gym/config.yaml
policy/gr1t1/legged_gym/model_4000_jit.pt
policy/gr1t2/base.yaml
policy/gr1t2/legged_gym/config.yaml
policy/gr1t2/legged_gym/model_4000_jit.pt
policy/l4w4/base.yaml
policy/l4w4/legged_gym/config.yaml
policy/l4w4/legged_gym/policy_25kg_b.pt
policy/lite3/base.yaml
policy/lite3/himloco/config.yaml
policy/lite3/himloco/policy_6_11.onnx
policy/lite3/himloco/policy_6_11.pt
policy/tita/base.yaml
policy/tita/robot_lab/config.yaml
policy/tita/robot_lab/policy.pt
scripts/common.sh
scripts/download_gazebo_models.sh
scripts/download_inference_runtime.sh
scripts/download_mujoco.sh
scripts/download_robot_descriptions.sh
scripts/install_pytorch_jetson.sh
src/rl_sar/CMakeLists.txt
src/rl_sar/fsm_robot/fsm_a1.hpp
src/rl_sar/fsm_robot/fsm_all.hpp
src/rl_sar/fsm_robot/fsm_b2.hpp
src/rl_sar/fsm_robot/fsm_b2w.hpp
src/rl_sar/fsm_robot/fsm_d1.hpp
src/rl_sar/fsm_robot/fsm_g1.hpp
src/rl_sar/fsm_robot/fsm_go2.hpp
src/rl_sar/fsm_robot/fsm_go2w.hpp
src/rl_sar/fsm_robot/fsm_gr1t1.hpp
src/rl_sar/fsm_robot/fsm_gr1t2.hpp
src/rl_sar/fsm_robot/fsm_l4w4.hpp
src/rl_sar/fsm_robot/fsm_lite3.hpp
src/rl_sar/fsm_robot/fsm_tita.hpp
src/rl_sar/include/rl_real_a1.hpp
src/rl_sar/include/rl_real_d1.hpp
src/rl_sar/include/rl_real_g1.hpp
src/rl_sar/include/rl_real_go2.hpp
src/rl_sar/include/rl_real_l4w4.hpp
src/rl_sar/include/rl_real_lite3.hpp
src/rl_sar/include/rl_sim.hpp
src/rl_sar/include/rl_sim_mujoco.hpp
src/rl_sar/launch/gazebo.launch
src/rl_sar/launch/gazebo.launch.py
src/rl_sar/library/core/fsm/fsm.hpp
src/rl_sar/library/core/inference_runtime/inference_runtime.cpp
src/rl_sar/library/core/inference_runtime/inference_runtime.hpp
src/rl_sar/library/core/logger/logger.hpp
src/rl_sar/library/core/loop/loop.hpp
src/rl_sar/library/core/matplotlibcpp/matplotlibcpp.h
src/rl_sar/library/core/motion_loader/motion_loader.cpp
src/rl_sar/library/core/motion_loader/motion_loader.hpp
src/rl_sar/library/core/observation_buffer/observation_buffer.cpp
src/rl_sar/library/core/observation_buffer/observation_buffer.hpp
src/rl_sar/library/core/rl_sdk/rl_sdk.cpp
src/rl_sar/library/core/rl_sdk/rl_sdk.hpp
src/rl_sar/library/core/vector_math/vector_math.hpp
src/rl_sar/library/thirdparty/mujoco_simulate/array_safety.h
src/rl_sar/library/thirdparty/mujoco_simulate/glfw_adapter.cc
src/rl_sar/library/thirdparty/mujoco_simulate/glfw_adapter.h
src/rl_sar/library/thirdparty/mujoco_simulate/glfw_corevideo.h
src/rl_sar/library/thirdparty/mujoco_simulate/glfw_corevideo.mm
src/rl_sar/library/thirdparty/mujoco_simulate/glfw_dispatch.cc
src/rl_sar/library/thirdparty/mujoco_simulate/glfw_dispatch.h
src/rl_sar/library/thirdparty/mujoco_simulate/macos_gui.mm
src/rl_sar/library/thirdparty/mujoco_simulate/mujoco_utils.hpp
src/rl_sar/library/thirdparty/mujoco_simulate/platform_ui_adapter.cc
src/rl_sar/library/thirdparty/mujoco_simulate/platform_ui_adapter.h
src/rl_sar/library/thirdparty/mujoco_simulate/simulate.cc
src/rl_sar/library/thirdparty/mujoco_simulate/simulate.h
src/rl_sar/library/thirdparty/robot_sdk/zhinao/l4w4_sdk/comm.h
src/rl_sar/library/thirdparty/robot_sdk/zhinao/l4w4_sdk/joystick.h
src/rl_sar/library/thirdparty/robot_sdk/zhinao/l4w4_sdk/l4w4_sdk.hpp
src/rl_sar/package.ros1.xml
src/rl_sar/package.ros2.xml
src/rl_sar/scripts/actuator_net.py
src/rl_sar/scripts/convert_policy.py
src/rl_sar/src/rl_real_a1.cpp
src/rl_sar/src/rl_real_d1.cpp
src/rl_sar/src/rl_real_g1.cpp
src/rl_sar/src/rl_real_go2.cpp
src/rl_sar/src/rl_real_l4w4.cpp
src/rl_sar/src/rl_real_lite3.cpp
src/rl_sar/src/rl_sim.cpp
src/rl_sar/src/rl_sim_mujoco.cpp
src/rl_sar/test/test_inference_runtime.cpp
src/rl_sar/test/test_observation_buffer.cpp
src/rl_sar/test/test_vector_math.cpp
src/rl_sar/worlds/earth.world
src/rl_sar/worlds/stairs.world
src/robot_joint_controller/CMakeLists.txt
src/robot_joint_controller/package.ros1.xml
src/robot_joint_controller/package.ros2.xml
src/robot_joint_controller/ros/include/robot_joint_controller.h
src/robot_joint_controller/ros/robot_joint_controller_plugins.xml
src/robot_joint_controller/ros/src/robot_joint_controller.cpp
src/robot_joint_controller/ros2/examples/config/robot_control.yaml
src/robot_joint_controller/ros2/examples/config/robot_control_group.yaml
src/robot_joint_controller/ros2/examples/launch/group_gazebo.launch.py
src/robot_joint_controller/ros2/examples/launch/single_gazebo.launch.py
src/robot_joint_controller/ros2/include/robot_joint_controller.hpp
src/robot_joint_controller/ros2/include/robot_joint_controller_group.hpp
src/robot_joint_controller/ros2/include/visibility_control.h
src/robot_joint_controller/ros2/robot_joint_controller_plugins.xml
src/robot_joint_controller/ros2/src/robot_joint_controller.cpp
src/robot_joint_controller/ros2/src/robot_joint_controller_group.cpp
src/robot_msgs/CMakeLists.txt
src/robot_msgs/msg/IMU.msg
src/robot_msgs/msg/MotorCommand.msg
src/robot_msgs/msg/MotorState.msg
src/robot_msgs/msg/RobotCommand.msg
src/robot_msgs/msg/RobotState.msg
src/robot_msgs/package.ros1.xml
src/robot_msgs/package.ros2.xml
```
