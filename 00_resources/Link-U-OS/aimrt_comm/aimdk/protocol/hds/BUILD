load("@integration//rules/utils:proto.bzl", "protobuf_utils")
load("@integration//rules/utils:ros.bzl", "ros_utils")

package(default_visibility = ["//visibility:public"])

protobuf_utils(
    name = "alert_utils",
    dep_protos = [
        ":exception_proto",
        "//aimdk/protocol/common:header_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/hds:alert.proto",
    type_support_name = "aimdk_protocol_alert",
)

protobuf_utils(
    name = "alert_channel_utils",
    dep_protos = [
        ":alert_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/hds:alert_channel.proto",
    type_support_name = "aimdk_protocol_alert_channel",
)

protobuf_utils(
    name = "exception_utils",
    dep_protos = [
        "//aimdk/protocol/common:timestamp_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/hds:exception.proto",
    type_support_name = "aimdk_protocol_exception",
)

protobuf_utils(
    name = "exception_channel_utils",
    dep_protos = [
        ":exception_proto",
        "//aimdk/protocol/common:timestamp_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/hds:exception_channel.proto",
    type_support_name = "aimdk_protocol_exception_channel",
)

protobuf_utils(
    name = "health_utils",
    dep_protos = [
        "//aimdk/protocol/common:header_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/hds:health.proto",
    type_support_name = "aimdk_protocol_health",
)

protobuf_utils(
    name = "health_channel_utils",
    dep_protos = [
        ":alert_proto",
        ":health_proto",
        "//aimdk/protocol/common:header_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/hds:health_channel.proto",
    type_support_name = "aimdk_protocol_health_channel",
)

protobuf_utils(
    name = "fallback_channel_utils",
    dep_protos = [
        "//aimdk/protocol/common:header_proto",
        "//aimdk/protocol/common:timestamp_proto",
        ":alert_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/hds:fallback_channel.proto",
    type_support_name = "aimdk_protocol_fallback_channel",
)

protobuf_utils(
    name = "system_status_utils",
    dep_protos = [
    ],
    proto = "@aimrt_protocol//aimdk/protocol/hds:system_status.proto",
    type_support_name = "aimdk_protocol_system_status",
)

protobuf_utils(
    name = "hds_service_utils",
    dep_protos = [
        ":alert_proto",
        "//aimdk/protocol/common:header_proto",
        "//aimdk/protocol/common:rpc_proto",
    ],
    is_rpc = True,
    proto = "@aimrt_protocol//aimdk/protocol/hds:hds_service.proto",
)

ros_utils(
    name = "hds_msgs_utils",
    interface_name = "hds_msgs",
    msgs = [
        "@aimrt_protocol//aimdk/protocol/hds:Exception.msg",
        "@aimrt_protocol//aimdk/protocol/hds:ExceptionChannel.msg",
    ],
    type_support_name = "aimdk_protocol_hds_msgs",
    deps = [
        "@ros2_rcl_interfaces//:builtin_interfaces",
    ],
)
