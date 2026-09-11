cmake_minimum_required(VERSION 3.8)
project(dog_policy_test)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(dog_control REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(dog_nav REQUIRED)

# ONNX Runtime
set(ONNXRUNTIME_PATH "/opt/onnxruntime")
include_directories(${ONNXRUNTIME_PATH}/include)
link_directories(${ONNXRUNTIME_PATH}/lib)

# =============================================================================
# 调试工具
# =============================================================================

add_executable(motor_feedback_dump src/motor_feedback_dump.cpp)
ament_target_dependencies(motor_feedback_dump
  rclcpp
  dog_control
)

add_executable(imu_dump src/imu_dump.cpp)
ament_target_dependencies(imu_dump
  rclcpp
  sensor_msgs
)

add_executable(print_joint src/print_joint.cpp)
ament_target_dependencies(print_joint
  rclcpp
  sensor_msgs
)

# =============================================================================
# RL 策略推理节点
# =============================================================================

# --- test_5: 中间迭代版本 ---
add_executable(dog_policy_test_5 src/dog_policy_test_5.cpp)
ament_target_dependencies(dog_policy_test_5
  rclcpp
  sensor_msgs
  dog_control
)
target_link_libraries(dog_policy_test_5 onnxruntime)
set_target_properties(dog_policy_test_5 PROPERTIES
  BUILD_RPATH "/opt/onnxruntime/lib"
  INSTALL_RPATH "/opt/onnxruntime/lib"
)

# --- test_9: 命令渐变 ---
add_executable(dog_policy_test_9 src/dog_policy_test_9.cpp)
ament_target_dependencies(dog_policy_test_9
  rclcpp
  sensor_msgs
  dog_control
)
target_link_libraries(dog_policy_test_9 onnxruntime)
set_target_properties(dog_policy_test_9 PROPERTIES
  BUILD_RPATH "/opt/onnxruntime/lib"
  INSTALL_RPATH "/opt/onnxruntime/lib"
)

# --- test_10: test_9 + 系统监控 ---
add_executable(dog_policy_test_10 src/dog_policy_test_10.cpp)
ament_target_dependencies(dog_policy_test_10
  rclcpp
  sensor_msgs
  dog_control
)
target_link_libraries(dog_policy_test_10 onnxruntime)
set_target_properties(dog_policy_test_10 PROPERTIES
  BUILD_RPATH "/opt/onnxruntime/lib"
  INSTALL_RPATH "/opt/onnxruntime/lib"
)

# --- test_11: 最新版（基于 test_10 + DogNavCommand 订阅）---
add_executable(dog_policy_test_11 src/dog_policy_test_11.cpp)
ament_target_dependencies(dog_policy_test_11
  rclcpp
  sensor_msgs
  geometry_msgs
  dog_control
  dog_nav
)
target_link_libraries(dog_policy_test_11 onnxruntime)
set_target_properties(dog_policy_test_11 PROPERTIES
  BUILD_RPATH "/opt/onnxruntime/lib"
  INSTALL_RPATH "/opt/onnxruntime/lib"
)

# --- test_12: 基于 test_11 + 内置模型热切换（[/] 键切换）---
add_executable(dog_policy_test_12 src/dog_policy_test_12.cpp)
ament_target_dependencies(dog_policy_test_12
  rclcpp
  sensor_msgs
  geometry_msgs
  dog_control
  dog_nav
)
target_link_libraries(dog_policy_test_12 onnxruntime)
set_target_properties(dog_policy_test_12 PROPERTIES
  BUILD_RPATH "/opt/onnxruntime/lib"
  INSTALL_RPATH "/opt/onnxruntime/lib"
)

# --- test_13: 基于 test_12 + /policy_mode 外部挂起（蹲下取箱支持）---
add_executable(dog_policy_test_13 src/dog_policy_test_13.cpp)
ament_target_dependencies(dog_policy_test_13
  rclcpp
  sensor_msgs
  geometry_msgs
  dog_control
  dog_nav
)
target_link_libraries(dog_policy_test_13 onnxruntime)
set_target_properties(dog_policy_test_13 PROPERTIES
  BUILD_RPATH "/opt/onnxruntime/lib"
  INSTALL_RPATH "/opt/onnxruntime/lib"
)

# =============================================================================
# 安装
# =============================================================================

install(TARGETS
  dog_policy_test_5
  dog_policy_test_9
  dog_policy_test_10
  dog_policy_test_11
  dog_policy_test_12
  dog_policy_test_13
  motor_feedback_dump
  imu_dump
  print_joint
  DESTINATION lib/${PROJECT_NAME}
)

# 安装配置文件目录（YAML 参数文件）
install(DIRECTORY config/
  DESTINATION share/${PROJECT_NAME}/config
)

ament_package()