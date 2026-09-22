load("@integration//rules/utils:proto.bzl", "protobuf_utils")

package(default_visibility = ["//visibility:public"])

protobuf_utils(
    name = "mc_force_primitive_utils",
    dep_protos = [
        "//aimdk/protocol/common:rpc_proto",
        "//google/protobuf:any_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/force:mc_force_primitive.proto",
    type_support_name = "aimdk_protocol_mc_force_primitive",
)

protobuf_utils(
    name = "mc_force_service_utils",
    dep_protos = [
        ":mc_force_primitive_proto",
        "//aimdk/protocol/common:rpc_proto",
    ],
    is_rpc = True,
    proto = "@aimrt_protocol//aimdk/protocol/mc/force:mc_force_service.proto",
)
