# taggy — 参考资源

> **来源**：`00_open/taggy/`　｜　**类型**：仿真与 bringup 参考（ROS2 + Gazebo）
> **关联机型**：unitree_go2（宇树 Go2 四足）
> **定位**：Go2 的 ROS2 bringup / 控制 / Gazebo 仿真（Taggy 巡逻机器人原型）：/cmd_vel↔Sport 桥接、unitree_go 与 unitree_api 消息定义、D435i 传感器 launch 与 Gazebo 世界
> **收录**：333 个文件 / 2.5 MB（其中推理策略/模型文件 0 个）
> **已省略**：0 个文件 / 0 B（登记在各目录 `_OMITTED.md`）

## 能帮什么

- **本体与场景描述**（1 个）：机型/场景描述（URDF·xacro·MJCF）：本体几何、关节树、碰撞与场景搭建
- **RL 训练工程**（2 个）：RL 训练工程：环境配置、奖励、指令、课程、域随机化、任务注册与训练脚本
- **部署与推理**（170 个）：部署与推理：策略文件（onnx/pt/engine）、FSM、控制频率、SDK 桥、sim2sim
- **动作与运动数据**（32 个）：动作与运动数据：重定向配置、参考动作、步态数据
- **文档与其它**（128 个）：文档、说明、许可与零散脚本

## 目录构成

```text
(根目录)/  （2 个文件）
HesaiLidar_ROS_2.0/  （223 个文件）
    (直接文件)/
    config/
    launch/
    msg/
    node/
    rviz/
    src/
go2_bringup/  （5 个文件）
    (直接文件)/
    launch/
go2_control/  （52 个文件）
    (直接文件)/
    include/
    src/
go2_examples/  （4 个文件）
    (直接文件)/
    go2_examples/
    scripts/
go2_interfaces/  （7 个文件）
    (直接文件)/
    go2_interfaces/
    scripts/
go2_simulation/  （4 个文件）
    (直接文件)/
    launch/
    worlds/
unitree_api/  （10 个文件）
    (直接文件)/
    msg/
unitree_go/  （26 个文件）
    (直接文件)/
    msg/
```

## 文件类型分布（Top 15）

| 扩展名 | 数量 |
|---|---:|
| `.h` | 66 |
| `.hpp` | 54 |
| `.msg` | 42 |
| `.cc` | 42 |
| `.md` | 32 |
| `.csv` | 32 |
| `.txt` | 13 |
| `.py` | 13 |
| `.cu` | 13 |
| `.xml` | 8 |
| `.dat` | 5 |
| `(无扩展名)` | 4 |
| `.rviz` | 2 |
| `.cpp` | 2 |
| `.in` | 1 |

## 文件索引（项目内相对路径）

```text
.gitignore
HesaiLidar_ROS_2.0/.gitignore
HesaiLidar_ROS_2.0/CMakeLists.txt
HesaiLidar_ROS_2.0/README.md
HesaiLidar_ROS_2.0/Version.h.in
HesaiLidar_ROS_2.0/change notes.md
HesaiLidar_ROS_2.0/config/config.yaml
HesaiLidar_ROS_2.0/launch/dashing_start.py
HesaiLidar_ROS_2.0/launch/start.launch
HesaiLidar_ROS_2.0/launch/start.py
HesaiLidar_ROS_2.0/msg/Firetime.msg
HesaiLidar_ROS_2.0/msg/LossPacket.msg
HesaiLidar_ROS_2.0/msg/Ptp.msg
HesaiLidar_ROS_2.0/msg/UdpFrame.msg
HesaiLidar_ROS_2.0/msg/UdpPacket.msg
HesaiLidar_ROS_2.0/msg/msg_ros2/Firetime.msg
HesaiLidar_ROS_2.0/msg/msg_ros2/LossPacket.msg
HesaiLidar_ROS_2.0/msg/msg_ros2/Ptp.msg
HesaiLidar_ROS_2.0/msg/msg_ros2/UdpFrame.msg
HesaiLidar_ROS_2.0/msg/msg_ros2/UdpPacket.msg
HesaiLidar_ROS_2.0/node/hesai_ros_driver_node.cc
HesaiLidar_ROS_2.0/node/hesai_ros_driver_node.cu
HesaiLidar_ROS_2.0/package.xml
HesaiLidar_ROS_2.0/rviz/rviz.rviz
HesaiLidar_ROS_2.0/rviz/rviz2.rviz
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/.gitignore
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/CMakeLists.txt
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/LICENSE
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/README.md
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/README_CN.md
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/change notes.md
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/config/channel_fov_filter.txt
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/angle_correction/AT128E2X_Angle Correction File.dat
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/angle_correction/AT128E3X_Angle Correction File.dat
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/angle_correction/ATX_Angle_Correction_File_V42.dat
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/angle_correction/ET25_Angle_Correction_File_V1.dat
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/angle_correction/FT120C1X_Angle Correction File.dat
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/angle_correction/JT128_Angle Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/angle_correction/JT16_Angle Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/angle_correction/OT128_40_Angle Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/angle_correction/OT128_Angle Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/angle_correction/Pandar128E3X_Angle Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/angle_correction/Pandar40M_Angle Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/angle_correction/Pandar40P_Angle Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/angle_correction/Pandar64_Angle Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/angle_correction/Pandar90E3X_Angle Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/angle_correction/PandarQT_Angle Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/angle_correction/PandarXT-16_Angle Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/angle_correction/PandarXT_Angle Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/angle_correction/QT128C2X_Angle Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/angle_correction/QT128C2X_Channel_Cofig.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/angle_correction/XT32M2X_Angle Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/firetime_correction/AT128E2X_Firetime Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/firetime_correction/ATX_Firetime Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/firetime_correction/JT128_Firetime Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/firetime_correction/OT128_40_Frietime Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/firetime_correction/OT128_Firetime Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/firetime_correction/Pandar128E3X_Firetime Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/firetime_correction/Pandar40E3X_Firetime Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/firetime_correction/Pandar40P_Firetime Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/firetime_correction/Pandar64E3X_Firetime Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/firetime_correction/Pandar64_Firetime Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/firetime_correction/Pandar90_Firetime Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/firetime_correction/PandarQT_Firetime Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/firetime_correction/PandarXT-16_Firetime Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/firetime_correction/PandarXT-32M2X_Firetime Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/firetime_correction/PandarXT-32_Firetime Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/firetime_correction/PandarXT_Firetime Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/correction/firetime_correction/QT128C2X_Firetime Correction File.csv
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/docs/common_error_codes.md
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/docs/common_error_codes_CN.md
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/docs/compile_macro_control_description.md
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/docs/compile_macro_control_description_CN.md
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/docs/compile_on_windows.md
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/docs/compile_on_windows_CN.md
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/docs/coordinate_transformation.md
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/docs/coordinate_transformation_CN.md
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/docs/invoke_sdk_api_command_interface.md
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/docs/invoke_sdk_api_command_interface_CN.md
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/docs/packet_loss_analysis.md
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/docs/packet_loss_analysis_CN.md
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/docs/parameter_introduction.md
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/docs/parameter_introduction_CN.md
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/docs/parsing_lidar_data_online.md
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/docs/parsing_lidar_data_online_CN.md
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/docs/parsing_pcap_file_data_offline.md
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/docs/parsing_pcap_file_data_offline_CN.md
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/docs/point_cloud_rearrangement_function.md
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/docs/point_cloud_rearrangement_function_CN.md
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/docs/save_point_cloud_data_as_a_pcd_file.md
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/docs/save_point_cloud_data_as_a_pcd_file_CN.md
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/docs/use_gpu_acceleration.md
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/docs/use_gpu_acceleration_CN.md
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/docs/visualization_of_point_cloud_data.md
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/docs/visualization_of_point_cloud_data_CN.md
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/driver/hesai_lidar_sdk.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/driver/hesai_lidar_sdk.hpp
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/CMakeLists.txt
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/Common/include/auto_tick_count.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/Common/include/byte_printer.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/Common/include/csv_reader.hpp
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/Common/include/hs_com.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/Common/include/inner_com.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/Common/include/plat_utils.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/Common/src/auto_tick_count.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/Common/src/plat_utils.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/Container/include/blocking_ring.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/Container/include/ring.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/Container/src/blocking_ring.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/Container/src/ring.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/Lidar/lidar.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/Lidar/lidar.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/Logger/include/logger.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/Logger/src/logger.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/PtcClient/include/client_base.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/PtcClient/include/lidar_communication_header.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/PtcClient/include/ptc_client.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/PtcClient/include/tcp_client.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/PtcClient/include/tcp_ssl_client.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/PtcClient/src/ptc_client.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/PtcClient/src/tcp_client.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/PtcClient/src/tcp_ssl_client.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/PtcParser/include/general_ptc_parser.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/PtcParser/include/ptc_1_0_parser.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/PtcParser/include/ptc_2_0_parser.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/PtcParser/ptc_parser.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/PtcParser/ptc_parser.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/PtcParser/src/general_ptc_parser.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/PtcParser/src/ptc_1_0_parser.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/PtcParser/src/ptc_2_0_parser.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/SerialClient/include/serial_client.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/SerialClient/src/serial_client.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/Source/include/pcap_saver.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/Source/include/pcap_source.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/Source/include/serial_source.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/Source/include/socket_source.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/Source/include/source.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/Source/include/tcp_source.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/Source/src/pcap_saver.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/Source/src/pcap_source.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/Source/src/serial_source.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/Source/src/socket_source.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/Source/src/source.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/Source/src/tcp_source.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParser/include/general_parser.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParser/include/udp1_4_parser.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParser/include/udp1_8_parser.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParser/include/udp3_1_parser.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParser/include/udp3_2_parser.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParser/include/udp4_3_parser.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParser/include/udp4_7_parser.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParser/include/udp6_1_parser.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParser/include/udp7_2_parser.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParser/include/udp_p40_parser.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParser/include/udp_p64_parser.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParser/src/general_parser.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParser/src/udp1_4_parser.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParser/src/udp1_8_parser.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParser/src/udp3_1_parser.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParser/src/udp3_2_parser.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParser/src/udp4_3_parser.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParser/src/udp4_7_parser.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParser/src/udp6_1_parser.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParser/src/udp7_2_parser.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParser/src/udp_p40_parser.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParser/src/udp_p64_parser.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParser/udp_parser.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParser/udp_parser.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParserGpu/include/general_parser_gpu.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParserGpu/include/general_struct_gpu.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParserGpu/include/return_code.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParserGpu/include/safe_call.cuh
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParserGpu/include/udp1_4_parser_gpu.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParserGpu/include/udp1_8_parser_gpu.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParserGpu/include/udp3_1_parser_gpu.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParserGpu/include/udp3_2_parser_gpu.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParserGpu/include/udp4_3_parser_gpu.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParserGpu/include/udp4_7_parser_gpu.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParserGpu/include/udp6_1_parser_gpu.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParserGpu/include/udp7_2_parser_gpu.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParserGpu/include/udp_p40_parser_gpu.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParserGpu/include/udp_p64_parser_gpu.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParserGpu/src/general_parser_gpu.cu
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParserGpu/src/udp1_4_parser_gpu.cu
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParserGpu/src/udp1_8_parser_gpu.cu
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParserGpu/src/udp3_1_parser_gpu.cu
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParserGpu/src/udp3_2_parser_gpu.cu
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParserGpu/src/udp4_3_parser_gpu.cu
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParserGpu/src/udp4_7_parser_gpu.cu
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParserGpu/src/udp6_1_parser_gpu.cu
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParserGpu/src/udp7_2_parser_gpu.cu
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParserGpu/src/udp_p40_parser_gpu.cu
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParserGpu/src/udp_p64_parser_gpu.cu
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParserGpu/udp_parser_gpu.cu
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpParserGpu/udp_parser_gpu.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpProtocol/fault_message.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpProtocol/udp_protocol_header.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpProtocol/udp_protocol_p40.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpProtocol/udp_protocol_p64.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpProtocol/udp_protocol_v1_4.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpProtocol/udp_protocol_v1_8.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpProtocol/udp_protocol_v3_1.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpProtocol/udp_protocol_v3_2.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpProtocol/udp_protocol_v4_3.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpProtocol/udp_protocol_v4_7.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpProtocol/udp_protocol_v6_1.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/UdpProtocol/udp_protocol_v7_2.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/driver_param.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/libhesai/lidar_types.h
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/test/multi_test.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/test/test.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/tool/CMakeLists.txt
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/tool/las_tool.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/tool/packet_loss_tool.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/tool/pcl_tool.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/tool_ptc/CMakeLists.txt
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/tool_ptc/ptc_tool.cc
HesaiLidar_ROS_2.0/src/driver/HesaiLidar_SDK_2.0/tool_ptc/ptc_upgrade.cc
HesaiLidar_ROS_2.0/src/manager/node_manager.cc
HesaiLidar_ROS_2.0/src/manager/node_manager.h
HesaiLidar_ROS_2.0/src/manager/source_drive_common.hpp
HesaiLidar_ROS_2.0/src/manager/source_driver_ros1.hpp
HesaiLidar_ROS_2.0/src/manager/source_driver_ros2.hpp
HesaiLidar_ROS_2.0/src/utility/yaml_reader.hpp
README.md
go2_bringup/CMakeLists.txt
go2_bringup/launch/full_bringup.launch.py
go2_bringup/launch/go2_control.launch.py
go2_bringup/launch/sensors.launch.py
go2_bringup/package.xml
go2_control/CMakeLists.txt
go2_control/include/common/patch.hpp
go2_control/include/common/sport_client.hpp
go2_control/include/common/time_tools.hpp
go2_control/include/nlohmann/adl_serializer.hpp
go2_control/include/nlohmann/byte_container_with_subtype.hpp
go2_control/include/nlohmann/detail/abi_macros.hpp
go2_control/include/nlohmann/detail/conversions/from_json.hpp
go2_control/include/nlohmann/detail/conversions/to_chars.hpp
go2_control/include/nlohmann/detail/conversions/to_json.hpp
go2_control/include/nlohmann/detail/exceptions.hpp
go2_control/include/nlohmann/detail/hash.hpp
go2_control/include/nlohmann/detail/input/binary_reader.hpp
go2_control/include/nlohmann/detail/input/input_adapters.hpp
go2_control/include/nlohmann/detail/input/json_sax.hpp
go2_control/include/nlohmann/detail/input/lexer.hpp
go2_control/include/nlohmann/detail/input/parser.hpp
go2_control/include/nlohmann/detail/input/position_t.hpp
go2_control/include/nlohmann/detail/iterators/internal_iterator.hpp
go2_control/include/nlohmann/detail/iterators/iter_impl.hpp
go2_control/include/nlohmann/detail/iterators/iteration_proxy.hpp
go2_control/include/nlohmann/detail/iterators/iterator_traits.hpp
go2_control/include/nlohmann/detail/iterators/json_reverse_iterator.hpp
go2_control/include/nlohmann/detail/iterators/primitive_iterator.hpp
go2_control/include/nlohmann/detail/json_custom_base_class.hpp
go2_control/include/nlohmann/detail/json_pointer.hpp
go2_control/include/nlohmann/detail/json_ref.hpp
go2_control/include/nlohmann/detail/macro_scope.hpp
go2_control/include/nlohmann/detail/macro_unscope.hpp
go2_control/include/nlohmann/detail/meta/call_std/begin.hpp
go2_control/include/nlohmann/detail/meta/call_std/end.hpp
go2_control/include/nlohmann/detail/meta/cpp_future.hpp
go2_control/include/nlohmann/detail/meta/detected.hpp
go2_control/include/nlohmann/detail/meta/identity_tag.hpp
go2_control/include/nlohmann/detail/meta/is_sax.hpp
go2_control/include/nlohmann/detail/meta/std_fs.hpp
go2_control/include/nlohmann/detail/meta/type_traits.hpp
go2_control/include/nlohmann/detail/meta/void_t.hpp
go2_control/include/nlohmann/detail/output/binary_writer.hpp
go2_control/include/nlohmann/detail/output/output_adapters.hpp
go2_control/include/nlohmann/detail/output/serializer.hpp
go2_control/include/nlohmann/detail/string_concat.hpp
go2_control/include/nlohmann/detail/string_escape.hpp
go2_control/include/nlohmann/detail/value_t.hpp
go2_control/include/nlohmann/json.hpp
go2_control/include/nlohmann/json_fwd.hpp
go2_control/include/nlohmann/ordered_map.hpp
go2_control/include/nlohmann/thirdparty/hedley/hedley.hpp
go2_control/include/nlohmann/thirdparty/hedley/hedley_undef.hpp
go2_control/package.xml
go2_control/src/common/sport_client.cpp
go2_control/src/go2_control_node.cpp
go2_examples/CMakeLists.txt
go2_examples/go2_examples/__init__.py
go2_examples/package.xml
go2_examples/scripts/keyboard_teleop.py
go2_interfaces/CMakeLists.txt
go2_interfaces/go2_interfaces/__init__.py
go2_interfaces/go2_interfaces/go2_sdk.py
go2_interfaces/package.xml
go2_interfaces/scripts/go2_odometry.py
go2_interfaces/scripts/go2_state_publisher.py
go2_interfaces/scripts/go2_velocity_controller.py
go2_simulation/CMakeLists.txt
go2_simulation/launch/gazebo_sim.launch.py
go2_simulation/package.xml
go2_simulation/worlds/coworking.sdf
unitree_api/CMakeLists.txt
unitree_api/msg/Request.msg
unitree_api/msg/RequestHeader.msg
unitree_api/msg/RequestIdentity.msg
unitree_api/msg/RequestLease.msg
unitree_api/msg/RequestPolicy.msg
unitree_api/msg/Response.msg
unitree_api/msg/ResponseHeader.msg
unitree_api/msg/ResponseStatus.msg
unitree_api/package.xml
unitree_go/CMakeLists.txt
unitree_go/msg/AudioData.msg
unitree_go/msg/BmsCmd.msg
unitree_go/msg/BmsState.msg
unitree_go/msg/Error.msg
unitree_go/msg/Go2FrontVideoData.msg
unitree_go/msg/HeightMap.msg
unitree_go/msg/IMUState.msg
unitree_go/msg/InterfaceConfig.msg
unitree_go/msg/LidarState.msg
unitree_go/msg/LowCmd.msg
unitree_go/msg/LowState.msg
unitree_go/msg/MotorCmd.msg
unitree_go/msg/MotorCmds.msg
unitree_go/msg/MotorState.msg
unitree_go/msg/MotorStates.msg
unitree_go/msg/PathPoint.msg
unitree_go/msg/Req.msg
unitree_go/msg/Res.msg
unitree_go/msg/SportModeCmd.msg
unitree_go/msg/SportModeState.msg
unitree_go/msg/TimeSpec.msg
unitree_go/msg/UwbState.msg
unitree_go/msg/UwbSwitch.msg
unitree_go/msg/WirelessController.msg
unitree_go/package.xml
```

## 导入边界与关键数值（人工补充，重新同步时需重做）

- **收录口径**：上游很小（333 文件 / 2.5 MB），**全量收录**（含 `HesaiLidar_ROS_2.0` 驱动本体与其 vendored SDK、`.dat/.csv` 标定数据），唯一未收的是 `.git/`。
- **许可**：上游**无根 LICENSE**（EDTH 黑客松原型，ROS2 **Foxy**，2025-11 后基本不维护）；`unitree_go` / `unitree_api` 为 Unitree 消息定义；`HesaiLidar_ROS_2.0` 自带 BSD LICENSE，但内含大量第三方代码与标定数据 → 整体仅作**内部参考**。
- **关键对照数值**：速度上限 **±1.0 m/s / ±1.0 rad/s**（`go2_velocity_controller`，50 Hz，指令超时 0.5 s，协方差 0.01）；D435i `640×480@30`，深度 `16UC1`(mm) + `/camera/color/points` + `/camera/imu`；静态 TF `base_link→hesai_lidar (0.1710, 0, 0.0908)`、`base_link→camera_link (0.3, 0, 0.3)`（后者默认注释）；Hesai XT16：`device_ip 192.168.123.20` / `udp_port 2368` / `ptc_port 9347` / `frame_frequency 10 Hz` / frame `hesai_lidar` / 话题 `/lidar_points` `/lidar_imu` `/lidar_packets_loss`。
- **消息定义（与真机口径对齐用）**：`SportModeState`(`position[3]` / `body_height` / `velocity[3]` / `yaw_speed` / `foot_position_body[12]` / `foot_force[4]` / `range_obstacle[4]` / `gait_type`)、`LowState`/`LowCmd`（20 槽位）、`IMUState`、`MotorCmd`/`MotorState`、`PathPoint`、`LidarState`、`HeightMap`(`resolution` / `origin` / `data` 行主序)、`UwbState`；`unitree_api` 的 `Request`/`Response` 头。
- **注意**：`go2_interfaces/go2_interfaces/go2_sdk.py` 是**伪 SDK**（自造 UDP `192.168.123.161:8082`，`struct '<BBffff'`，50 Hz），**不是** Unitree 真实 DDS 协议，只能当结构占位；`gazebo_sim.launch.py` 里机器人 spawn 被注释（开箱不会出现机器人），世界为 `worlds/coworking.sdf`（62 KB）。
