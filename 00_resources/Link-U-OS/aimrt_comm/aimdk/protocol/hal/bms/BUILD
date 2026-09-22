load("@integration//rules/utils:proto.bzl", "protobuf_utils")

package(default_visibility = ["//visibility:public"])

protobuf_utils(
    name = "bms_utils",
    dep_protos = [
        "//aimdk/protocol/common:rpc_proto",
    ],
    type_support_name = "aimdk_protocol_bms",
    proto = "@aimrt_protocol//aimdk/protocol/hal/bms:bms.proto",
)

protobuf_utils(
    name = "hal_bms_channel_utils",
    dep_protos = [
        ":bms_proto",
        "//aimdk/protocol/common:header_proto",
    ],
    type_support_name = "aimdk_protocol_hal_bms_channel",
    proto = "@aimrt_protocol//aimdk/protocol/hal/bms:hal_bms_channel.proto",
)

protobuf_utils(
    name = "hal_bms_service_utils",
    dep_protos = [
        ":bms_proto",
        "//aimdk/protocol/common:rpc_proto",
    ],
    is_rpc = True,
    proto = "@aimrt_protocol//aimdk/protocol/hal/bms:hal_bms_service.proto",
)
