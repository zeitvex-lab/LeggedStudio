load("@integration//rules/utils:proto.bzl", "protobuf_utils")

package(default_visibility = ["//visibility:public"])

protobuf_utils(
    name = "foot_kine_utils",
    dep_protos = [
        "//aimdk/protocol/common:se3_pose_proto",
        "//aimdk/protocol/common:se3_trajectory_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/kinematics:foot_kine.proto",
    type_support_name = "aimdk_protocol_foot_kine",
)

protobuf_utils(
    name = "kine_forward_utils",
    dep_protos = [
        "//aimdk/protocol/common:header_proto",
        "//aimdk/protocol/common:se3_pose_proto",
        "//aimdk/protocol/mc/common:arm_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/kinematics:kine_forward.proto",
    type_support_name = "aimdk_protocol_kine_forward",
)

protobuf_utils(
    name = "kine_inverse_utils",
    dep_protos = [
        "//aimdk/protocol/common:header_proto",
        "//aimdk/protocol/common:se3_pose_proto",
        "//aimdk/protocol/mc/common:arm_proto",
        "//aimdk/protocol/mc/data:joint_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/kinematics:kine_inverse.proto",
    type_support_name = "aimdk_protocol_kine_inverse",
)

protobuf_utils(
    name = "mc_kinematics_channel_utils",
    dep_protos = [
        ":foot_kine_proto",
        "//aimdk/protocol/common:header_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/kinematics:mc_kinematics_channel.proto",
    type_support_name = "aimdk_protocol_mc_kinematics_channel",
)

protobuf_utils(
    name = "mc_kinematics_service_utils",
    dep_protos = [
        ":kine_forward_proto",
        ":kine_inverse_proto",
    ],
    is_rpc = True,
    proto = "@aimrt_protocol//aimdk/protocol/mc/kinematics:mc_kinematics_service.proto",
)
