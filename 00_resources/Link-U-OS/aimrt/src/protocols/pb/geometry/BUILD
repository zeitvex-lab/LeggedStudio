package(
    default_visibility = ["//visibility:public"],
)

proto_library(
    name = "quaternion_proto",
    srcs = [
        "quaternion.proto",
    ],
    deps = [
        "//src/protocols/pb/common:header_proto",
    ],
)

cc_proto_library(
    name = "quaternion_cc_proto",
    deps = [":quaternion_proto"],
)

proto_library(
    name = "vector3_proto",
    srcs = [
        "vector3.proto",
    ],
    deps = [
        "//src/protocols/pb/common:header_proto",
    ],
)

cc_proto_library(
    name = "vector3_cc_proto",
    deps = [":vector3_proto"],
)

cc_binary(
    name = "aimrt_geometry_type_support",
    srcs = [
        "type_support_pkg_main.cc",
    ],
    linkshared = True,
    deps = [
        ":quaternion_cc_proto",
        ":vector3_cc_proto",
        "@aimrt//src/interface/aimrt_module_protobuf_interface",
        "@aimrt//src/interface/aimrt_type_support_pkg_c_interface",
    ],
)
