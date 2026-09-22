# Copyright (c) 2023, AgiBot Inc.
# All rights reserved.

set_namespace()

if(AIMRT_VIZ_BUILD_PLUGIN OR AIMRT_VIZ_BUILD_MODULE)
  add_subdirectory(viz_plugin)
endif()

if(AIMRT_VIZ_BUILD_MODULE)
  add_subdirectory(viz_web)
endif()
