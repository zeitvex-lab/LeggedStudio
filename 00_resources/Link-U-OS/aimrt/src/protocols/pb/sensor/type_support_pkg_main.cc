// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#include "src/interface/aimrt_type_support_pkg_c_interface/type_support_pkg_main.h"

#include "src/interface/aimrt_module_protobuf_interface/util/protobuf_type_support.h"

#include "src/protocols/pb/sensor/image.pb.h"
#include "src/protocols/pb/sensor/imu.pb.h"
#include "src/protocols/pb/sensor/joint_state.pb.h"
#include "src/protocols/pb/sensor/touch_sensor_state.pb.h"

static const aimrt_type_support_base_t* type_support_array[]{
    aimrt::GetProtobufMessageTypeSupport<aimrt::protocols::sensor::CompressedImage>(),
    aimrt::GetProtobufMessageTypeSupport<aimrt::protocols::sensor::ImuState>(),
    aimrt::GetProtobufMessageTypeSupport<aimrt::protocols::sensor::JointState>(),
    aimrt::GetProtobufMessageTypeSupport<aimrt::protocols::sensor::JointStateArray>(),
    aimrt::GetProtobufMessageTypeSupport<aimrt::protocols::sensor::TouchSensorState>(),
    aimrt::GetProtobufMessageTypeSupport<aimrt::protocols::sensor::TouchSensorStateArray>(),

};

extern "C" {

size_t AimRTDynlibGetTypeSupportArrayLength() {
  return sizeof(type_support_array) / sizeof(type_support_array[0]);
}

const aimrt_type_support_base_t** AimRTDynlibGetTypeSupportArray() {
  return type_support_array;
}
}