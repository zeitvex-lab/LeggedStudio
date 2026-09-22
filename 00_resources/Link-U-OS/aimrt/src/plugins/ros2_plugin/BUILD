package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "aimrt_ros2_plugin",
    srcs = glob(
        ["**/*.cc"],
        exclude = ["**/*_test.cc"],
    ) + glob(
        ["**/*.h"],
        exclude = ["**/*_test.h"],
    ),
    linkshared = True,
    deps = [
        "//src/interface/aimrt_core_plugin_interface",
        "//src/protocols/plugins/ros2_plugin_proto/common/msg:ros2_plugin_proto_lib",
        "//src/protocols/plugins/ros2_plugin_proto/common/srv:aimrt_ros2_plugin_proto_rpc",
        "//src/runtime/core",
        "@ros2_rclcpp//:rclcpp",
    ],
)
