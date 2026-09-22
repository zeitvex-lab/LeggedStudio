package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "aimrt_topic_logger_plugin",
    srcs = glob(
        [
            "*.cc",
            "*.h",
        ],
    ),
    linkshared = True,
    deps = [
        "//src/interface/aimrt_core_plugin_interface",
        "//src/interface/aimrt_module_protobuf_interface",
        "//src/protocols/plugins/topic_logger_plugin:topic_logger_plugin_cc_proto",
        "//src/runtime/core",
    ],
)
