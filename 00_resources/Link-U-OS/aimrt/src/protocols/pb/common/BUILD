package(
    default_visibility = ["//visibility:public"],
)

proto_library(
    name = "error_proto",
    srcs = [
        "error.proto",
    ],
)

cc_proto_library(
    name = "error_cc_proto",
    deps = [":error_proto"],
)

proto_library(
    name = "header_proto",
    srcs = [
        "header.proto",
    ],
)

cc_proto_library(
    name = "header_cc_proto",
    deps = [":header_proto"],
)

proto_library(
    name = "module_proto",
    srcs = [
        "module.proto",
    ],
    deps = [
        ":header_proto",
    ],
)

cc_proto_library(
    name = "module_cc_proto",
    deps = [":module_proto"],
)

cc_binary(
    name = "aimrt_common_type_support",
    srcs = [
        "type_support_pkg_main.cc",
    ],
    linkshared = True,
    deps = [
        ":error_cc_proto",
        ":header_cc_proto",
        ":module_cc_proto",
        "@aimrt//src/interface/aimrt_module_protobuf_interface",
        "@aimrt//src/interface/aimrt_type_support_pkg_c_interface",
    ],
)
