load("@integration//rules/utils:ros2_package.bzl", "ros2_colcon_package")
load("@integration//rules/utils:pkg_lib.bzl", "pkg_lib")

package(
    default_visibility = ["//visibility:public"],
)

# 打包用于 CMake 构建的 ROS2 消息(msg)和服务(srv)定义文件
pkg_lib(
    name = "ros2_source_files_tar",
    srcs = [
        "CMakeLists.txt",
        "ros2/CMakeLists.txt",
        "aimdk/protocol/CMakeLists.txt",
        "//aimdk/protocol/hal/joint:ros2_files",
        "//aimdk/protocol/hal/joint/msg:ros2_files",
        "//aimdk/protocol/hal/pose:ros2_files",
        "//aimdk/protocol/hal/pose/msg:ros2_files",
        "//aimdk/protocol/hal/power:ros2_files",
        "//aimdk/protocol/hal/power/msg:ros2_files",
        "//aimdk/protocol/hal/sensors:ros2_files",
        "//aimdk/protocol/hal/sensors/msg:ros2_files",
        "//aimdk/protocol/hal/temp:ros2_files",
        "//aimdk/protocol/hal/temp/msg:ros2_files",
        "//aimdk/protocol/hds:ros2_files",
        "//ros2/common:ros2_files",
        "//ros2/demo:ros2_files",
        "//ros2/demo/msg:ros2_files",
        "//ros2/demo/srv:ros2_files",
        "//ros2/record_playback:ros2_files",
        "//ros2/record_playback/msg:ros2_files",
        "//ros2/record_playback/srv:ros2_files",
    ] + glob([
        "cmake/**",
    ]),
)

# 构建x86_64架构的ROS2消息包
ros2_colcon_package(
    name = "ros2_package_x86",
    aarch_type = "x86_64",
    src_tar = ":ros2_source_files_tar",
)

# 构建aarch64架构的ROS2消息包
ros2_colcon_package(
    name = "ros2_package_aarch64",
    aarch_type = "aarch64",
    src_tar = ":ros2_source_files_tar",
)
