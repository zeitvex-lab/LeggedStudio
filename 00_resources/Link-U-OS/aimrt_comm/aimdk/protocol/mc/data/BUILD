load("@integration//rules/utils:proto.bzl", "protobuf_utils")

package(default_visibility = ["//visibility:public"])

protobuf_utils(
    name = "arm_utils",
    dep_protos = [
        "//aimdk/protocol/common:header_proto",
        "//aimdk/protocol/mc/common:arm_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/data:arm.proto",
    type_support_name = "aimdk_protocol_mc_data_arm",
)

protobuf_utils(
    name = "joint_utils",
    dep_protos = [
        "//aimdk/protocol/common:header_proto",
        "//aimdk/protocol/common:joint_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/data:joint.proto",
    type_support_name = "aimdk_protocol_mc_joint",
)

protobuf_utils(
    name = "mgpt_utils",
    dep_protos = [
        "//aimdk/protocol/common:header_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/data:mgpt.proto",
    type_support_name = "aimdk_protocol_mc_mgpt",
)

protobuf_utils(
    name = "planning_utils",
    dep_protos = [
        "//aimdk/protocol/common:header_proto",
        "//aimdk/protocol/mc/common:planning_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/data:planning.proto",
    type_support_name = "aimdk_protocol_mc_planning",
)

protobuf_utils(
    name = "tcp_utils",
    dep_protos = [
        "//aimdk/protocol/common:header_proto",
        "//aimdk/protocol/common:se3_pose_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/data:tcp.proto",
    type_support_name = "aimdk_protocol_mc_tcp",
)

protobuf_utils(
    name = "mc_data_service_utils",
    dep_protos = [
        ":joint_proto",
        ":mgpt_proto",
        ":planning_proto",
        ":tcp_proto",
        "//aimdk/protocol/common:rpc_proto",
        "//aimdk/protocol/hal/hand:hand_proto",
        "//aimdk/protocol/hal/neck:neck_proto",
    ],
    is_rpc = True,
    proto = "@aimrt_protocol//aimdk/protocol/mc/data:mc_data_service.proto",
)
