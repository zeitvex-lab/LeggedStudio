package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "normal_ros2_rpc_server_app",
    srcs = ["main.cc"],
    deps = [
        "//src/interface/aimrt_module_ros2_interface",
        "//src/protocols/ros2/example_ros2/common/srv:aimrt_example_ros2_rpc",
        "//src/runtime/core",
        "@com_github_gflags_gflags//:gflags",
    ],
)
