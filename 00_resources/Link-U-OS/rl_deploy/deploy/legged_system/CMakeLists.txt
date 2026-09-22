cmake_minimum_required(VERSION 3.13)
project(legged_system)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

set(CMAKE_MODULE_PATH ${CMAKE_MODULE_PATH} "${CMAKE_SOURCE_DIR}/cmake")
include(GetAimRT)

find_package(Eigen3 REQUIRED)

set(Eigen3_INCLUDE_DIRS ${EIGEN3_INCLUDE_DIR})

set(CMAKE_SKIP_BUILD_RPATH FALSE)
set(CMAKE_BUILD_WITH_INSTALL_RPATH FALSE)
set(CMAKE_INSTALL_RPATH_USE_LINK_PATH TRUE)
set(CMAKE_INSTALL_RPATH "${CMAKE_INSTALL_PREFIX}/lib")
set(CMAKE_INSTALL_NAME_DIR "${CMAKE_INSTALL_PREFIX}/lib")

# find dependencies
set(THIS_PACKAGE_INCLUDE_DEPENDS
    hardware_interface
    pluginlib
    rclcpp
    rclcpp_lifecycle
    realtime_tools
    std_msgs
    tf2_ros
    joint_msgs)

find_package(ament_cmake REQUIRED)
foreach(Dependency IN ITEMS ${THIS_PACKAGE_INCLUDE_DEPENDS})
  find_package(${Dependency} REQUIRED)
endforeach()

include_directories(include include/legged_system ${Eigen3_INCLUDE_DIRS})

## COMPILE
add_library(legged_system SHARED src/LeggedSystem.cpp src/Utilities.cpp src/LoopAnkleAnalyticalSolver.cpp)
target_compile_features(legged_system PUBLIC cxx_std_17)

target_include_directories(
  legged_system
  PUBLIC $<BUILD_INTERFACE:${PROJECT_SOURCE_DIR}/include>
         $<INSTALL_INTERFACE:include/legged_system>)

ament_target_dependencies(legged_system PUBLIC ${THIS_PACKAGE_INCLUDE_DEPENDS} tf2_ros)

find_package(Boost REQUIRED)

target_link_libraries(
  legged_system
  PUBLIC joint_msgs::joint_msgs__rosidl_generator_cpp # ROS library for message types
         joint_msgs::joint_msgs__rosidl_typesupport_cpp
         joint_msgs::joint_msgs__rosidl_typesupport_fastrtps_cpp
         joint_msgs::joint_msgs__rosidl_typesupport_introspection_cpp
         aimrt::interface::aimrt_module_ros2_interface
         aimrt::runtime::core)

target_compile_definitions(${PROJECT_NAME} PRIVATE "legged_system_BUILDING_DLL")

# Export hardware plugins
pluginlib_export_plugin_description_file(hardware_interface legged_system.xml)

# INSTALL
install(DIRECTORY include/ DESTINATION include/legged_system)

install(
  TARGETS legged_system
  EXPORT export_legged_system
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin)

# Install header files
install(
  DIRECTORY include/${PROJECT_NAME}/
  DESTINATION include/${PROJECT_NAME}
  FILES_MATCHING
  PATTERN "*.h")

# Install other directories
install(DIRECTORY DESTINATION share/${PROJECT_NAME})

# Install package.xml
install(FILES package.xml DESTINATION share/${PROJECT_NAME})

# Install cfg files
install(DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/cfg/ DESTINATION bin USE_SOURCE_PERMISSIONS)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  set(ament_cmake_copyright_FOUND TRUE)
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
