load("@integration//rules/utils:proto.bzl", "protobuf_utils")

package(default_visibility = ["//visibility:public"])


protobuf_utils(
    name = "process_health_channel_utils",
    dep_protos = [
         ":process_health_proto",
        "//aimdk/protocol/common:timestamp_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/hds/process:process_health_channel.proto",
    type_support_name = "aimdk_protocol_process_health_channel",
)


protobuf_utils(
    name = "process_health_utils",
    dep_protos = [
    ],
    proto = "@aimrt_protocol//aimdk/protocol/hds/process:process_health.proto",
    type_support_name = "aimdk_protocol_process_health",
)

protobuf_utils(
    name = "process_heartbeat_channel_utils",
    dep_protos = [
         ":process_heartbeat_proto",
        "//aimdk/protocol/common:timestamp_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/hds/process:process_heartbeat_channel.proto",
    type_support_name = "aimdk_protocol_process_heartbeat_channel",
)

protobuf_utils(
    name = "process_heartbeat_utils",
    dep_protos = [
    ],
    proto = "@aimrt_protocol//aimdk/protocol/hds/process:process_heartbeat.proto",
    type_support_name = "aimdk_protocol_process_heartbeat",
)
