package(default_visibility = ["//visibility:public"])

cc_library(
    name = "benchmark_publisher_module",
    srcs = ["benchmark_publisher_module.cc"],
    hdrs = ["benchmark_publisher_module.h"],
    deps = [
        "//src/interface/aimrt_module_cpp_interface",
        "//src/interface/aimrt_module_ros2_interface",
        "//src/protocols/ros2/example_ros2/common/msg:example_ros2_lib",
        "@yaml-cpp",
    ],
)
