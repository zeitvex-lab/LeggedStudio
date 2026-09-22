load("@integration//rules/utils:proto.bzl", "protobuf_utils")

package(default_visibility = ["//visibility:public"])

protobuf_utils(
    name = "hal_light_channel_utils",
    dep_protos = [
        "//aimdk/protocol/common:header_proto",
        "//aimdk/protocol/hal/light:light_proto",
    ],
    type_support_name = "aimdk_protocol_hal_light_channel",
    proto = "@aimrt_protocol//aimdk/protocol/hal/light:hal_light_channel.proto",
)

protobuf_utils(
    name = "light_utils",
    dep_protos = [
        "//aimdk/protocol/common:rpc_proto",
    ],
    type_support_name = "aimdk_protocol_light",
    proto = "@aimrt_protocol//aimdk/protocol/hal/light:light.proto",
)

protobuf_utils(
    name = "hal_light_service_utils",
    dep_protos = [
        ":light_proto",
        "//aimdk/protocol/common:rpc_proto",
    ],
    is_rpc = True,
    proto = "@aimrt_protocol//aimdk/protocol/hal/light:hal_light_service.proto",
)
