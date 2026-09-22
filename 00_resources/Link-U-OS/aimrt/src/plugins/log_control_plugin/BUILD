package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "aimrt_log_control_plugin",
    srcs = glob(
        ["*.cc", "*.h"],
    ),
    linkshared = True,
    deps = [
        "//src/interface/aimrt_core_plugin_interface",
        "//src/runtime/core",
        "//src/protocols/plugins/log_control_plugin:aimrt_log_control_rpc",
    ],
)
