package(
    default_visibility = ["//visibility:public"],
)

proto_library(
    name = "image_proto",
    srcs = [
        "image.proto",
    ],
    deps = [
        "//src/protocols/pb/common:header_proto",
    ],
)

cc_proto_library(
    name = "image_cc_proto",
    deps = [":image_proto"],
)

proto_library(
    name = "imu_proto",
    srcs = [
        "imu.proto",
    ],
    deps = [
        "//src/protocols/pb/common:header_proto",
        "//src/protocols/pb/geometry:quaternion_proto",
        "//src/protocols/pb/geometry:vector3_proto",
    ],
)

cc_proto_library(
    name = "imu_cc_proto",
    deps = [":imu_proto"],
)

proto_library(
    name = "joint_state_proto",
    srcs = [
        "joint_state.proto",
    ],
    deps = [
        "//src/protocols/pb/common:header_proto",
    ],
)

cc_proto_library(
    name = "joint_state_cc_proto",
    deps = [":joint_state_proto"],
)

proto_library(
    name = "touch_sensor_state_proto",
    srcs = [
        "touch_sensor_state.proto",
    ],
    deps = [
        "//src/protocols/pb/common:header_proto",
    ],
)

cc_proto_library(
    name = "touch_sensor_state_cc_proto",
    deps = [":touch_sensor_state_proto"],
)

cc_binary(
    name = "aimrt_sensor_type_support",
    srcs = [
        "type_support_pkg_main.cc",
    ],
    linkshared = True,
    deps = [
        ":image_cc_proto",
        ":imu_cc_proto",
        ":joint_state_cc_proto",
        ":touch_sensor_state_cc_proto",
        "@aimrt//src/interface/aimrt_module_protobuf_interface",
        "@aimrt//src/interface/aimrt_type_support_pkg_c_interface",
    ],
)
