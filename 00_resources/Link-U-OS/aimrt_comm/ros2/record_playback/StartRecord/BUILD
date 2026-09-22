load("@integration//rules/utils:ros.bzl", "ros_utils")

package(default_visibility = ["//visibility:public"])

ros_utils(
    name = "start_record_utils",
    interface_name = "record_playback_msgs",
    msgs = [
    ],
    srv = "@aimrt_protocol//ros2/record_playback/srv:StartRecord.srv",
    deps = [
        "@ros2_rcl_interfaces//:builtin_interfaces",
    ],
)
