# Copyright (c) 2023, AgiBot Inc.
# All rights reserved.

cmake_minimum_required(VERSION 3.24)

project(aimrt_viz LANGUAGES C CXX)

# Set cmake path
list(APPEND CMAKE_MODULE_PATH ${CMAKE_CURRENT_SOURCE_DIR}/cmake)

include(CMakeDependentOption)

# Some option
option(AIMRT_VIZ_BUILD_TESTS "AimRT VIZ build tests." OFF)
option(AIMRT_VIZ_BUILD_PLUGIN "AimRT VIZ build plugin." ON)
option(AIMRT_VIZ_BUILD_MODULE "AimRT VIZ build module." ON)
option(AIMRT_VIZ_BUILD_WEB "AimRT VIZ build web." ON)

option(AIMRT_VIZ_BUILD_WITH_WERROR "AimRT VIZ build with -Werror option." ON)
option(AIMRT_VIZ_INSTALL "Enable installation of AimRT VIZ." ON)

cmake_dependent_option(AIMRT_VIZ_BUILD_EXAMPLES "AimRT VIZ build examples." OFF #
                       "AIMRT_VIZ_BUILD_PLUGIN;AIMRT_VIZ_BUILD_MODULE;AIMRT_VIZ_BUILD_WEB" OFF)

# Some necessary settings
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Set default build type as Release
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

file(READ "${PROJECT_SOURCE_DIR}/VERSION" AIMRT_VIZ_VERSION)
string(STRIP "${AIMRT_VIZ_VERSION}" AIMRT_VIZ_VERSION)
message("AimRT_Viz Version : ${AIMRT_VIZ_VERSION}")

set(INSTALL_CONFIG_NAME ${PROJECT_NAME}-config)

# Master project configuration
if(CMAKE_CURRENT_SOURCE_DIR STREQUAL CMAKE_SOURCE_DIR)
  set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR})
  set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR})
  set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR})

  set(FETCHCONTENT_BASE_DIR ${CMAKE_SOURCE_DIR}/_deps)

  set(BUILD_SHARED_LIBS OFF)
  set(CMAKE_C_VISIBILITY_PRESET hidden)
  set(CMAKE_C_VISIBILITY_INLINES_HIDDEN ON)
  set(CMAKE_CXX_VISIBILITY_PRESET hidden)
  set(CMAKE_CXX_VISIBILITY_INLINES_HIDDEN ON)

  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    if(AIMRT_VIZ_BUILD_TESTS)
      set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} --coverage")
      set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} --coverage")
    endif()
  endif()

  set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
endif()

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fPIC")
  set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -fPIC")
elseif(CMAKE_CXX_COMPILER_ID MATCHES "MSVC")
  add_compile_options(/utf-8 /wd4819)
  set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} /Zc:__cplusplus")
endif()

if(WIN32)
  add_compile_definitions(NOMINMAX)
endif()

# Include cmake module
include(NamespaceTool)

if(AIMRT_VIZ_BUILD_TESTS)
  include(GetGTest)
  enable_testing()
endif()

include(GetAimRT)

# Add subdirectory
add_subdirectory(src)

# Install
if(AIMRT_VIZ_INSTALL)
  install(
    DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/cmake
    DESTINATION ./
    FILES_MATCHING
    PATTERN "*.cmake")

  install(EXPORT ${INSTALL_CONFIG_NAME} DESTINATION lib/cmake/${PROJECT_NAME})
endif()
