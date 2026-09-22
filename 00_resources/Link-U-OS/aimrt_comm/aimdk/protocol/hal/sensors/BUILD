load("@integration//rules/utils:proto.bzl", "protobuf_utils")
load("@integration//rules/utils:ros.bzl", "ros_utils")

package(default_visibility = ["//visibility:public"])

protobuf_utils(
    name = "cameras_intrinsic_utils",
    dep_protos = [
        "//aimdk/protocol/common:header_proto",
    ],
    is_rpc = True,
    proto = "@aimrt_protocol//aimdk/protocol/hal/sensors:cameras_intrinsic.proto",
)

protobuf_utils(
    name = "cameras_snapshot_utils",
    dep_protos = [
        "//aimdk/protocol/common:header_proto",
        "//aimdk/protocol/common:timestamp_proto",
    ],
    is_rpc = True,
    proto = "@aimrt_protocol//aimdk/protocol/hal/sensors:cameras_snapshot.proto",
)

protobuf_utils(
    name = "rs2_camera_utils",
    dep_protos = [
        ":cameras_intrinsic_proto",
    ],
    is_rpc = True,
    proto = "@aimrt_protocol//aimdk/protocol/hal/sensors:rs2_camera.proto",
)

protobuf_utils(
    name = "image_channel_utils",
    dep_protos = [
        "//aimdk/protocol/common:header_proto",
        "//aimdk/protocol/common:image_proto",
    ],
    is_rpc = True,
    proto = "@aimrt_protocol//aimdk/protocol/hal/sensors:image_channel.proto",
    rpc_need_type_support = True,
    type_support_name = "aimdk_protocol_image_channel",
)

protobuf_utils(
    name = "color_depth_image_channel_utils",
    dep_protos = [
        "//aimdk/protocol/common:header_proto",
        "//aimdk/protocol/common:image_proto",
    ],
    is_rpc = True,
    proto = "@aimrt_protocol//aimdk/protocol/hal/sensors:color_depth_image_channel.proto",
    rpc_need_type_support = True,
    type_support_name = "aimdk_protocol_color_depth_image_channel",
)

ros_utils(
    name = "sensors_msg_utils",
    interface_name = "sensors_msgs",
    msgs = [
        "@aimrt_protocol//aimdk/protocol/hal/sensors/msg:FootSensor.msg",
        "@aimrt_protocol//aimdk/protocol/hal/sensors/msg:FootSensorState.msg",
        "@aimrt_protocol//aimdk/protocol/hal/sensors/msg:ForceSensor.msg",
        "@aimrt_protocol//aimdk/protocol/hal/sensors/msg:ForceSensorState.msg",
        "@aimrt_protocol//aimdk/protocol/hal/sensors/msg:LivoxPoint.msg",
        "@aimrt_protocol//aimdk/protocol/hal/sensors/msg:LivoxPointCloud.msg",
    ],
    type_support_name = "aimdk_protocol_sensors_msgs",
    deps = [
        "@ros2_common_interfaces//:std_msgs",
        "@ros2_rcl_interfaces//:builtin_interfaces",
    ],
)
