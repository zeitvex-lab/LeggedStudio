load("@integration//rules/utils:proto.bzl", "protobuf_utils")

package(default_visibility = ["//visibility:public"])

protobuf_utils(
    name = "jaka_ctrl_utils",
    dep_protos = [
        "//aimdk/protocol/common:rpc_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/base:jaka_ctrl.proto",
    type_support_name = "aimdk_protocol_jaka_ctrl",
)

protobuf_utils(
    name = "mc_base_channel_utils",
    dep_protos = [
        ":mc_state_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/base:mc_base_channel.proto",
    type_support_name = "aimdk_protocol_mc_base_channel",
)

protobuf_utils(
    name = "mc_base_utils",
    dep_protos = [
        "//aimdk/protocol/common:control_source_proto",
        "//aimdk/protocol/common:rpc_proto",
        "//aimdk/protocol/mc/action:mc_action_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/base:mc_state.proto",
    type_support_name = "aimdk_protocol_mc_state",
)

protobuf_utils(
    name = "work_mode_utils",
    dep_protos = [
        "//aimdk/protocol/common:control_source_proto",
        "//aimdk/protocol/common:rpc_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/base:work_mode.proto",
    type_support_name = "aimdk_protocol_work_mode",
)

protobuf_utils(
    name = "mc_base_service_utils",
    dep_protos = [
        ":jaka_ctrl_proto",
        ":mc_state_proto",
        ":work_mode_proto",
    ],
    is_rpc = True,
    proto = "@aimrt_protocol//aimdk/protocol/mc/base:mc_base_service.proto",
)
