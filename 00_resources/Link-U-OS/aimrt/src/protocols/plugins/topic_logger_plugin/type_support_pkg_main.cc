// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#include "src/interface/aimrt_type_support_pkg_c_interface/type_support_pkg_main.h"

#include "src/interface/aimrt_module_protobuf_interface/util/protobuf_type_support.h"

#include "src/protocols/plugins/topic_logger_plugin/topic_logger.pb.h"

static const aimrt_type_support_base_t* type_support_array[]{
    aimrt::GetProtobufMessageTypeSupport<aimrt::protocols::topic_logger::LogData>()};

extern "C" {

size_t AimRTDynlibGetTypeSupportArrayLength() {
  return sizeof(type_support_array) / sizeof(type_support_array[0]);
}

const aimrt_type_support_base_t** AimRTDynlibGetTypeSupportArray() {
  return type_support_array;
}
}