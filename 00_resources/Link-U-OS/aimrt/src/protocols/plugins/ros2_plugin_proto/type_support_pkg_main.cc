// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#include "src/interface/aimrt_type_support_pkg_c_interface/type_support_pkg_main.h"

#include "src/interface/aimrt_module_ros2_interface/util/ros2_type_support.h"

#include "src/plugins/ros2_plugin_proto/msg/ros_msg_wrapper.hpp"

static const aimrt_type_support_base_t* type_support_array[]{
    aimrt::GetRos2MessageTypeSupport<ros2_plugin_proto::msg::RosMsgWrapper>()};

extern "C" {

size_t AimRTDynlibGetTypeSupportArrayLength() {
  return sizeof(type_support_array) / sizeof(type_support_array[0]);
}

const aimrt_type_support_base_t** AimRTDynlibGetTypeSupportArray() {
  return type_support_array;
}
}