load("@integration//rules/utils:proto.bzl", "protobuf_utils")

package(default_visibility = ["//visibility:public"])

protobuf_utils(
    name = "monitor_service_utils",
    dep_protos = [
        "//aimdk/protocol/common:header_proto",
        "//aimdk/protocol/common:rpc_proto",
        "//aimdk/protocol/hds/process:process_heartbeat_proto",
    ],
    is_rpc = True,
    proto = "@aimrt_protocol//aimdk/protocol/hds/monitor:monitor_service.proto",
)
