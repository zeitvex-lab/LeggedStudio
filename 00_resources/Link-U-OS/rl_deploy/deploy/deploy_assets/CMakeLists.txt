cmake_minimum_required(VERSION 3.10)
project(deploy_assets)

find_package(ament_cmake REQUIRED)

# assets now colocated under this package
set(THIRDPARTY_DIR ${CMAKE_CURRENT_SOURCE_DIR}/thirdparty)
set(SCRIPTS_DIR ${CMAKE_CURRENT_SOURCE_DIR}/scripts)
if(NOT EXISTS ${THIRDPARTY_DIR})
  message(FATAL_ERROR "thirdparty directory not found: ${THIRDPARTY_DIR}")
endif()

install(
  DIRECTORY ${THIRDPARTY_DIR}/
  DESTINATION thirdparty
)

install(
  DIRECTORY ${SCRIPTS_DIR}/
  DESTINATION scripts
  USE_SOURCE_PERMISSIONS
)

ament_package()
