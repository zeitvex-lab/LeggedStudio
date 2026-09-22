package(
    default_visibility = ["//visibility:public"],
)

proto_library(
    name = "topic_logger_plugin_proto",
    srcs = [
        "topic_logger.proto",
    ],
    deps = [
        "//src/protocols/pb/common:header_proto",
    ],
)

cc_proto_library(
    name = "topic_logger_plugin_cc_proto",
    deps = [":topic_logger_plugin_proto"],
)

cc_binary(
    name = "aimrt_topic_logger_type_support",
    srcs = [
        "type_support_pkg_main.cc",
    ],
    deps = [
        "//src/interface/aimrt_type_support_pkg_c_interface",
        "//src/interface/aimrt_module_protobuf_interface",
        ":topic_logger_plugin_cc_proto",
    ],
    linkshared = True,
)
