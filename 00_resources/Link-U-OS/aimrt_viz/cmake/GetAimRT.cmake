# Copyright (c) 2023, AgiBot Inc.
# All rights reserved.

include(FetchContent)

message(STATUS "get aimrt ...")

set(aimrt_DOWNLOAD_URL
    "https://github.com/AimRT/AimRT/archive/refs/tags/v1.0.0.tar.gz"
    CACHE STRING "")

if(aimrt_LOCAL_SOURCE)
  FetchContent_Declare(
    aimrt
    SOURCE_DIR ${aimrt_LOCAL_SOURCE}
    OVERRIDE_FIND_PACKAGE)
else()
  FetchContent_Declare(
    aimrt
    URL ${aimrt_DOWNLOAD_URL}
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE
    OVERRIDE_FIND_PACKAGE)
endif()


# Wrap it in a function to restrict the scope of the variables
function(get_aimrt)
  FetchContent_GetProperties(aimrt)

  if(NOT aimrt_POPULATED)

    set(AIMRT_BUILD_RUNTIME ON)
    set(AIMRT_BUILD_WITH_PROTOBUF ON)
    set(AIMRT_BUILD_PROTOCOLS OFF)
    set(AIMRT_BUILD_NET_PLUGIN ON)
    set(AIMRT_INSTALL AIMRT_VIZ_INSTALL)

    if(AIMRT_VIZ_BUILD_EXAMPLES)
      set(AIMRT_BUILD_EXAMPLES ON)
    endif()

    FetchContent_MakeAvailable(aimrt)
  endif()
endfunction()

get_aimrt()
