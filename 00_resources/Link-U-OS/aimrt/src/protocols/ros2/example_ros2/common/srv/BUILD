load("@integration//rules/utils:ros.bzl", "ros_utils")

package(
    default_visibility = ["//visibility:public"],
)

ros_utils(
    name = "example_ros2_utils",
    interface_name = "example_ros2",
    only_aimrt_rpc = True,
    srv = "//src/protocols/ros2/example_ros2/srv:RosTestRpc.srv",
    deps = [
        "@ros2_rcl_interfaces//:builtin_interfaces",
    ],
)
