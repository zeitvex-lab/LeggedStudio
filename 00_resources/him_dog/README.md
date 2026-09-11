# him_dog — 参考资源

> **来源**：`00_open/him_dog/`　｜　**类型**：参考项目
> **关联机型**：unitree_go1（宇树 Go1 四足）、unitree_go2（宇树 Go2 四足）
> **定位**：him_dog 四足工程
> **收录**：212 个文件 / 28.1 MB（其中推理策略/模型文件 15 个）
> **已省略**：161 个文件 / 155.0 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（28 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **关节与接口契约**（1 个）：关节与接口契约：关节序、limits、PD、action_scale、default pose、观测/动作维度
- **RL 训练工程**（26 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（22 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **地形与场景**（9 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **动作与运动数据**（12 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **评测与测试**（30 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（84 个）：文档、说明、许可与零散脚本

## 目录构成

```text
himdog/  （113 个文件）
    (直接文件)/
    dm_imu/
    dog_control/
    dog_nav/
    dog_policy_test/
uw-himloco/  （99 个文件）
    (直接文件)/
    legged_gym/
    mujoco/
    resources/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 69 |
| `.cpp` | 32 |
| `.xml` | 17 |
| `.urdf` | 16 |
| `.yaml` | 13 |
| `.onnx` | 13 |
| `.txt` | 11 |
| `.h` | 8 |
| `(无扩展名)` | 6 |
| `.hpp` | 6 |
| `.md` | 5 |
| `.msg` | 3 |
| `.sh` | 3 |
| `.launch` | 2 |
| `.cfg` | 1 |

## 文件索引（项目内相对路径）

```text
himdog/.gitignore
himdog/README.md
himdog/dm_imu/LICENSE
himdog/dm_imu/config/params.yaml
himdog/dm_imu/dm_imu/__init__.py
himdog/dm_imu/dm_imu/modules/__init__.py
himdog/dm_imu/dm_imu/modules/dm_crc.py
himdog/dm_imu/dm_imu/modules/dm_serial.py
himdog/dm_imu/dm_imu/node.py
himdog/dm_imu/launch/dm_imu.launch.py
himdog/dm_imu/launch/dm_imu_rviz.launch.py
himdog/dm_imu/package.xml
himdog/dm_imu/resource/dm_imu
himdog/dm_imu/rviz/imu.rviz
himdog/dm_imu/setup.cfg
himdog/dm_imu/setup.py
himdog/dog_control/CMakeLists.txt
himdog/dog_control/include/motor_ros2/controller_helpers.h
himdog/dog_control/include/motor_ros2/dji_3508_controller.h
himdog/dog_control/include/motor_ros2/leg_model.h
himdog/dog_control/include/motor_ros2/locomotion_core_types.h
himdog/dog_control/include/motor_ros2/locomotion_params.h
himdog/dog_control/include/motor_ros2/locomotion_planner.h
himdog/dog_control/include/motor_ros2/locomotion_runtime.h
himdog/dog_control/include/motor_ros2/motor_cfg.h
himdog/dog_control/launch/display.launch.py
himdog/dog_control/launch/dog_control.launch.py
himdog/dog_control/launch/locomotion_control.launch.py
himdog/dog_control/msg/LocomotionCommand.msg
himdog/dog_control/msg/MotorFeedback.msg
himdog/dog_control/package.xml
himdog/dog_control/script/can.sh
himdog/dog_control/script/imu.sh
himdog/dog_control/src/hardware/dji_3508_controller.cpp
himdog/dog_control/src/hardware/dji_3508_spin_test.cpp
himdog/dog_control/src/hardware/main.cpp
himdog/dog_control/src/hardware/motor_cfg.cpp
himdog/dog_control/src/hardware/zero_calibrator.cpp
himdog/dog_control/src/hardware/zero_calibrator_debug.cpp
himdog/dog_control/src/keyboard_input_node.cpp
himdog/dog_control/src/locomotion_core_node.cpp
himdog/dog_control/src/locomotion_params.cpp
himdog/dog_control/src/locomotion_planner.cpp
himdog/dog_control/src/locomotion_runtime.cpp
himdog/dog_control/src/manual_joint_pub.cpp
himdog/dog_control/src/pose_hold_tool.cpp
himdog/dog_control/src/xbox_input_node.cpp
himdog/dog_control/test/test_locomotion_core.cpp
himdog/dog_nav/CMakeLists.txt
himdog/dog_nav/README.md
himdog/dog_nav/README_VENUE.md
himdog/dog_nav/config/contorl.yaml
himdog/dog_nav/config/task_race_2.yaml
himdog/dog_nav/config/task_race_point.yaml
himdog/dog_nav/include/dog_nav/delivery_planner.hpp
himdog/dog_nav/include/dog_nav/field_path_planner.hpp
himdog/dog_nav/include/dog_nav/pick_place_actor.hpp
himdog/dog_nav/include/dog_nav/squat_controller.hpp
himdog/dog_nav/include/dog_nav/sucker_controller.hpp
himdog/dog_nav/include/dog_nav/sucker_dual.hpp
himdog/dog_nav/msg/DogNavCommand.msg
himdog/dog_nav/package.xml
himdog/dog_nav/resource/test_serial.py
himdog/dog_nav/resource/vision/box_detector_config.json
himdog/dog_nav/resource/vision/box_detector_pt.py
himdog/dog_nav/resource/vision/box_detector_rknn.py
himdog/dog_nav/resource/vision/d435i_client.py
himdog/dog_nav/resource/vision/d435i_stream.py
himdog/dog_nav/resource/vision/model/best.pt
himdog/dog_nav/resource/vision/model/best.rknn
himdog/dog_nav/resource/vision/solver.py
himdog/dog_nav/src/dog_nav_fallback.cpp
himdog/dog_nav/src/navigation_dog.cpp
himdog/dog_nav/src/navigation_dog_2.cpp
himdog/dog_nav/src/record_points.cpp
himdog/dog_nav/src/record_points_2.cpp
himdog/dog_nav/src/test_nav_movement.cpp
himdog/dog_nav/src/test_nav_pid.cpp
himdog/dog_nav/test/test_bfs.py
himdog/dog_nav/test/test_ocr.py
himdog/dog_nav/test/test_pick_place.py
himdog/dog_nav/test/test_place_turn.py
himdog/dog_nav/test/test_sucker.cpp
himdog/dog_nav/test/test_sucker.py
himdog/dog_policy_test/CMakeLists.txt
himdog/dog_policy_test/config/policy_params.yaml
himdog/dog_policy_test/config/policy_params_12.yaml
himdog/dog_policy_test/config/policy_params_13.yaml
himdog/dog_policy_test/package.xml
himdog/dog_policy_test/policy/46_model_1900.onnx
himdog/dog_policy_test/policy/46_model_3600.onnx
himdog/dog_policy_test/policy/dog_t/model_2000.onnx
himdog/dog_policy_test/policy/dog_t/model_3700.onnx
himdog/dog_policy_test/policy/good/model_1500.onnx
himdog/dog_policy_test/policy/good/model_3500.onnx
himdog/dog_policy_test/policy/model_4500.onnx
himdog/dog_policy_test/policy/old/45_model_2500.onnx
himdog/dog_policy_test/policy/old/45_model_3400.onnx
himdog/dog_policy_test/policy/old/46_model_1500.onnx
himdog/dog_policy_test/policy/old/46_model_2500.onnx
himdog/dog_policy_test/policy/old/46_model_2600.onnx
himdog/dog_policy_test/policy/old/46_model_3200.onnx
himdog/dog_policy_test/scripts/launch_policy_on_a.py
himdog/dog_policy_test/scripts/launch_policy_on_a.sh
himdog/dog_policy_test/src/dog_policy_test_10.cpp
himdog/dog_policy_test/src/dog_policy_test_11.cpp
himdog/dog_policy_test/src/dog_policy_test_12.cpp
himdog/dog_policy_test/src/dog_policy_test_13.cpp
himdog/dog_policy_test/src/dog_policy_test_5.cpp
himdog/dog_policy_test/src/dog_policy_test_9.cpp
himdog/dog_policy_test/src/imu_dump.cpp
himdog/dog_policy_test/src/motor_feedback_dump.cpp
himdog/dog_policy_test/src/print_joint.cpp
uw-himloco/.gitattributes
uw-himloco/.gitignore
uw-himloco/LICENSE
uw-himloco/MUJOCO_LOG.TXT
uw-himloco/README.md
uw-himloco/legged_gym/__init__.py
uw-himloco/legged_gym/envs/__init__.py
uw-himloco/legged_gym/envs/a1/a1_config.py
uw-himloco/legged_gym/envs/aliengo/aliengo_config.py
uw-himloco/legged_gym/envs/base/base_config.py
uw-himloco/legged_gym/envs/base/base_task.py
uw-himloco/legged_gym/envs/base/legged_robot.md
uw-himloco/legged_gym/envs/base/legged_robot.py
uw-himloco/legged_gym/envs/base/legged_robot_config.py
uw-himloco/legged_gym/envs/dog/dog_config.py
uw-himloco/legged_gym/envs/dog_t/dog_t_config.py
uw-himloco/legged_gym/envs/go1/go1_config.py
uw-himloco/legged_gym/envs/go2/go2_config.py
uw-himloco/legged_gym/scripts/45/mang_terrain_pt.py
uw-himloco/legged_gym/scripts/45/plane_pt.py
uw-himloco/legged_gym/scripts/46/mang_terrain_pt.py
uw-himloco/legged_gym/scripts/46/plane_pt.py
uw-himloco/legged_gym/scripts/look_pt.py
uw-himloco/legged_gym/scripts/onnx/45/many_terrain_onnx.py
uw-himloco/legged_gym/scripts/onnx/45/plane_onnx.py
uw-himloco/legged_gym/scripts/onnx/45/pt_to_onnx.py
uw-himloco/legged_gym/scripts/onnx/45/torchscript_to_onnx.py
uw-himloco/legged_gym/scripts/onnx/46/many_terrain_onnx.py
uw-himloco/legged_gym/scripts/onnx/46/pt_to_onnx.py
uw-himloco/legged_gym/scripts/onnx/benchmark_onnx.py
uw-himloco/legged_gym/scripts/onnx/look_onnx.py
uw-himloco/legged_gym/scripts/play.py
uw-himloco/legged_gym/scripts/test_angle.py
uw-himloco/legged_gym/scripts/test_pt.py
uw-himloco/legged_gym/scripts/train.py
uw-himloco/legged_gym/tests/test_env.py
uw-himloco/legged_gym/utils/__init__.py
uw-himloco/legged_gym/utils/helpers.py
uw-himloco/legged_gym/utils/logger.py
uw-himloco/legged_gym/utils/math.py
uw-himloco/legged_gym/utils/task_registry.py
uw-himloco/legged_gym/utils/terrain.py
uw-himloco/mujoco/MUJOCO_LOG.TXT
uw-himloco/mujoco/dog/config/dog.yaml
uw-himloco/mujoco/dog/config/dog_switch.yaml
uw-himloco/mujoco/dog/look_xml.py
uw-himloco/mujoco/dog/plane_onnx_45.py
uw-himloco/mujoco/dog/plane_onnx_46_h.py
uw-himloco/mujoco/dog/play_onnx_46.py
uw-himloco/mujoco/dog/play_xbox_onnx_46_switch.py
uw-himloco/mujoco/dog_t/config/dog_t.yaml
uw-himloco/mujoco/dog_t/play_onnx_46.py
uw-himloco/mujoco/go1/MUJOCO_LOG.TXT
uw-himloco/mujoco/go1/config/go1.yaml
uw-himloco/mujoco/go1/look_xml.py
uw-himloco/mujoco/go1/play_onnx.py
uw-himloco/mujoco/go2/config/go2.yaml
uw-himloco/mujoco/scripts/urdf_to_xml.py
uw-himloco/resources/robots/a1/a1_license.txt
uw-himloco/resources/robots/a1/urdf/a1.urdf
uw-himloco/resources/robots/a1/urdf/a1.urdf.origin
uw-himloco/resources/robots/aliengo/urdf/aliengo.urdf
uw-himloco/resources/robots/anymal_b/ANYmal_b_license.txt
uw-himloco/resources/robots/anymal_b/urdf/anymal_b.urdf
uw-himloco/resources/robots/anymal_c/ANYmal_c_license.txt
uw-himloco/resources/robots/anymal_c/urdf/anymal_c.urdf
uw-himloco/resources/robots/cassie/cassie_license.txt
uw-himloco/resources/robots/cassie/urdf/cassie.urdf
uw-himloco/resources/robots/dog/CMakeLists.txt
uw-himloco/resources/robots/dog/config/joint_names_2026【哮天】2.0（仿真模型）(UR3).yaml
uw-himloco/resources/robots/dog/launch/display.launch
uw-himloco/resources/robots/dog/launch/gazebo.launch
uw-himloco/resources/robots/dog/package.xml
uw-himloco/resources/robots/dog/urdf/dog.urdf
uw-himloco/resources/robots/dog/urdf/dog_1.urdf
uw-himloco/resources/robots/dog/urdf/old/2026【哮天】2.0（仿真模型）(UR3).csv
uw-himloco/resources/robots/dog/urdf/old/dog+odin.urdf
uw-himloco/resources/robots/dog/urdf/old/dog.urdf.bak
uw-himloco/resources/robots/dog/urdf/old/dog1.urdf
uw-himloco/resources/robots/dog/urdf/old/dog_15-30.urdf
uw-himloco/resources/robots/dog/urdf/old/dog_old.urdf
uw-himloco/resources/robots/dog/urdf/old/dog_old_1.urdf
uw-himloco/resources/robots/dog/urdf/old/dog_old_46.urdf
uw-himloco/resources/robots/dog/xml/dog.xml
uw-himloco/resources/robots/dog/xml/dog_1.xml
uw-himloco/resources/robots/dog/xml/dog_terrain.xml
uw-himloco/resources/robots/dog/xml/old/dog.xml
uw-himloco/resources/robots/dog_t/dog_t/urdf/dog_t.urdf
uw-himloco/resources/robots/dog_t/dog_t/xml/dog_t.xml
uw-himloco/resources/robots/dog_t/dog_t/xml/dog_t_terrain.xml
uw-himloco/resources/robots/go1/urdf/go1.urdf
uw-himloco/resources/robots/go1/xml/go1.xml
uw-himloco/resources/robots/go1/xml/scence.xml
uw-himloco/resources/robots/go1/xml/scene_terrain.xml
uw-himloco/resources/robots/go2/go2/urdf/go2.urdf
uw-himloco/resources/robots/go2_description/go2.xml
uw-himloco/resources/robots/go2_description/scene.xml
uw-himloco/resources/robots/go2_description/scene_terrain.xml
uw-himloco/setup.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `himdog/dog_nav/resource/vision` | 2 | 601 KB | [`himdog/dog_nav/resource/vision/_OMITTED.md`](./himdog/dog_nav/resource/vision/_OMITTED.md) |
| `himdog/dog_nav/resource/vision/audio` | 9 | 2.7 MB | [`himdog/dog_nav/resource/vision/audio/_OMITTED.md`](./himdog/dog_nav/resource/vision/audio/_OMITTED.md) |
| `uw-himloco/resources/robots/a1/meshes` | 6 | 8.7 MB | [`uw-himloco/resources/robots/a1/meshes/_OMITTED.md`](./uw-himloco/resources/robots/a1/meshes/_OMITTED.md) |
| `uw-himloco/resources/robots/aliengo/meshes` | 6 | 6.0 MB | [`uw-himloco/resources/robots/aliengo/meshes/_OMITTED.md`](./uw-himloco/resources/robots/aliengo/meshes/_OMITTED.md) |
| `uw-himloco/resources/robots/anymal_b/meshes` | 10 | 21.0 MB | [`uw-himloco/resources/robots/anymal_b/meshes/_OMITTED.md`](./uw-himloco/resources/robots/anymal_b/meshes/_OMITTED.md) |
| `uw-himloco/resources/robots/anymal_c/meshes` | 36 | 7.9 MB | [`uw-himloco/resources/robots/anymal_c/meshes/_OMITTED.md`](./uw-himloco/resources/robots/anymal_c/meshes/_OMITTED.md) |
| `uw-himloco/resources/robots/cassie/meshes` | 21 | 3.3 MB | [`uw-himloco/resources/robots/cassie/meshes/_OMITTED.md`](./uw-himloco/resources/robots/cassie/meshes/_OMITTED.md) |
| `uw-himloco/resources/robots/dog` | 1 | 4.5 MB | [`uw-himloco/resources/robots/dog/_OMITTED.md`](./uw-himloco/resources/robots/dog/_OMITTED.md) |
| `uw-himloco/resources/robots/dog/meshes` | 18 | 691 KB | [`uw-himloco/resources/robots/dog/meshes/_OMITTED.md`](./uw-himloco/resources/robots/dog/meshes/_OMITTED.md) |
| `uw-himloco/resources/robots/dog_t/dog_t/meshes` | 21 | 37.5 MB | [`uw-himloco/resources/robots/dog_t/dog_t/meshes/_OMITTED.md`](./uw-himloco/resources/robots/dog_t/dog_t/meshes/_OMITTED.md) |
| `uw-himloco/resources/robots/go1/meshes` | 5 | 9.8 MB | [`uw-himloco/resources/robots/go1/meshes/_OMITTED.md`](./uw-himloco/resources/robots/go1/meshes/_OMITTED.md) |
| `uw-himloco/resources/robots/go2/go2/dae` | 7 | 24.7 MB | [`uw-himloco/resources/robots/go2/go2/dae/_OMITTED.md`](./uw-himloco/resources/robots/go2/go2/dae/_OMITTED.md) |
| `uw-himloco/resources/robots/go2_description` | 3 | 629 KB | [`uw-himloco/resources/robots/go2_description/_OMITTED.md`](./uw-himloco/resources/robots/go2_description/_OMITTED.md) |
| `uw-himloco/resources/robots/go2_description/assets` | 16 | 27.1 MB | [`uw-himloco/resources/robots/go2_description/assets/_OMITTED.md`](./uw-himloco/resources/robots/go2_description/assets/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
