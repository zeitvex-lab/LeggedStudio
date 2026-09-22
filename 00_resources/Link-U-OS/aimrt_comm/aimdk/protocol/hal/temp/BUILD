load("@integration//rules/utils:proto.bzl", "protobuf_utils")
load("@integration//rules/utils:ros.bzl", "ros_utils")

package(default_visibility = ["//visibility:public"])

protobuf_utils(
    name = "hal_temp_channel_utils",
    dep_protos = [
        ":temp_proto",
        "//aimdk/protocol/common:header_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/hal/temp:hal_temp_channel.proto",
    type_support_name = "aimdk_protocol_hal_temp_channel",
)

protobuf_utils(
    name = "temp_utils",
    dep_protos = [
        "//aimdk/protocol/common:rpc_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/hal/temp:temp.proto",
    type_support_name = "aimdk_protocol_temp",
)

protobuf_utils(
    name = "hal_temp_service_utils",
    dep_protos = [
        ":temp_proto",
        "//aimdk/protocol/common:rpc_proto",
    ],
    is_rpc = True,
    proto = "@aimrt_protocol//aimdk/protocol/hal/temp:hal_temp_service.proto",
)

ros_utils(
    name = "temp_msgs_utils",
    interface_name = "temp_msgs",
    msgs = [
        "@aimrt_protocol//aimdk/protocol/hal/temp/msg:Temp.msg",
        "@aimrt_protocol//aimdk/protocol/hal/temp/msg:TempState.msg",
    ],
    type_support_name = "aimdk_protocol_temp_msgs",
    deps = [
        "@ros2_common_interfaces//:std_msgs",
    ],
)
