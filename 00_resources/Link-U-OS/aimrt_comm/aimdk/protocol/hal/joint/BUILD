load("@integration//rules/utils:proto.bzl", "protobuf_utils")
load("@integration//rules/utils:ros.bzl", "ros_utils")

package(default_visibility = ["//visibility:public"])

protobuf_utils(
    name = "joint_channel_utils",
    dep_protos = [
        "//aimdk/protocol/common:header_proto",
        "//aimdk/protocol/common:joint_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/hal/joint:joint_channel.proto",
    type_support_name = "aimdk_protocol_joint_channel",
)

ros_utils(
    name = "joint_msg_utils",
    interface_name = "joint_msgs",
    msgs = [
        "@aimrt_protocol//aimdk/protocol/hal/joint/msg:Command.msg",
        "@aimrt_protocol//aimdk/protocol/hal/joint/msg:JointCommand.msg",
        "@aimrt_protocol//aimdk/protocol/hal/joint/msg:JointState.msg",
        "@aimrt_protocol//aimdk/protocol/hal/joint/msg:State.msg",
    ],
    type_support_name = "aimdk_protocol_joint_msgs",
    deps = [
        "@ros2_common_interfaces//:std_msgs",
        "@ros2_rcl_interfaces//:builtin_interfaces",
    ],
)
