// Copyright (c) 2023, AgiBot Inc.
// All rights reserved.

#include <cstring>

#include "aimrt_pkg_c_interface/pkg_macro.h"
#include "viz_module/viz_module.h"

static std::tuple<std::string_view, std::function<aimrt::ModuleBase*()>> aimrt_module_register_array[]{
    {"VizModule", []() -> aimrt::ModuleBase* {
       return new aimrt_viz::viz_module::VizModule();
     }},
};

AIMRT_PKG_MAIN(aimrt_module_register_array)
