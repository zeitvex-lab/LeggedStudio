// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#include "src/interface/aimrt_type_support_pkg_c_interface/type_support_pkg_main.h"

#include "src/interface/aimrt_module_ros2_interface/util/ros2_type_support.h"

#include "src/protocols/ros2/aimrt_msgs/ros2_aimrt_msgs_interface/msg/joint_command.hpp"
#include "src/protocols/ros2/aimrt_msgs/ros2_aimrt_msgs_interface/msg/joint_command_array.hpp"
#include "src/protocols/ros2/aimrt_msgs/ros2_aimrt_msgs_interface/msg/joint_state.hpp"
#include "src/protocols/ros2/aimrt_msgs/ros2_aimrt_msgs_interface/msg/joint_state_array.hpp"
#include "src/protocols/ros2/aimrt_msgs/ros2_aimrt_msgs_interface/msg/message_header.hpp"
#include "src/protocols/ros2/aimrt_msgs/ros2_aimrt_msgs_interface/msg/touch_sensor_state.hpp"
#include "src/protocols/ros2/aimrt_msgs/ros2_aimrt_msgs_interface/msg/touch_sensor_state_array.hpp"

static const aimrt_type_support_base_t* type_support_array[]{
    aimrt::GetRos2MessageTypeSupport<ros2_aimrt_msgs_interface::msg::MessageHeader>(),
    aimrt::GetRos2MessageTypeSupport<ros2_aimrt_msgs_interface::msg::TouchSensorStateArray>(),
    aimrt::GetRos2MessageTypeSupport<ros2_aimrt_msgs_interface::msg::TouchSensorState>(),
    aimrt::GetRos2MessageTypeSupport<ros2_aimrt_msgs_interface::msg::JointStateArray>(),
    aimrt::GetRos2MessageTypeSupport<ros2_aimrt_msgs_interface::msg::JointState>(),
    aimrt::GetRos2MessageTypeSupport<ros2_aimrt_msgs_interface::msg::JointCommandArray>(),
    aimrt::GetRos2MessageTypeSupport<ros2_aimrt_msgs_interface::msg::JointCommand>()};

extern "C" {

size_t AimRTDynlibGetTypeSupportArrayLength() {
  return sizeof(type_support_array) / sizeof(type_support_array[0]);
}

const aimrt_type_support_base_t** AimRTDynlibGetTypeSupportArray() {
  return type_support_array;
}
}