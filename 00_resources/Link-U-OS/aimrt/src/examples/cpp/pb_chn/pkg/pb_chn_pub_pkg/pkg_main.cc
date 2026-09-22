// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#include <cstring>

#include "src/interface/aimrt_pkg_c_interface/pkg_macro.h"
#include "src/examples/cpp/pb_chn/module/benchmark_publisher_module/benchmark_publisher_module.h"
#include "src/examples/cpp/pb_chn/module/normal_publisher_module/normal_publisher_module.h"

using namespace aimrt::examples::cpp::pb_chn;

static std::tuple<std::string_view, std::function<aimrt::ModuleBase*()>> aimrt_module_register_array[]{
    {"NormalPublisherModule", []() -> aimrt::ModuleBase* {
       return new normal_publisher_module::NormalPublisherModule();
     }},
    {"BenchmarkPublisherModule", []() -> aimrt::ModuleBase* {
       return new benchmark_publisher_module::BenchmarkPublisherModule();
     }}};

AIMRT_PKG_MAIN(aimrt_module_register_array)
