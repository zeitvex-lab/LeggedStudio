load("@integration//rules/utils:ros.bzl", "ros_utils")
load("@integration//rules/utils:proto.bzl", "protobuf_utils")

package(default_visibility = ["//visibility:public"])

ros_utils(
    name = "power_msgs_utils",
    interface_name = "power_msgs",
    msgs = [
        "@aimrt_protocol//aimdk/protocol/hal/power/msg:PowerState.msg",
    ],
    type_support_name = "aimdk_protocol_power_msgs",
    deps = [
        "@ros2_common_interfaces//:std_msgs",
        "@ros2_rcl_interfaces//:builtin_interfaces",
    ],
)

protobuf_utils(
    name = "hal_power_service_utils",
    dep_protos = [
        "//aimdk/protocol/common:rpc_proto",
    ],
    is_rpc = True,
    proto = "@aimrt_protocol//aimdk/protocol/hal/power:hal_power_service.proto",
)
