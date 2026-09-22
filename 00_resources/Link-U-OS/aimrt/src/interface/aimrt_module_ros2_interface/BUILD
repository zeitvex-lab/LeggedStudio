package(default_visibility = ["//visibility:public"])

cc_library(
    name = "aimrt_module_ros2_interface",
    hdrs = glob(["**/*.h"]),
    deps = [
        "//src/common/ros2_util",
        "//src/interface/aimrt_module_cpp_interface",
        "@ros2_rclcpp//:rclcpp",
    ],
    includes = [".."],
)
