# Copyright (c) 2023, AgiBot Inc.
# All rights reserved

# Get the current folder name
string(REGEX REPLACE ".*/\(.*\)" "\\1" CUR_DIR ${CMAKE_CURRENT_SOURCE_DIR})

# Set namespace
set_namespace()

# install
if(AIMRT_MUJOCO_SIM_INSTALL)
  install(DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/bin/ DESTINATION bin
    USE_SOURCE_PERMISSIONS
  )
endif()
