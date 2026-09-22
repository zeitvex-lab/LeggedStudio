load("@integration//rules/utils:proto.bzl", "protobuf_utils")

package(default_visibility = ["//visibility:public"])

protobuf_utils(
    name = "box_utils",
    dep_protos = [
    ],
    type_support_name = "aimdk_protocol_box",
    proto = "@aimrt_protocol//aimdk/protocol/common:box.proto",
)

protobuf_utils(
    name = "control_source_utils",
    dep_protos = [
    ],
    type_support_name = "aimdk_protocol_control_source",
    proto = "@aimrt_protocol//aimdk/protocol/common:control_source.proto",
)

protobuf_utils(
    name = "header_utils",
    dep_protos = [
        ":control_source_proto",
        ":timestamp_proto",
    ],
    type_support_name = "aimdk_protocol_header",
    proto = "@aimrt_protocol//aimdk/protocol/common:header.proto",
)

protobuf_utils(
    name = "image_utils",
    dep_protos = [
        ":timestamp_proto",
    ],
    type_support_name = "aimdk_protocol_image",
    proto = "@aimrt_protocol//aimdk/protocol/common:image.proto",
)

protobuf_utils(
    name = "io_packet_utils",
    dep_protos = [
        ":timestamp_proto",
    ],
    type_support_name = "aimdk_protocol_io_packet",
    proto = "@aimrt_protocol//aimdk/protocol/common:io_packet.proto",
)

protobuf_utils(
    name = "joint_utils",
    dep_protos = [
    ],
    type_support_name = "aimdk_protocol_joint",
    proto = "@aimrt_protocol//aimdk/protocol/common:joint.proto",
)

protobuf_utils(
    name = "mocapjointstate_utils",
    dep_protos = [
        ":quaternion_proto",
        ":vec3_proto",
    ],
    type_support_name = "aimdk_protocol_mocapjointstate",
    proto = "@aimrt_protocol//aimdk/protocol/common:mocapjointstate.proto",
)

protobuf_utils(
    name = "odometry_utils",
    dep_protos = [
        ":se3_pose_proto",
        ":timestamp_proto",
        ":twist_proto",
    ],
    type_support_name = "aimdk_protocol_odometry",
    proto = "@aimrt_protocol//aimdk/protocol/common:odometry.proto",
)

protobuf_utils(
    name = "pixel_pose_utils",
    dep_protos = [
    ],
    type_support_name = "aimdk_protocol_pixel_pose",
    proto = "@aimrt_protocol//aimdk/protocol/common:pixel_pose.proto",
)

protobuf_utils(
    name = "qr_pose_utils",
    dep_protos = [
        ":se3_pose_proto",
    ],
    type_support_name = "aimdk_protocol_qr_pose",
    proto = "@aimrt_protocol//aimdk/protocol/common:qr_pose.proto",
)

protobuf_utils(
    name = "quaternion_utils",
    dep_protos = [
    ],
    type_support_name = "aimdk_protocol_quaternion",
    proto = "@aimrt_protocol//aimdk/protocol/common:quaternion.proto",
)

protobuf_utils(
    name = "rpc_utils",
    dep_protos = [
        ":header_proto",
        ":timestamp_proto",
    ],
    type_support_name = "aimdk_protocol_rpc",
    proto = "@aimrt_protocol//aimdk/protocol/common:rpc.proto",
)

protobuf_utils(
    name = "rpy_utils",
    dep_protos = [
    ],
    type_support_name = "aimdk_protocol_rpy",
    proto = "@aimrt_protocol//aimdk/protocol/common:rpy.proto",
)

protobuf_utils(
    name = "scalar_trajectory_utils",
    dep_protos = [
    ],
    type_support_name = "aimdk_protocol_scalar_trajectory",
    proto = "@aimrt_protocol//aimdk/protocol/common:scalar_trajectory.proto",
)

protobuf_utils(
    name = "se2_acceleration_utils",
    dep_protos = [
        ":vec2_proto",
    ],
    type_support_name = "aimdk_protocol_se2_acceleration",
    proto = "@aimrt_protocol//aimdk/protocol/common:se2_acceleration.proto",
)

protobuf_utils(
    name = "se2_pose_utils",
    dep_protos = [
        ":vec2_proto",
    ],
    type_support_name = "aimdk_protocol_se2_pose",
    proto = "@aimrt_protocol//aimdk/protocol/common:se2_pose.proto",
)

protobuf_utils(
    name = "se2_velocity_utils",
    dep_protos = [
        ":vec2_proto",
    ],
    type_support_name = "aimdk_protocol_se2_velocity",
    proto = "@aimrt_protocol//aimdk/protocol/common:se2_velocity.proto",
)

protobuf_utils(
    name = "se3_acceleration_utils",
    dep_protos = [
        ":quaternion_proto",
        ":vec3_proto",
    ],
    type_support_name = "aimdk_protocol_se3_acceleration",
    proto = "@aimrt_protocol//aimdk/protocol/common:se3_acceleration.proto",
)

protobuf_utils(
    name = "se3_pose_utils",
    dep_protos = [
        ":quaternion_proto",
        ":rpy_proto",
        ":vec3_proto",
    ],
    type_support_name = "aimdk_protocol_se3_pose",
    proto = "@aimrt_protocol//aimdk/protocol/common:se3_pose.proto",
)

protobuf_utils(
    name = "se3_trajectory_utils",
    dep_protos = [
        ":se3_acceleration_proto",
        ":se3_pose_proto",
        ":se3_velocity_proto",
        ":timestamp_proto",
    ],
    type_support_name = "aimdk_protocol_se3_trajectory",
    proto = "@aimrt_protocol//aimdk/protocol/common:se3_trajectory.proto",
)

protobuf_utils(
    name = "se3_velocity_utils",
    dep_protos = [
        ":vec3_proto",
    ],
    type_support_name = "aimdk_protocol_se3_velocity",
    proto = "@aimrt_protocol//aimdk/protocol/common:se3_velocity.proto",
)

protobuf_utils(
    name = "timestamp_utils",
    dep_protos = [
    ],
    type_support_name = "aimdk_protocol_timestamp",
    proto = "@aimrt_protocol//aimdk/protocol/common:timestamp.proto",
)

protobuf_utils(
    name = "twist_utils",
    dep_protos = [
        ":timestamp_proto",
        ":vec3_proto",
    ],
    type_support_name = "aimdk_protocol_twist",
    proto = "@aimrt_protocol//aimdk/protocol/common:twist.proto",
)

protobuf_utils(
    name = "vec2_utils",
    dep_protos = [
    ],
    type_support_name = "aimdk_protocol_vec2",
    proto = "@aimrt_protocol//aimdk/protocol/common:vec2.proto",
)

protobuf_utils(
    name = "vec3_utils",
    dep_protos = [
    ],
    type_support_name = "aimdk_protocol_vec3",
    proto = "@aimrt_protocol//aimdk/protocol/common:vec3.proto",
)

protobuf_utils(
    name = "wrench_utils",
    dep_protos = [
        ":timestamp_proto",
        ":vec3_proto",
    ],
    type_support_name = "aimdk_protocol_wrench",
    proto = "@aimrt_protocol//aimdk/protocol/common:wrench.proto",
)


protobuf_utils(
    name = "common_utils",
    dep_protos = [
        ":box_proto",
        ":control_source_proto",
        ":header_proto",
        ":image_proto",
        ":io_packet_proto",
        ":joint_proto",
        ":mocapjointstate_proto",
        ":odometry_proto",
        ":pixel_pose_proto",
        ":qr_pose_proto",
        ":quaternion_proto",
        ":rpc_proto",
        ":rpy_proto",
        ":scalar_trajectory_proto",
        ":se2_acceleration_proto",
        ":se2_pose_proto",
        ":se2_velocity_proto",
        ":se3_acceleration_proto",
        ":se3_pose_proto",
        ":se3_trajectory_proto",
        ":se3_velocity_proto",
        ":timestamp_proto",
        ":twist_proto",
        ":vec2_proto",
        ":vec3_proto",
        ":wrench_proto",
    ],
    type_support_name = "aimdk_protocol_common",
    proto = "@aimrt_protocol//aimdk/protocol/common:common.proto",
)
