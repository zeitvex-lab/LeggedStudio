load("@integration//rules/utils:proto.bzl", "protobuf_utils")


package(
    default_visibility = ["//visibility:public"],
)

exports_files(["rpc.proto", "common.proto"])

proto_library(
    name = "benchmark_proto",
    srcs = [
        "benchmark.proto",
    ],
)

cc_proto_library(
    name = "benchmark_cc_proto",
    deps = [":benchmark_proto"],
)

proto_library(
    name = "common_proto",
    srcs = [
        "common.proto",
    ],
)

cc_proto_library(
    name = "common_cc_proto",
    deps = [":common_proto"],
)

proto_library(
    name = "event_proto",
    srcs = [
        "event.proto",
    ],
)

cc_proto_library(
    name = "event_cc_proto",
    deps = [":event_proto"],
)

cc_binary(
    name = "aimrt_example_type_support",
    srcs = [
        "type_support_pkg_main.cc",
    ],
    linkshared = True,
    deps = [
        ":benchmark_cc_proto",
        ":common_cc_proto",
        ":event_cc_proto",
        "@aimrt//src/interface/aimrt_module_protobuf_interface",
        "@aimrt//src/interface/aimrt_type_support_pkg_c_interface",
    ],
)
