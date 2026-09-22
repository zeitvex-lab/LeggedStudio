load("@integration//rules/utils:proto.bzl", "protobuf_utils")

package(default_visibility = ["//visibility:public"])

protobuf_utils(
    name = "ball_utils",
    dep_protos = [
    ],
    proto = "@aimrt_protocol//aimdk/protocol/demo:ball.proto",
    type_support_name = "aimdk_protocol_ball",
)

protobuf_utils(
    name = "demo_channel_utils",
    dep_protos = [
        ":ball_proto",
        "//aimdk/protocol/common:header_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/demo:demo_channel.proto",
    type_support_name = "aimdk_protocol_demo_channel",
)

protobuf_utils(
    name = "demo_service_utils",
    dep_protos = [
        ":ball_proto",
        "//aimdk/protocol/common:header_proto",
    ],
    is_rpc = True,
    proto = "@aimrt_protocol//aimdk/protocol/demo:demo_service.proto",
    type_support_name = "aimdk_protocol_demo_service",
)

