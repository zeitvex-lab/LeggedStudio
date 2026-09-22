load("@integration//rules/utils:proto.bzl", "protobuf_utils")

package(default_visibility = ["//visibility:public"])

protobuf_utils(
    name = "mc_tools_cfg_utils",
    dep_protos = [
        "//aimdk/protocol/common:rpc_proto",
        "//aimdk/protocol/common:se3_pose_proto",
        "//aimdk/protocol/common:vec3_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/tools:mc_tools_cfg.proto",
    type_support_name = "aimdk_protocol_mc_tools_cfg",
)

protobuf_utils(
    name = "mc_tools_service_utils",
    dep_protos = [
        ":mc_tools_cfg_proto",
        "//aimdk/protocol/common:rpc_proto",
    ],
    is_rpc = True,
    proto = "@aimrt_protocol//aimdk/protocol/mc/tools:mc_tools_service.proto",
)
