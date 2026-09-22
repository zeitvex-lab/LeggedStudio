load("@integration//rules/utils:proto.bzl", "protobuf_utils")

package(default_visibility = ["//visibility:public"])

protobuf_utils(
    name = "aim_master_utils",
    dep_protos = [
        "//aimdk/protocol/common:header_proto",
        "//aimdk/protocol/common:timestamp_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/remote:aim_master.proto",
    type_support_name = "aimdk_protocol_aim_master",
)

protobuf_utils(
    name = "mc_remote_channel_utils",
    dep_protos = [
        ":aim_master_proto",
        ":quest_pro_controller_proto",
        ":remote_command_proto",
        ":universal_gamepad_proto",
        "//aimdk/protocol/common:header_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/remote:mc_remote_channel.proto",
    type_support_name = "aimdk_protocol_mc_remote_channel",
)

protobuf_utils(
    name = "quest_pro_controller_utils",
    dep_protos = [
        "//aimdk/protocol/common:se3_pose_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/remote:quest_pro_controller.proto",
    type_support_name = "aimdk_protocol_quest_pro_controller",
)

protobuf_utils(
    name = "remote_command_utils",
    dep_protos = [
        "//aimdk/protocol/common:header_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/remote:remote_command.proto",
    type_support_name = "aimdk_protocol_remote_command",
)

protobuf_utils(
    name = "universal_gamepad_utils",
    dep_protos = [
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/remote:universal_gamepad.proto",
    type_support_name = "aimdk_protocol_universal_gamepad",
)

protobuf_utils(
    name = "mc_remote_service_utils",
    dep_protos = [
        ":aim_master_proto",
        ":remote_command_proto",
        "//aimdk/protocol/common:rpc_proto",
    ],
    is_rpc = True,
    proto = "@aimrt_protocol//aimdk/protocol/mc/remote:mc_remote_service.proto",
)
