load("@integration//rules/utils:proto.bzl", "protobuf_utils")

package(default_visibility = ["//visibility:public"])

protobuf_utils(
    name = "agi_claw_utils",
    dep_protos = [
    ],
    type_support_name = "aimdk_protocol_agi_claw",
    proto = "@aimrt_protocol//aimdk/protocol/hal/hand:agi_claw.proto",
)

protobuf_utils(
    name = "agi_hand_utils",
    dep_protos = [
    ],
    type_support_name = "aimdk_protocol_agi_hand",
    proto = "@aimrt_protocol//aimdk/protocol/hal/hand:agi_hand.proto",
)

protobuf_utils(
    name = "hand_channel_utils",
    dep_protos = [
        ":hand_proto",
        "//aimdk/protocol/common:header_proto",
    ],
    type_support_name = "aimdk_protocol_hand_channel",
    proto = "@aimrt_protocol//aimdk/protocol/hal/hand:hand_channel.proto",
)

protobuf_utils(
    name = "inspire_utils",
    dep_protos = [
    ],
    type_support_name = "aimdk_protocol_inspire",
    proto = "@aimrt_protocol//aimdk/protocol/hal/hand:inspire.proto",
)

protobuf_utils(
    name = "jodell_utils",
    dep_protos = [
    ],
    type_support_name = "aimdk_protocol_jodell",
    proto = "@aimrt_protocol//aimdk/protocol/hal/hand:jodell.proto",
)

protobuf_utils(
    name = "agi_o10_hand_utils",
    dep_protos = [
    ],
    type_support_name = "aimdk_protocol_agi_o10_hand",
    proto = "@aimrt_protocol//aimdk/protocol/hal/hand:agi_o10_hand.proto",
)

protobuf_utils(
    name = "hal_hand_service_utils",
    dep_protos = [
        ":hand_proto",
        "//aimdk/protocol/common:rpc_proto",
    ],
    is_rpc = True,
    proto = "@aimrt_protocol//aimdk/protocol/hal/hand:hal_hand_service.proto",
)

protobuf_utils(
    name = "hand_utils",
    dep_protos = [
        ":agi_claw_proto",
        ":agi_hand_proto",
        ":inspire_proto",
        ":jodell_proto",
        ":agi_o10_hand_proto",
        "//aimdk/protocol/common:header_proto",
        "//aimdk/protocol/common:rpc_proto",
    ],
    type_support_name = "aimdk_protocol_hand",
    proto = "@aimrt_protocol//aimdk/protocol/hal/hand:hand.proto",
)
