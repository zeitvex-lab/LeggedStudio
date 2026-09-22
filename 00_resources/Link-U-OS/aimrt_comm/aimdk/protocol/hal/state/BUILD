load("@integration//rules/utils:proto.bzl", "protobuf_utils")

package(default_visibility = ["//visibility:public"])

protobuf_utils(
    name = "emergency_state_utils",
    dep_protos = [
        "//aimdk/protocol/common:rpc_proto",
    ],
    type_support_name = "aimdk_protocol_emergency_state",
    proto = "@aimrt_protocol//aimdk/protocol/hal/state:emergency_state.proto",
)

protobuf_utils(
    name = "hal_state_channel_utils",
    dep_protos = [
        ":emergency_state_proto",
        "//aimdk/protocol/common:header_proto",
    ],
    type_support_name = "aimdk_protocol_hal_state_channel",
    proto = "@aimrt_protocol//aimdk/protocol/hal/state:hal_state_channel.proto",
)

protobuf_utils(
    name = "operation_mode_utils",
    dep_protos = [
        "//aimdk/protocol/common:rpc_proto",
    ],
    type_support_name = "aimdk_protocol_operation_mode",
    proto = "@aimrt_protocol//aimdk/protocol/hal/state:operation_mode.proto",
)

protobuf_utils(
    name = "hal_emergency_service_utils",
    dep_protos = [
        ":emergency_state_proto",
        "//aimdk/protocol/common:rpc_proto",
    ],
    is_rpc = True,
    proto = "@aimrt_protocol//aimdk/protocol/hal/state:hal_emergency_service.proto",
)

protobuf_utils(
    name = "hal_operation_mode_service_utils",
    dep_protos = [
        ":operation_mode_proto",
        "//aimdk/protocol/common:rpc_proto",
    ],
    is_rpc = True,
    proto = "@aimrt_protocol//aimdk/protocol/hal/state:hal_operation_mode_service.proto",
)

protobuf_utils(
    name = "mcu_state_utils",
    dep_protos = [
        "//aimdk/protocol/common:header_proto",
    ],
    type_support_name = "aimdk_protocol_mcu_state",
    proto = "@aimrt_protocol//aimdk/protocol/hal/state:mcu_state.proto",
)