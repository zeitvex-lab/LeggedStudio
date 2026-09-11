# 26Raicom — 参考资源

> **来源**：`00_open/26Raicom/`　｜　**类型**：真机竞赛任务编排参考（多模态巡检）
> **关联机型**：unitree_go2（宇树 Go2 四足）
> **定位**：2026 睿抗（RAICOM）多模态巡检赛道全国一等奖代码：8 阶段全流程——PID 黑线循迹 + 白线触发前跳、三路 TOF 迷宫五阶段状态机、IMU 俯仰闭环上/下台阶、D1 七自由度机械臂 DLS 逆运动学抓取（D435i 红圆 + 深度）、YOLO+ORB+模板兜底标志识别；含赛规 PDF、场地立体图与硬件健壮性方案（看门狗 / 热插拔 / USB 带宽）
> **收录**：292 个文件 / 12.7 MB（其中推理策略/模型文件 2 个）
> **已省略**：12 个文件 / 527 KB（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **关节与接口契约**（1 个）：关节与接口契约：关节序、limits、PD、action_scale、default pose、观测/动作维度
- **部署与推理**（245 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **地形与场景**（1 个）：地形与场景资产：高度场、台阶、崎岖地形与场景构建
- **动作与运动数据**（4 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **评测与测试**（1 个）：评测与测试：指标脚本、基准与回归用例
- **文档与其它**（40 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （5 个文件）
D1_sdk/  （14 个文件）
    (直接文件)/
    src/
Recognition/  （5 个文件）
    (直接文件)/
    models/
final_code/  （34 个文件）
    (直接文件)/
    机身姿态/
    测距模块/
    视觉抓取/
unitree_sdk2_python/  （233 个文件）
    (直接文件)/
    example/
    unitree_sdk2py/
    unitree_sdk2py.egg-info/
标识/  （1 个文件）
    (直接文件)/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.py` | 248 |
| `.md` | 9 |
| `.cpp` | 9 |
| `.txt` | 7 |
| `(无扩展名)` | 6 |
| `.hpp` | 4 |
| `.sh` | 3 |
| `.pdf` | 2 |
| `.toml` | 1 |
| `.docx` | 1 |
| `.onnx` | 1 |
| `.pt` | 1 |

## 文件索引（项目内相对路径）

```text
26年赛题任务要求.txt
D1_sdk/CMakeLists.txt
D1_sdk/src/arm_zero_control.cpp
D1_sdk/src/get_arm_joint_angle.cpp
D1_sdk/src/joint_angle_control.cpp
D1_sdk/src/joint_enable_control.cpp
D1_sdk/src/msg/ArmString_.cpp
D1_sdk/src/msg/ArmString_.hpp
D1_sdk/src/msg/PubServoInfo_.cpp
D1_sdk/src/msg/PubServoInfo_.hpp
D1_sdk/src/msg/SetServoAngle_.cpp
D1_sdk/src/msg/SetServoAngle_.hpp
D1_sdk/src/msg/SetServoDumping_.cpp
D1_sdk/src/msg/SetServoDumping_.hpp
D1_sdk/src/multiple_joint_angle_control.cpp
README_upstream.md
Recognition/CLAUDE.md
Recognition/models/sign_classifier/best.onnx
Recognition/models/sign_classifier/best.pt
Recognition/ocr_recognizer.py
Recognition/sign_recognizer.py
final_code/0.sh
final_code/1.py
final_code/2.py
final_code/3.sh
final_code/Final_code.py
final_code/README.md
final_code/camera_preview.py
final_code/set_camera_exposure.sh
final_code/usb_blue_detect.py
final_code/机身姿态/README.md
final_code/机身姿态/phase3_stairs.py
final_code/机身姿态/pitch_monitor.py
final_code/机身姿态/read_attitude.py
final_code/测距模块/README.md
final_code/测距模块/TOF_read.py
final_code/测距模块/TOF_test.py
final_code/测距模块/经典步态前进.py
final_code/测距模块/迷宫_tof.py
final_code/视觉抓取/README.md
final_code/视觉抓取/arm_ik_control.py
final_code/视觉抓取/arm_ik_control1.py
final_code/视觉抓取/arm_sr-control.py
final_code/视觉抓取/color_object_detector.py
final_code/视觉抓取/d1_forward_kinematics.py
final_code/视觉抓取/d1_ik_solver.py
final_code/视觉抓取/dds_lib_fix.py
final_code/视觉抓取/depth_camera.py
final_code/视觉抓取/pick_and_place.py
final_code/视觉抓取/pick_and_place1.py
final_code/视觉抓取/中转放置.py
final_code/视觉抓取/临时.txt
final_code/视觉抓取/夹着走.py
final_code/视觉抓取/左右放置.py
final_code/迷宫.py
unitree_sdk2_python/.gitignore
unitree_sdk2_python/LICENSE
unitree_sdk2_python/README zh.md
unitree_sdk2_python/README.md
unitree_sdk2_python/example/go2/front_camera/camera_opencv.py
unitree_sdk2_python/example/go2/front_camera/capture_image.py
unitree_sdk2_python/example/go2/front_camera/depth_line_follow.py
unitree_sdk2_python/example/go2/front_camera/line_follow.py
unitree_sdk2_python/example/go2/front_camera/realsense_viewer.py
unitree_sdk2_python/example/go2/high_level/go2_sport_client.py
unitree_sdk2_python/example/go2/high_level/go2_utlidar_switch.py
unitree_sdk2_python/example/go2/low_level/go2_stand_example.py
unitree_sdk2_python/example/go2/low_level/unitree_legged_const.py
unitree_sdk2_python/example/go2w/high_level/go2w_sport_client.py
unitree_sdk2_python/example/go2w/low_level/go2w_stand_example.py
unitree_sdk2_python/example/go2w/low_level/unitree_legged_const.py
unitree_sdk2_python/example/helloworld/publisher.py
unitree_sdk2_python/example/helloworld/subscriber.py
unitree_sdk2_python/example/helloworld/user_data.py
unitree_sdk2_python/example/motionSwitcher/motion_switcher_example.py
unitree_sdk2_python/example/obstacles_avoid/obstacles_avoid_move.py
unitree_sdk2_python/example/obstacles_avoid/obstacles_avoid_switch.py
unitree_sdk2_python/example/vui_client/vui_client_example.py
unitree_sdk2_python/example/wireless_controller/wireless_controller.py
unitree_sdk2_python/pyproject.toml
unitree_sdk2_python/setup.py
unitree_sdk2_python/unitree_sdk2py.egg-info/PKG-INFO
unitree_sdk2_python/unitree_sdk2py.egg-info/SOURCES.txt
unitree_sdk2_python/unitree_sdk2py.egg-info/dependency_links.txt
unitree_sdk2_python/unitree_sdk2py.egg-info/requires.txt
unitree_sdk2_python/unitree_sdk2py.egg-info/top_level.txt
unitree_sdk2_python/unitree_sdk2py/__init__.py
unitree_sdk2_python/unitree_sdk2py/a2/__init__.py
unitree_sdk2_python/unitree_sdk2py/a2/audio/__init__.py
unitree_sdk2_python/unitree_sdk2py/a2/audio/audio_api.py
unitree_sdk2_python/unitree_sdk2py/a2/audio/audio_client.py
unitree_sdk2_python/unitree_sdk2py/a2/sport/__init__.py
unitree_sdk2_python/unitree_sdk2py/a2/sport/sport_api.py
unitree_sdk2_python/unitree_sdk2py/a2/sport/sport_client.py
unitree_sdk2_python/unitree_sdk2py/as2/__init__.py
unitree_sdk2_python/unitree_sdk2py/as2/sport/sport_api.py
unitree_sdk2_python/unitree_sdk2py/as2/sport/sport_client.py
unitree_sdk2_python/unitree_sdk2py/b2/__init__.py
unitree_sdk2_python/unitree_sdk2py/b2/back_video/__init__.py
unitree_sdk2_python/unitree_sdk2py/b2/back_video/back_video_api.py
unitree_sdk2_python/unitree_sdk2py/b2/back_video/back_video_client.py
unitree_sdk2_python/unitree_sdk2py/b2/front_video/__init__.py
unitree_sdk2_python/unitree_sdk2py/b2/front_video/front_video_api.py
unitree_sdk2_python/unitree_sdk2py/b2/front_video/front_video_client.py
unitree_sdk2_python/unitree_sdk2py/b2/robot_state/__init__.py
unitree_sdk2_python/unitree_sdk2py/b2/robot_state/robot_state_api.py
unitree_sdk2_python/unitree_sdk2py/b2/robot_state/robot_state_client.py
unitree_sdk2_python/unitree_sdk2py/b2/sport/__init__.py
unitree_sdk2_python/unitree_sdk2py/b2/sport/sport_api.py
unitree_sdk2_python/unitree_sdk2py/b2/sport/sport_client.py
unitree_sdk2_python/unitree_sdk2py/b2/vui/__init__.py
unitree_sdk2_python/unitree_sdk2py/b2/vui/vui_api.py
unitree_sdk2_python/unitree_sdk2py/b2/vui/vui_client.py
unitree_sdk2_python/unitree_sdk2py/comm/__init__.py
unitree_sdk2_python/unitree_sdk2py/comm/motion_switcher/__init__.py
unitree_sdk2_python/unitree_sdk2py/comm/motion_switcher/motion_switcher_api.py
unitree_sdk2_python/unitree_sdk2py/comm/motion_switcher/motion_switcher_client.py
unitree_sdk2_python/unitree_sdk2py/core/__init__.py
unitree_sdk2_python/unitree_sdk2py/core/channel.py
unitree_sdk2_python/unitree_sdk2py/core/channel_config.py
unitree_sdk2_python/unitree_sdk2py/core/channel_name.py
unitree_sdk2_python/unitree_sdk2py/g1/__init__.py
unitree_sdk2_python/unitree_sdk2py/g1/arm/__init__.py
unitree_sdk2_python/unitree_sdk2py/g1/arm/g1_arm_action_api.py
unitree_sdk2_python/unitree_sdk2py/g1/arm/g1_arm_action_client.py
unitree_sdk2_python/unitree_sdk2py/g1/audio/__init__.py
unitree_sdk2_python/unitree_sdk2py/g1/audio/g1_audio_api.py
unitree_sdk2_python/unitree_sdk2py/g1/audio/g1_audio_client.py
unitree_sdk2_python/unitree_sdk2py/g1/loco/__init__.py
unitree_sdk2_python/unitree_sdk2py/g1/loco/g1_loco_api.py
unitree_sdk2_python/unitree_sdk2py/g1/loco/g1_loco_client.py
unitree_sdk2_python/unitree_sdk2py/go2/__init__.py
unitree_sdk2_python/unitree_sdk2py/go2/obstacles_avoid/__init__.py
unitree_sdk2_python/unitree_sdk2py/go2/obstacles_avoid/obstacles_avoid_api.py
unitree_sdk2_python/unitree_sdk2py/go2/obstacles_avoid/obstacles_avoid_client.py
unitree_sdk2_python/unitree_sdk2py/go2/robot_state/__init__.py
unitree_sdk2_python/unitree_sdk2py/go2/robot_state/robot_state_api.py
unitree_sdk2_python/unitree_sdk2py/go2/robot_state/robot_state_client.py
unitree_sdk2_python/unitree_sdk2py/go2/sport/__init__.py
unitree_sdk2_python/unitree_sdk2py/go2/sport/sport_api.py
unitree_sdk2_python/unitree_sdk2py/go2/sport/sport_client.py
unitree_sdk2_python/unitree_sdk2py/go2/video/__init__.py
unitree_sdk2_python/unitree_sdk2py/go2/video/video_api.py
unitree_sdk2_python/unitree_sdk2py/go2/video/video_client.py
unitree_sdk2_python/unitree_sdk2py/go2/vui/__init__.py
unitree_sdk2_python/unitree_sdk2py/go2/vui/vui_api.py
unitree_sdk2_python/unitree_sdk2py/go2/vui/vui_client.py
unitree_sdk2_python/unitree_sdk2py/h1/__init__.py
unitree_sdk2_python/unitree_sdk2py/h1/loco/__init__.py
unitree_sdk2_python/unitree_sdk2py/h1/loco/h1_loco_api.py
unitree_sdk2_python/unitree_sdk2py/h1/loco/h1_loco_client.py
unitree_sdk2_python/unitree_sdk2py/h2/__init__.py
unitree_sdk2_python/unitree_sdk2py/h2/loco/__init__.py
unitree_sdk2_python/unitree_sdk2py/h2/loco/h2_loco_api.py
unitree_sdk2_python/unitree_sdk2py/h2/loco/h2_loco_client.py
unitree_sdk2_python/unitree_sdk2py/idl/__init__.py
unitree_sdk2_python/unitree_sdk2py/idl/builtin_interfaces/__init__.py
unitree_sdk2_python/unitree_sdk2py/idl/builtin_interfaces/msg/__init__.py
unitree_sdk2_python/unitree_sdk2py/idl/builtin_interfaces/msg/dds_/_Time_.py
unitree_sdk2_python/unitree_sdk2py/idl/builtin_interfaces/msg/dds_/__init__.py
unitree_sdk2_python/unitree_sdk2py/idl/default.py
unitree_sdk2_python/unitree_sdk2py/idl/geometry_msgs/__init__.py
unitree_sdk2_python/unitree_sdk2py/idl/geometry_msgs/msg/__init__.py
unitree_sdk2_python/unitree_sdk2py/idl/geometry_msgs/msg/dds_/_Point32_.py
unitree_sdk2_python/unitree_sdk2py/idl/geometry_msgs/msg/dds_/_PointStamped_.py
unitree_sdk2_python/unitree_sdk2py/idl/geometry_msgs/msg/dds_/_Point_.py
unitree_sdk2_python/unitree_sdk2py/idl/geometry_msgs/msg/dds_/_Pose2D_.py
unitree_sdk2_python/unitree_sdk2py/idl/geometry_msgs/msg/dds_/_PoseStamped_.py
unitree_sdk2_python/unitree_sdk2py/idl/geometry_msgs/msg/dds_/_PoseWithCovarianceStamped_.py
unitree_sdk2_python/unitree_sdk2py/idl/geometry_msgs/msg/dds_/_PoseWithCovariance_.py
unitree_sdk2_python/unitree_sdk2py/idl/geometry_msgs/msg/dds_/_Pose_.py
unitree_sdk2_python/unitree_sdk2py/idl/geometry_msgs/msg/dds_/_QuaternionStamped_.py
unitree_sdk2_python/unitree_sdk2py/idl/geometry_msgs/msg/dds_/_Quaternion_.py
unitree_sdk2_python/unitree_sdk2py/idl/geometry_msgs/msg/dds_/_TwistStamped_.py
unitree_sdk2_python/unitree_sdk2py/idl/geometry_msgs/msg/dds_/_TwistWithCovarianceStamped_.py
unitree_sdk2_python/unitree_sdk2py/idl/geometry_msgs/msg/dds_/_TwistWithCovariance_.py
unitree_sdk2_python/unitree_sdk2py/idl/geometry_msgs/msg/dds_/_Twist_.py
unitree_sdk2_python/unitree_sdk2py/idl/geometry_msgs/msg/dds_/_Vector3_.py
unitree_sdk2_python/unitree_sdk2py/idl/geometry_msgs/msg/dds_/__init__.py
unitree_sdk2_python/unitree_sdk2py/idl/nav_msgs/__init__.py
unitree_sdk2_python/unitree_sdk2py/idl/nav_msgs/msg/__init__.py
unitree_sdk2_python/unitree_sdk2py/idl/nav_msgs/msg/dds_/_MapMetaData_.py
unitree_sdk2_python/unitree_sdk2py/idl/nav_msgs/msg/dds_/_OccupancyGrid_.py
unitree_sdk2_python/unitree_sdk2py/idl/nav_msgs/msg/dds_/_Odometry_.py
unitree_sdk2_python/unitree_sdk2py/idl/nav_msgs/msg/dds_/__init__.py
unitree_sdk2_python/unitree_sdk2py/idl/sensor_msgs/__init__.py
unitree_sdk2_python/unitree_sdk2py/idl/sensor_msgs/msg/__init__.py
unitree_sdk2_python/unitree_sdk2py/idl/sensor_msgs/msg/dds_/PointField_Constants/_PointField_.py
unitree_sdk2_python/unitree_sdk2py/idl/sensor_msgs/msg/dds_/PointField_Constants/__init__.py
unitree_sdk2_python/unitree_sdk2py/idl/sensor_msgs/msg/dds_/_PointCloud2_.py
unitree_sdk2_python/unitree_sdk2py/idl/sensor_msgs/msg/dds_/_PointField_.py
unitree_sdk2_python/unitree_sdk2py/idl/sensor_msgs/msg/dds_/__init__.py
unitree_sdk2_python/unitree_sdk2py/idl/std_msgs/__init__.py
unitree_sdk2_python/unitree_sdk2py/idl/std_msgs/msg/__init__.py
unitree_sdk2_python/unitree_sdk2py/idl/std_msgs/msg/dds_/_Header_.py
unitree_sdk2_python/unitree_sdk2py/idl/std_msgs/msg/dds_/_String_.py
unitree_sdk2_python/unitree_sdk2py/idl/std_msgs/msg/dds_/__init__.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_api/__init__.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_api/msg/__init__.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_api/msg/dds_/_RequestHeader_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_api/msg/dds_/_RequestIdentity_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_api/msg/dds_/_RequestLease_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_api/msg/dds_/_RequestPolicy_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_api/msg/dds_/_Request_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_api/msg/dds_/_ResponseHeader_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_api/msg/dds_/_ResponseStatus_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_api/msg/dds_/_Response_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_api/msg/dds_/__init__.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_go/__init__.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_go/msg/__init__.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_go/msg/dds_/_AudioData_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_go/msg/dds_/_BmsCmd_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_go/msg/dds_/_BmsState_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_go/msg/dds_/_Error_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_go/msg/dds_/_Go2FrontVideoData_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_go/msg/dds_/_HeightMap_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_go/msg/dds_/_IMUState_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_go/msg/dds_/_InterfaceConfig_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_go/msg/dds_/_LidarState_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_go/msg/dds_/_LowCmd_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_go/msg/dds_/_LowState_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_go/msg/dds_/_MotorCmd_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_go/msg/dds_/_MotorCmds_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_go/msg/dds_/_MotorState_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_go/msg/dds_/_MotorStates_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_go/msg/dds_/_PathPoint_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_go/msg/dds_/_Req_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_go/msg/dds_/_Res_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_go/msg/dds_/_SportModeState_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_go/msg/dds_/_TimeSpec_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_go/msg/dds_/_UwbState_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_go/msg/dds_/_UwbSwitch_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_go/msg/dds_/_WirelessController_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_go/msg/dds_/__init__.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_hg/.idlpy_manifest
unitree_sdk2_python/unitree_sdk2py/idl/unitree_hg/__init__.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_hg/msg/.idlpy_manifest
unitree_sdk2_python/unitree_sdk2py/idl/unitree_hg/msg/__init__.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_hg/msg/dds_/.idlpy_manifest
unitree_sdk2_python/unitree_sdk2py/idl/unitree_hg/msg/dds_/_BmsCmd_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_hg/msg/dds_/_BmsState_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_hg/msg/dds_/_HandCmd_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_hg/msg/dds_/_HandState_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_hg/msg/dds_/_IMUState_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_hg/msg/dds_/_LowCmd_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_hg/msg/dds_/_LowState_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_hg/msg/dds_/_MainBoardState_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_hg/msg/dds_/_MotorCmd_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_hg/msg/dds_/_MotorState_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_hg/msg/dds_/_PressSensorState_.py
unitree_sdk2_python/unitree_sdk2py/idl/unitree_hg/msg/dds_/__init__.py
unitree_sdk2_python/unitree_sdk2py/rpc/__init__.py
unitree_sdk2_python/unitree_sdk2py/rpc/client.py
unitree_sdk2_python/unitree_sdk2py/rpc/client_base.py
unitree_sdk2_python/unitree_sdk2py/rpc/client_stub.py
unitree_sdk2_python/unitree_sdk2py/rpc/internal.py
unitree_sdk2_python/unitree_sdk2py/rpc/lease_client.py
unitree_sdk2_python/unitree_sdk2py/rpc/lease_server.py
unitree_sdk2_python/unitree_sdk2py/rpc/request_future.py
unitree_sdk2_python/unitree_sdk2py/rpc/server.py
unitree_sdk2_python/unitree_sdk2py/rpc/server_base.py
unitree_sdk2_python/unitree_sdk2py/rpc/server_stub.py
unitree_sdk2_python/unitree_sdk2py/test/client/obstacles_avoid_client_example.py
unitree_sdk2_python/unitree_sdk2py/test/client/robot_service_client_example.py
unitree_sdk2_python/unitree_sdk2py/test/client/sport_client_example.py
unitree_sdk2_python/unitree_sdk2py/test/client/video_client_example.py
unitree_sdk2_python/unitree_sdk2py/test/client/vui_client_example.py
unitree_sdk2_python/unitree_sdk2py/test/crc/test_crc.py
unitree_sdk2_python/unitree_sdk2py/test/helloworld/helloworld.py
unitree_sdk2_python/unitree_sdk2py/test/helloworld/publisher.py
unitree_sdk2_python/unitree_sdk2py/test/helloworld/subscriber.py
unitree_sdk2_python/unitree_sdk2py/test/lowlevel/lowlevel_control.py
unitree_sdk2_python/unitree_sdk2py/test/lowlevel/read_lowstate.py
unitree_sdk2_python/unitree_sdk2py/test/lowlevel/sub_lowstate.py
unitree_sdk2_python/unitree_sdk2py/test/lowlevel/unitree_go2_const.py
unitree_sdk2_python/unitree_sdk2py/test/rpc/test_api.py
unitree_sdk2_python/unitree_sdk2py/test/rpc/test_client_example.py
unitree_sdk2_python/unitree_sdk2py/test/rpc/test_server_example.py
unitree_sdk2_python/unitree_sdk2py/utils/__init__.py
unitree_sdk2_python/unitree_sdk2py/utils/bqueue.py
unitree_sdk2_python/unitree_sdk2py/utils/clib_lookup.py
unitree_sdk2_python/unitree_sdk2py/utils/crc.py
unitree_sdk2_python/unitree_sdk2py/utils/future.py
unitree_sdk2_python/unitree_sdk2py/utils/hz_sample.py
unitree_sdk2_python/unitree_sdk2py/utils/joystick.py
unitree_sdk2_python/unitree_sdk2py/utils/singleton.py
unitree_sdk2_python/unitree_sdk2py/utils/thread.py
unitree_sdk2_python/unitree_sdk2py/utils/timerfd.py
【赛规】CAIR强体赛道-足式机器人赛项-多模态巡检.pdf
场地立体图.pdf
标识/场地识别标志.docx
注意事项（必看）.md
```

## 省略登记索引

| 目录 | 省略文件数 | 体积 | 登记文件 |
|---|---:|---:|---|
| `Recognition` | 5 | 252 KB | [`Recognition/_OMITTED.md`](./Recognition/_OMITTED.md) |
| `unitree_sdk2_python/unitree_sdk2py/utils/lib` | 2 | 23 KB | [`unitree_sdk2_python/unitree_sdk2py/utils/lib/_OMITTED.md`](./unitree_sdk2_python/unitree_sdk2py/utils/lib/_OMITTED.md) |
| `标识` | 5 | 252 KB | [`标识/_OMITTED.md`](./标识/_OMITTED.md) |

> 以上文件未拷贝；需要时按登记的源路径回到 `00_open/` 取用。

## 导入边界与关键数值（人工补充，重新同步时需重做）

- **来历**：GitHub `mod6-fds/26Raicom` → `GO2_EDU.zip`（11.5 MB，664 条目）解包后收录；**解包后无嵌套压缩包**。
- **许可**：上游**无 LICENSE 文件**；`README_upstream.md` 与 `注意事项（必看）.md` 均声明「全部开源，仅供学习交流，**严禁销售或商业用途**」→ 仅作**内部参考**，不得商用；对外引用请先联系作者。
- **收录口径与省略**：`README_upstream.md` 为上游 README 原件（库生成的索引占用 `README.md`，故改名保留）；`best.onnx`(5.9 MB) + `best.pt`(3.1 MB) 按库约定作为**策略/模型文件**保留（5 类标志分类器，共 2 个）；省略 12 个文件 / 527 KB——`Recognition/` 与 `标识/` 下的模板与标志图（`.jpg`，按「图像/纹理」规则省略，报告见各目录 `_OMITTED.md`）、`unitree_sdk2_python/**/lib/*.so` 与 `.pyc`；`D1_sdk/build/`（5.7 MB 编译产物）按 `build/` 规则**整目录跳过**。
- **平台与传感器布局**：Go2 **Edu** + **D1 七自由度机械臂**；`GC2093` USB 摄像头装头部前方（地面视觉：黑线/白线/黑区/蓝区），`D435i` **装在机械臂末端**（红圆 + 深度测距，最佳 15~30 cm），`TinyF` TOF ×3 左/右/前（`/dev/ttyUSB0/1/2`，115200，量程 4000 mm）。
- **可直接对照我们契约的数值**：
  - 控制线程 `CTRL_HZ = 100`（10 ms 一次 DDS 下发）；步态 `ClassicWalk` + `SpeedLevel`（台阶用 2 档高扭矩，切档后须重调 `ClassicWalk(True)`）。
  - 循迹 PID（Phase 1）：`P1_THRESHOLD 80`、`P1_PID_KP 0.8`、`P1_BASE_SPEED 0.35 m/s`、`P1_WHITE_CROSS_CONFIRM 5`、`P1_JUMP_FORWARD_SPEED 1.0`；黑线阈值经验值：正常 80~100 / 强光 100~130 / 暗光 60~80。
  - 迷宫 TOF（Phase 2）：`BASE_FORWARD_SPEED 0.30`、`CENTER_GAIN 0.0006`、`P1_FRONT_MM 280`、`HAIRPIN_VX 0.25 / HAIRPIN_VYAW 0.6`、毛刺滤波 `SPIKE_DELTA_MM 800` / `CONFIRM_FRAMES 3`。
  - 台阶（Phase 3）：`P3_STAIRS_FAST_SPEED 0.7`、`P3_PITCH_CLIMBING_THRESH 0.15 rad`、`P3_PITCH_STOP_THRESH 0.08 rad`、`P3_TURN_ANGLE_DEG 90`、`P3_BLACK_RATIO_THRESHOLD 0.75`。
  - 机械臂：`REF_JOINT_ANGLES` 两版零位（`-90°` / `68.7°`，不同批次硬件）；J4 补偿 `j4_scale_y 0.73 / j4-scale-x-pos 1.3 / j4-scale-x-neg -0.1`；工作空间约 500 mm；坐标 **X 前 / Y 左 / Z 上，单位 cm**。
- **自带离线自检（可借鉴的验收姿势）**：`测距模块/迷宫_tof.py --sim`（毛刺滤波 / 横向纠偏律 / 多阶段状态机 / 库函数接线 4 项）、`视觉抓取/arm_ik_control.py --dry-run --xyz ...`（IK 精度离线）。
- **注意（作者自陈的坑）**：① Phase 5 依赖回头弯处**固定丢线点**触发中转抓取——换场地即失效；② 带网口的扩展坞会干扰 D1 的 USB 通信（务必用纯 USB 扩展坞）；③ 跳跃前必须关摄像头释放 USB 带宽；④ 代码与硬件强耦合（`/dev/video*` 自动探测、ToDesk 取画面），不可直接跑通全流程。
