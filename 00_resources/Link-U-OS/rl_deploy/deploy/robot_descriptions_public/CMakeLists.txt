cmake_minimum_required(VERSION 3.10.2)
project(robot_descriptions_public)
find_package(ament_cmake REQUIRED)

install(
  DIRECTORY launch urdf mesh convex rviz
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
