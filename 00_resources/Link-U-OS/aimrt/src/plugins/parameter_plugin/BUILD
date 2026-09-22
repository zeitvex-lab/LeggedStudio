package(default_visibility = ["//visibility:public"])

cc_binary(
    name = "aimrt_parameter_plugin",
    srcs = glob(
        ["*.cc", "*.h"],
    ),
    linkshared = True,
    deps = [
        "//src/interface/aimrt_core_plugin_interface",
        "//src/runtime/core",
        "//src/protocols/plugins/parameter_plugin:aimrt_parameter_rpc"
    ],
)
