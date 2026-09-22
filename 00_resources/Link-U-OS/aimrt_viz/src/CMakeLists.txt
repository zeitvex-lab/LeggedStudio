# Copyright (c) 2023, AgiBot Inc.
# All rights reserved

set_root_namespace("aimrt_viz")

add_subdirectory(tools)
add_subdirectory(protocols)

if(AIMRT_VIZ_BUILD_PLUGIN)
  add_subdirectory(plugins)
endif()

if(AIMRT_VIZ_BUILD_MODULE)
  add_subdirectory(module/viz_module)
  add_subdirectory(pkg/viz_pkg)
endif()

if(AIMRT_VIZ_BUILD_EXAMPLES)
  add_subdirectory(examples)
endif()
