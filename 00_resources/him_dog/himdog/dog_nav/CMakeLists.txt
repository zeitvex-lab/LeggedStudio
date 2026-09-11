cmake_minimum_required(VERSION 3.8)
project(dog_nav)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# =========================
# 依赖
# =========================
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(tf2 REQUIRED)
find_package(rosidl_default_generators REQUIRED)

# =========================
# 自定义消息生成
# =========================
rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/DogNavCommand.msg"
  DEPENDENCIES std_msgs
)

# =========================
# 导航节点
# =========================
add_executable(navigation_dog src/navigation_dog.cpp)
target_include_directories(navigation_dog PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_compile_features(navigation_dog PUBLIC c_std_99 cxx_std_17)

# 链接 ROS 依赖
ament_target_dependencies(navigation_dog
  rclcpp
  std_msgs
  sensor_msgs
  nav_msgs
  tf2
)

# 链接自定义消息（确保头文件和库正确引入）
rosidl_get_typesupport_target(cpp_typesupport_target ${PROJECT_NAME} rosidl_typesupport_cpp)
target_link_libraries(navigation_dog "${cpp_typesupport_target}")

# 打点工具
add_executable(record_points src/record_points.cpp)
target_include_directories(record_points PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_compile_features(record_points PUBLIC c_std_99 cxx_std_17)
ament_target_dependencies(record_points
  rclcpp
  std_msgs
  nav_msgs
  tf2
)
target_link_libraries(record_points "${cpp_typesupport_target}")

# 测试节点
add_executable(test_nav_movement src/test_nav_movement.cpp)
target_include_directories(test_nav_movement PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_compile_features(test_nav_movement PUBLIC c_std_99 cxx_std_17)
ament_target_dependencies(test_nav_movement
  rclcpp
  std_msgs
  nav_msgs
  tf2
)
target_link_libraries(test_nav_movement "${cpp_typesupport_target}")

# 测试节点（增强版：PID + 死区 + 斜坡 + 稳态确认）
add_executable(test_nav_pid src/test_nav_pid.cpp)
target_include_directories(test_nav_pid PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_compile_features(test_nav_pid PUBLIC c_std_99 cxx_std_17)
ament_target_dependencies(test_nav_pid
  rclcpp
  std_msgs
  nav_msgs
  tf2
)
target_link_libraries(test_nav_pid "${cpp_typesupport_target}")

# =========================
# 兜底节点（放弃 OCR，点0 扫描后只取箱11、12）
# =========================
add_executable(dog_nav_fallback src/dog_nav_fallback.cpp)
target_include_directories(dog_nav_fallback PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_compile_features(dog_nav_fallback PUBLIC c_std_99 cxx_std_17)
ament_target_dependencies(dog_nav_fallback
  rclcpp
  std_msgs
  sensor_msgs
  nav_msgs
  tf2
)
target_link_libraries(dog_nav_fallback "${cpp_typesupport_target}")

# =========================
# 新机构节点（一次吸两箱，10 节点布局，config/task_race_2.yaml）
# =========================
add_executable(navigation_dog_2 src/navigation_dog_2.cpp)
target_include_directories(navigation_dog_2 PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_compile_features(navigation_dog_2 PUBLIC c_std_99 cxx_std_17)
ament_target_dependencies(navigation_dog_2
  rclcpp
  std_msgs
  sensor_msgs
  nav_msgs
  tf2
)
target_link_libraries(navigation_dog_2 "${cpp_typesupport_target}")

# =========================
# 打点工具（新机构 10 节点，输出 task_race_2.yaml）
# =========================
add_executable(record_points_2 src/record_points_2.cpp)
target_include_directories(record_points_2 PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_compile_features(record_points_2 PUBLIC c_std_99 cxx_std_17)
ament_target_dependencies(record_points_2
  rclcpp
  nav_msgs
  tf2
)

install(TARGETS navigation_dog navigation_dog_2 record_points record_points_2 test_nav_movement test_nav_pid dog_nav_fallback
  DESTINATION lib/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  set(ament_cmake_copyright_FOUND TRUE)
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()