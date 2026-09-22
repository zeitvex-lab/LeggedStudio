load("@integration//rules/utils:ros.bzl", "ros_utils")

package(default_visibility = ["//visibility:public"])

ros_utils(
    name = "get_latest_ball_utils",
    interface_name = "demo_msgs",
    msgs = [
        "@aimrt_protocol//ros2/demo/msg:Ball.msg",
    ],
    srv = "@aimrt_protocol//ros2/demo/srv:GetLatestBall.srv",
    type_support_name = "ros2_demo_msgs",
    deps = [
        "@ros2_common_interfaces//:std_msgs",
        "@ros2_rcl_interfaces//:builtin_interfaces",
    ],
)
