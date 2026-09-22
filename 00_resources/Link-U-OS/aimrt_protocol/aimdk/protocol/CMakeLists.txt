# Copyright (c) 2025, AgiBot Inc.
# All rights reserved.

set_namespace()

set(ROS2_SUBPACKAGES
    hal/joint
    hal/pose
    hal/power
    hal/sensors
    hal/temp
    interaciton
    hds
)

foreach(SUBPACKAGE ${ROS2_SUBPACKAGES})
    if(EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/${SUBPACKAGE}/CMakeLists.txt)
        add_subdirectory(${SUBPACKAGE})
    endif()
endforeach()
