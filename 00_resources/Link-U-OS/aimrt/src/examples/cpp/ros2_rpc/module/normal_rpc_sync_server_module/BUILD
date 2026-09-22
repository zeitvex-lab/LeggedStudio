package(default_visibility = ["//visibility:public"])

cc_library(
    name = "normal_rpc_sync_server_module",
    srcs = glob(["*.cc"]),
    hdrs = glob(["*.h"]),
    deps = [
        "//src/interface/aimrt_module_cpp_interface",
        "//src/interface/aimrt_module_ros2_interface",
        "//src/protocols/ros2/example_ros2/common/srv:aimrt_example_ros2_rpc",
        "@yaml-cpp",
    ],
)
