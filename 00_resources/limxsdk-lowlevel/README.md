# limxsdk-lowlevel — 参考资源

> **来源**：`00_open/limxsdk-lowlevel/`　｜　**类型**：参考项目
> **关联机型**：limx_tron1_pf（逐际动力 TRON1-PF）、limx_tron1_sf（逐际动力 TRON1-SF）、limx_tron1_wf（逐际动力 TRON1-WF）
> **定位**：limxdynamics 官方低层 SDK（limxsdk：硬件接口/消息定义）
> **收录**：91 个文件 / 403 KB（其中推理策略/模型文件 0 个）
> **已省略**：12 个文件 / 76.6 MB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **关节与接口契约**（2 个）：关节与接口契约：关节序、limits、PD、action_scale、default pose、观测/动作维度
- **部署与推理**（68 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **文档与其它**（21 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （5 个文件）
examples/  （7 个文件）
    (直接文件)/
    common/
include/  （66 个文件）
    limxsdk/
python3/  （13 个文件）
    (直接文件)/
    examples/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.h` | 68 |
| `.py` | 11 |
| `.cpp` | 4 |
| `.txt` | 2 |
| `(无扩展名)` | 2 |
| `.md` | 2 |
| `.xml` | 1 |
| `.yaml` | 1 |

## 文件索引（项目内相对路径）

```text
CMakeLists.txt
LICENSE
README.md
README_cn.md
examples/CMakeLists.txt
examples/common/util.cpp
examples/common/util.h
examples/pf_controller_base.cpp
examples/pf_controller_base.h
examples/pf_groupJoints_move.cpp
examples/pf_joint_move.cpp
include/limxsdk/ability/ability_manager.h
include/limxsdk/ability/base_ability.h
include/limxsdk/ability/plugin_loader.h
include/limxsdk/ability/plugin_registry.h
include/limxsdk/ability/rate.h
include/limxsdk/ability/robot_data.h
include/limxsdk/ability/yaml_config_parser.h
include/limxsdk/apibase.h
include/limxsdk/centaur.h
include/limxsdk/codec/codec.h
include/limxsdk/datatypes.h
include/limxsdk/humanoid.h
include/limxsdk/macros.h
include/limxsdk/msg/control_msgs/GripperCommand.h
include/limxsdk/msg/controller_manager_msgs/ControllerState.h
include/limxsdk/msg/controller_manager_msgs/HardwareInterfaceResources.h
include/limxsdk/msg/controller_msgs/IMUData.h
include/limxsdk/msg/controller_msgs/JointCmd.h
include/limxsdk/msg/controller_msgs/JointCmdLimx.h
include/limxsdk/msg/controller_msgs/JointState.h
include/limxsdk/msg/controller_msgs/RCASCmdStamped.h
include/limxsdk/msg/controller_msgs/RCASCmdStampedWL.h
include/limxsdk/msg/controller_msgs/RCCmdStamped.h
include/limxsdk/msg/diagnostic_msgs/DiagnosticValue.h
include/limxsdk/msg/geometry_msgs/Point.h
include/limxsdk/msg/geometry_msgs/Pose.h
include/limxsdk/msg/geometry_msgs/PoseWithCovariance.h
include/limxsdk/msg/geometry_msgs/Quaternion.h
include/limxsdk/msg/geometry_msgs/Twist.h
include/limxsdk/msg/geometry_msgs/TwistWithCovariance.h
include/limxsdk/msg/geometry_msgs/Vector3.h
include/limxsdk/msg/hand_msgs/HandCmd.h
include/limxsdk/msg/hand_msgs/HandMsg.h
include/limxsdk/msg/hand_msgs/HandState.h
include/limxsdk/msg/hand_msgs/TactileCmd.h
include/limxsdk/msg/hand_msgs/TactileHandCmd.h
include/limxsdk/msg/hand_msgs/TactileHandState.h
include/limxsdk/msg/hand_msgs/TactileState.h
include/limxsdk/msg/ipcamera_msgs/CameraCtrl.h
include/limxsdk/msg/nav_msgs/MapMetaData.h
include/limxsdk/msg/nav_msgs/OccupancyGrid.h
include/limxsdk/msg/nav_msgs/Odometry.h
include/limxsdk/msg/perception_msgs/HeightEstimateResult.h
include/limxsdk/msg/sensor_msgs/Joy.h
include/limxsdk/msg/sensor_msgs/JoyH16.h
include/limxsdk/msg/std_msgs/Bool.h
include/limxsdk/msg/std_msgs/Byte.h
include/limxsdk/msg/std_msgs/Empty.h
include/limxsdk/msg/std_msgs/Float32MultiArray.h
include/limxsdk/msg/std_msgs/Float64Array.h
include/limxsdk/msg/std_msgs/Float64MultiArray.h
include/limxsdk/msg/std_msgs/Header.h
include/limxsdk/msg/std_msgs/Int32Array.h
include/limxsdk/msg/std_msgs/Int8.h
include/limxsdk/msg/std_msgs/Int8Array.h
include/limxsdk/msg/std_msgs/MultiArrayDimension.h
include/limxsdk/msg/std_msgs/MultiArrayLayout.h
include/limxsdk/msg/std_msgs/String.h
include/limxsdk/msg/std_msgs/UInt16Array.h
include/limxsdk/msg/task_state_msgs/TaskState.h
include/limxsdk/msg/teleop_msgs/VRState.h
include/limxsdk/msg/type_registry.h
include/limxsdk/pointfoot.h
include/limxsdk/topic_channel.h
include/limxsdk/tron2.h
include/limxsdk/wheellegged.h
package.xml
python3/.gitignore
python3/examples/ability/abilities.yaml
python3/examples/ability/dummy1.py
python3/examples/ability/dummy2.py
python3/examples/api/example_centaur.py
python3/examples/api/example_humanoid.py
python3/examples/api/example_tron1.py
python3/examples/api/example_tron2.py
python3/examples/api/example_tron2_brainco_hand.py
python3/examples/api/example_tron2_chassis_lifter.py
python3/examples/api/example_tron2_generic_sub_pub_topic.py
python3/examples/api/example_tron2_gripper.py
python3/examples/api/example_tron2_machine_data.py
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `doc` | 4 | 30.9 MB | [`doc/_OMITTED.md`](./doc/_OMITTED.md) |
| `lib/aarch64` | 1 | 8.9 MB | [`lib/aarch64/_OMITTED.md`](./lib/aarch64/_OMITTED.md) |
| `lib/amd64` | 1 | 9.6 MB | [`lib/amd64/_OMITTED.md`](./lib/amd64/_OMITTED.md) |
| `lib/arm32` | 1 | 9.2 MB | [`lib/arm32/_OMITTED.md`](./lib/arm32/_OMITTED.md) |
| `lib/win` | 2 | 5.5 MB | [`lib/win/_OMITTED.md`](./lib/win/_OMITTED.md) |
| `python3/aarch64` | 1 | 5.2 MB | [`python3/aarch64/_OMITTED.md`](./python3/aarch64/_OMITTED.md) |
| `python3/amd64` | 1 | 5.4 MB | [`python3/amd64/_OMITTED.md`](./python3/amd64/_OMITTED.md) |
| `python3/win` | 1 | 1.9 MB | [`python3/win/_OMITTED.md`](./python3/win/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。
