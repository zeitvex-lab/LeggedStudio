package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "normal_ros2_chn_publisher_app",
    srcs = ["main.cc"],
    deps = [
        "//src/interface/aimrt_module_ros2_interface",
        "//src/protocols/ros2/example_ros2/common/msg:example_ros2_lib",
        "//src/runtime/core",
        "@com_github_gflags_gflags//:gflags",
    ],
)
