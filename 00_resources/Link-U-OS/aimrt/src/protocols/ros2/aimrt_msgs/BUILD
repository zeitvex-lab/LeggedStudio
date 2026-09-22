load(
    "@com_github_mvukov_rules_ros2//ros2:interfaces.bzl",
    "cpp_ros2_interface_library",
    "ros2_interface_library",
)
load("@com_github_mvukov_rules_ros2//ros2:cc_defs.bzl", "ros2_cpp_library")
load("@integration//rules/rpc:ros2_rpc.bzl", "aimrt_cc_ros2_rpc")

package(default_visibility = ["//visibility:public"])


ros2_interface_library(
    name = "ros2_aimrt_msgs_interface",
    srcs = [
        "msg/JointCommand.msg",
        "msg/JointCommandArray.msg",
        "msg/JointState.msg",
        "msg/JointStateArray.msg",
        "msg/MessageHeader.msg",
        "msg/TouchSensorState.msg",
        "msg/TouchSensorStateArray.msg",
    ],
    deps = [
        "@ros2_rcl_interfaces//:builtin_interfaces",
    ],
)

cpp_ros2_interface_library(
    name = "ros2_aimrt_msgs_cc_interface",
    deps = [":ros2_aimrt_msgs_interface"],
)

ros2_cpp_library(
    name = "ros2_aimrt_msgs_cc_lib",
    srcs = [],
    deps = [
        ":ros2_aimrt_msgs_cc_interface",
        "@ros2_rclcpp//:rclcpp",
    ],
)

cc_binary(
    name = "aimrt_ros2_aimrt_msgs_type_support",
    srcs = [
        "type_support_pkg_main.cc",
    ],
    deps = [
        "@aimrt//src/interface/aimrt_type_support_pkg_c_interface",
        "@aimrt//src/interface/aimrt_module_ros2_interface",
        ":ros2_aimrt_msgs_cc_lib"
    ],
    linkshared = True,
    
)

