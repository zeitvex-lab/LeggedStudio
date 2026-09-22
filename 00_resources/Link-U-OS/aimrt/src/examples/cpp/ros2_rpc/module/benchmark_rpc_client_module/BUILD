package(default_visibility = ["//visibility:public"])

cc_library(
    name = "benchmark_rpc_client_module",
    srcs = ["benchmark_rpc_client_module.cc"],
    hdrs = ["benchmark_rpc_client_module.h"],
    deps = [
        "//src/interface/aimrt_module_cpp_interface",
        "//src/interface/aimrt_module_ros2_interface",
        "//src/protocols/ros2/example_ros2/common/srv:aimrt_example_ros2_rpc",
        "@yaml-cpp",
    ],
)
