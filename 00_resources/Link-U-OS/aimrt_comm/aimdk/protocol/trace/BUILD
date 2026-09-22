load("@integration//rules/utils:proto.bzl", "protobuf_utils")

package(default_visibility = ["//visibility:public"])

protobuf_utils(
    name = "event_channel_utils",
    dep_protos = [
        "//aimdk/protocol/common:header_proto",
        "//aimdk/protocol/common:timestamp_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/trace:event_channel.proto",
    type_support_name = "aimdk_protocol_event_channel",
)
