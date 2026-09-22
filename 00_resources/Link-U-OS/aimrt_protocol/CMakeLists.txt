# Copyright (c) 2025, AgiBot Inc.
# All rights reserved.

cmake_minimum_required(VERSION 3.24)

# Toolchain file should be included before project()


cmake_policy(SET CMP0148 OLD)

project(aimrt_protocol)

# Prevent variables from being reset by option
# This setting allows predefined variables to take precedence for FetchContent_MakeAvailable()
# See: https://cmake.org/cmake/help/latest/policy/CMP0077.html
set(CMAKE_POLICY_DEFAULT_CMP0077 NEW)

# Some necessary settings
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Set default build type as Release
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

include(cmake/NamespaceTool.cmake)
set_root_namespace(aimrt_protocol)

add_subdirectory(ros2)
add_subdirectory(aimdk/protocol)