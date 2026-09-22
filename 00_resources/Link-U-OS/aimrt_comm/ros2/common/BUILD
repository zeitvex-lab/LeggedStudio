load("@integration//rules/utils:ros.bzl", "ros_utils")

package(default_visibility = ["//visibility:public"])

ros_utils(
    name = "qrcode_utils",
    interface_name = "common_msgs",
    msgs = [
        "@aimrt_protocol//ros2/common:QRCode.msg",
    ],
    type_support_name = "ros2_common",
    deps = [
        "@ros2_common_interfaces//:geometry_msgs",
        "@ros2_rcl_interfaces//:builtin_interfaces",
    ],
)
