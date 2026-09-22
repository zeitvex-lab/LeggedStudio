load("@integration//rules/utils:proto.bzl", "protobuf_utils")

package(default_visibility = ["//visibility:public"])

protobuf_utils(
    name = "locomotion_utils",
    dep_protos = [
        "//aimdk/protocol/common:header_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/motion:locomotion.proto",
    type_support_name = "aimdk_protocol_locomotion",
)

protobuf_utils(
    name = "mc_adjust_utils",
    dep_protos = [
        "//aimdk/protocol/common:rpc_proto",
        "//aimdk/protocol/common:scalar_trajectory_proto",
        "//aimdk/protocol/common:se3_pose_proto",
        "//aimdk/protocol/mc/common:planning_proto",
        "//aimdk/protocol/mc/motion:motion_param_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/motion:mc_adjust.proto",
    type_support_name = "aimdk_protocol_mc_adjust",
)

protobuf_utils(
    name = "mc_motion_channel_utils",
    dep_protos = [
        ":locomotion_proto",
        ":waist_proto",
        "//aimdk/protocol/common:header_proto",
        "//aimdk/protocol/hal/hand:hand_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/motion:mc_motion_channel.proto",
    type_support_name = "aimdk_protocol_mc_motion_channel",
)

protobuf_utils(
    name = "motion_param_utils",
    dep_protos = [
        "//aimdk/protocol/common:se3_velocity_proto",
        "//aimdk/protocol/common:se3_acceleration_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/motion:motion_param.proto",
    type_support_name = "aimdk_protocol_motion_param",
)

protobuf_utils(
    name = "move_utils",
    dep_protos = [
        ":motion_param_proto",
        "//aimdk/protocol/common:header_proto",
        "//aimdk/protocol/common:scalar_trajectory_proto",
        "//aimdk/protocol/common:se3_pose_proto",
        "//aimdk/protocol/mc/common:arm_proto",
        "//aimdk/protocol/mc/common:move_pose_mode_proto",
        "//aimdk/protocol/mc/common:planning_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/motion:move.proto",
    type_support_name = "aimdk_protocol_move",
)

protobuf_utils(
    name = "movj_utils",
    dep_protos = [
        ":motion_param_proto",
        "//aimdk/protocol/common:header_proto",
        "//aimdk/protocol/mc/common:move_pose_mode_proto",
        "//aimdk/protocol/mc/common:planning_proto",
        "//aimdk/protocol/mc/data:joint_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/motion:movj.proto",
    type_support_name = "aimdk_protocol_movj",
)

protobuf_utils(
    name = "planning_utils",
    dep_protos = [
        ":motion_param_proto",
        "//aimdk/protocol/common:rpc_proto",
        "//aimdk/protocol/common:scalar_trajectory_proto",
        "//aimdk/protocol/common:se3_pose_proto",
        "//aimdk/protocol/common:joint_proto",
        "//aimdk/protocol/mc/common:planning_proto",
        "//aimdk/protocol/hal/hand:hand_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/motion:planning.proto",
    type_support_name = "aimdk_protocol_mc_motion_planning",
)

protobuf_utils(
    name = "stand_utils",
    dep_protos = [
        "//aimdk/protocol/common:header_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/motion:stand.proto",
    type_support_name = "aimdk_protocol_mc_motion_stand",
)

protobuf_utils(
    name = "waist_utils",
    dep_protos = [
        "//aimdk/protocol/common:rpc_proto",
        "//aimdk/protocol/common:scalar_trajectory_proto",
        "//aimdk/protocol/common:se3_pose_proto",
        "//aimdk/protocol/mc/common:planning_proto",
        "//aimdk/protocol/mc/motion:motion_param_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/motion:waist.proto",
    type_support_name = "aimdk_protocol_mc_motion_waist",
)

protobuf_utils(
    name = "collision_utils",
    dep_protos = [
        "//aimdk/protocol/common:header_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/motion:collision.proto",
    type_support_name = "aimdk_protocol_mc_motion_collision",
)

protobuf_utils(
    name = "state_notify_utils",
    dep_protos = [
        "//aimdk/protocol/common:header_proto",
    ],
    proto = "@aimrt_protocol//aimdk/protocol/mc/motion:state_notify.proto",
    type_support_name = "aimdk_protocol_mc_motion_state_notify",
)

protobuf_utils(
    name = "mc_motion_service_utils",
    dep_protos = [
        ":locomotion_proto",
        ":move_proto",
        ":movj_proto",
        ":planning_proto",
        ":stand_proto",
        ":mc_adjust_proto",
        ":collision_proto",
        ":state_notify_proto",
        "//aimdk/protocol/common:rpc_proto",
        "//aimdk/protocol/hal/hand:hand_proto",
        "//aimdk/protocol/hal/neck:neck_proto",
    ],
    is_rpc = True,
    proto = "@aimrt_protocol//aimdk/protocol/mc/motion:mc_motion_service.proto",
)
