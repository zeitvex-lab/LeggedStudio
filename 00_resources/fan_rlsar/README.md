# fan_rlsar — 参考资源

> **来源**：`00_open/fan_rlsar/`　｜　**类型**：参考项目
> **关联机型**：unitree_go2（宇树 Go2 四足）、unitree_go2w（宇树 Go2W 轮足）、unitree_b2（宇树 B2 四足）、unitree_b2w（宇树 B2W 轮足）、unitree_g1（宇树 G1 人形）、deeprobotics_lite3（云深处 Lite3 四足）
> **定位**：RL-SAR 的个人分支（多机型实验）
> **收录**：165 个文件 / 22.0 MB（其中推理策略/模型文件 16 个）
> **已省略**：0 个文件 / 0 B（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **RL 训练工程**（101 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（57 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **动作与运动数据**（5 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **评测与测试**（2 个）：评测与测试：指标脚本、基准与回归用例

## 目录构成

```text
rl_sar/  （165 个文件）
    (直接文件)/
    .github/
    docker/
    policy/
    scripts/
    src/
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
| `.py` | 5 |
| `.msg` | 5 |
| `.md` | 4 |
| `.txt` | 4 |
| `.cc` | 4 |
| `.yml` | 3 |
| `.csv` | 2 |

## 文件索引（项目内相对路径）

```text
rl_sar/.gitattributes
rl_sar/.github/ISSUE_TEMPLATE/bug_report.yml
rl_sar/.github/ISSUE_TEMPLATE/config.yml
rl_sar/.github/LICENSE_HEADER.txt
rl_sar/.gitignore
rl_sar/.gitmodules
rl_sar/.pre-commit-config.yaml
rl_sar/CONTRIBUTORS.md
rl_sar/LICENSE
rl_sar/README.md
rl_sar/README_CN.md
rl_sar/VERSION
rl_sar/build.sh
rl_sar/docker/.dockerignore
rl_sar/docker/Dockerfile
rl_sar/docker/README.md
rl_sar/docker/docker-compose.yml
rl_sar/docker/entrypoint.sh
rl_sar/policy/a1/base.yaml
rl_sar/policy/a1/legged_gym/config.yaml
rl_sar/policy/a1/legged_gym/model.pt
rl_sar/policy/a1/robot_lab/config.yaml
rl_sar/policy/b2/base.yaml
rl_sar/policy/b2/robot_lab/config.yaml
rl_sar/policy/b2/robot_lab/policy.pt
rl_sar/policy/b2w/base.yaml
rl_sar/policy/b2w/robot_lab/config.yaml
rl_sar/policy/b2w/robot_lab/policy.pt
rl_sar/policy/d1/base.yaml
rl_sar/policy/d1/robot_lab/config.yaml
rl_sar/policy/d1/robot_lab/policy.pt
rl_sar/policy/g1/base.yaml
rl_sar/policy/g1/robomimic/charleston/config.yaml
rl_sar/policy/g1/robomimic/charleston/dance_0605_aligned.pt
rl_sar/policy/g1/robomimic/locomotion/config.yaml
rl_sar/policy/g1/robomimic/locomotion/policy_29dof.pt
rl_sar/policy/g1/whole_body_tracking/dance_102/G1_Take_102.bvh_60hz.csv
rl_sar/policy/g1/whole_body_tracking/dance_102/config.yaml
rl_sar/policy/g1/whole_body_tracking/dance_102/policy.pt
rl_sar/policy/g1/whole_body_tracking/gangnam_style/G1_gangnam_style_V01.bvh_60hz.csv
rl_sar/policy/g1/whole_body_tracking/gangnam_style/config.yaml
rl_sar/policy/g1/whole_body_tracking/gangnam_style/policy.pt
rl_sar/policy/go2/base.yaml
rl_sar/policy/go2/himloco/config.yaml
rl_sar/policy/go2/himloco/himloco.pt
rl_sar/policy/go2/robot_lab/config.yaml
rl_sar/policy/go2/robot_lab/policy.pt
rl_sar/policy/go2w/base.yaml
rl_sar/policy/go2w/robot_lab/config.yaml
rl_sar/policy/go2w/robot_lab/policy.pt
rl_sar/policy/gr1t1/base.yaml
rl_sar/policy/gr1t1/legged_gym/config.yaml
rl_sar/policy/gr1t1/legged_gym/model_4000_jit.pt
rl_sar/policy/gr1t2/base.yaml
rl_sar/policy/gr1t2/legged_gym/config.yaml
rl_sar/policy/gr1t2/legged_gym/model_4000_jit.pt
rl_sar/policy/l4w4/base.yaml
rl_sar/policy/l4w4/legged_gym/config.yaml
rl_sar/policy/l4w4/legged_gym/policy_25kg_b.pt
rl_sar/policy/lite3/base.yaml
rl_sar/policy/lite3/himloco/config.yaml
rl_sar/policy/lite3/himloco/policy_6_11.pt
rl_sar/policy/tita/base.yaml
rl_sar/policy/tita/robot_lab/config.yaml
rl_sar/policy/tita/robot_lab/policy.pt
rl_sar/scripts/common.sh
rl_sar/scripts/download_gazebo_models.sh
rl_sar/scripts/download_inference_runtime.sh
rl_sar/scripts/download_mujoco.sh
rl_sar/scripts/download_robot_descriptions.sh
rl_sar/scripts/install_pytorch_jetson.sh
rl_sar/src/rl_sar/CMakeLists.txt
rl_sar/src/rl_sar/fsm_robot/fsm_a1.hpp
rl_sar/src/rl_sar/fsm_robot/fsm_all.hpp
rl_sar/src/rl_sar/fsm_robot/fsm_b2.hpp
rl_sar/src/rl_sar/fsm_robot/fsm_b2w.hpp
rl_sar/src/rl_sar/fsm_robot/fsm_d1.hpp
rl_sar/src/rl_sar/fsm_robot/fsm_g1.hpp
rl_sar/src/rl_sar/fsm_robot/fsm_go2.hpp
rl_sar/src/rl_sar/fsm_robot/fsm_go2w.hpp
rl_sar/src/rl_sar/fsm_robot/fsm_gr1t1.hpp
rl_sar/src/rl_sar/fsm_robot/fsm_gr1t2.hpp
rl_sar/src/rl_sar/fsm_robot/fsm_l4w4.hpp
rl_sar/src/rl_sar/fsm_robot/fsm_lite3.hpp
rl_sar/src/rl_sar/fsm_robot/fsm_tita.hpp
rl_sar/src/rl_sar/include/rl_real_a1.hpp
rl_sar/src/rl_sar/include/rl_real_d1.hpp
rl_sar/src/rl_sar/include/rl_real_g1.hpp
rl_sar/src/rl_sar/include/rl_real_go2.hpp
rl_sar/src/rl_sar/include/rl_real_l4w4.hpp
rl_sar/src/rl_sar/include/rl_real_lite3.hpp
rl_sar/src/rl_sar/include/rl_sim.hpp
rl_sar/src/rl_sar/include/rl_sim_mujoco.hpp
rl_sar/src/rl_sar/launch/gazebo.launch
rl_sar/src/rl_sar/launch/gazebo.launch.py
rl_sar/src/rl_sar/library/core/fsm/fsm.hpp
rl_sar/src/rl_sar/library/core/inference_runtime/inference_runtime.cpp
rl_sar/src/rl_sar/library/core/inference_runtime/inference_runtime.hpp
rl_sar/src/rl_sar/library/core/logger/logger.hpp
rl_sar/src/rl_sar/library/core/loop/loop.hpp
rl_sar/src/rl_sar/library/core/matplotlibcpp/matplotlibcpp.h
rl_sar/src/rl_sar/library/core/motion_loader/motion_loader.cpp
rl_sar/src/rl_sar/library/core/motion_loader/motion_loader.hpp
rl_sar/src/rl_sar/library/core/observation_buffer/observation_buffer.cpp
rl_sar/src/rl_sar/library/core/observation_buffer/observation_buffer.hpp
rl_sar/src/rl_sar/library/core/rl_sdk/rl_sdk.cpp
rl_sar/src/rl_sar/library/core/rl_sdk/rl_sdk.hpp
rl_sar/src/rl_sar/library/core/vector_math/vector_math.hpp
rl_sar/src/rl_sar/library/thirdparty/mujoco_simulate/array_safety.h
rl_sar/src/rl_sar/library/thirdparty/mujoco_simulate/glfw_adapter.cc
rl_sar/src/rl_sar/library/thirdparty/mujoco_simulate/glfw_adapter.h
rl_sar/src/rl_sar/library/thirdparty/mujoco_simulate/glfw_corevideo.h
rl_sar/src/rl_sar/library/thirdparty/mujoco_simulate/glfw_corevideo.mm
rl_sar/src/rl_sar/library/thirdparty/mujoco_simulate/glfw_dispatch.cc
rl_sar/src/rl_sar/library/thirdparty/mujoco_simulate/glfw_dispatch.h
rl_sar/src/rl_sar/library/thirdparty/mujoco_simulate/macos_gui.mm
rl_sar/src/rl_sar/library/thirdparty/mujoco_simulate/mujoco_utils.hpp
rl_sar/src/rl_sar/library/thirdparty/mujoco_simulate/platform_ui_adapter.cc
rl_sar/src/rl_sar/library/thirdparty/mujoco_simulate/platform_ui_adapter.h
rl_sar/src/rl_sar/library/thirdparty/mujoco_simulate/simulate.cc
rl_sar/src/rl_sar/library/thirdparty/mujoco_simulate/simulate.h
rl_sar/src/rl_sar/library/thirdparty/robot_sdk/zhinao/l4w4_sdk/comm.h
rl_sar/src/rl_sar/library/thirdparty/robot_sdk/zhinao/l4w4_sdk/joystick.h
rl_sar/src/rl_sar/library/thirdparty/robot_sdk/zhinao/l4w4_sdk/l4w4_sdk.hpp
rl_sar/src/rl_sar/package.ros1.xml
rl_sar/src/rl_sar/package.ros2.xml
rl_sar/src/rl_sar/scripts/actuator_net.py
rl_sar/src/rl_sar/scripts/convert_policy.py
rl_sar/src/rl_sar/src/rl_real_a1.cpp
rl_sar/src/rl_sar/src/rl_real_d1.cpp
rl_sar/src/rl_sar/src/rl_real_g1.cpp
rl_sar/src/rl_sar/src/rl_real_go2.cpp
rl_sar/src/rl_sar/src/rl_real_l4w4.cpp
rl_sar/src/rl_sar/src/rl_real_lite3.cpp
rl_sar/src/rl_sar/src/rl_sim.cpp
rl_sar/src/rl_sar/src/rl_sim_mujoco.cpp
rl_sar/src/rl_sar/test/test_inference_runtime.cpp
rl_sar/src/rl_sar/test/test_observation_buffer.cpp
rl_sar/src/rl_sar/test/test_vector_math.cpp
rl_sar/src/rl_sar/worlds/earth.world
rl_sar/src/rl_sar/worlds/stairs.world
rl_sar/src/robot_joint_controller/CMakeLists.txt
rl_sar/src/robot_joint_controller/package.ros1.xml
rl_sar/src/robot_joint_controller/package.ros2.xml
rl_sar/src/robot_joint_controller/ros/include/robot_joint_controller.h
rl_sar/src/robot_joint_controller/ros/robot_joint_controller_plugins.xml
rl_sar/src/robot_joint_controller/ros/src/robot_joint_controller.cpp
rl_sar/src/robot_joint_controller/ros2/examples/config/robot_control.yaml
rl_sar/src/robot_joint_controller/ros2/examples/config/robot_control_group.yaml
rl_sar/src/robot_joint_controller/ros2/examples/launch/group_gazebo.launch.py
rl_sar/src/robot_joint_controller/ros2/examples/launch/single_gazebo.launch.py
rl_sar/src/robot_joint_controller/ros2/include/robot_joint_controller.hpp
rl_sar/src/robot_joint_controller/ros2/include/robot_joint_controller_group.hpp
rl_sar/src/robot_joint_controller/ros2/include/visibility_control.h
rl_sar/src/robot_joint_controller/ros2/robot_joint_controller_plugins.xml
rl_sar/src/robot_joint_controller/ros2/src/robot_joint_controller.cpp
rl_sar/src/robot_joint_controller/ros2/src/robot_joint_controller_group.cpp
rl_sar/src/robot_msgs/CMakeLists.txt
rl_sar/src/robot_msgs/msg/IMU.msg
rl_sar/src/robot_msgs/msg/MotorCommand.msg
rl_sar/src/robot_msgs/msg/MotorState.msg
rl_sar/src/robot_msgs/msg/RobotCommand.msg
rl_sar/src/robot_msgs/msg/RobotState.msg
rl_sar/src/robot_msgs/package.ros1.xml
rl_sar/src/robot_msgs/package.ros2.xml
```
