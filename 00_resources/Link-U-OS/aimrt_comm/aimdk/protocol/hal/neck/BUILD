load("@integration//rules/utils:proto.bzl", "protobuf_utils")

package(default_visibility = ["//visibility:public"])

protobuf_utils(
    name = "neck_utils",
    dep_protos = [
        "//aimdk/protocol/common:header_proto",
        "//aimdk/protocol/common:joint_proto",
        "//aimdk/protocol/common:rpc_proto",
    ],
    type_support_name = "aimdk_protocol_neck",
    proto = "@aimrt_protocol//aimdk/protocol/hal/neck:neck.proto",
)

protobuf_utils(
    name = "hal_neck_service_utils",
    dep_protos = [
        "//aimdk/protocol/common:rpc_proto",
        "//aimdk/protocol/hal/neck:neck_proto",
    ],
    is_rpc = True,
    proto = "@aimrt_protocol//aimdk/protocol/hal/neck:hal_neck_service.proto",
)
