package(
    default_visibility = ["//visibility:public"],
)

proto_library(
    name = "joint_command_proto",
    srcs = [
        "joint_command.proto",
    ],
    deps = [
        "//src/protocols/pb/common:header_proto",
    ],
)

cc_proto_library(
    name = "joint_command_cc_proto",
    deps = [":joint_command_proto"],
)

cc_binary(
    name = "aimrt_actuator_type_support",
    srcs = [
        "type_support_pkg_main.cc",
    ],
    deps = [
        "//src/interface/aimrt_type_support_pkg_c_interface",
        "//src/interface/aimrt_module_protobuf_interface",
        ":joint_command_cc_proto",
    ],
    linkshared = True,
)
