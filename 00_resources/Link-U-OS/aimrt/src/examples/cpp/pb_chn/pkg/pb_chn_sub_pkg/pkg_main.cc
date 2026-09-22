// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#include <cstring>

#include "src/interface/aimrt_pkg_c_interface/pkg_macro.h"
#include "src/examples/cpp/pb_chn/module/benchmark_subscriber_module/benchmark_subscriber_module.h"
#include "src/examples/cpp/pb_chn/module/normal_subscriber_module/normal_subscriber_module.h"

using namespace aimrt::examples::cpp::pb_chn;

static std::tuple<std::string_view, std::function<aimrt::ModuleBase*()>> aimrt_module_register_array[]{
    {"NormalSubscriberModule", []() -> aimrt::ModuleBase* {
       return new normal_subscriber_module::NormalSubscriberModule();
     }},
    {"BenchmarkSubscriberModule", []() -> aimrt::ModuleBase* {
       return new benchmark_subscriber_module::BenchmarkSubscriberModule();
     }}};

AIMRT_PKG_MAIN(aimrt_module_register_array)
