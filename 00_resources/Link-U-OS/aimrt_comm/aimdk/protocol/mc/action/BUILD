load("@integration//rules/utils:proto.bzl", "protobuf_utils")

package(default_visibility = ["//visibility:public"])

protobuf_utils(
    name = "mc_action_utils",
    dep_protos = [
        ":mc_action_cmd_proto",
        "//aimdk/protocol/common:header_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/action:mc_action.proto",
    type_support_name = "aimdk_protocol_mc_action",
)

protobuf_utils(
    name = "mc_action_cmd_utils",
    dep_protos = [
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/action:mc_action_cmd.proto",
    type_support_name = "aimdk_protocol_mc_action_cmd",
)

protobuf_utils(
    name = "mc_action_service_utils",
    dep_protos = [
        ":mc_action_proto",
        "//aimdk/protocol/common:rpc_proto",
    ],
    is_rpc = True,
    proto = "@aimrt_protocol//aimdk/protocol/mc/action:mc_action_service.proto",
    type_support_name = "aimdk_protocol_mc_action_service",
)
