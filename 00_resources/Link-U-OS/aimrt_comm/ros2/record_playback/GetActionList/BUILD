load("@integration//rules/utils:ros.bzl", "ros_utils")

package(default_visibility = ["//visibility:public"])

ros_utils(
    name = "get_action_list_utils",
    interface_name = "record_playback_msgs",
    msgs = [
        "@aimrt_protocol//ros2/record_playback/msg:ActionInfo.msg",
    ],
    srv = "@aimrt_protocol//ros2/record_playback/srv:GetActionList.srv",
    deps = [
        "@ros2_rcl_interfaces//:builtin_interfaces",
    ], 
)
