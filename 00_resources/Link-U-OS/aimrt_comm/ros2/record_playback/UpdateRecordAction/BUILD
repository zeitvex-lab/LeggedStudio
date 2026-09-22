load("@integration//rules/utils:ros.bzl", "ros_utils")

package(default_visibility = ["//visibility:public"])

ros_utils(
    name = "update_record_action_utils",
    interface_name = "record_playback_msgs",
    msgs = [
        "@aimrt_protocol//ros2/record_playback/msg:TopicMeta.msg",
    ],
    srv = "@aimrt_protocol//ros2/record_playback/srv:UpdateRecordAction.srv",
    deps = [
        "@ros2_rcl_interfaces//:builtin_interfaces",
    ], 
)
